"""Thin helpers for instruction-pointer-driven interpreters."""

from __future__ import annotations

from dataclasses import dataclass

from llvmlite import ir


@dataclass(frozen=True)
class FetchedCell:
    """SSA values threaded through one fetch/decode step."""

    ip: ir.Value
    next_ip: ir.Value
    current_cell: ir.Value


def emit_tagged_cell_dispatch(
    builder: ir.IRBuilder,
    cells_ptr: ir.Value,
    ip: ir.Value,
    *,
    literal_target: ir.Block,
    opcode_target: ir.Block,
    cell_type: ir.Type,
    index_type: ir.Type,
    tag_mask: int,
) -> FetchedCell:
    cell_ptr = builder.gep(cells_ptr, [ip], inbounds=True, name="cell_ptr")
    current_cell = builder.load(cell_ptr, name="cell")
    next_ip = builder.add(ip, index_type(1), name="next_ip")
    is_literal = builder.icmp_unsigned(
        "==",
        builder.and_(current_cell, cell_type(tag_mask), name="tag_bits"),
        cell_type(0),
        name="is_literal",
    )
    builder.cbranch(is_literal, literal_target, opcode_target)
    return FetchedCell(ip=ip, next_ip=next_ip, current_cell=current_cell)
