"""Thin, hand-authored struct access helpers for llvmlite code generation."""

from __future__ import annotations

from dataclasses import dataclass

from llvmlite import ir

from .types import I32


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

    label: str
    ir_type: ir.Type
    view_type: type[BoundStructView] = BoundStructView

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
    def identified(
        cls,
        label: str,
        name: str,
        *fields: ir.Type,
        context: ir.Context = ir.global_context,
        view_type: type[BoundStructView] = BoundStructView,
    ) -> "StructHandle":
        struct_type = context.get_identified_type(name)
        if not struct_type.is_opaque:
            existing = tuple(struct_type.elements)
            if existing != fields:
                raise ValueError(
                    f"identified struct {name!r} already has a different body: {existing!r} != {fields!r}"
                )
        else:
            struct_type.set_body(*fields)
        return cls(label=label, ir_type=struct_type, view_type=view_type)

    def constant(self, *values: ir.Value) -> ir.Constant:
        return ir.Constant(self.ir_type, list(values))

    def define_global(self, module: ir.Module, name: str, *values: ir.Value) -> ir.GlobalVariable:
        global_var = ir.GlobalVariable(module, self.ir_type, name=name)
        global_var.initializer = self.constant(*values)
        return global_var

    def bind(self, builder: ir.IRBuilder, struct_ptr: ir.Value) -> BoundStructView:
        return self.view_type(self, builder, struct_ptr)
