"""Demonstrate the Python-loop to progressively lowered-handler seam."""

from __future__ import annotations

from pathlib import Path

from fythvm.codegen.llvm import configure_llvm

from seam_lowering import build_lowered_runtime
from seam_model import SCENARIOS, ScenarioResult
from seam_report import print_scenario
from seam_runtime import (
    assert_result_matches,
    execute_scenario,
    execute_scenario_to_completion,
)

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


def assert_trace_and_run_match(traced: ScenarioResult, lowered_run: ScenarioResult) -> None:
    assert traced.final_stack == lowered_run.final_stack
    assert traced.final_ip == lowered_run.final_ip
    assert traced.state_flags == lowered_run.state_flags


def main() -> None:
    configure_llvm()
    raw_runtime = build_lowered_runtime()
    opt_runtime = build_lowered_runtime(speed_level=3)
    raw_ir_artifact_path = write_ir_artifact(RAW_IR_ARTIFACT_PATH, raw_runtime.compiled.llvm_ir)
    opt_ir_artifact_path = write_ir_artifact(OPT_O3_IR_ARTIFACT_PATH, opt_runtime.compiled.llvm_ir)

    print("== Question ==")
    print("What is the smallest useful seam between a Python dispatch loop and a gradually lowered handler set?")
    print()
    print("== IR Artifacts ==")
    print(f"raw: {raw_ir_artifact_path}")
    print(f"O3:  {opt_ir_artifact_path}")
    print()
    print("== Optimization Comparison ==")
    print(
        f"raw IR lines={line_count(raw_runtime.compiled.llvm_ir)} "
        f"O3 IR lines={line_count(opt_runtime.compiled.llvm_ir)}"
    )
    print(
        f"raw asm lines={line_count(raw_runtime.compiled.assembly)} "
        f"O3 asm lines={line_count(opt_runtime.compiled.assembly)}"
    )
    print(
        f"O3 entrypoints: step=0x{opt_runtime.step.address:x} "
        f"step_xt=0x{opt_runtime.step_xt.address:x} "
        f"run=0x{opt_runtime.run.address:x}"
    )
    print()
    print("== O3 IR ==")
    print(opt_runtime.compiled.llvm_ir.rstrip())
    print()
    print("== Takeaway ==")
    print(
        "Inject lowered op resources from HandlerRequirements, rejoin a shared lowered "
        "NEXT-like trampoline, and keep Python focused on the outer loop and trace."
    )
    print()

    for scenario in SCENARIOS:
        raw_step_result = execute_scenario(scenario, raw_runtime.step.cfunc, raw_runtime.step_xt.cfunc)
        opt_step_result = execute_scenario(scenario, opt_runtime.step.cfunc, opt_runtime.step_xt.cfunc)
        raw_run_result = execute_scenario_to_completion(
            scenario,
            raw_runtime.run.cfunc,
            raw_runtime.step_xt.cfunc,
        )
        opt_run_result = execute_scenario_to_completion(
            scenario,
            opt_runtime.run.cfunc,
            opt_runtime.step_xt.cfunc,
        )
        assert_result_matches(scenario, raw_step_result)
        assert_result_matches(scenario, opt_step_result)
        assert_result_matches(scenario, raw_run_result, require_trace=False)
        assert_result_matches(scenario, opt_run_result, require_trace=False)
        assert_results_match(raw_step_result, opt_step_result)
        assert_trace_and_run_match(raw_step_result, raw_run_result)
        assert_trace_and_run_match(opt_step_result, opt_run_result)
        assert_trace_and_run_match(raw_step_result, opt_run_result)
        print_scenario(
            scenario,
            opt_step_result,
            lowered_step=opt_runtime.step,
            lowered_step_xt=opt_runtime.step_xt,
            lowered_run=opt_runtime.run,
        )


if __name__ == "__main__":
    main()
