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


def main() -> None:
    baseline = capture_snapshot(
        "baseline",
        "snapshot the module before any later edits or normalization",
        bias_seed=0,
    )
    variant = capture_snapshot(
        "variant",
        "same shape, but with a different global initializer",
        bias_seed=7,
    )

    print("== Question ==")
    print("How do you inspect and compare llvmlite IR without hiding the emitted LLVM?")
    print()
    print("== Pattern 1: Capture Early ==")
    print(
        "Take the raw string from str(module) while the variant still has the exact shape "
        "you want to study, then keep that snapshot around."
    )
    print()
    print_snapshot(baseline)
    print()
    print_snapshot(variant)
    print()
    print("== Pattern 2: Diff the Raw Text ==")
    print("Use a thin diff helper on the captured strings instead of diffing summaries.")
    print()
    print(diff_snapshots(baseline, variant) or "(no textual diff)")
    print()
    print("== Non-Obvious Failure Mode ==")
    print(
        "If you wait until after later edits, you lose the earlier IR shape. If you "
        "normalize or summarize too aggressively, a real difference like a global "
        "initializer change can disappear."
    )
    print()
    print("== Takeaway ==")
    print(
        "Keep one helper for raw snapshots and one for raw diffs. Add line numbers as a "
        "reader aid, but do not replace the LLVM text with a derived summary."
    )


if __name__ == "__main__":
    main()
