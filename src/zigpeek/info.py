"""Runtime report for ``zigpeek info``.

Prints how to use the zigpeek skill, then the resolved ``zigpeek`` / ``zig``
binaries and the Zig version this invocation would use for docs.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as pkg_version
from importlib.resources import files
from pathlib import Path

from zigpeek.fetch import bundled_path_for, cache_dir_for, default_cache_root, docs_slug
from zigpeek.libdir import probe_zig, resolve_lib_dir, zig_binary
from zigpeek.version import DEFAULT_ZIG_VERSION, resolve_version

USAGE_GUIDE = """\
# zigpeek

A Python+wasmtime CLI that drives the official autodoc WASM. `search` /
`get` read the local compiler's `lib/` when `zig` is on PATH (or `$ZIG` /
`$ZIGPEEK_ZIG`); otherwise they use a `sources.tar` (bundle, cache, or
ziglang.org). Output is markdown.

## Setup (run once per agent session/sandbox)

```sh
uv tool install zigpeek                    # enough if the sandbox has zig
uv tool install "zigpeek[offline]"         # bundles 0.16.0 when it does not
```

## Usage

```sh
# Reprint this guide plus binary paths and the active Zig version
zigpeek info

# Search the stdlib
zigpeek search ArrayList --limit 10

# Get full docs for a stdlib item
zigpeek get std.ArrayList

# Get the source file containing an item
zigpeek get std.ArrayList --source-file

# List all builtin functions
zigpeek builtins list

# Look up a builtin (by name or keyword)
zigpeek builtins get atomic
```

## When to use which command

| Need | Command |
|------|---------|
| See usage, binary paths, and the active Zig version | `zigpeek info` |
| Discover stdlib symbols matching a keyword | `zigpeek search <q>` |
| Read full docs + signature for a known FQN | `zigpeek get <fqn>` |
| Read the full source file (terse docstring; want invariants, internals, or per-field implementation) | `zigpeek get <fqn> --source-file` |
| Browse all `@`-builtins | `zigpeek builtins list` |
| Look up a specific `@builtin` (accepts `atomic` or `@atomic`) | `zigpeek builtins get <q>` |
| Warm cache before going offline | `zigpeek prefetch` |
| Run several lookups in one process (cheap) | `zigpeek batch` |

## Batching multiple lookups

Each invocation pays ~1 s of Python+wasmtime startup. For more than two lookups, use `zigpeek batch` — it reuses the WASM instance and parsed sources across commands.

```sh
zigpeek batch <<'EOF'
search ArrayList --limit 5
get std.ArrayList
get std.ArrayList --source-file
builtins get atomic
EOF
```

Each command's output is framed with a `===> <command>` separator. Per-line failures are reported inline and **do not abort the batch**; the exit code is the worst across all lines (`0` if all succeeded). `prefetch` and nested `batch` are rejected — run them outside.

Use `zigpeek batch -f commands.txt` to read from a file instead of stdin. Blank lines and lines starting with `#` are ignored.

**Reach for `--source-file` early** when:

- The docstring is one line or missing.
- The page lists a method signature but elides the body (e.g. `MultiArrayList.items` shows the prototype but the per-field pointer math from `ptrs[@intFromEnum(field)]` only lives in the source).
- You need invariants, error sets, or how a private field is computed.

## Finding nested types

Inner types live under the **defining module's path**, not the re-export. `std.MultiArrayList` is a re-export from `std.multi_array_list`; its inner `Slice` type only resolves at the defining path:

```sh
zigpeek get std.multi_array_list.MultiArrayList.Slice   # works
zigpeek get std.MultiArrayList.Slice                    # not found
```

If `search` only surfaces a re-export and `get` 404s on the inner type, re-run `get` with the module path.

## Version override

Defaults to the `zig` on PATH (or `$ZIG` / `$ZIGPEEK_ZIG`). If no compiler
is found, defaults to `0.16.0`. Override with:

```sh
zigpeek search ArrayList --version 0.15.1
ZIGPEEK_VERSION=master zigpeek search ArrayList
zigpeek search ArrayList --lib-dir /path/to/zig/lib
```

`info` accepts the same `--version`, `--lib-dir`, and `--cache-dir` flags
so you can see what a later `search` / `get` would resolve to.

## Exit codes

- `0` — success (markdown on stdout)
- `1` — bad input or "not found" (message on stderr)
- `2` — network/cache failure (message on stderr)

## Troubleshooting

