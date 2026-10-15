"""Měření ve 3D: rozměry plochy či hrany, vzdálenost a úhel dvou věcí, tloušťka stěny.

Vybereš-li jednu věc, dostaneš její rozměry (délka, průměr, obsah) a u plochy i tloušťku
stěny v místě kliknutí – jako ultrazvukový tloušťkoměr: od bodu kolmo do materiálu až
k protější ploše. Dvě věci dají nejkratší vzdálenost a podle tvaru i vzdálenost
rovnoběžných ploch/hran, rozteč os děr, vzdálenost osy od plochy nebo úhel.

Měření jde uložit do modelu (``Document.measurements``). Uložené měření drží plochy a hrany
**významem** (plocha: bod, směr, druh a poloměr; hrana: popis jako u zaoblení), nikdy
číslem, a při každém přepočtu se spočítá znovu.

Jednotky: mm, mm², úhly ve stupních.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from build123d import Edge, Face, GeomType, Part, Vector, Vertex

from skodacad.inspection import number
from skodacad.selectors import FACE_TYPES, SelectionError, find_face, select_edges

Point = tuple[float, float, float]
_PARALLEL = 1e-7  # |sin úhlu| – směry jsou rovnoběžné
_ON_FACE = 1e-3  # mm – kliknutý bod leží na ploše

# Druhy měření; uložené měření si pamatuje druh, okno podle něj vybere hodnotu.
KINDS = {
    "length": "délka hrany",
    "diameter": "průměr",
    "radius": "poloměr oblouku",
    "area": "obsah plochy",
    "thickness": "tloušťka stěny",
    "distance": "nejkratší vzdálenost",
    "parallel": "kolmá vzdálenost rovnoběžných věcí",
    "angle": "úhel",
    "centers": "vzdálenost středů",
}


class MeasureError(ValueError):
    """Měření nejde spočítat (zpráva je česky pro uživatele)."""


@dataclass(frozen=True)
class Value:
    """Jedna naměřená hodnota."""

    kind: str  # klíč z KINDS
    label: str  # česky, např. „Rozteč os“
    value: float
    unit: str  # "mm", "mm²" nebo "°"
    points: tuple[Point, Point] | None = None  # čára měření ve 3D (odkud kam)

    @property
    def text(self) -> str:
        return f"{self.label}: {format_value(self.value, self.unit)}"


def format_value(value: float, unit: str) -> str:
    if unit == "°":
        return f"{number(value)}°"
    return f"{number(value, 0 if unit == 'mm²' and value >= 1000 else 2)} {unit}"


@dataclass(frozen=True)
class _Geometry:
    """Co je na ploše/hraně podstatné pro měření."""

    kind: str  # "plane", "line", "axis", "point" nebo "other"
    origin: Vector | None = None
    direction: Vector | None = None  # normála roviny / směr úsečky či osy
    center: Vector | None = None  # střed kružnice nebo koule

    @property
    def linear(self) -> bool:
        return self.kind in ("line", "axis")


# --- měření vybraných ploch a hran --------------------------------------------------------


def measure(faces: list[Face], edges: list[Edge], point: Any = None,
            part: Part | None = None) -> list[Value]:
    """Hodnoty pro výběr ve 3D. Nejdůležitější hodnota je první.

    ``point`` je místo kliknutí (tloušťka stěny), ``part`` díl, na kterém se kliklo
    (paprsek tloušťky naráží na jeho plochy). Víc než dvě věci se neměří (vrátí []).
    """
    items: list[Face | Edge] = [*faces, *edges]
    if len(items) == 1:
        item = items[0]
        if isinstance(item, Face):
            return _face_values(item, point, part)
        return _edge_values(item)
    if len(items) == 2:
        return _pair_values(items[0], items[1])
    return []


def _face_values(face: Face, point: Any, part: Part | None) -> list[Value]:
    values = []
    where = _point_on(face, point)
    if face.geom_type in _ROUND:  # u díry a čepu je nejdůležitější průměr
        middle = _round_center(face, where)
        values.append(Value("diameter", "Průměr", 2 * face.radius, "mm",
                            (_tuple(where), _tuple(middle * 2 - where))))
    if part is not None:
        try:
            values.append(wall_thickness(part, face, where))
        except MeasureError:
            pass  # třeba plocha, za kterou žádný materiál není
    values.append(Value("area", "Obsah plochy", face.area, "mm²"))
    return values


def _edge_values(edge: Edge) -> list[Value]:
    values = []
    if edge.geom_type == GeomType.CIRCLE:
        center = edge.arc_center
        start = edge.position_at(0)
        if edge.is_closed:
            values.append(Value("diameter", "Průměr", 2 * edge.radius, "mm",
                                (_tuple(start), _tuple(center * 2 - start))))
        else:
            values.append(Value("radius", "Poloměr oblouku", edge.radius, "mm",
                                (_tuple(center), _tuple(edge.position_at(0.5)))))
    points = None
    if edge.geom_type == GeomType.LINE:
        points = (_tuple(edge.position_at(0)), _tuple(edge.position_at(1)))
    values.append(Value("length", "Délka hrany", edge.length, "mm", points))
    return values


def _pair_values(a: Face | Edge, b: Face | Edge) -> list[Value]:
    distance, pa, pb = a.distance_to_with_closest_points(b)
    shortest = Value("distance", "Nejkratší vzdálenost", distance, "mm", (_tuple(pa), _tuple(pb)))
    ga, gb = _geometry(a), _geometry(b)
    if gb.kind == "plane" and ga.kind != "plane":  # rovina vždy první – méně případů níž
        ga, gb, pa, pb = gb, ga, pb, pa
    values: list[Value] = []

    if ga.kind == "plane" and gb.kind == "plane":
        if _parallel(ga.direction, gb.direction):
            gap = abs((pa - gb.origin).dot(gb.direction))
            foot = pa - gb.direction * (pa - gb.origin).dot(gb.direction)
            values.append(Value("parallel", "Vzdálenost rovnoběžných ploch", gap, "mm",
                                (_tuple(pa), _tuple(foot))))
        else:
            values.append(Value("angle", "Úhel mezi plochami",
                                _angle(ga.direction, gb.direction), "°"))
    elif ga.kind == "plane" and gb.linear:
        noun = "osy" if gb.kind == "axis" else "hrany"
        if abs(ga.direction.dot(gb.direction)) < _PARALLEL:  # směr leží v rovině
            start = _foot_on_line(pb, gb)
            gap = abs((start - ga.origin).dot(ga.direction))
            foot = start - ga.direction * (start - ga.origin).dot(ga.direction)
            values.append(Value("parallel", f"Vzdálenost {noun} od plochy", gap, "mm",
                                (_tuple(start), _tuple(foot))))
        else:
            tilt = 90 - _angle(ga.direction, gb.direction, acute=True)
            values.append(Value("angle", f"Úhel {noun} a plochy", tilt, "°"))
    elif ga.kind == "plane" and gb.kind == "point":
        gap = abs((gb.center - ga.origin).dot(ga.direction))
        foot = gb.center - ga.direction * (gb.center - ga.origin).dot(ga.direction)
        values.append(Value("parallel", "Vzdálenost středu od plochy", gap, "mm",
                            (_tuple(gb.center), _tuple(foot))))
    elif ga.linear and gb.linear:
        label = {("axis", "axis"): ("Rozteč os", "Úhel mezi osami"),
                 ("line", "line"): ("Vzdálenost rovnoběžných hran", "Úhel mezi hranami")}.get(
            (ga.kind, gb.kind), ("Vzdálenost osy od hrany", "Úhel osy a hrany"))
        if _parallel(ga.direction, gb.direction):
            start = _foot_on_line(pa, ga)
            end = _foot_on_line(start, gb)
            values.append(Value("parallel", label[0], (end - start).length, "mm",
                                (_tuple(start), _tuple(end))))
        else:
            values.append(Value("angle", label[1],
                                _angle(ga.direction, gb.direction, acute=True), "°"))

    if ga.center is not None and gb.center is not None:
        values.append(Value("centers", "Vzdálenost středů", (gb.center - ga.center).length, "mm",
                            (_tuple(ga.center), _tuple(gb.center))))
    values.append(shortest)
    return values


def wall_thickness(part: Part, face: Face, point: Any) -> Value:
    """Tloušťka stěny v bodě plochy: od bodu kolmo do materiálu k nejbližší protější ploše."""
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

    start = Vector(*point)
    inward = -face.normal_at(start)
    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(part.wrapped, 1e-7)
    intersector.Perform(gp_Lin(gp_Pnt(*start), gp_Dir(*inward)), 1e-6, 1e9)
    hits = [intersector.WParameter(i) for i in range(1, intersector.NbPnt() + 1)]
    hits = [w for w in hits if w > 1e-4]
    if not hits:
        raise MeasureError("Za plochou v tomhle místě žádný materiál není – tloušťku stěny "
                           "nejde změřit.")
    depth = min(hits)
    return Value("thickness", "Tloušťka stěny", depth, "mm",
                 (_tuple(start), _tuple(start + inward * depth)))


# --- geometrie ------------------------------------------------------------------------------

_ROUND = (GeomType.CYLINDER, GeomType.SPHERE)


def _geometry(item: Face | Edge) -> _Geometry:
    if isinstance(item, Face):
        if item.geom_type == GeomType.PLANE:
            return _Geometry("plane", item.center(), item.normal_at())
        if item.geom_type in (GeomType.CYLINDER, GeomType.CONE):
            origin, direction = _surface_axis(item)
            return _Geometry("axis", origin, direction)
        if item.geom_type == GeomType.SPHERE:
            return _Geometry("point", center=_sphere_center(item))
        return _Geometry("other")
    if item.geom_type == GeomType.LINE:
        return _Geometry("line", item.position_at(0), item.tangent_at(0))
    if item.geom_type == GeomType.CIRCLE:
        center = item.arc_center
        normal = _circle_normal(item)
        return _Geometry("axis", center, normal, center)
    return _Geometry("other")


def _surface_axis(face: Face) -> tuple[Vector, Vector]:
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    surface = BRepAdaptor_Surface(face.wrapped)
    axis = (surface.Cylinder() if face.geom_type == GeomType.CYLINDER
            else surface.Cone()).Axis()
    location, direction = axis.Location(), axis.Direction()
    return (Vector(location.X(), location.Y(), location.Z()),
            Vector(direction.X(), direction.Y(), direction.Z()))


def _sphere_center(face: Face) -> Vector:
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    location = BRepAdaptor_Surface(face.wrapped).Sphere().Location()
    return Vector(location.X(), location.Y(), location.Z())


def _round_center(face: Face, point: Vector) -> Vector:
    """Střed průřezu válce/koule v místě bodu (bod promítnutý na osu, střed koule)."""
    if face.geom_type == GeomType.SPHERE:
        return _sphere_center(face)
    origin, direction = _surface_axis(face)
    return origin + direction * (point - origin).dot(direction)


def _circle_normal(edge: Edge) -> Vector:
    from OCP.BRepAdaptor import BRepAdaptor_Curve

    axis = BRepAdaptor_Curve(edge.wrapped).Circle().Axis().Direction()
    return Vector(axis.X(), axis.Y(), axis.Z())


def _foot_on_line(point: Vector, geometry: _Geometry) -> Vector:
    return geometry.origin + geometry.direction * (point - geometry.origin).dot(geometry.direction)


def _parallel(u: Vector, v: Vector) -> bool:
    return u.normalized().cross(v.normalized()).length < _PARALLEL


def _angle(u: Vector, v: Vector, acute: bool = False) -> float:
    cosine = u.normalized().dot(v.normalized())
    if acute:
        cosine = abs(cosine)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _point_on(face: Face, point: Any) -> Vector:
    """Bod na ploše: místo kliknutí, pokud na ní leží, jinak bod uvnitř plochy dál od hran."""
    if point is not None:
        distance, on_face, _ = face.distance_to_with_closest_points(Vertex(*point))
        if distance < _ON_FACE:
            return on_face
    return inner_point(face)


def inner_point(face: Face) -> Vector:
    """Bod uvnitř plochy co nejdál od jejích hran (střed plochy může ležet v díře)."""
    best, best_gap = None, -1.0
    edges = list(face.edges())
    for u in (0.5, 0.3, 0.7, 0.1, 0.9):
        for v in (0.5, 0.3, 0.7, 0.1, 0.9):
            candidate = face.position_at(u, v)
            distance, on_face, _ = face.distance_to_with_closest_points(Vertex(candidate))
            if distance > _ON_FACE:
                continue  # parametr mimo ořezanou plochu (v díře)
            gap = min((edge.distance_to(on_face) for edge in edges), default=1.0)
            if gap > best_gap:
                best, best_gap = on_face, gap
        if best_gap > 1.0:
            break
    if best is None:
        _, best, _ = face.distance_to_with_closest_points(Vertex(face.center()))
    return best


def _tuple(vector: Vector) -> Point:
    return (vector.X, vector.Y, vector.Z)


# --- uložená měření (odkazy významem) ---------------------------------------------------------


def _round_number(value: float, decimals: int = 4) -> float | int:
    rounded = round(value, decimals) + 0.0
    return int(rounded) if rounded.is_integer() else rounded


def face_reference(face: Face, point: Any = None) -> dict[str, Any]:
    """Plocha → odkaz významem: bod na ní, směr, druh a (u válce/koule) poloměr."""
    where = _point_on(face, point)
    spec: dict[str, Any] = {
        "at": [_round_number(v) for v in _tuple(where)],
        "normal": [_round_number(v) for v in _tuple(face.normal_at(where))],
    }
    kind = next((name for name, geom in FACE_TYPES.items() if geom == face.geom_type), None)
    if kind:
        spec["type"] = kind
    if face.geom_type in _ROUND:
        spec["radius"] = _round_number(face.radius, 6)
    return {"face": spec}


def reference_for(part: Part, item: Face | Edge, point: Any = None) -> dict[str, Any]:
    """Odkaz na plochu nebo hranu dílu pro uložené měření; ověří, že najde totéž."""
    from skodacad.picking import edge_selector

    if isinstance(item, Face):
        reference = face_reference(item, point)
        found = resolve(part, reference)
        if not isinstance(found, Face) or not found.is_same(item):
            raise MeasureError("Tuhle plochu nejde pro uložené měření jednoznačně určit – klikni "
                               "na ni kousek dál od hrany.")
        return reference
    try:
        return {"edge": edge_selector(part, [item])}
    except SelectionError as exc:
        raise MeasureError(str(exc)) from None


def resolve(part: Part, reference: Any) -> Face | Edge:
    """Odkaz z uloženého měření → plocha nebo hrana dílu (česká chyba, když zmizela)."""
    if isinstance(reference, dict) and "face" in reference:
        face, _ = find_face(part, reference["face"])
        return face
    if isinstance(reference, dict) and "edge" in reference:
        edges = select_edges(part, reference["edge"], float)
        if len(edges) != 1:
            raise SelectionError("Hrana uloženého měření není jednoznačná – vyber ji znovu.")
        return edges[0]
    raise SelectionError('Odkaz v měření musí být {"face": …} nebo {"edge": …}.')


def reference_point(reference: Any) -> Point | None:
    """Místo měření uložené v odkazu na plochu (tloušťka stěny se měří v něm)."""
    if isinstance(reference, dict) and isinstance(reference.get("face"), dict):
        try:
            x, y, z = (float(v) for v in reference["face"]["at"])
        except (KeyError, TypeError, ValueError):
            return None
        return (x, y, z)
    return None


@dataclass(frozen=True)
class SavedResult:
    """Uložené měření po přepočtu: hodnota, nebo česká chyba."""

    id: str
    name: str
    kind: str
    value: Value | None = None
    error: str = ""

    @property
    def text(self) -> str:
        if self.value is None:
            return f"{self.name}: ✕ {self.error}"
        return f"{self.name}: {format_value(self.value.value, self.value.unit)}"


def measurement_name(measurement: dict[str, Any]) -> str:
    name = measurement.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    kind = measurement.get("kind")
    return KINDS.get(kind, str(kind)).capitalize()


def evaluate(part: Part | None, measurement: dict[str, Any]) -> SavedResult:
    """Spočítá uložené měření na dílu."""
    name = measurement_name(measurement)
    kind = measurement.get("kind")
    mid = str(measurement.get("id", "?"))

    def failed(message: str) -> SavedResult:
        return SavedResult(mid, name, str(kind), error=message)

    if kind not in KINDS:
        return failed(f"neznámý druh měření „{kind}“ (umím: {', '.join(KINDS)})")
    if part is None:
        return failed("žádný díl není – není co měřit")
    references = [measurement[key] for key in ("a", "b") if key in measurement]
    if not references:
        return failed("měření nemá „a“ (plochu nebo hranu)")
    try:
        items = [resolve(part, reference) for reference in references]
        faces = [item for item in items if isinstance(item, Face)]
        edges = [item for item in items if isinstance(item, Edge)]
        point = reference_point(references[0]) if len(items) == 1 else None
        values = measure(faces, edges, point, part)
    except (SelectionError, MeasureError) as exc:
        return failed(str(exc))
    except Exception as exc:  # noqa: BLE001 – chyba jádra nesmí shodit přepočet
        return failed(f"neočekávaná chyba jádra ({type(exc).__name__}: {exc})")
    value = next((v for v in values if v.kind == kind), None)
    if value is None:
        return failed(_missing(kind, len(items)))
    return SavedResult(mid, name, kind, value)


def _missing(kind: str, count: int) -> str:
    if kind == "parallel":
        return "vybrané věci už nejsou rovnoběžné"
    if kind == "angle":
        return "vybrané věci jsou teď rovnoběžné – úhel mezi nimi není"
    if kind == "thickness":
        return "za plochou v tomhle místě žádný materiál není"
    if count == 1 and kind in ("distance", "centers"):
        return "vzdálenost potřebuje dvě vybrané věci"
    return f"{KINDS[kind]} u téhle plochy/hrany nejde změřit"


def new_measurement(part: Part, faces: list[Face], edges: list[Edge], kind: str,
                    point: Any = None, existing: list[dict[str, Any]] | None = None
                    ) -> dict[str, Any]:
    """Záznam uloženého měření z výběru ve 3D (odkazy významem, ověřené)."""
    if kind not in KINDS:
        raise MeasureError(f"Neznámý druh měření „{kind}“.")
    items: list[Face | Edge] = [*faces, *edges]
    if not 1 <= len(items) <= 2:
        raise MeasureError("Měřit jde jednu nebo dvě vybrané věci – plochy nebo hrany.")
    used = {m.get("id") for m in existing or []}
    number_ = 1
    while f"m{number_}" in used:
        number_ += 1
    record: dict[str, Any] = {"id": f"m{number_}", "kind": kind}
    for key, item in zip(("a", "b"), items, strict=False):
        record[key] = reference_for(part, item, point)  # bod rozhodne jen u kliknuté plochy
    result = evaluate(part, record)
    if result.value is None:
        raise MeasureError(f"Měření nejde uložit: {result.error}.")
    # název z měření (např. „Rozteč os“) – jde přejmenovat
    return {"id": record.pop("id"), "name": result.value.label, **record}
