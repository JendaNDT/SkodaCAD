"""Sémantický výběr ploch a hran.

Plochy a hrany se NIKDY nevybírají pořadovým číslem („hrana č. 7“), protože
po změně rozměru jádro čísluje topologii jinak (tzv. topological naming
problem). Výběr se popisuje významem: „hrany horní plochy, které jsou
kružnicí o poloměru D/2“. Takový popis platí i po změně parametrů.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from build123d import Axis, Edge, Face, GeomType, Part, Plane, Vector

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
_EDGE_KEYS = {"face", "type", "parallel", "radius"}
_TOLERANCE = 1e-6


class SelectionError(ValueError):
    """Výběr nic nenašel nebo je chybně zapsaný (zpráva je česky)."""


def _check_face_name(name: Any) -> str:
    if name not in FACE_DIRECTIONS:
        allowed = ", ".join(FACE_DIRECTIONS)
        raise SelectionError(f"Neznámá plocha „{name}“, povolené jsou: {allowed}.")
    return name


def select_faces(part: Part, name: str) -> list[Face]:
    """Všechny rovinné plochy s vnější normálou ve směru ``name``, které leží nejdál."""
    direction = Vector(*FACE_DIRECTIONS[_check_face_name(name)][0])
    candidates = [
        face
        for face in part.faces()
        if face.geom_type == GeomType.PLANE and face.normal_at().dot(direction) > 1 - _TOLERANCE
    ]
    if not candidates:
        raise SelectionError(f"Díl nemá žádnou rovinnou {FACE_NAMES_CZ[name]} plochu.")
    extreme = max(face.center().dot(direction) for face in candidates)
    return [face for face in candidates if abs(face.center().dot(direction) - extreme) < 1e-4]


def face_plane(part: Part, name: str) -> Plane:
    """Rovina skici na pojmenované ploše dílu; souřadnice skici jsou globální."""
    normal, x_dir = FACE_DIRECTIONS[_check_face_name(name)]
    level = select_faces(part, name)[0].center().dot(Vector(*normal))
    origin = Vector(*normal) * level
    return Plane(origin=origin, x_dir=x_dir, z_dir=normal)


def select_edges(part: Part, spec: Any, evaluate: Callable[[Any], float]) -> list[Edge]:
    """Hrany podle popisu ``spec``.

    ``spec`` je buď ``"all"``, nebo objekt s nepovinnými klíči:

    * ``face``: jen hrany pojmenované plochy (``top``, ``bottom``, ``front`` …)
    * ``type``: ``line`` (úsečka) nebo ``circle`` (kružnice/oblouk)
    * ``parallel``: jen úsečky rovnoběžné s osou ``X``, ``Y`` nebo ``Z``
    * ``radius``: jen kružnice s tímto poloměrem (číslo nebo výraz)
    """
    if spec == "all":
        spec = {}
    if not isinstance(spec, dict):
        raise SelectionError('Výběr hran musí být "all" nebo objekt, např. {"face": "top"}.')
    unknown = set(spec) - _EDGE_KEYS
    if unknown:
        raise SelectionError(
            f"Neznámý klíč ve výběru hran: {', '.join(sorted(unknown))} "
            f"(povolené: {', '.join(sorted(_EDGE_KEYS))})."
        )

    if "face" in spec:
        edges: list[Edge] = []
        for face in select_faces(part, spec["face"]):
            for edge in face.edges():
                if not any(edge.is_same(known) for known in edges):
                    edges.append(edge)
    else:
        edges = list(part.edges())

    if "type" in spec:
        if spec["type"] not in _EDGE_TYPES:
            raise SelectionError(f"Typ hrany „{spec['type']}“ neznám, povolené: line, circle.")
        edges = [edge for edge in edges if edge.geom_type == _EDGE_TYPES[spec["type"]]]

    if "parallel" in spec:
        if spec["parallel"] not in _AXES:
            raise SelectionError(f"Osa „{spec['parallel']}“ neexistuje, povolené: X, Y, Z.")
        axis = _AXES[spec["parallel"]].direction
        edges = [
            edge
            for edge in edges
            if edge.geom_type == GeomType.LINE
            and abs(abs(edge.tangent_at(0).dot(axis)) - 1) < _TOLERANCE
        ]

    if "radius" in spec:
        radius = evaluate(spec["radius"])
        edges = [
            edge
            for edge in edges
            if edge.geom_type == GeomType.CIRCLE
            and abs(edge.radius - radius) <= _TOLERANCE * max(1.0, radius)
        ]

    if not edges:
        described = json.dumps(spec, ensure_ascii=False) if spec else '"all"'
        raise SelectionError(f"Výběr hran {described} nenašel žádnou hranu.")
    return edges
