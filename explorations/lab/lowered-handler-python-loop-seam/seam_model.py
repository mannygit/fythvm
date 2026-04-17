from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from fythvm import dictionary

from seam_state import STATE_HALT_REQUESTED

ThreadCellToken: TypeAlias = int | str


@dataclass(frozen=True)
class Scenario:
    name: str
    thread: tuple[ThreadCellToken, ...]
    expected_stack: tuple[int, ...]
    expected_final_ip: int
    expected_state_flags: int
    expected_trace_backends: tuple[str, ...]
    custom_words: tuple["WordBlueprint", ...] = ()


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
    resolved_thread: tuple[int, ...]
    resolved_words: tuple["ResolvedWord", ...]
    final_stack: tuple[int, ...]
    final_ip: int
    state_flags: int
    trace: tuple[TraceRow, ...]


@dataclass(frozen=True)
class WordBlueprint:
    name: str
    handler_id: int
    thread: tuple[ThreadCellToken, ...]


@dataclass(frozen=True)
class ResolvedWord:
    xt: int
    name: str
    handler_id: int
    dfa_index: int
    thread: tuple[int, ...]


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
    Scenario(
        name="jit-docol-then-jit-exit-then-jit-halt",
        thread=(
            "SUM23",
            int(dictionary.PrimitiveInstruction.HALT),
        ),
        expected_stack=(5,),
        expected_final_ip=1,
        expected_state_flags=STATE_HALT_REQUESTED,
        expected_trace_backends=("jit", "jit", "jit", "jit", "jit", "jit"),
        custom_words=(
            WordBlueprint(
                name="SUM23",
                handler_id=int(dictionary.PrimitiveInstruction.DOCOL),
                thread=(
                    int(dictionary.PrimitiveInstruction.LIT),
                    2,
                    int(dictionary.PrimitiveInstruction.LIT),
                    3,
                    int(dictionary.PrimitiveInstruction.ADD),
                    int(dictionary.PrimitiveInstruction.EXIT),
                ),
            ),
        ),
    ),
)
