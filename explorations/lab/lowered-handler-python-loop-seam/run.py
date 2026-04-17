"""Demonstrate the Python-loop to progressively lowered-handler seam."""

from __future__ import annotations

from pathlib import Path

from fythvm.codegen.llvm import configure_llvm

from seam_lowering import build_lowered_runtime
from seam_model import SCENARIOS
from seam_report import print_scenario
from seam_runtime import assert_result_matches, execute_scenario

IR_ARTIFACT_PATH = Path(__file__).resolve().parents[3] / "lowered-handler-python-loop-seam.ll"


def write_ir_artifact(llvm_ir: str) -> Path:
    IR_ARTIFACT_PATH.write_text(f"{llvm_ir.rstrip()}\n", encoding="utf-8")
    return IR_ARTIFACT_PATH


def main() -> None:
    configure_llvm()
    _module, compiled, lowered_step, lowered_step_address = build_lowered_runtime()
    ir_artifact_path = write_ir_artifact(compiled.llvm_ir)

    print("== Question ==")
    print("What is the smallest useful seam between a Python dispatch loop and a gradually lowered handler set?")
    print()
    print("== IR Artifact ==")
    print(ir_artifact_path)
    print()
    print("== Generated IR ==")
    print(compiled.llvm_ir.rstrip())
    print()
    print("== Takeaway ==")
    print(
        "Inject lowered op resources from HandlerRequirements, rejoin a shared lowered "
        "NEXT-like trampoline, and keep Python focused on the outer loop and trace."
    )
    print()

    for scenario in SCENARIOS:
        result = execute_scenario(scenario, lowered_step)
        assert_result_matches(scenario, result)
        print_scenario(scenario, result, lowered_step_address=lowered_step_address)


if __name__ == "__main__":
    main()
