"""Tests for promoted code-generation primitives."""

from __future__ import annotations

import ctypes

from llvmlite import binding, ir

from fythvm.codegen import (
    BitField,
    BoundStructView,
    CurrentWordThreadIR,
    ContextStructStackAccess,
    Join,
    ParamLoop,
    SharedExit,
    StructField,
    StructHandle,
    StructViewStackAccess,
    SwitchDispatcher,
    ThreadCursorIR,
    ThreadJumpIR,
    compare_aligned_i32_regions,
    compile_ir_module,
    configure_llvm,
)
from fythvm.dictionary.layout import code_field_handle


I1 = ir.IntType(1)
I16 = ir.IntType(16)
I32 = ir.IntType(32)
I64 = ir.IntType(64)


class TinyStackContext(ctypes.Structure):
    _fields_ = [
        ("stack", ctypes.c_int16 * 4),
        ("sp", ctypes.c_int32),
    ]


class TinyStackView(BoundStructView):
    stack = StructField(0)
    sp = StructField(1)


class TinyThreadState(ctypes.Structure):
    _fields_ = [
        ("ip", ctypes.c_int32),
        ("thread_cells", ctypes.POINTER(ctypes.c_int32)),
        ("thread_length", ctypes.c_int32),
        ("current_word_thread_cells", ctypes.POINTER(ctypes.c_int32)),
        ("current_word_thread_length", ctypes.c_int32),
    ]


class PairView(BoundStructView):
    first = StructField(0)
    second = StructField(1)


class OuterView(BoundStructView):
    pair = StructField(0)
    total = StructField(1)


class FlagsView(BoundStructView):
    cell = StructField(0)
    low = BitField(0, 0, 3)
    high = BitField(0, 3, 5)


class AlternatePairView(BoundStructView):
    left = StructField(0)
    right = StructField(1)


class ReifiedContext(ctypes.Structure):
    _fields_ = [
        ("values", ctypes.c_int16 * 4),
        ("sp", ctypes.c_int32),
    ]


class ReifiedContextView(BoundStructView):
    values = StructField(0)
    sp = StructField(1)


class PaddedScalarContext(ctypes.Structure):
    _fields_ = [
        ("head", ctypes.c_int32),
        ("wide", ctypes.c_longlong),
        ("tail", ctypes.c_int32),
    ]


