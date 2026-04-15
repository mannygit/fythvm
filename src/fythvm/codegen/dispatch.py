"""Reusable switch/case dispatch helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from llvmlite import ir


CaseEmitter = Callable[[ir.IRBuilder], None]


@dataclass(frozen=True)
class SwitchCaseSpec:
    """Declarative description of one switch case."""

    match_value: ir.Value
    name: str
    emit_case: CaseEmitter


class SwitchDispatcher:
    """Build a visible LLVM switch while keeping case registration declarative."""

    def __init__(
        self,
        builder: ir.IRBuilder,
        switch_value: ir.Value,
        default_block: ir.Block,
        *,
        name: str,
    ):
        self.builder = builder
        self.switch_value = switch_value
        self.default_block = default_block
        self.name = name
        self._cases: list[SwitchCaseSpec] = []

    def add_case(self, match_value: ir.Value, name: str, emit_case: CaseEmitter) -> None:
        self._cases.append(SwitchCaseSpec(match_value=match_value, name=name, emit_case=emit_case))

    def emit(self) -> ir.instructions.SwitchInstr:
        switch = self.builder.switch(self.switch_value, self.default_block)
        for spec in self._cases:
            case_block = self.builder.function.append_basic_block(f"{self.name}.{spec.name}")
            switch.add_case(spec.match_value, case_block)
            with self.builder.goto_block(case_block):
                spec.emit_case(self.builder)
        return switch
