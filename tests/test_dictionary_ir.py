from __future__ import annotations

import ctypes

from llvmlite import binding, ir

from fythvm.codegen import StructHandle, compile_ir_module, configure_llvm
from fythvm.dictionary import (
    CurrentWordIR,
    DictionaryIR,
    DictionaryMemory,
    DictionaryRuntime,
    NULL_INDEX,
    RunCurrentXtIR,
)
from fythvm.dictionary.layout import dictionary_memory_handle


I8 = ir.IntType(8)
I32 = ir.IntType(32)


class TinyCurrentWordState(ctypes.Structure):
    _fields_ = [
        ("dictionary_memory", ctypes.POINTER(DictionaryMemory)),
        ("current_xt", ctypes.c_int32),
    ]


def _byte_global(module: ir.Module, name: str, payload: bytes) -> ir.GlobalVariable:
    global_var = ir.GlobalVariable(module, ir.ArrayType(I8, len(payload)), name=name)
    global_var.initializer = ir.Constant(global_var.type.pointee, bytearray(payload))
    global_var.global_constant = True
    return global_var


def _byte_ptr(builder: ir.IRBuilder, global_var: ir.GlobalVariable, name: str) -> ir.Value:
    return builder.bitcast(global_var, I8.as_pointer(), name=name)


def test_dictionary_ir_create_word_matches_runtime_layout() -> None:
    configure_llvm()

    module = ir.Module(name="dictionary_ir_create_word")
    module.triple = binding.get_default_triple()
    dup_name = _byte_global(module, "dup_name", b"dup\x00")
    emit_name = _byte_global(module, "emit_name", b"emit")

    fn = ir.Function(module, ir.FunctionType(I32, [dictionary_memory_handle().ir_type.as_pointer()]), name="seed")
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    dictionary = DictionaryIR(builder, fn.args[0])
    dictionary.create_word(
        _byte_ptr(builder, dup_name, "dup_ptr"),
        I32(3),
        handler_id=I32(10),
        data_values=(I32(111),),
    )
    last_index = dictionary.create_word(
        _byte_ptr(builder, emit_name, "emit_ptr"),
        I32(4),
        handler_id=I32(20),
        immediate=True,
        data_values=(I32(222), I32(333)),
    )
    builder.ret(last_index)

    compiled = compile_ir_module(module)
    seed = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.POINTER(DictionaryMemory))(compiled.function_address("seed"))

    memory = DictionaryMemory()
    runtime = DictionaryRuntime(memory)
    last_index = seed(ctypes.byref(memory))
    assert last_index == 5

    words = list(runtime.iter_words())
    assert [word.name_bytes for word in words] == [b"emit", b"dup"]
    assert words[0].handler_id == 20
    assert words[0].immediate is True
    assert words[0].read_data_cells(2) == [222, 333]
    assert words[1].handler_id == 10
    assert words[1].hidden is False
    assert words[1].read_data_cells(1) == [111]
    assert memory.registers.latest == 5
    assert memory.registers.here == 9


def test_dictionary_ir_find_word_is_newest_first_and_skips_hidden() -> None:
    configure_llvm()

    runtime = DictionaryRuntime()
    older_dup = runtime.create_word("dup", handler_id=1)
    runtime.create_word("secret", handler_id=2, hidden=True)
    newer_dup = runtime.create_word("dup", handler_id=3, immediate=True)
    runtime.create_word("emit", handler_id=4)

    module = ir.Module(name="dictionary_ir_find_word")
    module.triple = binding.get_default_triple()
    fn = ir.Function(
        module,
        ir.FunctionType(I32, [dictionary_memory_handle().ir_type.as_pointer(), I8.as_pointer(), I32]),
        name="find_word",
    )
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    dictionary = DictionaryIR(builder, fn.args[0])
    found_index = dictionary.find_word(fn.args[1], fn.args[2])
    builder.ret(found_index)

    compiled = compile_ir_module(module)
    find_word = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.POINTER(DictionaryMemory),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int32,
    )(compiled.function_address("find_word"))

    dup_query = (ctypes.c_uint8 * 4)(*b"dup\x00")
    secret_query = (ctypes.c_uint8 * 8)(*b"secret\x00\x00")
    missing_query = (ctypes.c_uint8 * 8)(*b"nosuch\x00\x00")

    found_dup = find_word(ctypes.byref(runtime.memory), dup_query, 3)
    found_secret = find_word(ctypes.byref(runtime.memory), secret_query, 6)
    found_missing = find_word(ctypes.byref(runtime.memory), missing_query, 6)

    assert found_dup == newer_dup.index
    assert found_dup != older_dup.index
    assert found_secret == NULL_INDEX
    assert found_missing == NULL_INDEX


