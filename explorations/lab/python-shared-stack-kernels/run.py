"""Demonstrate shared pure-Python primitive kernels grouped by requested operations."""

from __future__ import annotations

from collections import defaultdict
from types import ModuleType

import ops_arithmetic
import ops_compare_bitwise
import ops_memory
import ops_return_stack
import ops_stack
from machine import MachineSnapshot, MachineState
from registry import OperationSpec, Scenario


GROUP_MODULES: tuple[ModuleType, ...] = (
    ops_stack,
    ops_arithmetic,
    ops_compare_bitwise,
    ops_memory,
    ops_return_stack,
)


def first_doc_line(spec: OperationSpec) -> str:
    """Return the first docstring line for one registered operation."""

    doc = spec.func.__doc__ or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


def describe_memory(state: MachineState) -> str:
    """Render non-zero memory bytes compactly for scenario output."""

    active = [(index, byte) for index, byte in enumerate(state.memory) if byte]
    if not active:
        return "memory=<all zero>"
    rendered = " ".join(f"{index}:{byte:02x}" for index, byte in active[:12])
    if len(active) > 12:
        rendered += " ..."
    return f"memory={rendered}"


def describe_state(state: MachineState) -> str:
    """Render stack pointers, logical stacks, and active memory."""

    return f"{state.describe()} {describe_memory(state)}"


def execute_words(
    ops: dict[str, OperationSpec], state: MachineState, words: tuple[str, ...]
) -> None:
    """Execute one word sequence against one operation mapping."""

    for word in words:
        ops[word].func(state)


def validate_specs(module: ModuleType) -> None:
    """Check collection shape, docstring anchors, and expected word coverage."""

    raw_specs = module.RAW_SPECS
    kernel_specs = module.KERNEL_SPECS
    expected_words = tuple(module.EXPECTED_WORDS)

    raw_words = tuple(spec.forth_name for spec in raw_specs)
    kernel_words = tuple(spec.forth_name for spec in kernel_specs)

    assert raw_words == expected_words, (
        f"{module.__name__} raw words mismatch: {raw_words!r}"
    )
    assert kernel_words == expected_words, (
        f"{module.__name__} kernel words mismatch: {kernel_words!r}"
    )
    assert len(set(raw_words)) == len(raw_words), (
        f"{module.__name__} raw words must be unique"
    )
    assert len(set(kernel_words)) == len(kernel_words), (
        f"{module.__name__} kernel words must be unique"
    )

    for spec in (*raw_specs, *kernel_specs):
        doc_line = first_doc_line(spec)
        assert doc_line.startswith(spec.forth_name), (
            f"{spec.func.__name__} docstring must start with Forth name"
        )


def run_scenario(
    raw_ops: dict[str, OperationSpec],
    kernel_ops: dict[str, OperationSpec],
    scenario: Scenario,
) -> tuple[MachineSnapshot, MachineSnapshot]:
    """Run one scenario through both variants and enforce parity."""

    baseline = scenario.build_state()
    raw_state = baseline.clone()
    kernel_state = baseline.clone()

    execute_words(raw_ops, raw_state, scenario.words)
    execute_words(kernel_ops, kernel_state, scenario.words)

    scenario.assert_state(raw_state)
    scenario.assert_state(kernel_state)

    raw_snapshot = raw_state.snapshot()
    kernel_snapshot = kernel_state.snapshot()
    assert raw_snapshot == kernel_snapshot, f"parity mismatch for {scenario.label}"

    print(f"  scenario: {scenario.label}")
    print(f"    words: {' '.join(scenario.words)}")
    if scenario.note:
        print(f"    note: {scenario.note}")
    print(f"    before: {describe_state(baseline)}")
    print(f"    after:  {describe_state(raw_state)}")
    print("    parity: ok")

    return raw_snapshot, kernel_snapshot


def print_group(module: ModuleType) -> None:
    """Print registry details and scenario traces for one requested-operation group."""

    validate_specs(module)

    print(f"== {module.GROUP_TITLE} ==")
    print("registered words:")
    for raw_spec, kernel_spec in zip(
        module.RAW_SPECS, module.KERNEL_SPECS, strict=True
    ):
        print(
            "  "
            f"{raw_spec.forth_name:>5} "
            f"stack={raw_spec.stack_effect:<26} "
            f"raw={raw_spec.func.__name__:<18} "
            f"kernel={kernel_spec.func.__name__:<20} "
            f"shared={kernel_spec.kernel_name}"
        )
    print()
    print("scenario traces:")
    for scenario in module.SCENARIOS:
        run_scenario(module.RAW_OPS, module.KERNEL_OPS, scenario)
    print()


def print_summary() -> None:
    """Print the shared kernels that cover multiple Forth words."""

    kernel_to_words: dict[str, list[str]] = defaultdict(list)
    for module in GROUP_MODULES:
        for spec in module.KERNEL_SPECS:
            if spec.kernel_name is None:
                continue
            kernel_to_words[spec.kernel_name].append(spec.forth_name)

    print("== Kernel Summary ==")
    for kernel_name in sorted(kernel_to_words):
        words = kernel_to_words[kernel_name]
        if len(words) < 2:
            continue
        print(f"  {kernel_name}: {', '.join(words)}")
    print()


def main() -> None:
    """Run the grouped pure-Python shared-kernel exploration."""

    print("== Question ==")
    print(
        "Can the requested JonesForth-style primitive-empty words be organized by the user-facing"
        " Requested Operations groups while still sharing a smaller set of pure-Python kernels?"
    )
    print()

    print("== Setup ==")
    print("The lab keeps two implementations for each requested word:")
    print("- raw: direct per-word Python behavior")
    print("- kernelized: thin wrappers over shared helpers in kernels.py")
    print(
        "Each callable is registered through @forth_op(...) and anchored by a docstring whose first line starts with the Forth word name."
    )
    print()

    for module in GROUP_MODULES:
        print_group(module)

    print_summary()

    print("== Takeaway ==")
    print(
        "The readable source split is by requested operation type, but the implementation reuse still collapses"
        " into a small number of shared kernels such as permute, unary_transform, binary_reduce,"
        " memory_store/fetch/update, and stack-pointer accessors."
    )


if __name__ == "__main__":
    main()
