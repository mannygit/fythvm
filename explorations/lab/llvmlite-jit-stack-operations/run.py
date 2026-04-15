"""Demonstrate JITed stack operations over module-owned and host-owned memory."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import binding, ir


STACK_SIZE = 8
I32 = ir.IntType(32)
I64 = ir.IntType(64)
I64_PTR = I64.as_pointer()
I32_PTR = I32.as_pointer()


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def build_raw_global_module() -> ir.Module:
    module = ir.Module(name="jit_stack_operations_raw_global")
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


def build_raw_external_module() -> ir.Module:
    module = ir.Module(name="jit_stack_operations_raw_external")
    module.triple = binding.get_default_triple()

    stack_base_ptr = ir.GlobalVariable(module, I64_PTR, name="stack_base_ptr")
    stack_base_ptr.initializer = ir.Constant(I64_PTR, None)

    stack_sp_ptr = ir.GlobalVariable(module, I32_PTR, name="stack_sp_ptr")
    stack_sp_ptr.initializer = ir.Constant(I32_PTR, None)

    def load_stack_base(builder: ir.IRBuilder) -> ir.Value:
        return builder.load(stack_base_ptr, name="stack_base")

    def load_sp_ptr(builder: ir.IRBuilder) -> ir.Value:
        return builder.load(stack_sp_ptr, name="sp_ptr")

    def stack_slot(builder: ir.IRBuilder, index: ir.Value) -> ir.Value:
        return builder.gep(load_stack_base(builder), [index], inbounds=True, name="slot_ptr")

    bind_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), [I64, I64]), name="bind_external_stack")
    block = bind_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    builder.store(builder.inttoptr(bind_fn.args[0], I64_PTR, name="base_ptr"), stack_base_ptr)
    builder.store(builder.inttoptr(bind_fn.args[1], I32_PTR, name="sp_ptr"), stack_sp_ptr)
    builder.ret_void()

    reset_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="reset_stack")
    block = reset_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    builder.store(I32(STACK_SIZE), load_sp_ptr(builder))
    builder.ret_void()

    get_sp_fn = ir.Function(module, ir.FunctionType(I32, []), name="get_sp")
    block = get_sp_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    builder.ret(builder.load(load_sp_ptr(builder), name="sp"))

    push_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), [I64]), name="push")
    block = push_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    sp_ptr = load_sp_ptr(builder)
    current_sp = builder.load(sp_ptr, name="sp")
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(push_fn.args[0], stack_slot(builder, new_sp))
    builder.store(new_sp, sp_ptr)
    builder.ret_void()

    pop_fn = ir.Function(module, ir.FunctionType(I64, []), name="pop")
    block = pop_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    sp_ptr = load_sp_ptr(builder)
    current_sp = builder.load(sp_ptr, name="sp")
    value = builder.load(stack_slot(builder, current_sp), name="value")
    builder.store(builder.add(current_sp, I32(1), name="next_sp"), sp_ptr)
    builder.ret(value)

    dup_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="dup")
    block = dup_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    sp_ptr = load_sp_ptr(builder)
    current_sp = builder.load(sp_ptr, name="sp")
    top = builder.load(stack_slot(builder, current_sp), name="top")
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(top, stack_slot(builder, new_sp))
    builder.store(new_sp, sp_ptr)
    builder.ret_void()

    swap_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="swap")
    block = swap_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    current_sp = builder.load(load_sp_ptr(builder), name="sp")
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
    sp_ptr = load_sp_ptr(builder)
    current_sp = builder.load(sp_ptr, name="sp")
    second_sp = builder.add(current_sp, I32(1), name="second_sp")
    second = builder.load(stack_slot(builder, second_sp), name="second")
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(second, stack_slot(builder, new_sp))
    builder.store(new_sp, sp_ptr)
    builder.ret_void()

    return module


class StackStorage:
    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        raise NotImplementedError

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        raise NotImplementedError

    def slot(self, builder: ir.IRBuilder, index: ir.Value, name: str = "slot_ptr") -> ir.Value:
        return builder.gep(self.load_stack_base(builder), [index], inbounds=True, name=name)

    def load_sp(self, builder: ir.IRBuilder, name: str = "sp") -> ir.Value:
        return builder.load(self.load_sp_ptr(builder), name=name)

    def store_sp(self, builder: ir.IRBuilder, value: ir.Value) -> None:
        builder.store(value, self.load_sp_ptr(builder))


class GlobalStackStorage(StackStorage):
    def __init__(self, module: ir.Module):
        self.stack_array_type = ir.ArrayType(I64, STACK_SIZE)
        self.stack_array = ir.GlobalVariable(module, self.stack_array_type, name="stack_array")
        self.stack_array.initializer = ir.Constant(self.stack_array_type, None)
        self.stack_sp = ir.GlobalVariable(module, I32, name="stack_sp")
        self.stack_sp.initializer = I32(STACK_SIZE)

    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        return builder.gep(self.stack_array, [I32(0), I32(0)], inbounds=True, name="stack_base")

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        return self.stack_sp


class ExternalStackStorage(StackStorage):
    def __init__(self, module: ir.Module):
        self.module = module
        self.stack_base_ptr = ir.GlobalVariable(module, I64_PTR, name="stack_base_ptr")
        self.stack_base_ptr.initializer = ir.Constant(I64_PTR, None)
        self.stack_sp_ptr = ir.GlobalVariable(module, I32_PTR, name="stack_sp_ptr")
        self.stack_sp_ptr.initializer = ir.Constant(I32_PTR, None)

    def define_bind(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [I64, I64]), name="bind_external_stack")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        builder.store(builder.inttoptr(fn.args[0], I64_PTR, name="base_ptr"), self.stack_base_ptr)
        builder.store(builder.inttoptr(fn.args[1], I32_PTR, name="sp_ptr"), self.stack_sp_ptr)
        builder.ret_void()
        return fn

    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        return builder.load(self.stack_base_ptr, name="stack_base")

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        return builder.load(self.stack_sp_ptr, name="sp_ptr")


class StackOps:
    def __init__(self, module: ir.Module, storage: StackStorage):
        self.module = module
        self.storage = storage

    def define_reset(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), []), name="reset_stack")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        self.storage.store_sp(builder, I32(STACK_SIZE))
        builder.ret_void()
        return fn

    def define_get_sp(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(I32, []), name="get_sp")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        builder.ret(self.storage.load_sp(builder))
        return fn

    def define_push(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [I64]), name="push")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        current_sp = self.storage.load_sp(builder)
        new_sp = builder.sub(current_sp, I32(1), name="new_sp")
        builder.store(fn.args[0], self.storage.slot(builder, new_sp))
        self.storage.store_sp(builder, new_sp)
        builder.ret_void()
        return fn

    def define_pop(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(I64, []), name="pop")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        current_sp = self.storage.load_sp(builder)
        value = builder.load(self.storage.slot(builder, current_sp), name="value")
        self.storage.store_sp(builder, builder.add(current_sp, I32(1), name="next_sp"))
        builder.ret(value)
        return fn

    def define_dup(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), []), name="dup")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        current_sp = self.storage.load_sp(builder)
        top = builder.load(self.storage.slot(builder, current_sp), name="top")
        new_sp = builder.sub(current_sp, I32(1), name="new_sp")
        builder.store(top, self.storage.slot(builder, new_sp))
        self.storage.store_sp(builder, new_sp)
        builder.ret_void()
        return fn

    def define_swap(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), []), name="swap")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        current_sp = self.storage.load_sp(builder)
        next_sp = builder.add(current_sp, I32(1), name="next_sp")
        top_ptr = self.storage.slot(builder, current_sp)
        next_ptr = self.storage.slot(builder, next_sp)
        top = builder.load(top_ptr, name="top")
        next_value = builder.load(next_ptr, name="next_value")
        builder.store(top, next_ptr)
        builder.store(next_value, top_ptr)
        builder.ret_void()
        return fn

    def define_over(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), []), name="over")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        current_sp = self.storage.load_sp(builder)
        second_sp = builder.add(current_sp, I32(1), name="second_sp")
        second = builder.load(self.storage.slot(builder, second_sp), name="second")
        new_sp = builder.sub(current_sp, I32(1), name="new_sp")
        builder.store(second, self.storage.slot(builder, new_sp))
        self.storage.store_sp(builder, new_sp)
        builder.ret_void()
        return fn


def build_pythonic_global_module() -> ir.Module:
    module = ir.Module(name="jit_stack_operations_pythonic_global")
    module.triple = binding.get_default_triple()
    storage = GlobalStackStorage(module)
    ops = StackOps(module, storage)
    ops.define_reset()
    ops.define_get_sp()
    ops.define_push()
    ops.define_pop()
    ops.define_dup()
    ops.define_swap()
    ops.define_over()
    return module


def build_pythonic_external_module() -> ir.Module:
    module = ir.Module(name="jit_stack_operations_pythonic_external")
    module.triple = binding.get_default_triple()
    storage = ExternalStackStorage(module)
    storage.define_bind()
    ops = StackOps(module, storage)
    ops.define_reset()
    ops.define_get_sp()
    ops.define_push()
    ops.define_pop()
    ops.define_dup()
    ops.define_swap()
    ops.define_over()
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
    bind_external_stack_addr: int | None


def compile_module(label: str, module: ir.Module) -> CompiledModule:
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    bind_external_stack_addr = engine.get_function_address("bind_external_stack")

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
        bind_external_stack_addr=bind_external_stack_addr or None,
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


def call_void_i64_i64(address: int) -> ctypes.CFUNCTYPE:
    return ctypes.CFUNCTYPE(None, ctypes.c_int64, ctypes.c_int64)(address)


def execute_stack_scenario(
    compiled: CompiledModule,
    stack_view: ctypes.Array[ctypes.c_int64],
) -> tuple[list[str], int]:
    reset_stack = call_void0(compiled.reset_stack_addr)
    get_sp = call_int32_0(compiled.get_sp_addr)
    push = call_void_i64(compiled.push_addr)
    pop = call_i64_0(compiled.pop_addr)
    dup = call_void0(compiled.dup_addr)
    swap = call_void0(compiled.swap_addr)
    over = call_void0(compiled.over_addr)

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


def run_global_stack_scenario(compiled: CompiledModule) -> tuple[list[str], int]:
    stack_addr = compiled.engine.get_global_value_address("stack_array")
    stack_view = (ctypes.c_int64 * STACK_SIZE).from_address(stack_addr)
    return execute_stack_scenario(compiled, stack_view)


def run_external_stack_scenario(compiled: CompiledModule) -> tuple[list[str], int]:
    assert compiled.bind_external_stack_addr is not None, "external-backed scenario requires bind_external_stack"
    bind_external_stack = call_void_i64_i64(compiled.bind_external_stack_addr)

    stack_view = (ctypes.c_int64 * STACK_SIZE)()
    sp_view = ctypes.c_int32(STACK_SIZE)

    bind_external_stack(ctypes.addressof(stack_view), ctypes.addressof(sp_view))
    return execute_stack_scenario(compiled, stack_view)


def print_trace(title: str, trace: list[str]) -> None:
    print(f"== {title} ==")
    for line in trace:
        print(line)
    print()


def main() -> None:
    configure_llvm()

    raw_global = compile_module("raw module-global", build_raw_global_module())
    pythonic_global = compile_module("pythonic module-global", build_pythonic_global_module())
    raw_external = compile_module("raw external-backed", build_raw_external_module())
    pythonic_external = compile_module("pythonic external-backed", build_pythonic_external_module())

    print("== Question ==")
    print("What is the smallest useful downward-growing JITed stack pattern once stack storage ownership is separated from the stack operations?")
    print()

    print("== Raw Module-Global IR ==")
    print(raw_global.llvm_ir.rstrip())
    print()
    print("== Pythonic Module-Global IR ==")
    print(pythonic_global.llvm_ir.rstrip())
    print()
    print("== Raw External-Backed IR ==")
    print(raw_external.llvm_ir.rstrip())
    print()
    print("== Pythonic External-Backed IR ==")
    print(pythonic_external.llvm_ir.rstrip())
    print()

    raw_global_trace, raw_global_popped = run_global_stack_scenario(raw_global)
    pythonic_global_trace, pythonic_global_popped = run_global_stack_scenario(pythonic_global)
    raw_external_trace, raw_external_popped = run_external_stack_scenario(raw_external)
    pythonic_external_trace, pythonic_external_popped = run_external_stack_scenario(pythonic_external)

    print_trace("Raw Module-Global Stack Trace", raw_global_trace)
    print_trace("Pythonic Module-Global Stack Trace", pythonic_global_trace)
    print_trace("Raw External-Backed Stack Trace", raw_external_trace)
    print_trace("Pythonic External-Backed Stack Trace", pythonic_external_trace)

    print("== Comparison ==")
    print(f"module-global traces match: {raw_global_trace == pythonic_global_trace}")
    print(f"module-global popped values match: {raw_global_popped == pythonic_global_popped}")
    print(f"external-backed traces match: {raw_external_trace == pythonic_external_trace}")
    print(f"external-backed popped values match: {raw_external_popped == pythonic_external_popped}")
    print(
        "module-global vs external-backed trace parity: "
        f"{raw_global_trace == pythonic_global_trace == raw_external_trace == pythonic_external_trace}"
    )
    print(
        "module-global vs external-backed pop parity: "
        f"{raw_global_popped == pythonic_global_popped == raw_external_popped == pythonic_external_popped}"
    )
    print()

    print("== Takeaway ==")
    print("Keep the raw stack memory and stack pointer visible as the source of truth.")
    print("The extra indirection layer is the boundary that lets the same stack operations work over either module-owned globals or host-owned memory.")
    print("The Pythonic layer only factors storage access and repeated stack op definitions; it does not hide the physical stack layout or the pointer chasing required to reach external storage.")


if __name__ == "__main__":
    main()
