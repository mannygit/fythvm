"""Show phis as lowered block parameters instead of one-off merge hacks."""

from __future__ import annotations

import ctypes
from contextlib import contextmanager
from dataclasses import dataclass

from llvmlite import binding, ir

I32 = ir.IntType(32)
I64 = ir.IntType(64)


@dataclass(frozen=True)
class CompiledModule:
    llvm_ir: str
    engine: binding.ExecutionEngine
    select_addr: int
    zero_join_raw_addr: int
    zero_join_pythonic_addr: int
    raw_tuple_join_addr: int
    pythonic_tuple_join_addr: int
    state_join_addr: int


@dataclass(frozen=True)
class MachineState:
    x: ir.Value
    y: ir.Value
    tos: ir.Value


class Join:
    """Treat a merge block as if it had block parameters."""

    def __init__(self, builder: ir.IRBuilder, merge_block: ir.Block, specs: list[tuple[str, ir.Type]]):
        self.builder = builder
        self.merge_block = merge_block
        self.specs = specs
        self._phis: tuple[ir.PhiInstr, ...] = ()
        self._pending_incoming: list[tuple[ir.Block, tuple[ir.Value, ...]]] = []

    def __enter__(self) -> tuple[ir.PhiInstr, ...]:
        self.builder.position_at_end(self.merge_block)
        self._phis = tuple(self.builder.phi(ty, name=name) for name, ty in self.specs)
        for pred_block, values in self._pending_incoming:
            self._add_incoming_now(pred_block, *values)
        return self._phis

    def _add_incoming_now(self, pred_block: ir.Block, *values: ir.Value) -> None:
        if len(values) != len(self._phis):
            raise ValueError("incoming value count does not match join arity")

        for phi, value in zip(self._phis, values, strict=True):
            phi.add_incoming(value, pred_block)

    def add_incoming(self, pred_block: ir.Block, *values: ir.Value) -> None:
        if len(values) != len(self.specs):
            raise ValueError("incoming value count does not match join arity")

        if self._phis:
            self._add_incoming_now(pred_block, *values)
            return

        self._pending_incoming.append((pred_block, tuple(values)))

    def branch_from_here(self, builder: ir.IRBuilder, *values: ir.Value) -> None:
        pred_block = builder.basic_block
        builder.branch(self.merge_block)
        self.add_incoming(pred_block, *values)

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class StateJoin:
    """Named-state wrapper over Join for environment-style merge values."""

    def __init__(self, builder: ir.IRBuilder, merge_block: ir.Block):
        self.join = Join(builder, merge_block, [("x", I64), ("y", I64), ("tos", I64)])
        self._state: MachineState | None = None

    def __enter__(self) -> MachineState:
        x, y, tos = self.join.__enter__()
        self._state = MachineState(x=x, y=y, tos=tos)
        return self._state

    def add_incoming(self, pred_block: ir.Block, state: MachineState) -> None:
        self.join.add_incoming(pred_block, state.x, state.y, state.tos)

    def branch_from_here(self, builder: ir.IRBuilder, state: MachineState) -> None:
        self.join.branch_from_here(builder, state.x, state.y, state.tos)

    def __exit__(self, exc_type, exc, tb) -> bool:
        return self.join.__exit__(exc_type, exc, tb)


@contextmanager
def in_block(builder: ir.IRBuilder, block: ir.Block):
    builder.position_at_end(block)
    yield


def _configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def _emit_select_merge(module: ir.Module) -> None:
    fn_ty = ir.FunctionType(I64, [I64])
    func = ir.Function(module, fn_ty, name="select_merge")
    entry = func.append_basic_block("entry")
    builder = ir.IRBuilder(entry)
    is_non_negative = builder.icmp_signed(">=", func.args[0], ir.Constant(I64, 0), name="is_non_negative")
    positive = builder.add(func.args[0], ir.Constant(I64, 10), name="positive")
    negative = builder.sub(func.args[0], ir.Constant(I64, 10), name="negative")
    selected = builder.select(is_non_negative, positive, negative, name="selected")
    builder.ret(selected)


def _emit_zero_live_in_join_raw(module: ir.Module) -> None:
    fn_ty = ir.FunctionType(I64, [I64])
    func = ir.Function(module, fn_ty, name="zero_live_in_join_raw")
    entry = func.append_basic_block("entry")
    then_block = func.append_basic_block("then")
    else_block = func.append_basic_block("else")
    merge_block = func.append_basic_block("merge")

    builder = ir.IRBuilder(entry)
    is_even = builder.icmp_unsigned("==", builder.and_(func.args[0], ir.Constant(I64, 1)), ir.Constant(I64, 0))
    builder.cbranch(is_even, then_block, else_block)

    with in_block(builder, then_block):
        builder.branch(merge_block)

    with in_block(builder, else_block):
        builder.branch(merge_block)

    with in_block(builder, merge_block):
        result = builder.add(func.args[0], ir.Constant(I64, 100), name="result")
        builder.ret(result)


