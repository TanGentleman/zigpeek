# Architecture

| File                              | Role                                                |
| --------------------------------- | --------------------------------------------------- |
| `src/zigpeek/cli.py`              | argparse entrypoint, exit-code contract             |
| `src/zigpeek/stdlib.py`           | markdown rendering against the autodoc WASM         |
| `src/zigpeek/wasm.py`             | wasmtime driver + typed wrapper around WASM exports |
| `src/zigpeek/builtins.py`         | langref HTML parser + ranking                       |
| `src/zigpeek/fetch.py`            | sources.tar / langref download + `/tmp` cache       |
| `src/zigpeek/version.py`          | default Zig version + override resolution           |
| `src/zigpeek/_vendor/main.wasm`   | autodoc WASM, shipped inside the package            |
| `vendor/PROVENANCE.md`            | build instructions + SHA256 + upstream commit       |
| `vendor/patches/`                 | local patches applied before rebuilding the WASM    |
| `packages/zigpeek-offline/`       | data wheel for the `[offline]` extra                |
| `skills/zigpeek/SKILL.md`         | skill metadata for Claude Code                      |

## The `[offline]` extra

`uv tool install 'zigpeek[offline]'` pulls in the `zigpeek-offline`
data wheel, which ships a prefetched `sources.tar` + `langref.html` for
`DEFAULT_ZIG_VERSION`. At runtime `fetch.bundled_path_for` checks that
package first, so first use needs no network. Other Zig versions still
fetch on demand.

The data wheel is a uv workspace member built by a custom hatch hook
(`packages/zigpeek-offline/hatch_build.py`) that downloads the files at
wheel-build time — no manual prefetch step.

## Releasing

`./scripts/bump-version.sh X.Y.Z` rewrites the version literal in both
`pyproject.toml`s and the `==` pin in the main one. Then:

```sh
git commit -am "release X.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

CI (`release.yml`) builds both wheels, verifies versions match the tag,
publishes via PyPI trusted publishing, and attaches artifacts to a
GitHub Release. If `DEFAULT_ZIG_VERSION` changes, also bump
`ZIG_VERSION` in `packages/zigpeek-offline/hatch_build.py` first.

## Updating the vendored WASM

Bumping the Zig version may need a fresh `main.wasm`. Full build steps
(upstream repo, patches, SHA256 update) live in
[`vendor/PROVENANCE.md`](vendor/PROVENANCE.md).

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
