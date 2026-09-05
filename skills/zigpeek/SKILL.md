---
name: zigpeek
description: Look up Zig stdlib with the local zigpeek CLI. Run zigpeek info first. Use before writing or reviewing Zig that touches files, dirs, or process state — especially std.Io, Reader/Writer, and std.process.Init.
---

# zigpeek

```sh
zigpeek info
```

That prints when/how to use this CLI, where the binaries are, and which Zig version is active.

If missing: `uv tool install zigpeek` (or `"zigpeek[offline]"` when the sandbox has no zig).
