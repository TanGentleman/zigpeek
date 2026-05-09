# zigpeek

Fast CLI for Zig 0.16 stdlib + Skill for coding agents. Replaces the
[`zig-docs` MCP server](https://github.com/loonghao/zig-mcp) where MCP
isn't available — typically cloud agents.

## Install

```sh
uv tool install zigpeek
# or
pipx install zigpeek
```

## Usage

```sh
zigpeek prefetch                                 # warm cache (once per session)
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

## Use as a Claude Code skill

```sh
cp -r skills/zigpeek ~/.claude/skills/
```

Assumes `zigpeek` is on `$PATH` (see [Install](#install)). Full
agent-facing docs live in [`skills/zigpeek/SKILL.md`](skills/zigpeek/SKILL.md).

## License

MIT — see [`LICENSE`](LICENSE). Bundled `main.wasm` is also MIT (from
[`zig-mcp`](https://github.com/loonghao/zig-mcp)); see
[`vendor/PROVENANCE.md`](vendor/PROVENANCE.md). Internals and contributor
notes live in [`ARCHITECTURE.md`](ARCHITECTURE.md).
