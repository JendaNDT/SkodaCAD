"""Žebro (P6.13, návrh ``docs/p6-13-zebro.md``).

Žebro je tenká stěna, kterou zadá **otevřená trasa** (lomená čára) v rovině skici a tloušťka.
Stěna vede od trasy na zvolenou stranu **až k tělesu**: tělo se od ní odečte a ponechají se jen
kusy, které začínají na trase. Kusy za tělesem (vzadu, za protější stěnou) zmizí, takže žebro
končí vždy na prvním materiálu – ve dně krabičky, ve stěně nebo v rohu mezi nimi.

Žebro musí na tělese opravdu končit: kus, který by přečníval přes okraj těla (trasa delší než
díl) nebo se těla nedotýká, se odmítne s českou radou – žádná tichá náhrada.
"""

from __future__ import annotations

import math
from typing import Any

from build123d import Compound, Part, Plane, Polygon, Sketch, Vector, extrude

SIDES = ("left", "right")
FEATURE_KEYS = {"id", "type", "name", "plane", "offset", "points", "thickness", "side"}
TOL = 1e-6
MIN_SEGMENT = 1e-3  # mm, kratší úsek trasy je chyba zadání
MIN_POINTS = 2
MAX_POINTS = 50


class RibError(ValueError):
    """Český důvod odmítnutí žebra."""


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate(feature: dict[str, Any]) -> None:
    """Kontrola struktury zapsaného prvku (bez vyhodnocení výrazů a bez dílu)."""
    unknown = set(feature) - FEATURE_KEYS
    if unknown:
        raise RibError("Žebro: neznámý klíč " + ", ".join(sorted(map(str, unknown))) + ".")
    points = feature.get("points")
    if not isinstance(points, list) or not MIN_POINTS <= len(points) <= MAX_POINTS:
        raise RibError(f"Žebro potřebuje trasu z {MIN_POINTS} až {MAX_POINTS} bodů [x, y] "
                       "(„points“).")
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2 \
                or any(isinstance(v, bool) or not isinstance(v, (int, float, str))
                       for v in point):
            raise RibError("Každý bod trasy žebra musí být dvojice [x, y].")
    if feature.get("side", "left") not in SIDES:
        raise RibError("Strana žebra („side“) musí být „left“ nebo „right“.")
    thickness = feature.get("thickness")
    if isinstance(thickness, bool) or not isinstance(thickness, (int, float, str)):
        raise RibError("Tloušťka žebra („thickness“) musí být číslo nebo výraz.")


def build(plane: Plane, body: Part, points: list[tuple[float, float]], thickness: float,
          side: str) -> Part:
    """Žebro ze zadané trasy: jen kusy stěny od trasy k tělesu ``body``.

    ``points`` jsou souřadnice v rovině ``plane`` (osa X, Y skici), stěna vede kolmo ke spojnici
    prvního a posledního bodu na stranu ``side`` (``left`` = vlevo při pohledu od prvního bodu
    k poslednímu, kladná osa Z roviny směrem k divákovi) a má tloušťku ``thickness``
    souměrně kolem roviny skici.
    """
    if side not in SIDES:
        raise RibError("Strana žebra musí být „left“ nebo „right“.")
    if not _number(thickness) or not math.isfinite(thickness) or thickness <= 0:
        raise RibError(f"Tloušťka žebra musí být větší než 0 (je {thickness:g}).")
    if len(points) < MIN_POINTS:
        raise RibError("Žebro potřebuje trasu z aspoň dvou bodů.")

    chord = (points[-1][0] - points[0][0], points[-1][1] - points[0][1])
    length = math.hypot(*chord)
    if length < MIN_SEGMENT:
        raise RibError("První a poslední bod trasy žebra jsou na stejném místě – žebro "
                       "potřebuje trasu s jasným směrem.")
    unit = (chord[0] / length, chord[1] / length)
    previous = -math.inf
    for index, (x, y) in enumerate(points, start=1):
        progress = (x - points[0][0]) * unit[0] + (y - points[0][1]) * unit[1]
        if progress - previous < MIN_SEGMENT:
            raise RibError(
                f"Bod {index} trasy žebra se vrací nebo je těsně u předchozího – trasa musí "
                "postupovat jedním směrem od prvního bodu k poslednímu.")
        previous = progress
    normal = (-unit[1], unit[0]) if side == "left" else (unit[1], -unit[0])

    box = body.bounding_box()
    center = box.center()
    world = [plane.from_local_coords((x, y)) for x, y in points]
    reach = box.diagonal + max((p - center).length for p in world) + 1.0
    far = [(x + normal[0] * reach, y + normal[1] * reach) for x, y in points]
    outline = [(float(x), float(y)) for x, y in [*points, *reversed(far)]]
    wall = extrude(plane * (Sketch() + Polygon(*outline, align=None)),
                   amount=thickness / 2, both=True)

    free = wall - body
    pieces = list(free.solids())
    if not pieces:
        raise RibError("Žebro nic nepřidalo – trasa leží celá v materiálu, nebo je za tělesem. "
                       "Posuň trasu nebo zvol druhou stranu.")

    axis_normal = plane.x_dir * normal[0] + plane.y_dir * normal[1]
    origin = world[0]
    kept = []
    for piece in pieces:
        if not _touches_route(piece, world):
            continue  # kus za tělesem – nezačíná na trase
        depth = max(((v.center() - origin).dot(axis_normal)) for v in piece.vertices())
        if depth > reach - 1e-3:
            raise RibError(
                "Žebro přečnívá přes okraj tělesa – trasa musí celá ležet nad materiálem, "
                "na který se má žebro opřít. Zkrať trasu nebo ji posuň.")
        if piece.distance_to(body) > 1e-4:
            raise RibError("Žebro se tělesa nedotýká – trasa je moc daleko od materiálu "
                           "nebo vede na špatnou stranu. Zvol druhou stranu.")
        kept.append(piece)
    if not kept:
        raise RibError("Žebro nic nepřidalo – za trasou na zvolené straně není žádný "
                       "materiál. Zvol druhou stranu.")
    return Part(Compound(kept).wrapped)


def _touches_route(piece: Any, world: list[Vector]) -> bool:
    """Kus leží na trase, když nějaká úsečka trasy protíná jeho povrch (do 1e-4 mm)."""
    from build123d import Edge
    for a, b in zip(world, world[1:], strict=False):
        if piece.distance_to(Edge.make_line(a, b)) <= 1e-4:
            return True
    return False
