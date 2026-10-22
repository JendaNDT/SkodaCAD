"""Výběr kliknutím ve 3D → popis významem (ochrana proti topological naming problem).

Okno pošle plochy a hrany, na které uživatel klikl. Tady se z nich udělá popis,
který platí i po změně rozměrů: místo „hrana č. 7“ třeba
``{"between": ["front", "right"]}`` (svislá hrana vpravo vpředu) nebo
``{"face": "top", "radius": 3}`` (kružnice děr na horní ploše).

Popis hran se vždy ověří: musí vybrat přesně ty hrany, na které se klikalo.
"""

from __future__ import annotations

import itertools
import math
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
    face_plane_at,
    find_face,
    select_edges,
    select_faces,
    unique_shapes,
)

_TOLERANCE = 1e-6
_ON_EDGE = 1e-5  # mm – bod leží na hraně
_ON_FACE = 1e-6  # mm – zachovaná mez přenosu plochy z řezu
_EDGE_TYPE_NAMES = {GeomType.LINE: "line", GeomType.CIRCLE: "circle"}


@dataclass(frozen=True)
class FaceReference:
    """Kde leží rovina skici pro kliknutou plochu."""

    plane: Any  # pojmenovaná plocha (top, front …), nebo {"at", "normal"} u šikmé/zakřivené
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
    all_edges = unique_shapes(part.edges())
    if len(targets) == len(all_edges):
        if not _same_edges(_matches(part, "all"), targets):
            raise SelectionError("Vybrané hrany nelze jednoznačně popsat – vyber je znovu.")
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
    if not _same_edges(found, targets):
        result = [_exact_spec(edge, named, decimals=9) for edge in targets]
        if not _same_edges(_matches(part, result), targets):
            raise SelectionError("Vybrané hrany nelze jednoznačně popsat – upřesni výběr "
                                 "nebo vyber jinou hranu ve 3D.")
    return result


def _same_edges(found: list[Edge], targets: list[Edge]) -> bool:
    return len(found) == len(targets) and all(
        any(edge.is_same(target) for target in targets) for edge in found)


def map_edges(edges: list[Edge], target: Part) -> list[Edge]:
    """Najde hrany ``edges`` (z jiného stavu dílu) v dílu ``target``.

    Původní hrana smí být delší, ale musí obsahovat celý vybraný úsek/oblouk.
    Pro jinou křivku je bez totožnosti bezpečným výsledkem odmítnutí.
    """
    mapped: list[Edge] = []
    own = unique_shapes(target.edges())
    for edge in unique_shapes(edges):
        same = [other for other in own if edge.is_same(other)]
        if not same and edge.geom_type not in (GeomType.LINE, GeomType.CIRCLE):
            raise SelectionError("Vybraná obecná křivka nemá prokázaný protějšek – samotný "
                                 "stejný druh křivky nestačí. Vyber jinou hranu nebo řez vypni.")
        try:
            matches = same or [other for other in own if _contains_edge(other, edge)]
        except Exception:  # noqa: BLE001 – bez důkazu nelze výběr bezpečně přenést
            raise SelectionError("Vybranou hranu nelze v tomto stavu dílu bezpečně ověřit. "
                                 "Vyber jinou hranu nebo řez vypni.") from None
        if not matches:
            raise SelectionError(
                "Vybraná hrana v místě tohoto prvku ještě neexistuje (vznikla až později "
                "ve stromu). Vyber jinou hranu, nebo přidej nový prvek z výběru."
            )
        if len(matches) != 1:
            raise SelectionError("Vybraná hrana má v tomto stavu dílu více protějšků "
                                 "a není jednoznačná – vyber jinou hranu nebo řez vypni.")
        match = matches[0]
        if match not in mapped:
            mapped.append(match)
    return mapped


def _part_edges(part: Part, edges: list[Edge]) -> list[Edge]:
    """Hrany dílu odpovídající kliknutým (kontrola, že k dílu opravdu patří)."""
    own = unique_shapes(part.edges())
    result: list[Edge] = []
    for edge in edges:
        match = next((other for other in own if other.is_same(edge)), None)
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


def _exact_spec(edge: Edge, named: dict[str, list[Edge]], decimals: int = 3) -> dict[str, Any]:
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
    spec["near"] = [_number(v, decimals) for v in middle]
    return spec


