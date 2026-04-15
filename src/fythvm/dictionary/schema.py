"""Fixed ctypes schema for the dictionary runtime."""

from __future__ import annotations

import ctypes


CELL_SIZE = ctypes.sizeof(ctypes.c_int32)
DEFAULT_MEMORY_CELLS = 256
DEFAULT_STACK_CELLS = 16
NULL_INDEX = -1

NAME_LENGTH_MASK = 0x1F
HIDDEN_MASK = 0x40
IMMEDIATE_MASK = 0x80


def align_up(value: int, alignment: int = CELL_SIZE) -> int:
    return (value + alignment - 1) // alignment * alignment


class Registers(ctypes.Structure):
    __ir_name__ = "DictionaryRegisters"
    __ir_label__ = "dictionary registers"

    _fields_ = [
        ("here", ctypes.c_int32),
        ("latest", ctypes.c_int32),
        ("state", ctypes.c_int32),
        ("base", ctypes.c_int32),
        ("sp", ctypes.c_int32),
        ("rsp", ctypes.c_int32),
    ]


class StackBounds(ctypes.Structure):
    __ir_name__ = "DictionaryStackBounds"
    __ir_label__ = "stack bounds"

    _fields_ = [
        ("top", ctypes.POINTER(ctypes.c_int32)),
        ("bottom", ctypes.POINTER(ctypes.c_int32)),
    ]


class CodeField(ctypes.Structure):
    __ir_name__ = "DictionaryCodeField"
    __ir_label__ = "code field"

    _fields_ = [
        ("instruction", ctypes.c_uint32, 7),
        ("hidden", ctypes.c_uint32, 1),
        ("name_length", ctypes.c_uint32, 5),
        ("immediate", ctypes.c_uint32, 1),
        ("compiling", ctypes.c_uint32, 1),
        ("unused", ctypes.c_uint32, 17),
    ]


class WordPrefix(ctypes.Structure):
    __ir_name__ = "DictionaryWordPrefix"
    __ir_label__ = "word prefix"

    _fields_ = [
        ("link", ctypes.c_int32),
        ("code", CodeField),
        ("data_start", ctypes.c_int32 * 0),
    ]


class DictionaryMemory(ctypes.Structure):
    __ir_name__ = "DictionaryMemory"
    __ir_label__ = "dictionary memory"

    _fields_ = [
        ("registers", Registers),
        ("cells", ctypes.c_int32 * DEFAULT_MEMORY_CELLS),
        ("data_stack", ctypes.c_int32 * DEFAULT_STACK_CELLS),
        ("return_stack", ctypes.c_int32 * DEFAULT_STACK_CELLS),
    ]


class InterpreterRuntimeData(ctypes.Structure):
    __ir_name__ = "DictionaryRuntimeData"
    __ir_label__ = "dictionary runtime"

    _fields_ = [
        ("memory_ptr", ctypes.POINTER(DictionaryMemory)),
        ("psp", StackBounds),
        ("rsp", StackBounds),
        ("tos", ctypes.POINTER(ctypes.c_int32)),
        ("rtos", ctypes.POINTER(ctypes.c_int32)),
    ]


IR_STRUCTS = (
    Registers,
    StackBounds,
    CodeField,
    WordPrefix,
    DictionaryMemory,
    InterpreterRuntimeData,
)


__all__ = [
    "CELL_SIZE",
    "DEFAULT_MEMORY_CELLS",
    "DEFAULT_STACK_CELLS",
    "HIDDEN_MASK",
    "IMMEDIATE_MASK",
    "IR_STRUCTS",
    "NAME_LENGTH_MASK",
    "NULL_INDEX",
    "CodeField",
    "DictionaryMemory",
    "InterpreterRuntimeData",
    "Registers",
    "StackBounds",
    "WordPrefix",
    "align_up",
]
