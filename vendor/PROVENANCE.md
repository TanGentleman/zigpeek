# main.wasm provenance

**File:** `src/zigpeek/_vendor/main.wasm` (lives inside the package so
the binary travels with the wheel — `uv sync` editable installs, `uv build`,
and any future `uv tool install` all resolve it the same way via
`importlib.resources`. Build provenance and patches stay in this `vendor/`
directory and are not shipped in the wheel.)
**Size:** 198,076 bytes (~193 KB, ReleaseSmall)
**SHA256:** `a74b841e43de24a77f49a180b3148e6ea5f51ef3af83ecc846da8257cc4605b5`
**Built on:** 2026-05-03
**Built with Zig:** 0.16.0 (released)

## Source

Built from the [zig-mcp](https://github.com/zig-wasm/zig-mcp) project (the
upstream of the local `zig-docs` MCP server). The Zig source for this WASM
lives in `docs/` of that repo (`docs/main.zig`, `docs/Walk.zig`,
`docs/Decl.zig`, `docs/html_render.zig`, `docs/markdown.zig`).

- **Upstream commit:** `d804f936f9d6279b17e4c6d3dfcebb26a0c1ac2a`
- **Local patches:** `patches/walk-drop-asm-legacy.patch`
- **Build host checkout:** `~/Documents/GitHub/zig-mcp`

### Why a patch?

`build.zig.zon` pins `minimum_zig_version = 0.16.0-dev.205+4c0127566`, but
that exact dev tarball is no longer hosted on ziglang.org. `docs/Walk.zig`
references `Ast.Node.Tag.asm_legacy`, which was removed before the 0.16.0
release. The patch deletes that one switch arm so the file builds against
stable 0.16.0. The arm was a no-op (`.asm_legacy => {},`); dropping it is
semantically equivalent for any AST a 0.16.0 compiler can produce.

## Rebuild

```bash
cd ~/Documents/GitHub/zig-mcp
git fetch origin && git checkout <new-sha>
git apply <repo>/vendor/patches/walk-drop-asm-legacy.patch
zig build                                    # produces zig-out/main.wasm
cp zig-out/main.wasm <repo>/src/zigpeek/_vendor/main.wasm
shasum -a 256 <repo>/src/zigpeek/_vendor/main.wasm
# update SHA256 + commit + date in this file; refresh patch if upstream
# changed Walk.zig
```

If a future zig-mcp commit drops the `asm_legacy` arm upstream, delete the
patch and skip the `git apply` step.

## Why vendored?

Cloud agents have no Zig toolchain. Pre-building the WASM and committing it
to the repo lets the skill run with only Python + ziglang.org reachable.
The WASM is ~200 KB, infrequently changing, and reproducible from the
upstream commit + patch pinned above.
