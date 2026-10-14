"""Bezpečné vyhodnocování číselných výrazů s parametry.

Hodnota v modelu může být číslo (``18``) nebo výraz (``"D/2 - 5"``).
Výrazy smí obsahovat jen čísla, názvy parametrů, základní aritmetiku
a několik matematických funkcí. Úhly v goniometrických funkcích jsou
ve stupních. Žádný jiný Python kód se nespustí.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Mapping
from typing import Any


class ExpressionError(ValueError):
    """Výraz nebo parametr nejde vyhodnotit (zpráva je česky pro uživatele)."""


_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": lambda deg: math.sin(math.radians(deg)),
    "cos": lambda deg: math.cos(math.radians(deg)),
    "tan": lambda deg: math.tan(math.radians(deg)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
}

CONSTANTS = {"pi": math.pi}


def evaluate(value: Any, params: Mapping[str, float]) -> float:
    """Vrátí číselnou hodnotu čísla nebo výrazu ``value``."""
    if isinstance(value, bool):
        raise ExpressionError(f"Očekávám číslo nebo výraz, ne logickou hodnotu {value!r}.")
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ExpressionError(f"Očekávám číslo nebo výraz, dostal jsem {value!r}.")
    try:
        tree = ast.parse(value.strip(), mode="eval")
    except SyntaxError:
        raise ExpressionError(f"Výraz „{value}“ má chybný zápis.") from None
    try:
        result = _eval_node(tree.body, params, value)
    except ZeroDivisionError:
        raise ExpressionError(f"Ve výrazu „{value}“ se dělí nulou.") from None
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, ExpressionError):
            raise
        raise ExpressionError(f"Výraz „{value}“ nejde spočítat ({exc}).") from None
    if isinstance(result, complex) or not math.isfinite(result):
        raise ExpressionError(f"Výraz „{value}“ nedává konečné reálné číslo.")
    return float(result)


def _eval_node(node: ast.AST, params: Mapping[str, float], source: str) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(
        node.value, bool
    ):
        return float(node.value)  # float: obří mocniny skončí chybou místo zamrznutí
    if isinstance(node, ast.Name):
        if node.id in params:
            return params[node.id]
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        raise ExpressionError(f"Ve výrazu „{source}“ je neznámý parametr „{node.id}“.")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left = _eval_node(node.left, params, source)
        right = _eval_node(node.right, params, source)
        return _BINARY_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand, params, source))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in FUNCTIONS
        and not node.keywords
    ):
        args = [_eval_node(arg, params, source) for arg in node.args]
        return FUNCTIONS[node.func.id](*args)
    raise ExpressionError(f"Výraz „{source}“ obsahuje nepovolenou konstrukci.")


def resolve_parameters(raw: Mapping[str, Any]) -> dict[str, float]:
    """Spočítá všechny parametry; parametry se smí odkazovat na jiné parametry."""
    resolved: dict[str, float] = {}
    in_progress: list[str] = []

    def resolve(name: str) -> float:
        if name in resolved:
            return resolved[name]
        if name in in_progress:
            cycle = " → ".join([*in_progress[in_progress.index(name) :], name])
            raise ExpressionError(f"Parametry se odkazují samy na sebe v kruhu: {cycle}.")
        in_progress.append(name)
        for dependency in _referenced_names(raw[name]):
            if dependency in raw:
                resolve(dependency)
        try:
            resolved[name] = evaluate(raw[name], resolved)
        except ExpressionError as exc:
            raise ExpressionError(f"Parametr „{name}“: {exc}") from None
        in_progress.pop()
        return resolved[name]

    for name in raw:
        if not name.isidentifier() or name in CONSTANTS or name in FUNCTIONS:
            raise ExpressionError(f"„{name}“ nelze použít jako název parametru.")
        resolve(name)
    return resolved


def _referenced_names(value: Any) -> set[str]:
    if not isinstance(value, str):
        return set()
    try:
        tree = ast.parse(value.strip(), mode="eval")
    except SyntaxError:
        return set()  # chybný zápis nahlásí až evaluate()
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
