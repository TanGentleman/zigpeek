import io
import tarfile
from pathlib import Path

import pytest

from zigpeek.libdir import (
    ZigEnv,
    lib_dir_from_zig_env,
    pack_lib_dir,
    probe_zig,
    resolve_lib_dir,
    resolve_std_dir,
    zig_binary,
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
    lib.mkdir()
    payload = (
        f'.{{\n    .zig_exe = "/opt/zig/zig",\n    .lib_dir = "{lib}",\n'
        f'    .version = "0.16.0",\n}}\n'
    )

    class Proc:
        stdout = payload

    monkeypatch.setattr(
        "zigpeek.libdir.subprocess.run",
        lambda *a, **k: Proc(),
    )
    monkeypatch.setattr("zigpeek.libdir.zig_binary", lambda: "/opt/zig/zig")
    assert lib_dir_from_zig_env() == lib
    env = probe_zig()
    assert env == ZigEnv(exe="/opt/zig/zig", lib_dir=lib, version="0.16.0")


def test_lib_dir_from_zig_env_resolves_relative(monkeypatch, tmp_path):
    lib = tmp_path / "zig" / "lib"
    lib.mkdir(parents=True)
    payload = '.{ .lib_dir = "zig/lib", .version = "0.16.0", }\n'

    class Proc:
        stdout = payload

    monkeypatch.setattr(
        "zigpeek.libdir.subprocess.run",
        lambda *a, **k: Proc(),
    )
    monkeypatch.setattr("zigpeek.libdir.zig_binary", lambda: "zig")
    monkeypatch.chdir(tmp_path)
    assert lib_dir_from_zig_env() == lib.resolve()


def test_lib_dir_from_zig_env_missing_binary(monkeypatch):
    monkeypatch.setattr("zigpeek.libdir.zig_binary", lambda: None)
    with pytest.raises(FileNotFoundError, match="zig not found"):
        lib_dir_from_zig_env()


def test_zig_binary_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ZIGPEEK_ZIG", str(tmp_path / "custom-zig"))
    monkeypatch.setenv("ZIG", "/ignored")
    assert zig_binary() == str(tmp_path / "custom-zig")
    monkeypatch.delenv("ZIGPEEK_ZIG")
    assert zig_binary() == "/ignored"


def test_resolve_lib_dir_auto_uses_probe(tmp_path, monkeypatch):
    monkeypatch.delenv("ZIGPEEK_LIB_DIR", raising=False)
    monkeypatch.setattr(
        "zigpeek.libdir.probe_zig",
        lambda: ZigEnv(exe="zig", lib_dir=tmp_path / "lib", version="0.16.0"),
    )
    assert resolve_lib_dir(None) is None
    assert resolve_lib_dir(None, auto=True) == tmp_path / "lib"


def test_pack_feeds_wasm_search():
    std = WasmStd(WASM.read_bytes(), pack_lib_dir(FIXTURE_LIB))
    assert "std" in std.list_modules()
    hits = [std.fully_qualified_name(i) for i in std.execute_query("Answer", False)]
    assert "std.Answer" in hits
    assert std.find_decl("std.greet") is not None
    assert std.find_decl("std.should_not_appear") is None
