"""`zigpeek map`: a Textual TUI over the stdlib namespace tree.

The overview is a responsive grid of cards, one per top-level `std`
namespace or type. `/` filters cards and counts matching decls inside
each one. Enter opens a card as a lazily expanded member tree, with a docs
pane that renders `zigpeek get` as markdown for the highlighted decl.
"""

from __future__ import annotations

import re
import threading
from collections import defaultdict
from typing import Callable

from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Markdown, Static, Tree
from textual.widgets.tree import TreeNode

from zigpeek.stdlib import render_get_item
from zigpeek.wasm import WasmStd

KIND_STYLE = {
    "namespace": "bold magenta",
    "type": "bold cyan",
    "fn": "green",
    "type_fn": "cyan",
    "const": "yellow",
    "var": "yellow",
    "error_set": "red",
    "alias": "dim",
}
KIND_ORDER = {"namespace": 0, "type": 1, "type_fn": 2, "fn": 3}
CARD_WIDTH = 40
PREVIEW = 4
MAX_EXPANDED_MATCHES = 40
DOC_CHARS = (CARD_WIDTH - 4) * 2
DOCS_DEBOUNCE = 0.12
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def _short(fqn: str) -> str:
    return fqn.rpartition(".")[2]


def _card_doc(doc: str) -> str:
    doc = _MD_LINK_RE.sub(r"\1", doc or "")
    return doc if len(doc) <= DOC_CHARS else doc[: DOC_CHARS - 1].rstrip() + "…"


def _match_rank(name: str, query: str) -> tuple:
    """Exact, then prefix, then substring; shorter names first."""
    low = name.lower()
    return (low != query, not low.startswith(query), len(name))


def _sort_key(row: dict) -> tuple:
    return (KIND_ORDER.get(row["kind"], 4), _short(row["fqn"]).lower())


class Index:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = {r["fqn"]: r for r in rows}
        self.children: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            parent = r["fqn"].rpartition(".")[0]
            if parent:
                self.children[parent].append(r)
        for kids in self.children.values():
            kids.sort(key=_sort_key)
        self._sizes: dict[str, int] = {}

    def size(self, fqn: str) -> int:
        if fqn not in self._sizes:
            kids = self.children.get(fqn, [])
            self._sizes[fqn] = len(kids) + sum(self.size(k["fqn"]) for k in kids)
        return self._sizes[fqn]

    def descendants(self, fqn: str) -> list[dict]:
        out: list[dict] = []
        stack = list(reversed(self.children.get(fqn, [])))
        while stack:
            row = stack.pop()
            out.append(row)
            stack.extend(reversed(self.children.get(row["fqn"], [])))
        return out

    def roots(self) -> list[dict]:
        """`std` itself plus every top-level namespace/type with members."""
        std = self.rows.get("std")
        tops = sorted(
            (r for r in self.children.get("std", []) if self.children.get(r["fqn"])),
            key=lambda r: r["fqn"].lower(),
        )
        return ([std] if std else []) + tops


def _label(row: dict, index: Index, query: str = "") -> Text:
    name = _short(row["fqn"])
    t = Text(name, style=KIND_STYLE.get(row["kind"], ""))
    if query:
        start = name.lower().find(query)
        if start >= 0:
            t.stylize("reverse", start, start + len(query))
    t.append(f"  {row['kind']}", style="dim italic")
    if index.children.get(row["fqn"]):
        t.append(f"  {index.size(row['fqn']):,}", style="dim")
    return t


