"""Sémantický výběr ploch a hran.

Plochy a hrany se NIKDY nevybírají pořadovým číslem („hrana č. 7“), protože
po změně rozměru jádro čísluje topologii jinak (tzv. topological naming
problem). Výběr se popisuje významem: „hrany horní plochy, které jsou
kružnicí o poloměru D/2“. Takový popis platí i po změně parametrů.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from build123d import Axis, Edge, Face, GeomType, Part, Plane, Shape, Vector

# Směr vnější normály a osa X skici pro každou pojmenovanou plochu.
# Osa X skici je volená tak, aby souřadnice skici odpovídaly pohledu na plochu zvenku.
FACE_DIRECTIONS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "top": ((0, 0, 1), (1, 0, 0)),
    "bottom": ((0, 0, -1), (1, 0, 0)),
    "front": ((0, -1, 0), (1, 0, 0)),
    "back": ((0, 1, 0), (-1, 0, 0)),
    "right": ((1, 0, 0), (0, 1, 0)),
    "left": ((-1, 0, 0), (0, -1, 0)),
}

FACE_NAMES_CZ = {
    "top": "horní",
    "bottom": "spodní",
    "front": "přední",
    "back": "zadní",
    "right": "pravá",
    "left": "levá",
}

BASE_PLANES = {"XY": Plane.XY, "XZ": Plane.XZ, "YZ": Plane.YZ}

_AXES = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}
_EDGE_TYPES = {"line": GeomType.LINE, "circle": GeomType.CIRCLE}
_EDGE_KEYS = {"face", "between", "type", "parallel", "radius", "near"}
_TOLERANCE = 1e-6
_DISTANCE_TIE = 1e-4  # mm; nerozlišitelnost kandidátů, nikoli mez posunu odkazu
_Shape = TypeVar("_Shape", Edge, Face)


class SelectionError(ValueError):
    """Výběr je vadný, chybí nebo není jednoznačný (zpráva je česky)."""


class MissingSelectionError(SelectionError):
    """Platný předpis nemá žádný geometrický protějšek."""


class AmbiguousSelectionError(SelectionError):
    """Předpis pro jedno místo má více nerozlišitelných protějšků."""


def _check_face_name(name: Any) -> str:
    if not isinstance(name, str) or name not in FACE_DIRECTIONS:
        allowed = ", ".join(FACE_DIRECTIONS)
        raise SelectionError(f"Neznámá plocha „{name}“, povolené jsou: {allowed}.")
    return name


def unique_shapes(shapes: Iterable[_Shape]) -> list[_Shape]:
    """Jen opakovaný výskyt téhož tvaru; shodná geometrie jiné identity se neslučuje."""
    result: list[_Shape] = []
    for shape in shapes:
        if not any(shape.is_same(known) for known in result):
            result.append(shape)
    return result


def _entities(owner: Any, shapes: Iterable[_Shape]) -> list[_Shape]:
    # Zamčené build123d Shape.faces/edges už vracejí jedinečné nativní entity.
    # Cizí výčet/adaptér a sjednocení více výběrů dál ověřujeme přes is_same.
    # Žádná nová cache ani trvalý index; neopakovat kvadratický průchod nativním seznamem.
    return list(shapes) if isinstance(owner, Shape) else unique_shapes(shapes)


def _number(value: Any, evaluate: Callable[[Any], float], label: str) -> float:
    try:
        number = evaluate(value)
        if isinstance(value, bool) or isinstance(number, bool):
            raise ValueError
        number = float(number)
        if not math.isfinite(number):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise SelectionError(f"„{label}“ musí být konečné číslo nebo platný výraz.") from None
    return number


def _point(value: Any, evaluate: Callable[[Any], float], label: str) -> Vector:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise SelectionError(f"„{label}“ musí být bod [x, y, z].")
    return Vector(*(_number(v, evaluate, label) for v in value))


def select_faces(part: Part, name: str) -> list[Face]:
    """Všechny rovinné plochy s vnější normálou ve směru ``name``, které leží nejdál."""
    direction = Vector(*FACE_DIRECTIONS[_check_face_name(name)][0])
    candidates = [
        face
        for face in _entities(part, part.faces())
        if face.geom_type == GeomType.PLANE and face.normal_at().dot(direction) > 1 - _TOLERANCE
    ]
    if not candidates:
        raise MissingSelectionError(f"Díl nemá žádnou rovinnou {FACE_NAMES_CZ[name]} plochu.")
    extreme = max(face.center().dot(direction) for face in candidates)
    return [face for face in candidates if abs(face.center().dot(direction) - extreme) < 1e-4]


def face_plane(part: Part, name: str) -> Plane:
    """Rovina skici na pojmenované ploše dílu; souřadnice skici jsou globální."""
    normal, x_dir = FACE_DIRECTIONS[_check_face_name(name)]
    level = max(face.center().dot(Vector(*normal)) for face in select_faces(part, name))
    origin = Vector(*normal) * level
    return Plane(origin=origin, x_dir=x_dir, z_dir=normal)


def face_plane_at(part: Part, spec: Any) -> Plane:
    """Rovina skici na ploše dílu u bodu – i šikmé nebo zakřivené.

    ``spec`` je ``{"at": [x, y, z], "normal": [nx, ny, nz]}``: místo kliknutí na ploše
    a směr plochy v něm (rozhodne, když je bod na hraně mezi dvěma plochami). Plocha se
    pozná podle polohy a směru, ne podle čísla, takže přežije změnu parametrů.

    * rovinná (i šikmá) plocha → skica leží přímo na ní,
    * zakřivená plocha (válec, kužel, koule …) → rovina, která se plochy v bodě dotýká.

    Počátek skici je v místě kliknutí. Osa X skici míří u válce a kužele podél jeho osy,
    jinak vodorovně po ploše (u vodorovné plochy podél osy X dílu).
    """
    face, on_face = find_face(part, spec)
    at = _point(spec["at"], float, "at")
    normal = face.normal_at(on_face)
    if face.geom_type == GeomType.PLANE:  # šikmá plocha: počátek = bod promítnutý na ni
        origin = at - normal * (at - on_face).dot(normal)
    else:
        origin = on_face
    x_dir = _sketch_x_dir(face, normal)
    return Plane(origin=origin, x_dir=x_dir, z_dir=normal)


FACE_TYPES = {"plane": GeomType.PLANE, "cylinder": GeomType.CYLINDER, "cone": GeomType.CONE,
              "sphere": GeomType.SPHERE, "torus": GeomType.TORUS}
_ROUND_TYPES = (GeomType.CYLINDER, GeomType.SPHERE)  # plochy s jedním poloměrem


def find_face(part: Part, spec: Any) -> tuple[Face, Vector]:
    """Plocha dílu podle bodu a směru → (plocha, nejbližší bod na ní).

    ``spec`` je ``{"at": [x, y, z], "normal": [nx, ny, nz]}``, nepovinně i ``"type"``
    (``plane``, ``cylinder`` …) a ``"radius"``. Hledá se plocha nejbližší bodu ``at``;
    na hraně mezi plochami rozhodne směr. S ``type`` se hledá jen mezi plochami toho druhu
    a se zadaným ``radius`` jen mezi stejně velkými. Rovnocenné kandidáty odmítne;
    jde o geometrický předpis v aktuálním dílu, nikoli trvalou identitu plochy.
    """
    if not isinstance(spec, dict) or "at" not in spec:
        raise SelectionError("Plocha musí mít „at“: [x, y, z] (a „normal“).") from None
    unknown = set(spec) - {"at", "normal", "type", "radius"}
    if unknown:
        raise SelectionError("Neznámý klíč v odkazu na plochu: "
                             + ", ".join(sorted(map(str, unknown))) + ".")
    at = _point(spec["at"], float, "at")
    hint = Vector(0, 0, 0)
    if "normal" in spec:
        raw = _point(spec["normal"], float, "normal")
        length = math.hypot(*raw)
        if not math.isfinite(length) or length == 0:
            raise SelectionError("„normal“ musí být konečný nenulový směr [nx, ny, nz].")
        hint = Vector(*(v / length for v in raw))
    kind = None
    if "type" in spec:
        name = spec["type"]
        if not isinstance(name, str) or name not in FACE_TYPES:
            raise SelectionError(f"Neznámý typ plochy „{name}“, povolené: "
                                 + ", ".join(FACE_TYPES) + ".")
        kind = FACE_TYPES[name]
    radius = None
    if "radius" in spec:
        radius = _number(spec["radius"], float, "radius")
        if radius <= 0 or kind not in _ROUND_TYPES:
            raise SelectionError("„radius“ musí být kladný poloměr plochy cylinder nebo sphere.")
    from build123d import Vertex

    faces = _entities(part, part.faces())
    if kind is not None:
        faces = [face for face in faces if face.geom_type == kind]
        if radius is not None:
            faces = [face for face in faces
                     if abs(face.radius - radius) < _TOLERANCE * max(1, radius)]
        if kind == GeomType.PLANE and hint.length > 0:  # rovina se pozná hlavně podle směru
            faces = [face for face in faces
                     if face.normal_at().dot(hint) > 1 - _TOLERANCE]
    found = []
    for face in faces:
        distance, on_face, _ = face.distance_to_with_closest_points(Vertex(at))
        found.append((distance, face, on_face))
    if not found:
        raise MissingSelectionError(f"Plocha u bodu [{_short(at)}] už na dílu není – vyber ji "
                                    "znovu ve 3D.")
    nearest = min(distance for distance, _, _ in found)
    close = [(face, on_face) for distance, face, on_face in found
             if distance <= nearest + _DISTANCE_TIE]
    scored = [(face.normal_at(point).dot(hint), face, point) for face, point in close]
    best = max(score for score, _, _ in scored)
    winners = [(face, point) for score, face, point in scored if score >= best - _TOLERANCE]
    if len(winners) != 1:
        raise AmbiguousSelectionError(
            f"Plocha u bodu [{_short(at)}] není jednoznačná: popisu odpovídá "
            f"{len(winners)} stejně vhodných ploch. Vyber ji znovu ve 3D kousek dál od hrany.")
    face, on_face = winners[0]
    normal = face.normal_at(on_face)
    loose = kind in _ROUND_TYPES or kind == GeomType.CONE  # díra pozná se podle druhu a velikosti
    if hint.length > 0 and not loose and normal.dot(hint.normalized()) < 0.5:
        raise MissingSelectionError(f"Plocha u bodu [{_short(at)}] už na dílu není (nejbližší "
                                    "plocha míří jinam) – vyber ji znovu ve 3D.")
    return face, on_face


def _sketch_x_dir(face: Face, normal: Vector) -> Vector:
    """Osa X skici na ploše: podél osy válce/kužele, jinak vodorovně po ploše."""
    direction = None
    if face.geom_type in (GeomType.CYLINDER, GeomType.CONE):
        from OCP.BRepAdaptor import BRepAdaptor_Surface

        surface = BRepAdaptor_Surface(face.wrapped)
        axis = (surface.Cylinder() if face.geom_type == GeomType.CYLINDER
                else surface.Cone()).Axis().Direction()
        direction = Vector(axis.X(), axis.Y(), axis.Z())
    else:
        direction = Vector(0, 0, 1).cross(normal)
    direction = direction - normal * direction.dot(normal)  # do roviny skici
    if direction.length < 1e-6:  # vodorovná plocha – podél osy X dílu
        direction = Vector(1, 0, 0) - normal * normal.X
    direction = direction.normalized()
    largest = max((direction.X, direction.Y, direction.Z), key=abs)
    return -direction if largest < 0 else direction  # vždy ke kladným souřadnicím


def _short(point: Vector) -> str:
    return "; ".join(f"{round(v, 1):g}" for v in (point.X, point.Y, point.Z))


def describe_plane(plane: Any) -> str:
    """Rovina skici česky (pro formulář a hlášky)."""
    if isinstance(plane, dict):
        try:
            return f"plocha vybraná ve 3D (u bodu {_short(Vector(*plane['at']))})"
        except (KeyError, TypeError, ValueError):
            return "plocha vybraná ve 3D"
    if plane in FACE_NAMES_CZ:
        return f"{FACE_NAMES_CZ[plane]} plocha dílu"
    return f"rovina {plane}"


def select_edges(part: Part, spec: Any, evaluate: Callable[[Any], float]) -> list[Edge]:
    """Hrany podle popisu ``spec``.

    ``spec`` je ``"all"``, objekt s nepovinnými klíči, nebo seznam takových objektů
    (pak se vezmou hrany všech popisů dohromady):

    * ``face``: jen hrany pojmenované plochy (``top``, ``bottom``, ``front`` …)
    * ``between``: dvě pojmenované plochy – jen hrany, které leží na obou
      (např. ``["front", "right"]`` = svislá hrana vpravo vpředu)
    * ``type``: ``line`` (úsečka) nebo ``circle`` (kružnice/oblouk)
    * ``parallel``: jen úsečky rovnoběžné s osou ``X``, ``Y`` nebo ``Z``
    * ``radius``: jen kružnice s tímto poloměrem (číslo nebo výraz)
    * ``near``: bod ``[x, y, z]`` – z hran, které zbydou, jen ta nejbližší k bodu
      (rozliší třeba jednu ze čtyř stejných děr)
    """
    specs = _edge_specs(spec, evaluate)
    if len(specs) == 1:
        return _select_edges(part, specs[0])  # již jedinečný výsledek; žádné sjednocení
    edges: list[Edge] = []
    for item in specs:
        _add_unique(edges, _select_edges(part, item))
    return edges


def _edge_specs(spec: Any, evaluate: Callable[[Any], float]) -> list[dict[str, Any]]:
    """Nejdřív ověřit a vyčíslit celý předpis; geometrie nesmí maskovat vadný vstup."""
    if isinstance(spec, list):
        if not spec:
            raise SelectionError("Seznam výběrů hran je prázdný.")
        result = []
        for item in spec:
            if isinstance(item, list):
                raise SelectionError("Seznam výběrů hran nesmí obsahovat další seznam.")
            result.extend(_edge_specs(item, evaluate))
        return result
    if spec == "all":
        spec = {}
    if not isinstance(spec, dict):
        raise SelectionError('Výběr hran musí být "all" nebo objekt, např. {"face": "top"}.')
    unknown = set(spec) - _EDGE_KEYS
    if unknown:
        raise SelectionError(
            f"Neznámý klíč ve výběru hran: {', '.join(sorted(map(str, unknown)))} "
            f"(povolené: {', '.join(sorted(_EDGE_KEYS))})."
        )

    spec = dict(spec)
    if "face" in spec:
        _check_face_name(spec["face"])
    if "between" in spec:
        names = spec["between"]
        if not isinstance(names, list) or len(names) != 2:
            raise SelectionError('„between“ musí být dvě plochy, např. ["front", "right"].')
        for name in names:
            _check_face_name(name)
    if "type" in spec:
        name = spec["type"]
        if not isinstance(name, str) or name not in _EDGE_TYPES:
            raise SelectionError(f"Typ hrany „{name}“ neznám, povolené: line, circle.")
    if "parallel" in spec:
        name = spec["parallel"]
        if not isinstance(name, str) or name not in _AXES:
            raise SelectionError(f"Osa „{name}“ neexistuje, povolené: X, Y, Z.")
    if "radius" in spec:
        spec["radius"] = _number(spec["radius"], evaluate, "radius")
        if spec["radius"] <= 0:
            raise SelectionError("„radius“ musí být kladný poloměr hrany.")
    if "near" in spec:
        spec["near"] = list(_point(spec["near"], evaluate, "near"))
    return [spec]


def _select_edges(part: Part, spec: dict[str, Any]) -> list[Edge]:
    edges = face_edges(part, spec["face"]) if "face" in spec else _entities(part, part.edges())
    if "between" in spec:
        names = spec["between"]
        first, second = (face_edges(part, name) for name in names)
        edges = [edge for edge in edges
                 if any(edge.is_same(e) for e in first) and any(edge.is_same(e) for e in second)]

    if "type" in spec:
        edges = [edge for edge in edges if edge.geom_type == _EDGE_TYPES[spec["type"]]]

    if "parallel" in spec:
        edges = [edge for edge in edges if edge_axis(edge) == spec["parallel"]]

    if "radius" in spec:
        radius = spec["radius"]
        edges = [
            edge
            for edge in edges
            if edge.geom_type == GeomType.CIRCLE
            and abs(edge.radius - radius) <= _TOLERANCE * max(1.0, radius)
        ]

    if "near" in spec and edges:
        target = Vector(*spec["near"])
        distances = [(edge.distance_to(target), edge) for edge in edges]
        nearest = min(distance for distance, _ in distances)
        edges = [edge for distance, edge in distances if distance <= nearest + _DISTANCE_TIE]
        if len(edges) != 1:
            raise AmbiguousSelectionError("Výběr hrany není jednoznačný: stejně blízko jsou "
                                          f"{len(edges)} hrany. Upřesni výběr nebo ji vyber "
                                          "znovu ve 3D.")

    if not edges:
        described = json.dumps(spec, ensure_ascii=False) if spec else '"all"'
        raise MissingSelectionError(f"Výběr hran {described} nenašel žádnou hranu.")
    return edges


def face_edges(part: Part, name: str) -> list[Edge]:
    """Hrany pojmenované plochy (všech jejích kusů, bez opakování)."""
    edges: list[Edge] = []
    for face in select_faces(part, name):
        _add_unique(edges, face.edges())
    return edges


def edge_axis(edge: Edge) -> str | None:
    """Osa X/Y/Z, se kterou je úsečka rovnoběžná, jinak None."""
    if edge.geom_type != GeomType.LINE:
        return None
    tangent = edge.tangent_at(0)
    for name, axis in _AXES.items():
        if abs(abs(tangent.dot(axis.direction)) - 1) < _TOLERANCE:
            return name
    return None


def _add_unique(edges: list[Edge], new: list[Edge]) -> None:
    for edge in new:
        if not any(edge.is_same(known) for known in edges):
            edges.append(edge)


# Tvary pro české věty: „na horní ploše“, „mezi přední a pravou plochou“.
_FACE_LOCATIVE = {"top": "horní", "bottom": "spodní", "front": "přední", "back": "zadní",
                  "right": "pravé", "left": "levé"}
_FACE_INSTRUMENTAL = {"top": "horní", "bottom": "spodní", "front": "přední", "back": "zadní",
                      "right": "pravou", "left": "levou"}


def describe_edges(spec: Any) -> str:
    """Výběr hran česky, např. „hrany na horní ploše, kružnice R3“."""
    if isinstance(spec, list):
        return "; ".join(describe_edges(item) for item in spec)
    if spec == "all" or spec == {}:
        return "všechny hrany"
    if not isinstance(spec, dict):
        return str(spec)
    parts = []
    if "between" in spec and isinstance(spec["between"], list) and len(spec["between"]) == 2:
        first, second = (_FACE_INSTRUMENTAL.get(name, str(name)) for name in spec["between"])
        parts.append(f"hrana mezi {first} a {second} plochou")
    else:
        parts.append({"line": "úsečky", "circle": "kružnice"}.get(spec.get("type"), "hrany"))
    if "face" in spec:
        parts.append(f"na {_FACE_LOCATIVE.get(spec['face'], spec['face'])} ploše")
    if "parallel" in spec:
        parts.append(f"rovnoběžné s osou {spec['parallel']}")
    if "radius" in spec:
        parts.append(f"poloměr {spec['radius']}")
    if "near" in spec and isinstance(spec["near"], list):
        parts.append("nejbližší k bodu [" + "; ".join(str(v) for v in spec["near"]) + "]")
    return " ".join(parts[:1]) + (" " + ", ".join(parts[1:]) if len(parts) > 1 else "")
