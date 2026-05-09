import os
from importlib.resources import files
from pathlib import Path

import httpx

_CACHE_ENV = "ZIGPEEK_CACHE_DIR"
_DEFAULT_CACHE_ROOT = Path("/tmp/zigpeek-cache")


def sources_tar_url(zig_version: str) -> str:
    return f"https://ziglang.org/documentation/{zig_version}/std/sources.tar"


def langref_url(zig_version: str) -> str:
    return f"https://ziglang.org/documentation/{zig_version}/"


def cache_dir_for(zig_version: str, override: Path | str | None = None) -> Path:
    if override is not None:
        return Path(override) / zig_version
    root = os.environ.get(_CACHE_ENV)
    base = Path(root) if root else _DEFAULT_CACHE_ROOT
    return base / zig_version


def bundled_path_for(zig_version: str, filename: str) -> Path:
    """Where a pre-bundled snapshot would live for a given version."""
    return Path(str(files("zigpeek").joinpath("_data", zig_version, filename)))


def _http_get_bytes(url: str) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.content


def _read_or_fetch(
    url: str,
    cache_path: Path,
    refresh: bool,
    bundled: Path | None = None,
) -> bytes:
    if not refresh and bundled is not None and bundled.exists():
        return bundled.read_bytes()
    if not refresh and cache_path.exists():
        return cache_path.read_bytes()
    data = _http_get_bytes(url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    return data


def fetch_sources_tar(
    zig_version: str,
    refresh: bool = False,
    cache_dir: Path | str | None = None,
) -> bytes:
    return _read_or_fetch(
        sources_tar_url(zig_version),
        cache_dir_for(zig_version, cache_dir) / "sources.tar",
        refresh,
        bundled=bundled_path_for(zig_version, "sources.tar"),
    )


def fetch_langref_html(
    zig_version: str,
    refresh: bool = False,
    cache_dir: Path | str | None = None,
) -> str:
    data = _read_or_fetch(
        langref_url(zig_version),
        cache_dir_for(zig_version, cache_dir) / "langref.html",
        refresh,
        bundled=bundled_path_for(zig_version, "langref.html"),
    )
    return data.decode("utf-8")


def prefetch(
    zig_version: str,
    refresh: bool = False,
    cache_dir: Path | str | None = None,
) -> dict[str, Path]:
    """Populate the cache so subsequent reads are network-free.

    Returns a mapping of {"sources.tar": path, "langref.html": path}
    pointing at whichever location the read path will resolve to next
    (bundled snapshot if present, otherwise cache).
    """
    fetch_sources_tar(zig_version, refresh=refresh, cache_dir=cache_dir)
    fetch_langref_html(zig_version, refresh=refresh, cache_dir=cache_dir)
    bundled_src = bundled_path_for(zig_version, "sources.tar")
    bundled_lang = bundled_path_for(zig_version, "langref.html")
    cache = cache_dir_for(zig_version, cache_dir)
    return {
        "sources.tar": bundled_src if bundled_src.exists() else cache / "sources.tar",
        "langref.html": (
            bundled_lang if bundled_lang.exists() else cache / "langref.html"
        ),
    }