def _emit_tuple_join_raw(module: ir.Module) -> None:
    fn_ty = ir.FunctionType(I64, [I64, I64, I64])
    func = ir.Function(module, fn_ty, name="tuple_join_raw")
    entry = func.append_basic_block("entry")
    then_block = func.append_basic_block("then")
    else_block = func.append_basic_block("else")
    merge_block = func.append_basic_block("merge")

    builder = ir.IRBuilder(entry)
    is_non_negative = builder.icmp_signed(">=", func.args[0], ir.Constant(I64, 0), name="is_non_negative")
    builder.cbranch(is_non_negative, then_block, else_block)

    with in_block(builder, then_block):
        x_then = builder.add(func.args[0], ir.Constant(I64, 1), name="x_then")
        y_then = builder.mul(func.args[1], ir.Constant(I64, 2), name="y_then")
        tos_then = builder.add(func.args[2], ir.Constant(I64, 10), name="tos_then")
        builder.branch(merge_block)

    with in_block(builder, else_block):
        x_else = builder.sub(func.args[0], ir.Constant(I64, 1), name="x_else")
        y_else = builder.mul(func.args[1], ir.Constant(I64, 3), name="y_else")
        tos_else = builder.sub(func.args[2], ir.Constant(I64, 10), name="tos_else")
        builder.branch(merge_block)

    with in_block(builder, merge_block):
        x = builder.phi(I64, name="x")
        y = builder.phi(I64, name="y")
        tos = builder.phi(I64, name="tos")
        x.add_incoming(x_then, then_block)
        x.add_incoming(x_else, else_block)
        y.add_incoming(y_then, then_block)
        y.add_incoming(y_else, else_block)
        tos.add_incoming(tos_then, then_block)
        tos.add_incoming(tos_else, else_block)
        total = builder.add(builder.add(x, y, name="xy_sum"), tos, name="total")
        builder.ret(total)


def _emit_zero_live_in_join_pythonic(module: ir.Module) -> None:
    fn_ty = ir.FunctionType(I64, [I64])
    func = ir.Function(module, fn_ty, name="zero_live_in_join_pythonic")
    entry = func.append_basic_block("entry")
    then_block = func.append_basic_block("then")
    else_block = func.append_basic_block("else")
    merge_block = func.append_basic_block("merge")

    builder = ir.IRBuilder(entry)
    is_even = builder.icmp_unsigned("==", builder.and_(func.args[0], ir.Constant(I64, 1)), ir.Constant(I64, 0))
    builder.cbranch(is_even, then_block, else_block)

    join = Join(builder, merge_block, [])

    with in_block(builder, then_block):
        join.branch_from_here(builder)

    with in_block(builder, else_block):
        join.branch_from_here(builder)

    with join as merged_values:
        assert not merged_values
        result = builder.add(func.args[0], ir.Constant(I64, 100), name="result")
        builder.ret(result)


def _emit_tuple_join_pythonic(module: ir.Module) -> None:
    fn_ty = ir.FunctionType(I64, [I64, I64, I64])
    func = ir.Function(module, fn_ty, name="tuple_join_pythonic")
    entry = func.append_basic_block("entry")
    then_block = func.append_basic_block("then")
    else_block = func.append_basic_block("else")
    merge_block = func.append_basic_block("merge")

    builder = ir.IRBuilder(entry)
    is_non_negative = builder.icmp_signed(">=", func.args[0], ir.Constant(I64, 0), name="is_non_negative")
    builder.cbranch(is_non_negative, then_block, else_block)

    join = Join(builder, merge_block, [("x", I64), ("y", I64), ("tos", I64)])

    with in_block(builder, then_block):
        x_then = builder.add(func.args[0], ir.Constant(I64, 1), name="x_then")
        y_then = builder.mul(func.args[1], ir.Constant(I64, 2), name="y_then")
        tos_then = builder.add(func.args[2], ir.Constant(I64, 10), name="tos_then")
        join.branch_from_here(builder, x_then, y_then, tos_then)

    with in_block(builder, else_block):
        x_else = builder.sub(func.args[0], ir.Constant(I64, 1), name="x_else")
        y_else = builder.mul(func.args[1], ir.Constant(I64, 3), name="y_else")
        tos_else = builder.sub(func.args[2], ir.Constant(I64, 10), name="tos_else")
        join.branch_from_here(builder, x_else, y_else, tos_else)

    with join as (x, y, tos):
        total = builder.add(builder.add(x, y, name="xy_sum"), tos, name="total")
        builder.ret(total)


