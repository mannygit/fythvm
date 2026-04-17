"""Demonstrate the first Python-loop to lowered-handler seam."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Callable

from llvmlite import ir

from fythvm import dictionary
from fythvm.codegen import BoundStructView, StructField, StructHandle
from fythvm.codegen.llvm import compile_ir_module, configure_llvm


I32 = ir.IntType(32)
STATE_HALT_REQUESTED = 0x01
STACK_CAPACITY = 8


class LoweredLoopState(ctypes.Structure):
    _fields_ = [
        ("state_flags", ctypes.c_int32),
        ("ip", ctypes.c_int32),
        ("current_xt", ctypes.c_int32),
        ("stack_depth", ctypes.c_int32),
        ("data_stack", ctypes.c_int32 * STACK_CAPACITY),
    ]


class LoweredLoopStateView(BoundStructView):
    state_flags = StructField(0)
    ip = StructField(1)
    current_xt = StructField(2)
    stack_depth = StructField(3)
    data_stack = StructField(4)


STATE_HANDLE = StructHandle.from_ctypes(
    "lowered loop state",
    LoweredLoopState,
    view_type=LoweredLoopStateView,
)


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


@dataclass(frozen=True)
class LoweredExecutionControlIR:
    """Execution-control helper injected into lowered op bodies."""

    builder: ir.IRBuilder
    state: LoweredLoopStateView

    def request_halt(self) -> None:
        flags = self.state.state_flags.load(name="state_flags")
        updated = self.builder.or_(flags, I32(STATE_HALT_REQUESTED), name="halt_requested")
        self.state.state_flags.store(updated)


@dataclass(frozen=True)
class LoweredErrorExitIR:
    """Placeholder error-exit surface for lowered op signatures."""

    builder: ir.IRBuilder

    def __call__(self, code: str, detail: str) -> None:
        raise RuntimeError(
            "error-exit lowering is not modeled in this lab yet: "
            f"{code} {detail}"
        )


PythonHandler = Callable[[LoweredLoopState, tuple[int, ...]], str]
LoweredOp = Callable[..., None]


@dataclass(frozen=True)
class LoweredHandlerSpec:
    handler_id: int
    function_name: str
    op: LoweredOp
    note: str


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
        name="python-lit-then-jit-halt",
        thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            7,
            int(dictionary.PrimitiveInstruction.HALT),
        ),
        expected_stack=(7,),
        expected_final_ip=2,
        expected_state_flags=STATE_HALT_REQUESTED,
        expected_trace_backends=("python", "jit"),
    ),
)


def state_ir_type() -> ir.LiteralStructType:
    return STATE_HANDLE.ir_type


def state_handle() -> StructHandle:
    return STATE_HANDLE


def injected_ir_resources(
    *,
    builder: ir.IRBuilder,
    state: LoweredLoopStateView,
    descriptor: dictionary.InstructionDescriptor,
) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    requirements = descriptor.requirements
    if requirements.needs_execution_control:
        kwargs["control"] = LoweredExecutionControlIR(builder=builder, state=state)
    if requirements.needs_error_exit:
        kwargs["err"] = LoweredErrorExitIR(builder=builder)
    return kwargs


def op_halt_ir(
    builder: ir.IRBuilder,
    *,
    control: LoweredExecutionControlIR,
    err: LoweredErrorExitIR,
) -> None:
    """Emit HALT's local IR effect without owning wrapper termination."""

    _ = builder
    _ = err
    control.request_halt()


LOWERED_HANDLER_SPECS: dict[int, LoweredHandlerSpec] = {
    int(dictionary.PrimitiveInstruction.HALT): LoweredHandlerSpec(
        handler_id=int(dictionary.PrimitiveInstruction.HALT),
        function_name="lowered_halt",
        op=op_halt_ir,
        note="set HALT_REQUESTED in shared state and return to Python",
    )
}


def define_lowered_handler(module: ir.Module, spec: LoweredHandlerSpec) -> None:
    descriptor = dictionary.instruction_descriptor_for_handler_id(spec.handler_id)
    if descriptor is None:
        raise RuntimeError(f"missing descriptor for lowered handler id {spec.handler_id}")

    state_ptr_type = state_ir_type().as_pointer()
    function_type = ir.FunctionType(ir.VoidType(), [state_ptr_type])
    function = ir.Function(module, function_type, name=spec.function_name)
    block = function.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)

    state_ptr = function.args[0]
    state_ptr.name = "state"
    state = state_handle().bind(builder, state_ptr)
    kwargs = injected_ir_resources(builder=builder, state=state, descriptor=descriptor)
    spec.op(builder, **kwargs)
    builder.ret_void()


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


def build_lowered_runtime() -> tuple[
    ir.Module,
    object,
    dict[int, ctypes._CFuncPtr],  # type: ignore[attr-defined]
    dict[int, int],
]:
    module = ir.Module(name="lowered_handler_seam")
    for spec in LOWERED_HANDLER_SPECS.values():
        define_lowered_handler(module, spec)

    compiled = compile_ir_module(module)
    lowered_functions: dict[int, ctypes._CFuncPtr] = {}  # type: ignore[attr-defined]
    lowered_addresses: dict[int, int] = {}
    for handler_id, spec in LOWERED_HANDLER_SPECS.items():
        address = compiled.function_address(spec.function_name)
        lowered_addresses[handler_id] = address
        lowered_functions[handler_id] = ctypes.CFUNCTYPE(
            None,
            ctypes.POINTER(LoweredLoopState),
        )(address)
    return module, compiled, lowered_functions, lowered_addresses


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


def print_scenario(
    scenario: Scenario,
    result: ScenarioResult,
    *,
    lowered_addresses: dict[int, int],
) -> None:
    print(f"== {scenario.name.upper()} ==")
    print("thread:")
    for line in decompile_thread(scenario.thread):
        print(f"  {line}")
    halt_id = int(dictionary.PrimitiveInstruction.HALT)
    if halt_id in lowered_addresses:
        print(f"lowered HALT address: 0x{lowered_addresses[halt_id]:x}")
    print(
        "expected:"
        f" stack={list(scenario.expected_stack)}"
        f" final_ip={scenario.expected_final_ip}"
        f" state_flags=0x{scenario.expected_state_flags:x}"
        f" backends={list(scenario.expected_trace_backends)}"
    )
    for row in result.trace:
        print(f"step {row.step}: ip={row.ip} word={row.word} backend={row.backend}")
        print(f"  stack before: {list(row.stack_before)}")
        print(f"  state flags before: 0x{row.state_flags_before:x}")
        print(f"  note: {row.note}")
        print(f"  stack after: {list(row.stack_after)}")
        print(f"  state flags after: 0x{row.state_flags_after:x}")
    print(
        f"result: stack={list(result.final_stack)} final_ip={result.final_ip} "
        f"state_flags=0x{result.state_flags:x}"
    )
    print("expectation check: ok")
    print()


def main() -> None:
    configure_llvm()
    module, compiled, lowered_functions, lowered_addresses = build_lowered_runtime()

    print("== Question ==")
    print("What is the smallest useful seam between a Python dispatch loop and one lowered handler?")
    print()
    print("== Generated IR ==")
    print(compiled.llvm_ir.rstrip())
    print()
    print("== Takeaway ==")
    print("Inject lowered op resources from HandlerRequirements; let the wrapper own ret and let Python own dispatch.")
    print()

    for scenario in SCENARIOS:
        result = execute_scenario(scenario, lowered_functions)
        assert_result_matches(scenario, result)
        print_scenario(scenario, result, lowered_addresses=lowered_addresses)


if __name__ == "__main__":
    main()
