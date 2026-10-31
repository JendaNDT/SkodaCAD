"""Prvky modelu (skica, vysunutí, rotace, zaoblení, …) a jejich výpočet.

Každý prvek je funkce ``(ctx, feature) -> None`` zaregistrovaná dekorátorem
``@feature``. Prvek čte své hodnoty z JSON objektu ``feature``, číselné
hodnoty vyhodnocuje přes ``ctx.num`` (umí výrazy s parametry) a výsledek
ukládá do ``ctx``. Chyby hlásí výjimkou ``FeatureError`` s českou zprávou.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from build123d import (
    Align,
    Axis,
    Circle,
    Cone,
    Cylinder,
    Face,
    FilletPolyline,
    Kind,
    Line,
    Location,
    Part,
    Plane,
    PolarLocations,
    Polygon,
    Polyline,
    Pos,
    Rectangle,
    RectangleRounded,
    RegularPolygon,
    Rot,
    Sketch,
    SlotCenterToCenter,
    ThreePointArc,
    Transition,
    Vector,
    chamfer,
    extrude,
    fillet,
    loft,
    make_face,
    offset,
    revolve,
    sweep,
)

from skodacad import guided_loft, variable_fillet
from skodacad.direct_edit import DirectEditError, check_origin, set_diameter
from skodacad.direct_edit import move_face as direct_move_face
from skodacad.expressions import evaluate
from skodacad.geometry_validation import (
    GeometryValidationError,
    VolumeFacts,
    check_boolean,
    check_cut_volume,
    check_modification,
    inspect_volume,
    volume_tolerance,
)
from skodacad.holes import KINDS as HOLE_KINDS
from skodacad.holes import HoleError, HoleShape, hole_shape, point_height
from skodacad.holes import summary as hole_summary
from skodacad.loft_wall import check_normal_wall
from skodacad.projection import ProjectionError
from skodacad.projection import refresh as refresh_references
from skodacad.selectors import (
    BASE_PLANES,
    FACE_DIRECTIONS,
    face_plane,
    face_plane_at,
    find_face,
    select_edges,
    select_faces,
)
from skodacad.solver import SolveError, arc_midpoint, loops, solve
from skodacad.standards import KINDS as STANDARD_KINDS
from skodacad.standards import StandardError, part_shape, section_sketch
from skodacad.standards import summary as standard_summary
from skodacad.threads import thread_groove


class FeatureError(ValueError):
    """Prvek nejde spočítat (zpráva je česky pro uživatele)."""


# Operace jednoho prvku: těleso a jestli materiál přidal („add“), nebo ubral („cut“).
Operation = tuple[Part, str]


def _same_input(before: Any, after: Any) -> bool:
    """Přesná neměnnost vstupu, včetně typů a pořadí; 1 není True.

    Nezměněný NaN v nepoužitém metadatu zůstane stejným objektem. Kontrola
    konečnosti geometrických hodnot nadále patří do num a inspect_volume.
    """
    if type(before) is not type(after):
        return False
    if before is after:
        return True
    if isinstance(before, dict):
        return tuple(before) == tuple(after) and all(
            _same_input(value, after[key]) for key, value in before.items())
    if isinstance(before, (list, tuple)):
        return len(before) == len(after) and all(
            _same_input(a, b) for a, b in zip(before, after, strict=True))
    return before == after


@dataclass
class BuildContext:
    """Stav během přepočtu modelu."""

    params: dict[str, float]
    part: Part | None = None
    sketches: dict[str, tuple[Plane, Sketch]] = field(default_factory=dict)
    # Co který spočítaný prvek s dílem udělal (id → operace v pořadí). Pole a zrcadlení
    # podle toho opakují prvky – stejné těleso přidají/odeberou na jiném místě.
    operations: dict[str, list[Operation]] = field(default_factory=dict)
    recording: list[Operation] | None = None  # operace právě počítaného prvku
    # Díl po každém dosud přijatém prvku (id, díl) – jen ke čtení; potřebuje ho pojistka
    # původu plochy u přímých úprav (P2.2, H3). Drží stejné objekty jako parts_before.
    # V kandidátovi prvku je to n-tice (jen ke čtení), zapisuje jen rebuild po přijetí.
    history: list[tuple[str, Part | None]] | tuple[tuple[str, Part | None], ...] = field(
        default_factory=list)

    def _fork_for_feature(self, feature: dict[str, Any]) -> tuple[BuildContext, dict[str, Any]]:
        """Vlastní kontejnery prvku; přijaté nativní tvary jsou jen pro čtení.

        Změna tvaru/roviny na místě vyžaduje vlastní kopii. Nekopírujeme celý
        graf OCCT ani historii; kopie každého seznamu chrání i jeho staré aliasy.
        """
        candidate = BuildContext(
            params=self.params.copy(), part=self.part, sketches=self.sketches.copy(),
            operations={key: list(ops) for key, ops in self.operations.items()}, recording=[],
            history=tuple(self.history))  # n-tice: prvek historii nemůže změnit
        return candidate, copy.deepcopy(feature)

    def _accept_feature(self, candidate: BuildContext, original: dict[str, Any],
                        computed: dict[str, Any]) -> None:
        """Přijme celý prvek až po jeho závěrečné geometrické kontrole."""
        if not _same_input(self.params, candidate.params):
            raise FeatureError("Vnitřní chyba prvku: změnil vstupní parametry. "
                               "Použij Zpět a zkus přepočet.")
        if not _same_input(original, computed):
            raise FeatureError("Vnitřní chyba prvku: změnil své zadání. "
                               "Použij Zpět a zkus přepočet.")
        if candidate.recording is None:
            raise FeatureError("Vnitřní chyba prvku: chybí záznam operací. "
                               "Použij Zpět a zkus přepočet.")
        operations = candidate.operations.copy()
        operations[original["id"]] = list(candidate.recording)
        # Vše, co může selhat, proběhlo před zápisem do přijatého kontextu.
        self.part = candidate.part
        self.sketches = candidate.sketches
        self.operations = operations
        # params a původní recording rodiče zůstávají nedotčené.

    def num(self, value: Any) -> float:
        number = evaluate(value, self.params)
        if not math.isfinite(number):
            raise FeatureError("Geometrická hodnota musí být konečné reálné číslo – "
                               "zkontroluj parametr nebo výraz.")
        return number

    def positive(self, feature: dict[str, Any], key: str, label: str) -> float:
        value = self.num(required(feature, key))
        if value <= 0:
            raise FeatureError(f"{label} musí být větší než 0 (je {value:g}).")
        return value

    def require_part(self, label: str) -> Part:
        if self.part is None:
            raise FeatureError(f"{label} potřebuje existující díl – nejdřív vytvoř těleso.")
        return self.part

    def sketch(self, feature: dict[str, Any]) -> tuple[Plane, Sketch]:
        sketch_id = required(feature, "sketch")
        if sketch_id not in self.sketches:
            raise FeatureError(f"Skica „{sketch_id}“ neexistuje nebo je v modelu až později.")
        return self.sketches[sketch_id]

    def apply(self, solid: Part, operation: str, label: str,
              empty_cut: str = "zkontroluj rovinu skici, směr („direction“) a hloubku", *,
              empty_add: str = "změň polohu nebo rozměry přídavku") -> None:
        """Přidá nebo odebere těleso ``solid`` z dílu podle ``operation``.

        ``empty_cut`` je rada pro uživatele, když řez nic neodebere."""
        if operation not in ("new", "add", "cut"):
            raise FeatureError(f"Neznámá operace „{operation}“, povolené: new, add, cut.")
        if operation == "new" and self.part is not None:
            raise FeatureError(
                f"{label}: díl už existuje. Použij \"operation\": \"add\" nebo \"cut\"."
            )
        if operation == "cut":
            self.require_part(label)
        try:
            before = inspect_volume(self.part) if self.part is not None else None
            tool = inspect_volume(solid)
            if operation == "cut":
                candidate = self.part - solid
                check_cut_volume(before.volume, candidate.volume, empty_cut)
            else:
                candidate = solid if self.part is None else self.part + solid
            result = tool if candidate is solid else inspect_volume(candidate)
            check_boolean(operation, before, tool, result,
                          empty_cut=empty_cut, empty_add=empty_add)
        except GeometryValidationError as exc:
            raise FeatureError(f"{label}: {exc}") from None
        except Exception as exc:  # noqa: BLE001 – jádro nesmí přijmout částečný výsledek
            raise FeatureError(f"{label}: geometrickou operaci se nepodařilo spočítat – "
                               "uprav polohu nebo rozměry prvku.") from exc
        self.part = candidate
        if self.recording is not None:
            self.recording.append((solid, "cut" if operation == "cut" else "add"))


@dataclass(frozen=True)
class FeatureType:
    name: str
    label_cz: str
    build: Callable[[BuildContext, dict[str, Any]], None]


FEATURE_TYPES: dict[str, FeatureType] = {}
# Každý 3D typ musí projít závěrečnou kontrolou i tehdy, když nevolá ctx.apply.
# Při novém typu aktualizuj klasifikaci (regrese hlídá celý současný registr).
VOLUME_FEATURES = frozenset(("extrude", "revolve", "sweep", "loft", "guided_loft",
                             "standard", "hole",
                             "pattern", "mirror", "fillet", "variable_fillet", "chamfer", "shell",
                             "move_face", "face_diameter", "step_import"))


def feature(name: str, label_cz: str):
    def register(build: Callable[[BuildContext, dict[str, Any]], None]):
        FEATURE_TYPES[name] = FeatureType(name, label_cz, build)
        return build

    return register


def required(feature: dict[str, Any], key: str) -> Any:
    if key not in feature:
        raise FeatureError(f"Chybí povinná hodnota „{key}“.")
    return feature[key]


def _choice(feature: dict[str, Any], key: str, allowed: tuple[str, ...], default: str) -> str:
    value = feature.get(key, default)
    if value not in allowed:
        raise FeatureError(
            f"„{key}“ má neznámou hodnotu „{value}“, povolené: {', '.join(allowed)}."
        )
    return value


# --- Skica -------------------------------------------------------------------


def _resolve_plane(ctx: BuildContext, feature: dict[str, Any]) -> Plane:
    name = feature.get("plane", "XY")
    if isinstance(name, dict):  # šikmá či zakřivená plocha vybraná ve 3D
        plane = face_plane_at(ctx.require_part("Skica na ploše dílu"), name)
    elif name in BASE_PLANES:
        plane = BASE_PLANES[name]
    elif name in FACE_DIRECTIONS:
        plane = face_plane(ctx.require_part(f"Skica na ploše „{name}“"), name)
    else:
        allowed = ", ".join([*BASE_PLANES, *FACE_DIRECTIONS])
        raise FeatureError(f"Neznámá rovina „{name}“, povolené: {allowed}.")
    offset_value = ctx.num(feature.get("offset", 0))
    return plane.offset(offset_value) if offset_value else plane


def sketch_plane(part: Part | None, feature: dict[str, Any], params: dict[str, float]) -> Plane:
    """Rovina skici ``feature`` na dílu ``part`` (pro skicář – promítnutí hran dílu)."""
    return _resolve_plane(BuildContext(params=params, part=part), feature)


def _point(ctx: BuildContext, value: Any, what: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise FeatureError(f"{what} musí být dvojice souřadnic [x, y].")
    return ctx.num(value[0]), ctx.num(value[1])


def _element(ctx: BuildContext, element: dict[str, Any], plane: Plane | None = None) -> Sketch:
    shape = required(element, "shape")
    x, y = _point(ctx, element.get("center", [0, 0]), "„center“")
    angle = ctx.num(element.get("angle", 0))
    place = Pos(x, y) * Rot(0, 0, angle)

    if shape == "rectangle":
        width = ctx.positive(element, "width", "Šířka obdélníku")
        height = ctx.positive(element, "height", "Výška obdélníku")
        radius = ctx.num(element.get("corner_radius", 0))
        if radius < 0 or radius >= min(width, height) / 2:
            raise FeatureError(
                f"Zaoblení rohů obdélníku R{radius:g} musí být mezi 0 a polovinou kratší strany."
            )
        base = RectangleRounded(width, height, radius) if radius else Rectangle(width, height)
        return Sketch() + place * base
    if shape == "circle":
        diameter = ctx.positive(element, "diameter", "Průměr kružnice")
        return Sketch() + place * Circle(diameter / 2)
    if shape == "circle_pattern":
        count = ctx.num(required(element, "count"))
        if count < 1 or count != int(count):
            raise FeatureError(f"Počet kružnic musí být celé kladné číslo (je {count:g}).")
        pitch = ctx.positive(element, "pitch_diameter", "Roztečný průměr")
        diameter = ctx.positive(element, "diameter", "Průměr kružnice")
        start = ctx.num(element.get("start_angle", 0))
        circles = PolarLocations(pitch / 2, int(count), start_angle=start) * Circle(diameter / 2)
        return Sketch() + [place * circle for circle in circles]
    if shape == "regular_polygon":
        sides = ctx.num(required(element, "sides"))
        if sides < 3 or sides != int(sides):
            raise FeatureError(f"Mnohoúhelník musí mít aspoň 3 strany (má {sides:g}).")
        diameter = ctx.positive(element, "diameter", "Opsaný průměr mnohoúhelníku")
        return Sketch() + place * RegularPolygon(diameter / 2, int(sides))
    if shape == "slot":
        length = ctx.positive(element, "length", "Rozteč středů drážky")
        width = ctx.positive(element, "width", "Šířka drážky")
        return Sketch() + place * SlotCenterToCenter(length, width)
    if shape == "polygon":
        raw_points = required(element, "points")
        if not isinstance(raw_points, list) or len(raw_points) < 3:
            raise FeatureError("Mnohoúhelník potřebuje aspoň 3 body v „points“.")
        points = [_point(ctx, point, "Bod mnohoúhelníku") for point in raw_points]
        return Sketch() + place * Polygon(*points, align=None)
    if shape == "profile":
        return Sketch() + place * _profile_face(ctx, element, plane, (x, y, angle))
    if shape == "steel":
        return Sketch() + place * _steel_section(element)
    raise FeatureError(
        f"Neznámý tvar „{shape}“, povolené: rectangle, circle, circle_pattern, "
        "regular_polygon, slot, polygon, profile, steel."
    )


def _steel_section(data: dict[str, Any]) -> Sketch:
    """Průřez ocelového profilu podle tabulek („section“: „IPE 100“, „L 50x5“ …)."""
    try:
        return section_sketch(str(required(data, "section")))
    except StandardError as exc:
        raise FeatureError(str(exc)) from None


def _profile_face(ctx: BuildContext, element: dict[str, Any], plane: Plane | None = None,
                  place: tuple[float, float, float] | None = None) -> Sketch:
    """Obrys z úseček, oblouků a kružnic: vyřešit vazby, seřadit do smyček a udělat plochu.

    Smyčka uvnitř jiné smyčky je díra, smyčka uvnitř díry zase materiál (jako v běžných
    CAD). Smyčky se nesmí křížit. S rovinou ``plane`` se promítnuté hrany spočítají znovu
    z dílu před skicou (díl se mohl změnit)."""
    if plane is not None and element.get("references"):
        try:
            element = refresh_references(element, ctx.part, plane, place, ctx.num)
        except ProjectionError as exc:
            raise FeatureError(str(exc)) from None
    try:
        solved = solve(element, ctx.num)
        found = loops(element, solved.points, solved.radii)
    except SolveError as exc:
        raise FeatureError(f"Obrys: {exc}") from None
    faces = [_loop_face(loop) for loop in found]
    order = sorted(range(len(faces)), key=lambda i: -faces[i].area)
    depth = {}
    for position, i in enumerate(order):
        depth[i] = 0
        for j in order[:position]:  # jen větší smyčky můžou tuhle obsahovat
            common = (faces[i] & faces[j]).area
            if common <= 1e-6 * faces[i].area:
                continue
            if abs(common - faces[i].area) > 1e-6 * faces[i].area:
                raise FeatureError("Smyčky obrysu se navzájem kříží – díra musí ležet celá "
                                   "uvnitř obrysu (nebo celá mimo něj).")
            depth[i] += 1
    result = Sketch()
    for i in sorted(order, key=lambda i: depth[i]):
        result = result + faces[i] if depth[i] % 2 == 0 else result - faces[i]
    if result.area <= 1e-9:
        raise FeatureError("Obrys nemá žádnou plochu – díry ho celý vyplnily.")
    return result


def profile_problem(element: dict[str, Any], params: dict[str, float]) -> str:
    """Proč z obrysu nejde udělat plocha (křížení smyček, nulová plocha …), "" = jde.
    Pro skicář – ukáže to hned při kreslení, ne až ve 3D."""
    try:
        _profile_face(BuildContext(params=params), element)
    except FeatureError as exc:
        return str(exc).removeprefix("Obrys: ")
    except Exception:  # noqa: BLE001 – kontrola nesmí shodit skicář
        return "Z obrysu nejde udělat plocha – zkontroluj, jestli se čáry nekříží."
    return ""


def _loop_face(loop: list[tuple]) -> Sketch:
    if loop[0][0] == "circle":
        _, (x, y), radius = loop[0]
        return Sketch() + Pos(x, y) * Circle(radius)
    edges = []
    for kind, start, end, *center in loop:
        if kind == "line":
            edges.append(Line(start, end))
        else:
            edges.append(ThreePointArc(start, arc_midpoint(start, end, center[0]), end))
    try:
        face = make_face(edges)
    except Exception:  # noqa: BLE001 – chyby jádra převádíme na lidskou zprávu
        face = None
    if face is None or not face.is_valid or face.area <= 1e-9:
        raise FeatureError("Obrys se kříží sám se sebou nebo nemá plochu – uprav body či vazby.")
    return Sketch() + face


MIN_AREA = 1e-6  # mm² – menší tvar skici je chyba rozměrů, ne geometrie
SHAPE_NAMES = {"rectangle": "obdélník", "circle": "kružnice",
               "circle_pattern": "kružnice na roztečí",
               "regular_polygon": "pravidelný mnohoúhelník", "slot": "drážka",
               "polygon": "mnohoúhelník", "profile": "obrys", "steel": "ocelový profil"}


@feature("sketch", "Skica")
def build_sketch(ctx: BuildContext, feature: dict[str, Any]) -> None:
    plane = _resolve_plane(ctx, feature)
    elements = required(feature, "elements")
    if not isinstance(elements, list) or not elements:
        raise FeatureError("Skica potřebuje neprázdný seznam „elements“.")
    sketch: Sketch | None = None
    for number, element in enumerate(elements, start=1):
        if not isinstance(element, dict):
            raise FeatureError("Každý tvar ve skice musí být objekt.")
        mode = _choice(element, "mode", ("add", "subtract"), "add")
        shape = _element(ctx, element, plane)
        if shape.area <= MIN_AREA:  # jinak by s ním skica tiše zahodila i ostatní tvary
            name = SHAPE_NAMES.get(element.get("shape"), "tvar")
            raise FeatureError(f"Tvar {number} skici ({name}) má nulovou plochu – zkontroluj "
                               "jeho rozměry (body mnohoúhelníku nesmí ležet na jedné přímce).")
        if mode == "add":
            sketch = shape if sketch is None else sketch + shape
        elif sketch is None:
            raise FeatureError("Skica musí začínat přidaným tvarem, ne odečtením.")
        else:
            sketch = sketch - shape
    if sketch is None or sketch.area <= 0:
        raise FeatureError("Skica nemá žádnou plochu.")
    ctx.sketches[feature["id"]] = (plane, sketch)


# --- Tělesa ze skici -----------------------------------------------------------


@feature("extrude", "Vysunutí")
def build_extrude(ctx: BuildContext, feature: dict[str, Any]) -> None:
    plane, sketch = ctx.sketch(feature)
    operation = _choice(
        feature, "operation", ("new", "add", "cut"), "new" if ctx.part is None else "add"
    )
    placed = plane * sketch

    if feature.get("through_all", False):
        if operation != "cut":
            raise FeatureError("„through_all“ jde použít jen s operací „cut“.")
        part = ctx.require_part("Řez skrz")
        reach = part.bounding_box().diagonal + (part.center() - plane.origin).length
        solid = extrude(placed, amount=reach, both=True)
    else:
        distance = ctx.positive(feature, "distance", "Vzdálenost vysunutí")
        direction = _choice(
            feature,
            "direction",
            ("normal", "reverse", "both"),
            "reverse" if operation == "cut" else "normal",
        )
        if direction == "normal":
            solid = extrude(placed, amount=distance)
        elif direction == "reverse":
            solid = extrude(placed, amount=distance, dir=-plane.z_dir)
        else:  # symetricky: celková tloušťka = distance
            solid = extrude(placed, amount=distance / 2, both=True)

    ctx.apply(solid, operation, "Vysunutí")


@feature("revolve", "Rotace")
def build_revolve(ctx: BuildContext, feature: dict[str, Any]) -> None:
    plane, sketch = ctx.sketch(feature)
    axis_name = _choice(feature, "axis", ("X", "Y", "Z"), "Z")
    angle = ctx.num(feature.get("angle", 360))
    if not 0 < angle <= 360:
        raise FeatureError(f"Úhel rotace musí být v rozsahu (0, 360] stupňů (je {angle:g}).")
    operation = _choice(
        feature, "operation", ("new", "add", "cut"), "new" if ctx.part is None else "add"
    )
    axis = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}[axis_name]
    try:
        solid = revolve(plane * sketch, axis=axis, revolution_arc=angle)
    except Exception as exc:  # noqa: BLE001 – chyby jádra převádíme na lidskou zprávu
        raise FeatureError(
            f"Rotace kolem osy {axis_name} se nepodařila – skica musí ležet v rovině "
            f"obsahující osu a nesmí ji křížit ({exc})."
        ) from None
    ctx.apply(solid, operation, "Rotace")


# --- Tažení po trase a přechod mezi profily -------------------------------------

SWEEP_PROFILES = ("circle", "rectangle", "steel", "sketch")


@feature("sweep", "Tažení")
def build_sweep(ctx: BuildContext, feature: dict[str, Any]) -> None:
    """Profil (kruh/trubka, obdélník/jekl, ocelový profil, skica) tažený po trase z bodů.

    Trasa je jako ohýbaná trubka: body [x, y, z] a poloměr ohybu v rozích (0 = ostrý
    roh, spoj na pokos). Profil se postaví kolmo na začátek trasy: střed (počátek skici)
    v prvním bodě, šířka vodorovně (u svislého začátku podél osy X). Uzavřená trasa
    (poslední bod = první) dá rám – táhne se po dvou polovinách, které se potkají uprostřed
    rovných stran, takže jsou na pokos všechny rohy (OCCT uzavřenou trasu neumí).
    """
    paths, sharp = _sweep_paths(ctx, feature)
    shape = _sweep_profile(ctx, feature)
    operation = _choice(
        feature, "operation", ("new", "add", "cut"), "new" if ctx.part is None else "add"
    )
    pieces = []
    for path in paths:
        start, tangent = path @ 0, path % 0
        x_dir = Vector(0, 0, 1).cross(tangent)
        if x_dir.length < 1e-9:  # trasa začíná svisle
            x_dir = Vector(1, 0, 0)
        plane = Plane(origin=start, x_dir=x_dir.normalized(), z_dir=tangent)
        try:
            piece = sweep(plane * shape, path,
                          transition=Transition.RIGHT if sharp else Transition.TRANSFORMED)
        except Exception as exc:  # noqa: BLE001 – chyby jádra převádíme na lidskou zprávu
            raise FeatureError(f"Tažení se nepodařilo ({type(exc).__name__}) – profil je asi "
                               "větší než poloměr ohybu, nebo se trasa kříží sama se sebou."
                               ) from None
        if not piece.is_valid or piece.volume <= 0:
            raise FeatureError("Tažení dalo poškozené těleso – profil je nejspíš větší než "
                               "poloměr ohybu (zvětši poloměr nebo zmenši profil).")
        pieces.append(piece)
    solid = pieces[0] if len(pieces) == 1 else pieces[0] + pieces[1]
    if not solid.is_valid:
        raise FeatureError("Tažení po uzavřené trase dalo poškozené těleso – zkontroluj, jestli "
                           "se trasa nekříží sama se sebou.")
    ctx.apply(solid, operation, "Tažení", empty_cut="zkontroluj trasu a velikost profilu")


def _sweep_paths(ctx: BuildContext, feature: dict[str, Any]) -> tuple[list[Any], bool]:
    """Trasa tažení (u uzavřené dvě poloviny) a zda má ostré rohy."""
    raw = required(feature, "path")
    if not isinstance(raw, list) or len(raw) < 2:
        raise FeatureError("Trasa tažení potřebuje aspoň 2 body [x, y, z].")
    points: list[Vector] = []
    for index, point in enumerate(raw, start=1):
        if not isinstance(point, list) or len(point) != 3:
            raise FeatureError(f"Bod trasy č. {index} musí být [x, y, z].")
        vector = Vector(*(ctx.num(v) for v in point))
        if points and (vector - points[-1]).length < 1e-6:
            raise FeatureError(f"Body trasy č. {index - 1} a {index} jsou stejné – odstraň "
                               "jeden z nich.")
        points.append(vector)
    radius = ctx.num(feature.get("bend_radius", 0))
    if radius < 0:
        raise FeatureError(f"Poloměr ohybu nesmí být záporný (je {radius:g}).")
    closed = len(points) > 3 and (points[-1] - points[0]).length < 1e-6
    if closed:
        ring = _without_straight(points[:-1], closed=True)
        if len(ring) < 3:
            raise FeatureError("Uzavřená trasa potřebuje aspoň 3 rohy.")
        start = (ring[0] + ring[1]) * 0.5  # začátek i konec uprostřed rovné strany
        loop = [start, *ring[1:], ring[0], start]
        half = len(loop) // 2
        middle = (loop[half - 1] + loop[half]) * 0.5
        pieces = [[*loop[:half], middle], [middle, *loop[half:]]]
    else:
        pieces = [_without_straight(points, closed=False)]
    paths = []
    for piece in pieces:
        if len(piece) == 2 or radius == 0:
            paths.append(Polyline(*piece))
            continue
        try:
            paths.append(FilletPolyline(*piece, radius=radius))
        except Exception:  # noqa: BLE001
            raise FeatureError(f"Ohyb R{radius:g} se nevejde mezi body trasy – zmenši poloměr "
                               "ohybu nebo body oddal.") from None
    sharp = radius == 0 and any(len(piece) > 2 for piece in pieces)
    return paths, sharp


def _without_straight(points: list[Vector], closed: bool) -> list[Vector]:
    """Body bez těch, které leží na přímce mezi sousedy (nejsou to rohy)."""
    kept = []
    count = len(points)
    for i, point in enumerate(points):
        if not closed and i in (0, count - 1):
            kept.append(point)
            continue
        before, after = points[i - 1], points[(i + 1) % count]
        if (point - before).normalized().cross((after - point).normalized()).length > 1e-9:
            kept.append(point)
    return kept


def _sweep_profile(ctx: BuildContext, feature: dict[str, Any]) -> Sketch:
    kind = _choice(feature, "profile", SWEEP_PROFILES, "circle")
    wall = ctx.num(feature["wall"]) if feature.get("wall") not in (None, 0) else 0.0
    if wall < 0:
        raise FeatureError(f"Tloušťka stěny nesmí být záporná (je {wall:g}).")
    if kind == "sketch":
        _, sketch = ctx.sketch(feature)
        return sketch
    if kind == "steel":
        return _steel_section(feature)
    if kind == "circle":
        diameter = ctx.positive(feature, "diameter", "Průměr profilu")
        if wall and wall >= diameter / 2:
            raise FeatureError(f"Stěna {wall:g} mm je pro trubku Ø{diameter:g} moc tlustá "
                               "(musí být menší než poloměr).")
        shape = Circle(diameter / 2)
        return shape - Circle(diameter / 2 - wall) if wall else shape
    width = ctx.positive(feature, "width", "Šířka profilu")
    height = ctx.positive(feature, "height", "Výška profilu")
    if wall and 2 * wall >= min(width, height):
        raise FeatureError(f"Stěna {wall:g} mm je pro jekl {width:g} × {height:g} moc tlustá.")
    shape = Rectangle(width, height)
    return shape - Rectangle(width - 2 * wall, height - 2 * wall) if wall else shape


@feature("guided_loft", "Řízený přechod")
def build_guided_loft(ctx: BuildContext, feature: dict[str, Any]) -> None:
    operation = _choice(feature, "operation", ("new", "add", "cut"),
                        "new" if ctx.part is None else "add")
    try:
        geometry = guided_loft.prepare(feature, ctx.sketches, ctx.num)
        candidate = guided_loft.build(geometry)
    except guided_loft.GuidedLoftError as exc:
        raise FeatureError(str(exc)) from None
    ctx.apply(candidate, operation, "Řízený přechod", empty_cut="zkontroluj polohu obou skic")


@feature("loft", "Přechod")
def build_loft(ctx: BuildContext, feature: dict[str, Any]) -> None:
    """Plynulý přechod mezi dvěma a více skicami (v pořadí), plný nebo dutý se stěnou."""
    if "wall_mode" in feature:
        _choice(feature, "wall_mode", ("normal", "sections"), "normal")
    sections = _loft_sections(ctx, feature)
    ruled = bool(feature.get("ruled", False))
    operation = _choice(
        feature, "operation", ("new", "add", "cut"), "new" if ctx.part is None else "add"
    )
    try:
        solid = loft(sections, ruled=ruled)
    except Exception as exc:  # noqa: BLE001
        raise FeatureError(f"Přechod se nepodařil ({type(exc).__name__}) – skici musí ležet "
                           "v různých rovinách a nesmí se křížit.") from None
    if not solid.is_valid or solid.volume <= 0:
        raise FeatureError("Přechod dal poškozené těleso – zkontroluj pořadí a polohu skic.")
    if feature.get("wall") not in (None, 0):
        solid = _hollow_loft(ctx, feature, sections, solid, ruled)
    ctx.apply(solid, operation, "Přechod", empty_cut="zkontroluj polohu skic")


def _loft_sections(ctx: BuildContext, feature: dict[str, Any]) -> list[Any]:
    ids = required(feature, "sketches")
    if not isinstance(ids, list) or len(ids) < 2:
        raise FeatureError("Přechod potřebuje aspoň 2 skici (v pořadí, třeba dole a nahoře).")
    sections = []
    for sketch_id in ids:
        if sketch_id not in ctx.sketches:
            raise FeatureError(f"Skica „{sketch_id}“ neexistuje nebo je v modelu až později.")
        plane, sketch = ctx.sketches[sketch_id]
        faces = sketch.faces()
        if len(faces) != 1 or faces[0].inner_wires():
            raise FeatureError(f"Skica „{sketch_id}“ pro přechod musí mít jeden obrys bez děr "
                               "(dutý přechod zadej tloušťkou stěny).")
        sections.append(plane * faces[0])
    return sections


def _hollow_loft(ctx: BuildContext, feature: dict[str, Any], sections: list[Any],
                 solid: Part, ruled: bool) -> Part:
    if "wall_mode" in feature:
        return _explicit_hollow_loft(ctx, feature, sections, solid, ruled)
    return _legacy_hollow_loft(ctx, feature, sections, solid, ruled)


def _explicit_hollow_loft(ctx: BuildContext, feature: dict[str, Any], sections: list[Any],
                          solid: Part, ruled: bool) -> Part:
    """Výslovný režim nikdy nepřepíná způsob konstrukce stěny."""
    wall = ctx.positive(feature, "wall", "Tloušťka stěny")
    mode = feature["wall_mode"]
    before = inspect_volume(solid)
    if before.solids != 1:
        raise FeatureError("Dutý přechod potřebuje právě jedno souvislé těleso.")
    if mode == "normal":
        try:
            ends = [face for face in solid.faces() if face.geom_type.name == "PLANE"
                    and any(_coplanar(face, section) for section in (sections[0], sections[-1]))]
            if len(ends) != 2:
                raise ValueError("přechod nemá právě dvě čela")
            candidate = offset(solid, amount=-wall, openings=ends)
            check_modification(before, inspect_volume(candidate), shell=True)
            check_normal_wall(solid, candidate, ends, wall)
        except Exception as exc:  # noqa: BLE001 – jádro ani kontrola nesmí změnit režim
            raise FeatureError(
                f"Přechod se stěnou {wall:g} mm kolmo ke stěně se nepodařil – "
                "zmenši tloušťku nebo výslovně zvol „V rovinách skic“ "
                "(kolmo k šikmé stěně pak může být materiál tenčí)."
            ) from exc
        return candidate
    try:
        inner_faces = []
        for section in sections:
            inner = offset(section, amount=-wall, kind=Kind.INTERSECTION)
            faces = inner.faces()
            if (len(faces) != 1 or faces[0].inner_wires() or not faces[0].is_valid
                    or not 0 < faces[0].area < section.area):
                raise ValueError("vnitřní profil se rozpadl nebo nezmenšil")
            inner_faces.append(faces[0])
        tool = loft(inner_faces, ruled=ruled)
        tool_facts = inspect_volume(tool)
        if tool_facts.solids != 1:
            raise ValueError("vnitřní přechod se rozpadl")
        candidate = solid - tool
        after = inspect_volume(candidate)
        check_modification(before, after, shell=True)
        tolerance = max(volume_tolerance(before.volume, after.volume), tool_facts.volume * 1e-7)
        if abs(before.volume - after.volume - tool_facts.volume) > tolerance:
            raise ValueError("vnitřní přechod vyčnívá mimo vnější těleso")
    except Exception as exc:  # noqa: BLE001 – neplatný 2D profil nebo výsledek jádra
        raise FeatureError(
            f"Přechod se stěnou {wall:g} mm v rovinách skic se nepodařil – "
            "zmenši tloušťku nebo uprav profily (vnitřní přechod se musí vejít do vnějšího)."
        ) from exc
    return candidate


def _legacy_hollow_loft(ctx: BuildContext, feature: dict[str, Any], sections: list[Any],
                       solid: Part, ruled: bool) -> Part:
    """Dutý přechod s otevřenými konci. Stěna je kolmá k povrchu (jako plech); kde to jádro
    neumí (přechod kruh ↔ hranatý tvar), měří se v rovinách skic."""
    wall = ctx.positive(feature, "wall", "Tloušťka stěny")
    ends = [face for face in solid.faces() if face.geom_type.name == "PLANE"
            and any(_coplanar(face, section) for section in (sections[0], sections[-1]))]
    lateral = solid.area - sum(face.area for face in ends)
    try:
        shell = offset(solid, amount=-wall, openings=ends)
        if (shell.is_valid and 0 < shell.volume < solid.volume
                and abs(shell.volume - lateral * wall) < 0.25 * lateral * wall):
            return shell
    except Exception:  # noqa: BLE001 – jádro neumí, zkusí se stěna v rovinách skic
        pass
    try:
        inner = [offset(section, amount=-wall, kind=Kind.INTERSECTION) for section in sections]
        hollow = solid - loft([face for shape in inner for face in shape.faces()], ruled=ruled)
    except Exception:  # noqa: BLE001
        hollow = None
    if hollow is None or not hollow.is_valid or not 0 < hollow.volume < solid.volume:
        raise FeatureError(f"Dutý přechod se stěnou {wall:g} mm se nepodařil – stěna je asi "
                           "tlustší než nejužší místo skic.")
    return hollow


def _coplanar(face: Any, section: Any) -> bool:
    normal = section.normal_at()
    return (abs(abs(face.normal_at().dot(normal)) - 1) < 1e-6
            and abs((face.center() - section.center()).dot(normal)) < 1e-6)


# --- Úpravy hran a stěn ----------------------------------------------------------


def _modification_input(ctx: BuildContext, label: str) -> tuple[Part, VolumeFacts]:
    part = ctx.require_part(label)
    try:
        return part, inspect_volume(part)
    except GeometryValidationError as exc:
        raise FeatureError(f"{label}: {exc}") from None


def _accept_modification(ctx: BuildContext, candidate: Part, before: VolumeFacts,
                         label: str, *, shell: bool = False) -> None:
    try:
        check_modification(before, inspect_volume(candidate), shell=shell)
    except GeometryValidationError as exc:
        raise FeatureError(f"{label}: {exc}") from None
    ctx.part = candidate


@feature("fillet", "Zaoblení")
def build_fillet(ctx: BuildContext, feature: dict[str, Any]) -> None:
    part, before = _modification_input(ctx, "Zaoblení")
    radius = ctx.positive(feature, "radius", "Poloměr zaoblení")
    edges = select_edges(part, required(feature, "edges"), ctx.num)
    try:
        candidate = fillet(edges, radius)
    except Exception:  # noqa: BLE001
        raise FeatureError(
            f"Zaoblení R{radius:g} se nepodařilo na {len(edges)} hranách – poloměr je "
            "nejspíš větší, než dovoluje okolní geometrie."
        ) from None
    _accept_modification(ctx, candidate, before, "Zaoblení")


@feature("variable_fillet", "Proměnné zaoblení")
def build_variable_fillet(ctx: BuildContext, feature: dict[str, Any]) -> None:
    part, before = _modification_input(ctx, "Proměnné zaoblení")
    start = ctx.positive(feature, "radius_start", "Počáteční poloměr R1")
    end = ctx.positive(feature, "radius_end", "Koncový poloměr R2")
    edges = select_edges(part, required(feature, "edges"), ctx.num)
    if len(edges) != 1:
        raise FeatureError("Proměnné zaoblení potřebuje právě jednu přímou hranu.")
    try:
        variable_fillet.check_origin(ctx.history, edges[0], feature.get("origin"))
        candidate = variable_fillet.apply(part, edges[0], start, end,
            feature.get("direction"), feature.get("reverse", False), feature.get("normals"))
    except (variable_fillet.VariableFilletError, GeometryValidationError) as exc:
        raise FeatureError(f"Proměnné zaoblení: {exc}") from None
    _accept_modification(ctx, candidate, before, "Proměnné zaoblení")


@feature("chamfer", "Sražení")
def build_chamfer(ctx: BuildContext, feature: dict[str, Any]) -> None:
    part, before = _modification_input(ctx, "Sražení")
    distance = ctx.positive(feature, "distance", "Velikost sražení")
    edges = select_edges(part, required(feature, "edges"), ctx.num)
    try:
        candidate = chamfer(edges, distance)
    except Exception:  # noqa: BLE001
        raise FeatureError(
            f"Sražení {distance:g} mm se nepodařilo na {len(edges)} hranách – je nejspíš "
            "větší, než dovoluje okolní geometrie."
        ) from None
    _accept_modification(ctx, candidate, before, "Sražení")


@feature("shell", "Skořepina")
def build_shell(ctx: BuildContext, feature: dict[str, Any]) -> None:
    part, before = _modification_input(ctx, "Skořepina")
    thickness = ctx.positive(feature, "thickness", "Tloušťka stěny")
    open_faces = feature.get("open_faces", [])
    if not isinstance(open_faces, list):
        raise FeatureError("„open_faces“ musí být seznam ploch, např. [\"top\"].")
    if not open_faces:
        raise FeatureError("Skořepina potřebuje alespoň jednu otevřenou plochu – "
                           "vyber plochu, kterou chceš odstranit.")
    openings = [face for name in open_faces for face in select_faces(part, name)]
    try:
        candidate = offset(part, amount=-thickness, openings=openings)
    except Exception:  # noqa: BLE001
        raise FeatureError(
            f"Skořepina s tloušťkou {thickness:g} mm se nepodařila – stěna je nejspíš "
            "silnější, než dovolují zaoblení nebo malé detaily dílu."
        ) from None
    _accept_modification(ctx, candidate, before, "Skořepina", shell=True)


# --- Přímé úpravy ploch (P2) ---------------------------------------------------------------


DIRECT_EDIT_TYPES = {"move_face": "plane", "face_diameter": "cylinder"}


def _edited_face(ctx: BuildContext, feature: dict[str, Any], label: str) -> tuple[Face, Vector]:
    """Plocha přímé úpravy: odkaz významem (P1.3) + pojistka původu (P2.2, H2–H4)."""
    spec = required(feature, "face")
    wanted = DIRECT_EDIT_TYPES[feature["type"]]
    if not isinstance(spec, dict) or spec.get("type") != wanted:
        raise FeatureError(f"{label}: „face“ musí být plocha {{\"at\": [x, y, z], \"normal\": "
                           f"[nx, ny, nz], \"type\": \"{wanted}\"}} – vyber ji ve 3D.")
    face, point = find_face(ctx.part, spec)
    try:
        check_origin(ctx.history, face, point, feature.get("origin"), label)
    except DirectEditError as exc:
        raise FeatureError(str(exc)) from None
    return face, point


@feature("move_face", "Posunutí plochy")
def build_move_face(ctx: BuildContext, feature: dict[str, Any]) -> None:
    label = "Posunutí plochy"
    _modification_input(ctx, label)
    distance = ctx.num(required(feature, "distance"))
    face, point = _edited_face(ctx, feature, label)
    try:
        ctx.part = direct_move_face(ctx.part, face, point, distance, label)
    except DirectEditError as exc:
        raise FeatureError(str(exc)) from None


@feature("face_diameter", "Průměr plochy")
def build_face_diameter(ctx: BuildContext, feature: dict[str, Any]) -> None:
    label = "Průměr plochy"
    _modification_input(ctx, label)
    diameter = ctx.num(required(feature, "diameter"))
    face, point = _edited_face(ctx, feature, label)
    try:
        ctx.part = set_diameter(ctx.part, face, point, diameter, label)
    except DirectEditError as exc:
        raise FeatureError(str(exc)) from None


# --- Normalizované díly ----------------------------------------------------------------


@feature("standard", "Normalizovaný díl")
def build_standard(ctx: BuildContext, feature: dict[str, Any]) -> None:
    """Šroub, matice, podložka, ložisko, kolík, pero nebo tyč z ocelového profilu podle
    tabulek – stojí na rovině v zadaných polohách. Odebrání vyřízne kapsu (obrys bez děr,
    o vůli větší); „reverse“ díl otočí do materiálu (kapsa na matici)."""
    kind = _choice(feature, "kind", tuple(STANDARD_KINDS), "socket_screw")
    spec = STANDARD_KINDS[kind]
    length = ctx.num(required(feature, "length")) if spec.length else None
    operation = _choice(
        feature, "operation", ("new", "add", "cut"), "new" if ctx.part is None else "add"
    )
    clearance = ctx.num(feature.get("clearance", 0)) if operation == "cut" else 0.0
    plane = _resolve_plane(ctx, feature)
    positions = feature.get("positions", [[0, 0]])
    if not isinstance(positions, list) or not positions:
        raise FeatureError("Normalizovaný díl potřebuje aspoň jednu polohu v „positions“, "
                           "např. [[0, 0]].")
    points = [_point(ctx, point, "Poloha dílu") for point in positions]
    flipped = _choice(feature, "direction", ("normal", "reverse"), "normal") == "reverse"
    angle = ctx.num(feature.get("angle", 0))
    try:
        shape = part_shape(kind, str(required(feature, "size")), length,
                           pocket=operation == "cut", clearance=clearance)
    except StandardError as exc:
        raise FeatureError(str(exc)) from None
    if flipped:
        shape = shape.mirror(Plane.XY)
    shape = Rot(0, 0, angle) * shape
    tools = [plane * Pos(x, y) * shape for x, y in points]
    ctx.apply(tools[0] if len(tools) == 1 else Part() + tools, operation, "Normalizovaný díl",
              empty_cut="díl leží mimo materiál – pro kapsu ho otoč do materiálu "
                        "(„Otočit do materiálu“) nebo zkontroluj rovinu a polohy")


# --- Díry --------------------------------------------------------------------------

_TOP = (Align.CENTER, Align.CENTER, Align.MAX)  # horní podstava v z = 0, těleso jde do −Z


def _hole_tool(shape: HoleShape, length: float) -> Part:
    """Těleso, které se z dílu odebere: osa Z, povrch v z = 0, díra míří do −Z."""
    radius = shape.diameter / 2
    tool = Cylinder(radius, length, align=_TOP)
    if shape.point:
        tool += Pos(0, 0, -length) * Cone(0, radius, point_height(shape.diameter), align=_TOP)
    if shape.counterbore:
        big, deep = shape.counterbore
        tool += Cylinder(big / 2, deep, align=_TOP)
    if shape.countersink:
        big = shape.countersink / 2
        tool += Cone(radius, big, big - radius, align=_TOP)
    return tool


def _thread_tool(shape: HoleShape, length: float) -> Part:
    """Šroubovicová drážka vymodelovaného závitu (osa Z, povrch v z = 0, do −Z).

    Drážka začíná kousek nad dnem díry (nevyčnívá pod něj) a končí jednu otáčku nad
    povrchem, aby závit na povrchu čistě vyústil."""
    profile = shape.modeled
    thread_length = shape.thread_depth if shape.thread_depth is not None else length
    z_start = -thread_length + profile.inner_width / 2 + 0.05 * profile.pitch
    try:
        return thread_groove(profile, round(z_start, 6), profile.pitch)
    except Exception:  # noqa: BLE001 – chyby jádra převádíme na lidskou zprávu
        raise FeatureError("Závit se nepodařilo vymodelovat – zkus jinou velikost nebo "
                           "hloubku závitu.") from None


@feature("hole", "Díra")
def build_hole(ctx: BuildContext, feature: dict[str, Any]) -> None:
    part = ctx.require_part("Díra")
    plane = _resolve_plane(ctx, feature)
    kind = _choice(feature, "kind", tuple(HOLE_KINDS), "tapped")
    positions = feature.get("positions", [[0, 0]])
    if not isinstance(positions, list) or not positions:
        raise FeatureError("Díra potřebuje aspoň jednu polohu v „positions“, např. [[0, 0]].")
    points = [_point(ctx, point, "Poloha díry") for point in positions]

    def optional(key: str) -> float | None:
        return ctx.num(feature[key]) if key in feature else None

    through_all = bool(feature.get("through_all", False))
    try:
        shape = hole_shape(kind, str(required(feature, "size")), feature.get("fit", "medium"),
                           depth=optional("depth"), through_all=through_all,
                           thread_depth=optional("thread_depth"),
                           diameter=optional("diameter"),
                           modeled_thread=bool(feature.get("modeled_thread", False)),
                           print_clearance=optional("print_clearance"))
    except HoleError as exc:
        raise FeatureError(str(exc)) from None
    if shape.diameter <= 0:
        raise FeatureError("Průměr díry musí být větší než 0.")
    length = shape.depth if shape.depth is not None else _depth_through(part, plane)
    tool = _hole_tool(shape, length)
    tools = [plane * Pos(x, y) * tool for x, y in points]
    ctx.apply(tools[0] if len(tools) == 1 else Part() + tools, "cut", "Díra")
    if shape.modeled:  # drážku až po vyvrtání jádra – spojovat ji s jádrem je nespolehlivé
        groove = _thread_tool(shape, length)
        grooves = [plane * Pos(x, y) * groove for x, y in points]
        ctx.apply(grooves[0] if len(grooves) == 1 else Part() + grooves, "cut", "Závit")


def _depth_through(part: Part, plane: Plane) -> float:
    """Hloubka „skrz celý díl“: jak daleko pod rovinou (proti normále) díl sahá + 1 mm.

    Počítá se z rohů obalového kvádru – díra tak není zbytečně dlouhá (vymodelovaný
    závit má počet závitů podle délky)."""
    box = part.bounding_box()
    corners = [Vector(x, y, z) for x in (box.min.X, box.max.X) for y in (box.min.Y, box.max.Y)
               for z in (box.min.Z, box.max.Z)]
    reach = max((plane.origin - corner).dot(plane.z_dir) for corner in corners)
    return max(reach, 0.0) + 1.0


# --- Pole a zrcadlení ----------------------------------------------------------------

# Prvky, které přidávají nebo ubírají materiál – jen ty jde opakovat v poli a zrcadlit.
REPEATABLE_FEATURES = ("extrude", "revolve", "sweep", "loft", "guided_loft", "standard",
                       "hole", "pattern", "mirror")
PATTERN_KINDS = ("circular", "linear")
MAX_COPIES = 500
_AXES = {"X": Vector(1, 0, 0), "Y": Vector(0, 1, 0), "Z": Vector(0, 0, 1)}


def _whole_count(ctx: BuildContext, feature: dict[str, Any], key: str, label: str,
                 default: int | None = None) -> int:
    value = ctx.num(feature[key]) if key in feature else default
    if value is None:
        raise FeatureError(f"Chybí povinná hodnota „{key}“ ({label.lower()}).")
    if value < 1 or value != int(value):
        raise FeatureError(f"{label} musí být celé kladné číslo (je {value:g}).")
    return int(value)


def _source_operations(ctx: BuildContext, feature: dict[str, Any],
                       label: str) -> list[Operation]:
    """Operace prvků, které má pole/zrcadlení opakovat – v pořadí, jak vznikly v modelu."""
    ids = feature.get("features")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
        raise FeatureError(f"{label}: vyber prvky, které se mají opakovat (např. díru nebo "
                           "výřez) – „features“: [\"dira1\"].")
    for feature_id in ids:
        if feature_id not in ctx.operations:
            raise FeatureError(f"{label}: prvek „{feature_id}“ neexistuje nebo je ve stromu až "
                               "za tímto prvkem (případně má chybu).")
        if not ctx.operations[feature_id]:
            raise FeatureError(
                f"{label}: prvek „{feature_id}“ sám nepřidává ani neubírá materiál (skica, "
                "zaoblení, sražení, skořepina, přímá úprava plochy). Opakovat jde vysunutí, "
                "rotace, díry, pole a zrcadlení – zaoblení dej do stromu až za tento prvek.")
    wanted = set(ids)
    return [op for feature_id, ops in ctx.operations.items() if feature_id in wanted
            for op in ops]


def _repeat(ctx: BuildContext, operations: list[Operation],
            transforms: list[Callable[[Part], Part]], label: str, empty_cut: str) -> None:
    """Každou operaci zopakuje na všech kopiích (kopie jedné operace najednou)."""
    for solid, mode in operations:
        copies = [transform(solid) for transform in transforms]
        ctx.apply(copies[0] if len(copies) == 1 else Part() + copies, mode, label, empty_cut)


def _pattern_transforms(ctx: BuildContext,
                        feature: dict[str, Any]) -> list[Callable[[Part], Part]]:
    kind = _choice(feature, "kind", PATTERN_KINDS, "circular")
    if kind == "circular":
        count = _whole_count(ctx, feature, "count", "Počet kopií")
        axis_name = _choice(feature, "axis", tuple(_AXES), "Z")
        raw = feature.get("center", [0, 0, 0])
        if not isinstance(raw, (list, tuple)) or len(raw) != 3:
            raise FeatureError("Bod na ose („center“) musí být trojice souřadnic [x, y, z].")
        axis = Axis(tuple(ctx.num(v) for v in raw), tuple(_AXES[axis_name]))
        angle = ctx.num(feature.get("angle", 360))
        if not 0 < angle <= 360:
            raise FeatureError(f"Celkový úhel pole musí být v rozsahu (0, 360] stupňů "
                               f"(je {angle:g}).")
        if count < 2:
            raise FeatureError("Pole potřebuje aspoň 2 kusy (počet je včetně původního).")
        # Celý kruh: kopie rovnoměrně dokola. Výseč: první a poslední kus na krajích úhlu.
        step = angle / count if abs(angle - 360) < 1e-9 else angle / (count - 1)
        angles = [step * k for k in range(1, count)]
        return [lambda s, a=a: s.rotate(axis, a) for a in angles]

    directions = [(_choice(feature, "direction", tuple(_AXES), "X"), "count", "spacing", "")]
    if feature.get("direction2") is not None:
        directions.append((_choice(feature, "direction2", tuple(_AXES), "Y"), "count2",
                           "spacing2", " ve druhém směru"))
        if directions[1][0] == directions[0][0]:
            raise FeatureError("Druhý směr mřížky musí být jiný než první.")
    steps = [[Vector()]]
    for axis_name, count_key, spacing_key, where in directions:
        count = _whole_count(ctx, feature, count_key, f"Počet kusů{where}")
        spacing = ctx.num(required(feature, spacing_key)) if count > 1 else 0.0
        if count > 1 and abs(spacing) < 1e-9:
            raise FeatureError(f"Rozteč{where} nesmí být 0 – kopie by ležely na sobě.")
        steps.append([_AXES[axis_name] * (spacing * k) for k in range(count)])
    offsets = [a + b for a in steps[1] for b in (steps[2] if len(steps) > 2 else [Vector()])]
    offsets = offsets[1:]  # první je původní prvek
    if not offsets:
        raise FeatureError("Pole potřebuje aspoň 2 kusy (počet je včetně původního).")
    return [lambda s, v=v: s.moved(Location(v)) for v in offsets]


@feature("pattern", "Pole")
def build_pattern(ctx: BuildContext, feature: dict[str, Any]) -> None:
    ctx.require_part("Pole")
    transforms = _pattern_transforms(ctx, feature)
    if len(transforms) + 1 > MAX_COPIES:
        raise FeatureError(f"Pole má {len(transforms) + 1} kusů – víc než {MAX_COPIES} by se "
                           "počítalo velmi dlouho. Zmenši počet.")
    operations = _source_operations(ctx, feature, "Pole")
    _repeat(ctx, operations, transforms, "Pole",
            "kopie leží mimo díl, zkontroluj osu, směr, rozteč a počet")


@feature("step_import", "Import STEP")
def build_step_import(ctx: BuildContext, feature: dict[str, Any]) -> None:
    """Jediný uzavřený díl z ověřeného, do modelu vloženého STEP."""
    import time

    from build123d import Compound

    from skodacad.step_probe import StepProbeError, _inspect_step
    from skodacad.step_source import source_bytes
    from skodacad.step_task import StepTask
    from skodacad.worker import _STEP_PHASE, _shape_from

    if ctx.part is not None:
        raise FeatureError("Import STEP musí být prvním objemovým tělesem.")
    try:
        data = source_bytes(feature)
        if _STEP_PHASE is not None:
            _, shape = _inspect_step(data)
            part = Part(Compound([shape.solids()[0]]).wrapped)
        else:
            task = StepTask(data)
            try:
                while (result := task.poll()) is None:
                    time.sleep(0.02)
                if result.error:
                    raise StepProbeError(result.error)
                part = _shape_from(("Part", result.shape_bytes))
            finally:
                task.cancel()
        ctx.apply(part, "new", "Import STEP")
    except (StepProbeError, OSError) as exc:
        raise FeatureError(str(exc)) from exc


@feature("mirror", "Zrcadlení")
def build_mirror(ctx: BuildContext, feature: dict[str, Any]) -> None:
    part = ctx.require_part("Zrcadlení")
    plane = _resolve_plane(ctx, feature)
    if feature.get("features"):
        operations = _source_operations(ctx, feature, "Zrcadlení")
        _repeat(ctx, operations, [lambda s: s.mirror(plane)], "Zrcadlení",
                "zrcadlený prvek leží mimo díl nebo na stejném místě, zkontroluj rovinu")
        return
    ctx.apply(part.mirror(plane), "add", "Zrcadlení",  # celý díl: druhá polovina dílu
              empty_add="díl je podle této roviny už souměrný v mezích tolerance; "
                        "zvol jinou rovinu nebo ji posuň")


def short_label(feature: dict[str, Any]) -> str:
    """Druh a název prvku, např. „Díra „Upínání““."""
    label = FEATURE_TYPES[feature["type"]].label_cz if feature["type"] in FEATURE_TYPES else "?"
    name = feature.get("name")
    return f"{label} „{name}“" if name else f"{label} {feature['id']}"


def describe(feature: dict[str, Any], params: dict[str, float] | None = None) -> str:
    """Krátký popis prvku pro výpis stromu. S ``params`` se počty z výrazů vyčíslí."""
    text = short_label(feature)
    if feature["type"] == "hole" and isinstance(feature.get("size"), str):
        count = len(feature.get("positions") or [None])
        text += f" – {hole_summary(feature.get('kind', 'tapped'), feature['size'], count)}"
        if feature.get("modeled_thread"):
            text += " (vymodelovaný)"
    elif feature["type"] == "pattern":
        count = _plain(feature.get("count", "?"), params)
        if feature.get("kind", "circular") == "circular":
            text += f" – dokola, {count} ks"
        elif feature.get("direction2") is not None:
            text += f" – mřížka {count} × {_plain(feature.get('count2', '?'), params)} ks"
        else:
            text += f" – v řadě, {count} ks"
    elif feature["type"] == "mirror" and not feature.get("features"):
        text += " – celý díl"
    elif feature["type"] == "sweep":
        kind = feature.get("profile", "circle")
        hollow = feature.get("wall") not in (None, 0)
        if kind == "circle":
            diameter = _plain(feature.get("diameter", "?"), params)
            text += f" – {'trubka' if hollow else 'kruh'} Ø{diameter}"
        elif kind == "rectangle":
            text += (f" – {'jekl' if hollow else 'obdélník'} "
                     f"{_plain(feature.get('width', '?'), params)} × "
                     f"{_plain(feature.get('height', '?'), params)}")
        elif kind == "steel":
            text += f" – {STANDARD_KINDS['profile'].sizes.get(feature.get('section'), '?')}"
        else:
            text += f" – skica {feature.get('sketch', '?')}"
        if hollow and kind in ("circle", "rectangle"):
            text += f" × {_plain(feature['wall'], params)}"
        points = feature.get("path")
        if isinstance(points, list):
            text += f", trasa z {len(points)} {'bodu' if len(points) == 1 else 'bodů'}"
    elif feature["type"] == "standard":
        count = len(feature.get("positions") or [None])
        length = _plain(feature["length"], params) if "length" in feature else None
        part = standard_summary(feature.get("kind", "socket_screw"),
                                str(feature.get("size", "?")), length, count)
        text += f" – {part}"
        if feature.get("operation") == "cut":
            text += " (kapsa)"
    elif feature["type"] == "move_face" and "distance" in feature:
        value = _plain(feature["distance"], params)
        text += f" – o {value} mm"
    elif feature["type"] == "face_diameter" and "diameter" in feature:
        text += f" – na Ø{_plain(feature['diameter'], params)}"
    elif feature["type"] in ("loft", "guided_loft"):
        sketches = feature.get("sketches")
        count = len(sketches) if isinstance(sketches, list) else "?"
        text += f" – mezi {count} {'skicou' if count == 1 else 'skicami'}"
        if feature.get("wall") not in (None, 0):
            text += f", dutý {_plain(feature['wall'], params)} mm"
            if feature.get("wall_mode") == "normal":
                text += ", kolmo ke stěně"
            elif feature.get("wall_mode") == "sections":
                text += ", v rovinách skic"
    return text


def _plain(value: Any, params: dict[str, float] | None = None) -> str:
    """Číslo k popisu; výraz s parametry vyčíslí (když nejde, nechá text výrazu)."""
    if isinstance(value, str) and params is not None:
        try:
            value = evaluate(value, params)
        except Exception:  # noqa: BLE001 – popis nesmí nic shodit
            return value
    return f"{value:g}" if isinstance(value, (int, float)) else str(value)
