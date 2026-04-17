from __future__ import annotations

import ctypes
from dataclasses import dataclass
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
LoweredOp = Callable[..., None]
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
    """Ephemeral labeled continuation outcome for special-case handlers like 0BRANCH."""

    builder: ir.IRBuilder
    label_slot: ir.Value
    label_ids: dict[str, int]

    def select_between(self, condition: ir.Value, *, when_true: str, when_false: str) -> None:
        true_id = I32(self.label_ids[when_true])
        false_id = I32(self.label_ids[when_false])
        label_value = self.builder.select(condition, true_id, false_id, name="continuation_label")
        self.builder.store(label_value, self.label_slot)


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


@dataclass(frozen=True)
class CurrentXtDictionaryThreadIR:
    """Resolve the current word's thread through real dictionary memory."""

    state: LoweredLoopStateView
    dictionary_ir: dictionary.DictionaryIR
    thread_length_field_name: str = "current_word_thread_length"

    def ref(self) -> ThreadRefIR:
        current_xt = self.state.current_xt.load(name="current_xt")
        thread_cells = self.dictionary_ir.thread_cells_ptr_for_cfa(
            current_xt,
            name="current_word_thread_cells",
        )
        thread_length_field = getattr(self.state, self.thread_length_field_name)
        return ThreadRefIR(
            cells=thread_cells,
            length=thread_length_field.load(name="current_word_thread_length"),
        )


def injected_ir_resources(
    *,
    builder: ir.IRBuilder,
    state: LoweredLoopStateView,
    descriptor: dictionary.InstructionDescriptor,
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
        dictionary_memory = state.dictionary_memory.load(name="dictionary_memory")
        kwargs["current_word_thread"] = CurrentXtDictionaryThreadIR(
            state=state,
            dictionary_ir=dictionary.DictionaryIR(builder, dictionary_memory),
        )
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
) -> None:
    """Emit HALT's local IR effect without owning whole-step termination."""

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
    """Emit LIT's local IR effect without owning whole-step termination."""

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
    """Emit ADD's local IR effect without owning whole-step termination."""

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
    thread_jump: SeamThreadJumpIR,
    err: LoweredErrorExitIR,
) -> None:
    """Emit BRANCH's local IR effect without owning whole-step termination."""

    _ = builder
    _ = err
    offset = thread_cursor.read_inline_cell()
    thread_jump.branch_relative(offset)


def op_zbranch_ir(
    builder: ir.IRBuilder,
    *,
    data_stack: BoundStackAccess,
    thread_cursor: ThreadCursorIR,
    thread_jump: SeamThreadJumpIR,
    labeled_continuation: SeamLabeledContinuationIR,
    err: LoweredErrorExitIR,
) -> None:
    """Emit 0BRANCH's local IR effect without owning whole-step termination."""

    _ = err
    condition = data_stack.peek(name="zbranch_condition")
    offset = thread_cursor.read_inline_cell()
    data_stack.drop(name="zbranch_next_sp")
    should_branch = thread_jump.branch_if_zero(condition, offset)
    labeled_continuation.select_between(
        should_branch,
        when_true="branch_taken",
        when_false="branch_fallthrough",
    )


def op_docol_ir(
    builder: ir.IRBuilder,
    *,
    current_word_thread: CurrentXtDictionaryThreadIR,
    return_stack: ReturnStackIR,
    control: LoweredExecutionControlIR,
    err: LoweredErrorExitIR,
) -> None:
    """Emit DOCOL's local IR effect without owning whole-step termination."""

    _ = builder
    _ = err
    control.enter_thread(thread=current_word_thread.ref(), return_stack=return_stack)


def op_exit_ir(
    builder: ir.IRBuilder,
    *,
    return_stack: ReturnStackIR,
    control: LoweredExecutionControlIR,
    err: LoweredErrorExitIR,
) -> None:
    """Emit EXIT's local IR effect without owning whole-step termination."""

    _ = builder
    _ = err
    thread, return_ip = return_stack.pop_frame()
    control.return_to_thread(thread=thread, return_ip=return_ip)


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


