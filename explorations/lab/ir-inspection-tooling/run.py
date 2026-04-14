"""Show a minimal, explicit way to inspect and diff llvmlite IR."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff

from llvmlite import binding, ir


I32 = ir.IntType(32)


@dataclass(frozen=True)
class IRSnapshot:
    label: str
    note: str
    module_name: str
    bias_seed: int
    raw_ir: str
    line_count: int
    key_lines: tuple[str, ...]


@dataclass(frozen=True)
class InspectionRun:
    label: str
    baseline: IRSnapshot
    variant: IRSnapshot
    diff: str


def build_module(bias_seed: int) -> ir.Module:
    """Build one tiny module whose only textual difference is the bias seed."""
    module = ir.Module(name="ir_inspection_tooling")
    module.triple = binding.get_default_triple()

    seed = ir.GlobalVariable(module, I32, name="bias_seed")
    seed.linkage = "internal"
    seed.global_constant = True
    seed.initializer = ir.Constant(I32, bias_seed)

    score = ir.Function(module, ir.FunctionType(I32, [I32, I32]), name="score")
    entry = score.append_basic_block(name="entry")
    builder = ir.IRBuilder(entry)
    summed = builder.add(score.args[0], score.args[1], name="sum")
    bias = builder.load(seed, name="bias")
    builder.ret(builder.add(summed, bias, name="adjusted"))

    return module


def capture_snapshot(label: str, note: str, bias_seed: int) -> IRSnapshot:
    """Capture the raw emitted IR immediately, before later edits can erase context."""
    module = build_module(bias_seed)
    raw_ir = str(module)
    parsed = binding.parse_assembly(raw_ir)
    parsed.verify()
    key_lines = tuple(
        line.strip()
        for line in raw_ir.splitlines()
        if line.startswith("define ") or line.startswith('@"')
    )
    return IRSnapshot(
        label=label,
        note=note,
        module_name=module.name,
        bias_seed=bias_seed,
        raw_ir=raw_ir,
        line_count=len(raw_ir.splitlines()),
        key_lines=key_lines,
    )


def run_raw_inspection(baseline_bias: int, variant_bias: int) -> InspectionRun:
    baseline = capture_snapshot(
        "baseline",
        "snapshot the module before any later edits or normalization",
        bias_seed=baseline_bias,
    )
    variant = capture_snapshot(
        "variant",
        "same shape, but with a different global initializer",
        bias_seed=variant_bias,
    )
    return InspectionRun(
        label="raw",
        baseline=baseline,
        variant=variant,
        diff=diff_snapshots(baseline, variant),
    )


def number_ir(raw_ir: str) -> str:
    lines = raw_ir.splitlines()
    width = len(str(len(lines)))
    return "\n".join(f"{index:>{width}} | {line}" for index, line in enumerate(lines, start=1))


def format_snapshot(snapshot: IRSnapshot) -> str:
    lines = [
        f"label: {snapshot.label}",
        f"module: {snapshot.module_name}",
        f"note: {snapshot.note}",
        f"bias_seed: {snapshot.bias_seed}",
        f"line_count: {snapshot.line_count}",
    ]
    if snapshot.key_lines:
        lines.append("key_lines:")
        lines.extend(f"  - {line}" for line in snapshot.key_lines)
    return "\n".join(lines)


def print_snapshot(snapshot: IRSnapshot) -> None:
    print(f"== Snapshot: {snapshot.label} ==")
    print(format_snapshot(snapshot))
    print()
    print("-- raw LLVM --")
    print(snapshot.raw_ir.rstrip())
    print()
    print("-- line-numbered LLVM --")
    print(number_ir(snapshot.raw_ir))


def diff_snapshots(base: IRSnapshot, variant: IRSnapshot) -> str:
    diff_lines = unified_diff(
        base.raw_ir.splitlines(),
        variant.raw_ir.splitlines(),
        fromfile=f"{base.label}.ll",
        tofile=f"{variant.label}.ll",
        lineterm="",
    )
    return "\n".join(diff_lines)


class IRInspectionSession:
    """Bundle capture and rendering while leaving the raw LLVM text visible."""

    def __init__(self, baseline_bias: int, variant_bias: int):
        self.baseline_bias = baseline_bias
        self.variant_bias = variant_bias

    def capture(self, label: str, note: str, bias_seed: int) -> IRSnapshot:
        return capture_snapshot(label, note, bias_seed)

    def run(self) -> InspectionRun:
        baseline = self.capture(
            "baseline",
            "snapshot the module before any later edits or normalization",
            self.baseline_bias,
        )
        variant = self.capture(
            "variant",
            "same shape, but with a different global initializer",
            self.variant_bias,
        )
        return InspectionRun(
            label="pythonic",
            baseline=baseline,
            variant=variant,
            diff=diff_snapshots(baseline, variant),
        )

    def render(self, run: InspectionRun) -> None:
        print("Pattern 1: Capture Early")
        print(
            "Take the raw string from str(module) while the variant still has the exact shape "
            "you want to study, then keep that snapshot around."
        )
        print()
        print_snapshot(run.baseline)
        print()
        print_snapshot(run.variant)
        print()
        print("Pattern 2: Diff the Raw Text")
        print("Use a thin diff helper on the captured strings instead of diffing summaries.")
        print()
        print(run.diff or "(no textual diff)")
        print()
        print("Non-Obvious Failure Mode:")
        print(
            "If you wait until after later edits, you lose the earlier IR shape. If you "
            "normalize or summarize too aggressively, a real difference like a global "
            "initializer change can disappear."
        )
        print()


def main() -> None:
    raw_run = run_raw_inspection(0, 7)
    pythonic_session = IRInspectionSession(0, 7)
    pythonic_run = pythonic_session.run()

    print("== Question ==")
    print("How do you inspect and compare llvmlite IR without hiding the emitted LLVM?")
    print()
    print("== Raw Variant ==")
    print(
        "The raw version keeps the snapshot, line-numbering, and diff plumbing explicit so the LLVM text stays front and center."
    )
    print()
    print_snapshot(raw_run.baseline)
    print()
    print_snapshot(raw_run.variant)
    print()
    print("Raw diff:")
    print(raw_run.diff or "(no textual diff)")
    print()
    print("== Pythonic Variant ==")
    print(
        "The helper-object version groups repeated capture and comparison steps without turning the IR into a different representation."
    )
    print()
    pythonic_session.render(pythonic_run)
    print("== Comparison ==")
    print(f"same baseline line count: {raw_run.baseline.line_count == pythonic_run.baseline.line_count}")
    print(f"same variant line count: {raw_run.variant.line_count == pythonic_run.variant.line_count}")
    print(f"same diff text: {raw_run.diff == pythonic_run.diff}")
    print()
    print("== Takeaway ==")
    print(
        "Keep one helper for raw snapshots and one for raw diffs. Add line numbers as a "
        "reader aid, but do not replace the LLVM text with a derived summary."
    )


if __name__ == "__main__":
    main()
