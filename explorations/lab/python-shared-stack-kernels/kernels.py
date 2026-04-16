"""Shared implementation-shape helpers for the pure Python lab."""

from __future__ import annotations

from collections.abc import Callable

from machine import MachineState, bool_cell, to_cell


def drop_n(state: MachineState, n: int) -> None:
    """Drop ``n`` items from the data stack."""

    for _ in range(n):
        state.pop_data()


def permute(state: MachineState, window: int, order: tuple[int, ...]) -> None:
    """Rewrite the top stack window using a permutation over Forth-order items."""

    segment = state.data_window(window)
    state.replace_data_window(window, [segment[index] for index in order])


def dup_top(state: MachineState) -> None:
    """Duplicate the current top data-stack item."""

    state.push_data(state.peek_data(0))


def dup_top_if_nonzero(state: MachineState) -> None:
    """Duplicate the current top item only when it is non-zero."""

    value = state.peek_data(0)
    if value != 0:
        state.push_data(value)


def copy_from_depth(state: MachineState, depth: int) -> None:
    """Copy one deeper item to the top of stack."""

    state.push_data(state.peek_data(depth))


def dup_segment(state: MachineState, width: int) -> None:
    """Duplicate the top stack segment in Forth order."""

    for value in state.data_window(width):
        state.push_data(value)


def unary_transform(state: MachineState, fn: Callable[[int], int]) -> None:
    """Replace the top item with one transformed item."""

    state.push_data(to_cell(fn(state.pop_data())))


def unary_predicate(state: MachineState, fn: Callable[[int], bool]) -> None:
    """Replace the top item with one boolean-like cell."""

    state.push_data(bool_cell(fn(state.pop_data())))


def binary_reduce(state: MachineState, fn: Callable[[int, int], int]) -> None:
    """Reduce two inputs into one output."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    state.push_data(to_cell(fn(lhs, rhs)))


def binary_multi_result(
    state: MachineState,
    fn: Callable[[int, int], tuple[int, int]],
) -> None:
    """Reduce two inputs into two ordered outputs."""

    rhs = state.pop_data()
    lhs = state.pop_data()
    first, second = fn(lhs, rhs)
    state.push_data(first)
    state.push_data(second)


def memory_store(state: MachineState, *, width: int) -> None:
    """Store one cell or one byte through a stack-supplied address."""

    address = state.pop_data()
    value = state.pop_data()
    if width == 4:
        state.write_cell(address, value)
        return
    if width == 1:
        state.write_byte(address, value)
        return
    raise ValueError(f"unsupported store width {width}")


def memory_fetch(state: MachineState, *, width: int) -> None:
    """Fetch one cell or one byte through a stack-supplied address."""

    address = state.pop_data()
    if width == 4:
        state.push_data(state.read_cell(address))
        return
    if width == 1:
        state.push_data(state.read_byte(address))
        return
    raise ValueError(f"unsupported fetch width {width}")


def memory_update(state: MachineState, fn: Callable[[int, int], int]) -> None:
    """Load/update/store one cell at an address."""

    address = state.pop_data()
    delta = state.pop_data()
    state.write_cell(address, to_cell(fn(state.read_cell(address), delta)))


def copy_byte_and_advance(state: MachineState) -> None:
    """Copy one byte and leave advanced source and destination pointers."""

    src, dst = state.data_window(2)
    state.copy_byte(src, dst)
    state.replace_data_window(2, [src + 1, dst + 1])


def copy_block(state: MachineState) -> None:
    """Copy one byte block and consume source, destination, and length."""

    length = state.pop_data()
    dst = state.pop_data()
    src = state.pop_data()
    state.copy_bytes(src, dst, length)


def move_between_stacks(state: MachineState, direction: str) -> None:
    """Move one cell between the data and return stacks."""

    if direction == "to_return":
        state.push_return(state.pop_data())
        return
    if direction == "to_data":
        state.push_data(state.pop_return())
        return
    raise ValueError(f"unsupported stack direction {direction!r}")


def drop_return(state: MachineState) -> None:
    """Drop the top return-stack item."""

    state.pop_return()


def get_stack_pointer(state: MachineState, kind: str) -> None:
    """Push one current stack pointer onto the data stack."""

    if kind == "data":
        state.push_data(state.dsp)
        return
    if kind == "return":
        state.push_data(state.rsp)
        return
    raise ValueError(f"unsupported pointer kind {kind!r}")


def set_stack_pointer(state: MachineState, kind: str) -> None:
    """Install one stack pointer from the data stack."""

    pointer = state.pop_data()
    if kind == "data":
        state.set_dsp(pointer)
        return
    if kind == "return":
        state.set_rsp(pointer)
        return
    raise ValueError(f"unsupported pointer kind {kind!r}")


__all__ = [
    "binary_multi_result",
    "binary_reduce",
    "copy_block",
    "copy_byte_and_advance",
    "copy_from_depth",
    "drop_n",
    "drop_return",
    "dup_segment",
    "dup_top",
    "dup_top_if_nonzero",
    "get_stack_pointer",
    "memory_fetch",
    "memory_store",
    "memory_update",
    "move_between_stacks",
    "permute",
    "set_stack_pointer",
    "unary_predicate",
    "unary_transform",
]
