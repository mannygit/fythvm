"""Capture previous-link list IR abstractions from the old ~/fyth helper shape."""

from __future__ import annotations

from ctypes import CFUNCTYPE, POINTER, c_int32, c_uint8
from dataclasses import dataclass

from llvmlite import ir

from fythvm.codegen import I32, ParamLoop, compile_ir_module, configure_llvm


I8 = ir.IntType(8)
I8_PTR = I8.as_pointer()
I32_PTR = I32.as_pointer()

CELL_BYTES = 4
NODE_BYTES = 8
NULL_OFFSET = 0
FIRST_NODE_OFFSET = CELL_BYTES
MEMORY_BYTES = 64


@dataclass(slots=True)
class DecodedNode:
    data_offset: int
    previous_offset: int
    value: int


class ByteArena:
    def __init__(self, size: int = MEMORY_BYTES) -> None:
        self.memory = (c_uint8 * size)()
        self.here = c_int32(FIRST_NODE_OFFSET)
        self.latest = c_int32(NULL_OFFSET)

    def read_i32(self, offset: int) -> int:
        data = bytes(self.memory[offset : offset + CELL_BYTES])
        return int.from_bytes(data, "little", signed=True)

    def decode_nodes(self) -> list[DecodedNode]:
        nodes: list[DecodedNode] = []
        cursor = self.latest.value
        while cursor != NULL_OFFSET:
            previous_offset = self.read_i32(cursor - CELL_BYTES)
            value = self.read_i32(cursor)
            nodes.append(
                DecodedNode(
                    data_offset=cursor,
                    previous_offset=previous_offset,
                    value=value,
                )
            )
            cursor = previous_offset
        return nodes

    def render_cells(self) -> list[str]:
        lines = []
        for offset in range(0, self.here.value, CELL_BYTES):
            lines.append(f"{offset:03d}: 0x{self.read_i32(offset) & 0xFFFFFFFF:08x}")
        return lines


def raw_cell_ptr(builder: ir.IRBuilder, memory_ptr: ir.Argument, byte_offset: ir.Value, name: str) -> ir.Value:
    byte_ptr = builder.gep(memory_ptr, [byte_offset], name=f"{name}_byte_ptr")
    return builder.bitcast(byte_ptr, I32_PTR, name=f"{name}_ptr")


def raw_load_cell(builder: ir.IRBuilder, memory_ptr: ir.Argument, byte_offset: ir.Value, name: str) -> ir.Value:
    return builder.load(raw_cell_ptr(builder, memory_ptr, byte_offset, name), name=name)


def raw_store_cell(builder: ir.IRBuilder, memory_ptr: ir.Argument, byte_offset: ir.Value, value: ir.Value, name: str) -> None:
    builder.store(value, raw_cell_ptr(builder, memory_ptr, byte_offset, name))


class ByteCellMemory:
    def __init__(self, builder: ir.IRBuilder, memory_ptr: ir.Argument):
        self.builder = builder
        self.memory_ptr = memory_ptr

    def cell_ptr(self, byte_offset: ir.Value, name: str) -> ir.Value:
        byte_ptr = self.builder.gep(self.memory_ptr, [byte_offset], name=f"{name}_byte_ptr")
        return self.builder.bitcast(byte_ptr, I32_PTR, name=f"{name}_ptr")

    def load_cell(self, byte_offset: ir.Value, name: str) -> ir.Value:
        return self.builder.load(self.cell_ptr(byte_offset, name), name=name)

    def store_cell(self, byte_offset: ir.Value, value: ir.Value, name: str) -> None:
        self.builder.store(value, self.cell_ptr(byte_offset, name))


@dataclass(slots=True)
class PreviousLinkNode:
    list_ir: "PreviousLinkListIR"
    data_offset: ir.Value
    label: str

    def previous_slot_offset(self) -> ir.Value:
        return self.list_ir.builder.sub(self.data_offset, I32(CELL_BYTES), name=f"{self.label}_previous_slot")

    def previous_link(self) -> ir.Value:
        return self.list_ir.memory.load_cell(self.previous_slot_offset(), name=f"{self.label}_previous")

    def value(self) -> ir.Value:
        return self.list_ir.memory.load_cell(self.data_offset, name=f"{self.label}_value")


