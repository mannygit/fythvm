"""Show how a value-producing conditional lowers into llvmlite SSA."""

from __future__ import annotations

import ctypes
from contextlib import contextmanager
from dataclasses import dataclass

from llvmlite import binding, ir


@dataclass(frozen=True)
class CompiledModule:
    llvm_ir: str
    engine: binding.ExecutionEngine
    raw_branch_addr: int
    pythonic_branch_addr: int
    select_addr: int


class BranchMergeShape:
    """Local helper that keeps the blocks explicit while removing positioning noise."""

    def __init__(self, function: ir.Function, prefix: str):
        self.builder = ir.IRBuilder(function.append_basic_block(f"{prefix}.entry"))
        self.then_block = function.append_basic_block(f"{prefix}.then")
        self.else_block = function.append_basic_block(f"{prefix}.else")
        self.merge_block = function.append_basic_block(f"{prefix}.merge")
        self._incoming: list[tuple[ir.Value, object]] = []

    def branch(self, condition: ir.Value) -> None:
        self.builder.cbranch(condition, self.then_block, self.else_block)

    @contextmanager
    def then(self):
        self.builder.position_at_end(self.then_block)
        yield self
        if self.builder.basic_block.terminator is None:
            self.builder.branch(self.merge_block)

    @contextmanager
    def otherwise(self):
        self.builder.position_at_end(self.else_block)
        yield self
        if self.builder.basic_block.terminator is None:
            self.builder.branch(self.merge_block)

    def remember(self, value: ir.Value) -> None:
        self._incoming.append((value, self.builder.basic_block))

    def finish(self, ty: ir.Type, name: str = "merged") -> ir.Value:
        self.builder.position_at_end(self.merge_block)
        merged = self.builder.phi(ty, name=name)
        for value, block in self._incoming:
            merged.add_incoming(value, block)
        return merged


def _configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def _emit_raw_branch_merge(module: ir.Module, i64: ir.IntType) -> None:
    fn_ty = ir.FunctionType(i64, [i64])
    func = ir.Function(module, fn_ty, name="branch_merge")
    entry = func.append_basic_block(name="entry")
    then_block = func.append_basic_block(name="then")
    else_block = func.append_basic_block(name="else")
    merge_block = func.append_basic_block(name="merge")

    builder = ir.IRBuilder(entry)
    condition = builder.icmp_signed(">=", func.args[0], ir.Constant(i64, 0), name="is_non_negative")
    builder.cbranch(condition, then_block, else_block)

    builder.position_at_end(then_block)
    then_value = builder.add(func.args[0], ir.Constant(i64, 10), name="then_value")
    builder.branch(merge_block)

    builder.position_at_end(else_block)
    else_value = builder.sub(func.args[0], ir.Constant(i64, 10), name="else_value")
    builder.branch(merge_block)

    builder.position_at_end(merge_block)
    merged = builder.phi(i64, name="merged")
    merged.add_incoming(then_value, then_block)
    merged.add_incoming(else_value, else_block)
    builder.ret(merged)


def _emit_pythonic_branch_merge(module: ir.Module, i64: ir.IntType) -> None:
    fn_ty = ir.FunctionType(i64, [i64])
    func = ir.Function(module, fn_ty, name="branch_merge_pythonic")
    join = BranchMergeShape(func, "py_branch_merge")

    condition = join.builder.icmp_signed(
        ">=", func.args[0], ir.Constant(i64, 0), name="is_non_negative"
    )
    join.branch(condition)

    with join.then():
        then_value = join.builder.add(func.args[0], ir.Constant(i64, 10), name="then_value")
        join.remember(then_value)

    with join.otherwise():
        else_value = join.builder.sub(func.args[0], ir.Constant(i64, 10), name="else_value")
        join.remember(else_value)

    merged = join.finish(i64, name="merged")
    join.builder.ret(merged)


