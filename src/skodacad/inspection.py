"""Lidský popis vybrané plochy, hrany nebo bodu (pro stavový řádek okna)."""

from __future__ import annotations

from typing import Any

from build123d import Edge, Face, GeomType, Vertex
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX

_FACE_TYPES = {
    GeomType.PLANE: "rovinná",
    GeomType.CYLINDER: "válcová",
    GeomType.CONE: "kuželová",
    GeomType.SPHERE: "kulová",
    GeomType.TORUS: "toroidní (zaoblení)",
    GeomType.BSPLINE: "obecná (spline)",
    GeomType.BEZIER: "obecná (Bézier)",
    GeomType.REVOLUTION: "rotační",
    GeomType.EXTRUSION: "vysunutá",
    GeomType.OFFSET: "odsazená",
}


def number(value: float, decimals: int = 2) -> str:
    """1234.5 → „1 234.50“ (mezera mezi tisíci, jako ve výpisu příkazové řádky)."""
    if abs(value) < 0.5 * 10**-decimals:
        value = 0.0  # žádné „-0.00“
    return f"{value:,.{decimals}f}".replace(",", " ")


def describe_shape(shape: Any) -> str:
    """Popis podtvaru z OCCT (``TopoDS_Shape``) – plocha, hrana nebo bod."""
    kind = shape.ShapeType()
    if kind == TopAbs_FACE:
        return _describe_face(Face(shape))
    if kind == TopAbs_EDGE:
        return _describe_edge(Edge(shape))
    if kind == TopAbs_VERTEX:
        v = Vertex(shape)
        return f"Bod – X {number(v.X)}  Y {number(v.Y)}  Z {number(v.Z)} mm"
    return "Vybraný prvek"


def _describe_face(face: Face) -> str:
    kind = _FACE_TYPES.get(face.geom_type, "obecná")
    text = f"Plocha – {kind}, obsah {number(face.area)} mm²"
    if face.geom_type in (GeomType.CYLINDER, GeomType.SPHERE):
        text += f", R {number(face.radius)} (Ø {number(2 * face.radius)}) mm"
    if face.geom_type == GeomType.PLANE:
        n = face.normal_at()
        text += f", normála ({n.X:.2f}, {n.Y:.2f}, {n.Z:.2f})"
    return text


def _describe_edge(edge: Edge) -> str:
    if edge.geom_type == GeomType.LINE:
        return f"Hrana – úsečka, délka {number(edge.length)} mm"
    if edge.geom_type == GeomType.CIRCLE:
        kind = "kružnice" if edge.is_closed else "oblouk"
        return (f"Hrana – {kind} R {number(edge.radius)} (Ø {number(2 * edge.radius)}) mm, "
                f"délka {number(edge.length)} mm")
    return f"Hrana – křivka, délka {number(edge.length)} mm"
