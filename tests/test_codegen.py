"""Tests for promoted code-generation primitives."""

from __future__ import annotations

import ctypes

from llvmlite import binding, ir

from fythvm.codegen import ContextStructStackAccess, Join, SharedExit, compile_ir_module, configure_llvm


I1 = ir.IntType(1)
I16 = ir.IntType(16)
I32 = ir.IntType(32)
I64 = ir.IntType(64)


class TinyStackContext(ctypes.Structure):
    _fields_ = [
        ("stack", ctypes.c_int16 * 4),
        ("sp", ctypes.c_int32),
    ]


def test_shared_exit_merges_status_and_value() -> None:
    configure_llvm()

    module = ir.Module(name="shared_exit_test")
    module.triple = binding.get_default_triple()
    fn = ir.Function(module, ir.FunctionType(I32, [I1, I16.as_pointer()]), name="choose")
    cond, out_ptr = fn.args

    entry = fn.append_basic_block("entry")
    true_block = fn.append_basic_block("true")
    false_block = fn.append_basic_block("false")

    builder = ir.IRBuilder(entry)
    builder.cbranch(cond, true_block, false_block)

    exit_pair = SharedExit(fn, [("status", I32), ("value", I16)])

    builder.position_at_end(true_block)
    exit_pair.remember(builder, I32(7), I16(111))

    builder.position_at_end(false_block)
    exit_pair.remember(builder, I32(8), I16(222))

    status, value = exit_pair.finish()
    exit_pair.builder.store(value, out_ptr)
    exit_pair.builder.ret(status)

    compiled = compile_ir_module(module)
    choose = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_bool, ctypes.POINTER(ctypes.c_int16))(
        compiled.function_address("choose")
    )

    out = ctypes.c_int16(0)
    assert choose(True, ctypes.byref(out)) == 7
    assert out.value == 111
    assert choose(False, ctypes.byref(out)) == 8
    assert out.value == 222


def test_join_treats_merge_block_as_block_parameters() -> None:
    configure_llvm()

    module = ir.Module(name="join_test")
    module.triple = binding.get_default_triple()
    fn = ir.Function(module, ir.FunctionType(I64, [I1]), name="join_fn")

    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    then_block = fn.append_basic_block("then")
    else_block = fn.append_basic_block("else")
    merge_block = fn.append_basic_block("merge")
    builder.cbranch(fn.args[0], then_block, else_block)

    join = Join(builder, merge_block, [("x", I64), ("y", I64)])

    builder.position_at_end(then_block)
    join.branch_from_here(builder, I64(10), I64(20))

    builder.position_at_end(else_block)
    join.branch_from_here(builder, I64(100), I64(200))

    with join as (x, y):
        total = builder.add(x, y, name="total")
        builder.ret(total)

    compiled = compile_ir_module(module)
    join_fn = ctypes.CFUNCTYPE(ctypes.c_longlong, ctypes.c_bool)(compiled.function_address("join_fn"))
    assert join_fn(True) == 30
    assert join_fn(False) == 300


def test_context_struct_stack_access_reaches_stack_and_sp_fields() -> None:
    configure_llvm()

    ctx_type = ir.LiteralStructType([ir.ArrayType(I16, 4), I32])
    module = ir.Module(name="stack_access_test")
    module.triple = binding.get_default_triple()

    seed_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), [ctx_type.as_pointer(), I16]), name="seed")
    stack = ContextStructStackAccess(seed_fn.args[0])
    builder = ir.IRBuilder(seed_fn.append_basic_block("entry"))
    current_sp = stack.load_sp(builder)
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(seed_fn.args[1], stack.slot(builder, new_sp))
    stack.store_sp(builder, new_sp)
    builder.ret_void()

    peek_fn = ir.Function(module, ir.FunctionType(I16, [ctx_type.as_pointer()]), name="peek")
    stack = ContextStructStackAccess(peek_fn.args[0])
    builder = ir.IRBuilder(peek_fn.append_basic_block("entry"))
    builder.ret(builder.load(stack.slot(builder, stack.load_sp(builder)), name="value"))

    compiled = compile_ir_module(module)
    seed = ctypes.CFUNCTYPE(None, ctypes.POINTER(TinyStackContext), ctypes.c_int16)(compiled.function_address("seed"))
    peek = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.POINTER(TinyStackContext))(compiled.function_address("peek"))

    ctx = TinyStackContext()
    ctx.sp = 4
    seed(ctypes.byref(ctx), 12)
    assert ctx.sp == 3
    assert peek(ctypes.byref(ctx)) == 12
