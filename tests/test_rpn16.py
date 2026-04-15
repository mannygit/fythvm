"""Integration tests for the promoted 16-bit RPN calculator."""

from __future__ import annotations

import pytest

from fythvm import rpn16


@pytest.fixture(scope="module")
def calculator() -> rpn16.CompiledCalculator:
    return rpn16.compile_calculator()


@pytest.mark.parametrize(
    ("cells", "expected_result"),
    [
        ((rpn16.lit(2), rpn16.lit(1), rpn16.lit(1), rpn16.op("+"), rpn16.op("+"), rpn16.op("=")), 4),
        ((rpn16.lit(100), rpn16.lit(10), rpn16.op("/"), rpn16.op("=")), 10),
    ],
)
def test_calculator_success_cases(calculator: rpn16.CompiledCalculator, cells: tuple[int, ...], expected_result: int) -> None:
    result = calculator.evaluate(cells)
    assert result.status == rpn16.Status.OK
    assert result.result == expected_result
    assert result.logical_stack == [expected_result]


@pytest.mark.parametrize(
    ("cells", "expected_status"),
    [
        ((rpn16.op("+"), rpn16.op("=")), rpn16.Status.STACK_UNDERFLOW),
        ((rpn16.lit(10), rpn16.lit(0), rpn16.op("/"), rpn16.op("=")), rpn16.Status.DIVIDE_BY_ZERO),
        ((rpn16.lit(5), rpn16.TAG_MASK | ord("^"), rpn16.op("=")), rpn16.Status.BAD_OPCODE),
        ((rpn16.lit(1), rpn16.lit(2), rpn16.op("+")), rpn16.Status.MISSING_EXIT),
        ((rpn16.lit(1), rpn16.lit(2), rpn16.op("=")), rpn16.Status.STACK_NOT_SINGLETON),
        (
            (
                rpn16.lit(0),
                rpn16.lit(1),
                rpn16.lit(2),
                rpn16.lit(3),
                rpn16.lit(4),
                rpn16.lit(5),
                rpn16.lit(6),
                rpn16.lit(7),
                rpn16.lit(8),
                rpn16.op("="),
            ),
            rpn16.Status.STACK_OVERFLOW,
        ),
    ],
)
def test_calculator_failure_cases(
    calculator: rpn16.CompiledCalculator,
    cells: tuple[int, ...],
    expected_status: rpn16.Status,
) -> None:
    result = calculator.evaluate(cells)
    assert result.status == expected_status


def test_render_program_uses_operator_symbols() -> None:
    cells = (rpn16.lit(2), rpn16.lit(1), rpn16.op("+"), rpn16.op("="))
    assert rpn16.render_program(cells) == "2,1,+,="


def test_encoding_helpers_reject_invalid_values() -> None:
    with pytest.raises(ValueError):
        rpn16.lit(0x8000)

    with pytest.raises(ValueError):
        rpn16.op("^")
