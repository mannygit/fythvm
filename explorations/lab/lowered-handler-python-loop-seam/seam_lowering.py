from __future__ import annotations

import ctypes
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from llvmlite import binding, ir

from fythvm import dictionary
from fythvm.codegen import (
    BoundStackAccess,
    ReturnStackIR,
    StructViewStackAccess,
    ThreadCursorIR,
    ThreadRefIR,
)
from fythvm.codegen.llvm import compile_ir_module

from seam_state import LoweredLoopState, LoweredLoopStateView, STATE_HANDLE


I1 = ir.IntType(1)
I32 = ir.IntType(32)
LoweredContinuationValue = ir.Value | None
LoweredOp = Callable[..., LoweredContinuationValue]
TRUE_BIT = I1(1)
VOID = ir.VoidType()


@dataclass(frozen=True)
class LoweredExecutionControlIR:
    """Execution-control helper injected into lowered op bodies."""

    builder: ir.IRBuilder
    state: LoweredLoopStateView

    def request_halt(self) -> None:
        self.state.halt_requested.store(TRUE_BIT)

    def enter_thread(self, *, thread: ThreadRefIR, return_stack: ReturnStackIR) -> None:
        current_thread = ThreadRefIR(
            cells=self.state.thread_cells.load(name="current_thread_cells"),
            length=self.state.thread_length.load(name="current_thread_length"),
        )
        current_ip = self.state.ip.load(name="current_ip")
        return_ip = self.builder.add(current_ip, I32(1), name="return_ip")
        return_stack.push_frame(thread=current_thread, return_ip=return_ip)
        self.state.thread_cells.store(thread.cells)
        self.state.thread_length.store(thread.length)
        self.state.ip.store(I32(0))

    def return_to_thread(self, *, thread: ThreadRefIR, return_ip: ir.Value) -> None:
        self.state.thread_cells.store(thread.cells)
        self.state.thread_length.store(thread.length)
        self.state.ip.store(return_ip)


@dataclass(frozen=True)
class SeamLabeledContinuationIR:
    """SSA continuation outcome helper for special-case handlers like 0BRANCH."""

    builder: ir.IRBuilder
    label_ids: dict[str, int]

    def select_between(self, condition: ir.Value, *, when_true: str, when_false: str) -> ir.Value:
        true_id = I32(self.label_ids[when_true])
        false_id = I32(self.label_ids[when_false])
        return self.builder.select(
            condition,
            true_id,
            false_id,
            name="continuation_label",
        )


@dataclass(frozen=True)
class SeamThreadJumpIR:
    """Thread-jump helper layered over the shared ip field."""

    builder: ir.IRBuilder
    state: LoweredLoopStateView
    ip_field_name: str = "ip"

    def branch_relative(self, offset: ir.Value) -> None:
        ip_field = getattr(self.state, self.ip_field_name)
        current_ip = ip_field.load(name="branch_operand_ip")
        offset_base_ip = self.builder.add(current_ip, offset, name="branch_offset_base_ip")
        target_ip = self.builder.add(offset_base_ip, I32(1), name="branch_target_ip")
        ip_field.store(target_ip)

    def branch_if_zero(self, value: ir.Value, offset: ir.Value) -> ir.Value:
        ip_field = getattr(self.state, self.ip_field_name)
        current_ip = ip_field.load(name="zbranch_operand_ip")
        offset_base_ip = self.builder.add(current_ip, offset, name="zbranch_offset_base_ip")
        target_ip = self.builder.add(offset_base_ip, I32(1), name="zbranch_target_ip")
        should_branch = self.builder.icmp_signed("==", value, I32(0), name="zbranch_is_zero")
        next_ip = self.builder.select(should_branch, target_ip, current_ip, name="zbranch_next_ip")
        ip_field.store(next_ip)
        return should_branch


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


def lowered_step_function_name() -> str:
    return "lowered_step"


def lowered_run_function_name() -> str:
    return "lowered_run"


@dataclass(frozen=True)
class LoweredInterpreterEntrypoint:
    mode: "LoweredInterpreterMode"
    function_name: str
    cfunc: ctypes._CFuncPtr  # type: ignore[attr-defined]
    address: int
    description: str


class LoweredInterpreterMode(Enum):
    STEP = "step"
    RUN = "run"


@dataclass(frozen=True)
class LoweredRuntimeArtifacts:
    module: ir.Module
    compiled: object
    step: LoweredInterpreterEntrypoint
    run: LoweredInterpreterEntrypoint


