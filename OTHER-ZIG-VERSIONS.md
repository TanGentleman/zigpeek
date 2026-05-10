# Other Zig versions

`zigpeek[offline]` bundles docs for Zig **0.16.0** only. For any other version, use the plain install and fetch docs from `ziglang.org`.

## Install

```sh
uv tool install zigpeek                # or: pipx install zigpeek
```

## Selecting a version

```sh
zigpeek search ArrayList --version 0.15.1
ZIGPEEK_VERSION=master zigpeek search ArrayList
```

## Going offline

Warm the cache while you still have network — subsequent calls read from disk:

```sh
zigpeek prefetch --version 0.15.1
```

Cache lives under `/tmp/zigpeek-cache/<version>/` by default. Override with `--cache-dir` (or `ZIGPEEK_CACHE_DIR`) to persist outside `/tmp`:

```sh
zigpeek prefetch --version 0.15.1 --cache-dir ~/.cache/zigpeek
```

Pass the same `--cache-dir` on subsequent commands if you used a non-default location.

## Troubleshooting

- **`network/cache error`** — `ziglang.org` is blocked or unreachable. Run `zigpeek prefetch` from a network-enabled host first, or check your sandbox network policy.
- **`zigpeek: command not found`** — install via `uv tool install zigpeek` (or `pipx install zigpeek`). If neither is available, install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