def _continuation_block_for_kind(
    continuation: dictionary.ContinuationKind,
    *,
    advance_ip_block: ir.Block,
    refetch_block: ir.Block,
    halt_block: ir.Block,
) -> ir.Block:
    if continuation is dictionary.ContinuationKind.FALLTHROUGH:
        return advance_ip_block
    if continuation is dictionary.ContinuationKind.EXACT_IP:
        return refetch_block
    if continuation is dictionary.ContinuationKind.HALT:
        return halt_block
    raise RuntimeError(f"unsupported continuation kind for direct branch: {continuation.value}")


def emit_descriptor_continuation(
    *,
    builder: ir.IRBuilder,
    descriptor: dictionary.InstructionDescriptor,
    advance_ip_block: ir.Block,
    refetch_block: ir.Block,
    halt_block: ir.Block,
    labeled_continuation_slot: ir.Value | None,
) -> None:
    continuation = descriptor.continuation
    if continuation is not dictionary.ContinuationKind.LABELED:
        builder.branch(
            _continuation_block_for_kind(
                continuation,
                advance_ip_block=advance_ip_block,
                refetch_block=refetch_block,
                halt_block=halt_block,
            )
        )
        return

    if labeled_continuation_slot is None:
        raise RuntimeError(f"{descriptor.key} requested labeled continuation without a slot")

    label_value = builder.load(labeled_continuation_slot, name=f"{descriptor.key.lower()}_continuation_label")
    default_block = builder.append_basic_block(f"{descriptor.key.lower()}_continuation_default")
    switch = builder.switch(label_value, default_block)
    for label_index, (label_name, target_kind) in enumerate(descriptor.continuation_labels):
        case_block = builder.append_basic_block(f"{descriptor.key.lower()}_{label_name}")
        switch.add_case(I32(label_index), case_block)
        with builder.goto_block(case_block):
            builder.branch(
                _continuation_block_for_kind(
                    target_kind,
                    advance_ip_block=advance_ip_block,
                    refetch_block=refetch_block,
                    halt_block=halt_block,
                )
            )

    with builder.goto_block(default_block):
        builder.branch(halt_block)


