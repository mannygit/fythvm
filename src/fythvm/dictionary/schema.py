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
        ("handler_id", ctypes.c_uint32, 7),
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
        ("code_field", CodeField),
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


IR_SCHEMA_ROOTS = (
    WordPrefix,
    DictionaryMemory,
    InterpreterRuntimeData,
)


def _referenced_struct_types(field_type: object) -> tuple[type[ctypes.Structure], ...]:
    if isinstance(field_type, type) and issubclass(field_type, ctypes.Structure):
        return (field_type,)
    if isinstance(field_type, type) and issubclass(field_type, ctypes.Array):
        return _referenced_struct_types(field_type._type_)
    if isinstance(field_type, type) and issubclass(field_type, ctypes._Pointer):  # type: ignore[attr-defined]
        return _referenced_struct_types(field_type._type_)
    return ()


def _field_types(struct_cls: type[ctypes.Structure]) -> list[object]:
    return [field_type for _name, field_type, *_rest in struct_cls._fields_]


def iter_schema_family(
    roots: tuple[type[ctypes.Structure], ...] = IR_SCHEMA_ROOTS,
) -> tuple[type[ctypes.Structure], ...]:
    ordered: list[type[ctypes.Structure]] = []
    seen: set[type[ctypes.Structure]] = set()

    def visit(struct_cls: type[ctypes.Structure]) -> None:
        if struct_cls in seen:
            return
        seen.add(struct_cls)
        for field_type in _field_types(struct_cls):
            for nested in _referenced_struct_types(field_type):
                visit(nested)
        ordered.append(struct_cls)

    for root in roots:
        visit(root)
    return tuple(ordered)


IR_STRUCTS = iter_schema_family()


__all__ = [
    "CELL_SIZE",
    "DEFAULT_MEMORY_CELLS",
    "DEFAULT_STACK_CELLS",
    "HIDDEN_MASK",
    "IMMEDIATE_MASK",
    "IR_SCHEMA_ROOTS",
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
    "iter_schema_family",
]
