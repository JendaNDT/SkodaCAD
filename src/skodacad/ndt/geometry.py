"""Společné geometrické jádro NDT (etapa 02): dotazy na přesné těleso Open CASCADE.

Jen geometrie – kudy vede přímka, kde je materiál, kam míří plocha, co komu stojí v cestě.
Žádná fyzika UT/RT ani detekovatelnost vad; pravidla metod (šířka svazku, koncové echo …)
si nastaví každá metoda sama v dalších etapách. Bez okna a bez Qt.

Úseky v materiálu se neurčují párováním „vstup/výstup“ z průsečíků: jádro hlásí vstup
i u paprsku, který jen běží po povrchu (deska „naplocho“), a průsečík na hraně dvakrát.
Každý úsek mezi průsečíky se proto ověří bodem uprostřed (uvnitř / vně / na povrchu).
Co leží na povrchu, prochází hranou nebo se plochy jen tečně dotkne, je **nejisté**
(české důvody v ``reasons``) a nikdy se nezapočítá jako materiál.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from build123d import Part

ALGORITHM = "ndt-geometrie 1"  # verze algoritmu (do protokolu)
LENGTH_TOL = 1e-6  # mm – průsečíky blíž k sobě jsou jeden bod
EDGE_TOL = 1e-3  # mm – průsečík blíž k hraně plochy = „přes hranu“
GRAZING_COS = 0.01  # |cos| úhlu paprsek–normála pod touto mezí = tečný dotyk (≈ 89,4°)
TOLERANCES = {"délka [mm]": LENGTH_TOL, "hrana [mm]": EDGE_TOL,
              "tečnost [°]": round(math.degrees(math.acos(GRAZING_COS)), 1)}

ALONG_SURFACE = "Paprsek běží po povrchu dílu – délku v materiálu tu nejde určit."
THROUGH_EDGE = "Paprsek prochází hranou nebo rohem dílu."
GRAZING = "Paprsek se plochy jen tečně dotýká."
UNDECIDED = "Jádro tu nerozhodlo, jestli je bod v materiálu."

Point = tuple[float, float, float]


class GeometryError(ValueError):
    """Chybné zadání dotazu (zpráva česky)."""


# --- výsledky ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Hit:
    """Průsečík paprsku s povrchem dílu."""

    distance: float  # od počátku paprsku [mm]
    point: Point
    normal: Point  # ven z materiálu
    incidence: float  # úhel mezi paprskem a normálou plochy [°], 0 = kolmo
    entering: bool  # paprsek míří do materiálu (proti normále)
    reasons: tuple[str, ...] = ()
    face: Any = field(default=None, compare=False, repr=False)  # plocha build123d

    @property
    def certain(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class Segment:
    """Úsek paprsku v materiálu."""

    start: float  # [mm] od počátku paprsku
    end: float
    entry: Hit | None  # None = paprsek začíná v materiálu
    exit: Hit | None  # None = materiál pokračuje za konec paprsku
    reasons: tuple[str, ...] = ()

    @property
    def length(self) -> float:
        return self.end - self.start

    @property
    def certain(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class RayResult:
    """Průchod paprsku dílem: průsečíky, úseky v materiálu a jistota."""

    origin: Point
    direction: Point  # jednotkový
    max_length: float
    hits: tuple[Hit, ...]
    segments: tuple[Segment, ...]
    reasons: tuple[str, ...] = ()

    @property
    def certain(self) -> bool:
        return not self.reasons

    @property
    def material_length(self) -> float:
        """Délka v materiálu – jen jisté úseky [mm]."""
        return sum(s.length for s in self.segments if s.certain)

    def point_at(self, distance: float) -> Point:
        return _along(self.origin, self.direction, distance)


# --- jádro ---------------------------------------------------------------------------------


class PartGeometry:
    """Dotazy na jeden díl; jádro se načte jednou a další dotazy jsou rychlé (desetiny ms)."""

    def __init__(self, part: Part) -> None:
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

        if part is None:
            raise GeometryError("Model nemá těleso – není na čem počítat.")
        self.part = part
        self._intersector = IntCurvesFace_ShapeIntersector()
        self._intersector.Load(part.wrapped, 1e-7)
        self._classifier = BRepClass3d_SolidClassifier(part.wrapped)
        box = part.bounding_box()
        self._center = ((box.min.X + box.max.X) / 2, (box.min.Y + box.max.Y) / 2,
                        (box.min.Z + box.max.Z) / 2)
        self._radius = box.diagonal / 2
        margin = 1e-3
        self._low = (box.min.X - margin, box.min.Y - margin, box.min.Z - margin)
        self._high = (box.max.X + margin, box.max.Y + margin, box.max.Z + margin)

    # --- bod uvnitř / vně -----------------------------------------------------------------

    def classify(self, point: Point) -> str:
        """„inside“ (v materiálu), „outside“, „surface“ (na povrchu), nebo „unknown“."""
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT

        if not all(low <= v <= high for v, low, high in zip(point, self._low, self._high,
                                                             strict=True)):
            return "outside"  # mimo obalový kvádr – jádro není potřeba (rychlost)
        self._classifier.Perform(gp_Pnt(*point), LENGTH_TOL)
        state = self._classifier.State()
        return {TopAbs_IN: "inside", TopAbs_OUT: "outside", TopAbs_ON: "surface"}.get(
            state, "unknown")

    # --- paprsek ----------------------------------------------------------------------------

    def cast(self, origin: Point, direction: Point, max_length: float | None = None
             ) -> RayResult:
        """Průchod paprsku z ``origin`` směrem ``direction`` (do ``max_length`` mm, jinak za
        celý díl): průsečíky s povrchem, úseky v materiálu ověřené bodem uprostřed."""
        origin = _point(origin, "Počátek paprsku")
        unit = _unit(direction)
        reach = _distance(origin, self._center) + self._radius + 1.0
        limit = reach if max_length is None else float(max_length)
        if not limit > 0:
            raise GeometryError("Délka paprsku musí být kladná.")
        hits = self._hits(origin, unit, limit)
        breaks = sorted({0.0, limit, *(h.distance for h in hits if 0 < h.distance < limit)})
        pieces = []  # (od, do, stav úseku)
        for start, end in zip(breaks, breaks[1:], strict=False):
            if end - start > LENGTH_TOL:
                pieces.append((start, end, self.classify(_along(origin, unit, (start + end) / 2))))
        reasons: list[str] = [r for h in hits for r in h.reasons]
        if any(state == "surface" for *_, state in pieces):
            reasons.append(ALONG_SURFACE)
        if any(state == "unknown" for *_, state in pieces):
            reasons.append(UNDECIDED)
        segments = _segments(pieces, hits)
        return RayResult(origin, unit, limit, tuple(hits), tuple(segments),
                         tuple(dict.fromkeys(reasons)))

    def _hits(self, origin: Point, unit: Point, limit: float) -> list[Hit]:
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

        intersector = self._intersector
        intersector.Perform(gp_Lin(gp_Pnt(*origin), gp_Dir(*unit)), -LENGTH_TOL,
                            limit + LENGTH_TOL)
        raw = sorted((intersector.WParameter(i), i) for i in range(1, intersector.NbPnt() + 1))
        hits: list[Hit] = []
        for distance, index in raw:
            hit = self._hit(intersector, index, max(0.0, distance), unit)
            if hits and abs(hits[-1].distance - hit.distance) <= LENGTH_TOL:
                # dvě různé plochy v jednom bodě = hrana (nebo roh); dvakrát táž plocha = šev
                first = hits.pop()
                edge = () if first.face.wrapped.IsSame(hit.face.wrapped) else (THROUGH_EDGE,)
                hit = Hit(first.distance, first.point, first.normal, first.incidence,
                          first.entering, _merge(first.reasons, hit.reasons, edge), first.face)
            hits.append(hit)
        return hits

    def _hit(self, intersector: Any, index: int, distance: float, unit: Point) -> Hit:
        from build123d import Face

        face = intersector.Face(index)
        hit_point = intersector.Pnt(index)
        where = (hit_point.X(), hit_point.Y(), hit_point.Z())
        out = _outward_normal(face, intersector.UParameter(index), intersector.VParameter(index))
        cosine = sum(a * b for a, b in zip(out, unit, strict=True))
        reasons = []
        if out == (0.0, 0.0, 0.0):
            reasons.append(UNDECIDED)
        elif abs(cosine) < GRAZING_COS:
            reasons.append(GRAZING)
        if _edge_distance(face, where) < EDGE_TOL:
            reasons.append(THROUGH_EDGE)
        incidence = math.degrees(math.acos(min(1.0, abs(cosine))))
        return Hit(distance, where, out, incidence, cosine < 0, tuple(reasons), Face(face))


# --- pomocné výpočty -----------------------------------------------------------------------


def _segments(pieces: list[tuple[float, float, str]], hits: list[Hit]) -> list[Segment]:
    """Úseky v materiálu ze sousedních kousků „inside“; kousek na povrchu vedle = nejistý."""
    by_distance = {round(h.distance / LENGTH_TOL): h for h in hits}

    def hit_at(distance: float) -> Hit | None:
        key = round(distance / LENGTH_TOL)
        return by_distance.get(key) or by_distance.get(key - 1) or by_distance.get(key + 1)

    segments: list[Segment] = []
    index = 0
    while index < len(pieces):
        start, end, state = pieces[index]
        if state != "inside":
            index += 1
            continue
        first = index
        while index + 1 < len(pieces) and pieces[index + 1][2] == "inside":
            index += 1
        end = pieces[index][1]
        entry, exit_ = hit_at(start), hit_at(end)
        neighbours = [pieces[i][2] for i in (first - 1, index + 1) if 0 <= i < len(pieces)]
        reasons = [*(entry.reasons if entry else ()), *(exit_.reasons if exit_ else ())]
        if "surface" in neighbours:
            reasons.append(ALONG_SURFACE)
        segments.append(Segment(start, end, entry, exit_, tuple(dict.fromkeys(reasons))))
        index += 1
    return segments


def _outward_normal(face: Any, u: float, v: float) -> Point:
    """Jednotková normála plochy ven z materiálu v bodě (u, v); (0, 0, 0) = nejde určit.

    Na pólu koule (singulární bod parametrizace) dává ``BRepGProp_Face`` nulový vektor –
    tam pomůže ``BRepLProp_SLProps`` z vyšších derivací (orientaci plochy otočí ručně).
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.TopAbs import TopAbs_REVERSED

    point, normal = gp_Pnt(), gp_Vec()
    BRepGProp_Face(face).Normal(u, v, point, normal)
    if normal.Magnitude() > 1e-9:
        normal.Normalize()
        return (normal.X(), normal.Y(), normal.Z())
    props = BRepLProp_SLProps(BRepAdaptor_Surface(face), u, v, 2, 1e-9)
    if not props.IsNormalDefined():
        return (0.0, 0.0, 0.0)
    direction = props.Normal()
    sign = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0
    return (sign * direction.X(), sign * direction.Y(), sign * direction.Z())