def _contains_edge(target: Edge, source: Edge) -> bool:
    if source.geom_type != target.geom_type:
        return False
    if source.geom_type == GeomType.LINE:
        return (abs(abs(source.tangent_at(0).dot(target.tangent_at(0))) - 1) < _TOLERANCE
                and all(target.distance_to(point) < _ON_EDGE
                        for point in (source.start_point(), source.end_point())))
    if source.geom_type != GeomType.CIRCLE:
        return False
    if ((source.arc_center - target.arc_center).length >= _ON_EDGE
            or abs(source.radius - target.radius) >= _ON_EDGE
            or abs(abs(source.normal().dot(target.normal())) - 1) >= _TOLERANCE):
        return False
    if target.is_closed:
        return True
    if source.is_closed:
        return False
    # Souvislý úhlový interval celého oblouku, nikoli několik vzorkovaných bodů.
    radial = (target.start_point() - target.arc_center).normalized()
    tangent = target.tangent_at(0)
    start = source.start_point() - target.arc_center
    angle = math.atan2(start.dot(tangent), start.dot(radial)) % math.tau
    forward = -radial * math.sin(angle) + tangent * math.cos(angle)
    sign = 1 if source.tangent_at(0).dot(forward) > 0 else -1
    end = angle + sign * source.length / source.radius
    low, high = sorted((angle, end))
    tolerance = _ON_EDGE / target.radius
    extent = target.length / target.radius
    return any(low + turn * math.tau >= -tolerance
               and high + turn * math.tau <= extent + tolerance for turn in (-1, 0, 1))


def map_faces(faces: list[Face], target: Part) -> list[Face]:
    """Celý vybraný fragment → jediná původní plocha, při nejistotě odmítnout."""
    own = unique_shapes(target.faces())
    mapped: list[Face] = []
    for face in unique_shapes(faces):
        same = [other for other in own if face.is_same(other)]
        try:
            matches = same or [other for other in own if _contains_face(other, face)]
        except Exception:  # noqa: BLE001 – neověřený průnik nesmí určit protějšek
            raise SelectionError("Vybranou plochu nelze bezpečně přenést na původní díl. "
                                 "Vyber jinou plochu nebo řez vypni.") from None
        if len(matches) != 1:
            problem = ("nemá žádný doložený protějšek" if not matches
                       else f"má {len(matches)} protějšky a není jednoznačná")
            raise SelectionError(f"Vybraná plocha {problem} v původním dílu. "
                                 "Vyber jinou plochu nebo řez vypni.")
        if not any(matches[0].is_same(known) for known in mapped):
            mapped.append(matches[0])
    return mapped


def _contains_face(target: Face, source: Face) -> bool:
    from build123d import Vertex
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.collections import List_TopoDS_Shape
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    from skodacad.measure import inner_point

    if not _same_surface(target, source):
        return False
    point = inner_point(source)
    distance, on_target, _ = target.distance_to_with_closest_points(Vertex(point))
    if (distance > _ON_FACE
            or target.normal_at(on_target).dot(source.normal_at(point)) < 1 - _TOLERANCE):
        return False
    # Rozdíl musí být prázdný i ve zbytku plochy. Žádné zvětšování tolerance ani
    # změna vstupních TShape: tato operace slouží pouze jako důkaz obsažení.
    operation = BRepAlgoAPI_Cut()
    operation.SetNonDestructive(True)
    arguments, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
    arguments.Append(source.wrapped)
    tools.Append(target.wrapped)
    operation.SetArguments(arguments)
    operation.SetTools(tools)
    operation.Build()
    if not operation.IsDone():
        raise ValueError("Obsažení plochy se nepodařilo ověřit.")
    remainder = operation.Shape()
    if remainder.IsNull() or not BRepCheck_Analyzer(remainder).IsValid():
        raise ValueError("Rozdíl ploch není ověřený platný tvar.")
    return not TopExp_Explorer(remainder, TopAbs_FACE).More()


def _xyz(value: Any) -> Vector:
    return Vector(value.X(), value.Y(), value.Z())


def _same_axis(left: Any, right: Any) -> bool:
    direction = _xyz(left.Direction())
    offset = _xyz(left.Location()) - _xyz(right.Location())
    return (abs(direction.dot(_xyz(right.Direction()))) >= 1 - _TOLERANCE
            and offset.cross(direction).length <= _ON_FACE)


