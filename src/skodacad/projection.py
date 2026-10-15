"""Promítnutí hran dílu do roviny skici (skicář: vazby k dílu, převzetí obrysu).

Promítnutá hrana je v obrysu (tvar ``profile``) uložená jako odkaz::

    "references": {
      "r1": {"edge": {"between": ["top", "front"]}, "kind": "line",
             "points": [[-20, -15], [20, -15]]},
      "r2": {"edge": {"face": "top", "type": "circle"}, "kind": "circle",
             "center": [5, 3], "radius": 3}}

* ``edge`` – která hrana dílu, popsaná významem (``selectors.select_edges``) – žádné
  indexy, takže odkaz přežije změnu parametrů (topological naming problem).
* ``kind`` a souřadnice – promítnutý tvar v souřadnicích obrysu. Při každém přepočtu
  se znovu spočítají z dílu (díl se mohl změnit); uložené hodnoty jsou jen poslední stav,
  aby skicář mohl kreslit i bez dílu.

Promítnout jde úsečku (nesmí být kolmá na skicu) a kružnici či oblouk rovnoběžné se skicou.
V řešiči je promítnutá hrana pevná – k ní se dávají vazby a kóty.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from skodacad.selectors import SelectionError, select_edges
from skodacad.solver import REFERENCE_POINTS as POINTS  # noqa: F401 – body podle tvaru


class ProjectionError(ValueError):
    """Hranu nejde promítnout (zpráva česky)."""


Placement = tuple[float, float, float]  # posun x, y a natočení obrysu ve skice (center, angle)


@dataclass(frozen=True)
class Projected:
    """Promítnutá hrana v souřadnicích obrysu."""

    kind: str  # line / circle / arc (oblouk vždy proti směru hodin od start do end)
    points: tuple[tuple[float, float], ...] = ()  # line, arc: (začátek, konec)
    center: tuple[float, float] | None = None
    radius: float = 0.0
    depth: float = 0.0  # jak daleko pod rovinou skici hrana leží (bližší má přednost)

    def key(self) -> tuple:
        """Stejný tvar po promítnutí = stejný klíč (horní a spodní hrana kvádru splynou)."""
        def r(point: tuple[float, float]) -> tuple[float, float]:
            return round(point[0], 4) + 0.0, round(point[1], 4) + 0.0

        points = tuple(sorted(map(r, self.points))) if self.kind == "line" else tuple(
            map(r, self.points))
        center = r(self.center) if self.center is not None else None
        return self.kind, points, center, round(self.radius, 4)

    def as_reference(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind}
        if self.points:
            data["points"] = [[_clean(x), _clean(y)] for x, y in self.points]
        if self.center is not None:
            data["center"] = [_clean(self.center[0]), _clean(self.center[1])]
            data["radius"] = _clean(self.radius)
        return data


def _clean(value: float) -> float:
    return round(value, 6) + 0.0


def _to_profile(plane: Any, place: Placement | None) -> Callable[[Any], tuple[float, ...]]:
    """Bod v prostoru → (x, y, výška nad rovinou) v souřadnicích obrysu."""
    dx, dy, angle = place or (0.0, 0.0, 0.0)
    cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))

    def convert(point: Any) -> tuple[float, ...]:
        local = plane.to_local_coords(point)
        x, y = local.X - dx, local.Y - dy
        return x * cos + y * sin, -x * sin + y * cos, local.Z

    return convert


def project_edge(edge: Any, plane: Any, place: Placement | None = None) -> Projected | None:
    """Hrana dílu promítnutá do roviny skici, nebo None (jde jen do bodu, nebo je to
    křivka, kterou promítnout neumíme – elipsa, spline, kružnice natočená ke skice)."""
    convert = _to_profile(plane, place)
    kind = edge.geom_type.name
    if kind == "LINE":
        (ax, ay, az), (bx, by, bz) = convert(edge.start_point()), convert(edge.end_point())
        if math.dist((ax, ay), (bx, by)) < 1e-6:
            return None  # kolmá na skicu → jen bod
        return Projected("line", ((ax, ay), (bx, by)), depth=max(abs(az), abs(bz)))
    if kind != "CIRCLE":
        return None
    normal = edge.normal()
    if abs(abs(normal.dot(plane.z_dir)) - 1) > 1e-6:
        return None  # kružnice není rovnoběžná se skicou (promítla by se do elipsy)
    cx, cy, cz = convert(edge.arc_center)
    if edge.is_closed:
        return Projected("circle", center=(cx, cy), radius=edge.radius, depth=abs(cz))
    start, middle, end = (convert(p)[:2] for p in (edge.start_point(), edge.position_at(0.5),
                                                    edge.end_point()))
    turn = ((middle[0] - start[0]) * (end[1] - start[1])
            - (middle[1] - start[1]) * (end[0] - start[0]))
    if turn < 0:  # začátek → prostředek → konec po směru hodin: prohodit konce
        start, end = end, start
    return Projected("arc", (start, end), (cx, cy), edge.radius, depth=abs(cz))


def candidates(part: Any, plane: Any, place: Placement | None = None
               ) -> list[tuple[Any, Projected]]:
    """Hrany dílu, které jde do skici promítnout – každý tvar jen jednou (ta nejbližší
    ke skice), seřazené od nejbližších."""
    best: dict[tuple, tuple[Any, Projected]] = {}
    for edge in part.edges():
        projected = project_edge(edge, plane, place)
        if projected is None:
            continue
        key = projected.key()
        if key not in best or projected.depth < best[key][1].depth - 1e-9:
            best[key] = (edge, projected)
    return sorted(best.values(), key=lambda item: item[1].depth)


def reference_for(part: Any, edge: Any, plane: Any, place: Placement | None = None
                  ) -> dict[str, Any]:
    """Odkaz na promítnutou hranu: popis hrany významem + promítnutý tvar."""
    from skodacad.picking import edge_selector

    projected = project_edge(edge, plane, place)
    if projected is None:
        raise ProjectionError("Tuhle hranu do skici promítnout nejde.")
    return {"edge": edge_selector(part, [edge]), **projected.as_reference()}


def refresh(element: dict[str, Any], part: Any, plane: Any, place: Placement | None,
            evaluate: Callable[[Any], float]) -> dict[str, Any]:
    """Kopie obrysu s promítnutými hranami spočítanými znovu z dílu ``part``."""
    references = element.get("references") or {}
    if not references:
        return element
    if not isinstance(references, dict):
        raise ProjectionError("„references“ musí být objekt {jméno: promítnutá hrana}.")
    if part is None:
        raise ProjectionError("Obrys promítá hrany dílu, ale před skicou žádný díl není.")
    fresh = {}
    for name, reference in references.items():
        if not isinstance(reference, dict) or "edge" not in reference:
            raise ProjectionError(f"Promítnutá hrana „{name}“ nemá popis hrany („edge“).")
        try:
            edges = select_edges(part, reference["edge"], evaluate)
        except SelectionError:
            edges = []
        if len(edges) != 1:
            problem = ("už na dílu není" if not edges
                       else f"už není jednoznačná (popisu odpovídá {len(edges)} hran)")
            raise ProjectionError(f"Promítnutá hrana „{name}“ {problem} – díl se změnil. Ve "
                                  "skicáři ji smaž a promítni znovu.")
        projected = project_edge(edges[0], plane, place)
        if projected is None:
            raise ProjectionError(f"Promítnutou hranu „{name}“ teď nejde promítnout (není "
                                  "rovnoběžná se skicou) – ve skicáři ji smaž.")
        if reference.get("kind") not in (None, projected.kind):
            raise ProjectionError(f"Promítnutá hrana „{name}“ změnila tvar ({reference['kind']} "
                                  f"→ {projected.kind}) – ve skicáři ji smaž a promítni znovu.")
        fresh[name] = {"edge": reference["edge"], **projected.as_reference()}
    return {**element, "references": fresh}
