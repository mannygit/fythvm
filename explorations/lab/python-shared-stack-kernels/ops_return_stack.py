"""Requested operations: return/data stack control."""

from __future__ import annotations

from kernels import (
    drop_return,
    get_stack_pointer,
    move_between_stacks,
    set_stack_pointer,
)
from machine import MachineState
from registry import OperationCollector, Scenario


GROUP_TITLE = "5. Return/Data Stack Control"
EXPECTED_WORDS = (">R", "R>", "RSP@", "RSP!", "RDROP", "DSP@", "DSP!")

RAW = OperationCollector(group=GROUP_TITLE, variant="raw")
KERNELIZED = OperationCollector(group=GROUP_TITLE, variant="kernelized")


@RAW.forth_op(">R", "( x -- )")
def raw_to_r(state: MachineState) -> None:
    """>R ( x -- ): move the top data-stack item to the return stack."""

    state.push_return(state.pop_data())


@KERNELIZED.forth_op(">R", "( x -- )", kernel_name="move_between_stacks")
def kernel_to_r(state: MachineState) -> None:
    """>R ( x -- ): move the top data-stack item to the return stack."""

    move_between_stacks(state, "to_return")


@RAW.forth_op("R>", "( -- x )")
def raw_from_r(state: MachineState) -> None:
    """R> ( -- x ): move the top return-stack item to the data stack."""

    state.push_data(state.pop_return())


@KERNELIZED.forth_op("R>", "( -- x )", kernel_name="move_between_stacks")
def kernel_from_r(state: MachineState) -> None:
    """R> ( -- x ): move the top return-stack item to the data stack."""

    move_between_stacks(state, "to_data")


@RAW.forth_op("RSP@", "( -- rsp )")
def raw_rsp_fetch(state: MachineState) -> None:
    """RSP@ ( -- rsp ): push the current return-stack pointer."""

    state.push_data(state.rsp)


@KERNELIZED.forth_op("RSP@", "( -- rsp )", kernel_name="get_stack_pointer")
def kernel_rsp_fetch(state: MachineState) -> None:
    """RSP@ ( -- rsp ): push the current return-stack pointer."""

    get_stack_pointer(state, "return")


@RAW.forth_op("RSP!", "( rsp -- )")
def raw_rsp_store(state: MachineState) -> None:
    """RSP! ( rsp -- ): install a new return-stack pointer."""

    state.set_rsp(state.pop_data())


@KERNELIZED.forth_op("RSP!", "( rsp -- )", kernel_name="set_stack_pointer")
def kernel_rsp_store(state: MachineState) -> None:
    """RSP! ( rsp -- ): install a new return-stack pointer."""

    set_stack_pointer(state, "return")


@RAW.forth_op("RDROP", "( -- )")
def raw_rdrop(state: MachineState) -> None:
    """RDROP ( -- ): drop the top return-stack item."""

    state.pop_return()


@KERNELIZED.forth_op("RDROP", "( -- )", kernel_name="drop_return")
def kernel_rdrop(state: MachineState) -> None:
    """RDROP ( -- ): drop the top return-stack item."""

    drop_return(state)


@RAW.forth_op("DSP@", "( -- dsp )")
def raw_dsp_fetch(state: MachineState) -> None:
    """DSP@ ( -- dsp ): push the current data-stack pointer."""

    state.push_data(state.dsp)


@KERNELIZED.forth_op("DSP@", "( -- dsp )", kernel_name="get_stack_pointer")
def kernel_dsp_fetch(state: MachineState) -> None:
    """DSP@ ( -- dsp ): push the current data-stack pointer."""

    get_stack_pointer(state, "data")


@RAW.forth_op("DSP!", "( dsp -- )")
def raw_dsp_store(state: MachineState) -> None:
    """DSP! ( dsp -- ): install a new data-stack pointer."""

    state.set_dsp(state.pop_data())


@KERNELIZED.forth_op("DSP!", "( dsp -- )", kernel_name="set_stack_pointer")
def kernel_dsp_store(state: MachineState) -> None:
    """DSP! ( dsp -- ): install a new data-stack pointer."""

    set_stack_pointer(state, "data")


def _assert_state(
    *,
    data: list[int],
    return_stack: list[int],
    dsp: int | None = None,
    rsp: int | None = None,
):
    def check(state: MachineState) -> None:
        assert state.logical_data_stack() == data
        assert state.logical_return_stack() == return_stack
        if dsp is not None:
            assert state.dsp == dsp
        if rsp is not None:
            assert state.rsp == rsp

    return check


def _to_r_state() -> MachineState:
    return MachineState().seed_data(11, 22).seed_return(33)


def _from_r_state() -> MachineState:
    return MachineState().seed_data(11).seed_return(22, 33)


def _rsp_fetch_state() -> MachineState:
    return MachineState().seed_data(99).seed_return(10, 20)


def _rsp_store_state() -> MachineState:
    return MachineState().seed_data(77, 7).seed_return(10, 20)


def _rdrop_state() -> MachineState:
    return MachineState().seed_return(10, 20)


def _dsp_fetch_state() -> MachineState:
    return MachineState().seed_data(11, 22)


def _dsp_store_state() -> MachineState:
    return MachineState().seed_data(11, 22, 7)


SCENARIOS = (
    Scenario(
        ">R",
        (">R",),
        _to_r_state,
        _assert_state(data=[11], return_stack=[33, 22], rsp=6),
        "Move the top data item onto the return stack.",
    ),
    Scenario(
        "R>",
        ("R>",),
        _from_r_state,
        _assert_state(data=[11, 33], return_stack=[22], rsp=7),
        "Move the top return item onto the data stack.",
    ),
    Scenario(
        "RSP@",
        ("RSP@",),
        _rsp_fetch_state,
        _assert_state(data=[99, 6], return_stack=[10, 20], rsp=6),
        "Snapshot the return-stack pointer.",
    ),
    Scenario(
        "RSP!",
        ("RSP!",),
        _rsp_store_state,
        _assert_state(data=[77], return_stack=[10], rsp=7),
        "Install a new return-stack pointer.",
    ),
    Scenario(
        "RDROP",
        ("RDROP",),
        _rdrop_state,
        _assert_state(data=[], return_stack=[10], rsp=7),
        "Drop the top return-stack item.",
    ),
    Scenario(
        "DSP@",
        ("DSP@",),
        _dsp_fetch_state,
        _assert_state(data=[11, 22, 6], return_stack=[], dsp=5),
        "Snapshot the data-stack pointer.",
    ),
    Scenario(
        "DSP!",
        ("DSP!",),
        _dsp_store_state,
        _assert_state(data=[11], return_stack=[], dsp=7),
        "Install a new data-stack pointer.",
    ),
)

RAW_SPECS = RAW.specs
KERNEL_SPECS = KERNELIZED.specs
RAW_OPS = RAW.mapping()
KERNEL_OPS = KERNELIZED.mapping()