class GeneratedFlags(ctypes.Structure):
    _fields_ = [
        ("low", ctypes.c_ubyte, 3),
        ("high", ctypes.c_ubyte, 5),
        ("wide", ctypes.c_ushort),
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


def test_struct_handle_supports_named_field_access() -> None:
    configure_llvm()

    module = ir.Module(name="struct_handle_fields")
    module.triple = binding.get_default_triple()
    pair = StructHandle.literal("pair", I32, I64, view_type=PairView)
    pair_global = pair.define_global(module, "pair_data", I32(7), I64(33))

    fn = ir.Function(module, ir.FunctionType(I64, []), name="sum_pair")
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    view = pair.bind(builder, pair_global)
    total = builder.add(builder.zext(view.first.load(), I64), view.second.load(), name="sum")
    builder.ret(total)

    compiled = compile_ir_module(module)
    sum_pair = ctypes.CFUNCTYPE(ctypes.c_longlong)(compiled.function_address("sum_pair"))
    assert sum_pair() == 40


def test_struct_handle_can_reify_fixed_ctypes_layout() -> None:
    configure_llvm()

    module = ir.Module(name="ctypes_reified_struct_handle")
    module.triple = binding.get_default_triple()
    handle = StructHandle.from_ctypes("reified context", ReifiedContext, view_type=ReifiedContextView)

    expected_type = ir.LiteralStructType([ir.ArrayType(I16, 4), I32])
    assert str(handle.ir_type) == str(expected_type)

    instance = ReifiedContext((1, 2, 3, 4), 3)
    global_var = handle.define_global_from_ctypes(module, "ctx_data", instance)

    fn = ir.Function(module, ir.FunctionType(I32, []), name="read_sp")
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    view = handle.bind(builder, global_var)
    builder.ret(view.sp.load())

    compiled = compile_ir_module(module)
    read_sp = ctypes.CFUNCTYPE(ctypes.c_int32)(compiled.function_address("read_sp"))
    assert read_sp() == 3


def test_struct_handle_generated_view_tracks_ctypes_padding() -> None:
    configure_llvm()

    module = ir.Module(name="generated_view_tracks_padding")
    module.triple = binding.get_default_triple()
    handle = StructHandle.from_ctypes("padded scalar context", PaddedScalarContext)

    assert handle.view_source is not None
    assert "wide = StructField(2)" in handle.view_source
    assert "tail = StructField(3)" in handle.view_source

    instance = PaddedScalarContext(7, 123456789, 99)
    global_var = handle.define_global_from_ctypes(module, "ctx_data", instance)

    fn = ir.Function(module, ir.FunctionType(I32, []), name="read_tail")
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    view = handle.bind(builder, global_var)
    builder.ret(view.tail.load())

    compiled = compile_ir_module(module)
    read_tail = ctypes.CFUNCTYPE(ctypes.c_int32)(compiled.function_address("read_tail"))
    assert read_tail() == 99


def test_struct_handle_generated_view_exposes_logical_bitfields() -> None:
    configure_llvm()

    module = ir.Module(name="generated_view_bitfields")
    module.triple = binding.get_default_triple()
    handle = StructHandle.from_ctypes("generated flags", GeneratedFlags)

    assert handle.view_source is not None
    assert "low = BitField(0, 0, 3)" in handle.view_source
    assert "high = BitField(0, 3, 5)" in handle.view_source
    assert "wide = StructField(2)" in handle.view_source

    flags_global = handle.define_global_from_ctypes(module, "flags_data", GeneratedFlags(0, 0, 0))

    set_fields = ir.Function(module, ir.FunctionType(I32, []), name="set_generated_fields")
    builder = ir.IRBuilder(set_fields.append_basic_block("entry"))
    view = handle.bind(builder, flags_global)
    view.low.store(ir.IntType(3)(5))
    view.high.store(ir.IntType(5)(17))
    builder.ret(builder.zext(view.wide.load(), I32))

    read_sum = ir.Function(module, ir.FunctionType(I32, []), name="read_generated_sum")
    builder = ir.IRBuilder(read_sum.append_basic_block("entry"))
    view = handle.bind(builder, flags_global)
    low = builder.zext(view.low.load(), I32)
    high = builder.zext(view.high.load(), I32)
    builder.ret(builder.add(low, high))

    compiled = compile_ir_module(module)
    set_fields_fn = ctypes.CFUNCTYPE(ctypes.c_int32)(compiled.function_address("set_generated_fields"))
    read_sum_fn = ctypes.CFUNCTYPE(ctypes.c_int32)(compiled.function_address("read_generated_sum"))
    assert set_fields_fn() == 0
    assert read_sum_fn() == 22


def test_bound_struct_field_can_bind_nested_struct_view() -> None:
    configure_llvm()

    module = ir.Module(name="nested_struct_handle")
    module.triple = binding.get_default_triple()
    pair = StructHandle.identified("pair", "TestPair", I32, I32, view_type=PairView)
    outer = StructHandle.literal("outer", pair.ir_type, I32, view_type=OuterView)
    outer_global = outer.define_global(module, "outer_data", pair.constant(I32(4), I32(5)), I32(20))

    fn = ir.Function(module, ir.FunctionType(I64, []), name="sum_nested")
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    view = outer.bind(builder, outer_global)
    pair_view = view.pair.bind(pair)
    subtotal = builder.add(pair_view.first.load(), pair_view.second.load(), name="pair_sum")
    total = builder.add(subtotal, view.total.load(), name="total")
    builder.ret(builder.zext(total, I64))

    compiled = compile_ir_module(module)
    sum_nested = ctypes.CFUNCTYPE(ctypes.c_longlong)(compiled.function_address("sum_nested"))
    assert sum_nested() == 29


def test_identified_struct_handles_are_registry_cached_per_python_projection() -> None:
    pair_a = StructHandle.identified("pair", "RegistryPair", I32, I32, view_type=PairView)
    pair_b = StructHandle.identified("pair", "RegistryPair", I32, I32, view_type=PairView)
    pair_c = StructHandle.identified("pair", "RegistryPair", I32, I32, view_type=AlternatePairView)

    assert pair_a is pair_b
    assert pair_a is not pair_c
    assert pair_a.ir_type is pair_c.ir_type


def test_bitfield_descriptor_loads_and_stores_logical_fields() -> None:
    configure_llvm()

    module = ir.Module(name="bitfield_descriptor")
    module.triple = binding.get_default_triple()
    flags = StructHandle.literal("flags", I32, view_type=FlagsView)
    flags_global = flags.define_global(module, "flags_data", I32(0))

    set_fields = ir.Function(module, ir.FunctionType(I32, []), name="set_fields")
    builder = ir.IRBuilder(set_fields.append_basic_block("entry"))
    view = flags.bind(builder, flags_global)
    view.low.store(ir.IntType(3)(5))
    view.high.store(ir.IntType(5)(17))
    builder.ret(view.cell.load())

    read_sum = ir.Function(module, ir.FunctionType(I32, []), name="read_sum")
    builder = ir.IRBuilder(read_sum.append_basic_block("entry"))
    view = flags.bind(builder, flags_global)
    low = builder.zext(view.low.load(), I32)
    high = builder.zext(view.high.load(), I32)
    builder.ret(builder.add(low, high))

    compiled = compile_ir_module(module)
    set_fields_fn = ctypes.CFUNCTYPE(ctypes.c_int32)(compiled.function_address("set_fields"))
    read_sum_fn = ctypes.CFUNCTYPE(ctypes.c_int32)(compiled.function_address("read_sum"))
    assert set_fields_fn() == (17 << 3) | 5
    assert read_sum_fn() == 22


def test_generated_dictionary_code_field_view_exposes_logical_bitfields() -> None:
    configure_llvm()

    module = ir.Module(name="generated_code_field_view")
    module.triple = binding.get_default_triple()
    handle = code_field_handle()
    code_field_global = handle.define_global(module, "code_field_data", I32(0))

    set_fields = ir.Function(module, ir.FunctionType(I32, []), name="set_code_fields")
    builder = ir.IRBuilder(set_fields.append_basic_block("entry"))
    view = handle.bind(builder, code_field_global)
    view.handler_id.store(ir.IntType(7)(42))
    view.hidden.store(ir.IntType(1)(1))
    view.name_length.store(ir.IntType(5)(7))
    view.immediate.store(ir.IntType(1)(1))
    builder.ret(view.cell.load())

    read_fields = ir.Function(module, ir.FunctionType(I32, []), name="read_code_fields")
    builder = ir.IRBuilder(read_fields.append_basic_block("entry"))
    view = handle.bind(builder, code_field_global)
    total = builder.zext(view.handler_id.load(), I32)
    total = builder.add(total, builder.zext(view.hidden.load(), I32))
    total = builder.add(total, builder.zext(view.name_length.load(), I32))
    total = builder.add(total, builder.zext(view.immediate.load(), I32))
    builder.ret(total)

    compiled = compile_ir_module(module)
    set_fields_fn = ctypes.CFUNCTYPE(ctypes.c_int32)(compiled.function_address("set_code_fields"))
    read_fields_fn = ctypes.CFUNCTYPE(ctypes.c_int32)(compiled.function_address("read_code_fields"))
    assert set_fields_fn() == (42 | (1 << 7) | (7 << 8) | (1 << 13))
    assert read_fields_fn() == 42 + 1 + 7 + 1


def test_compare_aligned_i32_regions_compares_padded_name_bytes_word_at_a_time() -> None:
    configure_llvm()

    module = ir.Module(name="aligned_i32_region_compare")
    module.triple = binding.get_default_triple()
    fn = ir.Function(module, ir.FunctionType(I1, [ir.IntType(8).as_pointer(), ir.IntType(8).as_pointer(), I32]), name="eq")

    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    result = compare_aligned_i32_regions(builder, fn.args[0], fn.args[1], fn.args[2], name="name_eq")
    builder.ret(result)

    compiled = compile_ir_module(module)
    eq = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8), ctypes.c_int32)(
        compiled.function_address("eq")
    )

    same_a = (ctypes.c_uint8 * 8)(*b"dup\x00swap")
    same_b = (ctypes.c_uint8 * 8)(*b"dup\x00swap")
    diff_second_word = (ctypes.c_uint8 * 8)(*b"dup\x00swop")
    diff_first_word = (ctypes.c_uint8 * 8)(*b"dropswap")
    empty_a = (ctypes.c_uint8 * 4)(0, 0, 0, 0)
    empty_b = (ctypes.c_uint8 * 4)(0, 0, 0, 0)

    assert eq(same_a, same_b, 8) is True
    assert eq(same_a, diff_second_word, 8) is False
    assert eq(same_a, diff_first_word, 4) is False
    assert eq(empty_a, empty_b, 0) is True


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
    stack = ContextStructStackAccess(seed_fn.args[0]).bind(ir.IRBuilder(seed_fn.append_basic_block("entry")))
    current_sp = stack.load_sp()
    new_sp = stack.builder.sub(current_sp, I32(1), name="new_sp")
    stack.builder.store(seed_fn.args[1], stack.slot(new_sp))
    stack.store_sp(new_sp)
    stack.builder.ret_void()

    peek_fn = ir.Function(module, ir.FunctionType(I16, [ctx_type.as_pointer()]), name="peek")
    stack = ContextStructStackAccess(peek_fn.args[0]).bind(ir.IRBuilder(peek_fn.append_basic_block("entry")))
    stack.builder.ret(stack.peek(name="value"))

    compiled = compile_ir_module(module)
    seed = ctypes.CFUNCTYPE(None, ctypes.POINTER(TinyStackContext), ctypes.c_int16)(compiled.function_address("seed"))
    peek = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.POINTER(TinyStackContext))(compiled.function_address("peek"))

    ctx = TinyStackContext()
    ctx.sp = 4
    seed(ctypes.byref(ctx), 12)
    assert ctx.sp == 3
    assert peek(ctypes.byref(ctx)) == 12


