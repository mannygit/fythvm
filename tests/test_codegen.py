"""Tests for promoted code-generation primitives."""

from __future__ import annotations

import ctypes

from llvmlite import binding, ir

from fythvm.codegen import (
    ContextStructStackAccess,
    Join,
    ParamLoop,
    SharedExit,
    SwitchDispatcher,
    compile_ir_module,
    configure_llvm,
)


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


def test_param_loop_carries_one_value_through_loop_header() -> None:
    configure_llvm()

    module = ir.Module(name="param_loop_one_value")
    module.triple = binding.get_default_triple()
    fn = ir.Function(module, ir.FunctionType(I64, []), name="count_to_three")

    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    loop = ParamLoop(builder, "count", [("i", I64)])
    loop.begin(I64(0))

    with loop.head() as (i,):
        done = builder.icmp_unsigned(">=", i, I64(3), name="done")
        builder.cbranch(done, loop.exit_block, loop.body_block)

    with loop.body():
        next_i = builder.add(i, I64(1), name="next_i")
        loop.continue_from_here(next_i)

    with loop.exit():
        builder.ret(i)

    compiled = compile_ir_module(module)
    count_to_three = ctypes.CFUNCTYPE(ctypes.c_longlong)(compiled.function_address("count_to_three"))
    assert count_to_three() == 3


def test_param_loop_carries_multiple_values_through_loop_header() -> None:
    configure_llvm()

    module = ir.Module(name="param_loop_two_values")
    module.triple = binding.get_default_triple()
    fn = ir.Function(module, ir.FunctionType(I64, []), name="sum_zero_to_two")

    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    loop = ParamLoop(builder, "sum_loop", [("i", I64), ("acc", I64)])
    loop.begin(I64(0), I64(0))

    with loop.head() as (i, acc):
        done = builder.icmp_unsigned(">=", i, I64(3), name="done")
        builder.cbranch(done, loop.exit_block, loop.body_block)

    with loop.body():
        next_acc = builder.add(acc, i, name="next_acc")
        next_i = builder.add(i, I64(1), name="next_i")
        loop.continue_from_here(next_i, next_acc)

    with loop.exit():
        builder.ret(acc)

    compiled = compile_ir_module(module)
    sum_zero_to_two = ctypes.CFUNCTYPE(ctypes.c_longlong)(compiled.function_address("sum_zero_to_two"))
    assert sum_zero_to_two() == 3


def test_switch_dispatcher_routes_cases_and_default() -> None:
    configure_llvm()

    module = ir.Module(name="switch_dispatcher_basic")
    module.triple = binding.get_default_triple()
    fn = ir.Function(module, ir.FunctionType(I64, [I16]), name="choose")

    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    default_block = fn.append_basic_block("default")
    dispatcher = SwitchDispatcher(builder, fn.args[0], default_block, name="dispatch")
    dispatcher.add_case(I16(1), "one", lambda current: current.ret(I64(11)))
    dispatcher.add_case(I16(2), "two", lambda current: current.ret(I64(22)))
    dispatcher.emit()

    builder.position_at_end(default_block)
    builder.ret(I64(99))

    compiled = compile_ir_module(module)
    choose = ctypes.CFUNCTYPE(ctypes.c_longlong, ctypes.c_short)(compiled.function_address("choose"))
    assert choose(1) == 11
    assert choose(2) == 22
    assert choose(7) == 99


def test_switch_dispatcher_case_callbacks_can_feed_shared_join() -> None:
    configure_llvm()

    module = ir.Module(name="switch_dispatcher_join")
    module.triple = binding.get_default_triple()
    fn = ir.Function(module, ir.FunctionType(I64, [I16]), name="dispatch_join")

    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    default_block = fn.append_basic_block("default")
    merge_block = fn.append_basic_block("merge")
    join = Join(builder, merge_block, [("value", I64)])
    dispatcher = SwitchDispatcher(builder, fn.args[0], default_block, name="dispatch")
    dispatcher.add_case(I16(1), "one", lambda current: join.branch_from_here(current, I64(7)))
    dispatcher.add_case(I16(2), "two", lambda current: join.branch_from_here(current, I64(8)))
    dispatcher.emit()

    builder.position_at_end(default_block)
    join.branch_from_here(builder, I64(9))

    with join as (value,):
        builder.ret(value)

    compiled = compile_ir_module(module)
    dispatch_join = ctypes.CFUNCTYPE(ctypes.c_longlong, ctypes.c_short)(compiled.function_address("dispatch_join"))
    assert dispatch_join(1) == 7
    assert dispatch_join(2) == 8
    assert dispatch_join(3) == 9


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
