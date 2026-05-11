"""argparse entrypoint for `zigpeek`. Five stdlib/builtin lookup subcommands
plus a `prefetch` helper for offline-first workflows and a `batch` runner
that amortizes Python+wasmtime startup across many lookups.

Exit codes:
  0 — success (markdown on stdout)
  1 — bad input or "not found" (message on stderr)
  2 — network or cache failure (message on stderr)

For `batch`, the exit code is the maximum exit code seen across the
input lines, so a single not-found does not mask a later cache error.
"""

import argparse
import functools
import io
import shlex
import sys
from importlib.resources import files
from pathlib import Path

import httpx
import wasmtime

from zigpeek import builtins as builtins_mod
from zigpeek.fetch import (
    fetch_langref_html,
    fetch_sources_tar,
    langref_url,
    prefetch as fetch_prefetch,
)
from zigpeek.stdlib import render_get_item, render_search
from zigpeek.version import resolve_version
from zigpeek.wasm import WasmStd

_BATCH_DISALLOWED = frozenset({"batch", "prefetch"})


def _err(msg: str, code: int) -> int:
    print(msg, file=sys.stderr)
    return code


def _wrap_errors(fn):
    """Translate the two exception families every command shares into the
    documented exit codes. Keeps the per-command bodies focused on the
    happy path."""

    @functools.wraps(fn)
    def inner(args: argparse.Namespace) -> int:
        try:
            return fn(args)
        except (httpx.HTTPError, OSError) as e:
            return _err(f"network/cache error: {e}", 2)
        except (wasmtime.WasmtimeError, RuntimeError) as e:
            return _err(
                f"data error: {e}\n"
                "The cached or bundled sources.tar may be corrupt. "
                "Try `zigpeek prefetch --refresh`.",
                2,
            )

    return inner


def _vendor_wasm_bytes() -> bytes:
    wasm = files("zigpeek").joinpath("_vendor", "main.wasm")
    if not wasm.is_file():
        raise FileNotFoundError(
            "main.wasm not found inside the zigpeek package "
            "(expected at zigpeek/_vendor/main.wasm). "
            "See vendor/PROVENANCE.md for build instructions."
        )
    return wasm.read_bytes()


@functools.lru_cache(maxsize=4)
def _load_std(version: str, refresh: bool, cache_dir: str | None) -> WasmStd:
    sources = fetch_sources_tar(version, refresh=refresh, cache_dir=cache_dir)
    return WasmStd(_vendor_wasm_bytes(), sources)


@functools.lru_cache(maxsize=4)
def _load_builtins(
    version: str, refresh: bool, cache_dir: str | None
) -> tuple[list[builtins_mod.BuiltinFunction], str]:
    html = fetch_langref_html(version, refresh=refresh, cache_dir=cache_dir)
    base = langref_url(version)
    return builtins_mod.parse_builtin_functions_html(html, link_base_url=base), base


@_wrap_errors
def _cmd_search(args: argparse.Namespace) -> int:
    if not args.query:
        return _err("query cannot be empty", 1)
    version = resolve_version(args.version)
    std = _load_std(version, args.refresh, args.cache_dir)
    sys.stdout.write(render_search(std, args.query, limit=args.limit))
    sys.stdout.write("\n")
    return 0


@_wrap_errors
def _cmd_get(args: argparse.Namespace) -> int:
    if not args.fqn:
        return _err("fully-qualified name cannot be empty", 1)
    version = resolve_version(args.version)
    std = _load_std(version, args.refresh, args.cache_dir)
    md = render_get_item(std, args.fqn, get_source_file=args.source_file)
    if md.startswith("# Error"):
        print(md, file=sys.stderr)
        return 1
    sys.stdout.write(md)
    sys.stdout.write("\n")
    return 0


@_wrap_errors
def _cmd_builtins_list(args: argparse.Namespace) -> int:
    version = resolve_version(args.version)
    fns, base = _load_builtins(version, args.refresh, args.cache_dir)
    lines = "\n".join(f"- {fn.signature}" for fn in fns)
    sys.stdout.write(
        f"Available {len(fns)} builtin functions "
        f"(full docs: {base}):\n\n{lines}\n"
    )
    return 0


@_wrap_errors
def _cmd_builtins_get(args: argparse.Namespace) -> int:
    if not args.query:
        return _err("query cannot be empty", 1)
    version = resolve_version(args.version)
    fns, _ = _load_builtins(version, args.refresh, args.cache_dir)
    ranked = builtins_mod.rank_builtin_functions(fns, args.query)
    if not ranked:
        return _err(
            f'No builtin functions found matching "{args.query}". '
            "Try `zigpeek builtins list` to see all functions.",
            1,
        )
    chunks = [
        f"**{fn.func}**\n```zig\n{fn.signature}\n```\n\n{fn.docs}"
        for fn in ranked
    ]
    body = "\n\n---\n\n".join(chunks)
    if len(ranked) == 1:
        sys.stdout.write(body + "\n")
    else:
        sys.stdout.write(f"Found {len(ranked)} matching functions:\n\n{body}\n")
    return 0


