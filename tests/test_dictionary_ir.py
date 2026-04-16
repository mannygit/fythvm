from __future__ import annotations

import ctypes

from llvmlite import binding, ir

from fythvm.codegen import compile_ir_module, configure_llvm
from fythvm.dictionary import DictionaryIR, DictionaryMemory, DictionaryRuntime, NULL_INDEX
from fythvm.dictionary.layout import dictionary_memory_handle


I8 = ir.IntType(8)
I32 = ir.IntType(32)


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
