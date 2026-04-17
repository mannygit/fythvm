from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Callable

from llvmlite import ir

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
FALSE_BIT = I1(0)
VOID = ir.VoidType()


@dataclass(frozen=True)
class LoweredExecutionControlIR:
    """Execution-control helper injected into lowered op bodies.

    Normal handlers still rely on host-side fallthrough. Control-shaping handlers
    can instead install an exact next ip and set ``exact_ip_requested`` so the
    host loop skips its usual increment for that step.
    """

    builder: ir.IRBuilder
    state: LoweredLoopStateView

    def request_halt(self) -> None:
        self.state.halt_requested.store(TRUE_BIT)

    def request_exact_ip(self) -> None:
        self.state.exact_ip_requested.store(TRUE_BIT)

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
        self.request_exact_ip()

    def return_to_thread(self, *, thread: ThreadRefIR, return_ip: ir.Value) -> None:
        self.state.thread_cells.store(thread.cells)
        self.state.thread_length.store(thread.length)
        self.state.ip.store(return_ip)
        self.request_exact_ip()


@dataclass(frozen=True)
class SeamThreadJumpIR:
    """Thread-jump helper that can suppress host fallthrough when needed."""

    builder: ir.IRBuilder
    state: LoweredLoopStateView
    ip_field_name: str = "ip"

    def branch_relative(self, offset: ir.Value) -> None:
        ip_field = getattr(self.state, self.ip_field_name)
        current_ip = ip_field.load(name="branch_operand_ip")
        offset_base_ip = self.builder.add(current_ip, offset, name="branch_offset_base_ip")
        target_ip = self.builder.add(offset_base_ip, I32(1), name="branch_target_ip")
        ip_field.store(target_ip)
        self.state.exact_ip_requested.store(TRUE_BIT)

    def branch_if_zero(self, value: ir.Value, offset: ir.Value) -> None:
        ip_field = getattr(self.state, self.ip_field_name)
        current_ip = ip_field.load(name="zbranch_operand_ip")
        offset_base_ip = self.builder.add(current_ip, offset, name="zbranch_offset_base_ip")
        target_ip = self.builder.add(offset_base_ip, I32(1), name="zbranch_target_ip")
        should_branch = self.builder.icmp_signed("==", value, I32(0), name="zbranch_is_zero")
        next_ip = self.builder.select(should_branch, target_ip, current_ip, name="zbranch_next_ip")
        ip_field.store(next_ip)
        exact_ip_requested = self.builder.select(
            should_branch,
            TRUE_BIT,
            FALSE_BIT,
            name="zbranch_exact_ip_requested",
        )
        self.state.exact_ip_requested.store(exact_ip_requested)


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


def lowered_fetch_function_name() -> str:
    return "lowered_fetch"


def lowered_dispatch_function_name() -> str:
    return "lowered_dispatch"


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
    thread_jump: SeamThreadJumpIR,
    err: LoweredErrorExitIR,
) -> None:
    """Emit BRANCH's local IR effect without owning wrapper termination."""

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
    err: LoweredErrorExitIR,
) -> None:
    """Emit 0BRANCH's local IR effect without owning wrapper termination."""

    _ = err
    condition = data_stack.peek(name="zbranch_condition")
    offset = thread_cursor.read_inline_cell()
    data_stack.drop(name="zbranch_next_sp")
    thread_jump.branch_if_zero(condition, offset)


def op_docol_ir(
    builder: ir.IRBuilder,
    *,
    current_word_thread: CurrentXtDictionaryThreadIR,
    return_stack: ReturnStackIR,
    control: LoweredExecutionControlIR,
    err: LoweredErrorExitIR,
) -> None:
    """Emit DOCOL's local IR effect without owning wrapper termination."""

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
    """Emit EXIT's local IR effect without owning wrapper termination."""

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


def define_lowered_fetch(module: ir.Module) -> None:
    state_ptr_type = STATE_HANDLE.ir_type.as_pointer()
    function = ir.Function(
        module,
        ir.FunctionType(VOID, [state_ptr_type]),
        name=lowered_fetch_function_name(),
    )
    builder = ir.IRBuilder(function.append_basic_block(name="entry"))
    state_ptr = function.args[0]
    state_ptr.name = "state"
    state = STATE_HANDLE.bind(builder, state_ptr)

    current_ip = state.ip.load(name="fetch_ip")
    thread_cells = state.thread_cells.load(name="fetch_thread_cells")
    xt_ptr = builder.gep(thread_cells, [current_ip], inbounds=True, name="fetch_xt_ptr")
    current_xt = builder.load(xt_ptr, name="fetched_xt")
    state.current_xt.store(current_xt)
    builder.ret_void()


