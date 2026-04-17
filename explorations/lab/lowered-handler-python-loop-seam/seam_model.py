from __future__ import annotations

from dataclasses import dataclass

from fythvm import dictionary

from seam_state import STATE_HALT_REQUESTED


@dataclass(frozen=True)
class Scenario:
    name: str
    thread: tuple[int, ...]
    expected_stack: tuple[int, ...]
    expected_final_ip: int
    expected_state_flags: int
    expected_trace_backends: tuple[str, ...]


@dataclass(frozen=True)
class TraceRow:
    step: int
    ip: int
    word: str
    backend: str
    stack_before: tuple[int, ...]
    stack_after: tuple[int, ...]
    state_flags_before: int
    state_flags_after: int
    note: str


@dataclass(frozen=True)
class ScenarioResult:
    final_stack: tuple[int, ...]
    final_ip: int
    state_flags: int
    trace: tuple[TraceRow, ...]


SCENARIOS = (
    Scenario(
        name="halt-only",
        thread=(int(dictionary.PrimitiveInstruction.HALT),),
        expected_stack=(),
        expected_final_ip=0,
        expected_state_flags=STATE_HALT_REQUESTED,
        expected_trace_backends=("jit",),
    ),
    Scenario(
        name="jit-lit-add-then-jit-halt",
        thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            2,
            int(dictionary.PrimitiveInstruction.LIT),
            3,
            int(dictionary.PrimitiveInstruction.ADD),
            int(dictionary.PrimitiveInstruction.HALT),
        ),
        expected_stack=(5,),
        expected_final_ip=5,
        expected_state_flags=STATE_HALT_REQUESTED,
        expected_trace_backends=("jit", "jit", "jit", "jit"),
    ),
    Scenario(
        name="jit-branch-skip-then-jit-halt",
        thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            7,
            int(dictionary.PrimitiveInstruction.BRANCH),
            2,
            int(dictionary.PrimitiveInstruction.LIT),
            999,
            int(dictionary.PrimitiveInstruction.HALT),
        ),
        expected_stack=(7,),
        expected_final_ip=6,
        expected_state_flags=STATE_HALT_REQUESTED,
        expected_trace_backends=("jit", "jit", "jit"),
    ),
    Scenario(
        name="jit-zbranch-skip-then-jit-halt",
        thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            0,
            int(dictionary.PrimitiveInstruction.ZBRANCH),
            2,
            int(dictionary.PrimitiveInstruction.LIT),
            999,
            int(dictionary.PrimitiveInstruction.HALT),
        ),
        expected_stack=(),
        expected_final_ip=6,
        expected_state_flags=STATE_HALT_REQUESTED,
        expected_trace_backends=("jit", "jit", "jit"),
    ),
)
