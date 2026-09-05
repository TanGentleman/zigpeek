"""Pack a local Zig compiler ``lib/`` into the autodoc ``sources.tar`` layout.

The official docs tarball is just the compiler's ``lib/std/**/*.zig`` (no
``*test.zig``) with each path prefixed ``std/``. Feeding that same layout
lets ``search`` / ``get`` skip the ziglang.org download.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

_LIB_DIR_ENV = "ZIGPEEK_LIB_DIR"
_AUTO = frozenset({"zig", "auto"})


def resolve_lib_dir(cli_value: str | None) -> Path | None:
    """Resolve ``--lib-dir`` / ``ZIGPEEK_LIB_DIR`` to a filesystem path.

    ``None`` means "use the download/cache path". The sentinels ``zig``
    and ``auto`` run ``zig env`` and use its ``lib_dir``.
    """
    raw = cli_value if cli_value is not None else os.environ.get(_LIB_DIR_ENV)
    if not raw:
        return None
    if raw in _AUTO:
        return lib_dir_from_zig_env()
    return Path(raw).expanduser()


def lib_dir_from_zig_env() -> Path:
    try:
        proc = subprocess.run(
            ["zig", "env"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except FileNotFoundError as e:
        raise FileNotFoundError(
            "zig not found on PATH; pass --lib-dir /path/to/zig/lib"
        ) from e
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e)).strip()
        raise FileNotFoundError(f"zig env failed: {err}") from e
    except subprocess.TimeoutExpired as e:
        raise FileNotFoundError("zig env timed out") from e
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise FileNotFoundError("zig env produced invalid JSON") from e
    lib = data.get("lib_dir")
    if not lib:
        raise FileNotFoundError("zig env did not report lib_dir")
    return Path(lib)


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
