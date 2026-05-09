---
name: zigpeek
description: Look up Zig 0.16 standard library APIs and builtin functions via a local CLI (replaces the zig-docs MCP server in environments without MCP support, e.g. cloud agents). Use before writing or reviewing Zig code that touches stdlib — critical for std.Io filesystem APIs (std.Io.Dir, std.Io.File), Reader/Writer interfaces, and std.process.Init. Triggers when answering "how do I X in Zig" or writing Zig that touches files, dirs, env, or process state. If the zig-docs MCP server is already connected, prefer it over this CLI.
---

# zigpeek

A Python+wasmtime port of the four `zig-docs` MCP tools. Loads the same
autodoc WASM module the official Zig docs use, against the same
`sources.tar` from `ziglang.org`. Output is markdown, byte-equivalent
(modulo whitespace) to what the MCP returns.

## Setup (run once per agent session/sandbox)

Install the `zigpeek` CLI globally with either tool:

```sh
pipx install git+https://github.com/TanGentleman/zigpeek
# or
uv tool install git+https://github.com/TanGentleman/zigpeek
```

Then warm the cache so subsequent lookups are offline:

```sh
zigpeek prefetch
```

Requires outbound network access to `ziglang.org` on first use. Caches
downloads under `/tmp/zigpeek-cache/<version>/`.

## Usage

```sh
# Search the stdlib
zigpeek search ArrayList --limit 10

# Get full docs for a stdlib item
zigpeek get std.ArrayList

# Get the source file containing an item
zigpeek get std.ArrayList --source-file

# List all builtin functions
zigpeek builtins list

# Look up a builtin (by name or keyword)
zigpeek builtins get atomic

# Pre-populate the cache (so later commands don't need network)
zigpeek prefetch
```

## When to use which command

| Need                                              | Command                           |
| ------------------------------------------------- | --------------------------------- |
| Discover stdlib symbols matching a keyword        | `zigpeek search <q>`              |
| Read full docs + signature for a known FQN        | `zigpeek get <fqn>`               |
| Read the full source file (terse docstring; want invariants, internals, or per-field implementation) | `zigpeek get <fqn> --source-file` |
| Browse all `@`-builtins                           | `zigpeek builtins list`           |
| Look up a specific `@builtin` (accepts `atomic` or `@atomic`) | `zigpeek builtins get <q>` |
| Warm cache before going offline                   | `zigpeek prefetch`                |
| Run several lookups in one process (cheap)        | `zigpeek batch`                   |

## Batching multiple lookups

Each `zigpeek` invocation pays ~1 s of Python+wasmtime startup. If you
plan more than two lookups, pipe them through `zigpeek batch` to share
that cost across the whole sequence — the WASM instance and parsed
sources are reused between commands.

```sh
zigpeek batch <<'EOF'
search ArrayList --limit 5
get std.ArrayList
get std.ArrayList --source-file
builtins get atomic
EOF
```

Each command's output is framed with a `===> <command>` separator on its
own line. Per-line failures (not-found, bad input) are reported inline
and **do not abort the batch**; the process exit code is the worst code
seen across all lines (`0` if every command succeeded). `prefetch` and
nested `batch` are rejected — run them outside.

Use `zigpeek batch -f commands.txt` to read from a file instead of
stdin. Blank lines and lines starting with `#` are ignored.

**Reach for `--source-file` early** when:

- The docstring is one line or missing.
- The page lists a method signature but elides the body (e.g.
  `MultiArrayList.items` shows the prototype but the per-field pointer
  math from `ptrs[@intFromEnum(field)]` only lives in the source).
- You need invariants, error sets, or how a private field is computed.

## Finding nested types

Inner types live under the **defining module's path**, not the
re-export. `std.MultiArrayList` is a re-export from
`std.multi_array_list`; its inner `Slice` type only resolves at the
defining path:

```sh
zigpeek get std.multi_array_list.MultiArrayList.Slice   # works
zigpeek get std.MultiArrayList.Slice                    # not found
```

If `search` only surfaces a re-export and `get` 404s on the inner type,
re-run `get` with the module path.

## Version override

Defaults to Zig `0.16.0`. Override with:

```sh
zigpeek search ArrayList --version 0.15.1
ZIGPEEK_VERSION=master zigpeek search ArrayList
```

## Offline mode

If the agent will run without internet, prefetch first while you still
have network:

```sh
# Default cache (/tmp/zigpeek-cache/<version>/)
zigpeek prefetch

# Custom cache directory (persists outside /tmp)
zigpeek prefetch --cache-dir ~/.cache/zigpeek
```

After prefetch, every `search` / `get` / `builtins` call reads from disk
and never touches the network. Pass the same `--cache-dir` (or set
`ZIGPEEK_CACHE_DIR`) on subsequent commands if you used a non-default
location.

If a bundled snapshot ships inside the package (`src/zigpeek/_data/<version>/`),
the read path uses it automatically and prefetch becomes a no-op.

## Exit codes

- `0` — success (markdown on stdout)
- `1` — bad input or "not found" (message on stderr)
- `2` — network/cache failure (message on stderr)

## Troubleshooting

- **`zigpeek: command not found`** — install via `pipx install git+https://github.com/TanGentleman/zigpeek`
  (or `uv tool install ...`). If neither tool is available, install uv:
  `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **`network/cache error`** — `ziglang.org` is blocked or unreachable.
  Run `zigpeek prefetch` from a network-enabled host first, or check
  your sandbox network policy.
- **`Declaration "..." not found`** — the FQN is wrong. Two things to
  try: (1) `zigpeek search` to discover the canonical name; (2) if you
  searched a re-export (e.g. `std.MultiArrayList`), retry `get` against
  the defining module path (e.g. `std.multi_array_list.MultiArrayList`).