def define_lowered_step(module: ir.Module) -> None:
    state_ptr_type = STATE_HANDLE.ir_type.as_pointer()
    function = ir.Function(
        module,
        ir.FunctionType(VOID, [state_ptr_type]),
        name=lowered_step_function_name(),
    )
    builder = ir.IRBuilder(function.append_basic_block(name="entry"))
    state_ptr = function.args[0]
    state_ptr.name = "state"
    state = STATE_HANDLE.bind(builder, state_ptr)
    resolved_handler_id_ptr = builder.alloca(I32, name="resolved_handler_id_ptr")
    fetch_block = function.append_basic_block("fetch")
    dispatch_custom_block = function.append_basic_block("dispatch_custom_word")
    dispatch_primitive_block = function.append_basic_block("dispatch_primitive")
    dispatch_resolved_block = function.append_basic_block("dispatch_resolved")
    advance_ip_block = function.append_basic_block("advance_ip")
    refetch_block = function.append_basic_block("refetch")
    halt_block = function.append_basic_block("halt")
    step_complete_block = function.append_basic_block("step_complete")
    builder.branch(fetch_block)

    with builder.goto_block(fetch_block):
        current_xt = emit_fetch_current_xt(builder, state, name_prefix="step_fetch")
        dictionary_memory = state.dictionary_memory.load(name="dispatch_dictionary_memory")
        dictionary_ir = dictionary.DictionaryIR(builder, dictionary_memory)
        found_word_index = dictionary_ir.find_word_by_cfa(current_xt)
        found_custom_word = builder.icmp_signed(
            "!=",
            found_word_index,
            I32(dictionary.NULL_INDEX),
            name="dispatch_found_custom_word",
        )
        builder.cbranch(found_custom_word, dispatch_custom_block, dispatch_primitive_block)

    with builder.goto_block(dispatch_custom_block):
        dictionary_memory = state.dictionary_memory.load(name="custom_dictionary_memory")
        dictionary_ir = dictionary.DictionaryIR(builder, dictionary_memory)
        current_xt = state.current_xt.load(name="custom_current_xt")
        found_word_index = dictionary_ir.find_word_by_cfa(current_xt)
        custom_word = dictionary_ir.word(found_word_index)
        custom_code_field = custom_word.code_field.bind(dictionary_ir.code_field_handle)
        custom_handler_id = builder.zext(
            custom_code_field.handler_id.load(name="dispatch_custom_handler_id_i7"),
            I32,
            name="dispatch_custom_handler_id",
        )
        builder.store(custom_handler_id, resolved_handler_id_ptr)
        builder.branch(dispatch_resolved_block)

    with builder.goto_block(dispatch_primitive_block):
        primitive_handler_id = state.current_xt.load(name="dispatch_primitive_handler_id")
        builder.store(primitive_handler_id, resolved_handler_id_ptr)
        builder.branch(dispatch_resolved_block)

    builder.position_at_end(dispatch_resolved_block)
    resolved_handler_id = builder.load(resolved_handler_id_ptr, name="dispatch_handler_id")

    default_block = function.append_basic_block("unsupported")
    dispatcher = builder.switch(resolved_handler_id, default_block)
    for spec in LOWERED_HANDLER_SPECS.values():
        descriptor = dictionary.instruction_descriptor_for_handler_id(spec.handler_id)
        if descriptor is None:
            raise RuntimeError(f"missing descriptor for lowered handler id {spec.handler_id}")

        case_block = function.append_basic_block(f"case_{spec.function_name}")
        dispatcher.add_case(I32(spec.handler_id), case_block)
        with builder.goto_block(case_block):
            labeled_continuation = None
            labeled_continuation_slot = None
            if descriptor.requirements.needs_labeled_continuation:
                label_ids = {
                    label_name: label_index
                    for label_index, (label_name, _target_kind) in enumerate(
                        descriptor.continuation_labels
                    )
                }
                labeled_continuation_slot = builder.alloca(
                    I32,
                    name=f"{descriptor.key.lower()}_continuation_label_ptr",
                )
                labeled_continuation = SeamLabeledContinuationIR(
                    builder=builder,
                    label_slot=labeled_continuation_slot,
                    label_ids=label_ids,
                )
            kwargs = injected_ir_resources(
                builder=builder,
                state=state,
                descriptor=descriptor,
                labeled_continuation=labeled_continuation,
            )
            spec.op(builder, **kwargs)
            emit_descriptor_continuation(
                builder=builder,
                descriptor=descriptor,
                advance_ip_block=advance_ip_block,
                refetch_block=refetch_block,
                halt_block=halt_block,
                labeled_continuation_slot=labeled_continuation_slot,
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
        emit_fetch_current_xt(builder, state, name_prefix="step_refetch")
        builder.branch(refetch_done_block)

    with builder.goto_block(refetch_done_block):
        builder.branch(step_complete_block)

    with builder.goto_block(halt_block):
        builder.ret_void()

    with builder.goto_block(step_complete_block):
        builder.ret_void()


def build_lowered_runtime() -> tuple[
    ir.Module,
    object,
    ctypes._CFuncPtr,  # type: ignore[attr-defined]
    int,
]:
    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    module = ir.Module(name="lowered_handler_seam")
    module.triple = binding.get_default_triple()
    module.data_layout = str(target_machine.target_data)
    define_lowered_step(module)

    compiled = compile_ir_module(module)
    lowered_step_address = compiled.function_address(lowered_step_function_name())
    lowered_step = ctypes.CFUNCTYPE(
        None,
        ctypes.POINTER(LoweredLoopState),
    )(lowered_step_address)
    return module, compiled, lowered_step, lowered_step_address