def injected_ir_resources(
    *,
    builder: ir.IRBuilder,
    state: LoweredLoopStateView,
    descriptor: dictionary.InstructionDescriptor,
    current_word: dictionary.CurrentWordIR | None = None,
    labeled_continuation: SeamLabeledContinuationIR | None = None,
) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    requirements = descriptor.requirements
    if requirements.min_data_stack_in > 0 or requirements.min_data_stack_out_space > 0:
        kwargs["data_stack"] = StructViewStackAccess(state).bind(builder)
    if requirements.needs_thread_cursor:
        kwargs["thread_cursor"] = ThreadCursorIR(builder=builder, state=state)
    if requirements.needs_thread_jump:
        kwargs["thread_jump"] = SeamThreadJumpIR(builder=builder, state=state)
    if requirements.needs_current_xt:
        if current_word is None:
            raise RuntimeError(f"{descriptor.key} requested current_word without a surface")
        kwargs["current_word"] = current_word
    if requirements.needs_return_stack:
        kwargs["return_stack"] = ReturnStackIR(builder=builder, state=state)
    if requirements.needs_execution_control:
        kwargs["control"] = LoweredExecutionControlIR(builder=builder, state=state)
    if requirements.needs_error_exit:
        kwargs["err"] = LoweredErrorExitIR(builder=builder)
    if requirements.needs_labeled_continuation:
        if labeled_continuation is None:
            raise RuntimeError(f"{descriptor.key} requested labeled continuation without a surface")
        kwargs["labeled_continuation"] = labeled_continuation
    return kwargs


def op_halt_ir(
    builder: ir.IRBuilder,
    *,
    control: LoweredExecutionControlIR,
    err: LoweredErrorExitIR,
) -> LoweredContinuationValue:
    """Emit HALT's local IR effect without owning whole-step termination."""

    _ = builder
    _ = err
    control.request_halt()
    return None


def op_lit_ir(
    builder: ir.IRBuilder,
    *,
    data_stack: BoundStackAccess,
    thread_cursor: ThreadCursorIR,
    err: LoweredErrorExitIR,
) -> LoweredContinuationValue:
    """Emit LIT's local IR effect without owning whole-step termination."""

    _ = builder
    _ = err
    literal = thread_cursor.read_inline_cell()
    data_stack.push(literal, name="lit_sp")
    return None


def op_add_ir(
    builder: ir.IRBuilder,
    *,
    data_stack: BoundStackAccess,
    err: LoweredErrorExitIR,
) -> LoweredContinuationValue:
    """Emit ADD's local IR effect without owning whole-step termination."""

    _ = err
    data_stack.binary_reduce(
        lambda ir_builder, lhs, rhs: ir_builder.add(lhs, rhs, name="add_result"),
        result_index_name="add_result_index",
        result_ptr_name="add_result_ptr",
    )
    return None


def op_branch_ir(
    builder: ir.IRBuilder,
    *,
    thread_cursor: ThreadCursorIR,
    thread_jump: SeamThreadJumpIR,
    err: LoweredErrorExitIR,
) -> LoweredContinuationValue:
    """Emit BRANCH's local IR effect without owning whole-step termination."""

    _ = builder
    _ = err
    offset = thread_cursor.read_inline_cell()
    thread_jump.branch_relative(offset)
    return None


def op_zbranch_ir(
    builder: ir.IRBuilder,
    *,
    data_stack: BoundStackAccess,
    thread_cursor: ThreadCursorIR,
    thread_jump: SeamThreadJumpIR,
    labeled_continuation: SeamLabeledContinuationIR,
    err: LoweredErrorExitIR,
) -> LoweredContinuationValue:
    """Emit 0BRANCH's local IR effect without owning whole-step termination."""

    _ = err
    condition = data_stack.peek(name="zbranch_condition")
    offset = thread_cursor.read_inline_cell()
    data_stack.drop(name="zbranch_next_sp")
    should_branch = thread_jump.branch_if_zero(condition, offset)
    return labeled_continuation.select_between(
        should_branch,
        when_true="branch_taken",
        when_false="branch_fallthrough",
    )


