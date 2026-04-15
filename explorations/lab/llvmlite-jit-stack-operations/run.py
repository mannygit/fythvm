"""Demonstrate a tiny JITed downward-growing stack."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import binding, ir


STACK_SIZE = 8
I32 = ir.IntType(32)
I64 = ir.IntType(64)


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def build_raw_module() -> ir.Module:
    module = ir.Module(name="jit_stack_operations_raw")
    module.triple = binding.get_default_triple()

    stack_array_type = ir.ArrayType(I64, STACK_SIZE)
    stack_array = ir.GlobalVariable(module, stack_array_type, name="stack_array")
    stack_array.initializer = ir.Constant(stack_array_type, None)

    stack_sp = ir.GlobalVariable(module, I32, name="stack_sp")
    stack_sp.initializer = I32(STACK_SIZE)

    def stack_slot(builder: ir.IRBuilder, index: ir.Value) -> ir.Value:
        return builder.gep(stack_array, [I32(0), index], inbounds=True, name="slot_ptr")

    reset_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="reset_stack")
    block = reset_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    builder.store(I32(STACK_SIZE), stack_sp)
    builder.ret_void()

    get_sp_fn = ir.Function(module, ir.FunctionType(I32, []), name="get_sp")
    block = get_sp_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    builder.ret(builder.load(stack_sp, name="sp"))

    push_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), [I64]), name="push")
    block = push_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    current_sp = builder.load(stack_sp, name="sp")
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(push_fn.args[0], stack_slot(builder, new_sp))
    builder.store(new_sp, stack_sp)
    builder.ret_void()

    pop_fn = ir.Function(module, ir.FunctionType(I64, []), name="pop")
    block = pop_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    current_sp = builder.load(stack_sp, name="sp")
    value = builder.load(stack_slot(builder, current_sp), name="value")
    builder.store(builder.add(current_sp, I32(1), name="next_sp"), stack_sp)
    builder.ret(value)

    dup_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="dup")
    block = dup_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    current_sp = builder.load(stack_sp, name="sp")
    top = builder.load(stack_slot(builder, current_sp), name="top")
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(top, stack_slot(builder, new_sp))
    builder.store(new_sp, stack_sp)
    builder.ret_void()

    swap_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="swap")
    block = swap_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    current_sp = builder.load(stack_sp, name="sp")
    next_sp = builder.add(current_sp, I32(1), name="next_sp")
    top_ptr = stack_slot(builder, current_sp)
    next_ptr = stack_slot(builder, next_sp)
    top = builder.load(top_ptr, name="top")
    next_value = builder.load(next_ptr, name="next_value")
    builder.store(top, next_ptr)
    builder.store(next_value, top_ptr)
    builder.ret_void()

    over_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="over")
    block = over_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    current_sp = builder.load(stack_sp, name="sp")
    second_sp = builder.add(current_sp, I32(1), name="second_sp")
    second = builder.load(stack_slot(builder, second_sp), name="second")
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(second, stack_slot(builder, new_sp))
    builder.store(new_sp, stack_sp)
    builder.ret_void()

    return module


class StackLayout:
    def __init__(self, module: ir.Module):
        self.module = module
        self.stack_array_type = ir.ArrayType(I64, STACK_SIZE)
        self.stack_array = ir.GlobalVariable(module, self.stack_array_type, name="stack_array")
        self.stack_array.initializer = ir.Constant(self.stack_array_type, None)
        self.stack_sp = ir.GlobalVariable(module, I32, name="stack_sp")
        self.stack_sp.initializer = I32(STACK_SIZE)

    def slot(self, builder: ir.IRBuilder, index: ir.Value, name: str = "slot_ptr") -> ir.Value:
        return builder.gep(self.stack_array, [I32(0), index], inbounds=True, name=name)

    def load_sp(self, builder: ir.IRBuilder, name: str = "sp") -> ir.Value:
        return builder.load(self.stack_sp, name=name)

    def store_sp(self, builder: ir.IRBuilder, value: ir.Value) -> None:
        builder.store(value, self.stack_sp)

    def define_reset(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), []), name="reset_stack")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        self.store_sp(builder, I32(STACK_SIZE))
        builder.ret_void()
        return fn

    def define_get_sp(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(I32, []), name="get_sp")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        builder.ret(self.load_sp(builder))
        return fn

    def define_push(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [I64]), name="push")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        current_sp = self.load_sp(builder)
        new_sp = builder.sub(current_sp, I32(1), name="new_sp")
        builder.store(fn.args[0], self.slot(builder, new_sp))
        self.store_sp(builder, new_sp)
        builder.ret_void()
        return fn

    def define_pop(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(I64, []), name="pop")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        current_sp = self.load_sp(builder)
        value = builder.load(self.slot(builder, current_sp), name="value")
        self.store_sp(builder, builder.add(current_sp, I32(1), name="next_sp"))
        builder.ret(value)
        return fn

    def define_dup(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), []), name="dup")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        current_sp = self.load_sp(builder)
        top = builder.load(self.slot(builder, current_sp), name="top")
        new_sp = builder.sub(current_sp, I32(1), name="new_sp")
        builder.store(top, self.slot(builder, new_sp))
        self.store_sp(builder, new_sp)
        builder.ret_void()
        return fn

    def define_swap(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), []), name="swap")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        current_sp = self.load_sp(builder)
        next_sp = builder.add(current_sp, I32(1), name="next_sp")
        top_ptr = self.slot(builder, current_sp)
        next_ptr = self.slot(builder, next_sp)
        top = builder.load(top_ptr, name="top")
        next_value = builder.load(next_ptr, name="next_value")
        builder.store(top, next_ptr)
        builder.store(next_value, top_ptr)
        builder.ret_void()
        return fn

    def define_over(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), []), name="over")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        current_sp = self.load_sp(builder)
        second_sp = builder.add(current_sp, I32(1), name="second_sp")
        second = builder.load(self.slot(builder, second_sp), name="second")
        new_sp = builder.sub(current_sp, I32(1), name="new_sp")
        builder.store(second, self.slot(builder, new_sp))
        self.store_sp(builder, new_sp)
        builder.ret_void()
        return fn


def build_pythonic_module() -> ir.Module:
    module = ir.Module(name="jit_stack_operations_pythonic")
    module.triple = binding.get_default_triple()
    layout = StackLayout(module)
    layout.define_reset()
    layout.define_get_sp()
    layout.define_push()
    layout.define_pop()
    layout.define_dup()
    layout.define_swap()
    layout.define_over()
    return module


@dataclass(frozen=True)
class CompiledModule:
    label: str
    llvm_ir: str
    engine: binding.ExecutionEngine
    reset_stack_addr: int
    get_sp_addr: int
    push_addr: int
    pop_addr: int
    dup_addr: int
    swap_addr: int
    over_addr: int


def compile_module(label: str, module: ir.Module) -> CompiledModule:
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    return CompiledModule(
        label=label,
        llvm_ir=llvm_ir,
        engine=engine,
        reset_stack_addr=engine.get_function_address("reset_stack"),
        get_sp_addr=engine.get_function_address("get_sp"),
        push_addr=engine.get_function_address("push"),
        pop_addr=engine.get_function_address("pop"),
        dup_addr=engine.get_function_address("dup"),
        swap_addr=engine.get_function_address("swap"),
        over_addr=engine.get_function_address("over"),
    )


def logical_stack(array: ctypes.Array[ctypes.c_int64], sp: int) -> list[int]:
    return list(reversed(array[sp:STACK_SIZE]))


def call_void0(address: int) -> ctypes.CFUNCTYPE:
    return ctypes.CFUNCTYPE(None)(address)


def call_int32_0(address: int) -> ctypes.CFUNCTYPE:
    return ctypes.CFUNCTYPE(ctypes.c_int32)(address)


def call_void_i64(address: int) -> ctypes.CFUNCTYPE:
    return ctypes.CFUNCTYPE(None, ctypes.c_int64)(address)


def call_i64_0(address: int) -> ctypes.CFUNCTYPE:
    return ctypes.CFUNCTYPE(ctypes.c_int64)(address)


def run_stack_scenario(compiled: CompiledModule) -> tuple[list[str], int]:
    reset_stack = call_void0(compiled.reset_stack_addr)
    get_sp = call_int32_0(compiled.get_sp_addr)
    push = call_void_i64(compiled.push_addr)
    pop = call_i64_0(compiled.pop_addr)
    dup = call_void0(compiled.dup_addr)
    swap = call_void0(compiled.swap_addr)
    over = call_void0(compiled.over_addr)

    stack_addr = compiled.engine.get_global_value_address("stack_array")
    stack_view = (ctypes.c_int64 * STACK_SIZE).from_address(stack_addr)

    snapshots: list[str] = []

    def snapshot(label: str) -> None:
        sp = int(get_sp())
        snapshots.append(f"{label}: sp={sp}, logical_stack={logical_stack(stack_view, sp)}")

    reset_stack()
    snapshot("after reset")
    push(10)
    snapshot("after push 10")
    push(20)
    snapshot("after push 20")
    swap()
    snapshot("after swap")
    over()
    snapshot("after over")
    dup()
    snapshot("after dup")
    popped = int(pop())
    snapshots.append(f"pop() -> {popped}")
    snapshot("after pop")
    return snapshots, popped


def main() -> None:
    configure_llvm()
    raw = compile_module("raw", build_raw_module())
    pythonic = compile_module("pythonic", build_pythonic_module())

    print("== Question ==")
    print("What is the smallest useful downward-growing JITed stack pattern?")
    print()

    print("== Raw IR ==")
    print(raw.llvm_ir.rstrip())
    print()
    print("== Pythonic IR ==")
    print(pythonic.llvm_ir.rstrip())
    print()

    print("== Raw Stack Trace ==")
    raw_trace, raw_popped = run_stack_scenario(raw)
    for line in raw_trace:
        print(line)
    print()

    print("== Pythonic Stack Trace ==")
    pythonic_trace, pythonic_popped = run_stack_scenario(pythonic)
    for line in pythonic_trace:
        print(line)
    print()

    print("== Comparison ==")
    print(f"traces match: {raw_trace == pythonic_trace}")
    print(f"popped values match: {raw_popped == pythonic_popped}")
    print()

    print("== Takeaway ==")
    print("Keep the raw stack memory and stack pointer visible as the source of truth.")
    print("The Pythonic layer only reduces repeated slot arithmetic and function boilerplate; it does not hide the physical stack layout or the order in which values move.")


if __name__ == "__main__":
    main()
