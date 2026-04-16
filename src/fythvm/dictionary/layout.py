"""DO NOT EDIT: generated from `src/fythvm/dictionary/schema.py`.

Regenerate with:
  uv run python scripts/generate_dictionary_layout.py
"""

from __future__ import annotations

from llvmlite import ir

from ..codegen import BitField, BoundStructView, StructField, StructHandle

I8 = ir.IntType(8)
I16 = ir.IntType(16)
I32 = ir.IntType(32)
I64 = ir.IntType(64)


class CodeFieldView(BoundStructView):
    cell = StructField(0)
    handler_id = BitField(0, 0, 7)
    hidden = BitField(0, 7, 1)
    name_length = BitField(0, 8, 5)
    immediate = BitField(0, 13, 1)
    unused = BitField(0, 14, 18)


class WordPrefixView(BoundStructView):
    link = StructField(0)
    code_field = StructField(1)
    data_start = StructField(2)


class RegistersView(BoundStructView):
    here = StructField(0)
    latest = StructField(1)
    state = StructField(2)
    base = StructField(3)
    sp = StructField(4)
    rsp = StructField(5)


class DictionaryMemoryView(BoundStructView):
    registers = StructField(0)
    cells = StructField(1)
    data_stack = StructField(2)
    return_stack = StructField(3)


class StackBoundsView(BoundStructView):
    top = StructField(0)
    bottom = StructField(1)


class InterpreterRuntimeDataView(BoundStructView):
    memory_ptr = StructField(0)
    psp = StructField(1)
    rsp = StructField(2)
    tos = StructField(3)
    rtos = StructField(4)


def code_field_handle() -> StructHandle:
    return StructHandle.identified(
        'code field',
        'DictionaryCodeField',
        I32,
        view_type=CodeFieldView,
    )


def word_prefix_handle() -> StructHandle:
    return StructHandle.identified(
        'word prefix',
        'DictionaryWordPrefix',
        I32,
        code_field_handle().ir_type,
        ir.ArrayType(I32, 0),
        view_type=WordPrefixView,
    )


def registers_handle() -> StructHandle:
    return StructHandle.identified(
        'dictionary registers',
        'DictionaryRegisters',
        I32,
        I32,
        I32,
        I32,
        I32,
        I32,
        view_type=RegistersView,
    )


def dictionary_memory_handle() -> StructHandle:
    return StructHandle.identified(
        'dictionary memory',
        'DictionaryMemory',
        registers_handle().ir_type,
        ir.ArrayType(I32, 256),
        ir.ArrayType(I32, 16),
        ir.ArrayType(I32, 16),
        view_type=DictionaryMemoryView,
    )


def stack_bounds_handle() -> StructHandle:
    return StructHandle.identified(
        'stack bounds',
        'DictionaryStackBounds',
        I32.as_pointer(),
        I32.as_pointer(),
        view_type=StackBoundsView,
    )


def interpreter_runtime_handle() -> StructHandle:
    return StructHandle.identified(
        'dictionary runtime',
        'DictionaryRuntimeData',
        dictionary_memory_handle().ir_type.as_pointer(),
        stack_bounds_handle().ir_type,
        stack_bounds_handle().ir_type,
        I32.as_pointer(),
        I32.as_pointer(),
        view_type=InterpreterRuntimeDataView,
    )


__all__ = [
    "CodeFieldView",
    "WordPrefixView",
    "RegistersView",
    "DictionaryMemoryView",
    "StackBoundsView",
    "InterpreterRuntimeDataView",
    "code_field_handle",
    "word_prefix_handle",
    "registers_handle",
    "dictionary_memory_handle",
    "stack_bounds_handle",
    "interpreter_runtime_handle",
]
