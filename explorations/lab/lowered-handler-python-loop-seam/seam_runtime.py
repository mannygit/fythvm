from __future__ import annotations

import ctypes
from dataclasses import dataclass

from fythvm import dictionary

from seam_lowering import LOWERED_HANDLER_SPECS
from seam_model import Scenario, ScenarioResult, TraceRow, WordSpec
from seam_return import return_stack_depth
from seam_state import (
    LoweredLoopState,
    RETURN_STACK_CAPACITY,
    STACK_CAPACITY,
    state_flags_value,
)
from seam_thread import materialize_thread_buffer


@dataclass(frozen=True)
class ThreadRecord:
    name: str
    thread: tuple[int, ...]


def stack_snapshot(state: LoweredLoopState) -> tuple[int, ...]:
    sp = int(state.sp)
    window = [int(state.stack[index]) for index in range(sp, STACK_CAPACITY)]
    return tuple(reversed(window))


def projected_data_stack_depth(depth: int, requirements: dictionary.HandlerRequirements) -> int:
    return depth - requirements.min_data_stack_in + requirements.min_data_stack_out_space


def projected_return_stack_depth(depth: int, requirements: dictionary.HandlerRequirements) -> int:
    return depth - requirements.min_return_stack_in + requirements.min_return_stack_out_space


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


def ensure_return_stack_requirements(
    state: LoweredLoopState,
    descriptor: dictionary.InstructionDescriptor,
) -> None:
    requirements = descriptor.requirements
    depth = return_stack_depth(state)
    if depth < requirements.min_return_stack_in:
        raise RuntimeError(
            f"{descriptor.key} requires {requirements.min_return_stack_in} return-stack items,"
            f" got {depth}"
        )

    projected_depth = projected_return_stack_depth(depth, requirements)
    if projected_depth > RETURN_STACK_CAPACITY:
        raise RuntimeError(
            f"{descriptor.key} would overflow lab return stack:"
            f" projected depth {projected_depth}, capacity {RETURN_STACK_CAPACITY}"
        )


def decompile_thread(
    thread: tuple[int, ...],
    *,
    custom_words: tuple[WordSpec, ...] = (),
) -> tuple[str, ...]:
    lines: list[str] = []
    ip = 0
    custom_word_map = {word.xt: word for word in custom_words}
    while ip < len(thread):
        xt = int(thread[ip])
        if xt in custom_word_map:
            lines.append(f"{ip}: {custom_word_map[xt].name}")
            ip += 1
            continue

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
    state.rsp = RETURN_STACK_CAPACITY

    entry_buffer = materialize_thread_buffer(scenario.thread)
    entry_ptr = ctypes.cast(entry_buffer, ctypes.POINTER(ctypes.c_int32))
    state.thread_cells = entry_ptr
    state.thread_length = len(scenario.thread)

    thread_buffers: list[ctypes.Array[ctypes.c_int32]] = [entry_buffer]
    thread_records: dict[int, ThreadRecord] = {
        pointer_key(entry_ptr): ThreadRecord(name="entry", thread=scenario.thread)
    }
    custom_word_map = {word.xt: word for word in scenario.custom_words}
    custom_thread_ptrs: dict[int, ctypes._Pointer[ctypes.c_int32]] = {}  # type: ignore[attr-defined]

    for word in scenario.custom_words:
        buffer = materialize_thread_buffer(word.thread)
        ptr = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_int32))
        thread_buffers.append(buffer)
        thread_records[pointer_key(ptr)] = ThreadRecord(name=word.name, thread=word.thread)
        custom_thread_ptrs[word.xt] = ptr

    trace_rows: list[TraceRow] = []
    state_ptr = ctypes.pointer(state)
    null_thread_ptr = ctypes.POINTER(ctypes.c_int32)()

    while not halt_requested(state):
        current_record = current_thread_record(state, thread_records)
        ip = int(state.ip)
        if ip >= len(current_record.thread):
            raise RuntimeError(f"{current_record.name} stepped past end without HALT or EXIT")

        xt = int(current_record.thread[ip])
        state.current_xt = xt
        descriptor, word_name = resolve_word_descriptor(xt, custom_word_map)

        if xt in custom_word_map:
            word = custom_word_map[xt]
            state.current_word_thread_cells = custom_thread_ptrs[xt]
            state.current_word_thread_length = len(word.thread)
        else:
            state.current_word_thread_cells = null_thread_ptr
            state.current_word_thread_length = 0

        ensure_data_stack_requirements(state, descriptor)
        ensure_return_stack_requirements(state, descriptor)
        stack_before = stack_snapshot(state)
        flags_before = state_flags_value(state)

        if descriptor.handler_id in LOWERED_HANDLER_SPECS:
            backend = "jit"
            lowered_functions[descriptor.handler_id](state_ptr)
            note = LOWERED_HANDLER_SPECS[descriptor.handler_id].note
        else:
            raise RuntimeError(f"unsupported handler in seam lab: {descriptor.key}")

        trace_rows.append(
            TraceRow(
                step=len(trace_rows),
                ip=ip,
                word=word_name,
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


def pointer_key(ptr: ctypes._Pointer[ctypes.c_int32]) -> int:  # type: ignore[attr-defined]
    value = ctypes.cast(ptr, ctypes.c_void_p).value
    if value is None:
        raise RuntimeError("expected a non-null thread pointer")
    return int(value)


def current_thread_record(
    state: LoweredLoopState,
    thread_records: dict[int, ThreadRecord],
) -> ThreadRecord:
    key = pointer_key(state.thread_cells)
    if key not in thread_records:
        raise RuntimeError("state.thread_cells does not resolve to a known thread record")
    return thread_records[key]


def resolve_word_descriptor(
    xt: int,
    custom_word_map: dict[int, WordSpec],
) -> tuple[dictionary.InstructionDescriptor, str]:
    if xt in custom_word_map:
        word = custom_word_map[xt]
        descriptor = dictionary.instruction_descriptor_for_handler_id(word.handler_id)
        if descriptor is None:
            raise RuntimeError(f"no descriptor for custom word handler id {word.handler_id}")
        return descriptor, word.name

    descriptor = dictionary.instruction_descriptor_for_handler_id(xt)
    if descriptor is None:
        raise RuntimeError(f"no descriptor for xt {xt}")
    return descriptor, descriptor.key

