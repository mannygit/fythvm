"""DO NOT EDIT: generated from `src/fythvm/dictionary/schema.py`.

Regenerate with:
  uv run python scripts/generate_dictionary_layout.py
"""

from __future__ import annotations

from llvmlite import ir

from ..codegen import BoundStructView, StructField, StructHandle

I8 = ir.IntType(8)
I16 = ir.IntType(16)
I32 = ir.IntType(32)
I64 = ir.IntType(64)


class RegistersView(BoundStructView):
    here = StructField(0)
    latest = StructField(1)
    state = StructField(2)
    base = StructField(3)
    sp = StructField(4)
    rsp = StructField(5)


class StackBoundsView(BoundStructView):
    top = StructField(0)
    bottom = StructField(1)


class CodeFieldView(BoundStructView):
    cell = StructField(0)


class WordPrefixView(BoundStructView):
    link = StructField(0)
    code = StructField(1)
    data_start = StructField(2)


class DictionaryMemoryView(BoundStructView):
    registers = StructField(0)
    cells = StructField(1)
    data_stack = StructField(2)
    return_stack = StructField(3)


class InterpreterRuntimeDataView(BoundStructView):
    memory_ptr = StructField(0)
    psp = StructField(1)
    rsp = StructField(2)
    tos = StructField(3)
    rtos = StructField(4)


_REGISTERS_HANDLE: StructHandle | None = None
_STACKBOUNDS_HANDLE: StructHandle | None = None
_CODEFIELD_HANDLE: StructHandle | None = None
_WORDPREFIX_HANDLE: StructHandle | None = None
_DICTIONARYMEMORY_HANDLE: StructHandle | None = None
_INTERPRETERRUNTIMEDATA_HANDLE: StructHandle | None = None


def registers_handle() -> StructHandle:
    global _REGISTERS_HANDLE
    if _REGISTERS_HANDLE is None:
        _REGISTERS_HANDLE = StructHandle.identified(
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
    return _REGISTERS_HANDLE


def stack_bounds_handle() -> StructHandle:
    global _STACKBOUNDS_HANDLE
    if _STACKBOUNDS_HANDLE is None:
        _STACKBOUNDS_HANDLE = StructHandle.identified(
            'stack bounds',
            'DictionaryStackBounds',
            I32.as_pointer(),
            I32.as_pointer(),
            view_type=StackBoundsView,
        )
    return _STACKBOUNDS_HANDLE


def code_field_handle() -> StructHandle:
    global _CODEFIELD_HANDLE
    if _CODEFIELD_HANDLE is None:
        _CODEFIELD_HANDLE = StructHandle.identified(
            'code field',
            'DictionaryCodeField',
            I32,
            view_type=CodeFieldView,
        )
    return _CODEFIELD_HANDLE


def word_prefix_handle() -> StructHandle:
    global _WORDPREFIX_HANDLE
    if _WORDPREFIX_HANDLE is None:
        _WORDPREFIX_HANDLE = StructHandle.identified(
            'word prefix',
            'DictionaryWordPrefix',
            I32,
            code_field_handle().ir_type,
            ir.ArrayType(I32, 0),
            view_type=WordPrefixView,
        )
    return _WORDPREFIX_HANDLE


def dictionary_memory_handle() -> StructHandle:
    global _DICTIONARYMEMORY_HANDLE
    if _DICTIONARYMEMORY_HANDLE is None:
        _DICTIONARYMEMORY_HANDLE = StructHandle.identified(
            'dictionary memory',
            'DictionaryMemory',
            registers_handle().ir_type,
            ir.ArrayType(I32, 256),
            ir.ArrayType(I32, 16),
            ir.ArrayType(I32, 16),
            view_type=DictionaryMemoryView,
        )
    return _DICTIONARYMEMORY_HANDLE


def interpreter_runtime_handle() -> StructHandle:
    global _INTERPRETERRUNTIMEDATA_HANDLE
    if _INTERPRETERRUNTIMEDATA_HANDLE is None:
        _INTERPRETERRUNTIMEDATA_HANDLE = StructHandle.identified(
            'dictionary runtime',
            'DictionaryRuntimeData',
            dictionary_memory_handle().ir_type.as_pointer(),
            stack_bounds_handle().ir_type,
            stack_bounds_handle().ir_type,
            I32.as_pointer(),
            I32.as_pointer(),
            view_type=InterpreterRuntimeDataView,
        )
    return _INTERPRETERRUNTIMEDATA_HANDLE


__all__ = [
    "RegistersView",
    "StackBoundsView",
    "CodeFieldView",
    "WordPrefixView",
    "DictionaryMemoryView",
    "InterpreterRuntimeDataView",
    "registers_handle",
    "stack_bounds_handle",
    "code_field_handle",
    "word_prefix_handle",
    "dictionary_memory_handle",
    "interpreter_runtime_handle",
]
