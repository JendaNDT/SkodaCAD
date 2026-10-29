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
              "tečnost [°]": round(math.degrees(math.acos(GRAZING_COS)), 1),
              "průnik [mm³]": 1e-3}

ALONG_SURFACE = "Paprsek běží po povrchu dílu – délku v materiálu tu nejde určit."
THROUGH_EDGE = "Paprsek prochází hranou nebo rohem dílu."
GRAZING = "Paprsek se plochy jen tečně dotýká."
UNDECIDED = "Jádro tu nerozhodlo, jestli je bod v materiálu."
ON_EDGE = "Bod leží na hraně mezi plochami – směr plochy tu není jednoznačný."
NO_OVERLAP = "Průnik s dílem jádro nespočítalo – kolizi nejde vyloučit."
OVERLAP_TOL = 1e-3  # mm³ – menší průnik je jen dotyk (sonda položená na ploše)

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


@dataclass(frozen=True)
class SurfacePoint:
    """Bod plochy: směr ven z materiálu a zakřivení (pro přiložení sondy, tečnou rovinu)."""

    point: Point  # nejbližší bod plochy k zadanému bodu
    normal: Point  # ven z materiálu
    kind: str  # plane, cylinder, cone, sphere, torus, other
    curvatures: tuple[float, float]  # [1/mm]: + vypouklá (vnějšek trubky), − vydutá (díra)
    directions: tuple[Point, Point]  # hlavní směry k zakřivením (větší |zakřivení| první)
    distance: float  # jak daleko byl zadaný bod od plochy [mm]
    reasons: tuple[str, ...] = ()
    face: Any = field(default=None, compare=False, repr=False)

    @property
    def radii(self) -> tuple[float, float]:
        """Poloměry zakřivení [mm] (∞ = rovně)."""
        return tuple(1 / abs(k) if abs(k) > 1e-12 else math.inf for k in self.curvatures)

    @property
    def certain(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class Visibility:
    """Vidí bod plochy daným směrem ven, nebo mu něco stojí v cestě?"""

    visible: bool
    blocker: Hit | None  # první překážka (None = nic, nebo směr míří rovnou do materiálu)
    distance: float | None  # vzdálenost k překážce [mm], 0 = směr míří do materiálu
    reasons: tuple[str, ...] = ()

    @property
    def certain(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class Collision:
    """Překrytí tělesa (sonda, jho, detektor) s dílem a vůle k překážkám."""

    volume: float  # společný objem [mm³]
    colliding: bool  # průnik nad OVERLAP_TOL (nebo ho nejde vyloučit)
    clearance: float | None  # nejmenší vzdálenost k dílu bez ignorovaných ploch [mm]
    points: tuple[Point, Point] | None  # nejbližší body (na dílu, na tělese)
    reasons: tuple[str, ...] = ()

    @property
    def certain(self) -> bool:
        return not self.reasons


# --- jádro ---------------------------------------------------------------------------------


def _common(a: Any, b: Any) -> Any:
    """Průnik, který vstupní tvary nemění (``SetNonDestructive``). Výchozí režim OCCT
    zapisuje do hran vstupů: posunuté kopie sondy sdílejí hrany, takže každé přiložení
    přidalo záznam a další průnik byl pomalejší (6 000 přiložení: 4 → 45 ms na kolizi)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.collections import List_TopoDS_Shape

    arguments, tools = List_TopoDS_Shape(), List_TopoDS_Shape()
    arguments.Append(getattr(a, "wrapped", a))
    tools.Append(getattr(b, "wrapped", b))
    common = BRepAlgoAPI_Common()
    common.SetNonDestructive(True)
    common.SetArguments(arguments)
    common.SetTools(tools)
    common.Build()
    return common


def overlap(a: Any, b: Any) -> float | None:
    """Objem průniku dvou těles [mm³]; None = průnik nejde spočítat (bere se jako kolize)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    common = _common(a, b)
    if not common.IsDone():  # OCCT 8: chyby hlásí jen IsDone
        return None
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(common.Shape(), props)
    return abs(props.Mass())


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

    # --- bod plochy -------------------------------------------------------------------

    def surface_at(self, point: Point, face: Any = None) -> SurfacePoint:
        """Nejbližší bod plochy (nebo zadané ``face``): normála ven, zakřivení, druh plochy."""
        from build123d import Face, Vertex

        point = _point(point, "Bod")
        here = Vertex(*point)
        reasons: list[str] = []
        if face is None:
            found = sorted(((f.distance_to(here), f) for f in self.part.faces()),
                           key=lambda item: item[0])
            if not found:
                raise GeometryError("Díl nemá žádnou plochu.")
            face = found[0][1]
            if len(found) > 1 and found[1][0] - found[0][0] < EDGE_TOL:
                reasons.append(ON_EDGE)
        face = face if isinstance(face, Face) else Face(face)
        distance, on_face, _ = face.distance_to_with_closest_points(here)
        where = (on_face.X, on_face.Y, on_face.Z)
        u, v = _uv(face.wrapped, where)
        normal = _outward_normal(face.wrapped, u, v)
        if normal == (0.0, 0.0, 0.0):
            reasons.append(UNDECIDED)
        curvatures, directions = _curvature(face.wrapped, u, v, normal)
        kind = face.geom_type.name.lower()
        if kind not in ("plane", "cylinder", "cone", "sphere", "torus"):
            kind = "other"
        return SurfacePoint(where, normal, kind, curvatures, directions, distance,
                            tuple(reasons), face)

    # --- viditelnost ------------------------------------------------------------------

    def visible(self, point: Point, direction: Point, max_length: float | None = None
                ) -> Visibility:
        """Vidí bod (na povrchu dílu) směrem ``direction`` ven, nebo mu díl stojí v cestě?"""
        ray = self.cast(point, direction, max_length)
        blocking = next((s for s in ray.segments if s.end > EDGE_TOL), None)
        if blocking is not None and blocking.start <= EDGE_TOL:
            return Visibility(False, None, 0.0)  # směr míří rovnou do materiálu
        stop = blocking.start if blocking is not None else ray.max_length
        reasons = [r for h in ray.hits if EDGE_TOL < h.distance <= stop + LENGTH_TOL
                   for r in h.reasons]
        if ALONG_SURFACE in ray.reasons or UNDECIDED in ray.reasons:
            reasons += [r for r in ray.reasons if r in (ALONG_SURFACE, UNDECIDED)]
        reasons = list(dict.fromkeys(reasons))
        if blocking is None:
            return Visibility(True, None, None, tuple(reasons))
        return Visibility(False, blocking.entry, blocking.start, tuple(reasons))

    # --- kolize ---------------------------------------------------------------------------

    def collision(self, solid: Any, ignore_faces: Any = ()) -> Collision:
        """Překrytí tělesa s dílem (dotyk není kolize) a vůle k dílu bez ``ignore_faces``
        (plocha, na které těleso stojí)."""
        from OCP.BRep import BRep_Builder
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.TopoDS import TopoDS_Compound

        shape = getattr(solid, "wrapped", solid)
        reasons: list[str] = []
        common = _common(self.part, shape)
        volume = 0.0
        if common.IsDone():  # OCCT 8: chyby hlásí jen IsDone (HasErrors tu není)
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(common.Shape(), props)
            volume = abs(props.Mass())
        else:
            reasons.append(NO_OVERLAP)
        colliding = volume > OVERLAP_TOL or bool(reasons)
        ignored = [getattr(f, "wrapped", f) for f in ignore_faces]
        others = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(others)
        count = 0
        for face in self.part.faces():
            if not any(face.wrapped.IsSame(other) for other in ignored):
                builder.Add(others, face.wrapped)
                count += 1
        clearance, points = None, None
        if count:
            distance = BRepExtrema_DistShapeShape(others, shape)
            if distance.IsDone() and distance.NbSolution():
                a, b = distance.PointOnShape1(1), distance.PointOnShape2(1)
                clearance = distance.Value()
                points = ((a.X(), a.Y(), a.Z()), (b.X(), b.Y(), b.Z()))
        if colliding:
            clearance = 0.0
        return Collision(volume, colliding, clearance, points, tuple(reasons))

    # --- plochy studie --------------------------------------------------------------------

    def faces_of(self, target: Any) -> tuple[list[Any], list[str]]:
        """Plochy kontrolované oblasti studie (odkazy významem) → (plochy, české problémy)."""
        from skodacad.selectors import SelectionError, find_face

        faces, problems = [], []
        references = (target or {}).get("faces", []) if isinstance(target, dict) else []
        for number, reference in enumerate(references, start=1):
            try:
                face, _ = find_face(self.part, reference["face"])
            except (SelectionError, KeyError, TypeError) as exc:
                problems.append(f"Plocha č. {number}: {exc}")
                continue
            faces.append(face)
        return faces, problems

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


# --- kontrola pro self-test ---------------------------------------------------------------


def self_check(folder: Any) -> tuple[bool, str]:
    """Rychlá kontrola jádra na referenčních dílech (self-test aplikace, i ve Windows):
    paprsek trubkou 2 × 6 mm, přímka v ploše desky nejistá, sonda zasunutá 3 mm do žebra
    koliduje (3 × 20 × 25 mm³). Vrátí (v pořádku, český řádek zprávy)."""
    from pathlib import Path

    from build123d import Box, Pos

    from skodacad.document import Document
    from skodacad.rebuild import rebuild

    def part(name: str) -> Part:
        return rebuild(Document.load(Path(folder) / f"{name}.json")).part

    pipe = PartGeometry(part("trubka")).cast((0, 0, 100), (0, 0, -1))
    flat = PartGeometry(part("deska")).cast((-150, 0, 20), (1, 0, 0))
    hit = PartGeometry(part("zebro")).collision(Pos(22, 0, 32.5) * Box(40, 20, 25))
    if (abs(pipe.material_length - 12) < 1e-6 and pipe.certain
            and flat.material_length == 0 and not flat.certain
            and hit.colliding and abs(hit.volume - 1500) < 1e-3):
        return True, (f"NDT geometrie: OK (paprsek trubkou {pipe.material_length:.2f} mm, "
                      f"přímka v ploše nejistá, kolize sondy {hit.volume:.0f} mm³)")
    return False, (f"NDT geometrie: paprsek {pipe.material_length:.2f} mm, v ploše "
                   f"{flat.material_length:.2f} mm ({'; '.join(flat.reasons) or 'jisté'}), "
                   f"kolize {hit.volume:.1f} mm³ (čekáno 12, 0 a nejisté, 1500)")


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


def _uv(face: Any, point: Point) -> tuple[float, float]:
    from OCP.BRep import BRep_Tool
    from OCP.gp import gp_Pnt
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface

    uv = ShapeAnalysis_Surface(BRep_Tool.Surface_s(face)).ValueOfUV(gp_Pnt(*point), 1e-7)
    return uv.X(), uv.Y()


def _curvature(face: Any, u: float, v: float, normal: Point
               ) -> tuple[tuple[float, float], tuple[Point, Point]]:
    """Hlavní zakřivení vůči normále ven z materiálu: + vypouklá, − vydutá (větší |k| první).

    OCCT počítá zakřivení vůči normále plochy (kladné = plocha se ohýbá k normále); ta může
    mířit dovnitř materiálu (otočená plocha) – znaménko se srovná podle ``normal``.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.gp import gp_Dir

    props = BRepLProp_SLProps(BRepAdaptor_Surface(face), u, v, 2, 1e-9)
    if not props.IsCurvatureDefined() or not props.IsNormalDefined():
        return (0.0, 0.0), ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    occ = props.Normal()
    sign = 1.0 if occ.X() * normal[0] + occ.Y() * normal[1] + occ.Z() * normal[2] >= 0 else -1.0
    k_max, k_min = -sign * props.MaxCurvature(), -sign * props.MinCurvature()
    if props.IsUmbilic():  # rovina, koule – všechny směry stejné
        first = props.D1U()
        first_dir = gp_Dir(first) if first.Magnitude() > 1e-12 else gp_Dir(1, 0, 0)
        second_dir = gp_Dir(occ.Crossed(first_dir)) if not occ.IsParallel(
            first_dir, 1e-9) else gp_Dir(0, 1, 0)
        d_max, d_min = first_dir, second_dir
    else:
        d_max, d_min = gp_Dir(), gp_Dir()
        props.CurvatureDirections(d_max, d_min)
    pairs = sorted([(k_max, d_max), (k_min, d_min)], key=lambda item: -abs(item[0]))
    clean = tuple(0.0 if abs(k) < 1e-12 else k for k, _ in pairs)
    return clean, tuple((d.X(), d.Y(), d.Z()) for _, d in pairs)


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
