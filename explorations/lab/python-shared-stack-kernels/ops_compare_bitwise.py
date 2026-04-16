"""Requested operations: comparisons and bitwise words."""

from __future__ import annotations

from kernels import binary_reduce, unary_predicate, unary_transform
from machine import MachineState, bool_cell, to_cell
from registry import OperationCollector, Scenario


GROUP_TITLE = "3. Comparisons / Bitwise"
EXPECTED_WORDS = (
    "=",
    "<>",
    "<",
    ">",
    "<=",
    ">=",
    "0=",
    "0<>",
    "0<",
    "0>",
    "0<=",
    "0>=",
    "AND",
    "OR",
    "XOR",
    "INVERT",
)

RAW = OperationCollector(group=GROUP_TITLE, variant="raw")
KERNELIZED = OperationCollector(group=GROUP_TITLE, variant="kernelized")


@RAW.forth_op("=", "( x y -- flag )")
def raw_equ(state: MachineState) -> None:
    """= ( x y -- flag ): compare the top two items for equality."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(bool_cell(lhs == rhs))


@KERNELIZED.forth_op("=", "( x y -- flag )", kernel_name="binary_reduce")
def kernel_equ(state: MachineState) -> None:
    """= ( x y -- flag ): compare the top two items for equality."""

    binary_reduce(state, lambda lhs, rhs: bool_cell(lhs == rhs))


@RAW.forth_op("<>", "( x y -- flag )")
def raw_nequ(state: MachineState) -> None:
    """<> ( x y -- flag ): compare the top two items for inequality."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(bool_cell(lhs != rhs))


@KERNELIZED.forth_op("<>", "( x y -- flag )", kernel_name="binary_reduce")
def kernel_nequ(state: MachineState) -> None:
    """<> ( x y -- flag ): compare the top two items for inequality."""

    binary_reduce(state, lambda lhs, rhs: bool_cell(lhs != rhs))


@RAW.forth_op("<", "( x y -- flag )")
def raw_lt(state: MachineState) -> None:
    """< ( x y -- flag ): test whether the next item is less than the top item."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(bool_cell(lhs < rhs))


@KERNELIZED.forth_op("<", "( x y -- flag )", kernel_name="binary_reduce")
def kernel_lt(state: MachineState) -> None:
    """< ( x y -- flag ): test whether the next item is less than the top item."""

    binary_reduce(state, lambda lhs, rhs: bool_cell(lhs < rhs))


@RAW.forth_op(">", "( x y -- flag )")
def raw_gt(state: MachineState) -> None:
    """> ( x y -- flag ): test whether the next item is greater than the top item."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(bool_cell(lhs > rhs))


@KERNELIZED.forth_op(">", "( x y -- flag )", kernel_name="binary_reduce")
def kernel_gt(state: MachineState) -> None:
    """> ( x y -- flag ): test whether the next item is greater than the top item."""

    binary_reduce(state, lambda lhs, rhs: bool_cell(lhs > rhs))


@RAW.forth_op("<=", "( x y -- flag )")
def raw_le(state: MachineState) -> None:
    """<= ( x y -- flag ): test whether the next item is less-or-equal to the top item."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(bool_cell(lhs <= rhs))


@KERNELIZED.forth_op("<=", "( x y -- flag )", kernel_name="binary_reduce")
def kernel_le(state: MachineState) -> None:
    """<= ( x y -- flag ): test whether the next item is less-or-equal to the top item."""

    binary_reduce(state, lambda lhs, rhs: bool_cell(lhs <= rhs))


@RAW.forth_op(">=", "( x y -- flag )")
def raw_ge(state: MachineState) -> None:
    """>= ( x y -- flag ): test whether the next item is greater-or-equal to the top item."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(bool_cell(lhs >= rhs))


@KERNELIZED.forth_op(">=", "( x y -- flag )", kernel_name="binary_reduce")
def kernel_ge(state: MachineState) -> None:
    """>= ( x y -- flag ): test whether the next item is greater-or-equal to the top item."""

    binary_reduce(state, lambda lhs, rhs: bool_cell(lhs >= rhs))


