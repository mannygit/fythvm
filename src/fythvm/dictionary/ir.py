"""IR-side dictionary helpers built on the settled dictionary contract."""

from __future__ import annotations

from collections.abc import Sequence

from llvmlite import ir

from ..codegen import ParamLoop, compare_aligned_i32_regions
from ..codegen.types import I32
from .layout import code_field_handle, dictionary_memory_handle, registers_handle, word_prefix_handle
from .schema import CELL_SIZE, NULL_INDEX


I1 = ir.IntType(1)
I8 = ir.IntType(8)
I8_PTR = I8.as_pointer()
I32_PTR = I32.as_pointer()


def aligned_name_region_size_ir(builder: ir.IRBuilder, length: ir.Value, *, name: str = "aligned_name_bytes") -> ir.Value:
    """Round a byte length up to the 4-byte-aligned stored name region size."""

    if not isinstance(length.type, ir.IntType):
        raise TypeError(f"length must be an integer IR value, got {length.type!r}")
    return builder.and_(builder.add(length, length.type(CELL_SIZE - 1)), length.type(-CELL_SIZE), name=name)


def _i1_flag(value: bool | ir.Value) -> ir.Value:
    if isinstance(value, bool):
        return I1(1 if value else 0)
    if value.type != I1:
        raise TypeError(f"flag must be i1, got {value.type!r}")
    return value


def _i32_value(value: int | ir.Value) -> ir.Value:
    if isinstance(value, int):
        return I32(value)
    if value.type != I32:
        raise TypeError(f"value must be i32, got {value.type!r}")
    return value