class NamespaceCard(Static, can_focus=True):
    def __init__(self, index: Index, row: dict) -> None:
        super().__init__(classes="card")
        self.index = index
        self.row = row
        self.fqn = row["fqn"]
        self.size_total = index.size(self.fqn)
        self.text = " ".join([self.fqn, row["doc"]]).lower()
        # The `std` card only owns its direct leaves; the rest have own cards.
        members = (
            [r for r in index.children.get("std", []) if not index.children.get(r["fqn"])]
            if self.fqn == "std"
            else index.descendants(self.fqn)
        )
        cut = len(self.fqn) + 1
        self.names = [(_short(r["fqn"]).lower(), r["fqn"][cut:]) for r in members]
        self.query = ""
        self.hits: list[str] = []
        self.name_match = False

    def apply_filter(self, query: str) -> bool:
        """Set the filter; return whether the card should stay visible.
        `hits` are member paths relative to the card, best matches first."""
        self.query = query
        self.name_match = bool(query) and query in self.text
        if query:
            found = [rel for low, rel in self.names if query in low]
            self.hits = sorted(found, key=lambda rel: _match_rank(_short(rel), query))
        else:
            self.hits = []
        self.refresh()
        return not query or self.name_match or bool(self.hits)

    def render(self) -> Text:
        row = self.row
        t = Text()
        t.append(self.fqn, style=KIND_STYLE.get(row["kind"], "bold"))
        t.append(f"  {row['kind']}\n", style="dim italic")
        t.append((_card_doc(row["doc"]) or "—") + "\n", style="italic")
        t.append(f"{self.size_total:,} decls\n\n", style="dim")
        if self.query:
            n = len(self.hits)
            t.append(f"{n} match{'es' if n != 1 else ''}\n", style="bold yellow")
            for rel in self.hits[:PREVIEW]:
                parent, _, name = rel.rpartition(".")
                t.append("▸ ", style="yellow")
                if parent:
                    t.append(parent + ".", style="dim")
                t.append(name + "\n")
            return t
        if self.fqn == "std":
            kids = [r for r in self.index.children.get("std", []) if not self.index.children.get(r["fqn"])]
        else:
            kids = sorted(
                self.index.children.get(self.fqn, []),
                key=lambda r: -self.index.size(r["fqn"]),
            )
        for r in kids[:PREVIEW]:
            t.append("▸ ", style="magenta")
            t.append(_short(r["fqn"]), style=KIND_STYLE.get(r["kind"], ""))
            t.append("\n")
        if len(kids) > PREVIEW:
            t.append(f"  +{len(kids) - PREVIEW} more", style="dim")
        return t


