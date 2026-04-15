"""Generate the dictionary IR layout module from the ctypes schema."""

from __future__ import annotations

import ctypes
from pathlib import Path

from fythvm.dictionary import schema


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "fythvm" / "dictionary" / "layout.py"


INT_TYPE_NAMES = {
    ctypes.c_int8: "I8",
    ctypes.c_uint8: "I8",
    ctypes.c_bool: "I8",
    ctypes.c_int16: "I16",
    ctypes.c_uint16: "I16",
    ctypes.c_int32: "I32",
    ctypes.c_uint32: "I32",
    ctypes.c_int64: "I64",
    ctypes.c_uint64: "I64",
}

SIGNED_INT_TYPES = {
    ctypes.c_int8,
    ctypes.c_int16,
    ctypes.c_int32,
    ctypes.c_int64,
}


HANDLE_FN_NAMES = {
    "Registers": "registers_handle",
    "StackBounds": "stack_bounds_handle",
    "CodeField": "code_field_handle",
    "WordPrefix": "word_prefix_handle",
    "DictionaryMemory": "dictionary_memory_handle",
    "InterpreterRuntimeData": "interpreter_runtime_handle",
}


def view_name(struct_cls: type[ctypes.Structure]) -> str:
    return f"{struct_cls.__name__}View"


def field_specs(struct_cls: type[ctypes.Structure]) -> list[tuple[str, object]]:
    specs: list[tuple[str, object]] = []
    seen_offsets: set[int] = set()
    for field_spec in struct_cls._fields_:
        name, field_type, *rest = field_spec
        offset = getattr(struct_cls, name).offset
        if rest:
            if offset in seen_offsets:
                continue
            seen_offsets.add(offset)
            if struct_cls.__name__ == "CodeField" and offset == 0:
                name = "cell"
            else:
                name = f"storage_{offset:02d}"
        specs.append((name, field_type))
    return specs


def logical_bitfield_specs(struct_cls: type[ctypes.Structure]) -> list[tuple[str, int, int, int, bool]]:
    offset_to_storage_index: dict[int, int] = {}
    physical_index = 0
    seen_offsets: set[int] = set()
    for field_spec in struct_cls._fields_:
        field_name, _field_type, *rest = field_spec
        storage_offset = getattr(struct_cls, field_name).offset
        if rest and storage_offset in seen_offsets:
            continue
        seen_offsets.add(storage_offset)
        offset_to_storage_index[storage_offset] = physical_index
        physical_index += 1

    bit_offsets: dict[int, int] = {}
    specs: list[tuple[str, int, int, int, bool]] = []
    for field_spec in struct_cls._fields_:
        name, field_type, *rest = field_spec
        if not rest:
            continue
        bit_width = rest[0]
        storage_offset = getattr(struct_cls, name).offset
        bit_offset = bit_offsets.get(storage_offset, 0)
        storage_index = offset_to_storage_index[storage_offset]
        signed = field_type in SIGNED_INT_TYPES
        specs.append((name, storage_index, bit_offset, bit_width, signed))
        bit_offsets[storage_offset] = bit_offset + bit_width
    return specs


def ir_type_expr(field_type: object) -> str:
    if isinstance(field_type, type) and issubclass(field_type, ctypes.Structure):
        return f"{HANDLE_FN_NAMES[field_type.__name__]}().ir_type"

    if isinstance(field_type, type) and issubclass(field_type, ctypes._Pointer):  # type: ignore[attr-defined]
        pointee = field_type._type_
        return f"{ir_type_expr(pointee)}.as_pointer()"

    if isinstance(field_type, type) and issubclass(field_type, ctypes.Array):
        return f"ir.ArrayType({ir_type_expr(field_type._type_)}, {field_type._length_})"

    try:
        return INT_TYPE_NAMES[field_type]
    except KeyError as exc:
        raise TypeError(f"unsupported ctypes field type: {field_type!r}") from exc


def emit_views() -> list[str]:
    lines: list[str] = []
    for struct_cls in schema.IR_STRUCTS:
        lines.append(f"class {view_name(struct_cls)}(BoundStructView):")
        for index, (field_name, _field_type) in enumerate(field_specs(struct_cls)):
            lines.append(f"    {field_name} = StructField({index})")
        for field_name, storage_index, bit_offset, bit_width, signed in logical_bitfield_specs(struct_cls):
            args = f"{storage_index}, {bit_offset}, {bit_width}"
            if signed:
                args += ", signed=True"
            lines.append(f"    {field_name} = BitField({args})")
        lines.append("")
        lines.append("")
    return lines


def emit_handle_functions() -> list[str]:
    lines: list[str] = []
    for struct_cls in schema.IR_STRUCTS:
        fn_name = HANDLE_FN_NAMES[struct_cls.__name__]
        label = getattr(struct_cls, "__ir_label__")
        ir_name = getattr(struct_cls, "__ir_name__")
        field_exprs = [ir_type_expr(field_type) for _name, field_type in field_specs(struct_cls)]

        lines.append(f"def {fn_name}() -> StructHandle:")
        lines.append("    return StructHandle.identified(")
        lines.append(f"        {label!r},")
        lines.append(f"        {ir_name!r},")
        for expr in field_exprs:
            lines.append(f"        {expr},")
        lines.append(f"        view_type={view_name(struct_cls)},")
        lines.append("    )")
        lines.append("")
        lines.append("")
    return lines


def generate() -> str:
    lines = [
        '"""DO NOT EDIT: generated from `src/fythvm/dictionary/schema.py`.',
        "",
        "Regenerate with:",
        "  uv run python scripts/generate_dictionary_layout.py",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from llvmlite import ir",
        "",
        "from ..codegen import BitField, BoundStructView, StructField, StructHandle",
        "",
        "I8 = ir.IntType(8)",
        "I16 = ir.IntType(16)",
        "I32 = ir.IntType(32)",
        "I64 = ir.IntType(64)",
        "",
        "",
    ]
    lines.extend(emit_views())
    lines.extend(emit_handle_functions())
    lines.append("__all__ = [")
    for struct_cls in schema.IR_STRUCTS:
        lines.append(f'    "{view_name(struct_cls)}",')
    for struct_cls in schema.IR_STRUCTS:
        lines.append(f'    "{HANDLE_FN_NAMES[struct_cls.__name__]}",')
    lines.append("]")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT.write_text(generate())
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