def test_struct_view_stack_access_supports_reset_push_pop2_and_peek() -> None:
    configure_llvm()

    ctx_handle = StructHandle.literal("tiny stack context", ir.ArrayType(I16, 4), I32, view_type=TinyStackView)
    module = ir.Module(name="stack_ops_test")
    module.triple = binding.get_default_triple()

    apply_fn = ir.Function(module, ir.FunctionType(I16, [ctx_handle.ir_type.as_pointer(), I16, I16]), name="apply_add")
    builder = ir.IRBuilder(apply_fn.append_basic_block("entry"))
    ctx = ctx_handle.bind(builder, apply_fn.args[0])
    stack = StructViewStackAccess(ctx).bind(builder)
    stack.reset(I32(4))
    stack.push(apply_fn.args[1], name="push_lhs_sp")
    stack.push(apply_fn.args[2], name="push_rhs_sp")
    operands = stack.pop2()
    result = stack.builder.add(operands.lhs, operands.rhs, name="sum")
    stack.builder.store(result, stack.slot(operands.result_index, name="result_ptr"))
    stack.store_sp(operands.result_index)
    stack.builder.ret(stack.peek(name="top"))

    compiled = compile_ir_module(module)
    apply_add = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.POINTER(TinyStackContext), ctypes.c_int16, ctypes.c_int16)(
        compiled.function_address("apply_add")
    )

    ctx = TinyStackContext()
    result = apply_add(ctypes.byref(ctx), 7, 5)
    assert result == 12
    assert ctx.sp == 3
    assert ctx.stack[3] == 12


