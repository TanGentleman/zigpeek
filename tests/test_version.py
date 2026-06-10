import pytest

from zigpeek.version import DEFAULT_ZIG_VERSION, resolve_version


def test_default_version_is_master():
    assert DEFAULT_ZIG_VERSION == "master"


def test_resolve_returns_default_when_nothing_provided(monkeypatch):
    monkeypatch.delenv("ZIGPEEK_VERSION", raising=False)
    assert resolve_version(None) == "master"


def test_resolve_prefers_explicit_arg_over_env(monkeypatch):
    monkeypatch.setenv("ZIGPEEK_VERSION", "0.15.1")
    assert resolve_version("0.16.0") == "0.16.0"


def test_resolve_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("ZIGPEEK_VERSION", "0.15.1")
    assert resolve_version(None) == "0.15.1"


def test_resolve_rejects_empty_string(monkeypatch):
    monkeypatch.delenv("ZIGPEEK_VERSION", raising=False)
    with pytest.raises(ValueError):
        resolve_version("")
