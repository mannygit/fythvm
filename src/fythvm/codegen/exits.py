"""Helpers for shared exit blocks that merge return-like values."""

from __future__ import annotations

from llvmlite import ir


class SharedExit:
    """Collect one shared exit contract from multiple predecessor blocks."""

    def __init__(self, function: ir.Function, specs: list[tuple[str, ir.Type]], block_name: str = "exit"):
        self.builder = ir.IRBuilder(function.append_basic_block(block_name))
        self.exit_block = self.builder.basic_block
        self.specs = specs
        self._incoming: list[tuple[tuple[ir.Value, ...], ir.Block]] = []

    def remember(self, builder: ir.IRBuilder, *values: ir.Value) -> None:
        if len(values) != len(self.specs):
            raise ValueError("exit value count does not match exit arity")
        self._incoming.append((tuple(values), builder.basic_block))
        builder.branch(self.exit_block)

    def finish(self) -> tuple[ir.PhiInstr, ...]:
        self.builder.position_at_end(self.exit_block)
        phis = tuple(self.builder.phi(ty, name=name) for name, ty in self.specs)
        for values, block in self._incoming:
            for phi, value in zip(phis, values, strict=True):
                phi.add_incoming(value, block)
        return phis
