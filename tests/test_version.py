from pathlib import Path

import pytest

from zigpeek.libdir import ZigEnv
from zigpeek.version import DEFAULT_ZIG_VERSION, resolve_version


def test_default_version_is_0_16_0():
    assert DEFAULT_ZIG_VERSION == "0.16.0"


def test_resolve_returns_default_when_nothing_provided(monkeypatch):
    monkeypatch.delenv("ZIGPEEK_VERSION", raising=False)
    monkeypatch.setattr("zigpeek.version.probe_zig", lambda: None)
    assert resolve_version(None) == "0.16.0"


def test_resolve_uses_active_zig_version(monkeypatch):
    monkeypatch.delenv("ZIGPEEK_VERSION", raising=False)
    monkeypatch.setattr(
        "zigpeek.version.probe_zig",
        lambda: ZigEnv(exe="zig", lib_dir=Path("/z/lib"), version="0.15.1"),
    )
    assert resolve_version(None) == "0.15.1"


def test_resolve_prefers_env_over_active_zig(monkeypatch):
    monkeypatch.setenv("ZIGPEEK_VERSION", "master")
    monkeypatch.setattr(
        "zigpeek.version.probe_zig",
        lambda: ZigEnv(exe="zig", lib_dir=Path("/z/lib"), version="0.15.1"),
    )
    assert resolve_version(None) == "master"


def test_resolve_prefers_explicit_arg_over_env(monkeypatch):
    monkeypatch.setenv("ZIGPEEK_VERSION", "0.15.1")
    assert resolve_version("master") == "master"


def test_resolve_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("ZIGPEEK_VERSION", "0.15.1")
    assert resolve_version(None) == "0.15.1"


def test_resolve_rejects_empty_string(monkeypatch):
    monkeypatch.delenv("ZIGPEEK_VERSION", raising=False)
    with pytest.raises(ValueError):
        resolve_version("")
