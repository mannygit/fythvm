"""Struct access, ctypes reification, and generated logical views for llvmlite.

This module started as a thin bound-view layer over handwritten LLVM struct layouts.
It now also owns promoted ``ctypes.Structure`` reification, including:

- physical layout recovery with explicit padding
- arrays, pointers, and nested struct lowering
- generated logical view classes
- logical bitfield access over shared physical storage
"""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Hashable
from typing import ClassVar
from dataclasses import dataclass

from llvmlite import ir

from .types import I32


BYTEORDER = sys.byteorder


@dataclass(frozen=True)
class PhysicalFieldSpec:
    """One physical storage slot in a reified ctypes-backed IR struct."""

    name: str
    ir_type: ir.Type
    byte_offset: int
    byte_size: int
    kind: str


@dataclass(frozen=True)
class LogicalFieldSpec:
    """One logical field view projected over physical ctypes-backed storage."""

    name: str
    storage_index: int
    storage_name: str
    bit_offset: int | None = None
    bit_width: int | None = None

    @property
    def is_bitfield(self) -> bool:
        return self.bit_width is not None


@dataclass(frozen=True)
class BoundStructField:
    """One named field on a builder-bound struct view."""

    view: "BoundStructView"
    index: int
    field_name: str

    def ptr(self, *, name: str | None = None) -> ir.Value:
        ptr_name = name or f"{self.field_name}_ptr"
        return self.view.field_ptr(self.index, name=ptr_name)

    def load(self, *, name: str | None = None) -> ir.Value:
        load_name = name or self.field_name
        return self.view.builder.load(self.ptr(), name=load_name)

    def store(self, value: ir.Value) -> None:
        self.view.builder.store(value, self.ptr())

    def bind(self, handle: "StructHandle") -> "BoundStructView":
        return handle.bind(self.view.builder, self.ptr())

    def integer_type(self) -> ir.IntType:
        pointee = self.ptr().type.pointee
        if not isinstance(pointee, ir.IntType):
            raise TypeError(f"{self.field_name} is not backed by an integer field: {pointee!r}")
        return pointee


@dataclass(frozen=True)
class BoundBitField:
    """One logical bitfield view over a physical integer storage field."""

    view: "BoundStructView"
    storage_index: int
    field_name: str
    bit_offset: int
    bit_width: int
    signed: bool = False

    def storage(self) -> BoundStructField:
        return BoundStructField(
            self.view,
            self.storage_index,
            f"{self.field_name}_storage",
        )

    def load(self, *, name: str | None = None) -> ir.Value:
        builder = self.view.builder
        storage_field = self.storage()
        storage_value = storage_field.load(name=f"{self.field_name}_storage")
        storage_type = storage_field.integer_type()
        field_type = ir.IntType(self.bit_width)

        if self.bit_offset:
            shifted = builder.lshr(
                storage_value,
                storage_type(self.bit_offset),
                name=f"{self.field_name}_shifted",
            )
        else:
            shifted = storage_value

        if self.bit_width == storage_type.width:
            value = shifted
        else:
            value = builder.trunc(shifted, field_type, name=name or self.field_name)
        return value

    def store(self, value: ir.Value) -> None:
        builder = self.view.builder
        storage_field = self.storage()
        storage_type = storage_field.integer_type()
        field_type = ir.IntType(self.bit_width)

        field_value = value
        if not isinstance(field_value.type, ir.IntType):
            raise TypeError(f"{self.field_name} expects an integer value, got {field_value.type!r}")
        if field_value.type.width > self.bit_width:
            field_value = builder.trunc(field_value, field_type, name=f"{self.field_name}_bits")
        elif field_value.type.width < self.bit_width:
            field_value = builder.zext(field_value, field_type, name=f"{self.field_name}_bits")

        widened = field_value
        if widened.type.width < storage_type.width:
            widened = builder.zext(widened, storage_type, name=f"{self.field_name}_storage_bits")
        elif widened.type.width > storage_type.width:
            widened = builder.trunc(widened, storage_type, name=f"{self.field_name}_storage_bits")

        if self.bit_offset:
            shifted = builder.shl(
                widened,
                storage_type(self.bit_offset),
                name=f"{self.field_name}_positioned",
            )
        else:
            shifted = widened

        mask_value = ((1 << self.bit_width) - 1) << self.bit_offset
        mask = storage_type(mask_value)
        old_storage = storage_field.load(name=f"{self.field_name}_old_storage")
        cleared = builder.and_(
            old_storage,
            storage_type(~mask_value & ((1 << storage_type.width) - 1)),
            name=f"{self.field_name}_cleared",
        )
        masked = builder.and_(shifted, mask, name=f"{self.field_name}_masked")
        storage_field.store(builder.or_(cleared, masked, name=f"{self.field_name}_updated"))


