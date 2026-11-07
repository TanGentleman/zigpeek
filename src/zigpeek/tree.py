"""Walk every public decl under `std` once per Zig version and cache it as
`<cache>/<version>/map/tree-<source>.json` for `zigpeek map`."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import deque
from pathlib import Path
from typing import Callable

from zigpeek.fetch import cache_dir_for
from zigpeek.stdlib import (
    CAT_ALIAS,
    CAT_CONTAINER,
    CAT_ERROR_SET,
    CAT_FUNCTION,
    CAT_GLOBAL_CONST,
    CAT_GLOBAL_VARIABLE,
    CAT_NAMESPACE,
    CAT_PRIMITIVE,
    CAT_TYPE,
    CAT_TYPE_FUNCTION,
    CAT_TYPE_TYPE,
)
from zigpeek.wasm import WasmStd

SCHEMA = 1
MAX_DEPTH = 8
KIND_NAMES = {
    CAT_NAMESPACE: "namespace",
    CAT_CONTAINER: "type",
    CAT_GLOBAL_VARIABLE: "var",
    CAT_FUNCTION: "fn",
    CAT_PRIMITIVE: "const",
    CAT_ERROR_SET: "error_set",
    CAT_GLOBAL_CONST: "const",
    CAT_ALIAS: "alias",
    CAT_TYPE: "type",
    CAT_TYPE_TYPE: "type",
    CAT_TYPE_FUNCTION: "type_fn",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _first_line(doc_html: str) -> str:
    text = _WS_RE.sub(" ", html.unescape(_TAG_RE.sub("", doc_html))).strip()
    return text.split(". ")[0][:160]


def _resolve_alias(std: WasmStd, decl: int) -> int:
    seen: set[int] = set()
    while std.categorize_decl(decl, 0) == CAT_ALIAS and decl not in seen:
        seen.add(decl)
        nxt = std.get_aliasee()
        if nxt is None:
            break
        decl = nxt
    return decl


def walk_tree(std: WasmStd) -> list[dict]:
    """Every public decl reachable from `std`, breadth-first, each one named
    by the path it was reached through.

    Aliases resolve to one decl, so each decl appears once, under its
    shallowest path. Canonical names are not usable here: an alias often
    resolves into a file namespace that `std` never exposes, which would
    leave rows such as `std.hash.wyhash.Wyhash` with no parent row and so
    no place in the tree. Breadth-first also picks the name a reader
    expects -- `std.hash.Wyhash`, not a deep alias of the same struct."""
    rows: list[dict] = []
    seen: set[int] = set()
    queue = deque([(std.find_decl("std"), "std", 0)])
    while queue:
        decl, fqn, depth = queue.popleft()
        if decl is None:
            continue
        decl = _resolve_alias(std, decl)
        if decl in seen or depth > MAX_DEPTH:
            continue
        seen.add(decl)
        cat = std.categorize_decl(decl, 0)
        rows.append(
            {
                "fqn": fqn,
                "kind": KIND_NAMES.get(cat, "other"),
                "depth": depth,
                "doc": _first_line(std.decl_docs_html(decl, True)),
            }
        )
        if cat in (CAT_NAMESPACE, CAT_CONTAINER):
            members = std.namespace_members(decl, False)
            queue.extend((m, f"{fqn}.{std.decl_name(m)}", depth + 1) for m in members)
    return rows


def _source_key(lib_dir: str | None) -> str:
    return str(Path(lib_dir).resolve()) if lib_dir else "ziglang.org"


def tree_path(version: str, cache_dir: str | None, lib_dir: str | None) -> Path:
    """One file per (version, source), so a local `lib/` and the
    ziglang.org docs for the same version don't evict each other."""
    tag = hashlib.sha256(_source_key(lib_dir).encode()).hexdigest()[:12]
    return cache_dir_for(version, cache_dir) / "map" / f"tree-{tag}.json"


def load_or_walk(
    version: str,
    cache_dir: str | None,
    lib_dir: str | None,
    load_std: Callable[[], WasmStd],
    refresh: bool = False,
    on_walk: Callable[[], None] | None = None,
) -> list[dict]:
    """Cached rows for this version + source, walking the WASM on a miss.
    `refresh` (or an older schema) forces a re-walk."""
    path = tree_path(version, cache_dir, lib_dir)
    source = _source_key(lib_dir)
    if not refresh:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema") == SCHEMA and data.get("source") == source:
                return data["rows"]
        except (OSError, ValueError, KeyError, AttributeError):
            pass
    if on_walk is not None:
        on_walk()
    rows = walk_tree(load_std())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"schema": SCHEMA, "version": version, "source": source, "rows": rows}),
        encoding="utf-8",
    )
    tmp.replace(path)
    return rows
