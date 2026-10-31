"""Lineární zaoblení jedné přímé pravoúhlé vnější hrany (P6).

Přesný řez přímkovým loftem dvou podobných čtvrtkruhových profilů. Konce musí být
rovinné a kolmé k hraně. Není to náhradní postup pro obecné zaoblení OCCT.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from build123d import Compound, Edge, GeomType, Part, Solid, Vector, Vertex, Wire

from skodacad.geometry_validation import (
    check_modification,
    inspect_volume,
    volume_tolerance,
)

TOL = 1e-6


class VariableFilletError(ValueError):
    """Český důvod odmítnutí proměnného zaoblení."""


def direction(edge: Edge) -> list[float]:
    """Stálý výchozí směr: největší složka tečny je kladná, nezávisle na OCCT."""
    if edge.geom_type != GeomType.LINE:
        raise VariableFilletError("Proměnné zaoblení umí jen jednu přímou hranu.")
    vector = edge.tangent_at(0.5).normalized()
    main = max(range(3), key=lambda i: abs(tuple(vector)[i]))
    return list(vector if tuple(vector)[main] >= 0 else -vector)


def endpoints(edge: Edge, stored: object, reverse: object = False) -> tuple[Vector, Vector]:
    if (not isinstance(stored, list) or len(stored) != 3
            or any(isinstance(v, bool) or not isinstance(v, (int, float))
                   or not math.isfinite(v) for v in stored)):
        raise VariableFilletError("Chybí platný směr hrany – vyber hranu znovu ve 3D.")
    vector = Vector(*stored)
    if vector.length < TOL or not isinstance(reverse, bool):
        raise VariableFilletError("Směr hrany nesmí být nulový; obrácení musí být ano/ne.")
    vector = vector.normalized()
    vertices = edge.vertices()
    if edge.geom_type != GeomType.LINE or len(vertices) != 2 or edge.length < TOL:
        raise VariableFilletError("Proměnné zaoblení umí jen jednu otevřenou přímou hranu.")
    a, b = sorted((v.center() for v in vertices), key=lambda p: p.dot(vector))
    if abs((b - a).normalized().dot(vector)) < 1 - TOL:
        raise VariableFilletError("Směr už neodpovídá hraně – vyber ji znovu ve 3D.")
    return (b, a) if reverse else (a, b)


def edge_origin(history: Sequence[tuple[str, Part | None]], edge: Edge) -> str | None:
    """Prvek, od kterého na nosné přímce nepřetržitě existuje právě jedna hrana."""
    point, tangent = edge.position_at(0.5), edge.tangent_at(0.5)
    found = None
    for feature_id, part in reversed(history):
        matching = [] if part is None else [e for e in part.edges()
            if e.geom_type == GeomType.LINE
            and abs(e.tangent_at(0.5).dot(tangent)) > 1 - TOL
            and e.distance_to(Vertex(point)) < TOL]
        if len(matching) != 1:
            break
        found = feature_id
    return found


def check_origin(history: Sequence[tuple[str, Part | None]], edge: Edge,
                 stored: object) -> None:
    if not isinstance(stored, str) or not stored or edge_origin(history, edge) != stored:
        raise VariableFilletError("Původ hrany se změnil nebo chybí – vyber hranu znovu ve 3D.")


def _input(part: Part, edge: Edge, start: Vector, end: Vector):
    solids = list(part.solids())
    owners = [s for s in solids if any(edge.is_same(e) for e in s.edges())]
    if len(owners) != 1:
        raise VariableFilletError("Hrana nepatří právě jednomu tělesu dílu – vyber ji znovu.")
    owner, = owners
    sides = [f for f in owner.faces() if any(edge.is_same(e) for e in f.edges())]
    if len(sides) != 2 or any(f.geom_type != GeomType.PLANE for f in sides):
        raise VariableFilletError("Hrana musí ležet mezi dvěma rovinnými boky.")
    n1, n2 = (f.normal_at() for f in sides)
    axis = (end - start).normalized()
    if abs(n1.dot(n2)) > TOL:
        raise VariableFilletError("Boky musí svírat pravý úhel (90°).")
    if max(abs(n1.dot(axis)), abs(n2.dot(axis))) > TOL:
        raise VariableFilletError("Boky nejsou rovnoběžné s hranou.")
    middle = (start + end) * 0.5
    step = max(1e-4, min(edge.length * 1e-4, 0.01))
    if (not owner.is_inside(middle - (n1 + n2) * step)
            or owner.is_inside(middle + (n1 - n2) * step)
            or owner.is_inside(middle + (n2 - n1) * step)):
        raise VariableFilletError("První verze umí jen vnější vypouklý roh, nikoli vnitřní kout.")
    for point, normal in [(start, -axis), (end, axis)]:
        caps = [f for f in owner.faces() if not any(f.is_same(s) for s in sides)
                and any((v.center() - point).length < TOL for v in f.vertices())]
        if (len(caps) != 1 or caps[0].geom_type != GeomType.PLANE
                or caps[0].normal_at().dot(normal) < 1 - TOL):
            raise VariableFilletError("Oba konce hrany musí uzavírat rovinné kolmé plochy; "
                                      "tečné řetězce a složité rohy první verze neumí.")
    return owner, [s for s in solids if not s.is_same(owner)], -n1, -n2


def _wire(point: Vector, u: Vector, v: Vector, radius: float) -> Wire:
    a, b = point + u * radius, point + v * radius
    middle = point + (u + v) * (radius * (1 - 1 / math.sqrt(2)))
    return Wire([Edge.make_line(point, a), Edge.make_three_point_arc(a, middle, b),
                 Edge.make_line(b, point)])


def reference(part: Part, edge: Edge, history: Sequence[tuple[str, Part | None]]) -> dict:
    axis = direction(edge)
    start, end = endpoints(edge, axis)
    _, _, u, v = _input(part, edge, start, end)
    origin = edge_origin(history, edge)
    if not origin:
        raise VariableFilletError("Původ hrany nelze určit – vyber jinou hranu.")
    return {"direction": axis, "origin": origin, "normals": [list(-u), list(-v)]}


def apply(part: Part, edge: Edge, start_radius: float, end_radius: float,
          stored_direction: object, reverse: object = False, normals: object = None) -> Part:
    if any(not math.isfinite(r) or r <= 0 for r in (start_radius, end_radius)):
        raise VariableFilletError("Oba poloměry musí být konečná kladná čísla.")
    start, end = endpoints(edge, stored_direction, reverse)
    before = inspect_volume(part)
    owner, others, u, v = _input(part, edge, start, end)
    try:
        if not isinstance(normals, list) or len(normals) != 2:
            raise ValueError
        stored = [Vector(*n) for n in normals if isinstance(n, list) and len(n) == 3
                  and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                          and math.isfinite(x) for x in n)]
        if (len(stored) != 2 or any(abs(n.length - 1) > TOL for n in stored)
                or not all(any(n.dot(actual) > 1 - TOL for n in stored)
                           for actual in (-u, -v))):
            raise ValueError
    except (ValueError, TypeError):
        raise VariableFilletError("Boky hrany se změnily nebo chybí jejich pojistka – "
                                  "vyber hranu znovu ve 3D.") from None
    expected = ((1 - math.pi / 4) * edge.length / 3
                * (start_radius * start_radius + start_radius * end_radius
                   + end_radius * end_radius))
    if not math.isfinite(expected) or expected >= owner.volume:
        raise VariableFilletError("Zaoblení se nevejde do rohu – zmenši poloměry.")
    if expected <= volume_tolerance(before.volume, before.volume):
        raise VariableFilletError("Zaoblení je příliš malé a nemá rozlišitelný účinek.")
    try:
        tool = Solid.make_loft([_wire(start, u, v, start_radius),
                                _wire(end, u, v, end_radius)], ruled=True)
        edited = owner - tool
        result = Part(Compound([*others, edited]).wrapped)
        facts = inspect_volume(result)
        check_modification(before, facts)
    except Exception as exc:  # noqa: BLE001 – chybu geometrického jádra předat lidsky
        raise VariableFilletError("Zaoblení se nepodařilo spočítat – zmenši poloměry "
                                  "nebo vyber jinou přímou hranu.") from exc
    tolerance = max(volume_tolerance(before.volume, facts.volume), expected * 1e-6)
    if abs(before.volume - facts.volume - expected) > tolerance:
        raise VariableFilletError("Zaoblení se nevejde do rohu nebo zasahuje do jiného "
                                  "detailu (například díry) – zmenši poloměry.")
    if len(result.faces()) != len(part.faces()) + 1:
        raise VariableFilletError("Zaoblení by změnilo sousední detail nebo odstranilo "
                                  "některou plochu – zmenši poloměry.")
    return result
