from __future__ import annotations

from fythvm import dictionary

from seam_model import Scenario, ScenarioResult
from seam_runtime import decompile_thread


def print_scenario(
    scenario: Scenario,
    result: ScenarioResult,
    *,
    lowered_addresses: dict[int, int],
) -> None:
    print(f"== {scenario.name.upper()} ==")
    print("thread:")
    for line in decompile_thread(scenario.thread, custom_words=scenario.custom_words):
        print(f"  {line}")
    for word in scenario.custom_words:
        print(f"word {word.name}:")
        for line in decompile_thread(word.thread, custom_words=scenario.custom_words):
            print(f"  {line}")
    halt_id = int(dictionary.PrimitiveInstruction.HALT)
    if halt_id in lowered_addresses:
        print(f"lowered HALT address: 0x{lowered_addresses[halt_id]:x}")
    print(
        "expected:"
        f" stack={list(scenario.expected_stack)}"
        f" final_ip={scenario.expected_final_ip}"
        f" state_flags=0x{scenario.expected_state_flags:x}"
        f" backends={list(scenario.expected_trace_backends)}"
    )
    for row in result.trace:
        print(f"step {row.step}: ip={row.ip} word={row.word} backend={row.backend}")
        print(f"  stack before: {list(row.stack_before)}")
        print(f"  state flags before: 0x{row.state_flags_before:x}")
        print(f"  note: {row.note}")
        print(f"  stack after: {list(row.stack_after)}")
        print(f"  state flags after: 0x{row.state_flags_after:x}")
    print(
        f"result: stack={list(result.final_stack)} final_ip={result.final_ip} "
        f"state_flags=0x{result.state_flags:x}"
    )
    print("expectation check: ok")
    print()
