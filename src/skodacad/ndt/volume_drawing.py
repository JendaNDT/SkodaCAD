"""Kresba objemového pokrytí UT (07C): povrch cíle – i rozříznutého – obarvený podle buněk 07B.

Výsledek 07B nese jen čísla každého kusu (buňka, meze, stav), žádnou geometrii. Kresba proto
vezme účinné těleso cíle (případně rozříznuté rovinou řezu – plocha řezu je pak průřez
svarem), rozdělí jeho povrch na trojúhelníky a každý rozřeže podél rovin mřížky 07B. Úlomek
leží celý v jedné buňce a dostane barvu stavu jejího kusu. Když má buňka víc kusů s různými
stavy a úlomek nejde podle mezí kusu přiřadit jednoznačně, je **šedý** („nerozlišeno
v kresbě“) – nikdy zelený. Kresba čísla výsledku nemění: barva úlomku je stav vnitřního
bodu jeho kusu (aproximace 07B), ne zásah právě toho místa.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from skodacad.ndt.coverage import COLORS
from skodacad.ndt.geometry import Point
from skodacad.ndt.volume_coverage import VolumeCoverageMap, VolumeSample
from skodacad.ndt.welds import height_direction

UNRESOLVED = "unresolved"
UNRESOLVED_LABEL = "Nerozlišeno v kresbě"
GREY = (0.62, 0.62, 0.62)
TESSELLATION_MM = 0.05  # odchylka sítě povrchu od přesné plochy
_EPS = 1e-9

Mesh = tuple[list[Point], list[tuple[int, int, int]], list[tuple[float, float, float]]]


def state_at(pieces: list[tuple[VolumeSample, str]], point: Point) -> str:
    """Stav místa ``point`` (místní souřadnice) v buňce s kusy ``pieces``: jediný kus nebo
    jediný stav rovnou, jinak kus, do jehož mezí místo padne; nejednoznačné = UNRESOLVED."""
    states = {state for _sample, state in pieces}
    if len(states) == 1:
        return states.pop()
    inside = {state for sample, state in pieces
              if sample.piece_bounds is not None
              and all(lo - 1e-6 <= v <= hi + 1e-6 for v, lo, hi in
                      zip(point, *sample.piece_bounds, strict=True))}
    return inside.pop() if len(inside) == 1 else UNRESOLVED


def _clip(polygon: list[Point], axis: int, value: float, keep_above: bool) -> list[Point]:
    """Sutherland–Hodgman pro jednu rovinu mřížky (konvexní mnohoúhelník zůstane konvexní)."""
    result: list[Point] = []
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        a_in = a[axis] >= value if keep_above else a[axis] <= value
        b_in = b[axis] >= value if keep_above else b[axis] <= value
        if a_in:
            result.append(a)
        if a_in != b_in:
            t = (value - a[axis]) / (b[axis] - a[axis])
            result.append(tuple(p + t * (q - p) for p, q in zip(a, b, strict=True)))
    return result


def _area(polygon: list[Point]) -> float:
    total = 0.0
    a = polygon[0]
    for b, c in zip(polygon[1:], polygon[2:], strict=False):
        u = [q - p for p, q in zip(a, b, strict=True)]
        v = [q - p for p, q in zip(a, c, strict=True)]
        total += math.hypot(u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
                            u[0] * v[1] - u[1] * v[0]) / 2
    return total


def volume_mesh(result: VolumeCoverageMap, shape: Any) -> Mesh:
    """Barevná síť povrchu ``shape`` (účinný cíl, případně rozříznutý) podle stavů kusů.
    Uzly úlomků se nesdílejí, barvy se proto mezi buňkami nepřelévají."""
    a = result.assumptions
    frame, low, step = a["grid_frame"], a["grid_min"], a["target_step_mm"]
    counts = [max(1, math.ceil((hi - lo) / step - 1e-12))  # jako volume_coverage.grid_extent
              for lo, hi in zip(low, a["grid_max"], strict=True)]
    origin, across, axis = frame["origin"], frame["across"], frame["axis"]
    height = height_direction(axis, across)
    directions = (across, height, axis)
    by_cell: dict[tuple[int, int, int], list[tuple[VolumeSample, str]]] = defaultdict(list)
    for sample, state in zip(result.samples, result.states, strict=True):
        by_cell[sample.cell].append((sample, state))

    def local(p: Any) -> Point:
        d = (p.X - origin[0], p.Y - origin[1], p.Z - origin[2])
        return tuple(sum(x * y for x, y in zip(d, v, strict=True)) - lo
                     for v, lo in zip(directions, low, strict=True))

    def world(q: Point) -> Point:
        shifted = [x + lo for x, lo in zip(q, low, strict=True)]
        return tuple(origin[i] + sum(c * v[i] for c, v in zip(shifted, directions, strict=True))
                     for i in range(3))

    vertices, faces = shape.tessellate(TESSELLATION_MM)
    points = [local(v) for v in vertices]
    nodes: list[Point] = []
    triangles: list[tuple[int, int, int]] = []
    colors: list[tuple[float, float, float]] = []
    for face in faces:
        triangle = [points[i] for i in face]
        ranges = []
        for k in range(3):  # buňky jen uvnitř mřížky – čelo na jejím konci patří poslední
            first = math.floor(min(p[k] for p in triangle) / step + _EPS)
            last = math.ceil(max(p[k] for p in triangle) / step - _EPS)
            first = min(max(first, 0), counts[k] - 1)
            ranges.append(range(first, min(max(first + 1, last), counts[k])))
        for i in ranges[0]:
            for j in ranges[1]:
                for k in ranges[2]:
                    piece = triangle
                    for axis_k, index in ((0, i), (1, j), (2, k)):
                        piece = _clip(piece, axis_k, index * step, True)
                        if len(piece) >= 3:
                            piece = _clip(piece, axis_k, (index + 1) * step, False)
                        if len(piece) < 3:
                            break
                    if len(piece) < 3 or _area(piece) <= 1e-12:
                        continue
                    center = tuple(sum(p[c] for p in piece) / len(piece) + low[c]
                                   for c in range(3))
                    found = by_cell.get((i, j, k))
                    state = state_at(found, center) if found else UNRESOLVED
                    color = COLORS.get(state, GREY)
                    start = len(nodes)
                    nodes += [world(p) for p in piece]
                    colors += [color] * len(piece)
                    triangles += [(start, start + n, start + n + 1)
                                  for n in range(1, len(piece) - 1)]
    return nodes, triangles, colors


def mesh_areas(mesh: Mesh) -> dict[tuple[float, float, float], float]:
    """Obsah kresby podle barvy [mm²] (kontrola kresby v testech a self-testu)."""
    nodes, triangles, colors = mesh
    areas: dict[tuple[float, float, float], float] = defaultdict(float)
    for a, b, c in triangles:
        areas[colors[a]] += _area([nodes[a], nodes[b], nodes[c]])
    return dict(areas)
