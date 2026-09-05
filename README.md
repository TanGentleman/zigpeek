# zigpeek

Zig stdlib docs in a few seconds. Uses the Zig and agents you already have.

```sh
uv tool install zigpeek
```

```sh
zigpeek search ArrayList
zigpeek get std.Io.Dir.openFile
```

Zig master:

```sh
ZIGPEEK_VERSION=master zigpeek prefetch
```

Agent skill: `cp -r skills/zigpeek ~/.claude/skills/`

No Zig: `uv tool install 'zigpeek[offline]'`

MIT. [ARCHITECTURE.md](ARCHITECTURE.md).
