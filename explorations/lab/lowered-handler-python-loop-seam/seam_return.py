from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import ir

from fythvm.codegen import BoundStructView, ThreadRefIR
from fythvm.codegen.types import I32

from seam_state import RETURN_STACK_CAPACITY


@dataclass(frozen=True)
class ReturnFrameHost:
    thread_cells: ctypes._Pointer[ctypes.c_int32]  # type: ignore[attr-defined]
    thread_length: int
    return_ip: int


@dataclass(frozen=True)
class ReturnStackIR:
    """Lab-local return-frame storage over shared state arrays."""

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


def return_stack_depth(state) -> int:
    return RETURN_STACK_CAPACITY - int(state.rsp)


def pop_return_frame(state) -> ReturnFrameHost | None:
    rsp = int(state.rsp)
    if rsp >= RETURN_STACK_CAPACITY:
        return None
    frame = ReturnFrameHost(
        thread_cells=state.return_thread_cells[rsp],
        thread_length=int(state.return_thread_length[rsp]),
        return_ip=int(state.return_ip[rsp]),
    )
    state.rsp = rsp + 1
    return frame


def _array_slot_ptr(*, builder: ir.IRBuilder, array_field, index: ir.Value, slot_name: str) -> ir.Value:
    array_ptr = array_field.ptr(name=f"{slot_name}_array_ptr")
    base_ptr = builder.gep(array_ptr, [I32(0), I32(0)], inbounds=True, name=f"{slot_name}_base")
    return builder.gep(base_ptr, [index], inbounds=True, name=slot_name)
