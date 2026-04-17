from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Callable

from llvmlite import ir

from fythvm import dictionary
from fythvm.codegen.llvm import compile_ir_module

from seam_state import LoweredLoopState, LoweredLoopStateView, STATE_HANDLE, STATE_HALT_REQUESTED


I32 = ir.IntType(32)
LoweredOp = Callable[..., None]


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


@dataclass(frozen=True)
class LoweredHandlerSpec:
    handler_id: int
    function_name: str
    op: LoweredOp
    note: str


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

    state_ptr_type = STATE_HANDLE.ir_type.as_pointer()
    function_type = ir.FunctionType(ir.VoidType(), [state_ptr_type])
    function = ir.Function(module, function_type, name=spec.function_name)
    block = function.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)

    state_ptr = function.args[0]
    state_ptr.name = "state"
    state = STATE_HANDLE.bind(builder, state_ptr)
    kwargs = injected_ir_resources(builder=builder, state=state, descriptor=descriptor)
    spec.op(builder, **kwargs)
    builder.ret_void()


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