def _edge_distance(face: Any, point: Point) -> float:
    """Nejmenší vzdálenost bodu od skutečných hran plochy [mm]. Šev (místo, kde se válec či
    koule uzavírá) a body na pólech koule nejsou hrany – plocha přes ně jde hladce."""
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Compound

    edges = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(edges)
    explorer = TopExp_Explorer(face, TopAbs_EDGE)
    count = 0
    while explorer.More():
        edge = TopoDS.Edge(explorer.Current())
        if not BRep_Tool.Degenerated_s(edge) and not BRep_Tool.IsClosed_s(edge, face):
            builder.Add(edges, edge)
            count += 1
        explorer.Next()
    if not count:
        return math.inf  # uzavřená plocha bez hran (koule)
    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
    distance = BRepExtrema_DistShapeShape(vertex, edges)
    return distance.Value() if distance.IsDone() else 0.0


def _merge(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(reason for group in groups for reason in group))


def _point(value: Any, what: str) -> Point:
    try:
        x, y, z = (float(v) for v in value)
    except (TypeError, ValueError):
        raise GeometryError(f"{what} musí být tři čísla [x, y, z].") from None
    if not all(math.isfinite(v) for v in (x, y, z)):
        raise GeometryError(f"{what} musí být konečná čísla.")
    return (x, y, z)


def _unit(direction: Any) -> Point:
    x, y, z = _point(direction, "Směr paprsku")
    length = math.sqrt(x * x + y * y + z * z)
    if length < 1e-12:
        raise GeometryError("Směr paprsku nesmí být nulový.")
    return (x / length, y / length, z / length)


def _along(origin: Point, unit: Point, distance: float) -> Point:
    return (origin[0] + unit[0] * distance, origin[1] + unit[1] * distance,
            origin[2] + unit[2] * distance)


def _distance(a: Point, b: Point) -> float:
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(a, b, strict=True)))
