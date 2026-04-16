"""Requested operations: arithmetic helpers and arithmetic."""

from __future__ import annotations

from kernels import binary_multi_result, binary_reduce, unary_transform
from machine import MachineState, to_cell, trunc_divmod
from registry import OperationCollector, Scenario


GROUP_TITLE = "2. Arithmetic Helpers / Arithmetic"
EXPECTED_WORDS = ("1+", "1-", "4+", "4-", "+", "-", "*", "/MOD")

RAW = OperationCollector(group=GROUP_TITLE, variant="raw")
KERNELIZED = OperationCollector(group=GROUP_TITLE, variant="kernelized")


@RAW.forth_op("1+", "( x -- x+1 )")
def raw_incr(state: MachineState) -> None:
    """1+ ( x -- x+1 ): increment the top item by one."""

    state.push_data(state.pop_data() + 1)


@KERNELIZED.forth_op("1+", "( x -- x+1 )", kernel_name="unary_transform")
def kernel_incr(state: MachineState) -> None:
    """1+ ( x -- x+1 ): increment the top item by one."""

    unary_transform(state, lambda value: value + 1)


@RAW.forth_op("1-", "( x -- x-1 )")
def raw_decr(state: MachineState) -> None:
    """1- ( x -- x-1 ): decrement the top item by one."""

    state.push_data(state.pop_data() - 1)


@KERNELIZED.forth_op("1-", "( x -- x-1 )", kernel_name="unary_transform")
def kernel_decr(state: MachineState) -> None:
    """1- ( x -- x-1 ): decrement the top item by one."""

    unary_transform(state, lambda value: value - 1)


@RAW.forth_op("4+", "( x -- x+4 )")
def raw_incr4(state: MachineState) -> None:
    """4+ ( x -- x+4 ): add four to the top item."""

    state.push_data(state.pop_data() + 4)


@KERNELIZED.forth_op("4+", "( x -- x+4 )", kernel_name="unary_transform")
def kernel_incr4(state: MachineState) -> None:
    """4+ ( x -- x+4 ): add four to the top item."""

    unary_transform(state, lambda value: value + 4)


@RAW.forth_op("4-", "( x -- x-4 )")
def raw_decr4(state: MachineState) -> None:
    """4- ( x -- x-4 ): subtract four from the top item."""

    state.push_data(state.pop_data() - 4)


@KERNELIZED.forth_op("4-", "( x -- x-4 )", kernel_name="unary_transform")
def kernel_decr4(state: MachineState) -> None:
    """4- ( x -- x-4 ): subtract four from the top item."""

    unary_transform(state, lambda value: value - 4)


@RAW.forth_op("+", "( x y -- x+y )")
def raw_add(state: MachineState) -> None:
    """+ ( x y -- x+y ): add the top two stack items."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(lhs + rhs)


@KERNELIZED.forth_op("+", "( x y -- x+y )", kernel_name="binary_reduce")
def kernel_add(state: MachineState) -> None:
    """+ ( x y -- x+y ): add the top two stack items."""

    binary_reduce(state, lambda lhs, rhs: lhs + rhs)


@RAW.forth_op("-", "( x y -- x-y )")
def raw_sub(state: MachineState) -> None:
    """- ( x y -- x-y ): subtract the top item from the next item."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(lhs - rhs)


@KERNELIZED.forth_op("-", "( x y -- x-y )", kernel_name="binary_reduce")
def kernel_sub(state: MachineState) -> None:
    """- ( x y -- x-y ): subtract the top item from the next item."""

    binary_reduce(state, lambda lhs, rhs: lhs - rhs)


@RAW.forth_op("*", "( x y -- x*y )")
def raw_mul(state: MachineState) -> None:
    """* ( x y -- x*y ): multiply the top two stack items."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(lhs * rhs)


@KERNELIZED.forth_op("*", "( x y -- x*y )", kernel_name="binary_reduce")
def kernel_mul(state: MachineState) -> None:
    """* ( x y -- x*y ): multiply the top two stack items."""

    binary_reduce(state, lambda lhs, rhs: lhs * rhs)


@RAW.forth_op("/MOD", "( n d -- rem quot )")
def raw_divmod(state: MachineState) -> None:
    """/MOD ( n d -- rem quot ): divide and leave remainder plus quotient."""

    divisor = state.pop_data()
    dividend = state.pop_data()
    remainder, quotient = trunc_divmod(dividend, divisor)
    state.push_data(remainder)
    state.push_data(quotient)


@KERNELIZED.forth_op("/MOD", "( n d -- rem quot )", kernel_name="binary_multi_result")
def kernel_divmod(state: MachineState) -> None:
    """/MOD ( n d -- rem quot ): divide and leave remainder plus quotient."""

    binary_multi_result(state, trunc_divmod)


def _stack_state(*values: int) -> MachineState:
    return MachineState().seed_data(*values)


def _assert_data(expected: list[int]):
    def check(state: MachineState) -> None:
        assert state.logical_data_stack() == [to_cell(value) for value in expected]

    return check


SCENARIOS = (
    Scenario(
        "1+", ("1+",), lambda: _stack_state(4), _assert_data([5]), "Increment by one."
    ),
    Scenario(
        "1-", ("1-",), lambda: _stack_state(4), _assert_data([3]), "Decrement by one."
    ),
    Scenario(
        "4+",
        ("4+",),
        lambda: _stack_state(8),
        _assert_data([12]),
        "Add one cell width.",
    ),
    Scenario(
        "4-",
        ("4-",),
        lambda: _stack_state(8),
        _assert_data([4]),
        "Subtract one cell width.",
    ),
    Scenario(
        "+", ("+",), lambda: _stack_state(7, 5), _assert_data([12]), "Binary addition."
    ),
    Scenario(
        "-",
        ("-",),
        lambda: _stack_state(7, 5),
        _assert_data([2]),
        "Binary subtraction.",
    ),
    Scenario(
        "*",
        ("*",),
        lambda: _stack_state(7, 5),
        _assert_data([35]),
        "Binary multiplication.",
    ),
    Scenario(
        "/MOD-positive",
        ("/MOD",),
        lambda: _stack_state(17, 5),
        _assert_data([2, 3]),
        "Signed division with positive inputs.",
    ),
    Scenario(
        "/MOD-signed",
        ("/MOD",),
        lambda: _stack_state(-17, 5),
        _assert_data([-2, -3]),
        "Signed division truncates toward zero.",
    ),
)

RAW_SPECS = RAW.specs
KERNEL_SPECS = KERNELIZED.specs
RAW_OPS = RAW.mapping()
KERNEL_OPS = KERNELIZED.mapping()
