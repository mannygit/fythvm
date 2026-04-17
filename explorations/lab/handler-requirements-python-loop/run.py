"""Demonstrate a tiny Python interpreter loop driven by handler metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fythvm import dictionary


HandlerFn = Callable[..., str]


@dataclass(frozen=True)
class Scenario:
    name: str
    text: str
    thread: tuple[int, ...]


@dataclass
class LoopState:
    """Minimal execution state for the proof-of-concept loop."""

    thread: tuple[int, ...]
    stack_limit: int = 8
    ip: int = 0
    current_xt: int | None = None
    data_stack: list[int] = field(default_factory=list)
    halted: bool = False


class ExecutionFault(RuntimeError):
    """Lab-local execution failure with a stable status code."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def error_exit(code: str, detail: str) -> None:
    raise ExecutionFault(code, detail)


@dataclass
class ThreadCursor:
    """Thread-local operand access without handing the handler raw dispatch control."""

    state: LoopState

    def read_inline_cell(self) -> int:
        operand_ip = self.state.ip + 1
        if operand_ip >= len(self.state.thread):
            error_exit(
                "inline-operand-underflow",
                f"word at ip={self.state.ip} needs one inline cell",
            )
        literal = int(self.state.thread[operand_ip])
        self.state.ip = operand_ip
        return literal


@dataclass
class ExecutionControl:
    """Minimal local control hooks that stop short of owning dispatch policy."""

    state: LoopState

    def halt(self) -> None:
        self.state.halted = True


def handle_lit(*, data_stack: list[int], thread_cursor: ThreadCursor, err: Callable[[str, str], None]) -> str:
    _ = err
    literal = thread_cursor.read_inline_cell()
    data_stack.append(literal)
    return f"push literal {literal}"


def handle_add(*, data_stack: list[int], err: Callable[[str, str], None]) -> str:
    if len(data_stack) < 2:
        err("stack-underflow", "ADD needs two cells")
    rhs = data_stack.pop()
    lhs = data_stack.pop()
    result = lhs + rhs
    data_stack.append(result)
    return f"{lhs} + {rhs} -> {result}"


def handle_exit(*, control: ExecutionControl, err: Callable[[str, str], None]) -> str:
    _ = err
    control.halt()
    return "halt"


HANDLERS: dict[int, HandlerFn] = {
    int(dictionary.PrimitiveInstruction.LIT): handle_lit,
    int(dictionary.PrimitiveInstruction.ADD): handle_add,
    int(dictionary.PrimitiveInstruction.EXIT): handle_exit,
}


SCENARIOS = (
    Scenario(
        name="success",
        text="LIT 2 LIT 3 + EXIT",
        thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            2,
            int(dictionary.PrimitiveInstruction.LIT),
            3,
            int(dictionary.PrimitiveInstruction.ADD),
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
    ),
    Scenario(
        name="underflow",
        text="LIT 2 + EXIT",
        thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            2,
            int(dictionary.PrimitiveInstruction.ADD),
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
    ),
)


def injected_resources(
    descriptor: dictionary.InstructionDescriptor,
    state: LoopState,
) -> dict[str, object]:
    """Build the concrete injected argument set from metadata."""

    req = descriptor.requirements
    kwargs: dict[str, object] = {}

    if req.min_data_stack_in > 0 or req.min_data_stack_out_space > 0:
        kwargs["data_stack"] = state.data_stack
    if descriptor.associated_data_source is dictionary.AssociatedDataSource.INLINE_THREAD:
        kwargs["thread_cursor"] = ThreadCursor(state)
    if req.needs_ip:
        kwargs["thread_cursor"] = kwargs.get("thread_cursor", ThreadCursor(state))
    if req.needs_current_xt:
        kwargs["current_xt"] = state.current_xt
    if descriptor.key == "EXIT":
        kwargs["control"] = ExecutionControl(state)
    if req.needs_error_exit:
        kwargs["err"] = error_exit
    return kwargs


def enforce_requirements(
    descriptor: dictionary.InstructionDescriptor,
    state: LoopState,
) -> None:
    """Apply the current per-handler preflight checks."""

    req = descriptor.requirements
    depth = len(state.data_stack)
    available = state.stack_limit - depth

    if depth < req.min_data_stack_in:
        error_exit(
            "stack-underflow",
            (
                f"{descriptor.key} needs {req.min_data_stack_in} data cells at ingress, "
                f"but only {depth} are present"
            ),
        )
    if available < req.min_data_stack_out_space:
        error_exit(
            "stack-overflow",
            (
                f"{descriptor.key} declares {req.min_data_stack_out_space} cells of "
                f"data-stack egress space, but only {available} slots remain"
            ),
        )


def step_once(state: LoopState) -> tuple[dictionary.InstructionDescriptor, list[str], str]:
    if state.ip >= len(state.thread):
        error_exit("missing-exit", f"ip={state.ip} stepped past the end of the thread")

    state.current_xt = int(state.thread[state.ip])
    descriptor = dictionary.instruction_descriptor_for_handler_id(state.current_xt)
    if descriptor is None:
        error_exit("unknown-handler", f"no descriptor for handler id {state.current_xt}")

    handler = HANDLERS.get(state.current_xt)
    if handler is None:
        error_exit("missing-python-handler", f"no Python handler wired for {descriptor.key}")

    enforce_requirements(descriptor, state)
    kwargs = injected_resources(descriptor, state)
    injected_names = list(kwargs.keys())
    note = handler(**kwargs)

    if not state.halted:
        state.ip += 1
    return descriptor, injected_names, note


def run_scenario(scenario: Scenario) -> None:
    state = LoopState(thread=scenario.thread)
    print(f"== {scenario.name.upper()} ==")
    print(f"thread: {scenario.text}")

    step = 0
    try:
        while not state.halted:
            stack_before = list(state.data_stack)
            active_ip = state.ip
            descriptor, injected_names, note = step_once(state)
            print(
                f"step {step}: ip={active_ip} word={descriptor.key} "
                f"family={descriptor.family.key} "
                f"source={descriptor.associated_data_source.value} "
                f"kernel={descriptor.requirements.kernel}"
            )
            print(f"  stack before: {stack_before}")
            print(f"  injected: {', '.join(injected_names) if injected_names else '(none)'}")
            print(f"  note: {note}")
            print(f"  stack after: {state.data_stack}")
            print(f"  next ip: {'halt' if state.halted else state.ip}")
            step += 1
    except ExecutionFault as exc:
        print(f"step {step}: error {exc.code}: {exc.detail}")
        print(f"  stack at failure: {state.data_stack}")

    print()


def main() -> None:
    print("HandlerRequirements-driven Python loop")
    print("This is a minimal proof of concept over package metadata, not the package runtime.")
    print()
    for scenario in SCENARIOS:
        run_scenario(scenario)


if __name__ == "__main__":
    main()