class StructField:
    """Descriptor sugar for a fixed field index on a bound struct view."""

    def __init__(self, index: int):
        self.index = index
        self.field_name = f"field_{index:02d}"

    def __set_name__(self, owner: type["BoundStructView"], name: str) -> None:
        self.field_name = name

    def __get__(self, instance: "BoundStructView" | None, owner: type["BoundStructView"]):
        if instance is None:
            return self
        return BoundStructField(instance, self.index, self.field_name)


class BitField:
    """Descriptor sugar for one logical bitfield inside a storage field."""

    def __init__(self, storage_index: int, bit_offset: int, bit_width: int, *, signed: bool = False):
        self.storage_index = storage_index
        self.bit_offset = bit_offset
        self.bit_width = bit_width
        self.signed = signed
        self.field_name = f"bitfield_{storage_index:02d}_{bit_offset:02d}_{bit_width:02d}"

    def __set_name__(self, owner: type["BoundStructView"], name: str) -> None:
        self.field_name = name

    def __get__(self, instance: "BoundStructView" | None, owner: type["BoundStructView"]):
        if instance is None:
            return self
        return BoundBitField(
            instance,
            self.storage_index,
            self.field_name,
            self.bit_offset,
            self.bit_width,
            self.signed,
        )


class BoundStructView:
    """A struct access object bound to one active IR builder and one struct pointer."""

    def __init__(self, handle: "StructHandle", builder: ir.IRBuilder, struct_ptr: ir.Value):
        self.handle = handle
        self.builder = builder
        self.struct_ptr = struct_ptr

    def field_ptr(self, field_index: int, *, name: str) -> ir.Value:
        return self.builder.gep(
            self.struct_ptr,
            [I32(0), I32(field_index)],
            inbounds=True,
            name=name,
        )


