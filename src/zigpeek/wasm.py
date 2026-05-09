import struct

import wasmtime

_INVALID_INDEX = 0xFFFF_FFFF


def unpack_string(memory: bytes, ptr: int, length: int) -> str:
    if length == 0:
        return ""
    return memory[ptr : ptr + length].decode("utf-8", errors="replace")


def unpack_slice32(memory: bytes, ptr: int, length: int) -> list[int]:
    if length == 0:
        return []
    return list(struct.unpack_from(f"<{length}I", memory, ptr))


def unpack_slice64(memory: bytes, ptr: int, length: int) -> list[int]:
    if length == 0:
        return []
    return list(struct.unpack_from(f"<{length}Q", memory, ptr))


def split_packed(packed: int) -> tuple[int, int]:
    """Decode the JS BigInt packing: low32 = ptr, high32 = length."""
    return packed & 0xFFFFFFFF, packed >> 32


class WasmStd:
    """Drive the autodoc WASM module loaded from sources.tar.

    Mirrors the JS interface in ~/Documents/GitHub/zig-mcp/mcp/std.ts.
    The WASM imports a single js.log function (level, ptr, len) — we
    forward errors as exceptions and discard the rest.
    """

    def __init__(self, wasm_bytes: bytes, sources_tar: bytes) -> None:
        self._engine = wasmtime.Engine()
        self._store = wasmtime.Store(self._engine)
        module = wasmtime.Module(self._engine, wasm_bytes)

        log_type = wasmtime.FuncType(
            [wasmtime.ValType.i32(), wasmtime.ValType.i32(), wasmtime.ValType.i32()],
            [],
        )
        log_func = wasmtime.Func(self._store, log_type, self._on_log)
        instance = wasmtime.Instance(self._store, module, [log_func])

        self._exports = instance.exports(self._store)
        self._memory: wasmtime.Memory = self._exports["memory"]

        ptr = self._call("alloc", len(sources_tar))
        self._memory.write(self._store, sources_tar, ptr)
        self._call("unpack", ptr, len(sources_tar))

    def _on_log(self, level: int, ptr: int, length: int) -> None:
        if level == 0:
            raise RuntimeError(f"WASM log error: {self._read_string(ptr, length)}")

    def _call(self, name: str, *args: int) -> int:
        result = self._exports[name](self._store, *args)
        return int(result) if result is not None else 0

    def _call_optional(self, name: str, *args: int) -> int | None:
        result = self._call(name, *args)
        return None if result in (-1, _INVALID_INDEX) else result

    def _read_string(self, ptr: int, length: int) -> str:
        if length == 0:
            return ""
        return self._memory.read(self._store, ptr, ptr + length).decode(
            "utf-8", errors="replace"
        )

    def _read_slice32(self, ptr: int, length: int) -> list[int]:
        if length == 0:
            return []
        raw = self._memory.read(self._store, ptr, ptr + length * 4)
        return list(struct.unpack_from(f"<{length}I", raw))

    def _read_slice64(self, ptr: int, length: int) -> list[int]:
        if length == 0:
            return []
        raw = self._memory.read(self._store, ptr, ptr + length * 8)
        return list(struct.unpack_from(f"<{length}Q", raw))

    def _packed_string(self, packed: int) -> str:
        return self._read_string(*split_packed(packed))

    def _packed_slice32(self, packed: int) -> list[int]:
        return self._read_slice32(*split_packed(packed))

    def _packed_slice64(self, packed: int) -> list[int]:
        return self._read_slice64(*split_packed(packed))

    def _set_string(self, export: str, s: str) -> None:
        encoded = s.encode("utf-8")
        ptr = self._call(export, len(encoded))
        self._memory.write(self._store, encoded, ptr)

    def list_modules(self) -> list[str]:
        out: list[str] = []
        i = 0
        while True:
            name = self._packed_string(self._call("module_name", i))
            if not name:
                break
            out.append(name)
            i += 1
        return out

    def find_decl(self, fqn: str) -> int | None:
        self._set_string("set_input_string", fqn)
        return self._call_optional("find_decl")

    def find_file_root(self, path: str) -> int | None:
        self._set_string("set_input_string", path)
        return self._call_optional("find_file_root")

    def find_module_root(self, pkg_index: int) -> int:
        return self._call("find_module_root", pkg_index)

    def categorize_decl(self, decl_index: int, resolve_alias_to: int = 0) -> int:
        return self._call("categorize_decl", decl_index, resolve_alias_to)

    def get_aliasee(self) -> int | None:
        return self._call_optional("get_aliasee")

    def decl_parent(self, decl_index: int) -> int | None:
        return self._call_optional("decl_parent", decl_index)

    def fully_qualified_name(self, decl_index: int) -> str:
        return self._packed_string(self._call("decl_fqn", decl_index))

    def decl_name(self, decl_index: int) -> str:
        return self._packed_string(self._call("decl_name", decl_index))

    def decl_category_name(self, decl_index: int) -> str:
        return self._packed_string(self._call("decl_category_name", decl_index))

    def decl_docs_html(self, decl_index: int, short: bool) -> str:
        return self._packed_string(self._call("decl_docs_html", decl_index, int(short)))

    def decl_fn_proto_html(self, decl_index: int, linkify: bool) -> str:
        return self._packed_string(
            self._call("decl_fn_proto_html", decl_index, int(linkify))
        )

    def decl_param_html(self, decl_index: int, param: int) -> str:
        return self._packed_string(self._call("decl_param_html", decl_index, param))

    def decl_doctest_html(self, decl_index: int) -> str:
        return self._packed_string(self._call("decl_doctest_html", decl_index))

    def decl_source_html(self, decl_index: int) -> str:
        return self._packed_string(self._call("decl_source_html", decl_index))

    def decl_field_html(self, base_decl: int, field: int) -> str:
        return self._packed_string(self._call("decl_field_html", base_decl, field))

    def decl_type_html(self, decl_index: int) -> str:
        return self._packed_string(self._call("decl_type_html", decl_index))

    def decl_file_path(self, decl_index: int) -> str:
        return self._packed_string(self._call("decl_file_path", decl_index))

    def decl_params(self, decl_index: int) -> list[int]:
        return self._packed_slice32(self._call("decl_params", decl_index))

    def decl_fields(self, decl_index: int) -> list[int]:
        return self._packed_slice32(self._call("decl_fields", decl_index))

    def decl_error_set(self, decl_index: int) -> list[int]:
        return self._packed_slice64(self._call("decl_error_set", decl_index))

    def namespace_members(self, decl_index: int, include_private: bool) -> list[int]:
        return self._packed_slice32(
            self._call("namespace_members", decl_index, int(include_private))
        )

    def type_fn_members(self, decl_index: int, include_private: bool) -> list[int]:
        return self._packed_slice32(
            self._call("type_fn_members", decl_index, int(include_private))
        )

    def type_fn_fields(self, decl_index: int) -> list[int]:
        return self._packed_slice32(self._call("type_fn_fields", decl_index))

    def fn_error_set(self, decl_index: int) -> int | None:
        result = self._call("fn_error_set", decl_index)
        return None if result == 0 else result

    def fn_error_set_decl(self, decl_index: int, err_set_node: int) -> int:
        return self._call("fn_error_set_decl", decl_index, err_set_node)

    def error_set_node_list(self, base_decl: int, err_set_node: int) -> list[int]:
        return self._packed_slice64(
            self._call("error_set_node_list", base_decl, err_set_node)
        )

    def error_html(self, base_decl: int, err: int) -> str:
        return self._packed_string(self._call("error_html", base_decl, err))

    def execute_query(self, query: str, ignore_case: bool) -> list[int]:
        self._set_string("query_begin", query)
        ptr = self._call("query_exec", int(ignore_case))
        length = self._read_slice32(ptr, 1)[0]
        return self._read_slice32(ptr + 4, length)
