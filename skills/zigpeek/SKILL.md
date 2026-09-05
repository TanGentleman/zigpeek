---
name: zigpeek
description: Look up Zig standard library APIs and builtin functions via a local CLI. Prefers the zig on PATH (or $ZIG / $ZIGPEEK_ZIG); otherwise Zig 0.16.0. Use before writing or reviewing Zig that touches stdlib — critical for std.Io filesystem APIs (std.Io.Dir, std.Io.File), Reader/Writer interfaces, and std.process.Init. Triggers when answering "how do I X in Zig" or writing Zig that touches files, dirs, env, or process state.
---

# zigpeek

Look up Zig stdlib APIs and `@` builtins via a local CLI. **Start by running:**

```sh
zigpeek info
```

That prints how to use this skill, where the `zigpeek` and `zig` binaries are, and which Zig version is active.

If `zigpeek` is missing:

```sh
uv tool install zigpeek                    # enough if the sandbox has zig
uv tool install "zigpeek[offline]"         # bundles 0.16.0 when it does not
```

Then re-run `zigpeek info`.