class PreviousLinkListIR:
    """A node is `[previous link][data...]`, and the public offset points at data."""

    def __init__(self, builder: ir.IRBuilder, memory_ptr: ir.Argument, name: str):
        self.builder = builder
        self.memory = ByteCellMemory(builder, memory_ptr)
        self.name = name

    def node(self, data_offset: ir.Value, label: str) -> PreviousLinkNode:
        return PreviousLinkNode(self, data_offset, label)

    def append(self, here_ptr: ir.Argument, latest_ptr: ir.Argument, value: ir.Value) -> ir.Value:
        here = self.builder.load(here_ptr, name=f"{self.name}_here")
        latest = self.builder.load(latest_ptr, name=f"{self.name}_latest")
        previous_slot = self.builder.sub(here, I32(CELL_BYTES), name=f"{self.name}_previous_slot")
        self.memory.store_cell(previous_slot, latest, name=f"{self.name}_previous")
        self.memory.store_cell(here, value, name=f"{self.name}_value")
        new_here = self.builder.add(here, I32(NODE_BYTES), name=f"{self.name}_new_here")
        self.builder.store(new_here, here_ptr)
        self.builder.store(here, latest_ptr)
        return here

    def count(self, latest: ir.Value) -> None:
        loop = ParamLoop(self.builder, f"{self.name}.count", [("offset", I32), ("count", I32)])
        loop.begin(latest, I32(0))
        exit_count: ir.Value | None = None

        with loop.head() as (offset, count):
            exit_count = count
            active = self.builder.icmp_signed("!=", offset, I32(NULL_OFFSET), name=f"{self.name}_active")
            self.builder.cbranch(active, loop.body_block, loop.exit_block)

        with loop.body():
            node = self.node(offset, f"{self.name}_count_node")
            previous = node.previous_link()
            next_count = self.builder.add(count, I32(1), name=f"{self.name}_count_plus_one")
            loop.continue_from_here(previous, next_count)

        with loop.exit():
            assert exit_count is not None
            self.builder.ret(exit_count)

    def get_nth_offset(self, latest: ir.Value, n: ir.Value) -> None:
        loop = ParamLoop(self.builder, f"{self.name}.nth", [("offset", I32), ("count", I32)])
        found_block = self.builder.append_basic_block(f"{self.name}.nth.found")
        continue_block = self.builder.append_basic_block(f"{self.name}.nth.continue")
        loop.begin(latest, I32(0))
        current_offset: ir.Value | None = None

        with loop.head() as (offset, count):
            current_offset = offset
            active = self.builder.icmp_signed("!=", offset, I32(NULL_OFFSET), name=f"{self.name}_nth_active")
            self.builder.cbranch(active, loop.body_block, loop.exit_block)

        with loop.body():
            matched = self.builder.icmp_signed("==", count, n, name=f"{self.name}_nth_match")
            self.builder.cbranch(matched, found_block, continue_block)

        with self.builder.goto_block(found_block):
            self.builder.branch(loop.exit_block)

        with self.builder.goto_block(continue_block):
            node = self.node(offset, f"{self.name}_nth_node")
            previous = node.previous_link()
            next_count = self.builder.add(count, I32(1), name=f"{self.name}_nth_count_plus_one")
            loop.continue_from_here(previous, next_count)

        with loop.exit():
            assert current_offset is not None
            result = self.builder.phi(I32, name=f"{self.name}_nth_offset")
            result.add_incoming(I32(-1), loop.head_block)
            result.add_incoming(current_offset, found_block)
            self.builder.ret(result)


def emit_raw_append(module: ir.Module) -> None:
    fn_type = ir.FunctionType(I32, [I8_PTR, I32_PTR, I32_PTR, I32])
    fn = ir.Function(module, fn_type, name="raw_append")
    memory_ptr, here_ptr, latest_ptr, value = fn.args
    builder = ir.IRBuilder(fn.append_basic_block("entry"))

    here = builder.load(here_ptr, name="here")
    latest = builder.load(latest_ptr, name="latest")
    previous_slot = builder.sub(here, I32(CELL_BYTES), name="previous_slot")
    raw_store_cell(builder, memory_ptr, previous_slot, latest, name="previous")
    raw_store_cell(builder, memory_ptr, here, value, name="value")
    new_here = builder.add(here, I32(NODE_BYTES), name="new_here")
    builder.store(new_here, here_ptr)
    builder.store(here, latest_ptr)
    builder.ret(here)


