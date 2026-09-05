import os
import tempfile
from importlib.resources import files
from pathlib import Path

import httpx

_CACHE_ENV = "ZIGPEEK_CACHE_DIR"


def docs_slug(zig_version: str) -> str:
    """ziglang.org documentation path for a compiler version string.

    Nightlies are not hosted under ``0.N.0-dev.+hash``; they live at
    ``/documentation/master/``.
    """
    if zig_version in ("master", "latest") or "-dev" in zig_version or "+" in zig_version:
        return "master"
    return zig_version


def sources_tar_url(zig_version: str) -> str:
    return f"https://ziglang.org/documentation/{docs_slug(zig_version)}/std/sources.tar"


def langref_url(zig_version: str) -> str:
    return f"https://ziglang.org/documentation/{docs_slug(zig_version)}/"


def default_cache_root() -> Path:
    """XDG/platform cache root (no version suffix).

    ``ZIGPEEK_CACHE_DIR`` and ``--cache-dir`` override this. Last-resort
    fallback is ``$TMPDIR/zigpeek`` when no home directory is available.
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "zigpeek"
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "zigpeek"
    try:
        return Path.home() / ".cache" / "zigpeek"
    except (RuntimeError, KeyError):
        return Path(tempfile.gettempdir()) / "zigpeek"


def cache_dir_for(zig_version: str, override: Path | str | None = None) -> Path:
    if override is not None:
        return Path(override) / zig_version
    root = os.environ.get(_CACHE_ENV)
    base = Path(root) if root else default_cache_root()
    return base / zig_version


def bundled_path_for(zig_version: str, filename: str) -> Path:
    """Where a pre-bundled snapshot would live for a given version.

    Resolves to the ``zigpeek-offline`` companion package when
    installed (i.e. ``zigpeek[offline]``). Falls back to an in-package
    ``_data`` directory used by manual snapshot drops.
    """
    try:
        companion = files("zigpeek_offline").joinpath(zig_version, filename)
        p = Path(str(companion))
        if p.is_file():
            return p
    except (ModuleNotFoundError, FileNotFoundError):
        pass
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
