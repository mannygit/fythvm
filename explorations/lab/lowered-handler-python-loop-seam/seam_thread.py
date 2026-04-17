from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import ir

from seam_state import LoweredLoopStateView


I32 = ir.IntType(32)


@dataclass(frozen=True)
class ThreadCursorIR:
    """Current-thread operand access layered over ip and thread storage."""

    builder: ir.IRBuilder
    state: LoweredLoopStateView

    def read_inline_cell(self) -> ir.Value:
        current_ip = self.state.ip.load(name="current_ip")
        operand_ip = self.builder.add(current_ip, I32(1), name="operand_ip")
        thread_cells = self.state.thread_cells.load(name="thread_cells")
        slot_ptr = self.builder.gep(thread_cells, [operand_ip], inbounds=True, name="operand_ptr")
        operand = self.builder.load(slot_ptr, name="inline_operand")
        self.state.ip.store(operand_ip)
        return operand


def materialize_thread_buffer(thread: tuple[int, ...]) -> ctypes.Array[ctypes.c_int32]:
    return (ctypes.c_int32 * len(thread))(*thread)
