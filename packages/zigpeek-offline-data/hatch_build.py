"""Hatch build hook: download Zig docs into the wheel staging dir.

Runs once per ``uv build`` for ``zigpeek-offline-data``. Stdlib-only — the
data wheel must not pull httpx in just to build itself.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# Keep in lockstep with zigpeek's DEFAULT_ZIG_VERSION.
ZIG_VERSION = "0.16.0"

_SOURCES = (
    "sources.tar",
    f"https://ziglang.org/documentation/{ZIG_VERSION}/std/sources.tar",
)
_LANGREF = (
    "langref.html",
    f"https://ziglang.org/documentation/{ZIG_VERSION}/",
)


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        target = (
            Path(self.root)
            / "src"
            / "zigpeek_offline_data"
            / ZIG_VERSION
        )
        target.mkdir(parents=True, exist_ok=True)
        for filename, url in (_SOURCES, _LANGREF):
            dest = target / filename
            if dest.exists() and dest.stat().st_size > 0:
                continue
            with urllib.request.urlopen(url, timeout=60) as r:
                dest.write_bytes(r.read())
