# zigpeek

Fast CLI for Zig stdlib docs. Uses your local `zig` when one is on PATH.

## Install

```sh
uv tool install zigpeek                    # local zig, or fetch 0.16.0 docs
uv tool install 'zigpeek[offline]'         # also bundles 0.16.0 for no-zig hosts
```

For version pins, `--lib-dir`, and cache paths, see [`OTHER-ZIG-VERSIONS.md`](OTHER-ZIG-VERSIONS.md).

## Usage

```sh
zigpeek info                                     # usage, binaries, active Zig
zigpeek search ArrayList --limit 10              # fuzzy stdlib search
zigpeek get std.ArrayList                        # full docs for an FQN
zigpeek get std.ArrayList --source-file          # source file containing it
zigpeek builtins list                            # all @-builtins
zigpeek builtins get atomic                      # specific builtin
zigpeek batch <<EOF                              # amortize startup
search ArrayList
get std.ArrayList
EOF
```

When `zig` is on PATH (or `$ZIG` / `$ZIGPEEK_ZIG`), `search` / `get` read
that compiler's `lib/`. Otherwise zigpeek falls back to Zig 0.16.0 from
the `[offline]` bundle, the XDG cache, or ziglang.org.

## Claude Code skill

```sh
cp -r skills/zigpeek ~/.claude/skills/
```

See [`skills/zigpeek/SKILL.md`](skills/zigpeek/SKILL.md) for the
agent-facing usage.

## License

MIT — see [`LICENSE`](LICENSE) and [`ARCHITECTURE.md`](ARCHITECTURE.md)
for internals.

## Credits

The vendored autodoc WASM is built from
[`zig-wasm/zig-mcp`](https://github.com/zig-wasm/zig-mcp); see
[`vendor/PROVENANCE.md`](vendor/PROVENANCE.md).
