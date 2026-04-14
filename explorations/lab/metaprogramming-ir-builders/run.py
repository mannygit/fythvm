"""Explore raw versus Pythonic llvmlite IR builder styles."""

from __future__ import annotations

import ctypes
from contextlib import contextmanager
from dataclasses import dataclass

from llvmlite import binding, ir


I64 = ir.IntType(64)
CALLABLE_I64_TO_I64 = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def compile_module(module: ir.Module, function_name: str) -> tuple[str, binding.ExecutionEngine, CALLABLE_I64_TO_I64]:
    """Verify a module and return the IR, live engine, and callable function pointer."""

    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()
    address = engine.get_function_address(function_name)
    return llvm_ir, engine, CALLABLE_I64_TO_I64(address)


def build_raw_clamp_module() -> ir.Module:
    """Build a clamp function with explicit blocks and phi nodes."""

    module = ir.Module(name="metaprogramming_ir_builders_raw")
    module.triple = binding.get_default_triple()

    fn_ty = ir.FunctionType(I64, [I64])
    fn = ir.Function(module, fn_ty, name="clamp_0_10")
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
    return module


@dataclass
class BranchMerge:
    """A small helper that keeps branch/merge wiring visible but less repetitive."""

    builder: ir.IRBuilder
    condition: ir.Value
    name: str

    def __post_init__(self) -> None:
        function = self.builder.function
        self.then_block = function.append_basic_block(f"{self.name}.then")
        self.otherwise_block = function.append_basic_block(f"{self.name}.otherwise")
        self.merge_block = function.append_basic_block(f"{self.name}.merge")
        self.builder.cbranch(self.condition, self.then_block, self.otherwise_block)

    @contextmanager
    def then(self):
        self.builder.position_at_end(self.then_block)
        try:
            yield
        finally:
            self.builder.branch(self.merge_block)

    @contextmanager
    def otherwise(self):
        self.builder.position_at_end(self.otherwise_block)
        try:
            yield
        finally:
            self.builder.branch(self.merge_block)

    def merge(self, true_value: ir.Value, false_value: ir.Value) -> ir.Instruction:
        self.builder.position_at_end(self.merge_block)
        phi = self.builder.phi(true_value.type, name=self.name)
        phi.add_incoming(true_value, self.then_block)
        phi.add_incoming(false_value, self.otherwise_block)
        return phi


def build_pythonic_clamp_module() -> ir.Module:
    """Build the same clamp with a small context-managed helper object."""

    module = ir.Module(name="metaprogramming_ir_builders_pythonic")
    module.triple = binding.get_default_triple()

    fn_ty = ir.FunctionType(I64, [I64])
    fn = ir.Function(module, fn_ty, name="clamp_0_10")
    x = fn.args[0]
    x.name = "x"

    entry = fn.append_basic_block("entry")
    builder = ir.IRBuilder(entry)

    low_choice = BranchMerge(
        builder,
        builder.icmp_signed("<", x, ir.Constant(I64, 0), name="is_negative"),
        name="clamp_low",
    )
    with low_choice.then():
        low_then_value = ir.Constant(I64, 0)
    with low_choice.otherwise():
        low_else_value = x
    lower_bounded = low_choice.merge(low_then_value, low_else_value)

    high_choice = BranchMerge(
        builder,
        builder.icmp_signed(">", lower_bounded, ir.Constant(I64, 10), name="is_above_ten"),
        name="clamp_high",
    )
    with high_choice.then():
        high_then_value = ir.Constant(I64, 10)
    with high_choice.otherwise():
        high_else_value = lower_bounded
    clamped = high_choice.merge(high_then_value, high_else_value)

    builder.ret(clamped)
    return module


def call_clamp(module: ir.Module) -> tuple[str, binding.ExecutionEngine, CALLABLE_I64_TO_I64]:
    return compile_module(module, "clamp_0_10")


def main() -> None:
    configure_llvm()

    raw_module = build_raw_clamp_module()
    pythonic_module = build_pythonic_clamp_module()

    raw_ir, _raw_engine, raw_clamp = call_clamp(raw_module)
    pythonic_ir, _pythonic_engine, pythonic_clamp = call_clamp(pythonic_module)

    samples = [-7, 0, 5, 12]

    print("== Question ==")
    print("What is the smallest llvmlite helper that is useful without hiding the CFG?")
    print()

    print("== Raw Baseline ==")
    print("source of truth: explicit block wiring and phi nodes")
    print(raw_ir.rstrip())
    print()
    print("results")
    for value in samples:
        print(f"x={value:>3}: clamp_0_10={raw_clamp(value):>2}")
    print()

    print("== Pythonic Variant ==")
    print("readability layer: a tiny context-managed branch helper")
    print(pythonic_ir.rstrip())
    print()
    print("results")
    for value in samples:
        print(f"x={value:>3}: clamp_0_10={pythonic_clamp(value):>2}")
    print()

    print("== Comparison ==")
    print("Both versions clamp the same inputs, but only the raw one keeps every CFG step fully spelled out.")
    print("The Pythonic variant stays readable because it wraps branch/merge plumbing, not because it hides the control flow.")
    print()

    print("== Pattern ==")
    print("Use one thin helper for branch/phi repetition, but stop before the CFG becomes opaque.")
    print()

    print("== Takeaway ==")
    print("Keep the raw IR-like builder as the correctness reference, then let a small Pythonic layer earn its way in by making the same shape easier to read.")


if __name__ == "__main__":
    main()
