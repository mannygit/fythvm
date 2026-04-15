"""Helpers for treating merge blocks as if they had block parameters."""

from __future__ import annotations

from llvmlite import ir


class Join:
    """Treat a merge block as if it had block parameters."""

    def __init__(self, builder: ir.IRBuilder, merge_block: ir.Block, specs: list[tuple[str, ir.Type]]):
        self.builder = builder
        self.merge_block = merge_block
        self.specs = specs
        self._phis: tuple[ir.PhiInstr, ...] = ()
        self._pending_incoming: list[tuple[ir.Block, tuple[ir.Value, ...]]] = []

    def __enter__(self) -> tuple[ir.PhiInstr, ...]:
        self.builder.position_at_end(self.merge_block)
        self._phis = tuple(self.builder.phi(ty, name=name) for name, ty in self.specs)
        for pred_block, values in self._pending_incoming:
            self._add_incoming_now(pred_block, *values)
        return self._phis

    def _add_incoming_now(self, pred_block: ir.Block, *values: ir.Value) -> None:
        if len(values) != len(self._phis):
            raise ValueError("incoming value count does not match join arity")

        for phi, value in zip(self._phis, values, strict=True):
            phi.add_incoming(value, pred_block)

    def add_incoming(self, pred_block: ir.Block, *values: ir.Value) -> None:
        if len(values) != len(self.specs):
            raise ValueError("incoming value count does not match join arity")

        if self._phis:
            self._add_incoming_now(pred_block, *values)
            return

        self._pending_incoming.append((pred_block, tuple(values)))

    def branch_from_here(self, builder: ir.IRBuilder, *values: ir.Value) -> None:
        pred_block = builder.basic_block
        builder.branch(self.merge_block)
        self.add_incoming(pred_block, *values)

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False
