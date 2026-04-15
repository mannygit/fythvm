"""Tiny raw-cell RPN calculator built on promoted codegen primitives."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Sequence

from llvmlite import binding, ir

from .codegen import (
    I16,
    I16_PTR,
    I32,
    ContextStructStackAccess,
    SharedExit,
    compile_ir_module,
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
        self.loop_block = self.function.append_basic_block("loop")
        self.dispatch_block = self.function.append_basic_block("dispatch")
        self.literal_check_block = self.function.append_basic_block("literal.check")
        self.literal_store_block = self.function.append_basic_block("literal.store")
        self.opcode_block = self.function.append_basic_block("opcode.dispatch")
        self.missing_exit_block = self.function.append_basic_block("missing_exit")
        self.underflow_block = self.function.append_basic_block("underflow")
        self.divzero_block = self.function.append_basic_block("divzero")
        self.bad_opcode_block = self.function.append_basic_block("bad_opcode")
        self.bad_exit_shape_block = self.function.append_basic_block("bad_exit_shape")
        self.overflow_block = self.function.append_basic_block("overflow")
        self.ok_block = self.function.append_basic_block("ok")
        self.builder = ir.IRBuilder(self.entry_block)
        self.exit = SharedExit(self.function, [("status", I32), ("result", I16)])
        self.ip_phi: ir.PhiInstr | None = None
        self.next_ip: ir.Value | None = None
        self.current_cell: ir.Value | None = None
        self.switch: ir.instructions.SwitchInstr | None = None

    def emit_skeleton(self) -> None:
        self.stack.store_sp(self.builder, I32(STACK_SIZE))
        self.builder.branch(self.loop_block)

        self.builder.position_at_end(self.loop_block)
        self.ip_phi = self.builder.phi(I32, name="ip")
        self.ip_phi.add_incoming(I32(0), self.entry_block)
        reached_end = self.builder.icmp_signed(">=", self.ip_phi, self.cell_count, name="reached_end")
        self.builder.cbranch(reached_end, self.missing_exit_block, self.dispatch_block)

        self.builder.position_at_end(self.dispatch_block)
        cell_ptr = self.builder.gep(self.cells_ptr, [self.ip_phi], inbounds=True, name="cell_ptr")
        self.current_cell = self.builder.load(cell_ptr, name="cell")
        self.next_ip = self.builder.add(self.ip_phi, I32(1), name="next_ip")
        is_literal = self.builder.icmp_unsigned(
            "==",
            self.builder.and_(self.current_cell, I16(TAG_MASK), name="tag_bits"),
            I16(0),
            name="is_literal",
        )
        self.builder.cbranch(is_literal, self.literal_check_block, self.opcode_block)

    def emit_literal_handler(self) -> None:
        assert self.ip_phi is not None
        assert self.next_ip is not None
        assert self.current_cell is not None

        self.builder.position_at_end(self.literal_check_block)
        current_sp = self.stack.load_sp(self.builder)
        has_room = self.builder.icmp_unsigned("!=", current_sp, I32(0), name="has_room")
        self.builder.cbranch(has_room, self.literal_store_block, self.overflow_block)

        self.builder.position_at_end(self.literal_store_block)
        current_sp = self.stack.load_sp(self.builder)
        new_sp = self.builder.sub(current_sp, I32(1), name="new_sp")
        self.builder.store(self.current_cell, self.stack.slot(self.builder, new_sp))
        self.stack.store_sp(self.builder, new_sp)
        self.ip_phi.add_incoming(self.next_ip, self.literal_store_block)
        self.builder.branch(self.loop_block)

    def emit_binary_handler(
        self,
        opcode_value: int,
        name: str,
        operation,
        *,
        zero_sensitive: bool = False,
    ) -> None:
        assert self.switch is not None
        assert self.ip_phi is not None
        assert self.next_ip is not None

        check_block = self.function.append_basic_block(f"{name}.check")
        self.switch.add_case(I16(opcode_value), check_block)

        apply_block = self.function.append_basic_block(f"{name}.apply")
        self.builder.position_at_end(check_block)
        current_sp = self.stack.load_sp(self.builder)
        enough_items = self.builder.icmp_unsigned("<=", current_sp, I32(STACK_SIZE - 2), name=f"{name}_enough")
        if zero_sensitive:
            zero_check_block = self.function.append_basic_block(f"{name}.zero_check")
            self.builder.cbranch(enough_items, zero_check_block, self.underflow_block)

            self.builder.position_at_end(zero_check_block)
            rhs = self.builder.load(self.stack.slot(self.builder, current_sp, name=f"{name}_rhs_ptr"), name="rhs")
            rhs_is_zero = self.builder.icmp_signed("==", rhs, I16(0), name=f"{name}_rhs_is_zero")
            self.builder.cbranch(rhs_is_zero, self.divzero_block, apply_block)
        else:
            self.builder.cbranch(enough_items, apply_block, self.underflow_block)

        self.builder.position_at_end(apply_block)
        current_sp = self.stack.load_sp(self.builder)
        rhs = self.builder.load(self.stack.slot(self.builder, current_sp, name=f"{name}_rhs_ptr"), name="rhs")
        lhs_index = self.builder.add(current_sp, I32(1), name="lhs_index")
        lhs = self.builder.load(self.stack.slot(self.builder, lhs_index, name=f"{name}_lhs_ptr"), name="lhs")
        result = operation(self.builder, lhs, rhs)
        self.builder.store(result, self.stack.slot(self.builder, lhs_index, name=f"{name}_result_ptr"))
        self.stack.store_sp(self.builder, lhs_index)
        self.ip_phi.add_incoming(self.next_ip, apply_block)
        self.builder.branch(self.loop_block)

    def emit_exit_handler(self) -> None:
        assert self.switch is not None

        self.switch.add_case(I16(OP_EXIT), self.ok_block)

        self.builder.position_at_end(self.ok_block)
        current_sp = self.stack.load_sp(self.builder)
        has_single_value = self.builder.icmp_unsigned(
            "==", current_sp, I32(STACK_SIZE - 1), name="has_single_value"
        )
        singleton_ok_block = self.function.append_basic_block("ok.singleton")
        self.builder.cbranch(has_single_value, singleton_ok_block, self.bad_exit_shape_block)

        self.builder.position_at_end(singleton_ok_block)
        result = self.builder.load(self.stack.slot(self.builder, current_sp), name="result")
        self.exit.remember(self.builder, I32(STATUS_OK), result)

    def emit_error_blocks(self) -> None:
        for block, status in (
            (self.missing_exit_block, STATUS_MISSING_EXIT),
            (self.underflow_block, STATUS_STACK_UNDERFLOW),
            (self.divzero_block, STATUS_DIVIDE_BY_ZERO),
            (self.bad_opcode_block, STATUS_BAD_OPCODE),
            (self.bad_exit_shape_block, STATUS_STACK_NOT_SINGLETON),
            (self.overflow_block, STATUS_STACK_OVERFLOW),
        ):
            self.builder.position_at_end(block)
            self.exit.remember(self.builder, I32(status), I16(0))

    def emit(self) -> None:
        self.emit_skeleton()
        self.emit_literal_handler()

        self.builder.position_at_end(self.opcode_block)
        assert self.current_cell is not None
        self.switch = self.builder.switch(self.current_cell, self.bad_opcode_block)

        self.emit_binary_handler(OP_ADD, "add", lambda builder, lhs, rhs: builder.add(lhs, rhs, name="sum"))
        self.emit_binary_handler(OP_SUB, "sub", lambda builder, lhs, rhs: builder.sub(lhs, rhs, name="diff"))
        self.emit_binary_handler(OP_MUL, "mul", lambda builder, lhs, rhs: builder.mul(lhs, rhs, name="product"))
        self.emit_binary_handler(
            OP_DIV,
            "div",
            lambda builder, lhs, rhs: builder.sdiv(lhs, rhs, name="quotient"),
            zero_sensitive=True,
        )
        self.emit_binary_handler(
            OP_MOD,
            "mod",
            lambda builder, lhs, rhs: builder.srem(lhs, rhs, name="remainder"),
            zero_sensitive=True,
        )
        self.emit_exit_handler()
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
