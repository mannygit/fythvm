"""Demonstrate a linked dictionary layout in linear memory."""

from __future__ import annotations

from dataclasses import dataclass


CELL_SIZE = 4
NULL_PTR = 0
MAX_MEMORY_BYTES = 256
IMMEDIATE_MASK = 0x80
HIDDEN_MASK = 0x40
LENGTH_MASK = 0x1F


def align_up(offset: int, alignment: int = CELL_SIZE) -> int:
    return (offset + alignment - 1) // alignment * alignment


def pack_header(name_length: int, *, hidden: bool = False, immediate: bool = False) -> int:
    header = name_length & LENGTH_MASK
    if hidden:
        header |= HIDDEN_MASK
    if immediate:
        header |= IMMEDIATE_MASK
    return header


def unpack_header(header: int) -> tuple[int, bool, bool]:
    return (
        header & LENGTH_MASK,
        bool(header & HIDDEN_MASK),
        bool(header & IMMEDIATE_MASK),
    )


@dataclass(slots=True)
class EntryView:
    name: str
    value: int
    payload_offset: int
    previous_payload_offset: int
    header_byte: int
    hidden: bool
    immediate: bool

    @property
    def entry_start(self) -> int:
        return self.payload_offset - CELL_SIZE

    @property
    def value_offset(self) -> int:
        name_blob_size = align_up(1 + len(self.name))
        return self.payload_offset + name_blob_size


@dataclass(slots=True)
class LookupTrace:
    query: str
    visited: list[str]
    found: EntryView | None


class LinearMemory:
    def __init__(self, size: int = MAX_MEMORY_BYTES) -> None:
        self._bytes = bytearray(size)
        self.here = 0

    def align_here(self) -> int:
        self.here = align_up(self.here)
        return self.here

    def read_u32(self, offset: int) -> int:
        return int.from_bytes(self._bytes[offset : offset + CELL_SIZE], "little", signed=False)

    def write_u32(self, offset: int, value: int) -> None:
        self._bytes[offset : offset + CELL_SIZE] = value.to_bytes(CELL_SIZE, "little", signed=False)

    def read_u8(self, offset: int) -> int:
        return self._bytes[offset]

    def write_bytes(self, offset: int, data: bytes) -> None:
        end = offset + len(data)
        self._bytes[offset:end] = data

    def read_bytes(self, offset: int, length: int) -> bytes:
        return bytes(self._bytes[offset : offset + length])

    def dump_cells(self, start: int = 0, stop: int | None = None) -> list[tuple[int, int]]:
        if stop is None:
            stop = self.here
        stop = align_up(stop)
        return [(offset, self.read_u32(offset)) for offset in range(start, stop, CELL_SIZE)]


class LinkedDictionary:
    def __init__(self, memory: LinearMemory) -> None:
        self.memory = memory
        self.latest = NULL_PTR

    def insert(
        self,
        name: str,
        value: int,
        *,
        hidden: bool = False,
        immediate: bool = False,
    ) -> EntryView:
        name_bytes = name.encode("ascii")
        header_byte = pack_header(len(name_bytes), hidden=hidden, immediate=immediate)
        blob = bytes([header_byte]) + name_bytes
        blob_size = align_up(len(blob))
        entry_start = self.memory.align_here()
        payload_offset = entry_start + CELL_SIZE
        value_offset = payload_offset + blob_size
        entry_end = align_up(value_offset + CELL_SIZE)

        if entry_end > len(self.memory._bytes):
            raise MemoryError("dictionary memory exhausted")

        self.memory.write_u32(entry_start, self.latest)
        self.memory.write_bytes(payload_offset, blob.ljust(blob_size, b"\x00"))
        self.memory.write_u32(value_offset, value)
        self.memory.here = entry_end
        self.latest = payload_offset

        return EntryView(
            name=name,
            value=value,
            payload_offset=payload_offset,
            previous_payload_offset=self.memory.read_u32(entry_start),
            header_byte=header_byte,
            hidden=hidden,
            immediate=immediate,
        )

    def _decode_entry(self, payload_offset: int) -> EntryView:
        entry_start = payload_offset - CELL_SIZE
        previous_payload_offset = self.memory.read_u32(entry_start)
        header_byte = self.memory.read_u8(payload_offset)
        name_length, hidden, immediate = unpack_header(header_byte)
        name_start = payload_offset + 1
        name = self.memory.read_bytes(name_start, name_length).decode("ascii")
        value_offset = payload_offset + align_up(1 + name_length)
        value = self.memory.read_u32(value_offset)
        return EntryView(
            name=name,
            value=value,
            payload_offset=payload_offset,
            previous_payload_offset=previous_payload_offset,
            header_byte=header_byte,
            hidden=hidden,
            immediate=immediate,
        )

    def traverse(self) -> list[EntryView]:
        items: list[EntryView] = []
        cursor = self.latest
        while cursor != NULL_PTR:
            entry = self._decode_entry(cursor)
            items.append(entry)
            cursor = entry.previous_payload_offset
        return items

    def lookup(self, name: str) -> LookupTrace:
        visited: list[str] = []
        for entry in self.traverse():
            visited.append(entry.name)
            if entry.name == name:
                return LookupTrace(query=name, visited=visited, found=entry)
        return LookupTrace(query=name, visited=visited, found=None)

    def probe_wrong_previous_link(self, entry: EntryView) -> tuple[int, int]:
        wrong = self.memory.read_u32(entry.payload_offset)
        correct = self.memory.read_u32(entry.payload_offset - CELL_SIZE)
        return wrong, correct