def _emit_select_merge(module: ir.Module, i64: ir.IntType) -> None:
    fn_ty = ir.FunctionType(i64, [i64])
    select_fn = ir.Function(module, fn_ty, name="select_merge")
    select_entry = select_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(select_entry)
    select_condition = builder.icmp_signed(
        ">=", select_fn.args[0], ir.Constant(i64, 0), name="is_non_negative"
    )
    positive = builder.add(select_fn.args[0], ir.Constant(i64, 10), name="positive")
    negative = builder.sub(select_fn.args[0], ir.Constant(i64, 10), name="negative")
    selected = builder.select(select_condition, positive, negative, name="selected")
    builder.ret(selected)


def build_module() -> ir.Module:
    i64 = ir.IntType(64)
    module = ir.Module(name="ssa_phi_merge")
    module.triple = binding.get_default_triple()

    _emit_raw_branch_merge(module, i64)
    _emit_pythonic_branch_merge(module, i64)
    _emit_select_merge(module, i64)
    return module


def build_invalid_module() -> ir.Module:
    i64 = ir.IntType(64)
    module = ir.Module(name="ssa_phi_merge_invalid")
    module.triple = binding.get_default_triple()

    fn_ty = ir.FunctionType(i64, [i64])
    func = ir.Function(module, fn_ty, name="broken_branch_merge")
    entry = func.append_basic_block(name="entry")
    then_block = func.append_basic_block(name="then")
    else_block = func.append_basic_block(name="else")
    merge_block = func.append_basic_block(name="merge")

    builder = ir.IRBuilder(entry)
    condition = builder.icmp_signed(">=", func.args[0], ir.Constant(i64, 0), name="is_non_negative")
    builder.cbranch(condition, then_block, else_block)

    builder.position_at_end(then_block)
    then_value = builder.add(func.args[0], ir.Constant(i64, 10), name="then_value")
    builder.branch(merge_block)

    builder.position_at_end(else_block)
    builder.sub(func.args[0], ir.Constant(i64, 10), name="else_value")
    builder.branch(merge_block)

    builder.position_at_end(merge_block)
    builder.ret(then_value)

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
        raw_branch_addr=engine.get_function_address("branch_merge"),
        pythonic_branch_addr=engine.get_function_address("branch_merge_pythonic"),
        select_addr=engine.get_function_address("select_merge"),
    )


def call_i64_i64(address: int) -> ctypes._CFuncPtr:
    return ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)(address)


def show_invalid_module_failure() -> str:
    invalid_module = build_invalid_module()
    try:
        parsed = binding.parse_assembly(str(invalid_module))
        parsed.verify()
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


def main() -> None:
    _configure_llvm()
    compiled = compile_module(build_module())
    raw_branch = call_i64_i64(compiled.raw_branch_addr)
    pythonic_branch = call_i64_i64(compiled.pythonic_branch_addr)
    select = call_i64_i64(compiled.select_addr)

    samples = [-3, 0, 4]

    print("== Question ==")
    print("How does a value-producing conditional, including a ternary-like shape, lower into LLVM SSA?")
    print()

    print("== Target Triple ==")
    print(binding.get_default_triple())
    print()

    print("== Generated IR ==")
    print(compiled.llvm_ir.rstrip())
    print()

    print("== Raw vs Pythonic ==")
    for value in samples:
        raw_result = raw_branch(value)
        pythonic_result = pythonic_branch(value)
        select_result = select(value)
        print(
            f"input {value:>2}: raw_branch -> {raw_result:>3} | "
            f"pythonic_branch -> {pythonic_result:>3} | select_merge -> {select_result:>3}"
        )
    print()

    print("== Invalid Attempt ==")
    print("broken_branch_merge() without phi verification error:")
    print(show_invalid_module_failure())
    print()

    print("== What To Notice ==")
    print(
        "This example is ternary-sized on purpose: select_merge() is the straight-line conditional form, while the branch variants show the same value choice lowered through explicit CFG and phi."
    )
    print(
        "The raw branch version is the source of truth: explicit blocks, explicit predecessors, explicit phi inputs."
    )
    print(
        "The Pythonic version stays intentionally thin and keeps the same CFG visible; it only removes branch/positioning boilerplate because this lab is about the lowering itself, not a richer host-side protocol."
    )


if __name__ == "__main__":
    main()