def define_lowered_dispatch(module: ir.Module) -> None:
    state_ptr_type = STATE_HANDLE.ir_type.as_pointer()
    function = ir.Function(
        module,
        ir.FunctionType(VOID, [state_ptr_type]),
        name=lowered_dispatch_function_name(),
    )
    builder = ir.IRBuilder(function.append_basic_block(name="entry"))
    state_ptr = function.args[0]
    state_ptr.name = "state"
    state = STATE_HANDLE.bind(builder, state_ptr)

    current_xt = state.current_xt.load(name="dispatch_current_xt")
    dictionary_memory = state.dictionary_memory.load(name="dispatch_dictionary_memory")
    dictionary_ir = dictionary.DictionaryIR(builder, dictionary_memory)
    found_word_index = dictionary_ir.find_word_by_cfa(current_xt)
    found_custom_word = builder.icmp_signed(
        "!=",
        found_word_index,
        I32(dictionary.NULL_INDEX),
        name="dispatch_found_custom_word",
    )
    custom_block = function.append_basic_block("dispatch_custom_word")
    primitive_block = function.append_basic_block("dispatch_primitive")
    resolved_block = function.append_basic_block("dispatch_resolved")
    builder.cbranch(found_custom_word, custom_block, primitive_block)

    with builder.goto_block(custom_block):
        custom_word = dictionary_ir.word(found_word_index)
        custom_code_field = custom_word.code_field.bind(dictionary_ir.code_field_handle)
        custom_handler_id = builder.zext(
            custom_code_field.handler_id.load(name="dispatch_custom_handler_id_i7"),
            I32,
            name="dispatch_custom_handler_id",
        )
        builder.branch(resolved_block)

    with builder.goto_block(primitive_block):
        primitive_handler_id = current_xt
        builder.branch(resolved_block)

    builder.position_at_end(resolved_block)
    resolved_handler_id = builder.phi(I32, name="dispatch_handler_id")
    resolved_handler_id.add_incoming(custom_handler_id, custom_block)
    resolved_handler_id.add_incoming(primitive_handler_id, primitive_block)

    default_block = function.append_basic_block("unsupported")
    exit_block = function.append_basic_block("exit")
    dispatcher = builder.switch(resolved_handler_id, default_block)
    for spec in LOWERED_HANDLER_SPECS.values():
        case_block = function.append_basic_block(f"case_{spec.function_name}")
        dispatcher.add_case(I32(spec.handler_id), case_block)
        with builder.goto_block(case_block):
            builder.call(module.get_global(spec.function_name), [state_ptr])
            builder.branch(exit_block)

    with builder.goto_block(default_block):
        LoweredExecutionControlIR(builder=builder, state=state).request_halt()
        builder.branch(exit_block)

    builder.position_at_end(exit_block)
    builder.ret_void()


def build_lowered_runtime() -> tuple[
    ir.Module,
    object,
    ctypes._CFuncPtr,  # type: ignore[attr-defined]
    ctypes._CFuncPtr,  # type: ignore[attr-defined]
    dict[int, int],
]:
    module = ir.Module(name="lowered_handler_seam")
    for spec in LOWERED_HANDLER_SPECS.values():
        define_lowered_handler(module, spec)
    define_lowered_fetch(module)
    define_lowered_dispatch(module)

    compiled = compile_ir_module(module)
    lowered_addresses: dict[int, int] = {}
    for handler_id, spec in LOWERED_HANDLER_SPECS.items():
        address = compiled.function_address(spec.function_name)
        lowered_addresses[handler_id] = address
    lowered_fetch = ctypes.CFUNCTYPE(
        None,
        ctypes.POINTER(LoweredLoopState),
    )(compiled.function_address(lowered_fetch_function_name()))
    lowered_dispatch = ctypes.CFUNCTYPE(
        None,
        ctypes.POINTER(LoweredLoopState),
    )(compiled.function_address(lowered_dispatch_function_name()))
    return module, compiled, lowered_fetch, lowered_dispatch, lowered_addresses
