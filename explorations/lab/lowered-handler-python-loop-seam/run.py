"""Demonstrate the Python-loop to progressively lowered-handler seam."""

from __future__ import annotations

from fythvm.codegen.llvm import configure_llvm

from seam_lowering import build_lowered_runtime
from seam_model import SCENARIOS
from seam_report import print_scenario
from seam_runtime import assert_result_matches, execute_scenario


def main() -> None:
    configure_llvm()
    _module, compiled, lowered_fetch, lowered_dispatch, lowered_addresses = build_lowered_runtime()

    print("== Question ==")
    print("What is the smallest useful seam between a Python dispatch loop and a gradually lowered handler set?")
    print()
    print("== Generated IR ==")
    print(compiled.llvm_ir.rstrip())
    print()
    print("== Takeaway ==")
    print("Inject lowered op resources from HandlerRequirements; let the wrapper own ret, let Python own dispatch, and grow the seam one honest surface at a time.")
    print()

    for scenario in SCENARIOS:
        result = execute_scenario(scenario, lowered_fetch, lowered_dispatch)
        assert_result_matches(scenario, result)
        print_scenario(scenario, result, lowered_addresses=lowered_addresses)


if __name__ == "__main__":
    main()
