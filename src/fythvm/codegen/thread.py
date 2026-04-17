"""Reusable thread-access primitives for llvmlite code generation."""

from __future__ import annotations

from dataclasses import dataclass

from llvmlite import ir

from .structs import BoundStructView
from .types import I32


@dataclass(frozen=True)
class ThreadRefIR:
    """One lowered thread reference as a cells pointer plus a logical length."""

    cells: ir.Value
    length: ir.Value


@dataclass(frozen=True)
class ThreadCursorIR:
    """Current-thread operand access layered over ip and thread storage."""

    builder: ir.IRBuilder
    state: BoundStructView
    ip_field_name: str = "ip"
    thread_cells_field_name: str = "thread_cells"

    def read_inline_cell(self) -> ir.Value:
        ip_field = getattr(self.state, self.ip_field_name)
        thread_cells_field = getattr(self.state, self.thread_cells_field_name)
        current_ip = ip_field.load(name="current_ip")
        operand_ip = self.builder.add(current_ip, I32(1), name="operand_ip")
        thread_cells = thread_cells_field.load(name="thread_cells")
        slot_ptr = self.builder.gep(thread_cells, [operand_ip], inbounds=True, name="operand_ptr")
        operand = self.builder.load(slot_ptr, name="inline_operand")
        ip_field.store(operand_ip)
        return operand


@dataclass(frozen=True)
class ThreadJumpIR:
    """Thread-position redirection layered over the shared ip field."""

    builder: ir.IRBuilder
    state: BoundStructView
    ip_field_name: str = "ip"

    def branch_relative(self, offset: ir.Value) -> None:
        ip_field = getattr(self.state, self.ip_field_name)
        current_ip = ip_field.load(name="branch_ip")
        target_ip = self.builder.add(current_ip, offset, name="branch_target_ip")
        ip_field.store(target_ip)

    def branch_if_zero(self, value: ir.Value, offset: ir.Value) -> None:
        ip_field = getattr(self.state, self.ip_field_name)
        current_ip = ip_field.load(name="zbranch_ip")
        target_ip = self.builder.add(current_ip, offset, name="zbranch_target_ip")
        should_branch = self.builder.icmp_signed("==", value, I32(0), name="zbranch_is_zero")
        next_ip = self.builder.select(should_branch, target_ip, current_ip, name="zbranch_next_ip")
        ip_field.store(next_ip)


@dataclass(frozen=True)
class CurrentWordThreadIR:
    """Current-word thread access without leaking raw dictionary storage detail."""

    state: BoundStructView
    thread_cells_field_name: str = "current_word_thread_cells"
    thread_length_field_name: str = "current_word_thread_length"

    def ref(self) -> ThreadRefIR:
        thread_cells_field = getattr(self.state, self.thread_cells_field_name)
        thread_length_field = getattr(self.state, self.thread_length_field_name)
        return ThreadRefIR(
            cells=thread_cells_field.load(name="current_word_thread_cells"),
            length=thread_length_field.load(name="current_word_thread_length"),
        )
