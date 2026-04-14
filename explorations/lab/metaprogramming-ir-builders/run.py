"""Explore a thin metaprogramming helper for llvmlite IR builders."""

from __future__ import annotations

import ctypes

from llvmlite import binding, ir


I64 = ir.IntType(64)


def emit_if_else_value(
    builder: ir.IRBuilder,
    condition: ir.Value,
    then_value: ir.Value,
    else_value: ir.Value,
    *,
    name: str,
) -> ir.Instruction:
    """Emit a small if/else merge and return the merged value.

    This is intentionally thin: it removes repeated branch/phi boilerplate, but it
    does not try to hide the CFG behind a larger framework.
    """

    function = builder.function
    then_block = function.append_basic_block(f"{name}.then")
    else_block = function.append_basic_block(f"{name}.else")
    merge_block = function.append_basic_block(f"{name}.merge")

    builder.cbranch(condition, then_block, else_block)

    builder.position_at_end(then_block)
    builder.branch(merge_block)
    then_end = builder.block

    builder.position_at_end(else_block)
    builder.branch(merge_block)
    else_end = builder.block

    builder.position_at_end(merge_block)
    phi = builder.phi(then_value.type, name=name)
    phi.add_incoming(then_value, then_end)
    phi.add_incoming(else_value, else_end)
    return phi


def build_manual_clamp_function(module: ir.Module) -> ir.Function:
    """Build a direct branch/phi version of clamp(x, 0, 10)."""

    fn_ty = ir.FunctionType(I64, [I64])
    fn = ir.Function(module, fn_ty, name="manual_clamp_0_10")
    x = fn.args[0]
    x.name = "x"

    entry = fn.append_basic_block("entry")
    builder = ir.IRBuilder(entry)

    is_negative = builder.icmp_signed("<", x, ir.Constant(I64, 0), name="is_negative")
    negative_block = fn.append_basic_block("negative")
    check_high_block = fn.append_basic_block("check_high")
    merge_block = fn.append_basic_block("merge")
    builder.cbranch(is_negative, negative_block, check_high_block)

    builder.position_at_end(negative_block)
    builder.branch(merge_block)
    negative_end = builder.block

    builder.position_at_end(check_high_block)
    is_above_ten = builder.icmp_signed(">", x, ir.Constant(I64, 10), name="is_above_ten")
    high_block = fn.append_basic_block("high")
    in_range_block = fn.append_basic_block("in_range")
    builder.cbranch(is_above_ten, high_block, in_range_block)

    builder.position_at_end(high_block)
    builder.branch(merge_block)
    high_end = builder.block

    builder.position_at_end(in_range_block)
    builder.branch(merge_block)
    in_range_end = builder.block

    builder.position_at_end(merge_block)
    clamped = builder.phi(I64, name="clamped")
    clamped.add_incoming(ir.Constant(I64, 0), negative_end)
    clamped.add_incoming(ir.Constant(I64, 10), high_end)
    clamped.add_incoming(x, in_range_end)
    builder.ret(clamped)
    return fn


def build_helper_clamp_function(module: ir.Module) -> ir.Function:
    """Build the same clamp using a thin helper twice."""

    fn_ty = ir.FunctionType(I64, [I64])
    fn = ir.Function(module, fn_ty, name="helper_clamp_0_10")
    x = fn.args[0]
    x.name = "x"

    entry = fn.append_basic_block("entry")
    builder = ir.IRBuilder(entry)

    lower_bounded = emit_if_else_value(
        builder,
        builder.icmp_signed("<", x, ir.Constant(I64, 0), name="is_negative"),
        ir.Constant(I64, 0),
        x,
        name="clamp_low",
    )
    clamped = emit_if_else_value(
        builder,
        builder.icmp_signed(">", lower_bounded, ir.Constant(I64, 10), name="is_above_ten"),
        ir.Constant(I64, 10),
        lower_bounded,
        name="clamp_high",
    )
    builder.ret(clamped)
    return fn


def build_module() -> ir.Module:
    module = ir.Module(name="metaprogramming_ir_builders")
    module.triple = binding.get_default_triple()
    build_manual_clamp_function(module)
    build_helper_clamp_function(module)
    return module


def compile_module(module: ir.Module) -> tuple[str, binding.ExecutionEngine, dict[str, int]]:
    """Verify the module and return the IR plus a live engine and function addresses."""

    binding.initialize_native_target()
    binding.initialize_native_asmprinter()

    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()
    addresses = {
        "manual_clamp_0_10": engine.get_function_address("manual_clamp_0_10"),
        "helper_clamp_0_10": engine.get_function_address("helper_clamp_0_10"),
    }
    return llvm_ir, engine, addresses


def as_cfunc(address: int) -> ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64):
    return ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)(address)


def main() -> None:
    module = build_module()
    # Keep the engine alive for as long as any derived function pointer is used.
    llvm_ir, _engine, addresses = compile_module(module)

    manual = as_cfunc(addresses["manual_clamp_0_10"])
    helper = as_cfunc(addresses["helper_clamp_0_10"])
    samples = [-7, 0, 5, 12]

    print("== Question ==")
    print("What is the smallest llvmlite helper that is useful without hiding the CFG?")
    print()
    print("== Generated IR ==")
    print(llvm_ir.rstrip())
    print()
    print("== Runtime Results ==")
    print("manual_clamp_0_10 vs helper_clamp_0_10")
    for value in samples:
        manual_result = manual(value)
        helper_result = helper(value)
        print(f"x={value:>3}: manual={manual_result:>2} helper={helper_result:>2}")

    print()
    print("== Pattern ==")
    print("Use one thin helper for branch/phi repetition, but stop before the CFG becomes opaque.")
    print()
    print("== Takeaway ==")
    print("Helper-driven codegen is good when it removes repeated merge boilerplate, not when it turns the IR shape into a guessing game.")


if __name__ == "__main__":
    main()
