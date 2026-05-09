import struct

from zigpeek.wasm import unpack_slice32, unpack_slice64, unpack_string


def test_unpack_string_zero_length_returns_empty():
    memory = b"unused"
    assert unpack_string(memory, 0, 0) == ""


def test_unpack_string_decodes_utf8():
    memory = b"\x00\x00hello world"
    assert unpack_string(memory, 2, 5) == "hello"


def test_pack_unpack_roundtrip_via_packed_int():
    ptr = 4
    length = 5
    packed = (length << 32) | ptr
    memory = b"....hello!"
    got_ptr = packed & 0xFFFFFFFF
    got_len = packed >> 32
    assert unpack_string(memory, got_ptr, got_len) == "hello"


def test_unpack_slice32_zero_length_returns_empty():
    assert unpack_slice32(b"\x00" * 16, 0, 0) == []


def test_unpack_slice32_reads_little_endian_u32s():
    payload = struct.pack("<III", 1, 2, 3)
    memory = b"PAD" + payload
    assert unpack_slice32(memory, 3, 3) == [1, 2, 3]


def test_unpack_slice64_reads_little_endian_u64s():
    payload = struct.pack("<QQ", 0xDEADBEEF, 0x1234567890ABCDEF)
    memory = payload
    assert unpack_slice64(memory, 0, 2) == [0xDEADBEEF, 0x1234567890ABCDEF]
