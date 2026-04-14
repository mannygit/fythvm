"""Demonstrate a tiny JITed downward-growing stack."""

from __future__ import annotations

import ctypes

from llvmlite import binding, ir


STACK_SIZE = 8
I32 = ir.IntType(32)
I64 = ir.IntType(64)


def ensure_llvm_initialized() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def build_module() -> ir.Module:
    module = ir.Module(name="jit_stack_operations")
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


def logical_stack(array: ctypes.Array[ctypes.c_int64], sp: int) -> list[int]:
    return list(reversed(array[sp:STACK_SIZE]))


def main() -> None:
    ensure_llvm_initialized()
    module = build_module()
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    reset_stack = ctypes.CFUNCTYPE(None)(engine.get_function_address("reset_stack"))
    get_sp = ctypes.CFUNCTYPE(ctypes.c_int32)(engine.get_function_address("get_sp"))
    push = ctypes.CFUNCTYPE(None, ctypes.c_int64)(engine.get_function_address("push"))
    pop = ctypes.CFUNCTYPE(ctypes.c_int64)(engine.get_function_address("pop"))
    dup = ctypes.CFUNCTYPE(None)(engine.get_function_address("dup"))
    swap = ctypes.CFUNCTYPE(None)(engine.get_function_address("swap"))
    over = ctypes.CFUNCTYPE(None)(engine.get_function_address("over"))

    stack_addr = engine.get_global_value_address("stack_array")
    stack_view = (ctypes.c_int64 * STACK_SIZE).from_address(stack_addr)

    def snapshot(label: str) -> None:
        sp = int(get_sp())
        print(f"{label}: sp={sp}, logical_stack={logical_stack(stack_view, sp)}")

    print("== Question ==")
    print("What is the smallest useful downward-growing JITed stack pattern?")
    print()
    print("== Generated IR ==")
    print(llvm_ir.rstrip())
    print()
    print("== Stack Trace ==")
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
    print(f"pop() -> {popped}")
    snapshot("after pop")
    print()
    print("== Takeaway ==")
    print("Keep both the backing memory view and the logical stack view visible when exploring stack runtimes.")


if __name__ == "__main__":
    main()
