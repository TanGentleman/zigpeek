import asyncio
import json
import threading
import time

import pytest

from tests.test_cli import SKILL_ROOT, run_cli
from zigpeek import tree as tree_mod
from zigpeek.cli import _vendor_wasm_bytes
from zigpeek.libdir import pack_lib_dir
from zigpeek.wasm import WasmStd

MINI_LIB = SKILL_ROOT / "tests" / "fixtures" / "mini-lib"
ALIAS_LIB = SKILL_ROOT / "tests" / "fixtures" / "alias-lib"


def _mini_std() -> WasmStd:
    return WasmStd(_vendor_wasm_bytes(), pack_lib_dir(MINI_LIB))


def test_walk_tree_mini_lib():
    rows = tree_mod.walk_tree(_mini_std())
    by_fqn = {r["fqn"]: r for r in rows}
    assert rows[0]["fqn"] == "std"
    assert by_fqn["std.Answer"]["kind"] == "namespace"
    assert by_fqn["std.Answer.value"]["doc"] == "The meaning of life."
    assert by_fqn["std.Answer.value"]["depth"] == 2
    assert by_fqn["std.greet"]["kind"] == "fn"


def test_walk_names_decls_by_the_path_std_exposes():
    """`std.Thing` aliases a struct in a file `std` keeps private. Naming the
    row after the canonical `std.hidden.Thing` leaves it with no parent row,
    so it joins no card and no filter ever matches it."""
    std = WasmStd(_vendor_wasm_bytes(), pack_lib_dir(ALIAS_LIB))
    rows = tree_mod.walk_tree(std)
    fqns = {r["fqn"] for r in rows}
    assert {"std.Thing", "std.Thing.inner"} <= fqns
    assert "std.hidden.Thing" not in fqns
    orphans = [r["fqn"] for r in rows if r["fqn"] != "std" and r["fqn"].rpartition(".")[0] not in fqns]
    assert orphans == []


def test_load_or_walk_caches_per_source(tmp_path):
    calls = []

    def load():
        calls.append(1)
        return _mini_std()

    rows = tree_mod.load_or_walk("0.16.0", str(tmp_path), str(MINI_LIB), load)
    again = tree_mod.load_or_walk("0.16.0", str(tmp_path), str(MINI_LIB), load)
    assert rows == again and len(calls) == 1

    path = tree_mod.tree_path("0.16.0", str(tmp_path), str(MINI_LIB))
    data = json.loads(path.read_text())
    assert data["schema"] == tree_mod.SCHEMA and data["version"] == "0.16.0"

    # A different source for the same version gets its own file.
    other = tree_mod.tree_path("0.16.0", str(tmp_path), None)
    assert other != path

    tree_mod.load_or_walk("0.16.0", str(tmp_path), str(MINI_LIB), load, refresh=True)
    assert len(calls) == 2

    data["schema"] = 0
    path.write_text(json.dumps(data))
    tree_mod.load_or_walk("0.16.0", str(tmp_path), str(MINI_LIB), load)
    assert len(calls) == 3


def test_map_rejects_unknown_fqn(tmp_path):
    proc = run_cli(
        "map", "std.nope", "--lib-dir", str(MINI_LIB), "--cache-dir", str(tmp_path),
        env={"ZIGPEEK_VERSION": "0.16.0", "ZIG": "", "ZIGPEEK_ZIG": ""},
    )
    assert proc.returncode == 1
    assert '"std.nope" is not a declaration' in proc.stderr


def test_map_not_allowed_in_batch():
    proc = run_cli("batch", stdin="map\n")
    assert proc.returncode == 1
    assert "`map` is not allowed inside batch" in proc.stdout


textual = pytest.importorskip("textual")

from zigpeek.tui import (  # noqa: E402
    Index,
    MapApp,
    NamespaceCard,
    NamespaceScreen,
    OverviewScreen,
)

ROWS = [
    {"fqn": "std", "kind": "type", "depth": 0, "doc": ""},
    {"fqn": "std.ArrayList", "kind": "type_fn", "depth": 1, "doc": "A list"},
    {"fqn": "std.fs", "kind": "namespace", "depth": 1, "doc": "File System"},
    {"fqn": "std.fs.path", "kind": "namespace", "depth": 2, "doc": "Paths"},
    {"fqn": "std.fs.path.join", "kind": "fn", "depth": 3, "doc": "Join paths"},
    {"fqn": "std.fs.openFile", "kind": "fn", "depth": 2, "doc": "Open a file"},
    {"fqn": "std.http", "kind": "namespace", "depth": 1, "doc": "HTTP"},
    {"fqn": "std.http.Client", "kind": "type", "depth": 2, "doc": "Client"},
    {"fqn": "std.http.Server", "kind": "type", "depth": 2, "doc": "Server"},
    {"fqn": "std.http.Client.open", "kind": "fn", "depth": 3, "doc": "Open"},
    {"fqn": "std.http.Client.fetch", "kind": "fn", "depth": 3, "doc": "Fetch"},
]


