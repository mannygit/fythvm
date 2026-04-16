"""Pure Python + ctypes dictionary runtime prototype for fythvm."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Iterator, Sequence

from .schema import (
    CELL_SIZE,
    DEFAULT_MEMORY_CELLS,
    DEFAULT_STACK_CELLS,
    NULL_INDEX,
    CodeField,
    DictionaryMemory as DictionaryMemorySchema,
    WordPrefix,
    align_up,
)

def aligned_name_region_size(length: int) -> int:
    return align_up(length, CELL_SIZE)


class DictionaryMemory(DictionaryMemorySchema):
    def clear(self) -> None:
        for index in range(DEFAULT_MEMORY_CELLS):
            self.cells[index] = 0
        for index in range(DEFAULT_STACK_CELLS):
            self.data_stack[index] = 0
            self.return_stack[index] = 0
        self.registers.here = 0
        self.registers.latest = NULL_INDEX
        self.registers.state = 0
        self.registers.base = 0
        self.registers.sp = DEFAULT_STACK_CELLS
        self.registers.rsp = DEFAULT_STACK_CELLS

    @property
    def capacity_cells(self) -> int:
        return DEFAULT_MEMORY_CELLS

    @property
    def capacity_bytes(self) -> int:
        return self.capacity_cells * CELL_SIZE

    def get_cell_addr(self, index: int) -> int:
        return ctypes.addressof(self.cells) + index * CELL_SIZE

    def get_byte_addr(self, byte_offset: int) -> int:
        return ctypes.addressof(self.cells) + byte_offset

    def read_cell(self, index: int) -> int:
        return int(self.cells[index])

    def store_cell(self, index: int, value: int) -> None:
        self.cells[index] = value

    def read_bytes(self, byte_offset: int, length: int) -> bytes:
        return ctypes.string_at(self.get_byte_addr(byte_offset), length)

    def write_bytes(self, byte_offset: int, data: bytes) -> None:
        ctypes.memmove(self.get_byte_addr(byte_offset), data, len(data))

    @property
    def here(self) -> int:
        return int(self.registers.here)

    @here.setter
    def here(self, value: int) -> None:
        self.registers.here = value

    @property
    def latest(self) -> int:
        return int(self.registers.latest)

    @latest.setter
    def latest(self, value: int) -> None:
        self.registers.latest = value

    def used_bytes(self) -> bytes:
        return self.read_bytes(0, self.here * CELL_SIZE)


@dataclass(frozen=True)
class LookupTrace:
    query: bytes
    visited: list[bytes]
    found: "WordRecord | None"


@dataclass(frozen=True)
class WordRecord:
    memory: DictionaryMemory
    index: int

    @property
    def prefix(self) -> WordPrefix:
        return WordPrefix.from_address(self.memory.get_cell_addr(self.index))

    @property
    def code(self) -> CodeField:
        return self.prefix.code

    @property
    def link(self) -> int:
        return int(self.prefix.link)

    @property
    def name_length(self) -> int:
        return int(self.code.name_length)

    @property
    def aligned_name_bytes(self) -> int:
        return aligned_name_region_size(self.name_length)

    @property
    def name_start_byte_offset(self) -> int:
        return self.index * CELL_SIZE - self.aligned_name_bytes

    @property
    def name_bytes(self) -> bytes:
        return self.memory.read_bytes(self.name_start_byte_offset, self.name_length)

    @property
    def hidden(self) -> bool:
        return bool(self.code.hidden)

    @property
    def immediate(self) -> bool:
        return bool(self.code.immediate)

    @property
    def compiling(self) -> bool:
        return bool(self.code.compiling)

    @property
    def instruction(self) -> int:
        return int(self.code.instruction)

    @property
    def cfa_index(self) -> int:
        return self.index + 1

    @property
    def dfa_index(self) -> int:
        return self.index + 2

    def read_data_cells(self, count: int) -> list[int]:
        return [self.memory.read_cell(self.dfa_index + offset) for offset in range(count)]


class DictionaryRuntime:
    """Append-only pure Python + ctypes dictionary runtime for debug visibility."""

    def __init__(self, memory: DictionaryMemory | None = None):
        self.memory = memory if memory is not None else DictionaryMemory()
        self.memory.clear()

    def create_word(
        self,
        name: str | bytes,
        *,
        instruction: int = 0,
        hidden: bool = False,
        immediate: bool = False,
        compiling: bool = False,
        data: Sequence[int] = (),
    ) -> WordRecord:
        name_bytes = name.encode("ascii") if isinstance(name, str) else name
        padded_name_size = aligned_name_region_size(len(name_bytes))
        blob_offset = self.memory.here * CELL_SIZE
        required_cells = padded_name_size // CELL_SIZE + 2 + len(data)
        end_cell = self.memory.here + required_cells
        if end_cell > self.memory.capacity_cells:
            raise MemoryError("dictionary memory exhausted")
        self.memory.write_bytes(blob_offset, name_bytes.ljust(padded_name_size, b"\x00"))

        word_index = self.memory.here + padded_name_size // CELL_SIZE
        prefix = WordPrefix.from_address(self.memory.get_cell_addr(word_index))
        prefix.link = self.memory.latest
        prefix.code.instruction = instruction
        prefix.code.hidden = int(hidden)
        prefix.code.name_length = len(name_bytes)
        prefix.code.immediate = int(immediate)
        prefix.code.compiling = int(compiling)
        prefix.code.unused = 0

        for offset, cell in enumerate(data):
            self.memory.store_cell(word_index + 2 + offset, int(cell))

        self.memory.latest = word_index
        self.memory.here = word_index + 2 + len(data)
        return WordRecord(self.memory, word_index)

    def iter_words(self) -> Iterator[WordRecord]:
        current = self.memory.latest
        while current != NULL_INDEX:
            word = WordRecord(self.memory, current)
            next_link = word.link
            yield word
            current = next_link

    def trace_lookup(self, name: str | bytes) -> LookupTrace:
        query = name.encode("ascii") if isinstance(name, str) else name
        visited: list[bytes] = []
        for word in self.iter_words():
            visited.append(word.name_bytes)
            if word.hidden:
                continue
            if word.name_bytes == query:
                return LookupTrace(query=query, visited=visited, found=word)
        return LookupTrace(query=query, visited=visited, found=None)

    def find_word(self, name: str | bytes) -> WordRecord | None:
        return self.trace_lookup(name).found

    def visible_words(self) -> list[WordRecord]:
        return [word for word in self.iter_words() if not word.hidden]

    def memory_cells(self, *, stop: int | None = None) -> list[tuple[int, int]]:
        end = self.memory.here if stop is None else stop
        return [(index, self.memory.read_cell(index)) for index in range(end)]

    def render_word(self, word: WordRecord) -> str:
        return (
            f"{word.name_bytes.decode('ascii')!r} @ cell {word.index} "
            f"link={word.link} cfa={word.cfa_index} dfa={word.dfa_index} "
            f"hidden={word.hidden} immediate={word.immediate} compiling={word.compiling} "
            f"instr={word.instruction}"
        )

    def debug_lines(self) -> list[str]:
        lines = [
            f"here={self.memory.here} latest={self.memory.latest}",
            "words:",
        ]
        for word in self.iter_words():
            lines.append(f"  {self.render_word(word)}")
        lines.append("cells:")
        for index, value in self.memory_cells():
            lines.append(f"  {index:03d}: 0x{value & 0xFFFFFFFF:08x}")
        return lines
