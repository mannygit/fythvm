"""Tiny raw-cell RPN calculator built on promoted codegen primitives."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Callable, Literal, Sequence

from llvmlite import binding, ir

from .codegen import (
    FetchedCell,
    I16,
    I16_PTR,
    I32,
    ContextStructStackAccess,
    ParamLoop,
    SharedExit,
    SwitchDispatcher,
    compile_ir_module,
    emit_tagged_cell_dispatch,
    configure_llvm,
)


STACK_SIZE = 8
TAG_MASK = 0x8000
LITERAL_MAX = 0x7FFF

STATUS_OK = 0
STATUS_STACK_UNDERFLOW = 1
STATUS_DIVIDE_BY_ZERO = 2
STATUS_BAD_OPCODE = 3
STATUS_MISSING_EXIT = 4
STATUS_STACK_NOT_SINGLETON = 5
STATUS_STACK_OVERFLOW = 6

OP_ADD = TAG_MASK | ord("+")
OP_SUB = TAG_MASK | ord("-")
OP_MUL = TAG_MASK | ord("*")
OP_DIV = TAG_MASK | ord("/")
OP_MOD = TAG_MASK | ord("%")
OP_EXIT = TAG_MASK | ord("=")
KNOWN_OPS = {
    OP_ADD: "+",
    OP_SUB: "-",
    OP_MUL: "*",
    OP_DIV: "/",
    OP_MOD: "%",
    OP_EXIT: "=",
}

BinaryOperation = Callable[[ir.IRBuilder, ir.Value, ir.Value], ir.Value]


def _emit_add(builder: ir.IRBuilder, lhs: ir.Value, rhs: ir.Value) -> ir.Value:
    return builder.add(lhs, rhs, name="sum")


def _emit_sub(builder: ir.IRBuilder, lhs: ir.Value, rhs: ir.Value) -> ir.Value:
    return builder.sub(lhs, rhs, name="diff")


def _emit_mul(builder: ir.IRBuilder, lhs: ir.Value, rhs: ir.Value) -> ir.Value:
    return builder.mul(lhs, rhs, name="product")


def _emit_div(builder: ir.IRBuilder, lhs: ir.Value, rhs: ir.Value) -> ir.Value:
    return builder.sdiv(lhs, rhs, name="quotient")


def _emit_mod(builder: ir.IRBuilder, lhs: ir.Value, rhs: ir.Value) -> ir.Value:
    return builder.srem(lhs, rhs, name="remainder")


@dataclass(frozen=True)
class _OpcodeSpec:
    opcode_value: int
    name: str
    kind: Literal["binary", "exit"]
    operation: BinaryOperation | None = None
    zero_sensitive: bool = False


OPCODE_SPECS = (
    _OpcodeSpec(OP_ADD, "add", "binary", _emit_add),
    _OpcodeSpec(OP_SUB, "sub", "binary", _emit_sub),
    _OpcodeSpec(OP_MUL, "mul", "binary", _emit_mul),
    _OpcodeSpec(OP_DIV, "div", "binary", _emit_div, zero_sensitive=True),
    _OpcodeSpec(OP_MOD, "mod", "binary", _emit_mod, zero_sensitive=True),
    _OpcodeSpec(OP_EXIT, "exit", "exit"),
)

class CalcContext(ctypes.Structure):
    _fields_ = [
        ("stack", ctypes.c_int16 * STACK_SIZE),
        ("sp", ctypes.c_int32),
    ]


@dataclass(frozen=True)
class EvalResult:
    status: int
    result: int
    sp: int
    logical_stack: list[int]


@dataclass(frozen=True)
class CompiledCalculator:
    llvm_ir: str
    _engine: binding.ExecutionEngine
    _eval_addr: int

    def evaluate(self, cells: Sequence[int], ctx: CalcContext | None = None) -> EvalResult:
        if not cells:
            raise ValueError("cells must not be empty")

        for cell in cells:
            if not 0 <= cell <= 0xFFFF:
                raise ValueError(f"cell out of 16-bit range: {cell}")

        program = (ctypes.c_uint16 * len(cells))(*cells)
        result = ctypes.c_int16(0)
        runtime_ctx = ctx if ctx is not None else CalcContext()

        eval_cells = ctypes.CFUNCTYPE(
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int16),
            ctypes.c_int32,
            ctypes.POINTER(CalcContext),
            ctypes.POINTER(ctypes.c_int16),
        )(self._eval_addr)

        status = int(
            eval_cells(
                ctypes.cast(program, ctypes.POINTER(ctypes.c_int16)),
                len(cells),
                ctypes.byref(runtime_ctx),
                ctypes.byref(result),
            )
        )
        return EvalResult(
            status=status,
            result=int(result.value),
            sp=int(runtime_ctx.sp),
            logical_stack=logical_stack(runtime_ctx),
        )


def lit(value: int) -> int:
    if not 0 <= value <= LITERAL_MAX:
        raise ValueError(f"literal out of 15-bit range: {value}")
    return value


def op(symbol: str) -> int:
    if len(symbol) != 1 or symbol not in "+-*/%=":
        raise ValueError(f"unsupported operator: {symbol!r}")
    return TAG_MASK | ord(symbol)


def render_program(cells: Sequence[int]) -> str:
    rendered: list[str] = []
    for cell in cells:
        if cell & TAG_MASK:
            rendered.append(KNOWN_OPS.get(cell, f"op(0x{cell:04x})"))
        else:
            rendered.append(str(cell))
    return ",".join(rendered)


def status_name(status: int) -> str:
    return {
        STATUS_OK: "ok",
        STATUS_STACK_UNDERFLOW: "stack_underflow",
        STATUS_DIVIDE_BY_ZERO: "divide_by_zero",
        STATUS_BAD_OPCODE: "bad_opcode",
        STATUS_MISSING_EXIT: "missing_exit",
        STATUS_STACK_NOT_SINGLETON: "stack_not_singleton",
        STATUS_STACK_OVERFLOW: "stack_overflow",
    }[status]


def logical_stack(ctx: CalcContext) -> list[int]:
    return [int(value) for value in reversed(ctx.stack[ctx.sp:STACK_SIZE])]


class CalculatorEmitter:
    """Emit the concrete RPN evaluator using promoted helper pieces."""

    def __init__(self, module: ir.Module, name: str):
        self.ctx_type = ir.LiteralStructType([ir.ArrayType(I16, STACK_SIZE), I32])
        fn_ty = ir.FunctionType(I32, [I16_PTR, I32, self.ctx_type.as_pointer(), I16_PTR])
        self.function = ir.Function(module, fn_ty, name=name)
        self.cells_ptr, self.cell_count, self.ctx_ptr, self.out_result_ptr = self.function.args
        self.stack = ContextStructStackAccess(self.ctx_ptr)
        self.entry_block = self.function.append_basic_block("entry")
        self.builder = ir.IRBuilder(self.entry_block)
        self.loop = ParamLoop(self.builder, "eval", [("ip", I32)])
        self.literal_check_block = self.function.append_basic_block("literal.check")
        self.literal_store_block = self.function.append_basic_block("literal.store")
        self.opcode_block = self.function.append_basic_block("opcode.dispatch")
        self.underflow_block = self.function.append_basic_block("underflow")
        self.divzero_block = self.function.append_basic_block("divzero")
        self.bad_opcode_block = self.function.append_basic_block("bad_opcode")
        self.bad_exit_shape_block = self.function.append_basic_block("bad_exit_shape")
        self.overflow_block = self.function.append_basic_block("overflow")
        self.exit = SharedExit(self.function, [("status", I32), ("result", I16)])

    def emit_loop_head(self) -> ir.Value:
        self.stack.store_sp(self.builder, I32(STACK_SIZE))
        self.loop.begin(I32(0))

        with self.loop.head() as (ip,):
            reached_end = self.builder.icmp_signed(">=", ip, self.cell_count, name="reached_end")
            self.builder.cbranch(reached_end, self.loop.exit_block, self.loop.body_block)
            return ip

    def emit_dispatch(self, ip: ir.Value) -> FetchedCell:
        with self.loop.body():
            return emit_tagged_cell_dispatch(
                self.builder,
                self.cells_ptr,
                ip,
                literal_target=self.literal_check_block,
                opcode_target=self.opcode_block,
                cell_type=I16,
                index_type=I32,
                tag_mask=TAG_MASK,
            )

    def emit_literal_handler(self, step: FetchedCell) -> None:
        self.builder.position_at_end(self.literal_check_block)
        current_sp = self.stack.load_sp(self.builder)
        has_room = self.builder.icmp_unsigned("!=", current_sp, I32(0), name="has_room")
        self.builder.cbranch(has_room, self.literal_store_block, self.overflow_block)

        self.builder.position_at_end(self.literal_store_block)
        current_sp = self.stack.load_sp(self.builder)
        new_sp = self.builder.sub(current_sp, I32(1), name="new_sp")
        self.builder.store(step.current_cell, self.stack.slot(self.builder, new_sp))
        self.stack.store_sp(self.builder, new_sp)
        self.loop.continue_from_here(step.next_ip)

    def emit_binary_handler(
        self,
        builder: ir.IRBuilder,
        step: FetchedCell,
        spec: _OpcodeSpec,
    ) -> None:
        if spec.operation is None:
            raise ValueError(f"binary opcode spec {spec.name!r} is missing an operation")

        apply_block = self.function.append_basic_block(f"{spec.name}.apply")
        current_sp = self.stack.load_sp(builder)
        enough_items = builder.icmp_unsigned("<=", current_sp, I32(STACK_SIZE - 2), name=f"{spec.name}_enough")
        if spec.zero_sensitive:
            zero_check_block = self.function.append_basic_block(f"{spec.name}.zero_check")
            builder.cbranch(enough_items, zero_check_block, self.underflow_block)

            builder.position_at_end(zero_check_block)
            rhs = builder.load(self.stack.slot(builder, current_sp, name=f"{spec.name}_rhs_ptr"), name="rhs")
            rhs_is_zero = builder.icmp_signed("==", rhs, I16(0), name=f"{spec.name}_rhs_is_zero")
            builder.cbranch(rhs_is_zero, self.divzero_block, apply_block)
        else:
            builder.cbranch(enough_items, apply_block, self.underflow_block)

        builder.position_at_end(apply_block)
        current_sp = self.stack.load_sp(builder)
        rhs = builder.load(self.stack.slot(builder, current_sp, name=f"{spec.name}_rhs_ptr"), name="rhs")
        lhs_index = builder.add(current_sp, I32(1), name="lhs_index")
        lhs = builder.load(self.stack.slot(builder, lhs_index, name=f"{spec.name}_lhs_ptr"), name="lhs")
        result = spec.operation(builder, lhs, rhs)
        builder.store(result, self.stack.slot(builder, lhs_index, name=f"{spec.name}_result_ptr"))
        self.stack.store_sp(builder, lhs_index)
        self.loop.continue_from_here(step.next_ip)

    def emit_exit_handler(self, builder: ir.IRBuilder) -> None:
        current_sp = self.stack.load_sp(builder)
        has_single_value = builder.icmp_unsigned(
            "==", current_sp, I32(STACK_SIZE - 1), name="has_single_value"
        )
        singleton_ok_block = self.function.append_basic_block("ok.singleton")
        builder.cbranch(has_single_value, singleton_ok_block, self.bad_exit_shape_block)

        builder.position_at_end(singleton_ok_block)
        result = builder.load(self.stack.slot(builder, current_sp), name="result")
        self.exit.remember(builder, I32(STATUS_OK), result)

    def emit_opcode_dispatch(self, step: FetchedCell) -> None:
        self.builder.position_at_end(self.opcode_block)
        dispatcher = SwitchDispatcher(self.builder, step.current_cell, self.bad_opcode_block, name="opcode")
        for spec in OPCODE_SPECS:
            if spec.kind == "binary":
                dispatcher.add_case(
                    I16(spec.opcode_value),
                    spec.name,
                    lambda builder, spec=spec: self.emit_binary_handler(builder, step, spec),
                )
            else:
                dispatcher.add_case(I16(spec.opcode_value), spec.name, self.emit_exit_handler)
        dispatcher.emit()

    def emit_error_blocks(self) -> None:
        for block, status in (
            (self.loop.exit_block, STATUS_MISSING_EXIT),
            (self.underflow_block, STATUS_STACK_UNDERFLOW),
            (self.divzero_block, STATUS_DIVIDE_BY_ZERO),
            (self.bad_opcode_block, STATUS_BAD_OPCODE),
            (self.bad_exit_shape_block, STATUS_STACK_NOT_SINGLETON),
            (self.overflow_block, STATUS_STACK_OVERFLOW),
        ):
            self.builder.position_at_end(block)
            self.exit.remember(self.builder, I32(status), I16(0))

    def emit(self) -> None:
        ip = self.emit_loop_head()
        step = self.emit_dispatch(ip)
        self.emit_literal_handler(step)
        self.emit_opcode_dispatch(step)
        self.emit_error_blocks()

        status_phi, result_phi = self.exit.finish()
        self.exit.builder.store(result_phi, self.out_result_ptr)
        self.exit.builder.ret(status_phi)


def build_module(function_name: str = "eval_cells") -> ir.Module:
    module = ir.Module(name="fythvm_rpn16")
    module.triple = binding.get_default_triple()
    CalculatorEmitter(module, function_name).emit()
    return module


def compile_calculator() -> CompiledCalculator:
    configure_llvm()
    module = build_module()
    compiled = compile_ir_module(module)
    return CompiledCalculator(
        llvm_ir=compiled.llvm_ir,
        _engine=compiled.engine,
        _eval_addr=compiled.function_address("eval_cells"),
    )
