"""Tiny raw-cell RPN calculator built on promoted codegen primitives."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Callable, Literal, Sequence

from llvmlite import binding, ir

from .codegen import (
    I16,
    I16_PTR,
    I32,
    ContextStructStackAccess,
    FetchedCell,
    ParamLoop,
    SharedExit,
    SwitchDispatcher,
    compile_ir_module,
    configure_llvm,
    emit_tagged_cell_dispatch,
)

STACK_SIZE = 8
TAG_MASK = 0x8000
LITERAL_MAX = 0x7FFF

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


class Status(IntEnum):
    OK = 0
    STACK_UNDERFLOW = 1
    DIVIDE_BY_ZERO = 2
    BAD_OPCODE = 3
    MISSING_EXIT = 4
    STACK_NOT_SINGLETON = 5
    STACK_OVERFLOW = 6


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


@dataclass(frozen=True)
class _StatusTarget:
    kind: "_StatusKind"
    block: ir.Block
    status: int


class _StatusKind(Enum):
    UNDERFLOW = "underflow"
    DIVZERO = "divzero"
    BAD_EXIT_SHAPE = "bad_exit_shape"
    OVERFLOW = "overflow"
    BAD_OPCODE = "bad_opcode"


class CalcContext(ctypes.Structure):
    _fields_ = [
        ("stack", ctypes.c_int16 * STACK_SIZE),
        ("sp", ctypes.c_int32),
    ]


@dataclass(frozen=True)
class EvalResult:
    status: Status
    result: int
    sp: int
    logical_stack: list[int]


@dataclass(frozen=True)
class CompiledCalculator:
    llvm_ir: str
    _engine: binding.ExecutionEngine
    _eval_addr: int

    def evaluate(
        self, cells: Sequence[int], ctx: CalcContext | None = None
    ) -> EvalResult:
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

        status = Status(
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
        Status.OK: "ok",
        Status.STACK_UNDERFLOW: "stack_underflow",
        Status.DIVIDE_BY_ZERO: "divide_by_zero",
        Status.BAD_OPCODE: "bad_opcode",
        Status.MISSING_EXIT: "missing_exit",
        Status.STACK_NOT_SINGLETON: "stack_not_singleton",
        Status.STACK_OVERFLOW: "stack_overflow",
    }[status]


def logical_stack(ctx: CalcContext) -> list[int]:
    return [int(value) for value in reversed(ctx.stack[ctx.sp : STACK_SIZE])]


class CalculatorEmitter:
    """Emit the concrete RPN evaluator using promoted helper pieces."""

    def __init__(self, module: ir.Module, name: str):
        self.ctx_type = ir.LiteralStructType([ir.ArrayType(I16, STACK_SIZE), I32])
        fn_ty = ir.FunctionType(
            I32, [I16_PTR, I32, self.ctx_type.as_pointer(), I16_PTR]
        )
        self.function = ir.Function(module, fn_ty, name=name)
        self.cells_ptr, self.cell_count, self.ctx_ptr, self.out_result_ptr = (
            self.function.args
        )
        self.stack = ContextStructStackAccess(self.ctx_ptr)
        entry_block = self.function.append_basic_block("entry")
        self.builder = ir.IRBuilder(entry_block)
        self.stack_ops = self.stack.bind(self.builder)
        self.loop = ParamLoop(self.builder, "eval", [("ip", I32)])
        self.literal_check_block = self.function.append_basic_block("literal.check")
        self.opcode_block = self.function.append_basic_block("opcode.dispatch")
        self.status_targets: dict[_StatusKind, _StatusTarget] = {}
        self.register_status_target(_StatusKind.UNDERFLOW, Status.STACK_UNDERFLOW)
        self.register_status_target(_StatusKind.DIVZERO, Status.DIVIDE_BY_ZERO)
        self.register_status_target(
            _StatusKind.BAD_EXIT_SHAPE, Status.STACK_NOT_SINGLETON
        )
        self.register_status_target(_StatusKind.OVERFLOW, Status.STACK_OVERFLOW)
        self.exit = SharedExit(self.function, [("status", I32), ("result", I16)])

    def register_status_target(self, kind: _StatusKind, status: Status) -> ir.Block:
        block = self.function.append_basic_block(kind.value)
        self.status_targets[kind] = _StatusTarget(kind=kind, block=block, status=status)
        return block

    def status_block(self, kind: _StatusKind) -> ir.Block:
        return self.status_targets[kind].block

    def emit_loop_head(self) -> ir.Value:
        builder = self.builder
        self.stack_ops.reset(I32(STACK_SIZE))
        self.loop.begin(I32(0))

        with self.loop.head() as (ip,):
            builder = self.builder
            reached_end = builder.icmp_signed(
                ">=", ip, self.cell_count, name="reached_end"
            )
            builder.cbranch(reached_end, self.loop.exit_block, self.loop.body_block)
            return ip

    def emit_dispatch(self, ip: ir.Value) -> FetchedCell:
        with self.loop.body():
            builder = self.builder
            return emit_tagged_cell_dispatch(
                builder,
                self.cells_ptr,
                ip,
                literal_target=self.literal_check_block,
                opcode_target=self.opcode_block,
                cell_type=I16,
                index_type=I32,
                tag_mask=TAG_MASK,
            )

    def emit_literal_handler(self, step: FetchedCell) -> None:
        literal_store_block = self.function.append_basic_block("literal.store")

        builder = self.builder
        with builder.goto_block(self.literal_check_block):
            has_room = self.stack_ops.has_room()
            builder.cbranch(
                has_room, literal_store_block, self.status_block(_StatusKind.OVERFLOW)
            )

        with builder.goto_block(literal_store_block):
            self.stack_ops.push(step.current_cell)
            self.loop.continue_from_here(step.next_ip)

    def emit_binary_handler(self, step: FetchedCell, spec: _OpcodeSpec) -> None:
        if spec.operation is None:
            raise ValueError(
                f"binary opcode spec {spec.name!r} is missing an operation"
            )

        builder = self.builder
        enough_items = self.stack_ops.has_at_least(2, name=f"{spec.name}_enough")
        ready_check_block = self.function.append_basic_block(f"{spec.name}.ready")
        apply_block = self.function.append_basic_block(f"{spec.name}.apply")
        builder.cbranch(
            enough_items, ready_check_block, self.status_block(_StatusKind.UNDERFLOW)
        )

        with builder.goto_block(ready_check_block):
            operands = self.stack_ops.pop2()
            if spec.zero_sensitive:
                rhs_is_zero = builder.icmp_signed(
                    "==", operands.rhs, I16(0), name=f"{spec.name}_rhs_is_zero"
                )
                builder.cbranch(
                    rhs_is_zero, self.status_block(_StatusKind.DIVZERO), apply_block
                )
            else:
                builder.branch(apply_block)

        with builder.goto_block(apply_block):
            result = spec.operation(builder, operands.lhs, operands.rhs)
            builder.store(
                result,
                self.stack_ops.slot(
                    operands.result_index, name=f"{spec.name}_result_ptr"
                ),
            )
            self.stack_ops.store_sp(operands.result_index)
            self.loop.continue_from_here(step.next_ip)

    def emit_exit_handler(self) -> None:
        builder = self.builder
        has_single_value = self.stack_ops.has_exactly(1, name="has_single_value")
        singleton_ok_block = self.function.append_basic_block("ok.singleton")
        builder.cbranch(
            has_single_value,
            singleton_ok_block,
            self.status_block(_StatusKind.BAD_EXIT_SHAPE),
        )

        with builder.goto_block(singleton_ok_block):
            result = self.stack_ops.peek(name="result")
            self.exit.remember(builder, I32(Status.OK), result)

    def emit_opcode_dispatch(self, step: FetchedCell) -> None:
        builder = self.builder
        with builder.goto_block(self.opcode_block):
            bad_opcode_block = self.register_status_target(
                _StatusKind.BAD_OPCODE, Status.BAD_OPCODE
            )
            dispatcher = SwitchDispatcher(
                builder, step.current_cell, bad_opcode_block, name="opcode"
            )
            for spec in OPCODE_SPECS:
                if spec.kind == "binary":
                    dispatcher.add_case(
                        I16(spec.opcode_value),
                        spec.name,
                        lambda _builder, spec=spec: self.emit_binary_handler(
                            step, spec
                        ),
                    )
                else:
                    dispatcher.add_case(
                        I16(spec.opcode_value),
                        spec.name,
                        lambda _builder: self.emit_exit_handler(),
                    )
            dispatcher.emit()

    def emit_error_blocks(self) -> None:
        builder = self.builder
        for block, status in [(self.loop.exit_block, Status.MISSING_EXIT)] + [
            (target.block, target.status) for target in self.status_targets.values()
        ]:
            with builder.goto_block(block):
                self.exit.remember(builder, I32(status), I16(0))

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
