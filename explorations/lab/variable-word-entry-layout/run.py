"""Demonstrate the variable-size word-entry protocol behind the dictionary."""

from __future__ import annotations

from dataclasses import dataclass

from fythvm.dictionary import CELL_SIZE, DictionaryRuntime, WordRecord, aligned_name_region_size


@dataclass(frozen=True)
class RawWordShape:
    index: int
    link: int
    name_start_byte_offset: int
    aligned_name_bytes: int
    cfa_index: int
    dfa_index: int
    handler_id: int
    hidden: bool
    immediate: bool
    compiling: bool
    name_bytes: bytes


def raw_describe_word(word: WordRecord) -> RawWordShape:
    memory = word.memory
    length = word.name_length
    aligned_name_bytes = aligned_name_region_size(length)
    name_bytes = memory.read_bytes(word.name_start_byte_offset, length)
    return RawWordShape(
        index=word.index,
        link=word.link,
        name_start_byte_offset=word.name_start_byte_offset,
        aligned_name_bytes=aligned_name_bytes,
        cfa_index=word.index + 1,
        dfa_index=word.index + 2,
        handler_id=word.handler_id,
        hidden=word.hidden,
        immediate=word.immediate,
        compiling=word.compiling,
        name_bytes=name_bytes,
    )


def render_raw(shape: RawWordShape) -> str:
    return (
        f"{shape.name_bytes.decode('ascii')!r}: word={shape.index} "
        f"name_start_byte={shape.name_start_byte_offset} aligned_name_bytes={shape.aligned_name_bytes} "
        f"link={shape.link} cfa={shape.cfa_index} dfa={shape.dfa_index} "
        f"hidden={shape.hidden} immediate={shape.immediate} compiling={shape.compiling} "
        f"handler_id={shape.handler_id}"
    )


def render_cells(runtime: DictionaryRuntime) -> list[str]:
    return [
        f"cell {index:02d}: 0x{value & 0xFFFFFFFF:08x}"
        for index, value in runtime.memory_cells()
    ]


def main() -> None:
    runtime = DictionaryRuntime()
    runtime.create_word("dup", handler_id=10, data=(111,))
    runtime.create_word("swap", handler_id=20, hidden=True, data=(222,))
    runtime.create_word("emit", handler_id=30, immediate=True, compiling=True, data=(333, 444))

    words = list(runtime.iter_words())
    raw_shapes = [raw_describe_word(word) for word in words]

    print("== Question ==")
    print("How does the real dictionary word shape combine variable-size name bytes with a fixed word prefix and derived CFA/DFA cells?")
    print()

    print("== Layout Rules ==")
    print(f"cell size = {CELL_SIZE} bytes")
    print("name blob = raw name bytes + zero padding to cell alignment")
    print("fixed word prefix begins after the aligned name blob")
    print("latest stores the fixed-prefix cell index, not a payload byte offset")
    print()

    print("== Raw Offset Reconstruction ==")
    for shape in raw_shapes:
        print(render_raw(shape))
    print()

    print("== Pythonic View ==")
    for word in words:
        print(runtime.render_word(word))
    print()

    print("== Lookup Traces ==")
    for query in ["emit", "swap", "dup", "missing"]:
        trace = runtime.trace_lookup(query)
        visited = " -> ".join(name.decode("ascii") for name in trace.visited) or "(empty)"
        if trace.found is None:
            print(f"{query!r}: walked {visited} | not found")
        else:
            print(f"{query!r}: walked {visited} | found {trace.found.name_bytes.decode('ascii')!r} at word {trace.found.index}")
    print()

    print("== Failure-Mode Probe ==")
    emit_word = words[0]
    wrong_name_start = emit_word.index * CELL_SIZE
    correct_name_start = emit_word.name_start_byte_offset
    print(f"wrong assumption: name starts at byte {wrong_name_start}")
    print(f"correct value   : name starts at byte {correct_name_start}")
    print("The name bytes live before the fixed word prefix, so byte/cell arithmetic has to stay explicit.")
    print()

    print("== Memory Snapshot ==")
    for line in render_cells(runtime):
        print(line)
    print()

    print("== Takeaway ==")
    print("The word entry is not a fixed struct by itself. It is a variable-size name blob followed by a fixed prefix whose CFA/DFA offsets are derived from that blob size.")


if __name__ == "__main__":
    main()
