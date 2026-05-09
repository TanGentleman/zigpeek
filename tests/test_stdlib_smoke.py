import os

import pytest

from zigpeek.fetch import fetch_sources_tar
from zigpeek.stdlib import render_get_item, render_search
from zigpeek.wasm import WasmStd

SMOKE = pytest.mark.skipif(
    os.environ.get("ZIGPEEK_SMOKE") != "1",
    reason="set ZIGPEEK_SMOKE=1 to run network/WASM smoke tests",
)


@pytest.fixture
def std(vendor_wasm_path):
    sources = fetch_sources_tar("0.16.0")
    return WasmStd(vendor_wasm_path.read_bytes(), sources)


@SMOKE
def test_search_arraylist_returns_markdown(std):
    md = render_search(std, "ArrayList", limit=5)
    assert md.startswith("# Search Results")
    assert "ArrayList" in md
    assert "Found" in md


@SMOKE
def test_search_no_results_message(std):
    md = render_search(std, "zzzzzzzzzzzzzzzzzzzzzz", limit=5)
    assert "No results found" in md


@SMOKE
def test_get_item_returns_arraylist_doc(std):
    md = render_get_item(std, "std.ArrayList", get_source_file=False)
    assert md.startswith("#")
    assert "ArrayList" in md


@SMOKE
def test_get_item_unknown_returns_error(std):
    md = render_get_item(std, "std.does_not_exist_xyz", get_source_file=False)
    assert md.startswith("# Error")


@SMOKE
def test_get_item_source_file_returns_path_header(std):
    md = render_get_item(std, "std.ArrayList", get_source_file=True)
    assert md.startswith("# ")
    assert ".zig" in md.split("\n", 1)[0]