@dataclass(frozen=True)
class StructHandle:
    """A named owner for a struct layout plus its bound view type."""

    _identified_registry: ClassVar[dict[Hashable, "StructHandle"]] = {}

    label: str
    ir_type: ir.Type
    view_type: type[BoundStructView] = BoundStructView
    view_source: str | None = None
    logical_fields: tuple[LogicalFieldSpec, ...] = ()
    physical_fields: tuple[PhysicalFieldSpec, ...] = ()

    @classmethod
    def literal(
        cls,
        label: str,
        *fields: ir.Type,
        packed: bool = False,
        view_type: type[BoundStructView] = BoundStructView,
    ) -> "StructHandle":
        return cls(
            label=label,
            ir_type=ir.LiteralStructType(list(fields), packed=packed),
            view_type=view_type,
        )

    @classmethod
    def from_ctypes(
        cls,
        label: str,
        ctypes_cls: type[ctypes.Structure],
        *,
        view_type: type[BoundStructView] | None = None,
    ) -> "StructHandle":
        if not issubclass(ctypes_cls, ctypes.Structure):
            raise TypeError(f"expected ctypes.Structure subclass, got {ctypes_cls!r}")

        physical_storage: list[tuple[str, PhysicalFieldSpec]] = []
        unresolved_logical_fields: list[tuple[str, LogicalFieldSpec]] = []

        for field_name, ctype, *rest in ctypes_cls._fields_:
            field_desc = getattr(ctypes_cls, field_name)
            byte_offset = field_desc.offset
            byte_size = ctypes.sizeof(ctype)
            storage_ir_type = _ir_type_from_ctypes(ctype)

            if rest:
                storage_key = f"storage:{byte_offset}:{byte_size}"
                if storage_key not in {key for key, _ in physical_storage}:
                    physical_storage.append(
                        (
                            storage_key,
                            PhysicalFieldSpec(
                                name=f"_{field_name}_storage",
                                ir_type=storage_ir_type,
                                byte_offset=byte_offset,
                                byte_size=byte_size,
                                kind="storage",
                            ),
                        )
                    )
                unresolved_logical_fields.append(
                    (
                        storage_key,
                        LogicalFieldSpec(
                            name=field_name,
                            storage_index=-1,
                            storage_name="",
                            bit_offset=field_desc.bit_offset,
                            bit_width=field_desc.bit_size,
                        ),
                    )
                )
                continue

            storage_key = f"field:{field_name}"
            physical_storage.append(
                (
                    storage_key,
                    PhysicalFieldSpec(
                        name=field_name,
                        ir_type=storage_ir_type,
                        byte_offset=byte_offset,
                        byte_size=byte_size,
                        kind="storage",
                    ),
                )
            )
            unresolved_logical_fields.append(
                (
                    storage_key,
                    LogicalFieldSpec(
                        name=field_name,
                        storage_index=-1,
                        storage_name="",
                    ),
                )
            )

        storage_by_key = dict(physical_storage)
        ordered_storage = sorted(storage_by_key.items(), key=lambda item: (item[1].byte_offset, item[1].name))

        physical_fields: list[PhysicalFieldSpec] = []
        storage_index_by_key: dict[str, int] = {}
        current_offset = 0
        pad_index = 0
        for storage_key, storage_spec in ordered_storage:
            if storage_spec.byte_offset > current_offset:
                pad_size = storage_spec.byte_offset - current_offset
                physical_fields.append(
                    PhysicalFieldSpec(
                        name=f"_pad_{pad_index:02d}",
                        ir_type=ir.ArrayType(ir.IntType(8), pad_size),
                        byte_offset=current_offset,
                        byte_size=pad_size,
                        kind="padding",
                    )
                )
                current_offset += pad_size
                pad_index += 1
            elif storage_spec.byte_offset < current_offset:
                raise ValueError(
                    f"overlapping or out-of-order ctypes field layout is unsupported: {storage_spec.name}"
                )

            storage_index_by_key[storage_key] = len(physical_fields)
            physical_fields.append(storage_spec)
            current_offset = storage_spec.byte_offset + storage_spec.byte_size

        total_size = ctypes.sizeof(ctypes_cls)
        if total_size > current_offset:
            physical_fields.append(
                PhysicalFieldSpec(
                    name=f"_pad_{pad_index:02d}",
                    ir_type=ir.ArrayType(ir.IntType(8), total_size - current_offset),
                    byte_offset=current_offset,
                    byte_size=total_size - current_offset,
                    kind="padding",
                )
            )

        packed = getattr(ctypes_cls, "_pack_", None) is not None
        resolved_logical_fields = tuple(
            LogicalFieldSpec(
                name=logical.name,
                storage_index=storage_index_by_key[storage_key],
                storage_name=storage_by_key[storage_key].name,
                bit_offset=logical.bit_offset,
                bit_width=logical.bit_width,
            )
            for storage_key, logical in unresolved_logical_fields
        )

        generated_view_source: str | None = None
        resolved_view_type = view_type
        if resolved_view_type is None:
            resolved_view_type, generated_view_source = build_generated_view_type(
                ctypes_cls,
                resolved_logical_fields,
            )

        return cls(
            label=label,
            ir_type=ir.LiteralStructType([field.ir_type for field in physical_fields], packed=packed),
            view_type=resolved_view_type or BoundStructView,
            view_source=generated_view_source,
            logical_fields=resolved_logical_fields,
            physical_fields=tuple(physical_fields),
        )

    @classmethod
    def identified(
        cls,
        label: str,
        name: str,
        *fields: ir.Type,
        context: ir.Context = ir.global_context,
        view_type: type[BoundStructView] = BoundStructView,
        registry_key: Hashable | None = None,
    ) -> "StructHandle":
        key = registry_key or (
            context,
            name,
            label,
            view_type.__module__,
            view_type.__qualname__,
            fields,
        )
        if key in cls._identified_registry:
            return cls._identified_registry[key]

        struct_type = context.get_identified_type(name)
        if not struct_type.is_opaque:
            existing = tuple(struct_type.elements)
            if existing != fields:
                raise ValueError(
                    f"identified struct {name!r} already has a different body: {existing!r} != {fields!r}"
                )
        else:
            struct_type.set_body(*fields)
        handle = cls(label=label, ir_type=struct_type, view_type=view_type)
        cls._identified_registry[key] = handle
        return handle

    def constant(self, *values: ir.Value) -> ir.Constant:
        return ir.Constant(self.ir_type, list(values))

    def define_global(self, module: ir.Module, name: str, *values: ir.Value) -> ir.GlobalVariable:
        global_var = ir.GlobalVariable(module, self.ir_type, name=name)
        global_var.initializer = self.constant(*values)
        return global_var

    def constant_from_ctypes(self, instance: ctypes.Structure) -> ir.Constant:
        if not isinstance(instance, ctypes.Structure):
            raise TypeError(f"expected ctypes.Structure instance, got {instance!r}")

        raw = bytes(ctypes.string_at(ctypes.addressof(instance), ctypes.sizeof(instance)))
        values: list[ir.Constant] = []
        offset = 0
        for field_type in self.ir_type.elements:
            byte_size = ctypes_type_size(field_type)
            chunk = raw[offset : offset + byte_size]
            values.append(_constant_from_bytes(field_type, chunk))
            offset += byte_size
        return ir.Constant(self.ir_type, values)

    def define_global_from_ctypes(
        self,
        module: ir.Module,
        name: str,
        instance: ctypes.Structure,
    ) -> ir.GlobalVariable:
        global_var = ir.GlobalVariable(module, self.ir_type, name=name)
        global_var.initializer = self.constant_from_ctypes(instance)
        return global_var

    def bind(self, builder: ir.IRBuilder, struct_ptr: ir.Value) -> BoundStructView:
        return self.view_type(self, builder, struct_ptr)


