"""Port of mcp/extract-builtin-functions.ts and the ranking from mcp/tools.ts.

Parses Zig's langref HTML into a list of BuiltinFunction records, then ranks
those records by relevance to a query string.
"""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString, Tag


@dataclass
class BuiltinFunction:
    func: str
    signature: str
    docs: str


_WS_RE = re.compile(r"\s+")
_BLANK_LINES_RE = re.compile(r"\n{2,}")
_TRAILING_NEWLINES_RE = re.compile(r"\n+$")


def _rewrite_link(text: str, href: str, link_base_url: str | None) -> str:
    if href.startswith("#") and link_base_url:
        return f"[{text}]({link_base_url}{href})"
    return f"[{text}]({href})"


def _inline_text(tag: Tag, link_base_url: str | None) -> str:
    cloned = BeautifulSoup(str(tag), "lxml").find()
    if cloned is None:
        return ""

    for a in list(cloned.find_all("a")):
        href = a.get("href", "")
        text = a.get_text()
        a.replace_with(NavigableString(_rewrite_link(text, href, link_base_url)))

    for code in list(cloned.find_all("code")):
        code.replace_with(NavigableString(f"`{code.get_text()}`"))

    return _WS_RE.sub(" ", cloned.get_text()).strip()


def _next_sibling_tag(tag: Tag) -> Tag | None:
    sib = tag.next_sibling
    while sib is not None and not isinstance(sib, Tag):
        sib = sib.next_sibling
    return sib


def parse_builtin_functions_html(
    html: str,
    link_base_url: str | None,
) -> list[BuiltinFunction]:
    soup = BeautifulSoup(html, "lxml")
    section = soup.find("h2", id="Builtin-Functions")
    if section is None:
        raise ValueError("Could not find Builtin Functions section in HTML")

    builtins: list[BuiltinFunction] = []
    current = _next_sibling_tag(section)

    while current is not None and current.name != "h2":
        if current.name == "h3" and current.has_attr("id"):
            first_a = current.find("a")
            func = first_a.get_text() if first_a is not None else ""
            if func.startswith("@"):
                pre = _next_sibling_tag(current)
                signature = ""
                desc_start = pre
                if pre is not None and pre.name == "pre":
                    signature = pre.get_text().strip()
                    desc_start = _next_sibling_tag(pre)

                description_parts: list[str] = []
                desc_current = desc_start
                while desc_current is not None and desc_current.name not in ("h2", "h3"):
                    if desc_current.name == "p":
                        description_parts.append(
                            _inline_text(desc_current, link_base_url)
                        )
                    elif desc_current.name == "ul":
                        for li in desc_current.find_all("li", recursive=False):
                            li_text = _inline_text(li, link_base_url)
                            if li_text:
                                description_parts.append(f"* {li_text}")
                    elif desc_current.name == "figure":
                        figcaption = ""
                        cap_el = desc_current.find("figcaption")
                        if cap_el is not None:
                            figcaption = cap_el.get_text().strip()
                        pre_el = desc_current.find("pre")
                        code = pre_el.get_text() if pre_el is not None else ""
                        lang = ""
                        label = ""
                        if figcaption:
                            label = f"**{figcaption}**\n"
                            if figcaption.endswith(".zig"):
                                lang = "zig"
                            elif "shell" in figcaption.lower():
                                lang = "sh"
                        if code:
                            block = f"{label}\n```{lang}\n{code.strip()}\n```"
                            description_parts.append(block.strip())
                    desc_current = _next_sibling_tag(desc_current)

                docs = "\n".join(description_parts)
                docs = _BLANK_LINES_RE.sub("\n", docs)
                docs = _TRAILING_NEWLINES_RE.sub("", docs)
                if docs.lower().endswith("see also:"):
                    docs = docs[: -len("see also:")].strip()

                builtins.append(
                    BuiltinFunction(func=func, signature=signature, docs=docs)
                )

        current = _next_sibling_tag(current)

    return builtins


def rank_builtin_functions(
    functions: list[BuiltinFunction],
    query: str,
) -> list[BuiltinFunction]:
    q = query.lower().strip()
    if not q:
        return []

    scored: list[tuple[int, BuiltinFunction]] = []
    for fn in functions:
        f_lower = fn.func.lower()
        score = 0
        if f_lower == q:
            score += 1000
        elif f_lower.startswith(q):
            score += 500
        elif q in f_lower:
            score += 300
        if score > 0:
            score += max(0, 50 - len(fn.func))
            scored.append((score, fn))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [fn for _, fn in scored]