class OverviewScreen(Screen):
    BINDINGS = [
        Binding("enter", "open", "Open"),
        Binding("slash", "filter", "Filter"),
        Binding("s", "sort", "Sort"),
        Binding("escape", "clear", "Clear", show=False),
        Binding("left", "move(-1, 0)", show=False),
        Binding("right", "move(1, 0)", show=False),
        Binding("up", "move(0, -1)", show=False),
        Binding("down", "move(0, 1)", show=False),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, index: Index) -> None:
        super().__init__()
        self.index = index
        self.by_size = False
        self.query_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(
            placeholder="filter namespaces and decls…", id="filter", select_on_focus=False
        )
        with VerticalScroll(id="scroll"):
            with Grid(id="cards"):
                for row in self.index.roots():
                    yield NamespaceCard(self.index, row)
        yield Footer()

    def on_mount(self) -> None:
        self._subtitle()
        self.query_one("#filter").display = False
        self._relayout()
        self._focus_first()

    def _subtitle(self) -> None:
        cards = self._cards()
        order = "by size" if self.by_size else "A–Z"
        q = f" · matching “{self.query_text}”" if self.query_text else ""
        self.sub_title = (
            f"{len(cards)} namespaces · {len(self.index.rows):,} decls · {order}{q}"
        )

    def on_resize(self) -> None:
        self._relayout()

    def _columns(self) -> int:
        return max(1, (self.size.width - 4) // CARD_WIDTH)

    def _relayout(self) -> None:
        self.query_one("#cards").styles.grid_size_columns = self._columns()

    def _cards(self) -> list[NamespaceCard]:
        return [c for c in self.query_one("#cards").children if c.display]

    def _focus_first(self) -> None:
        cards = self._cards()
        if cards:
            cards[0].focus()
            cards[0].scroll_visible()

    def action_move(self, dx: int, dy: int) -> None:
        cards = self._cards()
        if not cards:
            return
        i = cards.index(self.focused) if self.focused in cards else 0
        j = min(max(i + dx + dy * self._columns(), 0), len(cards) - 1)
        cards[j].focus()
        cards[j].scroll_visible()

    def action_open(self) -> None:
        if isinstance(self.focused, NamespaceCard):
            self.app.push_screen(
                NamespaceScreen(self.index, self.focused.fqn, self.query_text)
            )

    def on_click(self, event) -> None:
        if isinstance(event.widget, NamespaceCard) and event.chain == 2:
            self.action_open()

    def _order(self, card: NamespaceCard) -> tuple:
        if self.query_text:
            best = _match_rank(_short(card.hits[0]), self.query_text) if card.hits else (True,) * 3
            return (not card.name_match, best, -len(card.hits), card.fqn.lower())
        if card.fqn == "std":
            return (0, 0, "")
        if self.by_size:
            return (1, -card.size_total, card.fqn.lower())
        return (1, 0, card.fqn.lower())

    def _reorder(self) -> None:
        self.query_one("#cards").sort_children(key=self._order)

    def action_sort(self) -> None:
        self.by_size = not self.by_size
        self._reorder()
        self._subtitle()
        self._focus_first()

    def action_filter(self) -> None:
        box = self.query_one("#filter", Input)
        box.display = True
        box.focus()

    def on_key(self, event: events.Key) -> None:
        # Typing anywhere starts a filter; s / q stay commands until it's open.
        box = self.query_one("#filter", Input)
        ch = event.character
        if self.focused is box or not event.is_printable or not ch or ch.isspace():
            return
        if ch in "/sq":
            return
        event.stop()
        event.prevent_default()
        self.action_filter()
        box.value += ch
        box.cursor_position = len(box.value)

    def action_clear(self) -> None:
        box = self.query_one("#filter", Input)
        box.value = ""
        box.display = False
        self._apply("")
        self._focus_first()

    def _apply(self, raw: str) -> None:
        self.query_text = raw.strip().lower()
        for card in self.query(NamespaceCard):
            card.display = card.apply_filter(self.query_text)
        self._reorder()
        self._subtitle()

    @on(Input.Changed, "#filter")
    def _filter(self, event: Input.Changed) -> None:
        self._apply(event.value)

    @on(Input.Submitted, "#filter")
    def _filter_done(self) -> None:
        self._focus_first()


class NamespaceScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("c", "copy", "Copy fqn"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(
        self, index: Index, fqn: str, query: str = "", focus: str | None = None
    ) -> None:
        super().__init__()
        self.index = index
        self.fqn = fqn
        self.query_text = query
        self.focus_fqn = focus
        self.nodes: dict[str, TreeNode] = {}
        self._docs_fqn: str | None = None
        self._docs_timer = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Tree(Text(self.fqn, style="bold"), id="tree")
            with VerticalScroll(id="docs-pane"):
                yield Markdown(id="docs")
        yield Footer()

    def on_mount(self) -> None:
        row = self.index.rows[self.fqn]
        self.sub_title = f"{self.fqn} · {self.index.size(self.fqn):,} decls"
        tree = self.query_one("#tree", Tree)
        tree.root.data = row
        self.nodes[self.fqn] = tree.root
        self._populate(tree.root)
        tree.root.expand()
        tree.focus()
        first = self.nodes.get(self.focus_fqn or "") or self._reveal_matches()
        if first is not None:
            # Node line numbers only exist after the tree has laid out.
            self.call_after_refresh(self._move_to, first)
            row = first.data
        self._show_summary(row)

    def _move_to(self, node: TreeNode) -> None:
        tree = self.query_one("#tree", Tree)
        tree.move_cursor(node)
        tree.scroll_to_node(node)

    def _populate(self, node: TreeNode) -> None:
        if node.children or node.data is None:
            return
        for row in self.index.children.get(node.data["fqn"], []):
            has_kids = bool(self.index.children.get(row["fqn"]))
            child = node.add(
                _label(row, self.index, self.query_text), data=row, allow_expand=has_kids
            )
            self.nodes[row["fqn"]] = child

    def _reveal_matches(self) -> TreeNode | None:
        """Expand the path to the first few decls whose name matches the
        overview filter; return the first one."""
        q = self.query_text
        if not q:
            return None
        hits = [
            r for r in self.index.descendants(self.fqn) if q in _short(r["fqn"]).lower()
        ]
        if self.fqn == "std":
            hits = [r for r in hits if r["depth"] == 1]
        hits.sort(key=lambda r: _match_rank(_short(r["fqn"]), q))
        first = None
        for row in hits[:MAX_EXPANDED_MATCHES]:
            parts = row["fqn"][len(self.fqn) + 1 :].split(".")
            fqn = self.fqn
            for part in parts[:-1]:
                fqn = f"{fqn}.{part}"
                node = self.nodes.get(fqn)
                if node is None:
                    break
                self._populate(node)
                node.expand()
            node = self.nodes.get(row["fqn"])
            if first is None:
                first = node
        return first

    @on(Tree.NodeExpanded)
    def _expand(self, event: Tree.NodeExpanded) -> None:
        self._populate(event.node)

    @on(Tree.NodeHighlighted)
    def _highlight(self, event: Tree.NodeHighlighted) -> None:
        if event.node.data is not None:
            self._show_summary(event.node.data)

    def action_copy(self) -> None:
        node = self.query_one("#tree", Tree).cursor_node
        if node is not None and node.data is not None:
            self.app.copy_to_clipboard(node.data["fqn"])
            self.notify(f"Copied {node.data['fqn']}", timeout=2)

    def _show_summary(self, row: dict) -> None:
        """Instant one-liner from the cached tree; full `get` docs follow
        once the cursor settles."""
        md = f"# `{row['fqn']}`\n\n*{row['kind']}*\n\n{row['doc'] or ''}\n\n"
        kids = self.index.children.get(row["fqn"], [])
        if kids:
            md += f"{len(kids):,} members · {self.index.size(row['fqn']):,} decls\n"
        self.query_one("#docs", Markdown).update(md)
        self._docs_fqn = row["fqn"]
        if self.app.load_std is not None:
            if self._docs_timer is not None:
                self._docs_timer.stop()
            self._docs_timer = self.set_timer(
                DOCS_DEBOUNCE, lambda fqn=row["fqn"]: self._render_docs(fqn)
            )

    @work(thread=True, group="docs")
    def _render_docs(self, fqn: str) -> None:
        if fqn != self._docs_fqn:
            return
        md = self.app.render_markdown(fqn)
        self.app.call_from_thread(self._set_docs, fqn, md)

    def _set_docs(self, fqn: str, md: str) -> None:
        if fqn == self._docs_fqn:
            self.query_one("#docs", Markdown).update(md)


class MapApp(App):
    TITLE = "zigpeek map"
    CSS = """
    #cards {
        grid-gutter: 1 2;
        grid-rows: 10;
        height: auto;
        padding: 1 2;
    }
    .card {
        height: 10;
        min-height: 10;
        padding: 0 1;
        border: round $primary-darken-2;
    }
    .card:focus {
        border: round $accent;
        background: $boost;
    }
    #filter { margin: 0 2; }
    #tree { width: 45%; border-right: vkey $primary-darken-2; }
    #docs-pane { padding: 0 2; }
    """

    def __init__(
        self,
        rows: list[dict],
        version: str,
        load_std: Callable[[], WasmStd] | None = None,
        start: str | None = None,
    ) -> None:
        super().__init__()
        self.index = Index(rows)
        self.version = version
        self.load_std = load_std
        self.start = start
        self._std: WasmStd | None = None
        self._std_lock = threading.Lock()

    def std(self) -> WasmStd:
        with self._std_lock:
            if self._std is None:
                self._std = self.load_std()
            return self._std

    def render_markdown(self, fqn: str) -> str:
        """One WASM store, one caller at a time: wasmtime aborts the process
        if two threads call into the same store, and the docs workers
        overlap whenever a render outlives the next cursor move."""
        with self._std_lock:
            if self._std is None:
                self._std = self.load_std()
            return render_get_item(self._std, fqn)

    def on_mount(self) -> None:
        self.theme = "tokyo-night"
        self.title = f"zigpeek map · Zig {self.version}"
        self.push_screen(OverviewScreen(self.index))
        row = self.index.rows.get(self.start or "")
        if row is not None:
            if self.index.children.get(row["fqn"]) or row["fqn"] == "std":
                self.push_screen(NamespaceScreen(self.index, row["fqn"]))
            else:
                parent = row["fqn"].rpartition(".")[0]
                self.push_screen(NamespaceScreen(self.index, parent, focus=row["fqn"]))
        if self.load_std is not None:
            self.run_worker(self.std, thread=True, group="preload")
