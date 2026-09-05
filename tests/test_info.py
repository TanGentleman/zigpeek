from pathlib import Path

from zigpeek.info import collect_runtime_info, render_environment, render_info
from zigpeek.libdir import ZigEnv
from zigpeek.version import DEFAULT_ZIG_VERSION


def test_render_info_includes_skill_usage():
    info = collect_runtime_info()
    text = render_info(info)
    assert text.startswith("# zigpeek\n")
    assert "zigpeek info" in text
    assert "zigpeek search <q>" in text
    assert "zigpeek get <fqn>" in text
    assert "zigpeek builtins list" in text
    assert "zigpeek batch" in text
    assert "## Environment" in text


def test_collect_reports_local_zig(monkeypatch, tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    env = ZigEnv(exe="/opt/zig/zig", lib_dir=lib, version="0.15.1")
    monkeypatch.delenv("ZIGPEEK_VERSION", raising=False)
    monkeypatch.delenv("ZIGPEEK_LIB_DIR", raising=False)
    monkeypatch.setattr("zigpeek.info.probe_zig", lambda: env)
    monkeypatch.setattr("zigpeek.info.resolve_version", lambda v: env.version)
    monkeypatch.setattr(
        "zigpeek.info.resolve_lib_dir",
        lambda cli, auto=False: lib if auto else None,
    )
    info = collect_runtime_info()
    assert info.zig_usable
    assert info.zig_exe == "/opt/zig/zig"
    assert info.zig_version == "0.15.1"
    assert info.zig_lib_dir == str(lib)
    assert info.docs_version == "0.15.1"
    assert info.docs_version_reason == "from local zig"
    env = render_environment(info)
    assert "/opt/zig/zig" in env
    assert "0.15.1" in env
    assert str(lib) in env


def test_collect_without_zig_falls_back(monkeypatch):
    monkeypatch.delenv("ZIGPEEK_VERSION", raising=False)
    monkeypatch.delenv("ZIGPEEK_LIB_DIR", raising=False)
    monkeypatch.setattr("zigpeek.info.probe_zig", lambda: None)
    monkeypatch.setattr("zigpeek.info.zig_binary", lambda: None)
    monkeypatch.setattr(
        "zigpeek.info.resolve_lib_dir", lambda cli, auto=False: None
    )
    monkeypatch.setattr("zigpeek.info.resolve_version", lambda v: DEFAULT_ZIG_VERSION)
    info = collect_runtime_info()
    assert not info.zig_usable
    assert info.zig_exe is None
    assert info.docs_version == DEFAULT_ZIG_VERSION
    assert "fallback" in info.docs_version_reason
    env = render_environment(info)
    assert "$ZIGPEEK_ZIG" in env
    assert DEFAULT_ZIG_VERSION in env


def test_collect_unusable_zig_binary_is_reported(monkeypatch):
    monkeypatch.delenv("ZIGPEEK_VERSION", raising=False)
    monkeypatch.setattr("zigpeek.info.probe_zig", lambda: None)
    monkeypatch.setattr("zigpeek.info.zig_binary", lambda: "/broken/zig")
    monkeypatch.setattr(
        "zigpeek.info.resolve_lib_dir", lambda cli, auto=False: None
    )
    monkeypatch.setattr("zigpeek.info.resolve_version", lambda v: DEFAULT_ZIG_VERSION)
    info = collect_runtime_info()
    env = render_environment(info)
    assert "/broken/zig" in env
    assert "unusable" in env


def test_explicit_version_pin_skips_auto_lib(monkeypatch, tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    monkeypatch.setenv("ZIGPEEK_VERSION", "0.15.1")
    monkeypatch.delenv("ZIGPEEK_LIB_DIR", raising=False)
    monkeypatch.setattr(
        "zigpeek.info.probe_zig",
        lambda: ZigEnv(exe="zig", lib_dir=lib, version="0.16.0"),
    )
    info = collect_runtime_info()
    assert info.docs_version == "0.15.1"
    assert "ZIGPEEK_VERSION" in info.docs_version_reason
    assert info.stdlib_kind != "local compiler lib/"


def test_cli_version_pin_reason(monkeypatch):
    monkeypatch.delenv("ZIGPEEK_VERSION", raising=False)
    monkeypatch.delenv("ZIGPEEK_LIB_DIR", raising=False)
    monkeypatch.setattr("zigpeek.info.probe_zig", lambda: None)
    monkeypatch.setattr("zigpeek.info.zig_binary", lambda: None)
    monkeypatch.setattr(
        "zigpeek.info.resolve_lib_dir", lambda cli, auto=False: None
    )
    info = collect_runtime_info(version="master")
    assert info.docs_version == "master"
    assert "--version" in info.docs_version_reason


def test_lib_dir_flag_is_reported(tmp_path):
    lib = tmp_path / "std-root"
    lib.mkdir()
    info = collect_runtime_info(lib_dir=str(lib))
    assert info.stdlib_kind == "local compiler lib/"
    assert str(lib) in info.stdlib_detail
    assert "exists" in info.stdlib_detail


def test_missing_lib_dir_is_labeled(tmp_path):
    missing = tmp_path / "nope"
    info = collect_runtime_info(lib_dir=str(missing))
    assert "missing" in info.stdlib_detail


def test_cache_dir_override_appears(tmp_path, monkeypatch):
    monkeypatch.delenv("ZIGPEEK_VERSION", raising=False)
    monkeypatch.delenv("ZIGPEEK_LIB_DIR", raising=False)
    monkeypatch.setattr("zigpeek.info.probe_zig", lambda: None)
    monkeypatch.setattr(
        "zigpeek.info.resolve_lib_dir", lambda cli, auto=False: None
    )
    info = collect_runtime_info(cache_dir=str(tmp_path))
    assert info.cache_root == str(tmp_path)


def test_zigpeek_version_and_wasm_are_populated():
    info = collect_runtime_info()
    assert info.zigpeek_version
    assert info.zigpeek_version != "unknown"
    assert info.wasm_path.endswith("main.wasm")
    assert Path(info.wasm_path).name == "main.wasm"
