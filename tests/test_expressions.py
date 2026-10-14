import math

import pytest

from skodacad.expressions import ExpressionError, evaluate, resolve_parameters


def test_numbers_and_arithmetic():
    assert evaluate(18, {}) == 18.0
    assert evaluate("2 * (3 + 4) - 1", {}) == 13.0
    assert evaluate("D/2 - 5", {"D": 100}) == 45.0
    assert evaluate("-x ** 2", {"x": 3}) == -9.0


def test_functions_use_degrees():
    assert evaluate("sin(30)", {}) == pytest.approx(0.5)
    assert evaluate("sqrt(16) + pi", {}) == pytest.approx(4 + math.pi)
    assert evaluate("max(a, b)", {"a": 1, "b": 7}) == 7.0


def test_parameters_may_reference_each_other_in_any_order():
    params = resolve_parameters({"k": "D - 40", "D": 165, "r": "k / 2"})
    assert params == {"k": 125.0, "D": 165.0, "r": 62.5}


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("D +", "chybný zápis"),
        ("X * 2", "neznámý parametr „X“"),
        ("1 / 0", "dělí nulou"),
        ("__import__('os')", "nepovolenou konstrukci"),
        ("open('soubor')", "nepovolenou konstrukci"),
        ("(1).__class__", "nepovolenou konstrukci"),
        ("sqrt(-1)", "nejde spočítat"),
        (True, "logickou hodnotu"),
        ([1, 2], "Očekávám číslo"),
    ],
)
def test_errors_are_readable_and_nothing_unsafe_runs(value, message):
    with pytest.raises(ExpressionError, match=message):
        evaluate(value, {"D": 10})


def test_huge_power_fails_instead_of_freezing():
    with pytest.raises(ExpressionError):
        evaluate("9 ** 9 ** 9", {})


def test_parameter_cycle_is_reported():
    with pytest.raises(ExpressionError, match="v kruhu: a → b → a"):
        resolve_parameters({"a": "b + 1", "b": "a + 1"})


def test_invalid_parameter_name():
    with pytest.raises(ExpressionError, match="nelze použít"):
        resolve_parameters({"pi": 3})
