"""Výběr kliknutím ve 3D → popis významem (ochrana proti topological naming problem).

Okno pošle plochy a hrany, na které uživatel klikl. Tady se z nich udělá popis,
který platí i po změně rozměrů: místo „hrana č. 7“ třeba
``{"between": ["front", "right"]}`` (svislá hrana vpravo vpředu) nebo
``{"face": "top", "radius": 3}`` (kružnice děr na horní ploše).

Popis hran se vždy ověří: musí vybrat přesně ty hrany, na které se klikalo.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

from build123d import Edge, Face, GeomType, Part, Vector
from build123d.topology.shape_core import downcast

from skodacad.selectors import (
    FACE_DIRECTIONS,
    FACE_NAMES_CZ,
    SelectionError,
    edge_axis,
    face_edges,
    face_plane,
    select_edges,
    select_faces,
)

_TOLERANCE = 1e-6
_ON_EDGE = 1e-5  # mm – bod leží na hraně
_EDGE_TYPE_NAMES = {GeomType.LINE: "line", GeomType.CIRCLE: "circle"}


@dataclass(frozen=True)
class FaceReference:
    """Kde leží rovina skici pro kliknutou plochu."""

    plane: str  # pojmenovaná plocha dílu (top, front …), jejíž směr plocha má
    offset: float  # posun od ní (0 = přímo ta plocha, záporné = hlouběji v dílu)
    point: tuple[float, float]  # místo kliknutí v souřadnicích skici


def split_shapes(shapes: list[Any]) -> tuple[list[Face], list[Edge]]:
    """Kliknuté tvary z prohlížeče (TopoDS) → plochy a hrany build123d, bez opakování."""
    faces: list[Face] = []
    edges: list[Edge] = []
    for shape in shapes:
        topods = getattr(shape, "wrapped", shape)
        try:
            specific = downcast(topods)
        except Exception:  # noqa: BLE001 – neznámý druh tvaru (vrchol …) se ignoruje
            continue
        kind = type(specific).__name__
        if kind == "TopoDS_Face":
            face = Face(specific)
            if face not in faces:
                faces.append(face)
        elif kind == "TopoDS_Edge":
            edge = Edge(specific)
            if edge not in edges:
                edges.append(edge)
    return faces, edges


# --- hrany ---------------------------------------------------------------------------


def edge_selector(part: Part, edges: list[Edge]) -> Any:
    """Nejjednodušší popis, který vybere přesně hrany ``edges`` dílu ``part``.

    Výsledek je ``"all"``, jeden objekt (např. ``{"face": "top"}``) nebo seznam
    objektů, když jeden popis nestačí.
    """
    targets = _part_edges(part, edges)
    if not targets:
        raise SelectionError("Nejsou vybrané žádné hrany – klikni na hranu ve 3D.")
    all_edges = list(part.edges())
    if len(targets) == len(all_edges):
        return "all"

    named = _named_face_edges(part)
    remaining = list(targets)
    chosen: list[Any] = []
    tried: list[Any] = []
    covers: list[tuple[Any, list[Edge]]] = []
    for edge in targets:
        for spec in _candidates(edge, named):
            if spec in tried:
                continue
            tried.append(spec)
            matched = _matches(part, spec)
            if matched and all(m in targets for m in matched):
                covers.append((spec, matched))

    while remaining:
        best = max(
            covers,
            key=lambda cover: (sum(1 for m in cover[1] if m in remaining), -len(cover[0])),
            default=None,
        )
        if best is None or not any(m in remaining for m in best[1]):
            # Pojistka: jednotlivé hrany vždy popíše „nejbližší k bodu“.
            for edge in remaining:
                chosen.append(_exact_spec(edge, named))
            break
        chosen.append(best[0])
        remaining = [edge for edge in remaining if edge not in best[1]]

    result: Any = chosen[0] if len(chosen) == 1 else chosen
    found = _matches(part, result)
    if len(found) != len(targets) or not all(edge in targets for edge in found):
        result = [_exact_spec(edge, named) for edge in targets]
    return result


def map_edges(edges: list[Edge], target: Part) -> list[Edge]:
    """Najde hrany ``edges`` (z jiného stavu dílu) v dílu ``target``.

    Hrana může být v ``target`` delší (pozdější zaoblení ji zkrátilo) – stačí,
    aby její střed ležel na hraně stejného druhu.
    """
    mapped: list[Edge] = []
    for edge in edges:
        middle = edge.position_at(0.5)
        match = next((other for other in target.edges() if _same_curve(edge, other)
                      and other.distance_to(middle) < _ON_EDGE), None)
        if match is None:
            raise SelectionError(
                "Vybraná hrana v místě tohoto prvku ještě neexistuje (vznikla až později "
                "ve stromu). Vyber jinou hranu, nebo přidej nový prvek z výběru."
            )
        if match not in mapped:
            mapped.append(match)
    return mapped


def _part_edges(part: Part, edges: list[Edge]) -> list[Edge]:
    """Hrany dílu odpovídající kliknutým (kontrola, že k dílu opravdu patří)."""
    own = list(part.edges())
    result: list[Edge] = []
    for edge in edges:
        match = next((other for other in own if other == edge), None)
        if match is None:
            raise SelectionError("Vybraná hrana nepatří k aktuálnímu dílu – vyber ji znovu.")
        if match not in result:
            result.append(match)
    return result


def _named_face_edges(part: Part) -> dict[str, list[Edge]]:
    named = {}
    for name in FACE_DIRECTIONS:
        try:
            named[name] = face_edges(part, name)
        except SelectionError:
            continue
    return named


def _matches(part: Part, spec: Any) -> list[Edge]:
    try:
        return select_edges(part, spec, float)
    except SelectionError:
        return []


def _number(value: float, decimals: int) -> float | int:
    rounded = round(value, decimals) + 0.0  # + 0.0 odstraní „-0.0“
    return int(rounded) if rounded.is_integer() else rounded


def _radius(edge: Edge) -> float | int:
    radius = _number(edge.radius, 4)
    if abs(radius - edge.radius) > _TOLERANCE * max(1.0, edge.radius):
        radius = _number(edge.radius, 9)
    return radius


def _candidates(edge: Edge, named: dict[str, list[Edge]]) -> list[dict[str, Any]]:
    """Možné popisy hrany od nejobecnějšího; vybere se ten, který nic nepřidá navíc."""
    faces = [name for name, edges in named.items() if edge in edges]
    kind = _EDGE_TYPE_NAMES.get(edge.geom_type)
    axis = edge_axis(edge)
    radius = _radius(edge) if kind == "circle" else None

    specs: list[dict[str, Any]] = [{"face": name} for name in faces]
    if axis:
        specs.append({"parallel": axis})
    if radius is not None:
        specs.append({"radius": radius})
    if kind:
        specs.append({"type": kind})
    for name in faces:
        if axis:
            specs.append({"face": name, "parallel": axis})
        if radius is not None:
            specs.append({"face": name, "radius": radius})
        if kind:
            specs.append({"face": name, "type": kind})
    specs.extend({"between": [a, b]} for a, b in itertools.combinations(faces, 2))
    return specs


def _exact_spec(edge: Edge, named: dict[str, list[Edge]]) -> dict[str, Any]:
    """Popis jedné hrany: co o ní víme + nejbližší k jejímu středu."""
    spec: dict[str, Any] = {}
    faces = [name for name, edges in named.items() if edge in edges]
    if faces:
        spec["face"] = faces[0]
    axis = edge_axis(edge)
    if axis:
        spec["parallel"] = axis
    elif edge.geom_type == GeomType.CIRCLE:
        spec["radius"] = _radius(edge)
    middle = edge.position_at(0.5)
    spec["near"] = [_number(middle.X, 3), _number(middle.Y, 3), _number(middle.Z, 3)]
    return spec


def _same_curve(edge: Edge, other: Edge) -> bool:
    if edge.geom_type != other.geom_type:
        return False
    if edge.geom_type == GeomType.LINE:
        return abs(abs(edge.tangent_at(0).dot(other.tangent_at(0))) - 1) < _TOLERANCE
    if edge.geom_type == GeomType.CIRCLE:
        return abs(edge.radius - other.radius) < _ON_EDGE
    return True


# --- plochy ----------------------------------------------------------------------------


def face_direction(face: Face) -> str:
    """Pojmenovaný směr (top, front …), kterým míří rovinná plocha – jinak SelectionError."""
    if face.geom_type != GeomType.PLANE:
        raise SelectionError(
            "Vybraná plocha je zakřivená – skicovat a otevírat jde jen rovinné plochy."
        )
    normal = face.normal_at()
    for name, (direction, _x_dir) in FACE_DIRECTIONS.items():
        if normal.dot(Vector(*direction)) > 1 - _TOLERANCE:
            return name
    raise SelectionError(
        "Vybraná plocha je šikmá – zatím jde použít jen plochy kolmé k ose X, Y nebo Z."
    )


def face_reference(part: Part, face: Face, point: Any = None) -> FaceReference:
    """Rovina skici na kliknuté rovinné ploše.

    Vnější plocha dílu (nejvyšší, nejpřednější …) dostane přímo své jméno
    (``top``). Plocha uvnitř (dno kapsy, schod) dostane jméno směru a posun
    od vnější plochy, např. ``top`` s posunem −5.
    """
    name = face_direction(face)
    direction = Vector(*FACE_DIRECTIONS[name][0])
    outer = face_plane(part, name)
    offset = _number(face.center().dot(direction) - outer.origin.dot(direction), 4)
    plane = outer.offset(offset) if offset else outer
    where = Vector(*point) if point is not None else face.center()
    local = plane.to_local_coords(where)
    return FaceReference(name, offset, (_number(local.X, 1), _number(local.Y, 1)))


def open_face_name(part: Part, face: Face) -> str:
    """Jméno vnější plochy pro skořepinu (otevřená strana) – jinak SelectionError.

    Porovnává se poloha, ne totožnost: plocha smí pocházet i z pozdějšího stavu dílu.
    """
    name = face_direction(face)
    direction = Vector(*FACE_DIRECTIONS[name][0])
    outer = max(other.center().dot(direction) for other in select_faces(part, name))
    if abs(face.center().dot(direction) - outer) > 1e-4:
        raise SelectionError(
            f"Otevřít jde jen vnější plochy dílu – vybraná plocha míří ven jako "
            f"{FACE_NAMES_CZ[name]}, ale není to krajní {FACE_NAMES_CZ[name]} plocha."
        )
    return name
