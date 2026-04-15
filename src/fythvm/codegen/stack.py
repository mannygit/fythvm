"""Reusable stack-access primitives for llvmlite code generation."""

from __future__ import annotations

from dataclasses import dataclass

from llvmlite import ir

from .structs import BoundStructField, BoundStructView
from .types import I32


@dataclass(frozen=True)
class PoppedPair:
    """Two top stack values plus the index where a reduced result should land."""

    lhs: ir.Value
    rhs: ir.Value
    result_index: ir.Value


class BoundStackAccess:
    """A stack access object bound to one active IR builder."""

    def __init__(self, access: "AbstractStackAccess", builder: ir.IRBuilder):
        self.access = access
        self.builder = builder

    def slot(self, index: ir.Value, name: str = "slot_ptr") -> ir.Value:
        return self.access.slot(self.builder, index, name=name)

    def load_sp(self, name: str = "sp") -> ir.Value:
        return self.access.load_sp(self.builder, name=name)

    def store_sp(self, value: ir.Value) -> None:
        self.access.store_sp(self.builder, value)

    def reset(self, empty_sp: ir.Value) -> None:
        self.access.reset(self.builder, empty_sp)

    def push(self, value: ir.Value, *, name: str = "new_sp") -> ir.Value:
        return self.access.push(self.builder, value, name=name)

    def pop2(self, *, result_index_name: str = "lhs_index") -> PoppedPair:
        return self.access.pop2(self.builder, result_index_name=result_index_name)

    def peek(self, *, name: str = "value") -> ir.Value:
        return self.access.peek(self.builder, name=name)

    def has_room(self, *, name: str = "has_room") -> ir.Value:
        return self.access.has_room(self.builder, name=name)

    def has_at_least(self, count: int, *, name: str = "has_at_least") -> ir.Value:
        return self.access.has_at_least(self.builder, count, name=name)

    def has_exactly(self, count: int, *, name: str = "has_exactly") -> ir.Value:
        return self.access.has_exactly(self.builder, count, name=name)


class AbstractStackAccess:
    """Keep stack semantics separate from how stack fields are reached."""

    def bind(self, builder: ir.IRBuilder) -> BoundStackAccess:
        return BoundStackAccess(self, builder)

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

    def reset(self, builder: ir.IRBuilder, empty_sp: ir.Value) -> None:
        self.store_sp(builder, empty_sp)

    def push(self, builder: ir.IRBuilder, value: ir.Value, *, name: str = "new_sp") -> ir.Value:
        current_sp = self.load_sp(builder)
        new_sp = builder.sub(current_sp, I32(1), name=name)
        builder.store(value, self.slot(builder, new_sp))
        self.store_sp(builder, new_sp)
        return new_sp

    def pop2(self, builder: ir.IRBuilder, *, result_index_name: str = "lhs_index") -> PoppedPair:
        current_sp = self.load_sp(builder)
        rhs = builder.load(self.slot(builder, current_sp, name="rhs_ptr"), name="rhs")
        result_index = builder.add(current_sp, I32(1), name=result_index_name)
        lhs = builder.load(self.slot(builder, result_index, name="lhs_ptr"), name="lhs")
        return PoppedPair(lhs=lhs, rhs=rhs, result_index=result_index)

    def peek(self, builder: ir.IRBuilder, *, name: str = "value") -> ir.Value:
        current_sp = self.load_sp(builder)
        return builder.load(self.slot(builder, current_sp), name=name)

    def has_room(self, builder: ir.IRBuilder, *, name: str = "has_room") -> ir.Value:
        current_sp = self.load_sp(builder)
        return builder.icmp_unsigned("!=", current_sp, I32(0), name=name)

    def has_at_least(self, builder: ir.IRBuilder, count: int, *, name: str = "has_at_least") -> ir.Value:
        current_sp = self.load_sp(builder)
        highest_valid_sp = I32(self.stack_capacity(builder) - count)
        return builder.icmp_unsigned("<=", current_sp, highest_valid_sp, name=name)

    def has_exactly(self, builder: ir.IRBuilder, count: int, *, name: str = "has_exactly") -> ir.Value:
        current_sp = self.load_sp(builder)
        expected_sp = I32(self.stack_capacity(builder) - count)
        return builder.icmp_unsigned("==", current_sp, expected_sp, name=name)

    def stack_capacity(self, builder: ir.IRBuilder) -> int:
        raise NotImplementedError


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

    def stack_capacity(self, builder: ir.IRBuilder) -> int:
        stack_type = self.ctx_ptr.type.pointee.elements[self.stack_field_index]
        return stack_type.count


class StructViewStackAccess(AbstractStackAccess):
    """Derive stack pointers from named fields on a bound struct view."""

    def __init__(
        self,
        view: BoundStructView,
        *,
        stack_field_name: str = "stack",
        sp_field_name: str = "sp",
    ):
        self.view = view
        self.stack_field = getattr(view, stack_field_name)
        self.sp_field = getattr(view, sp_field_name)
        if not isinstance(self.stack_field, BoundStructField):
            raise TypeError(f"{stack_field_name!r} is not a struct field on {type(view).__name__}")
        if not isinstance(self.sp_field, BoundStructField):
            raise TypeError(f"{sp_field_name!r} is not a struct field on {type(view).__name__}")

    def _ensure_builder(self, builder: ir.IRBuilder) -> None:
        if builder is not self.view.builder:
            raise ValueError("StructViewStackAccess must be used with the builder bound to its context view")

    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        self._ensure_builder(builder)
        stack_array_ptr = self.stack_field.ptr(name="stack_array_ptr")
        return builder.gep(stack_array_ptr, [I32(0), I32(0)], inbounds=True, name="stack_base")

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        self._ensure_builder(builder)
        return self.sp_field.ptr(name="sp_ptr")

    def stack_capacity(self, builder: ir.IRBuilder) -> int:
        self._ensure_builder(builder)
        stack_type = self.stack_field.ptr().type.pointee
        return stack_type.count
