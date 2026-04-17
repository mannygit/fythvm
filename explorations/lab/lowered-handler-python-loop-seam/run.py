"""Demonstrate the Python-loop to progressively lowered-handler seam."""

from __future__ import annotations

from pathlib import Path

from fythvm.codegen.llvm import configure_llvm

from seam_lowering import build_lowered_runtime
from seam_model import SCENARIOS, ScenarioResult
from seam_report import print_scenario
from seam_runtime import assert_result_matches, execute_scenario

RAW_IR_ARTIFACT_PATH = Path(__file__).resolve().parents[3] / "lowered-handler-python-loop-seam.ll"
OPT_O3_IR_ARTIFACT_PATH = Path(__file__).resolve().parents[3] / "lowered-handler-python-loop-seam.O3.ll"


def write_ir_artifact(path: Path, llvm_ir: str) -> Path:
    path.write_text(f"{llvm_ir.rstrip()}\n", encoding="utf-8")
    return path


def line_count(text: str) -> int:
    return len(text.rstrip().splitlines())


def assert_results_match(raw: ScenarioResult, optimized: ScenarioResult) -> None:
    assert raw.final_stack == optimized.final_stack
    assert raw.final_ip == optimized.final_ip
    assert raw.state_flags == optimized.state_flags
    assert raw.trace == optimized.trace


def main() -> None:
    configure_llvm()
    _raw_module, raw_compiled, raw_lowered_step, _raw_lowered_step_address = build_lowered_runtime()
    _opt_module, opt_compiled, opt_lowered_step, opt_lowered_step_address = build_lowered_runtime(
        speed_level=3
    )
    raw_ir_artifact_path = write_ir_artifact(RAW_IR_ARTIFACT_PATH, raw_compiled.llvm_ir)
    opt_ir_artifact_path = write_ir_artifact(OPT_O3_IR_ARTIFACT_PATH, opt_compiled.llvm_ir)

    print("== Question ==")
    print("What is the smallest useful seam between a Python dispatch loop and a gradually lowered handler set?")
    print()
    print("== IR Artifacts ==")
    print(f"raw: {raw_ir_artifact_path}")
    print(f"O3:  {opt_ir_artifact_path}")
    print()
    print("== Optimization Comparison ==")
    print(
        f"raw IR lines={line_count(raw_compiled.llvm_ir)} "
        f"O3 IR lines={line_count(opt_compiled.llvm_ir)}"
    )
    print(
        f"raw asm lines={line_count(raw_compiled.assembly)} "
        f"O3 asm lines={line_count(opt_compiled.assembly)}"
    )
    print()
    print("== O3 IR ==")
    print(opt_compiled.llvm_ir.rstrip())
    print()
    print("== Takeaway ==")
    print(
        "Inject lowered op resources from HandlerRequirements, rejoin a shared lowered "
        "NEXT-like trampoline, and keep Python focused on the outer loop and trace."
    )
    print()

    for scenario in SCENARIOS:
        raw_result = execute_scenario(scenario, raw_lowered_step)
        opt_result = execute_scenario(scenario, opt_lowered_step)
        assert_result_matches(scenario, raw_result)
        assert_result_matches(scenario, opt_result)
        assert_results_match(raw_result, opt_result)
        print_scenario(scenario, opt_result, lowered_step_address=opt_lowered_step_address)


if __name__ == "__main__":
    main()
