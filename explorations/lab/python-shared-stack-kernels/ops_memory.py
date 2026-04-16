"""Requested operations: memory primitives."""

from __future__ import annotations

from kernels import (
    copy_block,
    copy_byte_and_advance,
    memory_fetch,
    memory_store,
    memory_update,
)
from machine import MachineState
from registry import OperationCollector, Scenario


GROUP_TITLE = "4. Memory Primitives"
EXPECTED_WORDS = ("!", "@", "+!", "-!", "C!", "C@", "C@C!", "CMOVE")

RAW = OperationCollector(group=GROUP_TITLE, variant="raw")
KERNELIZED = OperationCollector(group=GROUP_TITLE, variant="kernelized")


@RAW.forth_op("!", "( x addr -- )")
def raw_store(state: MachineState) -> None:
    """! ( x addr -- ): store one cell through an address."""

    address = state.pop_data()
    value = state.pop_data()
    state.write_cell(address, value)


@KERNELIZED.forth_op("!", "( x addr -- )", kernel_name="memory_store")
def kernel_store(state: MachineState) -> None:
    """! ( x addr -- ): store one cell through an address."""

    memory_store(state, width=4)


@RAW.forth_op("@", "( addr -- x )")
def raw_fetch(state: MachineState) -> None:
    """@ ( addr -- x ): fetch one cell through an address."""

    state.push_data(state.read_cell(state.pop_data()))


@KERNELIZED.forth_op("@", "( addr -- x )", kernel_name="memory_fetch")
def kernel_fetch(state: MachineState) -> None:
    """@ ( addr -- x ): fetch one cell through an address."""

    memory_fetch(state, width=4)


@RAW.forth_op("+!", "( n addr -- )")
def raw_add_store(state: MachineState) -> None:
    """+! ( n addr -- ): add one delta into a cell at an address."""

    address = state.pop_data()
    delta = state.pop_data()
    state.write_cell(address, state.read_cell(address) + delta)


@KERNELIZED.forth_op("+!", "( n addr -- )", kernel_name="memory_update")
def kernel_add_store(state: MachineState) -> None:
    """+! ( n addr -- ): add one delta into a cell at an address."""

    memory_update(state, lambda current, delta: current + delta)


@RAW.forth_op("-!", "( n addr -- )")
def raw_sub_store(state: MachineState) -> None:
    """-! ( n addr -- ): subtract one delta from a cell at an address."""

    address = state.pop_data()
    delta = state.pop_data()
    state.write_cell(address, state.read_cell(address) - delta)


@KERNELIZED.forth_op("-!", "( n addr -- )", kernel_name="memory_update")
def kernel_sub_store(state: MachineState) -> None:
    """-! ( n addr -- ): subtract one delta from a cell at an address."""

    memory_update(state, lambda current, delta: current - delta)


@RAW.forth_op("C!", "( x addr -- )")
def raw_store_byte(state: MachineState) -> None:
    """C! ( x addr -- ): store the low byte through an address."""

    address = state.pop_data()
    value = state.pop_data()
    state.write_byte(address, value)


@KERNELIZED.forth_op("C!", "( x addr -- )", kernel_name="memory_store")
def kernel_store_byte(state: MachineState) -> None:
    """C! ( x addr -- ): store the low byte through an address."""

    memory_store(state, width=1)


@RAW.forth_op("C@", "( addr -- x )")
def raw_fetch_byte(state: MachineState) -> None:
    """C@ ( addr -- x ): fetch one zero-extended byte through an address."""

    state.push_data(state.read_byte(state.pop_data()))


@KERNELIZED.forth_op("C@", "( addr -- x )", kernel_name="memory_fetch")
def kernel_fetch_byte(state: MachineState) -> None:
    """C@ ( addr -- x ): fetch one zero-extended byte through an address."""

    memory_fetch(state, width=1)


@RAW.forth_op("C@C!", "( src dst -- src+1 dst+1 )")
def raw_ccopy(state: MachineState) -> None:
    """C@C! ( src dst -- src+1 dst+1 ): copy one byte and advance both pointers."""

    src, dst = state.data_window(2)
    state.copy_byte(src, dst)
    state.replace_data_window(2, [src + 1, dst + 1])


