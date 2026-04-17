"""Reusable return-stack access primitives for llvmlite code generation."""

from __future__ import annotations

from dataclasses import dataclass

from llvmlite import ir

from .structs import BoundStructView
from .thread import ThreadRefIR
from .types import I32


@dataclass(frozen=True)
class ReturnStackIR:
    """Return-frame storage over shared state arrays."""

    builder: ir.IRBuilder
    state: BoundStructView
    thread_cells_field_name: str = "return_thread_cells"
    thread_length_field_name: str = "return_thread_length"
    return_ip_field_name: str = "return_ip"
    rsp_field_name: str = "rsp"

    def push_frame(self, *, thread: ThreadRefIR, return_ip: ir.Value) -> ir.Value:
        current_rsp = getattr(self.state, self.rsp_field_name).load(name="rsp")
        new_rsp = self.builder.sub(current_rsp, I32(1), name="new_rsp")

        thread_cells_ptr = _array_slot_ptr(
            builder=self.builder,
            array_field=getattr(self.state, self.thread_cells_field_name),
            index=new_rsp,
            slot_name="return_thread_cells_ptr",
        )
        self.builder.store(thread.cells, thread_cells_ptr)

        thread_length_ptr = _array_slot_ptr(
            builder=self.builder,
            array_field=getattr(self.state, self.thread_length_field_name),
            index=new_rsp,
            slot_name="return_thread_length_ptr",
        )
        self.builder.store(thread.length, thread_length_ptr)

        return_ip_ptr = _array_slot_ptr(
            builder=self.builder,
            array_field=getattr(self.state, self.return_ip_field_name),
            index=new_rsp,
            slot_name="return_ip_ptr",
        )
        self.builder.store(return_ip, return_ip_ptr)

        getattr(self.state, self.rsp_field_name).store(new_rsp)
        return new_rsp

    def pop_frame(self) -> tuple[ThreadRefIR, ir.Value]:
        current_rsp = getattr(self.state, self.rsp_field_name).load(name="rsp")

        thread_cells_ptr = _array_slot_ptr(
            builder=self.builder,
            array_field=getattr(self.state, self.thread_cells_field_name),
            index=current_rsp,
            slot_name="popped_thread_cells_ptr",
        )
        thread_cells = self.builder.load(thread_cells_ptr, name="popped_thread_cells")

        thread_length_ptr = _array_slot_ptr(
            builder=self.builder,
            array_field=getattr(self.state, self.thread_length_field_name),
            index=current_rsp,
            slot_name="popped_thread_length_ptr",
        )
        thread_length = self.builder.load(thread_length_ptr, name="popped_thread_length")

        return_ip_ptr = _array_slot_ptr(
            builder=self.builder,
            array_field=getattr(self.state, self.return_ip_field_name),
            index=current_rsp,
            slot_name="popped_return_ip_ptr",
        )
        return_ip = self.builder.load(return_ip_ptr, name="popped_return_ip")

        next_rsp = self.builder.add(current_rsp, I32(1), name="next_rsp")
        getattr(self.state, self.rsp_field_name).store(next_rsp)
        return ThreadRefIR(cells=thread_cells, length=thread_length), return_ip


def _array_slot_ptr(*, builder: ir.IRBuilder, array_field, index: ir.Value, slot_name: str) -> ir.Value:
    array_ptr = array_field.ptr(name=f"{slot_name}_array_ptr")
    base_ptr = builder.gep(array_ptr, [I32(0), I32(0)], inbounds=True, name=f"{slot_name}_base")
    return builder.gep(base_ptr, [index], inbounds=True, name=slot_name)
