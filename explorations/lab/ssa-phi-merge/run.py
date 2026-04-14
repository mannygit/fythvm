"""Show when llvmlite needs a phi node at a control-flow merge."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import binding, ir


@dataclass(frozen=True)
class CompiledModule:
    llvm_ir: str
    engine: binding.ExecutionEngine
    branch_addr: int
    select_addr: int


def _configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def build_phi_module() -> ir.Module:
    i64 = ir.IntType(64)
    i1 = ir.IntType(1)
    module = ir.Module(name="ssa_phi_merge")
    module.triple = binding.get_default_triple()

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
        branch_addr=engine.get_function_address("branch_merge"),
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
    compiled = compile_module(build_phi_module())
    branch = call_i64_i64(compiled.branch_addr)
    select = call_i64_i64(compiled.select_addr)

    samples = [-3, 0, 4]

    print("== Question ==")
    print("When does a control-flow merge need a phi node instead of a straight-line expression?")
    print()

    print("== Target Triple ==")
    print(binding.get_default_triple())
    print()

    print("== Generated IR ==")
    print(compiled.llvm_ir.rstrip())
    print()

    print("== Runtime Results ==")
    for value in samples:
        branch_result = branch(value)
        select_result = select(value)
        print(f"input {value:>2}: branch_merge -> {branch_result:>3} | select_merge -> {select_result:>3}")
    print()

    print("== Invalid Attempt ==")
    print("broken_branch_merge() without phi verification error:")
    print(show_invalid_module_failure())
    print()

    print("== What To Notice ==")
    print("The branch version needs a phi at the merge block because each predecessor computes a different runtime value.")
    print("The select version works only because both candidate values are safe to compute eagerly in straight line.")


if __name__ == "__main__":
    main()