def test_dictionary_ir_resolves_thread_cells_pointer_from_cfa() -> None:
    configure_llvm()

    runtime = DictionaryRuntime()
    word = runtime.create_word("sum23", handler_id=17, data=(101, 202, 303))

    module = ir.Module(name="dictionary_ir_thread_cells_ptr_for_cfa")
    module.triple = binding.get_default_triple()
    fn = ir.Function(
        module,
        ir.FunctionType(I32, [dictionary_memory_handle().ir_type.as_pointer(), I32]),
        name="read_first_thread_cell",
    )
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    dictionary = DictionaryIR(builder, fn.args[0])
    thread_cells_ptr = dictionary.thread_cells_ptr_for_cfa(fn.args[1], name="thread_cells_ptr")
    builder.ret(builder.load(thread_cells_ptr, name="first_thread_cell"))

    compiled = compile_ir_module(module)
    read_first_thread_cell = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.POINTER(DictionaryMemory),
        ctypes.c_int32,
    )(compiled.function_address("read_first_thread_cell"))

    assert read_first_thread_cell(ctypes.byref(runtime.memory), word.cfa_index) == 101


def test_dictionary_ir_find_word_by_cfa_prefers_real_dictionary_word() -> None:
    configure_llvm()

    runtime = DictionaryRuntime()
    newer = runtime.create_word("sum23", handler_id=76)
    older = runtime.create_word("helper", handler_id=15)

    module = ir.Module(name="dictionary_ir_find_word_by_cfa")
    module.triple = binding.get_default_triple()
    fn = ir.Function(
        module,
        ir.FunctionType(I32, [dictionary_memory_handle().ir_type.as_pointer(), I32]),
        name="find_word_by_cfa",
    )
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    dictionary = DictionaryIR(builder, fn.args[0])
    builder.ret(dictionary.find_word_by_cfa(fn.args[1]))

    compiled = compile_ir_module(module)
    find_word_by_cfa = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.POINTER(DictionaryMemory),
        ctypes.c_int32,
    )(compiled.function_address("find_word_by_cfa"))

    assert find_word_by_cfa(ctypes.byref(runtime.memory), older.cfa_index) == older.index
    assert find_word_by_cfa(ctypes.byref(runtime.memory), newer.cfa_index) == newer.index
    assert find_word_by_cfa(ctypes.byref(runtime.memory), 999) == NULL_INDEX


def test_current_word_ir_resolves_handler_id_for_primitive_and_custom_xt() -> None:
    configure_llvm()

    runtime = DictionaryRuntime()
    custom = runtime.create_word("sum23", handler_id=76)
    state_handle = StructHandle.from_ctypes("tiny current word state", TinyCurrentWordState)

    module = ir.Module(name="current_word_ir_resolved_handler")
    module.triple = binding.get_default_triple()
    fn = ir.Function(module, ir.FunctionType(I32, [state_handle.ir_type.as_pointer()]), name="resolve_handler_id")
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    state = state_handle.bind(builder, fn.args[0])
    dispatch_custom = fn.append_basic_block("dispatch_custom")
    dispatch_primitive = fn.append_basic_block("dispatch_primitive")
    dispatch_resolved = fn.append_basic_block("dispatch_resolved")

    current_word = CurrentWordIR.resolve_from_state(
        builder=builder,
        state=state,
        dispatch_custom_block=dispatch_custom,
        dispatch_primitive_block=dispatch_primitive,
        dispatch_resolved_block=dispatch_resolved,
        name_prefix="test_current_word",
    )

    builder.position_at_end(dispatch_resolved)
    builder.ret(current_word.resolved_handler_id)

    compiled = compile_ir_module(module)
    resolve_handler_id = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.POINTER(TinyCurrentWordState),
    )(compiled.function_address("resolve_handler_id"))

    state = TinyCurrentWordState(ctypes.pointer(runtime.memory), custom.cfa_index)
    assert resolve_handler_id(ctypes.byref(state)) == 76

    state.current_xt = 15
    assert resolve_handler_id(ctypes.byref(state)) == 15