class DictionaryIR:
    """IR helpers for the `[name bytes + pad][link][CodeField][data...]` dictionary."""

    def __init__(self, builder: ir.IRBuilder, memory_ptr: ir.Value):
        self.builder = builder
        self.memory = dictionary_memory_handle().bind(builder, memory_ptr)
        self.word_prefix_handle = word_prefix_handle()
        self.code_field_handle = code_field_handle()
        self.registers_handle = registers_handle()

    @property
    def cells_array_ptr(self) -> ir.Value:
        return self.memory.cells.ptr(name="cells_ptr")

    @property
    def cells_byte_ptr(self) -> ir.Value:
        return self.builder.bitcast(self.cells_array_ptr, I8_PTR, name="cells_bytes")

    def latest_index(self) -> ir.Value:
        return self.memory.registers.bind(self.registers_handle).latest.load(name="latest")

    def store_latest_index(self, value: ir.Value) -> None:
        self.memory.registers.bind(self.registers_handle).latest.store(value)

    def here_index(self) -> ir.Value:
        return self.memory.registers.bind(self.registers_handle).here.load(name="here")

    def store_here_index(self, value: ir.Value) -> None:
        self.memory.registers.bind(self.registers_handle).here.store(value)

    def cell_ptr(self, cell_index: ir.Value, *, name: str) -> ir.Value:
        return self.builder.gep(self.cells_array_ptr, [I32(0), cell_index], inbounds=True, name=name)

    def cell_load(self, cell_index: ir.Value, *, name: str) -> ir.Value:
        return self.builder.load(self.cell_ptr(cell_index, name=f"{name}_ptr"), name=name)

    def cell_store(self, cell_index: ir.Value, value: ir.Value, *, name: str) -> None:
        self.builder.store(value, self.cell_ptr(cell_index, name=f"{name}_ptr"))

    def byte_ptr(self, byte_offset: ir.Value, *, name: str) -> ir.Value:
        return self.builder.gep(self.cells_byte_ptr, [byte_offset], inbounds=True, name=name)

    def word_prefix_ptr(self, word_index: ir.Value, *, name: str) -> ir.Value:
        return self.builder.bitcast(
            self.cell_ptr(word_index, name=f"{name}_cell_ptr"),
            self.word_prefix_handle.ir_type.as_pointer(),
            name=name,
        )

    def word(self, word_index: ir.Value):
        return self.word_prefix_handle.bind(self.builder, self.word_prefix_ptr(word_index, name="word_ptr"))

    def word_index_for_cfa(self, cfa_index: ir.Value, *, name: str = "word_index") -> ir.Value:
        """Resolve a word's prefix cell index from its CFA cell index."""

        return self.builder.sub(cfa_index, I32(1), name=name)

    def dfa_index_for_cfa(self, cfa_index: ir.Value, *, name: str = "dfa_index") -> ir.Value:
        """Resolve a word's data-field start cell index from its CFA cell index."""

        return self.builder.add(cfa_index, I32(1), name=name)

    def thread_cells_ptr_for_cfa(self, cfa_index: ir.Value, *, name: str = "thread_cells_ptr") -> ir.Value:
        """Resolve a colon word's thread cells pointer from its CFA cell index."""

        return self.cell_ptr(self.dfa_index_for_cfa(cfa_index, name=f"{name}_dfa_index"), name=name)

    def name_length(self, word_index: ir.Value) -> ir.Value:
        word = self.word(word_index)
        code_field = word.code_field.bind(self.code_field_handle)
        return self.builder.zext(code_field.name_length.load(name="name_length_i5"), I32, name="name_length")

    def aligned_name_bytes(self, name_length: ir.Value, *, name: str = "aligned_name_bytes") -> ir.Value:
        return aligned_name_region_size_ir(self.builder, name_length, name=name)

    def name_start_byte_offset(self, word_index: ir.Value, name_length: ir.Value, *, name: str = "name_start_byte_offset") -> ir.Value:
        word_byte_offset = self.builder.mul(word_index, I32(CELL_SIZE), name=f"{name}_word_byte_offset")
        aligned_name_bytes = self.aligned_name_bytes(name_length, name=f"{name}_aligned_name_bytes")
        return self.builder.sub(word_byte_offset, aligned_name_bytes, name=name)

    def name_ptr(self, word_index: ir.Value, name_length: ir.Value, *, name: str = "name_ptr") -> ir.Value:
        return self.byte_ptr(self.name_start_byte_offset(word_index, name_length, name=f"{name}_offset"), name=name)

    def word_matches_aligned_name(self, word_index: ir.Value, query_name_ptr: ir.Value, query_name_length: ir.Value) -> ir.Value:
        stored_length = self.name_length(word_index)
        same_length = self.builder.icmp_unsigned("==", stored_length, query_name_length, name="same_length")
        compare_block = self.builder.append_basic_block("compare_name")
        mismatch_block = self.builder.append_basic_block("mismatch_length")
        exit_block = self.builder.append_basic_block("name_match_exit")

        with self.builder.goto_block(exit_block):
            matched = self.builder.phi(I1, name="name_match")

        self.builder.cbranch(same_length, compare_block, mismatch_block)

        with self.builder.goto_block(mismatch_block):
            matched.add_incoming(I1(0), self.builder.basic_block)
            self.builder.branch(exit_block)

        with self.builder.goto_block(compare_block):
            stored_name_ptr = self.name_ptr(word_index, stored_length, name="stored_name_ptr")
            compare_length = self.aligned_name_bytes(query_name_length, name="query_aligned_name_bytes")
            same_bytes = compare_aligned_i32_regions(
                self.builder,
                stored_name_ptr,
                query_name_ptr,
                compare_length,
                name="name_region_equal",
            )
            matched.add_incoming(same_bytes, self.builder.basic_block)
            self.builder.branch(exit_block)

        self.builder.position_at_end(exit_block)
        return matched

    def find_word(self, query_name_ptr: ir.Value, query_name_length: ir.Value, *, visible_only: bool = True) -> ir.Value:
        latest = self.latest_index()
        loop = ParamLoop(self.builder, "find_word", [("current", I32)])
        found_block = self.builder.append_basic_block("find_word.found")
        compare_block = self.builder.append_basic_block("find_word.compare")
        continue_block = self.builder.append_basic_block("find_word.continue")
        loop.begin(latest)
        current_word: ir.Value | None = None

        with loop.head() as (current,):
            current_word = current
            active = self.builder.icmp_signed("!=", current, I32(NULL_INDEX), name="find_word_active")
            self.builder.cbranch(active, loop.body_block, loop.exit_block)

        with loop.body():
            word = self.word(current)
            code_field = word.code_field.bind(self.code_field_handle)
            if visible_only:
                hidden = code_field.hidden.load(name="find_word_hidden")
                visible = self.builder.icmp_unsigned("==", hidden, I1(0), name="find_word_visible")
                self.builder.cbranch(visible, compare_block, continue_block)
            else:
                self.builder.branch(compare_block)

        with self.builder.goto_block(compare_block):
            matched = self.word_matches_aligned_name(current, query_name_ptr, query_name_length)
            self.builder.cbranch(matched, found_block, continue_block)

        with self.builder.goto_block(found_block):
            self.builder.branch(loop.exit_block)

        with self.builder.goto_block(continue_block):
            word = self.word(current)
            next_link = word.link.load(name="find_word_next_link")
            loop.continue_from_here(next_link)

        with loop.exit():
            assert current_word is not None
            result = self.builder.phi(I32, name="found_word_index")
            result.add_incoming(I32(NULL_INDEX), loop.head_block)
            result.add_incoming(current_word, found_block)
            return result

    def _copy_bytes(self, dest_ptr: ir.Value, src_ptr: ir.Value, length: ir.Value, *, loop_name: str) -> None:
        loop = ParamLoop(self.builder, loop_name, [("i", I32)])
        loop.begin(I32(0))

        with loop.head() as (i,):
            active = self.builder.icmp_unsigned("<", i, length, name=f"{loop_name}_active")
            self.builder.cbranch(active, loop.body_block, loop.exit_block)

        with loop.body():
            src_byte = self.builder.load(self.builder.gep(src_ptr, [i], inbounds=True, name=f"{loop_name}_src_ptr"), name=f"{loop_name}_src")
            self.builder.store(src_byte, self.builder.gep(dest_ptr, [i], inbounds=True, name=f"{loop_name}_dest_ptr"))
            loop.continue_from_here(self.builder.add(i, I32(1), name=f"{loop_name}_next_i"))

        with loop.exit():
            return

    def _zero_fill_bytes(self, dest_ptr: ir.Value, start: ir.Value, stop: ir.Value, *, loop_name: str) -> None:
        loop = ParamLoop(self.builder, loop_name, [("i", I32)])
        loop.begin(start)

        with loop.head() as (i,):
            active = self.builder.icmp_unsigned("<", i, stop, name=f"{loop_name}_active")
            self.builder.cbranch(active, loop.body_block, loop.exit_block)

        with loop.body():
            self.builder.store(I8(0), self.builder.gep(dest_ptr, [i], inbounds=True, name=f"{loop_name}_dest_ptr"))
            loop.continue_from_here(self.builder.add(i, I32(1), name=f"{loop_name}_next_i"))

        with loop.exit():
            return

    def create_word(
        self,
        name_ptr: ir.Value,
        name_length: ir.Value,
        *,
        handler_id: int | ir.Value = 0,
        hidden: bool | ir.Value = False,
        immediate: bool | ir.Value = False,
        data_values: Sequence[int | ir.Value] = (),
    ) -> ir.Value:
        here = self.here_index()
        latest = self.latest_index()
        aligned_name_bytes = self.aligned_name_bytes(name_length)
        name_region_cells = self.builder.udiv(aligned_name_bytes, I32(CELL_SIZE), name="name_region_cells")
        word_index = self.builder.add(here, name_region_cells, name="word_index")
        name_byte_offset = self.builder.mul(here, I32(CELL_SIZE), name="name_byte_offset")
        stored_name_ptr = self.byte_ptr(name_byte_offset, name="stored_name_ptr")

        self._copy_bytes(stored_name_ptr, name_ptr, name_length, loop_name="copy_name_bytes")
        self._zero_fill_bytes(stored_name_ptr, name_length, aligned_name_bytes, loop_name="zero_pad_name_bytes")

        word = self.word(word_index)
        word.link.store(latest)
        code_field = word.code_field.bind(self.code_field_handle)
        handler_value = _i32_value(handler_id)
        if handler_value.type.width > 7:
            handler_value = self.builder.trunc(handler_value, ir.IntType(7), name="handler_id_i7")
        elif handler_value.type.width < 7:
            handler_value = self.builder.zext(handler_value, ir.IntType(7), name="handler_id_i7")
        code_field.handler_id.store(handler_value)
        code_field.hidden.store(_i1_flag(hidden))
        name_length_i5 = name_length
        if name_length_i5.type.width > 5:
            name_length_i5 = self.builder.trunc(name_length_i5, ir.IntType(5), name="name_length_i5")
        elif name_length_i5.type.width < 5:
            name_length_i5 = self.builder.zext(name_length_i5, ir.IntType(5), name="name_length_i5")
        code_field.name_length.store(name_length_i5)
        code_field.immediate.store(_i1_flag(immediate))
        code_field.unused.store(ir.IntType(18)(0))

        for offset, value in enumerate(data_values):
            cell_value = _i32_value(value)
            self.cell_store(self.builder.add(word_index, I32(2 + offset), name=f"data_index_{offset}"), cell_value, name=f"data_{offset}")

        new_here = self.builder.add(word_index, I32(2 + len(data_values)), name="new_here")
        self.store_latest_index(word_index)
        self.store_here_index(new_here)
        return word_index


__all__ = [
    "DictionaryIR",
    "aligned_name_region_size_ir",
]
