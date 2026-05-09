from pathlib import Path

from zigpeek.fetch import (
    bundled_path_for,
    cache_dir_for,
    fetch_langref_html,
    fetch_sources_tar,
    langref_url,
    prefetch,
    sources_tar_url,
)


def test_url_builders():
    assert (
        sources_tar_url("0.16.0")
        == "https://ziglang.org/documentation/0.16.0/std/sources.tar"
    )
    assert langref_url("0.16.0") == "https://ziglang.org/documentation/0.16.0/"


def test_cache_dir_uses_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGPEEK_CACHE_DIR", str(tmp_path))
    d = cache_dir_for("0.16.0")
    assert d == tmp_path / "0.16.0"


def test_default_cache_dir_is_tmp_zigpeek_cache(monkeypatch):
    monkeypatch.delenv("ZIGPEEK_CACHE_DIR", raising=False)
    assert cache_dir_for("0.16.0") == Path("/tmp/zigpeek-cache/0.16.0")


def test_cache_dir_override_beats_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGPEEK_CACHE_DIR", "/should/be/ignored")
    assert cache_dir_for("0.16.0", override=tmp_path) == tmp_path / "0.16.0"


def test_fetch_sources_uses_cache_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGPEEK_CACHE_DIR", str(tmp_path))
    cached = tmp_path / "0.16.0" / "sources.tar"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"PRE-CACHED")

    data = fetch_sources_tar("0.16.0", refresh=False)
    assert data == b"PRE-CACHED"


def test_fetch_sources_uses_cache_dir_kwarg(tmp_path):
    cached = tmp_path / "0.16.0" / "sources.tar"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"VIA-KWARG")

    data = fetch_sources_tar("0.16.0", refresh=False, cache_dir=tmp_path)
    assert data == b"VIA-KWARG"


def test_fetch_sources_refresh_overwrites_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGPEEK_CACHE_DIR", str(tmp_path))
    cached = tmp_path / "0.16.0" / "sources.tar"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"OLD")

    calls: list[str] = []

    def fake_get(url: str) -> bytes:
        calls.append(url)
        return b"NEW"

    monkeypatch.setattr("zigpeek.fetch._http_get_bytes", fake_get)
    data = fetch_sources_tar("0.16.0", refresh=True)
    assert data == b"NEW"
    assert cached.read_bytes() == b"NEW"
    assert calls == [sources_tar_url("0.16.0")]


def test_fetch_langref_caches_text(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGPEEK_CACHE_DIR", str(tmp_path))

    def fake_get(url: str) -> bytes:
        return b"<html>hello</html>"

    monkeypatch.setattr("zigpeek.fetch._http_get_bytes", fake_get)

    html = fetch_langref_html("0.16.0", refresh=False)
    assert html == "<html>hello</html>"
    assert (tmp_path / "0.16.0" / "langref.html").read_bytes() == (
        b"<html>hello</html>"
    )


def test_bundled_path_resolves_under_package():
    p = bundled_path_for("0.16.0", "sources.tar")
    assert p.parts[-3:] == ("_data", "0.16.0", "sources.tar")
    assert "zigpeek" in p.parts


def _bundled_in(root: Path):
    """Helper: build a bundled_path_for that resolves under `root`."""

    def _inner(version: str, filename: str) -> Path:
        return root / version / filename

    return _inner


def test_bundled_snapshot_short_circuits_network(tmp_path, monkeypatch):
    """If a bundled snapshot exists, fetch returns it without touching cache or network."""
    monkeypatch.setenv("ZIGPEEK_CACHE_DIR", str(tmp_path))
    bundled_root = tmp_path / "_bundled"
    bundled_file = bundled_root / "0.16.0" / "sources.tar"
    bundled_file.parent.mkdir(parents=True)
    bundled_file.write_bytes(b"BUNDLED")

    monkeypatch.setattr(
        "zigpeek.fetch.bundled_path_for", _bundled_in(bundled_root)
    )

    def boom(url: str) -> bytes:
        raise AssertionError(f"network should not be hit, got {url}")

    monkeypatch.setattr("zigpeek.fetch._http_get_bytes", boom)
    assert fetch_sources_tar("0.16.0") == b"BUNDLED"


def test_bundled_bypassed_when_refresh(tmp_path, monkeypatch):
    bundled_root = tmp_path / "_bundled"
    bundled_file = bundled_root / "0.16.0" / "sources.tar"
    bundled_file.parent.mkdir(parents=True)
    bundled_file.write_bytes(b"BUNDLED")
    monkeypatch.setattr(
        "zigpeek.fetch.bundled_path_for", _bundled_in(bundled_root)
    )
    monkeypatch.setenv("ZIGPEEK_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        "zigpeek.fetch._http_get_bytes", lambda url: b"FRESH"
    )
    assert fetch_sources_tar("0.16.0", refresh=True) == b"FRESH"


def test_prefetch_populates_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("ZIGPEEK_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "zigpeek.fetch.bundled_path_for", _bundled_in(tmp_path / "no-bundle")
    )

    def fake_get(url: str) -> bytes:
        return b"SRC" if url.endswith("sources.tar") else b"<html/>"

    monkeypatch.setattr("zigpeek.fetch._http_get_bytes", fake_get)

    paths = prefetch("0.16.0")
    assert paths["sources.tar"] == tmp_path / "0.16.0" / "sources.tar"
    assert paths["langref.html"] == tmp_path / "0.16.0" / "langref.html"
    assert paths["sources.tar"].read_bytes() == b"SRC"
    assert paths["langref.html"].read_bytes() == b"<html/>"


def test_prefetch_reports_bundled_paths_when_present(tmp_path, monkeypatch):
    bundled_root = tmp_path / "_bundled"
    (bundled_root / "0.16.0").mkdir(parents=True)
    (bundled_root / "0.16.0" / "sources.tar").write_bytes(b"B")
    (bundled_root / "0.16.0" / "langref.html").write_bytes(b"B")
    monkeypatch.setattr(
        "zigpeek.fetch.bundled_path_for", _bundled_in(bundled_root)
    )
    monkeypatch.setenv("ZIGPEEK_CACHE_DIR", str(tmp_path / "cache"))

    def boom(url: str) -> bytes:
        raise AssertionError("network should not be hit")

    monkeypatch.setattr("zigpeek.fetch._http_get_bytes", boom)

    paths = prefetch("0.16.0")
    assert paths["sources.tar"] == bundled_root / "0.16.0" / "sources.tar"
    assert paths["langref.html"] == bundled_root / "0.16.0" / "langref.html"