@RAW.forth_op("0=", "( x -- flag )")
def raw_zequ(state: MachineState) -> None:
    """0= ( x -- flag ): test whether the top item is zero."""

    state.push_data(bool_cell(state.pop_data() == 0))


@KERNELIZED.forth_op("0=", "( x -- flag )", kernel_name="unary_predicate")
def kernel_zequ(state: MachineState) -> None:
    """0= ( x -- flag ): test whether the top item is zero."""

    unary_predicate(state, lambda value: value == 0)


@RAW.forth_op("0<>", "( x -- flag )")
def raw_znequ(state: MachineState) -> None:
    """0<> ( x -- flag ): test whether the top item is non-zero."""

    state.push_data(bool_cell(state.pop_data() != 0))


@KERNELIZED.forth_op("0<>", "( x -- flag )", kernel_name="unary_predicate")
def kernel_znequ(state: MachineState) -> None:
    """0<> ( x -- flag ): test whether the top item is non-zero."""

    unary_predicate(state, lambda value: value != 0)


@RAW.forth_op("0<", "( x -- flag )")
def raw_zlt(state: MachineState) -> None:
    """0< ( x -- flag ): test whether the top item is negative."""

    state.push_data(bool_cell(state.pop_data() < 0))


@KERNELIZED.forth_op("0<", "( x -- flag )", kernel_name="unary_predicate")
def kernel_zlt(state: MachineState) -> None:
    """0< ( x -- flag ): test whether the top item is negative."""

    unary_predicate(state, lambda value: value < 0)


@RAW.forth_op("0>", "( x -- flag )")
def raw_zgt(state: MachineState) -> None:
    """0> ( x -- flag ): test whether the top item is positive."""

    state.push_data(bool_cell(state.pop_data() > 0))


@KERNELIZED.forth_op("0>", "( x -- flag )", kernel_name="unary_predicate")
def kernel_zgt(state: MachineState) -> None:
    """0> ( x -- flag ): test whether the top item is positive."""

    unary_predicate(state, lambda value: value > 0)


@RAW.forth_op("0<=", "( x -- flag )")
def raw_zle(state: MachineState) -> None:
    """0<= ( x -- flag ): test whether the top item is non-positive."""

    state.push_data(bool_cell(state.pop_data() <= 0))


@KERNELIZED.forth_op("0<=", "( x -- flag )", kernel_name="unary_predicate")
def kernel_zle(state: MachineState) -> None:
    """0<= ( x -- flag ): test whether the top item is non-positive."""

    unary_predicate(state, lambda value: value <= 0)


@RAW.forth_op("0>=", "( x -- flag )")
def raw_zge(state: MachineState) -> None:
    """0>= ( x -- flag ): test whether the top item is non-negative."""

    state.push_data(bool_cell(state.pop_data() >= 0))


@KERNELIZED.forth_op("0>=", "( x -- flag )", kernel_name="unary_predicate")
def kernel_zge(state: MachineState) -> None:
    """0>= ( x -- flag ): test whether the top item is non-negative."""

    unary_predicate(state, lambda value: value >= 0)


@RAW.forth_op("AND", "( x y -- x&y )")
def raw_and(state: MachineState) -> None:
    """AND ( x y -- x&y ): bitwise-and the top two items."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(lhs & rhs)


@KERNELIZED.forth_op("AND", "( x y -- x&y )", kernel_name="binary_reduce")
def kernel_and(state: MachineState) -> None:
    """AND ( x y -- x&y ): bitwise-and the top two items."""

    binary_reduce(state, lambda lhs, rhs: lhs & rhs)


@RAW.forth_op("OR", "( x y -- x|y )")
def raw_or(state: MachineState) -> None:
    """OR ( x y -- x|y ): bitwise-or the top two items."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(lhs | rhs)


@KERNELIZED.forth_op("OR", "( x y -- x|y )", kernel_name="binary_reduce")
def kernel_or(state: MachineState) -> None:
    """OR ( x y -- x|y ): bitwise-or the top two items."""

    binary_reduce(state, lambda lhs, rhs: lhs | rhs)