def op_docol_ir(
    builder: ir.IRBuilder,
    *,
    current_word: dictionary.CurrentWordIR,
    return_stack: ReturnStackIR,
    control: LoweredExecutionControlIR,
    err: LoweredErrorExitIR,
) -> LoweredContinuationValue:
    """Emit DOCOL's local IR effect without owning whole-step termination."""

    _ = builder
    _ = err
    word_thread_lengths = current_word.state.word_thread_lengths.load(name="word_thread_lengths")
    control.enter_thread(
        thread=current_word.thread_ref(word_thread_lengths),
        return_stack=return_stack,
    )
    return None


def op_exit_ir(
    builder: ir.IRBuilder,
    *,
    return_stack: ReturnStackIR,
    control: LoweredExecutionControlIR,
    err: LoweredErrorExitIR,
) -> LoweredContinuationValue:
    """Emit EXIT's local IR effect without owning whole-step termination."""

    _ = builder
    _ = err
    thread, return_ip = return_stack.pop_frame()
    control.return_to_thread(thread=thread, return_ip=return_ip)
    return None


def op_execute_ir(
    builder: ir.IRBuilder,
    *,
    data_stack: BoundStackAccess,
    current_word: dictionary.CurrentWordIR,
    err: LoweredErrorExitIR,
) -> LoweredContinuationValue:
    """Emit EXECUTE by installing a new current xt and re-entering dispatch."""

    _ = builder
    _ = err
    execute_xt = data_stack.peek(name="execute_xt")
    data_stack.drop(name="execute_next_sp")
    current_word.install_xt(execute_xt)
    return None


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
    int(dictionary.PrimitiveInstruction.ZBRANCH): LoweredHandlerSpec(
        handler_id=int(dictionary.PrimitiveInstruction.ZBRANCH),
        function_name="lowered_zbranch",
        op=op_zbranch_ir,
        note="pop one stack cell, read one inline branch offset, and redirect ip when the value is zero",
    ),
    int(dictionary.PrimitiveInstruction.DOCOL): LoweredHandlerSpec(
        handler_id=int(dictionary.PrimitiveInstruction.DOCOL),
        function_name="lowered_docol",
        op=op_docol_ir,
        note="push a return frame and enter the current word thread through lowered thread surfaces",
    ),
    int(dictionary.PrimitiveInstruction.EXIT): LoweredHandlerSpec(
        handler_id=int(dictionary.PrimitiveInstruction.EXIT),
        function_name="lowered_exit",
        op=op_exit_ir,
        note="pop one return frame and restore the caller thread through lowered control surfaces",
    ),
    int(dictionary.PrimitiveInstruction.EXECUTE): LoweredHandlerSpec(
        handler_id=int(dictionary.PrimitiveInstruction.EXECUTE),
        function_name="lowered_execute",
        op=op_execute_ir,
        note="pop an xt from the data stack, install it as the current word, and re-enter lowered dispatch",
    ),
    int(dictionary.PrimitiveInstruction.HALT): LoweredHandlerSpec(
        handler_id=int(dictionary.PrimitiveInstruction.HALT),
        function_name="lowered_halt",
        op=op_halt_ir,
        note="set HALT_REQUESTED in shared state and return to Python",
    )
}


def emit_fetch_current_xt(
    builder: ir.IRBuilder,
    state: LoweredLoopStateView,
    *,
    name_prefix: str,
) -> ir.Value:
    current_ip = state.ip.load(name=f"{name_prefix}_ip")
    thread_cells = state.thread_cells.load(name=f"{name_prefix}_thread_cells")
    xt_ptr = builder.gep(thread_cells, [current_ip], inbounds=True, name=f"{name_prefix}_xt_ptr")
    current_xt = builder.load(xt_ptr, name=f"{name_prefix}_xt")
    state.current_xt.store(current_xt)
    return current_xt


def emit_dispatch_current_word(
    *,
    builder: ir.IRBuilder,
    state: LoweredLoopStateView,
    dispatch_current_block: ir.Block,
    dispatch_custom_block: ir.Block,
    dispatch_primitive_block: ir.Block,
    dispatch_resolved_block: ir.Block,
    name_prefix: str,
) -> dictionary.CurrentWordIR:
    with builder.goto_block(dispatch_current_block):
        return dictionary.CurrentWordIR.resolve_from_state(
            builder=builder,
            state=state,
            dispatch_custom_block=dispatch_custom_block,
            dispatch_primitive_block=dispatch_primitive_block,
            dispatch_resolved_block=dispatch_resolved_block,
            name_prefix=name_prefix,
        )