def build_generated_view_type(
    ctypes_cls: type[ctypes.Structure],
    logical_fields: tuple[LogicalFieldSpec, ...],
) -> tuple[type[BoundStructView], str]:
    """Generate a named logical projection class from resolved ctypes layout."""

    view_name = f"{ctypes_cls.__name__}View"
    source_lines = [
        f"class {view_name}(BoundStructView):",
        f'    """Generated bound view for {ctypes_cls.__name__}."""',
    ]
    for logical in logical_fields:
        if logical.is_bitfield:
            source_lines.append(
                f"    {logical.name} = BitField({logical.storage_index}, {logical.bit_offset}, {logical.bit_width})"
            )
        else:
            source_lines.append(f"    {logical.name} = StructField({logical.storage_index})")
    source = "\n".join(source_lines)
    namespace: dict[str, object] = {
        "BoundStructView": BoundStructView,
        "BitField": BitField,
        "StructField": StructField,
    }
    exec(source, namespace)
    return namespace[view_name], source


INTEGER_TYPE_CODES: set[str] = {
    "?",
    "b",
    "B",
    "h",
    "H",
    "i",
    "I",
    "l",
    "L",
    "q",
    "Q",
}


def _ir_type_from_ctypes(ctype: object) -> ir.Type:
    if isinstance(ctype, type) and issubclass(ctype, ctypes.Array):
        return ir.ArrayType(_ir_type_from_ctypes(ctype._type_), ctype._length_)

    if isinstance(ctype, type) and issubclass(ctype, ctypes.Structure):
        return StructHandle.from_ctypes(ctype.__name__, ctype).ir_type

    if isinstance(ctype, type) and issubclass(ctype, ctypes._Pointer):  # type: ignore[attr-defined]
        return _ir_type_from_ctypes(ctype._type_).as_pointer()

    if (
        isinstance(ctype, type)
        and issubclass(ctype, ctypes._SimpleCData)  # type: ignore[attr-defined]
        and getattr(ctype, "_type_", None) in INTEGER_TYPE_CODES
    ):
        return ir.IntType(ctypes.sizeof(ctype) * 8)

    raise ValueError(f"unsupported ctypes field type: {ctype!r}")


def ctypes_type_size(ir_type: ir.Type) -> int:
    if isinstance(ir_type, ir.IntType):
        return ir_type.width // 8
    if isinstance(ir_type, ir.ArrayType):
        return ctypes_type_size(ir_type.element) * ir_type.count
    if isinstance(ir_type, ir.LiteralStructType):
        return sum(ctypes_type_size(element) for element in ir_type.elements)
    if isinstance(ir_type, ir.PointerType):
        return ctypes.sizeof(ctypes.c_void_p)
    raise TypeError(f"unsupported IR type for ctypes constant materialization: {ir_type!r}")


def _constant_from_bytes(ir_type: ir.Type, chunk: bytes) -> ir.Constant:
    if isinstance(ir_type, ir.IntType):
        return ir.Constant(ir_type, int.from_bytes(chunk, byteorder=BYTEORDER, signed=False))

    if isinstance(ir_type, ir.ArrayType):
        element_size = ctypes_type_size(ir_type.element)
        if isinstance(ir_type.element, ir.IntType) and ir_type.element.width == 8:
            return ir.Constant(ir_type, [ir.IntType(8)(byte) for byte in chunk])
        return ir.Constant(
            ir_type,
            [
                _constant_from_bytes(
                    ir_type.element,
                    chunk[index * element_size : (index + 1) * element_size],
                )
                for index in range(ir_type.count)
            ],
        )

    if isinstance(ir_type, ir.LiteralStructType):
        values: list[ir.Constant] = []
        offset = 0
        for element in ir_type.elements:
            element_size = ctypes_type_size(element)
            values.append(_constant_from_bytes(element, chunk[offset : offset + element_size]))
            offset += element_size
        return ir.Constant(ir_type, values)

    if isinstance(ir_type, ir.PointerType):
        return ir.Constant(ir_type, int.from_bytes(chunk, byteorder=BYTEORDER, signed=False))

    raise TypeError(f"unsupported IR type for ctypes constant materialization: {ir_type!r}")
