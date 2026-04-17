from __future__ import annotations

import ctypes
from fythvm import dictionary

from seam_lowering import LOWERED_HANDLER_SPECS
from seam_model import Scenario, ScenarioResult, TraceRow
from seam_state import LoweredLoopState, STACK_CAPACITY, state_flags_value
from seam_thread import materialize_thread_buffer


def stack_snapshot(state: LoweredLoopState) -> tuple[int, ...]:
    sp = int(state.sp)
    window = [int(state.stack[index]) for index in range(sp, STACK_CAPACITY)]
    return tuple(reversed(window))


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
    depth = STACK_CAPACITY - int(state.sp)
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
        if descriptor.key == "BRANCH":
            operand = int(thread[ip + 1]) if ip + 1 < len(thread) else "<missing>"
            lines.append(f"{ip}: BRANCH {operand}")
            ip += 2
            continue
        if descriptor.key == "0BRANCH":
            operand = int(thread[ip + 1]) if ip + 1 < len(thread) else "<missing>"
            lines.append(f"{ip}: 0BRANCH {operand}")
            ip += 2
            continue
        lines.append(f"{ip}: {descriptor.key}")
        ip += 1
    return tuple(lines)


def halt_requested(state: LoweredLoopState) -> bool:
    return bool(int(state.halt_requested))


def execute_scenario(
    scenario: Scenario,
    lowered_functions: dict[int, ctypes._CFuncPtr],  # type: ignore[attr-defined]
) -> ScenarioResult:
    state = LoweredLoopState()
    state.sp = STACK_CAPACITY
    thread_buffer = materialize_thread_buffer(scenario.thread)
    state.thread_cells = ctypes.cast(thread_buffer, ctypes.POINTER(ctypes.c_int32))
    state.thread_length = len(scenario.thread)
    trace_rows: list[TraceRow] = []

    while not halt_requested(state):
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
        flags_before = state_flags_value(state)

        if xt in LOWERED_HANDLER_SPECS:
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
                state_flags_after=state_flags_value(state),
                note=note,
            )
        )

        if halt_requested(state):
            break
        state.ip = int(state.ip) + 1

    return ScenarioResult(
        final_stack=stack_snapshot(state),
        final_ip=int(state.ip),
        state_flags=state_flags_value(state),
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
