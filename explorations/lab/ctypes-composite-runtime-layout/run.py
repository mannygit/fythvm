"""Demonstrate composite ctypes runtime records with promoted struct helpers."""

from __future__ import annotations

import ctypes

from llvmlite import binding, ir

from fythvm.codegen import compile_ir_module, configure_llvm
from fythvm.dictionary import (
    CELL_SIZE,
    DEFAULT_STACK_CELLS,
    DictionaryMemory,
    InterpreterRuntimeData,
    Registers,
    StackBounds,
)
from fythvm.dictionary.schema import DictionaryMemory as DictionaryMemorySchema
from fythvm.dictionary.layout import (
    dictionary_memory_handle,
    interpreter_runtime_handle,
    registers_handle,
    stack_bounds_handle,
)


I32 = ir.IntType(32)
I64 = ir.IntType(64)


def describe_ctypes_layout(struct_cls: type[ctypes.Structure]) -> str:
    offsets = [getattr(struct_cls, field_name).offset for field_name, *_ in struct_cls._fields_]
    return f"{struct_cls.__name__}: sizeof={ctypes.sizeof(struct_cls)} offsets={offsets}"


def array_slot(builder: ir.IRBuilder, array_ptr: ir.Value, index: int, *, name: str) -> ir.Value:
    return builder.gep(array_ptr, [I32(0), I32(index)], inbounds=True, name=name)


def build_module() -> ir.Module:
    configure_llvm()
    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()

    module = ir.Module(name="ctypes_composite_runtime_layout")
    module.triple = binding.get_default_triple()
    module.data_layout = str(target_machine.target_data)

    memory_handle = dictionary_memory_handle()
    registers = registers_handle()
    stack_bounds = stack_bounds_handle()
    runtime_handle = interpreter_runtime_handle()

    raw_read_here = ir.Function(module, ir.FunctionType(I32, [memory_handle.ir_type.as_pointer()]), name="raw_read_here")
    memory_ptr = raw_read_here.args[0]
    builder = ir.IRBuilder(raw_read_here.append_basic_block("entry"))
    registers_ptr = builder.gep(memory_ptr, [I32(0), I32(0)], inbounds=True, name="registers_ptr")
    here_ptr = builder.gep(registers_ptr, [I32(0), I32(0)], inbounds=True, name="here_ptr")
    builder.ret(builder.load(here_ptr, name="here"))

    pythonic_read_here = ir.Function(module, ir.FunctionType(I32, [memory_handle.ir_type.as_pointer()]), name="pythonic_read_here")
    memory_ptr = pythonic_read_here.args[0]
    builder = ir.IRBuilder(pythonic_read_here.append_basic_block("entry"))
    memory_view = memory_handle.bind(builder, memory_ptr)
    registers_view = memory_view.registers.bind(registers)
    builder.ret(registers_view.here.load())

    sum_first_three_cells = ir.Function(
        module,
        ir.FunctionType(I32, [memory_handle.ir_type.as_pointer()]),
        name="sum_first_three_cells",
    )
    memory_ptr = sum_first_three_cells.args[0]
    builder = ir.IRBuilder(sum_first_three_cells.append_basic_block("entry"))
    memory_view = memory_handle.bind(builder, memory_ptr)
    cells_ptr = memory_view.cells.ptr(name="cells_ptr")
    first = builder.load(array_slot(builder, cells_ptr, 0, name="cell0_ptr"), name="cell0")
    second = builder.load(array_slot(builder, cells_ptr, 1, name="cell1_ptr"), name="cell1")
    third = builder.load(array_slot(builder, cells_ptr, 2, name="cell2_ptr"), name="cell2")
    subtotal = builder.add(first, second, name="subtotal")
    builder.ret(builder.add(subtotal, third, name="total"))

    stack_span_bytes = ir.Function(module, ir.FunctionType(I64, [runtime_handle.ir_type.as_pointer()]), name="stack_span_bytes")
    runtime_ptr = stack_span_bytes.args[0]
    builder = ir.IRBuilder(stack_span_bytes.append_basic_block("entry"))
    runtime_view = runtime_handle.bind(builder, runtime_ptr)
    psp_view = runtime_view.psp.bind(stack_bounds)
    top_addr = builder.ptrtoint(psp_view.top.load(name="top"), I64, name="top_addr")
    bottom_addr = builder.ptrtoint(psp_view.bottom.load(name="bottom"), I64, name="bottom_addr")
    builder.ret(builder.sub(bottom_addr, top_addr, name="span"))

    return module


def main() -> None:
    module = build_module()
    compiled = compile_ir_module(module)

    memory = DictionaryMemory()
    memory.clear()
    memory.registers.here = 12
    memory.registers.latest = 9
    memory.cells[0] = 7
    memory.cells[1] = 11
    memory.cells[2] = 13

    stack_top = ctypes.cast(ctypes.byref(memory.data_stack, 0), ctypes.POINTER(ctypes.c_int32))
    stack_bottom = ctypes.cast(
        ctypes.byref(memory.data_stack, (DEFAULT_STACK_CELLS - 1) * CELL_SIZE),
        ctypes.POINTER(ctypes.c_int32),
    )
    runtime = InterpreterRuntimeData(
        memory_ptr=ctypes.cast(ctypes.pointer(memory), ctypes.POINTER(DictionaryMemorySchema)),
        psp=StackBounds(top=stack_top, bottom=stack_bottom),
        rsp=StackBounds(top=stack_top, bottom=stack_bottom),
        tos=stack_top,
        rtos=stack_top,
    )

    raw_read_here = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(DictionaryMemory))(
        compiled.function_address("raw_read_here")
    )
    pythonic_read_here = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(DictionaryMemory))(
        compiled.function_address("pythonic_read_here")
    )
    sum_first_three_cells = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(DictionaryMemory))(
        compiled.function_address("sum_first_three_cells")
    )
    stack_span_bytes = ctypes.CFUNCTYPE(ctypes.c_longlong, ctypes.POINTER(InterpreterRuntimeData))(
        compiled.function_address("stack_span_bytes")
    )

    print("== Question ==")
    print("How do the fixed runtime records from ~/fyth map into nested ctypes structs, arrays, pointers, and promoted llvmlite struct views?")
    print()

    print("== Fixed Runtime Records ==")
    print(describe_ctypes_layout(Registers))
    print(describe_ctypes_layout(StackBounds))
    print(describe_ctypes_layout(DictionaryMemory))
    print(describe_ctypes_layout(InterpreterRuntimeData))
    print()

    print("== Generated IR ==")
    print(compiled.llvm_ir)
    print()

    print("== Live Proof ==")
    print(f"raw_read_here(memory)      -> {raw_read_here(ctypes.pointer(memory))}")
    print(f"pythonic_read_here(memory) -> {pythonic_read_here(ctypes.pointer(memory))}")
    print(f"sum_first_three_cells      -> {sum_first_three_cells(ctypes.pointer(memory))}")
    print(f"stack_span_bytes(runtime)  -> {stack_span_bytes(ctypes.pointer(runtime))}")
    print()

    print("== Takeaway ==")
    print("Nested structs, arrays, and pointers are all expressible as fixed ctypes records plus promoted StructHandle views.")
    print("That works well for Registers/Memory/RuntimeData. It does not solve the variable-size word-entry protocol yet.")


if __name__ == "__main__":
    main()
