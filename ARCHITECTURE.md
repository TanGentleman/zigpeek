# Architecture

| File                              | Role                                                |
| --------------------------------- | --------------------------------------------------- |
| `src/zigpeek/cli.py`              | argparse entrypoint, exit-code contract             |
| `src/zigpeek/stdlib.py`           | markdown rendering (port of `zig-mcp/mcp/std.ts`)   |
| `src/zigpeek/wasm.py`             | wasmtime driver + typed wrapper around WASM exports |
| `src/zigpeek/builtins.py`         | langref HTML parser + ranking                       |
| `src/zigpeek/fetch.py`            | sources.tar / langref download + `/tmp` cache       |
| `src/zigpeek/version.py`          | default Zig version + override resolution           |
| `src/zigpeek/_vendor/main.wasm`   | autodoc WASM, shipped inside the package            |
| `vendor/PROVENANCE.md`            | build instructions + SHA256 + upstream commit       |
| `vendor/patches/`                 | local patches applied before rebuilding the WASM    |
| `skills/zigpeek/SKILL.md`         | skill metadata for Claude Code                      |

## Why a port and not a wrapper?

The autodoc renderer lives inside the WASM as HTML-emitting exports.
Wrapping the upstream MCP would mean shipping Node.js to every cloud
agent. Porting the ~700 lines of TS that drive the WASM gets us the same
output with only Python + a vendored binary.

## Updating the vendored WASM

Bumping the Zig version may need a fresh `main.wasm`. Build steps live in
[`vendor/PROVENANCE.md`](vendor/PROVENANCE.md). Summary:

```sh
cd ~/Documents/GitHub/zig-mcp
git pull
zig build
cp zig-out/main.wasm <repo>/src/zigpeek/_vendor/main.wasm
shasum -a 256 <repo>/src/zigpeek/_vendor/main.wasm
# update SHA256 + commit + date in vendor/PROVENANCE.md
```

Run smoke tests after updating:

```sh
ZIGPEEK_SMOKE=1 uv run pytest -v
```

## Testing

```sh
uv sync                              # install deps
uv run pytest -q                     # unit tests (no network)
ZIGPEEK_SMOKE=1 uv run pytest        # adds smoke tests (needs network + WASM)
```