def test_index_roots_and_sizes():
    ix = Index(ROWS)
    assert [r["fqn"] for r in ix.roots()] == ["std", "std.fs", "std.http"]
    assert ix.size("std.fs") == 3
    assert ix.size("std") == len(ROWS) - 1
    # namespaces sort before fns
    assert [r["fqn"] for r in ix.children["std.fs"]] == ["std.fs.path", "std.fs.openFile"]


def _run(app, body, size=(160, 45)):
    async def go():
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await body(app, pilot)

    asyncio.run(go())


def test_overview_filter_sort_and_drilldown():
    async def body(app, pilot):
        cards = list(app.screen.query(NamespaceCard))
        assert [c.fqn for c in cards] == ["std", "std.fs", "std.http"]

        await pilot.press("slash", *"open", "enter")
        assert [c.display for c in cards] == [False, True, True]
        assert cards[1].hits == ["openFile"]
        assert cards[2].hits == ["Client.open"]
        # Exact match ranks std.http above std.fs's prefix match.
        visible = [c.fqn for c in app.screen.query_one("#cards").children if c.display]
        assert visible == ["std.http", "std.fs"]
        assert "matching “open”" in app.screen.sub_title

        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, NamespaceScreen) and screen.fqn == "std.http"
        tree = screen.query_one("#tree")
        # The match is revealed and highlighted.
        assert tree.cursor_node.data["fqn"] == "std.http.Client.open"

        await pilot.press("escape")
        assert isinstance(app.screen, OverviewScreen)
        await pilot.press("escape")
        assert all(c.display for c in cards)

        await pilot.press("s")
        order = [c.fqn for c in app.screen.query_one("#cards").children]
        assert order == ["std", "std.http", "std.fs"]
        assert "by size" in app.screen.sub_title

    _run(MapApp(ROWS, version="0.16.0"), body)


def test_typing_starts_filter_without_slash():
    async def body(app, pilot):
        cards = list(app.screen.query(NamespaceCard))
        # Keys sent in one burst, before the box has focus, must all land.
        await pilot.press(*"open")
        box = app.screen.query_one("#filter")
        assert box.display and box.value == "open"
        assert [c.display for c in cards] == [False, True, True]
        await pilot.press("escape", "s")
        assert not box.display
        assert "by size" in app.screen.sub_title

    _run(MapApp(ROWS, version="0.16.0"), body)


def test_lazy_tree_expand():
    async def body(app, pilot):
        await pilot.press("right", "enter")
        await pilot.pause()
        tree = app.screen.query_one("#tree")
        path, open_file = tree.root.children
        assert path.data["fqn"] == "std.fs.path" and not path.children
        path.expand()
        await pilot.pause()
        assert [c.data["fqn"] for c in path.children] == ["std.fs.path.join"]
        assert open_file.data["kind"] == "fn" and not open_file.allow_expand

    _run(MapApp(ROWS, version="0.16.0"), body)


def test_start_at_leaf_focuses_it():
    async def body(app, pilot):
        screen = app.screen
        assert isinstance(screen, NamespaceScreen) and screen.fqn == "std.fs.path"
        assert screen.query_one("#tree").cursor_node.data["fqn"] == "std.fs.path.join"

    _run(MapApp(ROWS, version="0.16.0", start="std.fs.path.join"), body)


def test_docs_pane_renders_get():
    rows = tree_mod.walk_tree(_mini_std())

    async def body(app, pilot):
        assert isinstance(app.screen, NamespaceScreen)
        await pilot.pause(0.3)  # docs debounce
        await app.workers.wait_for_complete()
        await pilot.pause()
        md = app.screen.query_one("#docs")
        assert "The meaning of life" in md.source
        assert "42" in md.source

    _run(MapApp(rows, version="0.16.0", load_std=_mini_std, start="std.Answer.value"), body)


def test_commands_still_work_while_the_filter_box_shows():
    """Enter leaves the box visible but unfocused. The footer keeps offering
    Sort and Quit there, so those keys must not land in the box."""

    async def body(app, pilot):
        await pilot.press("slash", *"open", "enter")
        box = app.screen.query_one("#filter")
        assert box.display and box.value == "open"
        await pilot.press("s")
        assert box.value == "open" and "by size" in app.screen.sub_title
        await pilot.press("q")
        await pilot.pause()
        assert not app.is_running

    _run(MapApp(ROWS, version="0.16.0"), body)


def test_render_markdown_lets_one_thread_into_the_wasm_store(monkeypatch):
    """wasmtime aborts the process when two threads call into one store, and
    the docs workers overlap whenever a render outlives the next cursor move."""
    live = 0
    peak = 0
    guard = threading.Lock()

    def traced(std, fqn, *args, **kwargs):
        nonlocal live, peak
        with guard:
            live += 1
            peak = max(peak, live)
        time.sleep(0.02)
        with guard:
            live -= 1
        return f"# {fqn}"

    monkeypatch.setattr("zigpeek.tui.render_get_item", traced)
    app = MapApp(ROWS, version="0.16.0", load_std=lambda: object())
    threads = [
        threading.Thread(target=app.render_markdown, args=("std.fs",)) for _ in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == 1
