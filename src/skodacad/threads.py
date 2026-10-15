"""Vymodelovaný vnitřní závit pro 3D tisk: šroubovicová drážka z rovinných plošek.

Proč plošky a ne „hladká“ šroubovice: tažení profilu po šroubovici i plochy napnuté mezi
šroubovicemi dávají v jádru OCCT nespolehlivé booleovské operace (díra se občas vůbec
nevyřízne, ověřeno pro M3–M30). Drážka složená z trojúhelníků je spolehlivá; plošky se
od přesného tvaru odchylují nejvýš o ``MAX_SAG`` (0,05 mm – pod rozlišením tiskárny).

Profil drážky leží v rovině osy (jako skutečný profil závitu ISO 68-1) a posouvá se
šroubovým pohybem. Boky jsou na vnitřní straně prodloužené o 0,15·P do jádra díry, aby se
drážka s vyvrtaným jádrem protínala čistě napříč, ne těsně u plochy (šířka drážky tam
zůstává pod P, sousední závity se nedotknou).
"""

from __future__ import annotations

import math
from functools import lru_cache

from build123d import Solid
from build123d.topology.shape_core import downcast
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeSolid,
    BRepBuilderAPI_MakeVertex,
    BRepBuilderAPI_MakeWire,
)
from OCP.BRepLib import BRepLib
from OCP.collections import (
    IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as EdgeFaces,
)
from OCP.GeomAbs import GeomAbs_C0, GeomAbs_C2
from OCP.gp import gp_Pnt
from OCP.ShapeFix import ShapeFix_Solid
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Shell

from skodacad.holes import ThreadProfile

MAX_SAG = 0.05  # mm – největší odchylka plošky od přesné šroubovice
MIN_STEPS, MAX_STEPS = 12, 48  # počet plošek na jednu otáčku
SMOOTH_ANGLE = 35.0  # ° – hrany mezi ploškami s menším zlomem se kreslí jako hladké


def steps_per_turn(radius: float, sag: float = MAX_SAG) -> int:
    """Kolik plošek na otáčku, aby tětiva na poloměru ``radius`` nevybočila víc než ``sag``."""
    if radius <= sag:
        return MIN_STEPS
    steps = math.ceil(math.pi / math.acos(1 - sag / radius))
    return max(MIN_STEPS, min(MAX_STEPS, steps))


INWARD = 0.15  # prodloužení boků do jádra díry (násobek stoupání)


def groove_section(profile: ThreadProfile) -> list[tuple[float, float]]:
    """Řez drážkou v rovině osy: (poloměr, posun v ose) – lichoběžník s boky 60°."""
    slope = (profile.inner_width - profile.outer_width) / 2 / (
        profile.outer_radius - profile.inner_radius)  # = tan 30°
    inward = INWARD * profile.pitch
    half = profile.inner_width / 2 + slope * inward
    inner = profile.inner_radius - inward
    wo = profile.outer_width / 2
    return [(inner, -half), (profile.outer_radius, -wo), (profile.outer_radius, wo),
            (inner, half)]


@lru_cache(maxsize=32)
def thread_groove(profile: ThreadProfile, z_start: float, z_end: float,
                  steps: int | None = None) -> Solid:
    """Drážka od ``z_start`` do ``z_end`` (osa Z, pravotočivý závit).

    Výsledek se pamatuje – při přepočtu modelu se stejná drážka nestaví znovu.
    """
    section = groove_section(profile)
    steps = steps or steps_per_turn(profile.outer_radius)
    turns = (z_end - z_start) / profile.pitch
    count = max(2, math.ceil(turns * steps))
    rings = []
    for k in range(count + 1):
        t = turns * k / count
        angle = 2 * math.pi * t
        z = z_start + profile.pitch * t
        cos, sin = math.cos(angle), math.sin(angle)
        rings.append([gp_Pnt(r * cos, r * sin, z + dz) for r, dz in section])

    # Plošky skládáme se sdílenými vrcholy a hranami – rychlejší než sešívání.
    vertices = [[BRepBuilderAPI_MakeVertex(point).Vertex() for point in ring] for ring in rings]
    edges: dict[tuple, object] = {}

    def edge(a: tuple[int, int], b: tuple[int, int]):
        key = (a, b) if a <= b else (b, a)
        if key not in edges:
            edges[key] = BRepBuilderAPI_MakeEdge(vertices[key[0][0]][key[0][1]],
                                                 vertices[key[1][0]][key[1][1]]).Edge()
        return edges[key]

    builder = BRep_Builder()
    shell = TopoDS_Shell()
    builder.MakeShell(shell)

    def face(*corners: tuple[int, int]) -> None:
        wire = BRepBuilderAPI_MakeWire()
        for a, b in zip(corners, corners[1:] + corners[:1], strict=True):
            wire.Add(edge(a, b))
        builder.Add(shell, BRepBuilderAPI_MakeFace(wire.Wire(), True).Face())

    sides = len(section)
    for k in range(count):
        for i in range(sides):
            j = (i + 1) % sides
            face((k, i), (k, j), (k + 1, j))
            face((k, i), (k + 1, j), (k + 1, i))
    face(*[(0, i) for i in range(sides)])  # rovinné konce drážky (profil v rovině osy)
    face(*[(count, i) for i in reversed(range(sides))])
    solid = BRepBuilderAPI_MakeSolid(shell).Solid()
    fix = ShapeFix_Solid(solid)  # srovná orientaci (vnějšek ven)
    fix.Perform()
    result = fix.Solid()
    _mark_facet_edges(result)
    return Solid(downcast(result))


def _mark_facet_edges(solid) -> None:
    """Hrany mezi ploškami s malým zlomem označí jako „velmi hladké“ (C2).

    Prohlížeč kreslí jen hrany do hladkosti C1, takže čáry trojúhelníků závitu zmizí,
    ale tečné hrany zaoblení (G1) i ostré hrany zůstanou vidět."""
    BRepLib.EncodeRegularity_s(solid, math.radians(SMOOTH_ANGLE))
    faces_of_edge = EdgeFaces()
    TopExp.MapShapesAndAncestors_s(solid, TopAbs_EDGE, TopAbs_FACE, faces_of_edge)
    builder = BRep_Builder()
    for index in range(1, faces_of_edge.Extent() + 1):
        faces = list(faces_of_edge.FindFromIndex(index))
        if len(faces) != 2:
            continue
        edge = TopoDS.Edge(faces_of_edge.FindKey(index))
        first, second = TopoDS.Face(faces[0]), TopoDS.Face(faces[1])
        if BRep_Tool.Continuity_s(edge, first, second) != GeomAbs_C0:
            builder.Continuity(edge, first, second, GeomAbs_C2)
