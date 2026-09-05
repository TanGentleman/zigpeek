---
name: zigpeek
description: Look up Zig standard library APIs and builtin functions via a local CLI. Prefers the zig on PATH (or $ZIG / $ZIGPEEK_ZIG); otherwise Zig 0.16.0. Use before writing or reviewing Zig that touches stdlib — critical for std.Io filesystem APIs (std.Io.Dir, std.Io.File), Reader/Writer interfaces, and std.process.Init. Triggers when answering "how do I X in Zig" or writing Zig that touches files, dirs, env, or process state.
---

# zigpeek

```sh
zigpeek info
```

That prints when/how to use this CLI, where the binaries are, and which Zig version is active.

If missing: `uv tool install zigpeek` (or `"zigpeek[offline]"` when the sandbox has no zig).