def test_struct_view_stack_access_supports_binary_reduce() -> None:
    configure_llvm()

    ctx_handle = StructHandle.literal("tiny stack context", ir.ArrayType(I16, 4), I32, view_type=TinyStackView)
    module = ir.Module(name="stack_binary_reduce_test")
    module.triple = binding.get_default_triple()

    apply_fn = ir.Function(module, ir.FunctionType(I16, [ctx_handle.ir_type.as_pointer(), I16, I16]), name="apply_add")
    builder = ir.IRBuilder(apply_fn.append_basic_block("entry"))
    ctx = ctx_handle.bind(builder, apply_fn.args[0])
    stack = StructViewStackAccess(ctx).bind(builder)
    stack.reset(I32(4))
    stack.push(apply_fn.args[1], name="push_lhs_sp")
    stack.push(apply_fn.args[2], name="push_rhs_sp")
    stack.binary_reduce(
        lambda ir_builder, lhs, rhs: ir_builder.add(lhs, rhs, name="sum"),
        result_index_name="sum_index",
        result_ptr_name="sum_ptr",
    )
    builder.ret(stack.peek(name="top"))

    compiled = compile_ir_module(module)
    apply_add = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.POINTER(TinyStackContext), ctypes.c_int16, ctypes.c_int16)(
        compiled.function_address("apply_add")
    )

    ctx = TinyStackContext()
    result = apply_add(ctypes.byref(ctx), 7, 5)
    assert result == 12
    assert ctx.sp == 3
    assert ctx.stack[3] == 12


def test_struct_view_stack_access_supports_drop() -> None:
    configure_llvm()

    ctx_handle = StructHandle.literal("tiny stack context", ir.ArrayType(I16, 4), I32, view_type=TinyStackView)
    module = ir.Module(name="stack_drop_test")
    module.triple = binding.get_default_triple()

    apply_fn = ir.Function(module, ir.FunctionType(I32, [ctx_handle.ir_type.as_pointer(), I16]), name="apply_drop")
    builder = ir.IRBuilder(apply_fn.append_basic_block("entry"))
    ctx = ctx_handle.bind(builder, apply_fn.args[0])
    stack = StructViewStackAccess(ctx).bind(builder)
    stack.reset(I32(4))
    stack.push(apply_fn.args[1], name="push_value_sp")
    new_sp = stack.drop(name="drop_sp")
    builder.ret(new_sp)

    compiled = compile_ir_module(module)
    apply_drop = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(TinyStackContext), ctypes.c_int16)(
        compiled.function_address("apply_drop")
    )

    ctx = TinyStackContext()
    result = apply_drop(ctypes.byref(ctx), 7)
    assert result == 4
    assert ctx.sp == 4