@RAW.forth_op("XOR", "( x y -- x^y )")
def raw_xor(state: MachineState) -> None:
    """XOR ( x y -- x^y ): bitwise-xor the top two items."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(lhs ^ rhs)


@KERNELIZED.forth_op("XOR", "( x y -- x^y )", kernel_name="binary_reduce")
def kernel_xor(state: MachineState) -> None:
    """XOR ( x y -- x^y ): bitwise-xor the top two items."""

    binary_reduce(state, lambda lhs, rhs: lhs ^ rhs)


@RAW.forth_op("INVERT", "( x -- ~x )")
def raw_invert(state: MachineState) -> None:
    """INVERT ( x -- ~x ): bitwise invert the top item."""

    state.push_data(~state.pop_data())


@KERNELIZED.forth_op("INVERT", "( x -- ~x )", kernel_name="unary_transform")
def kernel_invert(state: MachineState) -> None:
    """INVERT ( x -- ~x ): bitwise invert the top item."""

    unary_transform(state, lambda value: ~value)


def _stack_state(*values: int) -> MachineState:
    return MachineState().seed_data(*values)


def _assert_data(expected: list[int]):
    def check(state: MachineState) -> None:
        assert state.logical_data_stack() == [to_cell(value) for value in expected]

    return check


SCENARIOS = (
    Scenario(
        "=", ("=",), lambda: _stack_state(7, 7), _assert_data([1]), "Equality yields 1."
    ),
    Scenario(
        "<>",
        ("<>",),
        lambda: _stack_state(7, 5),
        _assert_data([1]),
        "Inequality yields 1.",
    ),
    Scenario(
        "<", ("<",), lambda: _stack_state(3, 5), _assert_data([1]), "Signed less-than."
    ),
    Scenario(
        ">",
        (">",),
        lambda: _stack_state(5, 3),
        _assert_data([1]),
        "Signed greater-than.",
    ),
    Scenario(
        "<=",
        ("<=",),
        lambda: _stack_state(5, 5),
        _assert_data([1]),
        "Signed less-or-equal.",
    ),
    Scenario(
        ">=",
        (">=",),
        lambda: _stack_state(5, 5),
        _assert_data([1]),
        "Signed greater-or-equal.",
    ),
    Scenario(
        "0=", ("0=",), lambda: _stack_state(0), _assert_data([1]), "Zero predicate."
    ),
    Scenario(
        "0<>",
        ("0<>",),
        lambda: _stack_state(9),
        _assert_data([1]),
        "Non-zero predicate.",
    ),
    Scenario(
        "0<",
        ("0<",),
        lambda: _stack_state(-1),
        _assert_data([1]),
        "Negative predicate.",
    ),
    Scenario(
        "0>", ("0>",), lambda: _stack_state(9), _assert_data([1]), "Positive predicate."
    ),
    Scenario(
        "0<=",
        ("0<=",),
        lambda: _stack_state(0),
        _assert_data([1]),
        "Non-positive predicate.",
    ),
    Scenario(
        "0>=",
        ("0>=",),
        lambda: _stack_state(0),
        _assert_data([1]),
        "Non-negative predicate.",
    ),
    Scenario(
        "AND",
        ("AND",),
        lambda: _stack_state(0b1100, 0b1010),
        _assert_data([0b1000]),
        "Bitwise and.",
    ),
    Scenario(
        "OR",
        ("OR",),
        lambda: _stack_state(0b1100, 0b1010),
        _assert_data([0b1110]),
        "Bitwise or.",
    ),
    Scenario(
        "XOR",
        ("XOR",),
        lambda: _stack_state(0b1100, 0b1010),
        _assert_data([0b0110]),
        "Bitwise xor.",
    ),
    Scenario(
        "INVERT",
        ("INVERT",),
        lambda: _stack_state(0),
        _assert_data([-1]),
        "Bitwise invert.",
    ),
)

RAW_SPECS = RAW.specs
KERNEL_SPECS = KERNELIZED.specs
RAW_OPS = RAW.mapping()
KERNEL_OPS = KERNELIZED.mapping()
