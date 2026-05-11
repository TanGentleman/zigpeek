---
name: zig-0.15-to-0.16
description: Port Zig code from 0.15.x to 0.16.0. Use when upgrading a Zig project, when a project pins to 0.15.1/0.15.2, or when reviewing code with pre-0.16 idioms (`std.fs.cwd()`, `file.close()` with no arg, `pub fn main() !void` doing I/O, `GeneralPurposeAllocator`, `std.Thread.Pool`, `std.io.fixedBufferStream`, `@Type(...)`). Pairs with the `zigpeek` CLI to verify each migration's signature against the real 0.16 stdlib.
---

# Zig 0.15.x → 0.16.0

0.16 is the **"I/O as an Interface"** release. Almost anything that blocks, allocates, or touches the OS now takes an `Io` parameter. Mechanical but voluminous; this skill captures the highest-leverage rows so you spend time on signatures, not on guessing namespaces.

This skill is intentionally non-exhaustive. **Add rows as you hit them** — see "Extending" below.

## Triage

1. `zig version` → 0.16.0. Run `zig build` and group errors.
2. Fix `main` first: adopt `std.process.Init` so you have an `io`.
3. Thread `io: std.Io` (and `gpa: Allocator`) through the call graph.
4. Walk the table below. For anything not listed, run `zigpeek get <fqn>` (cold ~1 s; use `zigpeek batch` for ≥3 lookups) before guessing.

## main + Io plumbing

```zig
// 0.15
pub fn main() !void {
    var gpa: std.heap.GeneralPurposeAllocator(.{}) = .{};
    defer _ = gpa.deinit();
    // ...
}

// 0.16
pub fn main(init: std.process.Init) !void {
    const io = init.io; // std.Io
    const gpa = init.gpa; // DebugAllocator (Debug)
    const arena = init.arena.allocator();
    const args = try init.minimal.args.toSlice(arena);
    const env = init.environ_map; // *Environ.Map
    _ = .{ io, gpa, args, env };
}
```

In tests use `std.testing.io`. Escape hatch for program edges (top-level tools, scripts) — not from inside libraries:

```zig
var threaded: std.Io.Threaded = .init_single_threaded;
const io = threaded.io();
```

## Before → After

Rows are in priority order. Verify any non-obvious row with the `zigpeek` lookup in the right column.

| 0.15.x                                                | 0.16.0                                                                   | Verify with                              |
| ----------------------------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------- |
| `std.fs.cwd().openFile(p, .{})`                       | `std.Io.Dir.cwd().openFile(io, p, .{})`                                  | `zigpeek get std.Io.Dir.openFile`        |
| `file.close()`                                        | `file.close(io)`                                                         | `zigpeek get std.Io.File.close`          |
| `dir.makeDir(p)`                                      | `dir.createDir(io, p, .default_dir)`                                     | `zigpeek get std.Io.Dir.createDir`       |
| `cwd().readFileAlloc(gpa, p, 1234)`                   | `cwd().readFileAlloc(io, p, gpa, .limited(1234))` (`error.StreamTooLong` replaces `FileTooBig`) | `zigpeek get std.Io.Dir.readFileAlloc`   |
| `file.setEndPos(n)` / `getEndPos()`                   | `file.setLength(io, n)` / `file.length(io)`                              | `zigpeek get std.Io.File.length`         |
| `std.process.getCwdAlloc(gpa)`                        | `std.process.currentPathAlloc(io, gpa)`                                  | `zigpeek get std.process.currentPathAlloc` |
| `std.process.Child.run(.{...})`                       | `std.process.run(gpa, io, .{...})`                                      | `zigpeek get std.process.run`            |
| `std.process.Child.init(argv, gpa); …spawn()`         | `try std.process.spawn(io, .{ .argv = argv, ... })`                      | `zigpeek get std.process.spawn`          |
| `std.process.execv(arena, argv)`                      | `std.process.replace(io, .{ .argv = argv })`                             | `zigpeek get std.process.replace`        |
| `std.os.environ` / `getEnvVarOwned`                   | `init.environ_map.get(key)` or `init.minimal.environ.getPosix(key)`      | `zigpeek get std.process.Environ`        |
| `std.io.fixedBufferStream(buf).reader()`              | `var r: std.Io.Reader = .fixed(buf);`                                    | `zigpeek get std.Io.Reader.fixed`        |
| `std.io.fixedBufferStream(buf).writer()`              | `var w: std.Io.Writer = .fixed(buf);`                                    | `zigpeek get std.Io.Writer.fixed`        |
| `std.leb.readUleb128(r, T)`                           | `r.takeLeb128(T)`                                                        | `zigpeek get std.Io.Reader.takeLeb128`   |
| `file.read(buf)` / `pread`                            | `file.readStreaming(...)` / `readPositional(...)`                        | `zigpeek get std.Io.File.readStreaming`  |
| `std.Thread.Pool` + `spawnWg` / `WaitGroup`           | `var g: std.Io.Group = .init; g.async(io, fn, ...); try g.await(io);`    | `zigpeek get std.Io.Group`               |
| `std.Thread.Mutex` / `Condition` / `ResetEvent` *(inside async tasks)* | `std.Io.Mutex` / `Io.Condition` / `Io.Event`            | `zigpeek get std.Io.Mutex`               |
| `GeneralPurposeAllocator`                             | `DebugAllocator` (renamed in 0.15; carryover)                            | `zigpeek get std.heap.DebugAllocator`    |
| `std.heap.ThreadSafeAllocator`                        | removed — `ArenaAllocator` is now lock-free; redesign rather than wrap    | —                                        |
| `AutoArrayHashMapUnmanaged` / `ArrayHashMap`          | `std.array_hash_map.Auto` / `.String` / `.Custom`                         | `zigpeek search array_hash_map`          |
| `PriorityQueue.init(...)`, `.add`, `.remove`          | `var q: PriorityQueue(...) = .empty;` then `.push` / `.pop`              | `zigpeek get std.PriorityQueue`          |
| `@Type(.{ .int = .{ .signedness = .unsigned, .bits = N } })` | `@Int(.unsigned, N)`                                               | `zigpeek builtins get Int`               |
| `@Type(.{ .@"struct" = ... })` etc.                   | `@Struct(layout, BackingInt, names, types, attrs)` (and `@Union` / `@Enum` / `@Fn` / `@Pointer` / `@Tuple` / `@EnumLiteral`); reify of error sets is gone | `zigpeek builtins get Struct`       |
| `@cImport({ @cInclude("foo.h"); })` *(still valid)*   | `b.addTranslateC(.{ .root_source_file = b.path("c.h"), ... }).createModule()` then `@import("c")` *(now idiomatic)* | `zigpeek search addTranslateC`   |
| `std.posix.PROT.READ \| std.posix.PROT.WRITE`         | `.{ .READ = true, .WRITE = true }`                                      | `zigpeek search mmap`                    |
| `std.posix.mlock(slice)` / `mlockall(...)`            | `std.process.lockMemory(slice, .{})` / `lockMemoryAll(.{...})`           | `zigpeek get std.process.lockMemory`     |
| `dir.atomicFile(io, p, .{...})` then `flush() + renameIntoPlace()` | `dir.createFileAtomic(io, p, .{ .replace = true, .make_path = true })` then `flush() + replace(io)` | `zigpeek get std.Io.Dir.createFileAtomic` |
| `std.fs.path.relative(gpa, from, to)`                 | `std.fs.path.relative(gpa, cwd_path, environ_map, from, to)` (now pure)  | `zigpeek get std.fs.path.relative`       |
| `writer.print("{D}", .{ns})`                          | `writer.print("{f}", .{std.Io.Duration{ .nanoseconds = ns }})`           | `zigpeek get std.Io.Duration`            |
| Error: `RenameAcrossMountPoints` / `NotSameFileSystem`| `error.CrossDevice`                                                      | —                                        |
| Error: `SharingViolation`                             | `error.FileBusy`                                                         | —                                        |
| Error: `EnvironmentVariableNotFound`                  | `error.EnvironmentVariableMissing`                                       | —                                        |

