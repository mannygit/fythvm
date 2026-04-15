"""Evaluate a small raw-cell RPN calculator through JIT-emitted LLVM."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import binding, ir


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

I1 = ir.IntType(1)
I16 = ir.IntType(16)
I16_PTR = I16.as_pointer()
I32 = ir.IntType(32)


class CalcContext(ctypes.Structure):
    _fields_ = [
        ("stack", ctypes.c_int16 * STACK_SIZE),
        ("sp", ctypes.c_int32),
    ]


@dataclass(frozen=True)
class Scenario:
    name: str
    cells: tuple[int, ...]
    expected_status: int
    expected_result: int | None


@dataclass(frozen=True)
class ScenarioResult:
    status: int
    result: int
    sp: int
    logical_stack: list[int]


@dataclass(frozen=True)
class CompiledModule:
    label: str
    llvm_ir: str
    engine: binding.ExecutionEngine
    eval_addr: int


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def lit(value: int) -> int:
    if not 0 <= value <= LITERAL_MAX:
        raise ValueError(f"literal out of 15-bit range: {value}")
    return value


def op(symbol: str) -> int:
    if len(symbol) != 1 or symbol not in "+-*/%=":
        raise ValueError(f"unsupported operator: {symbol!r}")
    return TAG_MASK | ord(symbol)


def logical_stack(ctx: CalcContext) -> list[int]:
    return [int(value) for value in reversed(ctx.stack[ctx.sp:STACK_SIZE])]


def format_cells(cells: tuple[int, ...]) -> str:
    return "[" + ", ".join(str(cell) for cell in cells) + "]"


def render_program(cells: tuple[int, ...]) -> str:
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


class EvalExit:
    """Collect one status/result pair at a shared exit block."""

    def __init__(self, function: ir.Function, out_result_ptr: ir.Value):
        self.builder = ir.IRBuilder(function.append_basic_block("exit"))
        self.exit_block = self.builder.basic_block
        self.out_result_ptr = out_result_ptr
        self._incoming: list[tuple[ir.Value, ir.Value, ir.Block]] = []

    def remember(self, builder: ir.IRBuilder, status: ir.Value, result: ir.Value) -> None:
        self._incoming.append((status, result, builder.basic_block))
        builder.branch(self.exit_block)

    def finish(self) -> None:
        self.builder.position_at_end(self.exit_block)
        status_phi = self.builder.phi(I32, name="status")
        result_phi = self.builder.phi(I16, name="result")
        for status, result, block in self._incoming:
            status_phi.add_incoming(status, block)
            result_phi.add_incoming(result, block)
        self.builder.store(result_phi, self.out_result_ptr)
        self.builder.ret(status_phi)


class AbstractStackAccess:
    """Keep stack semantics separate from how the stack fields are reached."""

    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        raise NotImplementedError

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        raise NotImplementedError

    def slot(self, builder: ir.IRBuilder, index: ir.Value, name: str = "slot_ptr") -> ir.Value:
        return builder.gep(self.load_stack_base(builder), [index], inbounds=True, name=name)

    def load_sp(self, builder: ir.IRBuilder, name: str = "sp") -> ir.Value:
        return builder.load(self.load_sp_ptr(builder), name=name)

    def store_sp(self, builder: ir.IRBuilder, value: ir.Value) -> None:
        builder.store(value, self.load_sp_ptr(builder))


class ContextStructStackAccess(AbstractStackAccess):
    def __init__(self, ctx_ptr: ir.Value):
        self.ctx_ptr = ctx_ptr

    def load_stack_base(self, builder: ir.IRBuilder) -> ir.Value:
        stack_array_ptr = builder.gep(self.ctx_ptr, [I32(0), I32(0)], inbounds=True, name="stack_array_ptr")
        return builder.gep(stack_array_ptr, [I32(0), I32(0)], inbounds=True, name="stack_base")

    def load_sp_ptr(self, builder: ir.IRBuilder) -> ir.Value:
        return builder.gep(self.ctx_ptr, [I32(0), I32(1)], inbounds=True, name="sp_ptr")


class CalculatorEmitter:
    """Thin helper over the repetitive dispatch and exit scaffolding."""

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
        self.exit = EvalExit(self.function, self.out_result_ptr)
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
        self.exit.finish()


def build_raw_module() -> ir.Module:
    module = ir.Module(name="cell_rpn_calculator_raw")
    module.triple = binding.get_default_triple()

    ctx_type = ir.LiteralStructType([ir.ArrayType(I16, STACK_SIZE), I32])
    fn_ty = ir.FunctionType(I32, [I16_PTR, I32, ctx_type.as_pointer(), I16_PTR])
    func = ir.Function(module, fn_ty, name="eval_cells_raw")
    cells_ptr, cell_count, ctx_ptr, out_result_ptr = func.args

    def stack_base(builder: ir.IRBuilder) -> ir.Value:
        stack_array_ptr = builder.gep(ctx_ptr, [I32(0), I32(0)], inbounds=True, name="stack_array_ptr")
        return builder.gep(stack_array_ptr, [I32(0), I32(0)], inbounds=True, name="stack_base")

    def sp_ptr(builder: ir.IRBuilder) -> ir.Value:
        return builder.gep(ctx_ptr, [I32(0), I32(1)], inbounds=True, name="sp_ptr")

    def slot(builder: ir.IRBuilder, index: ir.Value, name: str = "slot_ptr") -> ir.Value:
        return builder.gep(stack_base(builder), [index], inbounds=True, name=name)

    def load_sp(builder: ir.IRBuilder, name: str = "sp") -> ir.Value:
        return builder.load(sp_ptr(builder), name=name)

    def store_sp(builder: ir.IRBuilder, value: ir.Value) -> None:
        builder.store(value, sp_ptr(builder))

    entry = func.append_basic_block("entry")
    loop_block = func.append_basic_block("loop")
    dispatch_block = func.append_basic_block("dispatch")
    literal_check_block = func.append_basic_block("literal.check")
    literal_store_block = func.append_basic_block("literal.store")
    opcode_block = func.append_basic_block("opcode.dispatch")
    missing_exit_block = func.append_basic_block("missing_exit")
    underflow_block = func.append_basic_block("underflow")
    divzero_block = func.append_basic_block("divzero")
    bad_opcode_block = func.append_basic_block("bad_opcode")
    bad_exit_shape_block = func.append_basic_block("bad_exit_shape")
    overflow_block = func.append_basic_block("overflow")
    ok_block = func.append_basic_block("ok")
    ok_singleton_block = func.append_basic_block("ok.singleton")
    exit_block = func.append_basic_block("exit")

    incoming: list[tuple[ir.Value, ir.Value, ir.Block]] = []

    def remember_exit(builder: ir.IRBuilder, status: ir.Value, result: ir.Value) -> None:
        incoming.append((status, result, builder.basic_block))
        builder.branch(exit_block)

    builder = ir.IRBuilder(entry)
    store_sp(builder, I32(STACK_SIZE))
    builder.branch(loop_block)

    builder.position_at_end(loop_block)
    ip = builder.phi(I32, name="ip")
    ip.add_incoming(I32(0), entry)
    reached_end = builder.icmp_signed(">=", ip, cell_count, name="reached_end")
    builder.cbranch(reached_end, missing_exit_block, dispatch_block)

    builder.position_at_end(dispatch_block)
    cell_ptr = builder.gep(cells_ptr, [ip], inbounds=True, name="cell_ptr")
    cell = builder.load(cell_ptr, name="cell")
    next_ip = builder.add(ip, I32(1), name="next_ip")
    tag_bits = builder.and_(cell, I16(TAG_MASK), name="tag_bits")
    is_literal = builder.icmp_unsigned("==", tag_bits, I16(0), name="is_literal")
    builder.cbranch(is_literal, literal_check_block, opcode_block)

    builder.position_at_end(literal_check_block)
    current_sp = load_sp(builder)
    has_room = builder.icmp_unsigned("!=", current_sp, I32(0), name="has_room")
    builder.cbranch(has_room, literal_store_block, overflow_block)

    builder.position_at_end(literal_store_block)
    current_sp = load_sp(builder)
    new_sp = builder.sub(current_sp, I32(1), name="new_sp")
    builder.store(cell, slot(builder, new_sp))
    store_sp(builder, new_sp)
    ip.add_incoming(next_ip, literal_store_block)
    builder.branch(loop_block)

    builder.position_at_end(opcode_block)
    switch = builder.switch(cell, bad_opcode_block)

    def emit_binary_handler(opcode_value: int, name: str, operation, *, zero_sensitive: bool = False) -> None:
        check_block = func.append_basic_block(f"{name}.check")
        apply_block = func.append_basic_block(f"{name}.apply")
        switch.add_case(I16(opcode_value), check_block)

        builder.position_at_end(check_block)
        current_sp = load_sp(builder)
        enough_items = builder.icmp_unsigned("<=", current_sp, I32(STACK_SIZE - 2), name=f"{name}_enough")
        if zero_sensitive:
            zero_check_block = func.append_basic_block(f"{name}.zero_check")
            builder.cbranch(enough_items, zero_check_block, underflow_block)

            builder.position_at_end(zero_check_block)
            rhs = builder.load(slot(builder, current_sp, name=f"{name}_rhs_ptr"), name="rhs")
            rhs_is_zero = builder.icmp_signed("==", rhs, I16(0), name=f"{name}_rhs_is_zero")
            builder.cbranch(rhs_is_zero, divzero_block, apply_block)
        else:
            builder.cbranch(enough_items, apply_block, underflow_block)

        builder.position_at_end(apply_block)
        current_sp = load_sp(builder)
        rhs = builder.load(slot(builder, current_sp, name=f"{name}_rhs_ptr"), name="rhs")
        lhs_index = builder.add(current_sp, I32(1), name="lhs_index")
        lhs = builder.load(slot(builder, lhs_index, name=f"{name}_lhs_ptr"), name="lhs")
        result = operation(builder, lhs, rhs)
        builder.store(result, slot(builder, lhs_index, name=f"{name}_result_ptr"))
        store_sp(builder, lhs_index)
        ip.add_incoming(next_ip, apply_block)
        builder.branch(loop_block)

    emit_binary_handler(OP_ADD, "add", lambda builder, lhs, rhs: builder.add(lhs, rhs, name="sum"))
    emit_binary_handler(OP_SUB, "sub", lambda builder, lhs, rhs: builder.sub(lhs, rhs, name="diff"))
    emit_binary_handler(OP_MUL, "mul", lambda builder, lhs, rhs: builder.mul(lhs, rhs, name="product"))
    emit_binary_handler(OP_DIV, "div", lambda builder, lhs, rhs: builder.sdiv(lhs, rhs, name="quotient"), zero_sensitive=True)
    emit_binary_handler(OP_MOD, "mod", lambda builder, lhs, rhs: builder.srem(lhs, rhs, name="remainder"), zero_sensitive=True)

    switch.add_case(I16(OP_EXIT), ok_block)

    builder.position_at_end(ok_block)
    current_sp = load_sp(builder)
    has_single_value = builder.icmp_unsigned("==", current_sp, I32(STACK_SIZE - 1), name="has_single_value")
    builder.cbranch(has_single_value, ok_singleton_block, bad_exit_shape_block)

    builder.position_at_end(ok_singleton_block)
    result = builder.load(slot(builder, current_sp), name="result")
    remember_exit(builder, I32(STATUS_OK), result)

    for block, status in (
        (missing_exit_block, STATUS_MISSING_EXIT),
        (underflow_block, STATUS_STACK_UNDERFLOW),
        (divzero_block, STATUS_DIVIDE_BY_ZERO),
        (bad_opcode_block, STATUS_BAD_OPCODE),
        (bad_exit_shape_block, STATUS_STACK_NOT_SINGLETON),
        (overflow_block, STATUS_STACK_OVERFLOW),
    ):
        builder.position_at_end(block)
        remember_exit(builder, I32(status), I16(0))

    builder.position_at_end(exit_block)
    status_phi = builder.phi(I32, name="status")
    result_phi = builder.phi(I16, name="result")
    for status, exit_result, block in incoming:
        status_phi.add_incoming(status, block)
        result_phi.add_incoming(exit_result, block)
    builder.store(result_phi, out_result_ptr)
    builder.ret(status_phi)

    return module


def build_pythonic_module() -> ir.Module:
    module = ir.Module(name="cell_rpn_calculator_pythonic")
    module.triple = binding.get_default_triple()
    CalculatorEmitter(module, "eval_cells_pythonic").emit()
    return module


def compile_module(label: str, module: ir.Module, function_name: str) -> CompiledModule:
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()
    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()
    return CompiledModule(
        label=label,
        llvm_ir=llvm_ir,
        engine=engine,
        eval_addr=engine.get_function_address(function_name),
    )


def run_program(compiled: CompiledModule, cells: tuple[int, ...]) -> ScenarioResult:
    program = (ctypes.c_uint16 * len(cells))(*cells)
    result = ctypes.c_int16(0)
    ctx = CalcContext()

    eval_cells = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int16),
        ctypes.c_int32,
        ctypes.POINTER(CalcContext),
        ctypes.POINTER(ctypes.c_int16),
    )(compiled.eval_addr)

    status = int(
        eval_cells(
            ctypes.cast(program, ctypes.POINTER(ctypes.c_int16)),
            len(cells),
            ctypes.byref(ctx),
            ctypes.byref(result),
        )
    )
    return ScenarioResult(
        status=status,
        result=int(result.value),
        sp=int(ctx.sp),
        logical_stack=logical_stack(ctx),
    )


def scenario_line(scenario: Scenario, result: ScenarioResult) -> str:
    return (
        f"{scenario.name}: program={render_program(scenario.cells)} raw_cells={format_cells(scenario.cells)} "
        f"-> status={status_name(result.status)}({result.status}), result={result.result}, "
        f"sp={result.sp}, logical_stack={result.logical_stack}"
    )


def build_scenarios() -> list[Scenario]:
    return [
        Scenario("sum_chain", (lit(2), lit(1), lit(1), op("+"), op("+"), op("=")), STATUS_OK, 4),
        Scenario("division", (lit(100), lit(10), op("/"), op("=")), STATUS_OK, 10),
        Scenario("underflow", (op("+"), op("=")), STATUS_STACK_UNDERFLOW, None),
        Scenario("divide_by_zero", (lit(10), lit(0), op("/"), op("=")), STATUS_DIVIDE_BY_ZERO, None),
        Scenario("bad_opcode", (lit(5), TAG_MASK | ord("^"), op("=")), STATUS_BAD_OPCODE, None),
        Scenario("missing_exit", (lit(1), lit(2), op("+")), STATUS_MISSING_EXIT, None),
        Scenario("bad_exit_shape", (lit(1), lit(2), op("=")), STATUS_STACK_NOT_SINGLETON, None),
        Scenario(
            "overflow",
            (
                lit(0),
                lit(1),
                lit(2),
                lit(3),
                lit(4),
                lit(5),
                lit(6),
                lit(7),
                lit(8),
                op("="),
            ),
            STATUS_STACK_OVERFLOW,
            None,
        ),
    ]


def print_trace(title: str, lines: list[str]) -> None:
    print(f"== {title} ==")
    for line in lines:
        print(line)
    print()


def main() -> None:
    configure_llvm()

    raw = compile_module("raw", build_raw_module(), "eval_cells_raw")
    pythonic = compile_module("pythonic", build_pythonic_module(), "eval_cells_pythonic")
    scenarios = build_scenarios()

    raw_lines: list[str] = []
    pythonic_lines: list[str] = []

    for scenario in scenarios:
        raw_result = run_program(raw, scenario.cells)
        pythonic_result = run_program(pythonic, scenario.cells)
        assert raw_result == pythonic_result, f"variant mismatch for {scenario.name}"
        assert raw_result.status == scenario.expected_status, f"unexpected status for {scenario.name}"
        if scenario.expected_result is not None:
            assert raw_result.result == scenario.expected_result, f"unexpected result for {scenario.name}"

        raw_lines.append(scenario_line(scenario, raw_result))
        pythonic_lines.append(scenario_line(scenario, pythonic_result))

    print("== Question ==")
    print("What is the smallest useful raw-cell RPN calculator once the program is a 16-bit cell buffer, the stack lives in a passed context struct, and '=' is the only exit instruction?")
    print()

    print("== Raw IR ==")
    print(raw.llvm_ir.rstrip())
    print()

    print("== Pythonic IR ==")
    print(pythonic.llvm_ir.rstrip())
    print()

    print_trace("Raw Runtime Scenarios", raw_lines)
    print_trace("Pythonic Runtime Scenarios", pythonic_lines)

    print("== Comparison ==")
    print(f"all scenario lines match: {raw_lines == pythonic_lines}")
    print(f"successful examples covered: {[render_program(s.cells) for s in scenarios if s.expected_status == STATUS_OK]}")
    print()

    print("== Takeaway ==")
    print("Treat the calculator as a raw-cell interpreter: one loop carries the instruction pointer, the context struct owns the stack, and '=' defines the explicit exit contract.")
    print("The Pythonic layer earns its keep only by centralizing context-backed stack access, shared exit bookkeeping, and repetitive dispatch scaffolding without hiding the opcode branches or loop state.")


if __name__ == "__main__":
    main()
