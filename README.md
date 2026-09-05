# zigpeek

Fast CLI for Zig stdlib docs. Uses the `zig` on PATH (or `$ZIG` / `$ZIGPEEK_ZIG`); otherwise Zig 0.16.0 from `[offline]`, cache, or ziglang.org.

```sh
uv tool install zigpeek
uv tool install 'zigpeek[offline]'   # no local zig
```

```sh
zigpeek info          # when/how, binaries, active Zig
zigpeek --help
```

`--version` / `$ZIGPEEK_VERSION` pins a ziglang.org tarball (skips local `lib/`). `--lib-dir` / `$ZIGPEEK_LIB_DIR` points at another tree. `prefetch` warms `$XDG_CACHE_HOME/zigpeek` (or `~/.cache/zigpeek`). Nightlies fetch langref from `/documentation/master/`.

Skill: `cp -r skills/zigpeek ~/.claude/skills/`

MIT. Internals: [`ARCHITECTURE.md`](ARCHITECTURE.md). WASM: [`vendor/PROVENANCE.md`](vendor/PROVENANCE.md).