def test_struct_view_stack_access_shape_predicates_follow_stack_capacity() -> None:
    configure_llvm()

    ctx_handle = StructHandle.literal("tiny stack context", ir.ArrayType(I16, 4), I32, view_type=TinyStackView)
    module = ir.Module(name="stack_shape_predicates")
    module.triple = binding.get_default_triple()

    encode_fn = ir.Function(module, ir.FunctionType(I32, [ctx_handle.ir_type.as_pointer()]), name="encode")
    builder = ir.IRBuilder(encode_fn.append_basic_block("entry"))
    ctx = ctx_handle.bind(builder, encode_fn.args[0])
    stack = StructViewStackAccess(ctx).bind(builder)

    has_room = stack.has_room(name="has_room")
    has_two = stack.has_at_least(2, name="has_two")
    has_one = stack.has_exactly(1, name="has_one")

    encoded = stack.builder.zext(has_room, I32, name="room_i32")
    encoded = stack.builder.or_(encoded, stack.builder.shl(stack.builder.zext(has_two, I32), I32(1)), name="room_two")
    encoded = stack.builder.or_(encoded, stack.builder.shl(stack.builder.zext(has_one, I32), I32(2)), name="all_bits")
    stack.builder.ret(encoded)

    compiled = compile_ir_module(module)
    encode = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(TinyStackContext))(compiled.function_address("encode"))

    ctx = TinyStackContext()
    ctx.sp = 4
    assert encode(ctypes.byref(ctx)) == 1

    ctx.sp = 2
    assert encode(ctypes.byref(ctx)) == 3

    ctx.sp = 3
    assert encode(ctypes.byref(ctx)) == 5


def test_thread_cursor_and_jump_follow_ctypes_reified_state() -> None:
    configure_llvm()

    state_handle = StructHandle.from_ctypes("tiny thread state", TinyThreadState)
    module = ir.Module(name="thread_cursor_and_jump_test")
    module.triple = binding.get_default_triple()

    apply_fn = ir.Function(module, ir.FunctionType(I32, [state_handle.ir_type.as_pointer()]), name="apply")
    builder = ir.IRBuilder(apply_fn.append_basic_block("entry"))
    state = state_handle.bind(builder, apply_fn.args[0])
    cursor = ThreadCursorIR(builder=builder, state=state)
    jump = ThreadJumpIR(builder=builder, state=state)
    offset = cursor.read_inline_cell()
    jump.branch_relative(offset)
    builder.ret(state.ip.load(name="final_ip"))

    compiled = compile_ir_module(module)
    apply = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(TinyThreadState))(compiled.function_address("apply"))

    thread = (ctypes.c_int32 * 3)(17, 2, 99)
    state = TinyThreadState()
    state.ip = 0
    state.thread_cells = ctypes.cast(thread, ctypes.POINTER(ctypes.c_int32))
    state.thread_length = 3

    result = apply(ctypes.byref(state))
    assert result == 3
    assert state.ip == 3


def test_current_word_thread_ref_reads_cells_and_length_from_reified_state() -> None:
    configure_llvm()

    state_handle = StructHandle.from_ctypes("tiny current word thread state", TinyThreadState)
    module = ir.Module(name="current_word_thread_ref_test")
    module.triple = binding.get_default_triple()

    apply_fn = ir.Function(module, ir.FunctionType(I32, [state_handle.ir_type.as_pointer()]), name="apply")
    builder = ir.IRBuilder(apply_fn.append_basic_block("entry"))
    state = state_handle.bind(builder, apply_fn.args[0])
    current_word_thread = CurrentWordThreadIR(state=state)
    thread = current_word_thread.ref()
    first_cell_ptr = builder.gep(thread.cells, [I32(0)], inbounds=True, name="first_cell_ptr")
    first_cell = builder.load(first_cell_ptr, name="first_cell")
    encoded = builder.add(first_cell, thread.length, name="encoded")
    builder.ret(encoded)

    compiled = compile_ir_module(module)
    apply = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(TinyThreadState))(compiled.function_address("apply"))

    current_word_thread = (ctypes.c_int32 * 3)(10, 20, 30)
    state = TinyThreadState()
    state.current_word_thread_cells = ctypes.cast(current_word_thread, ctypes.POINTER(ctypes.c_int32))
    state.current_word_thread_length = 3

    result = apply(ctypes.byref(state))
    assert result == 13
