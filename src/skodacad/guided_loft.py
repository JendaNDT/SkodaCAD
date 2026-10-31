"""Řízený plný přechod: dvě XY obdélníková čela, čtyři kubická vodítka.

Stejný parametr z=H*t pro všechna vodítka. Každý vodorovný průřez je
čtyřúhelník. Kladnost jeho čtyř orientovaných součinů po celém intervalu
se ověřuje Bernsteinovými mezemi a dělením de Casteljau, nikoli vzorky.
Neprůkazný případ se odmítá. Podrobnosti a číselné rezervy: docs/p6-7-rizeny-prechod.md.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from build123d import Compound, Face, GeomType, Location, Part, Plane, Shell, Solid, Vector

from skodacad.geometry_validation import inspect_volume

CORNERS = ((1, 1), (-1, 1), (-1, -1), (1, -1))  # geometrické X/Y, obvod proti hodinám
LABELS = ("A · X+ Y+", "B · X− Y+", "C · X− Y−", "D · X+ Y−")
LENGTH_TOL = 1e-6
REL_MARGIN = 1e-10
MAX_DEPTH = 18
MAX_NODES = 4096


class GuidedLoftError(ValueError):
    """Český důvod odmítnutí vstupu nebo geometrie."""


def default_guides() -> list[dict]:
    return [{"corner": {"x": x, "y": y}, "controls": [[0, 0], [0, 0]]} for x, y in CORNERS]


def _finite(value) -> bool:
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def validate(feature: dict, evaluate: Callable | None = None) -> dict:
    """Stejná strukturální kontrola při čtení JSON i přímém přepočtu; beze změny vstupů."""
    sketches = feature.get("sketches")
    if (not isinstance(sketches, list) or len(sketches) != 2
            or any(not isinstance(s, str) or not s for s in sketches)
            or sketches[0] == sketches[1]):
        raise GuidedLoftError("Řízený přechod potřebuje právě dvě různé obdélníkové skici.")
    if any(key in feature for key in ("wall", "wall_mode", "ruled")):
        raise GuidedLoftError("Řízený přechod zatím vytváří plné těleso bez volby stěny "
                              "a bez přepínače rovných stěn.")
    if "operation" in feature and feature["operation"] not in ("new", "add", "cut"):
        raise GuidedLoftError("Operace řízeného přechodu musí být new, add nebo cut.")
    guides = feature.get("guides")
    if not isinstance(guides, list) or len(guides) != 4:
        raise GuidedLoftError("Řízený přechod potřebuje čtyři rohová vodítka.")
    result = {}
    for guide in guides:
        if not isinstance(guide, dict) or set(guide) != {"corner", "controls"}:
            raise GuidedLoftError("Vodítko musí mít „corner“ a dvě rukojeti „controls“.")
        corner = guide["corner"]
        if (not isinstance(corner, dict) or set(corner) != {"x", "y"}
                or any(type(corner[k]) is not int or corner[k] not in (-1, 1) for k in corner)):
            raise GuidedLoftError("Roh vodítka urči znaménky x/y: 1 nebo −1.")
        key = (corner["x"], corner["y"])
        if key in result:
            raise GuidedLoftError("Každý roh smí mít právě jedno vodítko – jeden roh se opakuje.")
        controls = guide["controls"]
        if (not isinstance(controls, list) or len(controls) != 2
                or any(not isinstance(p, list) or len(p) != 2 for p in controls)):
            raise GuidedLoftError("Každé vodítko potřebuje dvě rukojeti [posun X, posun Y].")
        values = []
        for p in controls:
            coords = []
            for value in p:
                if (type(value) not in (int, float, str)
                        or isinstance(value, str) and not value.strip()
                        or isinstance(value, int | float) and not _finite(value)):
                    raise GuidedLoftError("Posun rukojeti musí být konečné číslo nebo výraz.")
                number = evaluate(value) if evaluate is not None else value
                if evaluate is not None and not math.isfinite(number):
                    raise GuidedLoftError("Posun rukojeti není konečné číslo – uprav výraz.")
                coords.append(number)
            values.append(tuple(coords))
        result[key] = tuple(values)
    return result


@dataclass(frozen=True)
class Geometry:
    origin: tuple[float, float, float]
    poles: tuple[tuple[tuple[float, float, float], ...], ...]  # místní XY vůči prvnímu čelu
    widths: tuple[float, float]
    heights: tuple[float, float]
    height: float
    center_delta: tuple[float, float]

    def world(self, p) -> tuple[float, float, float]:
        return tuple(a + b for a, b in zip(self.origin, p, strict=True))


def _rectangle(plane, sketch) -> tuple[float, float, float, float, float]:
    if (Vector(plane.z_dir).dot(Vector(0, 0, 1)) < 1 - 1e-12
            or Vector(plane.x_dir).dot(Vector(1, 0, 0)) < 1 - 1e-12):
        raise GuidedLoftError("Řízený přechod zatím potřebuje skici v rovinách XY "
                              "se souhlasnými osami a druhou skicu výše.")
    faces = list(sketch.faces())
    if (len(faces) != 1 or faces[0].inner_wires() or len(faces[0].edges()) != 4
            or any(e.geom_type != GeomType.LINE for e in faces[0].edges())):
        raise GuidedLoftError("Řízený přechod potřebuje obdélníkové profily bez děr a zaoblení.")
    if not faces[0].is_valid:
        raise GuidedLoftError("Profil řízeného přechodu není platný obdélník.")
    for edge in faces[0].edges():
        a, b = edge.position_at(0), edge.position_at(1)
        if abs(a.X-b.X) > LENGTH_TOL and abs(a.Y-b.Y) > LENGTH_TOL:
            raise GuidedLoftError("Strany profilu musí být rovnoběžné s osami X/Y skici.")
    vertices = list(faces[0].vertices())
    if len(vertices) != 4:
        raise GuidedLoftError("Profil nemá čtyři jednoznačné rohy obdélníku.")
    xmin, xmax = min(v.X for v in vertices), max(v.X for v in vertices)
    ymin, ymax = min(v.Y for v in vertices), max(v.Y for v in vertices)
    width, height = xmax - xmin, ymax - ymin
    if not all(math.isfinite(v) for v in (xmin, xmax, ymin, ymax, width, height)):
        raise GuidedLoftError("Rozměry profilu jsou příliš velké – zmenši je.")
    if min(width, height) <= 10 * LENGTH_TOL:
        raise GuidedLoftError("Obdélník je pro řízený přechod příliš úzký – zvětši profil.")
    for x in (xmin, xmax):
        for y in (ymin, ymax):
            if sum(math.dist((v.X, v.Y, v.Z), (x, y, 0)) < LENGTH_TOL for v in vertices) != 1:
                raise GuidedLoftError("Strany profilu musí být rovnoběžné s osami X/Y skici.")
    cx, cy = xmin + width/2 + plane.origin.X, ymin + height/2 + plane.origin.Y
    return cx, cy, plane.origin.Z, width, height


def prepare(feature: dict, sketches: dict, evaluate: Callable) -> Geometry:
    handles = validate(feature, evaluate)
    profiles = []
    for sid in feature["sketches"]:
        if sid not in sketches:
            raise GuidedLoftError(f"Skica „{sid}“ neexistuje nebo je až za řízeným přechodem.")
        profiles.append(_rectangle(*sketches[sid]))
    a, b = profiles
    height = b[2] - a[2]
    if not math.isfinite(height) or height <= 10 * LENGTH_TOL:
        raise GuidedLoftError("Druhá skica řízeného přechodu musí být výše než první – "
                              "zvětši její posun roviny nebo změň pořadí skic.")
    delta = (b[0]-a[0], b[1]-a[1])
    poles = []
    for sx, sy in CORNERS:
        start, end = (sx*a[3]/2, sy*a[4]/2, 0.), (delta[0]+sx*b[3]/2, delta[1]+sy*b[4]/2, height)
        controls = [start]
        for k, offsets in zip((1, 2), handles[(sx, sy)], strict=True):
            controls.append((start[0] + (end[0]-start[0])*k/3 + offsets[0],
                             start[1] + (end[1]-start[1])*k/3 + offsets[1], height*k/3))
        controls.append(end)
        poles.append(tuple(controls))
    data = Geometry(tuple(a[:3]), tuple(poles), (a[3], b[3]), (a[4], b[4]), height, delta)
    coords = [v for rail in data.poles for p in rail for v in data.world(p)]
    if not all(math.isfinite(v) and math.ulp(v) * 16 < LENGTH_TOL for v in coords):
        raise GuidedLoftError("Souřadnice vodítek jsou příliš velké pro přesné spojení – "
                              "zmenši posuny a přesuň díl blíž k počátku.")
    return data


def point(poles, t: float) -> tuple[float, float, float]:
    return tuple(math.fsum(math.comb(3, i)*t**i*(1-t)**(3-i)*poles[i][j]
                           for i in range(4)) for j in range(3))


def _difference(a, b):
    return [(b[i][0]-a[i][0], b[i][1]-a[i][1]) for i in range(4)]


def _cross(a, b) -> list[float]:
    # Součin dvou kubických Bernsteinových polynomů v bázi stupně šest.
    return [math.fsum(math.comb(3, i)*math.comb(3, k-i)/math.comb(6, k)
                      * (a[i][0]*b[k-i][1] - a[i][1]*b[k-i][0])
                      for i in range(max(0, k-3), min(3, k)+1)) for k in range(7)]


def _positive(coeffs: list[float], margin: float) -> bool:
    pending = [(coeffs, 0)]
    nodes = 0
    while pending:
        values, depth = pending.pop()
        nodes += 1
        if min(values) > margin:
            continue  # celá konvexní obálka koeficientů leží nad rezervou
        if max(values) <= margin or depth >= MAX_DEPTH or nodes > MAX_NODES:
            return False  # záporné nebo neprokázané; nejistota nikdy není přijetí
        left, right = [values[0]], [values[-1]]
        while len(values) > 1:
            values = [(a+b)/2 for a, b in zip(values, values[1:], strict=False)]
            left.append(values[0])
            right.append(values[-1])
        pending.extend(((left, depth+1), (list(reversed(right)), depth+1)))
    return True


def checked_volume(data: Geometry) -> float:
    """Konzervativní mez konvexity po celé výšce a nezávislý integrál objemu."""
    edges = [_difference(data.poles[i], data.poles[(i+1) % 4]) for i in range(4)]
    scale = max(abs(v) for edge in edges for p in edge for v in p)
    if not math.isfinite(scale) or scale <= LENGTH_TOL:
        raise GuidedLoftError("Vodítka tvoří nerozlišitelný průřez – zvětši profil.")
    normalized = [[(x/scale, y/scale) for x, y in edge] for edge in edges]
    margin = max(REL_MARGIN, LENGTH_TOL/scale * (LENGTH_TOL/scale))
    if any(not _positive(_cross(normalized[i], normalized[(i+1) % 4]), margin)
           for i in range(4)):
        raise GuidedLoftError("Vodítka se kříží, zužují průřez nebo nelze prokázat jeho "
                              "konvexitu – zmenši posuny rukojetí.")
    diagonals = [_difference(data.poles[0], data.poles[i]) for i in (1, 2, 3)]
    a, b, c = [[(x/scale, y/scale) for x, y in d] for d in diagonals]
    area = math.fsum((*_cross(a, b), *_cross(b, c))) / 14
    volume = ((area * scale) * data.height) * scale
    if not math.isfinite(volume) or volume <= 0:
        raise GuidedLoftError("Objem řízeného přechodu nelze přesně vyhodnotit – zmenši rozměry.")
    return volume


def build(data: Geometry) -> Part:
    expected = checked_volume(data)
    try:
        faces = [Face.make_bezier_surface([data.poles[i], data.poles[(i+1) % 4]])
                 for i in range(4)]
        caps = [Face.make_rect(data.widths[0], data.heights[0]),
                Face.make_rect(data.widths[1], data.heights[1],
                               Plane(origin=(*data.center_delta, data.height)))]
        # Vlastní čela z čísel: sešívání nesmí upravit sdílené skici přepočtu.
        candidate = Solid(Shell([*faces, *caps]))
        facts = inspect_volume(candidate)
        if facts.solids != 1 or abs(facts.volume-expected) > max(2e-5, expected*1e-8):
            raise ValueError("objem nesouhlasí s integrálem průřezů")
        final_faces = list(candidate.faces())
        for i, rail in enumerate(data.poles):
            for t in (0, .25, .5, .75, 1):
                p = Vector(point(rail, t))
                if min(face.distance_to(p) for face in final_faces) > LENGTH_TOL:
                    raise ValueError("výsledek nezachoval vodítko")
            for u in (.2, .5, .8):
                for t in (.2, .5, .8):
                    a, b = point(rail, t), point(data.poles[(i+1) % 4], t)
                    p = Vector(tuple((1-u)*x+u*y for x, y in zip(a, b, strict=True)))
                    if min(face.distance_to(p) for face in final_faces) > LENGTH_TOL:
                        raise ValueError("výsledek nezachoval analytický plášť")
        return Part(Compound([candidate.moved(Location(data.origin))]).wrapped)
    except Exception as exc:  # noqa: BLE001 -- žádná náhradní geometrie při selhání jádra
        raise GuidedLoftError("Řízený přechod se nepodařilo spojit do ověřeného tělesa – "
                              "zmenši posuny rukojetí nebo rozměry profilů.") from exc
