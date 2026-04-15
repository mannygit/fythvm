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


@dataclass
class CompiledVariant:
    llvm_ir: str
    engine: binding.ExecutionEngine
    clamp: CALLABLE_I64_TO_I64
    classify: CALLABLE_I64_TO_I64


def compile_variant(module: ir.Module) -> CompiledVariant:
    """Verify a module and return the IR, live engine, and callable functions."""

    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()
    return CompiledVariant(
        llvm_ir=llvm_ir,
        engine=engine,
        clamp=CALLABLE_I64_TO_I64(engine.get_function_address("clamp_0_10")),
        classify=CALLABLE_I64_TO_I64(engine.get_function_address("classify_score")),
    )


def build_raw_variant_module() -> ir.Module:
    """Build the branch/phi clamp plus a straight-line select-lowered classifier."""

    module = ir.Module(name="metaprogramming_ir_builders_raw")
    module.triple = binding.get_default_triple()

    fn_ty = ir.FunctionType(I64, [I64])

    clamp_fn = ir.Function(module, fn_ty, name="clamp_0_10")
    x = clamp_fn.args[0]
    x.name = "x"

    entry = clamp_fn.append_basic_block("entry")
    builder = ir.IRBuilder(entry)

    is_negative = builder.icmp_signed("<", x, ir.Constant(I64, 0), name="is_negative")
    negative_block = clamp_fn.append_basic_block("negative")
    check_high_block = clamp_fn.append_basic_block("check_high")
    merge_block = clamp_fn.append_basic_block("merge")
    builder.cbranch(is_negative, negative_block, check_high_block)

    builder.position_at_end(negative_block)
    builder.branch(merge_block)
    negative_end = builder.block

    builder.position_at_end(check_high_block)
    is_above_ten = builder.icmp_signed(">", x, ir.Constant(I64, 10), name="is_above_ten")
    high_block = clamp_fn.append_basic_block("high")
    in_range_block = clamp_fn.append_basic_block("in_range")
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

    classify_fn = ir.Function(module, fn_ty, name="classify_score")
    score = classify_fn.args[0]
    score.name = "score"

    classify_entry = classify_fn.append_basic_block("entry")
    builder = ir.IRBuilder(classify_entry)

    is_below_zero = builder.icmp_signed("<", score, ir.Constant(I64, 0), name="is_below_zero")
    below_zero = builder.select(
        is_below_zero,
        ir.Constant(I64, -1),
        ir.Constant(I64, 0),
        name="below_zero",
    )
    is_below_ten = builder.icmp_signed("<", score, ir.Constant(I64, 10), name="is_below_ten")
    classified = builder.select(
        is_below_ten,
        below_zero,
        ir.Constant(I64, 1),
        name="classified",
    )
    builder.ret(classified)
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


@dataclass
class ComparisonLowering:
    """A tiny helper that keeps repeated compare lowering readable."""

    builder: ir.IRBuilder
    subject: ir.Value

    def choose_below(
        self,
        threshold: int,
        true_value: ir.Value,
        false_value: ir.Value,
        *,
        name: str,
    ) -> ir.Value:
        condition = self.builder.icmp_signed(
            "<",
            self.subject,
            ir.Constant(I64, threshold),
            name=f"{name}.is_below",
        )
        return self.builder.select(condition, true_value, false_value, name=name)


def build_pythonic_variant_module() -> ir.Module:
    """Build the same clamp and classifier with two small helper objects."""

    module = ir.Module(name="metaprogramming_ir_builders_pythonic")
    module.triple = binding.get_default_triple()

    fn_ty = ir.FunctionType(I64, [I64])

    clamp_fn = ir.Function(module, fn_ty, name="clamp_0_10")
    x = clamp_fn.args[0]
    x.name = "x"

    entry = clamp_fn.append_basic_block("entry")
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

    classify_fn = ir.Function(module, fn_ty, name="classify_score")
    score = classify_fn.args[0]
    score.name = "score"

    classify_entry = classify_fn.append_basic_block("entry")
    builder = ir.IRBuilder(classify_entry)
    lowering = ComparisonLowering(builder, score)

    below_zero = lowering.choose_below(
        0,
        ir.Constant(I64, -1),
        ir.Constant(I64, 0),
        name="below_zero",
    )
    classified = lowering.choose_below(
        10,
        below_zero,
        ir.Constant(I64, 1),
        name="below_ten",
    )
    builder.ret(classified)
    return module


def main() -> None:
    configure_llvm()

    raw_variant = compile_variant(build_raw_variant_module())
    pythonic_variant = compile_variant(build_pythonic_variant_module())

    clamp_samples = [-7, 0, 5, 12]
    classification_samples = [-4, 0, 7, 12]

    print("== Question ==")
    print("What is the smallest llvmlite helper that is useful without hiding the CFG or making select look like branch prediction?")
    print()

    print("== Raw Baseline ==")
    print("source of truth: explicit block wiring, phi nodes, and select-based comparison lowering")
    print(raw_variant.llvm_ir.rstrip())
    print()
    print("clamp results")
    for value in clamp_samples:
        print(f"x={value:>3}: clamp_0_10={raw_variant.clamp(value):>2}")
    print("comparison results")
    for value in classification_samples:
        print(f"x={value:>3}: classify_score={raw_variant.classify(value):>2}")
    print()

    print("== Pythonic Variant ==")
    print("readability layer: a tiny branch helper plus a tiny comparison-lowering helper")
    print(pythonic_variant.llvm_ir.rstrip())
    print()
    print("clamp results")
    for value in clamp_samples:
        print(f"x={value:>3}: clamp_0_10={pythonic_variant.clamp(value):>2}")
    print("comparison results")
    for value in classification_samples:
        print(f"x={value:>3}: classify_score={pythonic_variant.classify(value):>2}")
    print()

    print("== Comparison ==")
    print("The clamp example shows helper factoring for branch/phi wiring.")
    print("The comparison example shows helper factoring for repeated icmp + select lowering.")
    print("Neither example is about branch prediction; the select form is only used when both candidate values are already safe to compute.")
    print()

    print("== Pattern ==")
    print("Use one thin helper for repeated branch/phi wiring or repeated compare lowering, but stop before the CFG or the straight-line lowering shape becomes opaque.")
    print()

    print("== Takeaway ==")
    print("Keep the raw IR-like builder as the correctness reference, then let a small Pythonic layer earn its way in by making the same shape easier to read.")


if __name__ == "__main__":
    main()
