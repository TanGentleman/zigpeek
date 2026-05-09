import pytest

from zigpeek.builtins import (
    BuiltinFunction,
    parse_builtin_functions_html,
    rank_builtin_functions,
)


def test_parses_two_functions(fixture_path):
    html = fixture_path("tiny-langref.html").read_text()
    fns = parse_builtin_functions_html(html, link_base_url="https://x/")
    assert len(fns) == 2
    assert fns[0].func == "@addWithOverflow"
    assert fns[1].func == "@atomicLoad"


def test_signature_extracted(fixture_path):
    html = fixture_path("tiny-langref.html").read_text()
    fns = parse_builtin_functions_html(html, link_base_url=None)
    assert fns[0].signature.startswith("@addWithOverflow(")


def test_inline_code_rewritten(fixture_path):
    html = fixture_path("tiny-langref.html").read_text()
    fns = parse_builtin_functions_html(html, link_base_url=None)
    assert "`a + b`" in fns[0].docs
    assert "`ptr`" in fns[1].docs


def test_anchor_link_rewritten_with_base(fixture_path):
    html = fixture_path("tiny-langref.html").read_text()
    fns = parse_builtin_functions_html(html, link_base_url="https://x/")
    assert "[overflow](https://x/#overflow)" in fns[0].docs


def test_list_items_prefixed(fixture_path):
    html = fixture_path("tiny-langref.html").read_text()
    fns = parse_builtin_functions_html(html, link_base_url=None)
    assert "* The first element is the wrapped result." in fns[0].docs
    assert "* The second element is the carry bit." in fns[0].docs


def test_h3_after_h2_is_ignored(fixture_path):
    html = fixture_path("tiny-langref.html").read_text()
    fns = parse_builtin_functions_html(html, link_base_url=None)
    assert "@ignored" not in {f.func for f in fns}


def test_missing_section_raises():
    with pytest.raises(ValueError):
        parse_builtin_functions_html("<html></html>", link_base_url=None)


def _fn(name: str) -> BuiltinFunction:
    return BuiltinFunction(func=name, signature=f"{name}()", docs="")


def test_rank_exact_match_wins():
    fns = [_fn("@addWithOverflow"), _fn("@add")]
    ranked = rank_builtin_functions(fns, "@add")
    assert ranked[0].func == "@add"


def test_rank_prefix_beats_substring():
    fns = [_fn("@xatomicY"), _fn("@atomicLoad")]
    ranked = rank_builtin_functions(fns, "@atomic")
    assert ranked[0].func == "@atomicLoad"


def test_rank_returns_empty_when_no_match():
    fns = [_fn("@foo")]
    assert rank_builtin_functions(fns, "zzz") == []


def test_rank_is_case_insensitive():
    fns = [_fn("@AddWithOverflow")]
    ranked = rank_builtin_functions(fns, "addwithoverflow")
    assert ranked[0].func == "@AddWithOverflow"