def test_current_word_ir_resolves_thread_ref_from_cfa_and_length_table() -> None:
    configure_llvm()

    runtime = DictionaryRuntime()
    word = runtime.create_word("sum23", handler_id=76, data=(101, 202, 303))
    thread_lengths = (ctypes.c_int32 * 256)()
    thread_lengths[word.cfa_index] = 3
    state_handle = StructHandle.from_ctypes("tiny current word state", TinyCurrentWordState)

    module = ir.Module(name="current_word_ir_thread_ref")
    module.triple = binding.get_default_triple()
    fn = ir.Function(
        module,
        ir.FunctionType(I32, [state_handle.ir_type.as_pointer(), I32.as_pointer()]),
        name="read_thread_signature",
    )
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    state = state_handle.bind(builder, fn.args[0])
    dispatch_custom = fn.append_basic_block("dispatch_custom")
    dispatch_primitive = fn.append_basic_block("dispatch_primitive")
    dispatch_resolved = fn.append_basic_block("dispatch_resolved")

    current_word = CurrentWordIR.resolve_from_state(
        builder=builder,
        state=state,
        dispatch_custom_block=dispatch_custom,
        dispatch_primitive_block=dispatch_primitive,
        dispatch_resolved_block=dispatch_resolved,
        name_prefix="test_current_word",
    )

    builder.position_at_end(dispatch_resolved)
    thread_ref = current_word.thread_ref(fn.args[1], name_prefix="current_word")
    first_cell = builder.load(thread_ref.cells, name="first_cell")
    signature = builder.add(first_cell, builder.mul(thread_ref.length, I32(1000)), name="thread_signature")
    builder.ret(signature)

    compiled = compile_ir_module(module)
    read_thread_signature = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.POINTER(TinyCurrentWordState),
        ctypes.POINTER(ctypes.c_int32),
    )(compiled.function_address("read_thread_signature"))

    state = TinyCurrentWordState(ctypes.pointer(runtime.memory), word.cfa_index)
    assert read_thread_signature(ctypes.byref(state), thread_lengths) == 3101


def test_run_current_xt_ir_resolves_installed_xt_through_shared_center() -> None:
    configure_llvm()

    runtime = DictionaryRuntime()
    custom = runtime.create_word("sum23", handler_id=76)
    state_handle = StructHandle.from_ctypes("tiny current xt state", TinyCurrentWordState)

    module = ir.Module(name="run_current_xt_ir")
    module.triple = binding.get_default_triple()
    fn = ir.Function(module, ir.FunctionType(I32, [state_handle.ir_type.as_pointer()]), name="run_current_xt")
    builder = ir.IRBuilder(fn.append_basic_block("entry"))
    state = state_handle.bind(builder, fn.args[0])
    dispatch_current = fn.append_basic_block("dispatch_current_word")
    dispatch_custom = fn.append_basic_block("dispatch_custom")
    dispatch_primitive = fn.append_basic_block("dispatch_primitive")
    dispatch_resolved = fn.append_basic_block("dispatch_resolved")
    builder.branch(dispatch_current)

    run_current_xt = RunCurrentXtIR.resolve_from_state(
        builder=builder,
        state=state,
        dispatch_current_block=dispatch_current,
        dispatch_custom_block=dispatch_custom,
        dispatch_primitive_block=dispatch_primitive,
        dispatch_resolved_block=dispatch_resolved,
        name_prefix="run_current_xt",
    )

    builder.position_at_end(dispatch_resolved)
    builder.ret(run_current_xt.resolved_handler_id)

    compiled = compile_ir_module(module)
    run_current_xt_cfunc = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.POINTER(TinyCurrentWordState),
    )(compiled.function_address("run_current_xt"))

    state = TinyCurrentWordState(ctypes.pointer(runtime.memory), custom.cfa_index)
    assert run_current_xt_cfunc(ctypes.byref(state)) == 76

    state.current_xt = 15
    assert run_current_xt_cfunc(ctypes.byref(state)) == 15