- **`Declaration "..." not found`** — the FQN is wrong. Two things to try: (1) `zigpeek search` to discover the canonical name; (2) if you searched a re-export (e.g. `std.MultiArrayList`), retry `get` against the defining module path (e.g. `std.multi_array_list.MultiArrayList`).
- **`network/cache error`** — no `zig` on PATH and no `[offline]` bundle / cache. Install Zig, or `uv tool install "zigpeek[offline]"`, or run `zigpeek prefetch` on a networked host.
"""


@dataclass(frozen=True)
class RuntimeInfo:
    zigpeek_version: str
    zigpeek_exe: str | None
    zig_exe: str | None
    zig_version: str | None
    zig_lib_dir: str | None
    zig_usable: bool
    docs_version: str
    docs_version_reason: str
    stdlib_kind: str
    stdlib_detail: str
    cache_root: str
    wasm_path: str
    offline_installed: bool


def _zigpeek_version() -> str:
    try:
        return pkg_version("zigpeek")
    except PackageNotFoundError:
        return "unknown"


def _zigpeek_exe() -> str | None:
    found = shutil.which("zigpeek")
    if found:
        return str(Path(found).resolve())
    argv0 = Path(sys.argv[0]).expanduser()
    try:
        if argv0.exists():
            return str(argv0.resolve())
    except OSError:
        pass
    return sys.argv[0] or None


def _offline_installed() -> bool:
    try:
        files("zigpeek_offline")
    except (ModuleNotFoundError, FileNotFoundError):
        return False
    return True


def _version_reason(cli_version: str | None, *, has_local_zig: bool) -> str:
    if cli_version is not None:
        return "pinned by --version (local lib/ skipped)"
    if os.environ.get("ZIGPEEK_VERSION"):
        return "pinned by $ZIGPEEK_VERSION (local lib/ skipped)"
    if has_local_zig:
        return "from local zig"
    return f"fallback; no local zig (default {DEFAULT_ZIG_VERSION})"


def _stdlib_source(
    *,
    docs_version: str,
    lib_dir: Path | None,
    cache_dir: str | None,
) -> tuple[str, str]:
    if lib_dir is not None:
        path = Path(lib_dir)
        exists = "exists" if path.exists() else "missing"
        return "local compiler lib/", f"{path} ({exists})"

    bundled = bundled_path_for(docs_version, "sources.tar")
    if bundled.is_file():
        return "offline bundle", str(bundled)

    cached = cache_dir_for(docs_version, cache_dir) / "sources.tar"
    if cached.is_file():
        return "XDG cache", str(cached)

    slug = docs_slug(docs_version)
    return (
        "download on first use",
        f"https://ziglang.org/documentation/{slug}/std/sources.tar "
        f"(then {cache_dir_for(docs_version, cache_dir) / 'sources.tar'})",
    )


def collect_runtime_info(
    *,
    version: str | None = None,
    lib_dir: str | None = None,
    cache_dir: str | None = None,
) -> RuntimeInfo:
    probed = probe_zig()
    version_is_explicit = version is not None or bool(os.environ.get("ZIGPEEK_VERSION"))
    docs_version = resolve_version(version)
    resolved_lib = resolve_lib_dir(lib_dir, auto=not version_is_explicit)
    stdlib_kind, stdlib_detail = _stdlib_source(
        docs_version=docs_version,
        lib_dir=resolved_lib,
        cache_dir=cache_dir,
    )
    cache_root = Path(cache_dir) if cache_dir else default_cache_root()
    wasm = Path(str(files("zigpeek").joinpath("_vendor", "main.wasm")))
    return RuntimeInfo(
        zigpeek_version=_zigpeek_version(),
        zigpeek_exe=_zigpeek_exe(),
        zig_exe=probed.exe if probed is not None else zig_binary(),
        zig_version=probed.version if probed is not None else None,
        zig_lib_dir=str(probed.lib_dir) if probed is not None else None,
        zig_usable=probed is not None,
        docs_version=docs_version,
        docs_version_reason=_version_reason(version, has_local_zig=probed is not None),
        stdlib_kind=stdlib_kind,
        stdlib_detail=stdlib_detail,
        cache_root=str(cache_root),
        wasm_path=str(wasm),
        offline_installed=_offline_installed(),
    )


def render_environment(info: RuntimeInfo) -> str:
    zigpeek_bin = info.zigpeek_exe or "(not found on PATH)"
    if info.zig_usable:
        zig_lines = (
            f"  binary:   {info.zig_exe}\n"
            f"  version:  {info.zig_version}\n"
            f"  lib/:     {info.zig_lib_dir}"
        )
    elif info.zig_exe:
        zig_lines = (
            f"  binary:   {info.zig_exe}\n"
            f"  version:  (unusable; `zig env` failed)\n"
            f"  lib/:     (unknown)"
        )
    else:
        zig_lines = (
            "  binary:   (not found; checked $ZIGPEEK_ZIG, $ZIG, then PATH)\n"
            "  version:  (none)\n"
            "  lib/:     (none)"
        )
    offline = "installed" if info.offline_installed else "not installed"
    return (
        "## Environment\n"
        "\n"
        "zigpeek:\n"
        f"  version:  {info.zigpeek_version}\n"
        f"  binary:   {zigpeek_bin}\n"
        "\n"
        "zig (compiler on this machine):\n"
        f"{zig_lines}\n"
        "\n"
        "docs this invocation would use:\n"
        f"  version:  {info.docs_version}  ({info.docs_version_reason})\n"
        f"  stdlib:   {info.stdlib_kind}\n"
        f"            {info.stdlib_detail}\n"
        f"  cache:    {info.cache_root}\n"
        f"  wasm:     {info.wasm_path}\n"
        f"  offline:  {offline}\n"
    )


def render_info(info: RuntimeInfo) -> str:
    return f"{USAGE_GUIDE.rstrip()}\n\n---\n\n{render_environment(info)}"
