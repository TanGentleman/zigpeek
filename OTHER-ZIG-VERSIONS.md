# Versions, local compilers, and cache

When `zig` is on PATH (or `$ZIG` / `$ZIGPEEK_ZIG` points at a binary),
zigpeek uses that compiler's version and `lib/` by default. `search` /
`get` then need no network.

## Install without a local Zig

`zigpeek[offline]` bundles docs for Zig **0.16.0** only — the fallback
when no compiler is found:

```sh
uv tool install 'zigpeek[offline]'
uv tool install zigpeek                    # fetch 0.16.0 (or --version) on first use
```

## Pinning a version or tree

`--version` / `ZIGPEEK_VERSION` pins a ziglang.org tarball (and skips
the local `lib/`). `--lib-dir` / `ZIGPEEK_LIB_DIR` points at another
`lib/` or `std/` tree. Nightly version strings (`0.N.0-dev.+hash`)
fetch langref from `/documentation/master/`.

```sh
zigpeek search ArrayList --version 0.15.1
ZIGPEEK_VERSION=master zigpeek search ArrayList
zigpeek get std.ArrayList --lib-dir /path/to/zig/lib
```

`builtins` still uses langref.html (download / `[offline]` bundle /
`/documentation/master/` for nightlies).

## Going offline without a compiler

Warm the cache while you still have network — subsequent calls read from disk:

```sh
zigpeek prefetch --version 0.15.1
```

Cache lives under `$XDG_CACHE_HOME/zigpeek/<version>/` (or `~/.cache/zigpeek/<version>/`).
Override with `--cache-dir` or `ZIGPEEK_CACHE_DIR`:

```sh
zigpeek prefetch --version 0.15.1 --cache-dir /mnt/docs-cache
```

Pass the same `--cache-dir` on subsequent commands if you used a non-default location.

## Troubleshooting

- **`network/cache error`** — no local `zig`, and `ziglang.org` is blocked or the `[offline]` bundle is missing. Run `zigpeek prefetch` from a network-enabled host, or install Zig.
- **`zigpeek: command not found`** — install via `uv tool install zigpeek` (or `pipx install zigpeek`). If neither is available, install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
