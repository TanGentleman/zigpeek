# zigpeek

Look up Zig standard library docs from the command line. Install takes a few
seconds and plugs into the Zig and agents you already use.

```sh
uv tool install zigpeek
```

It uses the `zig` you already have. Search when you don't know the name, get
docs when you do:

```sh
zigpeek search ArrayList
zigpeek get std.Io.Dir.openFile
```

For an agent, copy the skill next to the ones you already have:

```sh
cp -r skills/zigpeek ~/.claude/skills/
```

or into whatever skills folder your agent already uses. After that, the agent
can run `zigpeek info` and look things up on its own.

No Zig on this machine? This install includes the docs:

```sh
uv tool install 'zigpeek[offline]'
```

MIT. How it works: [`ARCHITECTURE.md`](ARCHITECTURE.md).
