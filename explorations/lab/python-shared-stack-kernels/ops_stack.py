"""Requested operations: stack manipulation."""

from __future__ import annotations

from kernels import (
    copy_from_depth,
    drop_n,
    dup_segment,
    dup_top,
    dup_top_if_nonzero,
    permute,
)
from machine import MachineState
from registry import OperationCollector, Scenario


GROUP_TITLE = "1. Stack Manipulation"
EXPECTED_WORDS = (
    "DROP",
    "SWAP",
    "DUP",
    "OVER",
    "ROT",
    "-ROT",
    "2DROP",
    "2DUP",
    "2SWAP",
    "?DUP",
)

RAW = OperationCollector(group=GROUP_TITLE, variant="raw")
KERNELIZED = OperationCollector(group=GROUP_TITLE, variant="kernelized")


@RAW.forth_op("DROP", "( x -- )")
def raw_drop(state: MachineState) -> None:
    """DROP ( x -- ): remove the top stack item."""

    state.pop_data()


@KERNELIZED.forth_op("DROP", "( x -- )", kernel_name="drop_n")
def kernel_drop(state: MachineState) -> None:
    """DROP ( x -- ): remove the top stack item."""

    drop_n(state, 1)


@RAW.forth_op("SWAP", "( x y -- y x )")
def raw_swap(state: MachineState) -> None:
    """SWAP ( x y -- y x ): exchange the top two items."""

    top = state.pop_data()
    second = state.pop_data()
    state.push_data(top)
    state.push_data(second)


@KERNELIZED.forth_op("SWAP", "( x y -- y x )", kernel_name="permute")
def kernel_swap(state: MachineState) -> None:
    """SWAP ( x y -- y x ): exchange the top two items."""

    permute(state, 2, (1, 0))


@RAW.forth_op("DUP", "( x -- x x )")
def raw_dup(state: MachineState) -> None:
    """DUP ( x -- x x ): duplicate the top stack item."""

    state.push_data(state.peek_data(0))


@KERNELIZED.forth_op("DUP", "( x -- x x )", kernel_name="dup_top")
def kernel_dup(state: MachineState) -> None:
    """DUP ( x -- x x ): duplicate the top stack item."""

    dup_top(state)


@RAW.forth_op("OVER", "( x y -- x y x )")
def raw_over(state: MachineState) -> None:
    """OVER ( x y -- x y x ): copy the second item to the top."""

    state.push_data(state.peek_data(1))


@KERNELIZED.forth_op("OVER", "( x y -- x y x )", kernel_name="copy_from_depth")
def kernel_over(state: MachineState) -> None:
    """OVER ( x y -- x y x ): copy the second item to the top."""

    copy_from_depth(state, 1)


@RAW.forth_op("ROT", "( x y z -- y z x )")
def raw_rot(state: MachineState) -> None:
    """ROT ( x y z -- y z x ): rotate the top three items left."""

    state.replace_data_window(
        3, [state.data_window(3)[1], state.data_window(3)[2], state.data_window(3)[0]]
    )


@KERNELIZED.forth_op("ROT", "( x y z -- y z x )", kernel_name="permute")
def kernel_rot(state: MachineState) -> None:
    """ROT ( x y z -- y z x ): rotate the top three items left."""

    permute(state, 3, (1, 2, 0))


@RAW.forth_op("-ROT", "( x y z -- z x y )")
def raw_nrot(state: MachineState) -> None:
    """-ROT ( x y z -- z x y ): rotate the top three items right."""

    state.replace_data_window(
        3, [state.data_window(3)[2], state.data_window(3)[0], state.data_window(3)[1]]
    )


@KERNELIZED.forth_op("-ROT", "( x y z -- z x y )", kernel_name="permute")
def kernel_nrot(state: MachineState) -> None:
    """-ROT ( x y z -- z x y ): rotate the top three items right."""

    permute(state, 3, (2, 0, 1))


@RAW.forth_op("2DROP", "( x y -- )")
def raw_two_drop(state: MachineState) -> None:
    """2DROP ( x y -- ): drop the top two stack items."""

    state.pop_data()
    state.pop_data()


@KERNELIZED.forth_op("2DROP", "( x y -- )", kernel_name="drop_n")
def kernel_two_drop(state: MachineState) -> None:
    """2DROP ( x y -- ): drop the top two stack items."""

    drop_n(state, 2)