def emit_raw_count(module: ir.Module) -> None:
    fn_type = ir.FunctionType(I32, [I8_PTR, I32])
    fn = ir.Function(module, fn_type, name="raw_count")
    memory_ptr, latest = fn.args
    entry_block = fn.append_basic_block("entry")
    head_block = fn.append_basic_block("head")
    body_block = fn.append_basic_block("body")
    exit_block = fn.append_basic_block("exit")
    builder = ir.IRBuilder(entry_block)
    builder.branch(head_block)

    builder.position_at_end(head_block)
    offset = builder.phi(I32, name="offset")
    count = builder.phi(I32, name="count")
    offset.add_incoming(latest, entry_block)
    count.add_incoming(I32(0), entry_block)
    active = builder.icmp_signed("!=", offset, I32(NULL_OFFSET), name="active")
    builder.cbranch(active, body_block, exit_block)

    builder.position_at_end(body_block)
    previous_slot = builder.sub(offset, I32(CELL_BYTES), name="previous_slot")
    previous = raw_load_cell(builder, memory_ptr, previous_slot, name="previous")
    next_count = builder.add(count, I32(1), name="count_plus_one")
    builder.branch(head_block)
    offset.add_incoming(previous, body_block)
    count.add_incoming(next_count, body_block)

    builder.position_at_end(exit_block)
    builder.ret(count)


def emit_raw_get_nth(module: ir.Module) -> None:
    fn_type = ir.FunctionType(I32, [I8_PTR, I32, I32])
    fn = ir.Function(module, fn_type, name="raw_get_nth")
    memory_ptr, latest, n = fn.args
    entry_block = fn.append_basic_block("entry")
    head_block = fn.append_basic_block("head")
    body_block = fn.append_basic_block("body")
    found_block = fn.append_basic_block("found")
    continue_block = fn.append_basic_block("continue")
    exit_block = fn.append_basic_block("exit")
    builder = ir.IRBuilder(entry_block)
    builder.branch(head_block)

    builder.position_at_end(head_block)
    offset = builder.phi(I32, name="offset")
    count = builder.phi(I32, name="count")
    offset.add_incoming(latest, entry_block)
    count.add_incoming(I32(0), entry_block)
    active = builder.icmp_signed("!=", offset, I32(NULL_OFFSET), name="active")
    builder.cbranch(active, body_block, exit_block)

    builder.position_at_end(body_block)
    matched = builder.icmp_signed("==", count, n, name="matched")
    builder.cbranch(matched, found_block, continue_block)

    builder.position_at_end(found_block)
    builder.branch(exit_block)

    builder.position_at_end(continue_block)
    previous_slot = builder.sub(offset, I32(CELL_BYTES), name="previous_slot")
    previous = raw_load_cell(builder, memory_ptr, previous_slot, name="previous")
    next_count = builder.add(count, I32(1), name="count_plus_one")
    builder.branch(head_block)
    offset.add_incoming(previous, continue_block)
    count.add_incoming(next_count, continue_block)

    builder.position_at_end(exit_block)
    result = builder.phi(I32, name="nth_offset")
    result.add_incoming(I32(-1), head_block)
    result.add_incoming(offset, found_block)
    builder.ret(result)


def emit_helper_append(module: ir.Module) -> None:
    fn_type = ir.FunctionType(I32, [I8_PTR, I32_PTR, I32_PTR, I32])
    fn = ir.Function(module, fn_type, name="helper_append")
    memory_ptr, here_ptr, latest_ptr, value = fn.args
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    linked_list = PreviousLinkListIR(builder, memory_ptr, "helper")
    builder.ret(linked_list.append(here_ptr, latest_ptr, value))


def emit_helper_count(module: ir.Module) -> None:
    fn_type = ir.FunctionType(I32, [I8_PTR, I32])
    fn = ir.Function(module, fn_type, name="helper_count")
    memory_ptr, latest = fn.args
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    PreviousLinkListIR(builder, memory_ptr, "helper").count(latest)


def emit_helper_get_nth(module: ir.Module) -> None:
    fn_type = ir.FunctionType(I32, [I8_PTR, I32, I32])
    fn = ir.Function(module, fn_type, name="helper_get_nth")
    memory_ptr, latest, n = fn.args
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    PreviousLinkListIR(builder, memory_ptr, "helper").get_nth_offset(latest, n)


