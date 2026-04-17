from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Callable

from llvmlite import ir

from fythvm import dictionary
from fythvm.codegen import BoundStackAccess, StructViewStackAccess
from fythvm.codegen.llvm import compile_ir_module

from seam_state import LoweredLoopState, LoweredLoopStateView, STATE_HANDLE
from seam_thread import ThreadCursorIR, ThreadJumpIR


I1 = ir.IntType(1)
LoweredOp = Callable[..., None]
HALT_REQUESTED_BIT = I1(1)


@dataclass(frozen=True)
class LoweredExecutionControlIR:
    """Execution-control helper injected into lowered op bodies."""

    builder: ir.IRBuilder
    state: LoweredLoopStateView

    def request_halt(self) -> None:
        self.state.halt_requested.store(HALT_REQUESTED_BIT)


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
    if requirements.min_data_stack_in > 0 or requirements.min_data_stack_out_space > 0:
        kwargs["data_stack"] = StructViewStackAccess(state).bind(builder)
    if requirements.needs_thread_cursor:
        kwargs["thread_cursor"] = ThreadCursorIR(builder=builder, state=state)
    if requirements.needs_thread_jump:
        kwargs["thread_jump"] = ThreadJumpIR(builder=builder, state=state)
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


def op_lit_ir(
    builder: ir.IRBuilder,
    *,
    data_stack: BoundStackAccess,
    thread_cursor: ThreadCursorIR,
    err: LoweredErrorExitIR,
) -> None:
    """Emit LIT's local IR effect without owning wrapper termination."""

    _ = builder
    _ = err
    literal = thread_cursor.read_inline_cell()
    data_stack.push(literal, name="lit_sp")


def op_add_ir(
    builder: ir.IRBuilder,
    *,
    data_stack: BoundStackAccess,
    err: LoweredErrorExitIR,
) -> None:
    """Emit ADD's local IR effect without owning wrapper termination."""

    _ = err
    data_stack.binary_reduce(
        lambda ir_builder, lhs, rhs: ir_builder.add(lhs, rhs, name="add_result"),
        result_index_name="add_result_index",
        result_ptr_name="add_result_ptr",
    )


def op_branch_ir(
    builder: ir.IRBuilder,
    *,
    thread_cursor: ThreadCursorIR,
    thread_jump: ThreadJumpIR,
    err: LoweredErrorExitIR,
) -> None:
    """Emit BRANCH's local IR effect without owning wrapper termination."""

    _ = builder
    _ = err
    offset = thread_cursor.read_inline_cell()
    thread_jump.branch_relative(offset)


LOWERED_HANDLER_SPECS: dict[int, LoweredHandlerSpec] = {
    int(dictionary.PrimitiveInstruction.LIT): LoweredHandlerSpec(
        handler_id=int(dictionary.PrimitiveInstruction.LIT),
        function_name="lowered_lit",
        op=op_lit_ir,
        note="read one inline cell after ip and push it through the lowered stack view",
    ),
    int(dictionary.PrimitiveInstruction.ADD): LoweredHandlerSpec(
        handler_id=int(dictionary.PrimitiveInstruction.ADD),
        function_name="lowered_add",
        op=op_add_ir,
        note="reduce the top two stack cells through the lowered stack view",
    ),
    int(dictionary.PrimitiveInstruction.BRANCH): LoweredHandlerSpec(
        handler_id=int(dictionary.PrimitiveInstruction.BRANCH),
        function_name="lowered_branch",
        op=op_branch_ir,
        note="read one inline branch offset and redirect ip through the lowered thread surfaces",
    ),
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
