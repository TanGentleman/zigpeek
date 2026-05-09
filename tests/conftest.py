from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
VENDOR_WASM = TESTS_DIR.parent / "vendor" / "main.wasm"
FIXTURES_DIR = TESTS_DIR / "fixtures"


@pytest.fixture
def vendor_wasm_path() -> Path:
    if not VENDOR_WASM.exists():
        pytest.skip(f"vendor/main.wasm not present at {VENDOR_WASM}")
    return VENDOR_WASM


@pytest.fixture
def fixture_path():
    def _loader(name: str) -> Path:
        return FIXTURES_DIR / name

    return _loader
