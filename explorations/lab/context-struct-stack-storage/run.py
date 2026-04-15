"""Demonstrate stack ops emitted from an abstract pointer-derivation base class."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import binding, ir


STACK_SIZE = 8
I32 = ir.IntType(32)
I64 = ir.IntType(64)
I64_PTR = I64.as_pointer()
I32_PTR = I32.as_pointer()


class StackContext(ctypes.Structure):
    _fields_ = [
        ("generation", ctypes.c_int32),
        ("stack", ctypes.c_int64 * STACK_SIZE),
        ("sp", ctypes.c_int32),
    ]


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


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


def call_void_i64_1(address: int) -> ctypes.CFUNCTYPE:
    return ctypes.CFUNCTYPE(None, ctypes.c_int64)(address)


def build_raw_context_module() -> ir.Module:
    module = ir.Module(name="context_struct_stack_storage_raw")
    module.triple = binding.get_default_triple()

    ctx_type = ir.LiteralStructType([I32, ir.ArrayType(I64, STACK_SIZE), I32])
    ctx_ptr_global = ir.GlobalVariable(module, ctx_type.as_pointer(), name="stack_ctx_ptr")
    ctx_ptr_global.initializer = ir.Constant(ctx_type.as_pointer(), None)

    def load_ctx(builder: ir.IRBuilder) -> ir.Value:
        return builder.load(ctx_ptr_global, name="ctx")

    def stack_base(builder: ir.IRBuilder) -> ir.Value:
        ctx = load_ctx(builder)
        stack_array_ptr = builder.gep(ctx, [I32(0), I32(1)], inbounds=True, name="stack_array_ptr")
        return builder.gep(stack_array_ptr, [I32(0), I32(0)], inbounds=True, name="stack_base")

    def sp_ptr(builder: ir.IRBuilder) -> ir.Value:
        ctx = load_ctx(builder)
        return builder.gep(ctx, [I32(0), I32(2)], inbounds=True, name="sp_ptr")

    def slot(builder: ir.IRBuilder, index: ir.Value) -> ir.Value:
        return builder.gep(stack_base(builder), [index], inbounds=True, name="slot_ptr")

    bind_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), [I64]), name="bind_stack_context")
    builder = ir.IRBuilder(bind_fn.append_basic_block(name="entry"))
    builder.store(builder.inttoptr(bind_fn.args[0], ctx_type.as_pointer(), name="ctx_ptr"), ctx_ptr_global)
    builder.ret_void()

    reset_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="reset_stack")
    builder = ir.IRBuilder(reset_fn.append_basic_block(name="entry"))
    builder.store(I32(STACK_SIZE), sp_ptr(builder))
    builder.ret_void()

    get_sp_fn = ir.Function(module, ir.FunctionType(I32, []), name="get_sp")
    builder = ir.IRBuilder(get_sp_fn.append_basic_block(name="entry"))
    builder.ret(builder.load(sp_ptr(builder), name="sp"))

    push_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), [I64]), name="push")
    builder = ir.IRBuilder(push_fn.append_basic_block(name="entry"))
    current_sp = builder.load(sp_ptr(builder), name="sp")
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(push_fn.args[0], slot(builder, new_sp))
    builder.store(new_sp, sp_ptr(builder))
    builder.ret_void()

    pop_fn = ir.Function(module, ir.FunctionType(I64, []), name="pop")
    builder = ir.IRBuilder(pop_fn.append_basic_block(name="entry"))
    current_sp = builder.load(sp_ptr(builder), name="sp")
    value = builder.load(slot(builder, current_sp), name="value")
    builder.store(builder.add(current_sp, I32(1), name="next_sp"), sp_ptr(builder))
    builder.ret(value)

    dup_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="dup")
    builder = ir.IRBuilder(dup_fn.append_basic_block(name="entry"))
    current_sp = builder.load(sp_ptr(builder), name="sp")
    top = builder.load(slot(builder, current_sp), name="top")
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(top, slot(builder, new_sp))
    builder.store(new_sp, sp_ptr(builder))
    builder.ret_void()

    swap_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="swap")
    builder = ir.IRBuilder(swap_fn.append_basic_block(name="entry"))
    current_sp = builder.load(sp_ptr(builder), name="sp")
    next_sp = builder.add(current_sp, I32(1), name="next_sp")
    top_ptr = slot(builder, current_sp)
    next_ptr = slot(builder, next_sp)
    top = builder.load(top_ptr, name="top")
    next_value = builder.load(next_ptr, name="next_value")
    builder.store(top, next_ptr)
    builder.store(next_value, top_ptr)
    builder.ret_void()

    over_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), []), name="over")
    builder = ir.IRBuilder(over_fn.append_basic_block(name="entry"))
    current_sp = builder.load(sp_ptr(builder), name="sp")
    second_sp = builder.add(current_sp, I32(1), name="second_sp")
    second = builder.load(slot(builder, second_sp), name="second")
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(second, slot(builder, new_sp))
    builder.store(new_sp, sp_ptr(builder))
    builder.ret_void()

    return module


class AbstractStackEmitter:
    def __init__(self, module: ir.Module):
        self.module = module

    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        raise NotImplementedError

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        raise NotImplementedError

    def define_bind(self) -> ir.Function | None:
        return None

    def slot(self, builder: ir.IRBuilder, index: ir.Value, name: str = "slot_ptr") -> ir.Value:
        return builder.gep(self.load_stack_base(builder), [index], inbounds=True, name=name)

    def load_sp(self, builder: ir.IRBuilder, name: str = "sp") -> ir.Value:
        return builder.load(self.load_sp_ptr(builder), name=name)

    def store_sp(self, builder: ir.IRBuilder, value: ir.Value) -> None:
        builder.store(value, self.load_sp_ptr(builder))

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

    def define_all(self) -> None:
        self.define_bind()
        self.define_reset()
        self.define_get_sp()
        self.define_push()
        self.define_pop()
        self.define_dup()
        self.define_swap()
        self.define_over()


class ModuleGlobalStackEmitter(AbstractStackEmitter):
    def __init__(self, module: ir.Module):
        super().__init__(module)
        self.stack_array = ir.GlobalVariable(module, ir.ArrayType(I64, STACK_SIZE), name="stack_array")
        self.stack_array.initializer = ir.Constant(self.stack_array.type.pointee, None)
        self.stack_sp = ir.GlobalVariable(module, I32, name="stack_sp")
        self.stack_sp.initializer = I32(STACK_SIZE)

    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        return builder.gep(self.stack_array, [I32(0), I32(0)], inbounds=True, name="stack_base")

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        return self.stack_sp


class PointerGlobalStackEmitter(AbstractStackEmitter):
    def __init__(self, module: ir.Module):
        super().__init__(module)
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


class ContextStructStackEmitter(AbstractStackEmitter):
    def __init__(self, module: ir.Module):
        super().__init__(module)
        self.ctx_type = ir.LiteralStructType([I32, ir.ArrayType(I64, STACK_SIZE), I32])
        self.ctx_ptr_global = ir.GlobalVariable(module, self.ctx_type.as_pointer(), name="stack_ctx_ptr")
        self.ctx_ptr_global.initializer = ir.Constant(self.ctx_type.as_pointer(), None)

    def define_bind(self) -> ir.Function:
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [I64]), name="bind_stack_context")
        builder = ir.IRBuilder(fn.append_basic_block(name="entry"))
        builder.store(builder.inttoptr(fn.args[0], self.ctx_type.as_pointer(), name="ctx_ptr"), self.ctx_ptr_global)
        builder.ret_void()
        return fn

    def load_ctx(self, builder: ir.IRBuilder) -> ir.Value:
        return builder.load(self.ctx_ptr_global, name="ctx")

    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        ctx = self.load_ctx(builder)
        stack_array_ptr = builder.gep(ctx, [I32(0), I32(1)], inbounds=True, name="stack_array_ptr")
        return builder.gep(stack_array_ptr, [I32(0), I32(0)], inbounds=True, name="stack_base")

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        ctx = self.load_ctx(builder)
        return builder.gep(ctx, [I32(0), I32(2)], inbounds=True, name="sp_ptr")


def build_pythonic_module(name: str, emitter_type: type[AbstractStackEmitter]) -> ir.Module:
    module = ir.Module(name=name)
    module.triple = binding.get_default_triple()
    emitter_type(module).define_all()
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
    bind_stack_context_addr: int | None


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
        bind_external_stack_addr=engine.get_function_address("bind_external_stack") or None,
        bind_stack_context_addr=engine.get_function_address("bind_stack_context") or None,
    )


def execute_stack_scenario(compiled: CompiledModule, stack_view: ctypes.Array[ctypes.c_int64]) -> tuple[list[str], int]:
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


def run_global_scenario(compiled: CompiledModule) -> tuple[list[str], int]:
    stack_addr = compiled.engine.get_global_value_address("stack_array")
    stack_view = (ctypes.c_int64 * STACK_SIZE).from_address(stack_addr)
    return execute_stack_scenario(compiled, stack_view)


def run_pointer_global_scenario(compiled: CompiledModule) -> tuple[list[str], int]:
    assert compiled.bind_external_stack_addr is not None
    bind_external_stack = call_void_i64_i64(compiled.bind_external_stack_addr)
    stack_view = (ctypes.c_int64 * STACK_SIZE)()
    sp_view = ctypes.c_int32(STACK_SIZE)
    bind_external_stack(ctypes.addressof(stack_view), ctypes.addressof(sp_view))
    return execute_stack_scenario(compiled, stack_view)


def run_context_struct_scenario(compiled: CompiledModule) -> tuple[list[str], int]:
    assert compiled.bind_stack_context_addr is not None
    bind_stack_context = call_void_i64_1(compiled.bind_stack_context_addr)
    ctx = StackContext()
    ctx.generation = 7
    ctx.sp = STACK_SIZE
    bind_stack_context(ctypes.addressof(ctx))
    return execute_stack_scenario(compiled, ctx.stack)


def print_trace(title: str, trace: list[str]) -> None:
    print(f"== {title} ==")
    for line in trace:
        print(line)
    print()


def main() -> None:
    configure_llvm()

    raw_context = compile_module("raw context-struct", build_raw_context_module())
    py_global = compile_module(
        "pythonic module-global",
        build_pythonic_module("context_struct_stack_storage_global", ModuleGlobalStackEmitter),
    )
    py_pointer = compile_module(
        "pythonic pointer-global",
        build_pythonic_module("context_struct_stack_storage_pointer", PointerGlobalStackEmitter),
    )
    py_context = compile_module(
        "pythonic context-struct",
        build_pythonic_module("context_struct_stack_storage_context", ContextStructStackEmitter),
    )

    print("== Question ==")
    print("How do you factor stack operations into one abstract layer while concrete emitters supply the IR pointers for module globals, pointer globals, or context-struct fields?")
    print()

    print("== Raw Context-Struct IR ==")
    print(raw_context.llvm_ir.rstrip())
    print()
    print("== Pythonic Module-Global IR ==")
    print(py_global.llvm_ir.rstrip())
    print()
    print("== Pythonic Pointer-Global IR ==")
    print(py_pointer.llvm_ir.rstrip())
    print()
    print("== Pythonic Context-Struct IR ==")
    print(py_context.llvm_ir.rstrip())
    print()

    raw_trace, raw_popped = run_context_struct_scenario(raw_context)
    global_trace, global_popped = run_global_scenario(py_global)
    pointer_trace, pointer_popped = run_pointer_global_scenario(py_pointer)
    context_trace, context_popped = run_context_struct_scenario(py_context)

    print_trace("Raw Context-Struct Stack Trace", raw_trace)
    print_trace("Pythonic Module-Global Stack Trace", global_trace)
    print_trace("Pythonic Pointer-Global Stack Trace", pointer_trace)
    print_trace("Pythonic Context-Struct Stack Trace", context_trace)

    print("== Comparison ==")
    print(f"raw context vs pythonic context traces match: {raw_trace == context_trace}")
    print(f"all provider traces match: {raw_trace == global_trace == pointer_trace == context_trace}")
    print(f"all popped values match: {raw_popped == global_popped == pointer_popped == context_popped}")
    print()

    print("== Takeaway ==")
    print("Make the stack operations themselves the reusable layer, and make concrete emitters supply only the IR needed to reach the stack base and stack-pointer cell.")
    print("Once that boundary is explicit, the same push/pop/dup/swap/over logic can target module globals, pointer globals, or fields inside a runtime context struct.")


if __name__ == "__main__":
    main()
