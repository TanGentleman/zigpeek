import io
import tarfile
from pathlib import Path

import pytest

from zigpeek.libdir import (
    lib_dir_from_zig_env,
    pack_lib_dir,
    resolve_lib_dir,
    resolve_std_dir,
)
from zigpeek.wasm import WasmStd

FIXTURE_LIB = Path(__file__).resolve().parent / "fixtures" / "mini-lib"
WASM = Path(__file__).resolve().parent.parent / "src" / "zigpeek" / "_vendor" / "main.wasm"


def _tar_names(data: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r") as tar:
        return [m.name for m in tar.getmembers()]


def test_resolve_std_dir_accepts_lib_or_std():
    assert resolve_std_dir(FIXTURE_LIB) == FIXTURE_LIB / "std"
    assert resolve_std_dir(FIXTURE_LIB / "std") == FIXTURE_LIB / "std"


def test_resolve_std_dir_rejects_garbage(tmp_path):
    with pytest.raises(FileNotFoundError, match="not a Zig lib"):
        resolve_std_dir(tmp_path)


def test_pack_prefixes_std_and_skips_test_zig():
    names = _tar_names(pack_lib_dir(FIXTURE_LIB))
    assert names == ["std/std.zig"]
    assert "std/foo_test.zig" not in names


def test_resolve_lib_dir_none_and_path(tmp_path, monkeypatch):
    monkeypatch.delenv("ZIGPEEK_LIB_DIR", raising=False)
    assert resolve_lib_dir(None) is None
    assert resolve_lib_dir(str(tmp_path)) == tmp_path


def test_resolve_lib_dir_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGPEEK_LIB_DIR", str(tmp_path))
    assert resolve_lib_dir(None) == tmp_path
    assert resolve_lib_dir("/explicit") == Path("/explicit")


def test_resolve_lib_dir_zig_sentinel(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "zigpeek.libdir.lib_dir_from_zig_env", lambda: tmp_path / "from-zig"
    )
    assert resolve_lib_dir("zig") == tmp_path / "from-zig"
    assert resolve_lib_dir("auto") == tmp_path / "from-zig"


def test_lib_dir_from_zig_env_parses_zig_struct(monkeypatch, tmp_path):
    lib = tmp_path / "lib"
    payload = f'.{{\n    .zig_exe = "/opt/zig/zig",\n    .lib_dir = "{lib}",\n}}\n'

    class Proc:
        stdout = payload

    monkeypatch.setattr(
        "zigpeek.libdir.subprocess.run",
        lambda *a, **k: Proc(),
    )
    assert lib_dir_from_zig_env() == lib


def test_lib_dir_from_zig_env_resolves_relative(monkeypatch, tmp_path):
    payload = '.{ .lib_dir = "zig/lib", }\n'

    class Proc:
        stdout = payload

    monkeypatch.setattr(
        "zigpeek.libdir.subprocess.run",
        lambda *a, **k: Proc(),
    )
    monkeypatch.chdir(tmp_path)
    assert lib_dir_from_zig_env() == (tmp_path / "zig" / "lib").resolve()


def test_lib_dir_from_zig_env_missing_binary(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("zig")

    monkeypatch.setattr("zigpeek.libdir.subprocess.run", boom)
    with pytest.raises(FileNotFoundError, match="zig not found"):
        lib_dir_from_zig_env()


def test_pack_feeds_wasm_search():
    std = WasmStd(WASM.read_bytes(), pack_lib_dir(FIXTURE_LIB))
    assert "std" in std.list_modules()
    hits = [std.fully_qualified_name(i) for i in std.execute_query("Answer", False)]
    assert "std.Answer" in hits
    assert std.find_decl("std.greet") is not None
    assert std.find_decl("std.should_not_appear") is None
