"""Reusable stack-access primitives for llvmlite code generation."""

from __future__ import annotations

from llvmlite import ir

from .types import I32


class AbstractStackAccess:
    """Keep stack semantics separate from how stack fields are reached."""

    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        raise NotImplementedError

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        raise NotImplementedError

    def slot(self, builder: ir.IRBuilder, index: ir.Value, name: str = "slot_ptr") -> ir.Value:
        return builder.gep(self.load_stack_base(builder), [index], inbounds=True, name=name)

    def load_sp(self, builder: ir.IRBuilder, name: str = "sp") -> ir.Value:
        return builder.load(self.load_sp_ptr(builder), name=name)

    def store_sp(self, builder: ir.IRBuilder, value: ir.Value) -> None:
        builder.store(value, self.load_sp_ptr(builder))


class ContextStructStackAccess(AbstractStackAccess):
    """Derive stack pointers from a context struct with stack and sp fields."""

    def __init__(self, ctx_ptr: ir.Value, *, stack_field_index: int = 0, sp_field_index: int = 1):
        self.ctx_ptr = ctx_ptr
        self.stack_field_index = stack_field_index
        self.sp_field_index = sp_field_index

    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        stack_array_ptr = builder.gep(
            self.ctx_ptr,
            [I32(0), I32(self.stack_field_index)],
            inbounds=True,
            name="stack_array_ptr",
        )
        return builder.gep(stack_array_ptr, [I32(0), I32(0)], inbounds=True, name="stack_base")

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        return builder.gep(
            self.ctx_ptr,
            [I32(0), I32(self.sp_field_index)],
            inbounds=True,
            name="sp_ptr",
        )
