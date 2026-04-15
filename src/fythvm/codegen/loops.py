"""Loop helpers built on the block-parameter join model."""

from __future__ import annotations

from contextlib import contextmanager

from llvmlite import ir

from .joins import Join


class ParamLoop:
    """Treat a loop header as a block with parameters plus visible loop blocks."""

    def __init__(self, builder: ir.IRBuilder, name: str, specs: list[tuple[str, ir.Type]]):
        self.builder = builder
        self.name = name
        self.entry_block = builder.basic_block
        self.head_block = builder.append_basic_block(f"{name}.head")
        self.body_block = builder.append_basic_block(f"{name}.body")
        self.exit_block = builder.append_basic_block(f"{name}.exit")
        self._join = Join(builder, self.head_block, specs)

    def begin(self, *values: ir.Value) -> None:
        self._join.add_incoming(self.entry_block, *values)
        self.builder.branch(self.head_block)

    def continue_from_here(self, *values: ir.Value) -> None:
        self._join.branch_from_here(self.builder, *values)

    @contextmanager
    def head(self):
        with self._join as values:
            yield values

    @contextmanager
    def body(self):
        self.builder.position_at_end(self.body_block)
        yield self.builder.basic_block

    @contextmanager
    def exit(self):
        self.builder.position_at_end(self.exit_block)
        yield self.builder.basic_block