def _continuation_block_for_kind(
    continuation: dictionary.ContinuationKind,
    *,
    advance_ip_block: ir.Block,
    refetch_block: ir.Block,
    dispatch_current_block: ir.Block,
    halt_block: ir.Block,
) -> ir.Block:
    if continuation is dictionary.ContinuationKind.FALLTHROUGH:
        return advance_ip_block
    if continuation is dictionary.ContinuationKind.EXACT_IP:
        return refetch_block
    if continuation is dictionary.ContinuationKind.DISPATCH_CURRENT:
        return dispatch_current_block
    if continuation is dictionary.ContinuationKind.HALT:
        return halt_block
    raise RuntimeError(f"unsupported continuation kind for direct branch: {continuation.value}")


def emit_descriptor_continuation(
    *,
    builder: ir.IRBuilder,
    descriptor: dictionary.InstructionDescriptor,
    advance_ip_block: ir.Block,
    refetch_block: ir.Block,
    dispatch_current_block: ir.Block,
    halt_block: ir.Block,
    labeled_continuation_value: ir.Value | None,
) -> None:
    continuation = descriptor.continuation
    if continuation is not dictionary.ContinuationKind.LABELED:
        builder.branch(
            _continuation_block_for_kind(
                continuation,
                advance_ip_block=advance_ip_block,
                refetch_block=refetch_block,
                dispatch_current_block=dispatch_current_block,
                halt_block=halt_block,
            )
        )
        return

    if labeled_continuation_value is None:
        raise RuntimeError(f"{descriptor.key} requested labeled continuation without an SSA value")

    default_block = builder.append_basic_block(f"{descriptor.key.lower()}_continuation_default")
    switch = builder.switch(labeled_continuation_value, default_block)
    for label_index, (label_name, target_kind) in enumerate(descriptor.continuation_labels):
        case_block = builder.append_basic_block(f"{descriptor.key.lower()}_{label_name}")
        switch.add_case(I32(label_index), case_block)
        with builder.goto_block(case_block):
            builder.branch(
                _continuation_block_for_kind(
                    target_kind,
                    advance_ip_block=advance_ip_block,
                    refetch_block=refetch_block,
                    dispatch_current_block=dispatch_current_block,
                    halt_block=halt_block,
                )
            )

    with builder.goto_block(default_block):
        builder.branch(halt_block)