Removed with no replacement: `SegmentedList`, `meta.declList`, `Thread.Mutex.Recursive`, `std.once`, `std.Thread.Pool`, `fs.getAppDataDir`, `DynLib` on Windows, `builtin.subsystem`.

The reader/writer "Generic"/"Any" wrappers (`Io.GenericReader` / `AnyReader` / `GenericWriter` / `AnyWriter` / `null_writer` / `CountingReader`) are gone because `std.Io.Reader` / `std.Io.Writer` *are* the vtable-backed abstraction now — use them directly.

## Pitfalls

- **`reader.interface` / `writer.interface` must be by reference.** `const r = &fr.interface;` Copying detaches it from the parent and hides the real error.
- **`error.ReadFailed` / `error.WriteFailed` are placeholders.** Catch them and propagate `fr.err.?` / `fw.err.?` — including `error.Canceled`, which is mandatory under any `Io` impl that supports cancelation.
- **`Walker.deinit()` takes no args**; `Dir.close(io)` and `File.close(io)` do. Mixing produces confusing compile errors.
- **Sync primitives inside `io.async` / `Group.async` tasks must be `Io.*`, not `std.Thread.*`.** Mixing is a correctness bug under `Io.Evented` (it'll happen to work under `Io.Threaded`).
- **Returning the address of a local** (`return &x;`) is a hard compile error in 0.16. Almost always a real bug; fix the lifetime.
- **`extern` enums / packed types need explicit backing types** — `enum(u8) {...}`, `packed struct(u32) {...}`. Inferred is rejected.

## Extending

This skill grows with the projects you migrate. When you hit a 0.15 idiom not in the table:

1. Add a row in priority order (filesystem/process > readers/writers > containers/sync > language > build).
2. Include a `zigpeek get <fqn>` (or `zigpeek search <q>`) lookup so the next reader can verify the signature without reading release notes.
3. If a whole category emerges (build system, crypto, networking), start a new section rather than an unwieldy table.

Cross-check signatures at commit time, not edit time:

```sh
zigpeek prefetch
zigpeek batch <<'EOF'
get std.Io.Dir.openFile
get std.process.spawn
get std.Io.Reader.takeLeb128
EOF
```

If `zigpeek` 404s on an inner type, retry with the defining module path (e.g. `std.multi_array_list.MultiArrayList.Slice`, not `std.MultiArrayList.Slice`).
