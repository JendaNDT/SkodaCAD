"""Odkazy na parametry této úrovně sestavy, bez přepočtu a bez čtení zdrojových dílů."""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from skodacad.assembly import Assembly


@dataclass(frozen=True)
class ParameterUse:
    place: str
    field: str
    expression: Any
    via: tuple[str, ...] = ()


@dataclass(frozen=True)
class UsageReport:
    uses: tuple[ParameterUse, ...]
    warnings: tuple[str, ...]


def parameter_usage(assembly: Assembly | None, parameters: Mapping[str, Any],
                    name: str) -> UsageReport:
    """Každé místo jednou; při více cestách nejkratší (shoda podle názvu, ne podřetězce).

    Výrazy parametrů pocházejí z pracovní tabulky, polohy/vazby z otevřené sestavy.
    Cyklus nezpůsobí nekonečné hledání. U nečitelného výrazu nelze tvrdit úplnost.
    """
    sites = [(f"Parametr „{key}“", "Hodnota", value) for key, value in parameters.items()]
    if assembly is not None:
        for component in assembly.components:
            place = f"Komponenta „{component.label}“ ({component.id})"
            for label, values in (("Posun", component.position), ("Otočení", component.rotation)):
                unit = "mm" if label == "Posun" else "°"
                sites += [(place, f"{label} {axis} [{unit}]", value)
                          for axis, value in zip("XYZ", values, strict=True)]
        sites += [(f"Vazba „{c.label}“ ({c.id})", "Vzdálenost [mm]", c.value)
                  for c in assembly.constraints if c.type == "distance"]

    warnings = []
    references = []
    for place, field, value in sites:
        refs = set()
        if isinstance(value, str):
            try:
                nodes = list(ast.walk(ast.parse(value.strip(), mode="eval")))
                callees = {node.func for node in nodes if isinstance(node, ast.Call)}
                refs = {node.id for node in nodes
                        if isinstance(node, ast.Name) and node not in callees}
            except (SyntaxError, ValueError):
                warnings.append(f"{place}, {field}: výraz nejde přečíst.")
        references.append(refs)

    dependencies = dict(zip(parameters, references[:len(parameters)], strict=True))
    paths: dict[str, tuple[str, ...]] = {name: ()}
    waiting = deque([name])
    while waiting:
        parent = waiting.popleft()
        for key, refs in dependencies.items():
            if parent in refs and key not in paths:
                paths[key] = (*paths[parent], key)
                waiting.append(key)

    uses = []
    for (place, field, value), refs in zip(sites, references, strict=True):
        matches = refs & paths.keys()
        if matches:
            closest = min(matches, key=lambda key: (len(paths[key]), key))
            uses.append(ParameterUse(place, field, value, paths[closest]))
    return UsageReport(tuple(uses), tuple(warnings))
