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