def build_module() -> ir.Module:
    module = ir.Module(name="previous_link_list_ir_abstractions")
    emit_raw_append(module)
    emit_raw_count(module)
    emit_raw_get_nth(module)
    emit_helper_append(module)
    emit_helper_count(module)
    emit_helper_get_nth(module)
    return module


def render_nodes(nodes: list[DecodedNode]) -> list[str]:
    return [
        f"data @ {node.data_offset:03d} | previous -> {node.previous_offset:03d} | value = {node.value}"
        for node in nodes
    ]


def main() -> None:
    configure_llvm()
    module = build_module()
    compiled = compile_ir_module(module)

    append_fn_type = CFUNCTYPE(c_int32, POINTER(c_uint8), POINTER(c_int32), POINTER(c_int32), c_int32)
    count_fn_type = CFUNCTYPE(c_int32, POINTER(c_uint8), c_int32)
    nth_fn_type = CFUNCTYPE(c_int32, POINTER(c_uint8), c_int32, c_int32)

    raw_append = append_fn_type(compiled.function_address("raw_append"))
    raw_count = count_fn_type(compiled.function_address("raw_count"))
    raw_get_nth = nth_fn_type(compiled.function_address("raw_get_nth"))
    helper_append = append_fn_type(compiled.function_address("helper_append"))
    helper_count = count_fn_type(compiled.function_address("helper_count"))
    helper_get_nth = nth_fn_type(compiled.function_address("helper_get_nth"))

    raw_arena = ByteArena()
    helper_arena = ByteArena()
    inserted_values = [11, 22, 33]

    raw_offsets = [
        raw_append(raw_arena.memory, raw_arena.here, raw_arena.latest, value) for value in inserted_values
    ]
    helper_offsets = [
        helper_append(helper_arena.memory, helper_arena.here, helper_arena.latest, value) for value in inserted_values
    ]

    assert raw_offsets == helper_offsets == [4, 12, 20]
    assert raw_arena.here.value == helper_arena.here.value == 28
    assert raw_arena.latest.value == helper_arena.latest.value == 20
    assert bytes(raw_arena.memory) == bytes(helper_arena.memory)

    raw_count_value = raw_count(raw_arena.memory, raw_arena.latest.value)
    helper_count_value = helper_count(helper_arena.memory, helper_arena.latest.value)
    assert raw_count_value == helper_count_value == 3

    raw_nth = [raw_get_nth(raw_arena.memory, raw_arena.latest.value, n) for n in range(4)]
    helper_nth = [helper_get_nth(helper_arena.memory, helper_arena.latest.value, n) for n in range(4)]
    assert raw_nth == helper_nth == [20, 12, 4, -1]

    decoded = helper_arena.decode_nodes()
    assert [node.value for node in decoded] == [33, 22, 11]

    print("== Question ==")
    print("What should an IR helper own for a newest-first previous-link list in linear memory?")
    print()

    print("== Layout Rules ==")
    print("Each node is `[previous link][data]` in byte-addressed memory.")
    print("The public node offset points at the data cell, not at the previous-link cell.")
    print(f"NULL_OFFSET = {NULL_OFFSET}")
    print(f"FIRST_NODE_OFFSET = {FIRST_NODE_OFFSET}")
    print(f"NODE_BYTES = {NODE_BYTES}")
    print()

    print("== Append Results ==")
    print(f"inserted values       = {inserted_values}")
    print(f"raw append offsets    = {raw_offsets}")
    print(f"helper append offsets = {helper_offsets}")
    print(f"latest offset         = {helper_arena.latest.value}")
    print(f"next free offset      = {helper_arena.here.value}")
    print()

    print("== Decoded Traversal ==")
    for line in render_nodes(decoded):
        print(line)
    print()

    print("== Query Results ==")
    print(f"raw_count(latest)    = {raw_count_value}")
    print(f"helper_count(latest) = {helper_count_value}")
    for n, (raw_offset, helper_offset) in enumerate(zip(raw_nth, helper_nth, strict=True)):
        print(f"nth={n}: raw -> {raw_offset:>3} | helper -> {helper_offset:>3}")
    print()

    print("== Memory Snapshot ==")
    for line in helper_arena.render_cells():
        print(line)
    print()

    print("== LLVM IR ==")
    print(compiled.llvm_ir)
    print()

    print("== Takeaway ==")
    print("The helper should own the `[previous link][data]` convention and modern loop scaffolding,")
    print("but the emitted count and nth-node traversals should still read like explicit CFG, not magic.")


if __name__ == "__main__":
    main()
