# Other Zig versions

`zigpeek[offline]` bundles docs for Zig **0.16.0** only. For any other version, use the plain install and fetch docs from `ziglang.org`.

## Install

```sh
uv tool install zigpeek                # or: pipx install zigpeek
```

## Selecting a version

When `zig` is on PATH (or `$ZIG` / `$ZIGPEEK_ZIG` points at a binary),
zigpeek uses that compiler's version and `lib/` by default. Pin a
ziglang.org tarball with `--version` / `ZIGPEEK_VERSION`, or point at
another tree with `--lib-dir` / `ZIGPEEK_LIB_DIR`:

```sh
zigpeek search ArrayList --version 0.15.1
ZIGPEEK_VERSION=master zigpeek search ArrayList
zigpeek get std.ArrayList --lib-dir /path/to/zig/lib
```

`builtins` still uses langref.html (download / `[offline]` bundle).

## Going offline

Warm the cache while you still have network — subsequent calls read from disk:

```sh
zigpeek prefetch --version 0.15.1
```

Cache lives under `$XDG_CACHE_HOME/zigpeek/<version>/` (or `~/.cache/zigpeek/<version>/`) by default. Override with `--cache-dir` or `ZIGPEEK_CACHE_DIR`:

```sh
zigpeek prefetch --version 0.15.1 --cache-dir /mnt/docs-cache
```

Pass the same `--cache-dir` on subsequent commands if you used a non-default location.

## Troubleshooting

- **`network/cache error`** — `ziglang.org` is blocked or unreachable. Run `zigpeek prefetch` from a network-enabled host first, or check your sandbox network policy.
- **`zigpeek: command not found`** — install via `uv tool install zigpeek` (or `pipx install zigpeek`). If neither is available, install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