@_wrap_errors
def _cmd_prefetch(args: argparse.Namespace) -> int:
    version = resolve_version(args.version)
    paths = fetch_prefetch(version, refresh=args.refresh, cache_dir=args.cache_dir)
    sys.stdout.write(
        f"Prefetched docs for Zig {version}:\n"
        f"  sources.tar  → {paths['sources.tar']}\n"
        f"  langref.html → {paths['langref.html']}\n"
    )
    return 0


def _read_batch_lines(args: argparse.Namespace) -> list[str]:
    if args.file:
        text = args.file.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    return text.splitlines()


def _run_captured(parser: argparse.ArgumentParser, tokens: list[str]) -> tuple[
    int, str, str
]:
    """Parse + dispatch a batch line, capturing its stdout/stderr so the
    parent batch loop can frame each command's output."""
    out, err = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        try:
            sub_args = parser.parse_args(tokens)
        except SystemExit as se:
            # argparse exits 2 for usage errors; map to 1 (bad input) so the
            # batch exit code reserves 2 for real cache/network failures.
            code = 0 if se.code == 0 else 1
            return code, out.getvalue(), err.getvalue()
        code = sub_args.func(sub_args)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return code, out.getvalue(), err.getvalue()


def _cmd_batch(args: argparse.Namespace) -> int:
    parser = build_parser()
    worst = 0
    first = True
    for raw in _read_batch_lines(args):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as e:
            if not first:
                sys.stdout.write("\n")
            sys.stdout.write(f"===> {line}\n# Error\nunparseable line: {e}\n")
            worst = max(worst, 1)
            first = False
            continue
        if not tokens:
            continue
        if tokens[0] in _BATCH_DISALLOWED:
            if not first:
                sys.stdout.write("\n")
            sys.stdout.write(
                f"===> {line}\n# Error\n"
                f"`{tokens[0]}` is not allowed inside batch.\n"
            )
            worst = max(worst, 1)
            first = False
            continue
        code, out, err = _run_captured(parser, tokens)
        if not first:
            sys.stdout.write("\n")
        sys.stdout.write(f"===> {line}\n")
        sys.stdout.write(out)
        if err:
            sys.stdout.write(err)
        worst = max(worst, code)
        first = False
    return worst


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--version", default=None, help="Zig version (default: 0.16.0)")
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-download of cached resources",
    )
    p.add_argument(
        "--cache-dir",
        default=None,
        help=(
            "Cache directory root (overrides ZIGPEEK_CACHE_DIR; "
            "default: /tmp/zigpeek-cache)"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zigpeek", description="Zig 0.16 docs CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="Search the standard library")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=20)
    _add_common(p_search)
    p_search.set_defaults(func=_cmd_search)

    p_get = sub.add_parser("get", help="Get docs for a fully-qualified stdlib name")
    p_get.add_argument("fqn")
    p_get.add_argument(
        "--source-file",
        action="store_true",
        help="Return the entire source file for the item",
    )
    _add_common(p_get)
    p_get.set_defaults(func=_cmd_get)

    p_builtins = sub.add_parser("builtins", help="Builtin function lookups")
    builtins_sub = p_builtins.add_subparsers(dest="builtins_cmd", required=True)

    p_blist = builtins_sub.add_parser("list", help="List all builtin functions")
    _add_common(p_blist)
    p_blist.set_defaults(func=_cmd_builtins_list)

    p_bget = builtins_sub.add_parser("get", help="Look up a builtin by name/keyword")
    p_bget.add_argument("query")
    _add_common(p_bget)
    p_bget.set_defaults(func=_cmd_builtins_get)

    p_pre = sub.add_parser(
        "prefetch",
        help="Download sources.tar + langref.html so other commands run offline",
    )
    _add_common(p_pre)
    p_pre.set_defaults(func=_cmd_prefetch)

    p_batch = sub.add_parser(
        "batch",
        help=(
            "Run many lookups in one process; reads one command per line "
            "from stdin (or -f FILE) and frames each output with `===> <cmd>`"
        ),
    )
    p_batch.add_argument(
        "-f",
        "--file",
        type=Path,
        default=None,
        help="Read commands from FILE instead of stdin",
    )
    p_batch.set_defaults(func=_cmd_batch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