def define_lowered_interpreter(
    module: ir.Module,
    *,
    function_name: str,
    run_to_completion: bool,
) -> None:
    state_ptr_type = STATE_HANDLE.ir_type.as_pointer()
    function = ir.Function(
        module,
        ir.FunctionType(VOID, [state_ptr_type]),
        name=function_name,
    )
    builder = ir.IRBuilder(function.append_basic_block(name="entry"))
    state_ptr = function.args[0]
    state_ptr.name = "state"
    state = STATE_HANDLE.bind(builder, state_ptr)
    fetch_block = function.append_basic_block("fetch")
    dispatch_current_block = function.append_basic_block("dispatch_current_word")
    dispatch_custom_block = function.append_basic_block("dispatch_custom_word")
    dispatch_primitive_block = function.append_basic_block("dispatch_primitive")
    dispatch_resolved_block = function.append_basic_block("dispatch_resolved")
    advance_ip_block = function.append_basic_block("advance_ip")
    refetch_block = function.append_basic_block("refetch")
    halt_block = function.append_basic_block("halt")
    return_block = function.append_basic_block("return")
    builder.branch(fetch_block)

    with builder.goto_block(fetch_block):
        emit_fetch_current_xt(builder, state, name_prefix=f"{function_name}_fetch")
        builder.branch(dispatch_current_block)

    current_word = emit_dispatch_current_word(
        builder=builder,
        state=state,
        dispatch_current_block=dispatch_current_block,
        dispatch_custom_block=dispatch_custom_block,
        dispatch_primitive_block=dispatch_primitive_block,
        dispatch_resolved_block=dispatch_resolved_block,
        name_prefix=function_name,
    )

    builder.position_at_end(dispatch_resolved_block)
    default_block = function.append_basic_block("unsupported")
    dispatcher = builder.switch(current_word.resolved_handler_id, default_block)
    case_blocks: dict[int, ir.Block] = {}
    for spec in LOWERED_HANDLER_SPECS.values():
        descriptor = dictionary.instruction_descriptor_for_handler_id(spec.handler_id)
        if descriptor is None:
            raise RuntimeError(f"missing descriptor for lowered handler id {spec.handler_id}")

        case_block = function.append_basic_block(f"case_{spec.function_name}")
        case_blocks[spec.handler_id] = case_block
        dispatcher.add_case(I32(spec.handler_id), case_block)
        with builder.goto_block(case_block):
            labeled_continuation = None
            if descriptor.requirements.needs_labeled_continuation:
                label_ids = {
                    label_name: label_index
                    for label_index, (label_name, _target_kind) in enumerate(
                        descriptor.continuation_labels
                    )
                }
                labeled_continuation = SeamLabeledContinuationIR(
                    builder=builder,
                    label_ids=label_ids,
                )
            kwargs = injected_ir_resources(
                builder=builder,
                state=state,
                descriptor=descriptor,
                current_word=current_word,
                labeled_continuation=labeled_continuation,
            )
            labeled_continuation_value = spec.op(builder, **kwargs)
            emit_descriptor_continuation(
                builder=builder,
                descriptor=descriptor,
                advance_ip_block=advance_ip_block,
                refetch_block=refetch_block,
                dispatch_current_block=dispatch_current_block,
                halt_block=halt_block,
                labeled_continuation_value=labeled_continuation_value,
            )

    with builder.goto_block(default_block):
        state.halt_requested.store(TRUE_BIT)
        builder.branch(halt_block)

    with builder.goto_block(advance_ip_block):
        current_ip = state.ip.load(name="step_current_ip")
        next_ip = builder.add(current_ip, I32(1), name="step_next_ip")
        state.ip.store(next_ip)
        builder.branch(refetch_block)

    with builder.goto_block(refetch_block):
        refetch_ip = state.ip.load(name="step_refetch_ip")
        thread_length = state.thread_length.load(name="step_refetch_thread_length")
        can_refetch = builder.icmp_signed("<", refetch_ip, thread_length, name="step_can_refetch")
        refetch_in_bounds_block = function.append_basic_block("refetch_in_bounds")
        refetch_done_block = function.append_basic_block("refetch_done")
        builder.cbranch(can_refetch, refetch_in_bounds_block, refetch_done_block)

    with builder.goto_block(refetch_in_bounds_block):
        if run_to_completion:
            builder.branch(fetch_block)
        else:
            emit_fetch_current_xt(builder, state, name_prefix="step_refetch")
            builder.branch(refetch_done_block)

    with builder.goto_block(refetch_done_block):
        builder.branch(return_block)

    with builder.goto_block(halt_block):
        builder.branch(return_block)

    with builder.goto_block(return_block):
        builder.ret_void()


def define_lowered_step(module: ir.Module) -> None:
    define_lowered_interpreter(
        module,
        function_name=lowered_step_function_name(),
        run_to_completion=False,
    )


def define_lowered_run(module: ir.Module) -> None:
    define_lowered_interpreter(
        module,
        function_name=lowered_run_function_name(),
        run_to_completion=True,
    )


def build_lowered_runtime(
    *,
    speed_level: int | None = None,
) -> LoweredRuntimeArtifacts:
    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    module = ir.Module(name="lowered_handler_seam")
    module.triple = binding.get_default_triple()
    module.data_layout = str(target_machine.target_data)
    define_lowered_step(module)
    define_lowered_run(module)

    compiled = compile_ir_module(module, speed_level=speed_level)
    lowered_step_address = compiled.function_address(lowered_step_function_name())
    lowered_step = ctypes.CFUNCTYPE(
        None,
        ctypes.POINTER(LoweredLoopState),
    )(lowered_step_address)
    lowered_run_address = compiled.function_address(lowered_run_function_name())
    lowered_run = ctypes.CFUNCTYPE(
        None,
        ctypes.POINTER(LoweredLoopState),
    )(lowered_run_address)
    return LoweredRuntimeArtifacts(
        module=module,
        compiled=compiled,
        step=LoweredInterpreterEntrypoint(
            mode=LoweredInterpreterMode.STEP,
            function_name=lowered_step_function_name(),
            cfunc=lowered_step,
            address=lowered_step_address,
            description="trace-friendly one-step lowered NEXT entrypoint",
        ),
        run=LoweredInterpreterEntrypoint(
            mode=LoweredInterpreterMode.RUN,
            function_name=lowered_run_function_name(),
            cfunc=lowered_run,
            address=lowered_run_address,
            description="multi-step lowered inner-loop entrypoint",
        ),
    )
