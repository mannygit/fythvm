from __future__ import annotations

import ctypes
from typing import Callable

from fythvm import dictionary

from seam_lowering import LOWERED_HANDLER_SPECS
from seam_model import Scenario, ScenarioResult, TraceRow
from seam_state import LoweredLoopState, STACK_CAPACITY, STATE_HALT_REQUESTED


PythonHandler = Callable[[LoweredLoopState, tuple[int, ...]], str]


def stack_snapshot(state: LoweredLoopState) -> tuple[int, ...]:
    return tuple(int(state.data_stack[index]) for index in range(int(state.stack_depth)))


def stack_push(state: LoweredLoopState, value: int) -> None:
    depth = int(state.stack_depth)
    if depth >= STACK_CAPACITY:
        raise RuntimeError("stack overflow in lab state")
    state.data_stack[depth] = int(value)
    state.stack_depth = depth + 1


def projected_data_stack_depth(
    depth: int,
    requirements: dictionary.HandlerRequirements,
) -> int:
    return depth - requirements.min_data_stack_in + requirements.min_data_stack_out_space


def ensure_data_stack_requirements(
    state: LoweredLoopState,
    descriptor: dictionary.InstructionDescriptor,
) -> None:
    requirements = descriptor.requirements
    depth = int(state.stack_depth)
    if depth < requirements.min_data_stack_in:
        raise RuntimeError(
            f"{descriptor.key} requires {requirements.min_data_stack_in} data-stack items,"
            f" got {depth}"
        )

    projected_depth = projected_data_stack_depth(depth, requirements)
    if projected_depth > STACK_CAPACITY:
        raise RuntimeError(
            f"{descriptor.key} would overflow lab data stack:"
            f" projected depth {projected_depth}, capacity {STACK_CAPACITY}"
        )


def decompile_thread(thread: tuple[int, ...]) -> tuple[str, ...]:
    lines: list[str] = []
    ip = 0
    while ip < len(thread):
        xt = int(thread[ip])
        descriptor = dictionary.instruction_descriptor_for_handler_id(xt)
        if descriptor is None:
            lines.append(f"{ip}: <unknown {xt}>")
            ip += 1
            continue
        if descriptor.key == "LIT":
            operand = int(thread[ip + 1]) if ip + 1 < len(thread) else "<missing>"
            lines.append(f"{ip}: LIT {operand}")
            ip += 2
            continue
        lines.append(f"{ip}: {descriptor.key}")
        ip += 1
    return tuple(lines)


def handle_python_lit(state: LoweredLoopState, thread: tuple[int, ...]) -> str:
    operand_ip = int(state.ip) + 1
    if operand_ip >= len(thread):
        raise RuntimeError("LIT missing operand")
    stack_push(state, int(thread[operand_ip]))
    state.ip = operand_ip
    return f"push literal {int(thread[operand_ip])}"


PYTHON_HANDLER_BY_ID: dict[int, PythonHandler] = {
    int(dictionary.PrimitiveInstruction.LIT): handle_python_lit,
}


def execute_scenario(
    scenario: Scenario,
    lowered_functions: dict[int, ctypes._CFuncPtr],  # type: ignore[attr-defined]
) -> ScenarioResult:
    state = LoweredLoopState()
    trace_rows: list[TraceRow] = []

    while not (int(state.state_flags) & STATE_HALT_REQUESTED):
        ip = int(state.ip)
        if ip >= len(scenario.thread):
            raise RuntimeError("thread stepped past end without HALT")

        xt = int(scenario.thread[ip])
        state.current_xt = xt
        descriptor = dictionary.instruction_descriptor_for_handler_id(xt)
        if descriptor is None:
            raise RuntimeError(f"no descriptor for xt {xt}")

        ensure_data_stack_requirements(state, descriptor)
        stack_before = stack_snapshot(state)
        flags_before = int(state.state_flags)

        if xt in PYTHON_HANDLER_BY_ID:
            backend = "python"
            note = PYTHON_HANDLER_BY_ID[xt](state, scenario.thread)
        elif xt in LOWERED_HANDLER_SPECS:
            backend = "jit"
            lowered_functions[xt](ctypes.pointer(state))
            note = LOWERED_HANDLER_SPECS[xt].note
        else:
            raise RuntimeError(f"unsupported handler in seam lab: {descriptor.key}")

        trace_rows.append(
            TraceRow(
                step=len(trace_rows),
                ip=ip,
                word=descriptor.key,
                backend=backend,
                stack_before=stack_before,
                stack_after=stack_snapshot(state),
                state_flags_before=flags_before,
                state_flags_after=int(state.state_flags),
                note=note,
            )
        )

        if int(state.state_flags) & STATE_HALT_REQUESTED:
            break
        state.ip = int(state.ip) + 1

    return ScenarioResult(
        final_stack=stack_snapshot(state),
        final_ip=int(state.ip),
        state_flags=int(state.state_flags),
        trace=tuple(trace_rows),
    )


def assert_result_matches(scenario: Scenario, result: ScenarioResult) -> None:
    assert result.final_stack == scenario.expected_stack, (
        f"{scenario.name}: expected stack {scenario.expected_stack}, got {result.final_stack}"
    )
    assert result.final_ip == scenario.expected_final_ip, (
        f"{scenario.name}: expected final ip {scenario.expected_final_ip}, got {result.final_ip}"
    )
    assert result.state_flags == scenario.expected_state_flags, (
        f"{scenario.name}: expected state flags {scenario.expected_state_flags}, got {result.state_flags}"
    )
    actual_backends = tuple(row.backend for row in result.trace)
    assert actual_backends == scenario.expected_trace_backends, (
        f"{scenario.name}: expected backends {scenario.expected_trace_backends}, got {actual_backends}"
    )
