"""Inspect how a sample dictionary word is physically encoded in memory.

Usage:
    uv run python scripts/inspect_dictionary_word_layout.py
"""

from __future__ import annotations

import ctypes

from fythvm.dictionary import CodeField, DictionaryRuntime, WordPrefix


def _hex_bytes(data: bytes) -> str:
    return " ".join(f"{byte:02x}" for byte in data)


def _bit_string(value: int, width: int) -> str:
    return f"{value:0{width}b}"


def main() -> None:
    runtime = DictionaryRuntime()
    word = runtime.create_word(
        "dup",
        instruction=42,
        hidden=True,
        immediate=True,
        compiling=True,
        data=[0x11111111, 0x22222222],
    )

    name_blob_offset = word.name_start_byte_offset
    name_blob_bytes = runtime.memory.read_bytes(name_blob_offset, word.aligned_name_bytes)

    prefix_addr = runtime.memory.get_cell_addr(word.index)
    prefix_bytes = ctypes.string_at(prefix_addr, ctypes.sizeof(WordPrefix))
    code_addr = ctypes.addressof(word.prefix.code)
    code_bytes = ctypes.string_at(code_addr, ctypes.sizeof(CodeField))
    code_value = ctypes.c_uint32.from_address(code_addr).value

    word_total_bytes = (word.dfa_index + 2 - (word.name_start_byte_offset // 4)) * 4
    full_word_bytes = runtime.memory.read_bytes(name_blob_offset, word_total_bytes)

    print("== Sample Word ==")
    print(f"name={word.name_bytes!r}")
    print(f"word_index={word.index} cfa_index={word.cfa_index} dfa_index={word.dfa_index}")
    print(f"link={word.link}")
    print()

    print("== Name Bytes Region ==")
    print(f"offset={name_blob_offset} bytes={_hex_bytes(name_blob_bytes)}")
    print(f"decoded name bytes={word.name_bytes!r}")
    print("layout: raw name bytes followed by zero padding up to cell alignment")
    print()

    print("== Fixed Prefix ==")
    print(f"prefix_offset={word.index * 4} prefix_bytes={_hex_bytes(prefix_bytes)}")
    print(f"link_cell=0x{ctypes.c_uint32(word.link & 0xFFFFFFFF).value:08x}")
    print()

    print("== CodeField Cell ==")
    print(f"code_bytes={_hex_bytes(code_bytes)}")
    print(f"raw=0x{code_value:08x} bits={_bit_string(code_value, 32)}")
    print(
        "decoded: "
        f"instruction={word.code.instruction} hidden={bool(word.code.hidden)} "
        f"name_length={word.code.name_length} immediate={bool(word.code.immediate)} "
        f"compiling={bool(word.code.compiling)} unused={word.code.unused}"
    )
    print(
        "bit layout: "
        "[instruction:7][hidden:1][name_length:5][immediate:1][compiling:1][unused:17]"
    )
    print()

    print("== Full Word Bytes ==")
    print(_hex_bytes(full_word_bytes))


if __name__ == "__main__":
    main()