def _same_surface(target: Face, source: Face) -> bool:
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    kind = source.geom_type
    if kind != target.geom_type:
        return False
    left, right = BRepAdaptor_Surface(source.wrapped), BRepAdaptor_Surface(target.wrapped)
    if kind == GeomType.PLANE:
        a, b = left.Plane(), right.Plane()
        return (abs(_xyz(a.Axis().Direction()).dot(_xyz(b.Axis().Direction()))) >= 1 - _TOLERANCE
                and a.Contains(b.Location(), _ON_FACE))
    if kind == GeomType.CYLINDER:
        a, b = left.Cylinder(), right.Cylinder()
        return abs(a.Radius() - b.Radius()) <= _ON_FACE and _same_axis(a.Axis(), b.Axis())
    if kind == GeomType.SPHERE:
        a, b = left.Sphere(), right.Sphere()
        return (abs(a.Radius() - b.Radius()) <= _ON_FACE
                and (_xyz(a.Location()) - _xyz(b.Location())).length <= _ON_FACE)
    if kind == GeomType.CONE:
        a, b = left.Cone(), right.Cone()
        return (abs(a.SemiAngle()) == abs(b.SemiAngle())  # při nejistotě konzervativně odmítnout
                and (_xyz(a.Apex()) - _xyz(b.Apex())).length <= _ON_FACE
                and _same_axis(a.Axis(), b.Axis()))
    if kind == GeomType.TORUS:
        a, b = left.Torus(), right.Torus()
        return (abs(a.MajorRadius() - b.MajorRadius()) <= _ON_FACE
                and abs(a.MinorRadius() - b.MinorRadius()) <= _ON_FACE
                and (_xyz(a.Location()) - _xyz(b.Location())).length <= _ON_FACE
                and _same_axis(a.Axis(), b.Axis()))
    return False  # shoda obecného typu ani jediného bodu neprokazuje stejný nosič


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
    """Rovina skici na kliknuté ploše.

    Vnější plocha dílu (nejvyšší, nejpřednější …) dostane přímo své jméno
    (``top``). Plocha uvnitř (dno kapsy, schod) dostane jméno směru a posun
    od vnější plochy, např. ``top`` s posunem −5. Šikmá nebo zakřivená plocha dostane
    ``{"at": místo kliknutí, "normal": směr plochy v něm}`` – skica leží na ní, u
    zakřivené na rovině, která se jí v místě kliknutí dotýká (počátek skici = místo kliknutí).
    """
    if not any(face.is_same(known) for known in part.faces()):
        raise SelectionError("Kliknutá plocha nepatří k aktuálnímu dílu – vyber ji znovu.")
    try:
        name = face_direction(face)
    except SelectionError:
        return _face_reference_at(part, face, point)
    direction = Vector(*FACE_DIRECTIONS[name][0])
    outer = face_plane(part, name)
    offset = _number(face.center().dot(direction) - outer.origin.dot(direction), 4)
    plane = outer.offset(offset) if offset else outer
    where = Vector(*point) if point is not None else face.center()
    local = plane.to_local_coords(where)
    return FaceReference(name, offset, (_number(local.X, 1), _number(local.Y, 1)))


def _face_reference_at(part: Part, face: Face, point: Any) -> FaceReference:
    from build123d import Vertex

    where = Vector(*point) if point is not None else face.position_at(0.5, 0.5)
    _, on_face, _ = face.distance_to_with_closest_points(Vertex(where))
    normal = face.normal_at(on_face)
    spec = {"at": [_number(v, 4) for v in on_face], "normal": [_number(v, 4) for v in normal]}
    found, _ = find_face(part, spec)
    if not found.is_same(face):
        raise SelectionError("Kliknutá plocha nepatří k aktuálnímu dílu nebo ji nelze "
                             "jednoznačně popsat – vyber ji znovu.")
    plane = face_plane_at(part, spec)  # ověřit: najde se plocha znovu?
    if (plane.origin - on_face).length > 1e-3:
        raise SelectionError("Tuhle plochu nejde pro skicu jednoznačně určit – klikni kousek "
                             "dál od hrany.")
    return FaceReference(spec, 0.0, (0.0, 0.0))


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
