# zigpeek

Fast CLI for Zig 0.16 stdlib + Skill for coding agents.

## Install

```sh
uv tool install 'zigpeek[offline]'     # bundles Zig 0.16.0 docs; no network needed
```

For other Zig versions, see [`OTHER-ZIG-VERSIONS.md`](OTHER-ZIG-VERSIONS.md).

## Usage

```sh
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
