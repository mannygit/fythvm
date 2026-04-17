"""Demonstrate the first Python-loop to lowered-handler seam."""

from __future__ import annotations

from fythvm.codegen.llvm import configure_llvm

from seam_lowering import build_lowered_runtime
from seam_model import SCENARIOS
from seam_report import print_scenario
from seam_runtime import assert_result_matches, execute_scenario


def main() -> None:
    configure_llvm()
    _module, compiled, lowered_functions, lowered_addresses = build_lowered_runtime()

    print("== Question ==")
    print("What is the smallest useful seam between a Python dispatch loop and one lowered handler?")
    print()
    print("== Generated IR ==")
    print(compiled.llvm_ir.rstrip())
    print()
    print("== Takeaway ==")
    print("Inject lowered op resources from HandlerRequirements; let the wrapper own ret and let Python own dispatch.")
    print()

    for scenario in SCENARIOS:
        result = execute_scenario(scenario, lowered_functions)
        assert_result_matches(scenario, result)
        print_scenario(scenario, result, lowered_addresses=lowered_addresses)


if __name__ == "__main__":
    main()
