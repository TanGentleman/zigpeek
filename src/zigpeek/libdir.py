"""Pack a local Zig compiler ``lib/`` into the autodoc ``sources.tar`` layout.

The official docs tarball is just the compiler's ``lib/std/**/*.zig`` (no
``*test.zig``) with each path prefixed ``std/``. Feeding that same layout
lets ``search`` / ``get`` skip the ziglang.org download.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

_LIB_DIR_ENV = "ZIGPEEK_LIB_DIR"
_ZIG_BIN_ENVS = ("ZIGPEEK_ZIG", "ZIG")
_AUTO = frozenset({"zig", "auto"})
_LIB_DIR_RE = re.compile(r'\.lib_dir\s*=\s*"([^"]+)"')
_VERSION_RE = re.compile(r'\.version\s*=\s*"([^"]+)"')


@dataclass(frozen=True)
class ZigEnv:
    exe: str
    lib_dir: Path
    version: str


def zig_binary() -> str | None:
    """Path to a Zig executable: ``ZIGPEEK_ZIG``, then ``ZIG``, then PATH."""
    for key in _ZIG_BIN_ENVS:
        val = os.environ.get(key)
        if val:
            return val
    return shutil.which("zig")


def probe_zig(exe: str | None = None) -> ZigEnv | None:
    """Return env info for a working compiler, or ``None`` if none is usable."""
    cmd = exe or zig_binary()
    if not cmd:
        return None
    try:
        proc = subprocess.run(
            [cmd, "env"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    lib_m = _LIB_DIR_RE.search(proc.stdout)
    ver_m = _VERSION_RE.search(proc.stdout)
    if not lib_m or not ver_m:
        return None
    lib = Path(lib_m.group(1))
    if not lib.is_absolute():
        lib = (Path.cwd() / lib).resolve()
    if not lib.exists():
        return None
    return ZigEnv(exe=cmd, lib_dir=lib, version=ver_m.group(1))


def resolve_lib_dir(cli_value: str | None, *, auto: bool = False) -> Path | None:
    """Resolve ``--lib-dir`` / ``ZIGPEEK_LIB_DIR`` to a filesystem path.

    ``None`` means "use the download/cache path". The sentinels ``zig``
    and ``auto`` run ``zig env``. When ``auto`` is true and nothing was
    specified, a valid compiler on PATH / ``ZIG`` / ``ZIGPEEK_ZIG`` is used.
    """
    raw = cli_value if cli_value is not None else os.environ.get(_LIB_DIR_ENV)
    if raw:
        if raw in _AUTO:
            return lib_dir_from_zig_env()
        return Path(raw).expanduser()
    if auto:
        env = probe_zig()
        if env is not None:
            return env.lib_dir
    return None


def lib_dir_from_zig_env() -> Path:
    env = probe_zig()
    if env is None:
        raise FileNotFoundError(
            "zig not found on PATH; pass --lib-dir /path/to/zig/lib "
            "or set ZIG / ZIGPEEK_ZIG"
        )
    return env.lib_dir


def resolve_std_dir(lib_dir: Path) -> Path:
    """Accept either the compiler ``lib/`` or the ``std/`` directory itself."""
    lib_dir = lib_dir.expanduser().resolve()
    if not lib_dir.exists():
        raise FileNotFoundError(f"lib dir not found: {lib_dir}")
    candidates = []
    if (lib_dir / "std").is_dir():
        candidates.append(lib_dir / "std")
    candidates.append(lib_dir)
    for std_dir in candidates:
        if (std_dir / "std.zig").is_file() or (std_dir / "root.zig").is_file():
            return std_dir
    raise FileNotFoundError(
        f"{lib_dir} is not a Zig lib/ or std/ directory "
        "(expected std/std.zig or std.zig)"
    )


def pack_lib_dir(lib_dir: Path | str) -> bytes:
    """Return an uncompressed tar matching ziglang.org's ``sources.tar``."""
    std_dir = resolve_std_dir(Path(lib_dir))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for path in sorted(p for p in std_dir.rglob("*.zig") if p.is_file()):
            if path.name.endswith("test.zig"):
                continue
            data = path.read_bytes()
            info = tarfile.TarInfo(name=f"std/{path.relative_to(std_dir).as_posix()}")
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()
