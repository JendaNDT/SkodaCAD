"""Přejmenování přesných odkazů v receptu sestavy, bez změny zápisu okolního výrazu."""

from __future__ import annotations

import ast
import keyword
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from skodacad.assembly import Assembly, AssemblyError
from skodacad.expressions import CONSTANTS, FUNCTIONS


def check_parameter_name(name: str) -> None:
    if (not isinstance(name, str) or not name.isidentifier() or keyword.iskeyword(name)
            or name in CONSTANTS or name in FUNCTIONS
            or unicodedata.normalize("NFKC", name) != name):
        raise AssemblyError(f"„{name}“ nelze použít jako název parametru. "
                            "Zadej například roztec nebo mezera_vicka.")


def rename_expression(value: Any, old: str, new: str, place: str) -> Any:
    """AST určí jména; UTF-8 rozsahy nahradí jen tokeny, nikoli komentáře či podřetězce."""
    if not isinstance(value, str) or old == new:
        return value
    source = value.strip()
    try:
        nodes = list(ast.walk(ast.parse(source, mode="eval")))
    except (SyntaxError, ValueError):
        raise AssemblyError(f"{place}: výraz „{value}“ nejde přečíst. "
                            "Nejprve jej oprav; název se nezměnil.") from None
    callees = {node.func for node in nodes if isinstance(node, ast.Call)}
    prefix = len(value[:len(value)-len(value.lstrip())].encode("utf-8"))
    # Python počítá řádky podle CR/LF; např. svislý tabulátor v komentáři není nový řádek.
    starts = [prefix, *[prefix + match.end()
                        for match in re.finditer(rb"\r\n?|\n", source.encode("utf-8"))]]
    spans = [(starts[node.lineno-1] + node.col_offset,
              starts[node.end_lineno-1] + node.end_col_offset)
             for node in nodes if isinstance(node, ast.Name) and node.id == old
             and node not in callees]
    content = value.encode("utf-8")
    for start, end in sorted(spans, reverse=True):
        content = content[:start] + new.encode("utf-8") + content[end:]
    return content.decode("utf-8")


def rename_parameters(parameters: Mapping[str, Any], old: str, new: str) -> dict[str, Any]:
    check_parameter_name(new)
    if old not in parameters:
        raise AssemblyError(f"Parametr „{old}“ se v tabulce nenašel.")
    if old != new and new in parameters:
        raise AssemblyError(f"Parametr „{new}“ už existuje. Zvol jiný název; "
                            "nic se nepřejmenovalo.")
    return {new if name == old else name:
            rename_expression(value, old, new, f"Parametr „{name}“")
            for name, value in parameters.items()}


def rename_references(assembly: Assembly, old: str, new: str) -> None:
    """Přepisuje jen pracovní kopii. Vnitřní soubory ani popisy/id se neupravují."""
    check_parameter_name(new)
    for component in assembly.components:
        for attribute in ("position", "rotation"):
            values = getattr(component, attribute)
            setattr(component, attribute, [
                rename_expression(value, old, new, f"Poloha komponenty „{component.label}“")
                for value in values])
    for constraint in assembly.constraints:
        if constraint.type == "distance":
            constraint.value = rename_expression(constraint.value, old, new,
                                                 f"Vzdálenost vazby „{constraint.label}“")
