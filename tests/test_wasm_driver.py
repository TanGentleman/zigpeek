import os

import pytest

from zigpeek.fetch import fetch_sources_tar
from zigpeek.wasm import WasmStd

SMOKE = pytest.mark.skipif(
    os.environ.get("ZIGPEEK_SMOKE") != "1",
    reason="set ZIGPEEK_SMOKE=1 to run network/WASM smoke tests",
)


@SMOKE
def test_wasmstd_loads_and_lists_modules(vendor_wasm_path):
    sources = fetch_sources_tar("0.16.0")
    std = WasmStd(vendor_wasm_path.read_bytes(), sources)
    modules = std.list_modules()
    assert "std" in modules


@SMOKE
def test_find_decl_for_known_fqn(vendor_wasm_path):
    sources = fetch_sources_tar("0.16.0")
    std = WasmStd(vendor_wasm_path.read_bytes(), sources)
    idx = std.find_decl("std.ArrayList")
    assert idx is not None
    assert std.fully_qualified_name(idx).startswith("std")


@SMOKE
def test_query_returns_results_for_arraylist(vendor_wasm_path):
    sources = fetch_sources_tar("0.16.0")
    std = WasmStd(vendor_wasm_path.read_bytes(), sources)
    hits = std.execute_query("ArrayList", ignore_case=False)
    assert len(hits) > 0