@KERNELIZED.forth_op(
    "C@C!", "( src dst -- src+1 dst+1 )", kernel_name="copy_byte_and_advance"
)
def kernel_ccopy(state: MachineState) -> None:
    """C@C! ( src dst -- src+1 dst+1 ): copy one byte and advance both pointers."""

    copy_byte_and_advance(state)


@RAW.forth_op("CMOVE", "( src dst len -- )")
def raw_cmove(state: MachineState) -> None:
    """CMOVE ( src dst len -- ): copy one byte block."""

    length = state.pop_data()
    dst = state.pop_data()
    src = state.pop_data()
    state.copy_bytes(src, dst, length)


@KERNELIZED.forth_op("CMOVE", "( src dst len -- )", kernel_name="copy_block")
def kernel_cmove(state: MachineState) -> None:
    """CMOVE ( src dst len -- ): copy one byte block."""

    copy_block(state)


def _assert_data(expected: list[int]):
    def check(state: MachineState) -> None:
        assert state.logical_data_stack() == expected

    return check


def _store_state() -> MachineState:
    return MachineState().seed_data(0x11223344, 8)


def _fetch_state() -> MachineState:
    state = MachineState().seed_data(8)
    state.write_cell(8, 0x11223344)
    return state


def _add_store_state() -> MachineState:
    state = MachineState().seed_data(5, 8)
    state.write_cell(8, 10)
    return state


def _sub_store_state() -> MachineState:
    state = MachineState().seed_data(3, 8)
    state.write_cell(8, 10)
    return state


def _store_byte_state() -> MachineState:
    return MachineState().seed_data(0x1234, 8)


def _fetch_byte_state() -> MachineState:
    state = MachineState().seed_data(8)
    state.write_byte(8, 0xFE)
    return state


def _ccopy_state() -> MachineState:
    state = MachineState().seed_data(4, 8)
    state.write_byte(4, 0x41)
    return state


def _cmove_state() -> MachineState:
    state = MachineState().seed_data(4, 12, 4)
    state.memory[4:8] = b"ABCD"
    return state


def _assert_store(state: MachineState) -> None:
    assert state.logical_data_stack() == []
    assert state.read_cell(8) == 0x11223344


def _assert_fetch(state: MachineState) -> None:
    assert state.logical_data_stack() == [0x11223344]


def _assert_add_store(state: MachineState) -> None:
    assert state.logical_data_stack() == []
    assert state.read_cell(8) == 15


def _assert_sub_store(state: MachineState) -> None:
    assert state.logical_data_stack() == []
    assert state.read_cell(8) == 7


def _assert_store_byte(state: MachineState) -> None:
    assert state.logical_data_stack() == []
    assert state.read_byte(8) == 0x34


def _assert_fetch_byte(state: MachineState) -> None:
    assert state.logical_data_stack() == [0xFE]


def _assert_ccopy(state: MachineState) -> None:
    assert state.logical_data_stack() == [5, 9]
    assert state.read_byte(8) == 0x41


def _assert_cmove(state: MachineState) -> None:
    assert state.logical_data_stack() == []
    assert state.memory_slice(12, 4) == b"ABCD"


SCENARIOS = (
    Scenario("!", ("!",), _store_state, _assert_store, "Store a 32-bit cell."),
    Scenario("@", ("@",), _fetch_state, _assert_fetch, "Fetch a 32-bit cell."),
    Scenario(
        "+!", ("+!",), _add_store_state, _assert_add_store, "Update a cell by addition."
    ),
    Scenario(
        "-!",
        ("-!",),
        _sub_store_state,
        _assert_sub_store,
        "Update a cell by subtraction.",
    ),
    Scenario("C!", ("C!",), _store_byte_state, _assert_store_byte, "Store one byte."),
    Scenario("C@", ("C@",), _fetch_byte_state, _assert_fetch_byte, "Fetch one byte."),
    Scenario(
        "C@C!",
        ("C@C!",),
        _ccopy_state,
        _assert_ccopy,
        "Copy one byte and return advanced pointers.",
    ),
    Scenario("CMOVE", ("CMOVE",), _cmove_state, _assert_cmove, "Copy one byte block."),
)

RAW_SPECS = RAW.specs
KERNEL_SPECS = KERNELIZED.specs
RAW_OPS = RAW.mapping()
KERNEL_OPS = KERNELIZED.mapping()
