"""Sloupek (P6.15, návrh ``docs/p6-15-sloupek.md``).

Válcový sloupek (podpěra pro šroub, desku plošných spojů, distanční sloupek) vede od zadané
roviny **až k tělesu**: z válce se odečte těleso a ponechají se jen kusy, které začínají na
startovní kružnici. Volitelný otvor se vrtá **jen do sloupku**, těleso pod ním zůstane celé.

Sloupek musí na tělese opravdu končit: kus, který by přečníval přes okraj těla nebo se těla
nedotýká, se odmítne s českou radou – žádná tichá náhrada.
"""

from __future__ import annotations

import math
from typing import Any

from build123d import Compound, Cylinder, Part, Plane, Pos, Vector, Vertex

DIRECTIONS = ("normal", "reverse")
FEATURE_KEYS = {"id", "type", "name", "plane", "offset", "positions", "diameter",
                "hole_diameter", "hole_depth", "direction"}
MAX_POSITIONS = 100
MIN_WALL = 0.2  # mm, nejtenčí stěna sloupku kolem otvoru


class BossError(ValueError):
    """Český důvod odmítnutí sloupku."""


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate(feature: dict[str, Any]) -> None:
    """Kontrola struktury zapsaného prvku (bez vyhodnocení výrazů a bez dílu)."""
    unknown = set(feature) - FEATURE_KEYS
    if unknown:
        raise BossError("Sloupek: neznámý klíč " + ", ".join(sorted(map(str, unknown))) + ".")
    positions = feature.get("positions")
    if not isinstance(positions, list) or not 1 <= len(positions) <= MAX_POSITIONS:
        raise BossError(f"Sloupek potřebuje 1 až {MAX_POSITIONS} poloh [x, y] („positions“).")
    for point in positions:
        if not isinstance(point, (list, tuple)) or len(point) != 2 \
                or any(isinstance(v, bool) or not isinstance(v, (int, float, str))
                       for v in point):
            raise BossError("Každá poloha sloupku musí být dvojice [x, y].")
    if feature.get("direction", "reverse") not in DIRECTIONS:
        raise BossError("Směr sloupku („direction“) musí být „normal“ nebo „reverse“.")
    for key in ("diameter", "hole_diameter", "hole_depth"):
        value = feature.get(key)
        if value is not None and (isinstance(value, bool)
                                  or not isinstance(value, (int, float, str))):
            raise BossError(f"„{key}“ musí být číslo nebo výraz.")
    if "diameter" not in feature:
        raise BossError("Sloupek potřebuje průměr („diameter“).")


def build(plane: Plane, body: Part, positions: list[tuple[float, float]], diameter: float,
          hole_diameter: float | None, hole_depth: float | None, direction: str) -> Part:
    """Sloupky z ``positions`` (souřadnice v rovině ``plane``) až k tělesu ``body``.

    ``direction`` ``reverse`` vede sloupek proti normále roviny (u roviny XY dolů), ``normal``
    po normále. ``hole_diameter`` vyvrtá otvor jen do sloupku, ``hole_depth`` omezí jeho hloubku
    (bez hodnoty vede celým sloupkem).
    """
    if direction not in DIRECTIONS:
        raise BossError("Směr sloupku musí být „normal“ nebo „reverse“.")
    if not _number(diameter) or not math.isfinite(diameter) or diameter <= 0:
        raise BossError(f"Průměr sloupku musí být větší než 0 (je {diameter:g}).")
    if hole_diameter is not None:
        if not _number(hole_diameter) or not math.isfinite(hole_diameter) or hole_diameter <= 0:
            raise BossError("Průměr otvoru musí být větší než 0.")
        if hole_diameter > diameter - 2 * MIN_WALL:
            raise BossError(f"Otvor Ø{hole_diameter:g} je pro sloupek Ø{diameter:g} moc velký – "
                            f"kolem otvoru musí zůstat stěna aspoň {MIN_WALL:g} mm.")
    if hole_depth is not None and (not _number(hole_depth) or not math.isfinite(hole_depth)
                                   or hole_depth <= 0):
        raise BossError("Hloubka otvoru musí být větší než 0.")

    box = body.bounding_box()
    center = box.center()
    sign = -1.0 if direction == "reverse" else 1.0
    axis_vector = plane.z_dir * sign
    starts = [plane.from_local_coords((x, y)) for x, y in positions]
    reach = box.diagonal + max((p - center).length for p in starts) + 1.0

    pieces: list[Any] = []
    for index, start in enumerate(starts, start=1):
        post = _cylinder(start, axis_vector, diameter / 2, reach)
        free = post - body
        kept = []
        for piece in free.solids():
            if piece.distance_to(_point(start)) > 1e-4:
                continue  # kus za tělesem – nezačíná na startovní kružnici
            depth = max(((v.center() - start).dot(axis_vector)) for v in piece.vertices())
            if depth > reach - 1e-3:
                raise BossError(
                    f"Sloupek {index} přečnívá přes okraj tělesa – pod ním není materiál, "
                    "na který by se opřel. Posuň ho nad materiál.")
            if piece.distance_to(body) > 1e-4:
                raise BossError(f"Sloupek {index} se tělesa nedotýká – je moc daleko od "
                                "materiálu nebo vede na špatnou stranu. Zkus druhý směr.")
            kept.append(piece)
        if not kept:
            raise BossError(f"Sloupek {index} nic nepřidal – startovní poloha leží v materiálu "
                            "nebo za ním. Změň rovinu, polohu nebo směr.")
        for piece in kept:
            if hole_diameter is not None:
                length = reach if hole_depth is None else hole_depth
                hole = _cylinder(start, axis_vector, hole_diameter / 2, length)
                piece = piece - hole
                if not piece.solids():
                    raise BossError(f"Otvor u sloupku {index} sloupek celý odebral – zmenši "
                                    "průměr otvoru.")
            pieces.append(piece)
    solids = [solid for piece in pieces for solid in piece.solids()]
    return Part(Compound(solids).wrapped)


def _point(vector: Vector) -> Vertex:
    return Vertex(vector.X, vector.Y, vector.Z)


def _cylinder(start: Vector, axis: Vector, radius: float, length: float) -> Part:
    """Válec od bodu ``start`` ve směru ``axis`` dlouhý ``length`` s osou ve ``start``."""
    plane = Plane(origin=start, z_dir=axis)
    return plane * Pos(0, 0, length / 2) * Cylinder(radius, length)