def _emit_state_join_pythonic(module: ir.Module) -> None:
    fn_ty = ir.FunctionType(I64, [I64, I64, I64])
    func = ir.Function(module, fn_ty, name="state_join_pythonic")
    entry = func.append_basic_block("entry")
    then_block = func.append_basic_block("then")
    else_block = func.append_basic_block("else")
    merge_block = func.append_basic_block("merge")

    builder = ir.IRBuilder(entry)
    is_non_negative = builder.icmp_signed(">=", func.args[0], ir.Constant(I64, 0), name="is_non_negative")
    builder.cbranch(is_non_negative, then_block, else_block)

    join = StateJoin(builder, merge_block)

    with in_block(builder, then_block):
        then_state = MachineState(
            x=builder.add(func.args[0], ir.Constant(I64, 1), name="x_then"),
            y=builder.mul(func.args[1], ir.Constant(I64, 2), name="y_then"),
            tos=builder.add(func.args[2], ir.Constant(I64, 10), name="tos_then"),
        )
        join.branch_from_here(builder, then_state)

    with in_block(builder, else_block):
        else_state = MachineState(
            x=builder.sub(func.args[0], ir.Constant(I64, 1), name="x_else"),
            y=builder.mul(func.args[1], ir.Constant(I64, 3), name="y_else"),
            tos=builder.sub(func.args[2], ir.Constant(I64, 10), name="tos_else"),
        )
        join.branch_from_here(builder, else_state)

    with join as state:
        total = builder.add(builder.add(state.x, state.y, name="xy_sum"), state.tos, name="total")
        builder.ret(total)


def build_module() -> ir.Module:
    module = ir.Module(name="block_parameter_joins")
    module.triple = binding.get_default_triple()
    _emit_select_merge(module)
    _emit_zero_live_in_join_raw(module)
    _emit_zero_live_in_join_pythonic(module)
    _emit_tuple_join_raw(module)
    _emit_tuple_join_pythonic(module)
    _emit_state_join_pythonic(module)
    return module


def compile_module(module: ir.Module) -> CompiledModule:
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    return CompiledModule(
        llvm_ir=llvm_ir,
        engine=engine,
        select_addr=engine.get_function_address("select_merge"),
        zero_join_raw_addr=engine.get_function_address("zero_live_in_join_raw"),
        zero_join_pythonic_addr=engine.get_function_address("zero_live_in_join_pythonic"),
        raw_tuple_join_addr=engine.get_function_address("tuple_join_raw"),
        pythonic_tuple_join_addr=engine.get_function_address("tuple_join_pythonic"),
        state_join_addr=engine.get_function_address("state_join_pythonic"),
    )


def call_i64_i64(address: int) -> ctypes._CFuncPtr:
    return ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)(address)


def call_i64_i64_i64_i64(address: int) -> ctypes._CFuncPtr:
    return ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64)(
        address
    )


def main() -> None:
    _configure_llvm()
    compiled = compile_module(build_module())
    select_merge = call_i64_i64(compiled.select_addr)
    zero_join_raw = call_i64_i64(compiled.zero_join_raw_addr)
    zero_join_pythonic = call_i64_i64(compiled.zero_join_pythonic_addr)
    raw_tuple_join = call_i64_i64_i64_i64(compiled.raw_tuple_join_addr)
    pythonic_tuple_join = call_i64_i64_i64_i64(compiled.pythonic_tuple_join_addr)
    state_join = call_i64_i64_i64_i64(compiled.state_join_addr)

    tuple_samples = [(-3, 5, 20), (4, 5, 20)]

    print("== Question ==")
    print("What is the general mental model behind phis once a control-flow merge carries more than one live value?")
    print()

    print("== Target Triple ==")
    print(binding.get_default_triple())
    print()

    print("== Case Summary ==")
    print("select_merge: no join block, no block parameters, no phis")
    print("zero_live_in_join_raw / zero_live_in_join_pythonic: real CFG join with zero block parameters")
    print("tuple_join_raw / tuple_join_pythonic / state_join_pythonic: one join block with x, y, tos as block parameters lowered to phis")
    print()

    print("== Generated IR ==")
    print(compiled.llvm_ir.rstrip())
    print()

    print("== Runtime Results ==")
    for value in (-3, 4):
        print(
            f"select input {value:>2}: select_merge -> {select_merge(value):>3} | "
            f"zero_join_raw -> {zero_join_raw(value):>3} | "
            f"zero_join -> {zero_join_pythonic(value):>3}"
        )
    for a, b, tos in tuple_samples:
        print(
            f"tuple input ({a:>2}, {b:>2}, {tos:>2}): raw -> {raw_tuple_join(a, b, tos):>3} | "
            f"tuple_join -> {pythonic_tuple_join(a, b, tos):>3} | "
            f"state_join -> {state_join(a, b, tos):>3}"
        )
    print()

    print("== What To Notice ==")
    print("The tuple join is the source of truth: each predecessor computes one outgoing environment, and the merge block rebuilds that environment with one phi per live-in.")
    print("Join treats the merge block as if it had block parameters: predecessors contribute edge values, and the block body consumes merged entry values.")
    print("Join.branch_from_here() is the next semantic step: predecessors do not just add phi inputs, they transfer control to the successor carrying an outgoing environment.")
    print("StateJoin does not change the lowering. It only lets the same block-entry values read like one named environment instead of one naked tuple.")


if __name__ == "__main__":
    main()