def format_offset(offset: int) -> str:
    return f"{offset:03d}"


def render_entry(entry: EntryView) -> str:
    return (
        f"{entry.name:<5} | payload @ {format_offset(entry.payload_offset)} | "
        f"prev -> {format_offset(entry.previous_payload_offset)} | "
        f"value @ {format_offset(entry.value_offset)} = {entry.value}"
    )


def render_cells(memory: LinearMemory, *, stop: int) -> list[str]:
    lines = []
    for offset, cell in memory.dump_cells(0, stop):
        lines.append(f"cell {offset // CELL_SIZE:02d} @ {format_offset(offset)} = 0x{cell:08x}")
    return lines


def main() -> None:
    memory = LinearMemory()
    dictionary = LinkedDictionary(memory)

    inserted = [
        dictionary.insert("alpha", 11),
        dictionary.insert("beta", 22),
        dictionary.insert("gamma", 33),
    ]

    print("== Question ==")
    print("How does a linked dictionary store newest-first entries in linear memory?")
    print()

    print("== Layout Rules ==")
    print(f"CELL_SIZE = {CELL_SIZE} bytes")
    print("0 means null")
    print("Each entry stores its previous payload offset in the cell before the payload")
    print("The payload begins with a packed 1-byte header followed by the name bytes")
    print()

    print("== Insertions ==")
    for entry in inserted:
        print(render_entry(entry))
    print(f"latest payload pointer = {format_offset(dictionary.latest)}")
    print()

    print("== Newest-First Traversal ==")
    for entry in dictionary.traverse():
        print(f"visit -> {entry.name:<5} (value {entry.value}, previous {format_offset(entry.previous_payload_offset)})")
    print()

    print("== Lookup Traces ==")
    for query in ["beta", "alpha", "missing"]:
        trace = dictionary.lookup(query)
        visited = " -> ".join(trace.visited) if trace.visited else "(empty)"
        if trace.found is None:
            print(f"lookup {query!r}: walked {visited} | not found")
        else:
            print(
                f"lookup {query!r}: walked {visited} | found payload {format_offset(trace.found.payload_offset)} "
                f"| value {trace.found.value}"
            )
    print()

    print("== Failure-Mode Probe ==")
    beta = dictionary.lookup("beta").found
    assert beta is not None
    wrong_prev, correct_prev = dictionary.probe_wrong_previous_link(beta)
    wrong_cell_index = beta.payload_offset
    wrong_byte_jump = wrong_cell_index * CELL_SIZE
    print(f"beta payload offset = {beta.payload_offset} bytes = cell {beta.payload_offset // CELL_SIZE}")
    print(f"wrong read at payload offset -> 0x{wrong_prev:08x} (header/name bytes, not the link)")
    print(f"correct read at payload offset - CELL_SIZE -> 0x{correct_prev:08x} (alpha payload offset)")
    print(f"if you treat the byte offset as a cell index, you jump to byte {wrong_byte_jump}, which is nonsense here")
    print()

    print("== Memory Snapshot ==")
    for line in render_cells(memory, stop=memory.here):
        print(line)
    print()

    print("== Takeaway ==")
    print("The dictionary head is just the newest payload offset, and each entry points back from the cell before its payload.")
    print("That makes insertion cheap and traversal deterministic, but it is still only the first-pass memory shape.")


if __name__ == "__main__":
    main()