@RAW.forth_op("2DUP", "( x y -- x y x y )")
def raw_two_dup(state: MachineState) -> None:
    """2DUP ( x y -- x y x y ): duplicate the top stack pair."""

    first, second = state.data_window(2)
    state.push_data(first)
    state.push_data(second)


@KERNELIZED.forth_op("2DUP", "( x y -- x y x y )", kernel_name="dup_segment")
def kernel_two_dup(state: MachineState) -> None:
    """2DUP ( x y -- x y x y ): duplicate the top stack pair."""

    dup_segment(state, 2)


@RAW.forth_op("2SWAP", "( a b c d -- c d a b )")
def raw_two_swap(state: MachineState) -> None:
    """2SWAP ( a b c d -- c d a b ): swap the top two pairs."""

    a, b, c, d = state.data_window(4)
    state.replace_data_window(4, [c, d, a, b])


@KERNELIZED.forth_op("2SWAP", "( a b c d -- c d a b )", kernel_name="permute")
def kernel_two_swap(state: MachineState) -> None:
    """2SWAP ( a b c d -- c d a b ): swap the top two pairs."""

    permute(state, 4, (2, 3, 0, 1))


@RAW.forth_op("?DUP", "( x -- x ) | ( x -- x x )")
def raw_qdup(state: MachineState) -> None:
    """?DUP ( x -- x ) | ( x -- x x ): duplicate top item when non-zero."""

    value = state.peek_data(0)
    if value != 0:
        state.push_data(value)


@KERNELIZED.forth_op(
    "?DUP", "( x -- x ) | ( x -- x x )", kernel_name="dup_top_if_nonzero"
)
def kernel_qdup(state: MachineState) -> None:
    """?DUP ( x -- x ) | ( x -- x x ): duplicate top item when non-zero."""

    dup_top_if_nonzero(state)


def _stack_state(*values: int) -> MachineState:
    return MachineState().seed_data(*values)


def _assert_data(expected: list[int]):
    def check(state: MachineState) -> None:
        assert state.logical_data_stack() == expected

    return check


SCENARIOS = (
    Scenario(
        "drop",
        ("DROP",),
        lambda: _stack_state(11, 22),
        _assert_data([11]),
        "Drop the current top item.",
    ),
    Scenario(
        "swap",
        ("SWAP",),
        lambda: _stack_state(11, 22),
        _assert_data([22, 11]),
        "Swap top two items.",
    ),
    Scenario(
        "dup",
        ("DUP",),
        lambda: _stack_state(11),
        _assert_data([11, 11]),
        "Duplicate top item.",
    ),
    Scenario(
        "over",
        ("OVER",),
        lambda: _stack_state(11, 22),
        _assert_data([11, 22, 11]),
        "Copy second item to top.",
    ),
    Scenario(
        "rot",
        ("ROT",),
        lambda: _stack_state(11, 22, 33),
        _assert_data([22, 33, 11]),
        "Rotate top three left.",
    ),
    Scenario(
        "minus-rot",
        ("-ROT",),
        lambda: _stack_state(11, 22, 33),
        _assert_data([33, 11, 22]),
        "Rotate top three right.",
    ),
    Scenario(
        "two-drop",
        ("2DROP",),
        lambda: _stack_state(11, 22),
        _assert_data([]),
        "Drop the top pair.",
    ),
    Scenario(
        "two-dup",
        ("2DUP",),
        lambda: _stack_state(11, 22),
        _assert_data([11, 22, 11, 22]),
        "Duplicate the top pair.",
    ),
    Scenario(
        "two-swap",
        ("2SWAP",),
        lambda: _stack_state(11, 22, 33, 44),
        _assert_data([33, 44, 11, 22]),
        "Swap the top two pairs.",
    ),
    Scenario(
        "qdup-nonzero",
        ("?DUP",),
        lambda: _stack_state(7),
        _assert_data([7, 7]),
        "Duplicate when non-zero.",
    ),
    Scenario(
        "qdup-zero",
        ("?DUP",),
        lambda: _stack_state(0),
        _assert_data([0]),
        "Leave zero untouched.",
    ),
)

RAW_SPECS = RAW.specs
KERNEL_SPECS = KERNELIZED.specs
RAW_OPS = RAW.mapping()
KERNEL_OPS = KERNELIZED.mapping()
