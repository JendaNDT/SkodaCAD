"""Prvky modelu (skica, vysunutí, rotace, zaoblení, …) a jejich výpočet.

Každý prvek je funkce ``(ctx, feature) -> None`` zaregistrovaná dekorátorem
``@feature``. Prvek čte své hodnoty z JSON objektu ``feature``, číselné
hodnoty vyhodnocuje přes ``ctx.num`` (umí výrazy s parametry) a výsledek
ukládá do ``ctx``. Chyby hlásí výjimkou ``FeatureError`` s českou zprávou.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from build123d import (
    Axis,
    Circle,
    Part,
    Plane,
    PolarLocations,
    Polygon,
    Pos,
    Rectangle,
    RectangleRounded,
    RegularPolygon,
    Rot,
    Sketch,
    SlotCenterToCenter,
    chamfer,
    extrude,
    fillet,
    offset,
    revolve,
)

from skodacad.expressions import evaluate
from skodacad.selectors import (
    BASE_PLANES,
    FACE_DIRECTIONS,
    face_plane,
    select_edges,
    select_faces,
)


class FeatureError(ValueError):
    """Prvek nejde spočítat (zpráva je česky pro uživatele)."""


@dataclass
class BuildContext:
    """Stav během přepočtu modelu."""

    params: dict[str, float]
    part: Part | None = None
    sketches: dict[str, tuple[Plane, Sketch]] = field(default_factory=dict)

    def num(self, value: Any) -> float:
        return evaluate(value, self.params)

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

    def apply(self, solid: Part, operation: str, label: str) -> None:
        """Přidá nebo odebere těleso ``solid`` z dílu podle ``operation``."""
        if operation == "new":
            if self.part is not None:
                raise FeatureError(
                    f"{label}: díl už existuje. Použij \"operation\": \"add\" nebo \"cut\"."
                )
            self.part = solid
        elif operation == "add":
            self.part = solid if self.part is None else self.part + solid
        elif operation == "cut":
            part = self.require_part(label)
            result = part - solid
            if abs(part.volume - result.volume) < 1e-9 * max(1.0, part.volume):
                raise FeatureError(
                    f"{label}: řez neodebral žádný materiál – zkontroluj rovinu skici, "
                    "směr („direction“) a hloubku."
                )
            self.part = result
        else:
            raise FeatureError(f"Neznámá operace „{operation}“, povolené: new, add, cut.")


@dataclass(frozen=True)
class FeatureType:
    name: str
    label_cz: str
    build: Callable[[BuildContext, dict[str, Any]], None]


FEATURE_TYPES: dict[str, FeatureType] = {}


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
    if name in BASE_PLANES:
        plane = BASE_PLANES[name]
    elif name in FACE_DIRECTIONS:
        plane = face_plane(ctx.require_part(f"Skica na ploše „{name}“"), name)
    else:
        allowed = ", ".join([*BASE_PLANES, *FACE_DIRECTIONS])
        raise FeatureError(f"Neznámá rovina „{name}“, povolené: {allowed}.")
    offset_value = ctx.num(feature.get("offset", 0))
    return plane.offset(offset_value) if offset_value else plane


def _point(ctx: BuildContext, value: Any, what: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise FeatureError(f"{what} musí být dvojice souřadnic [x, y].")
    return ctx.num(value[0]), ctx.num(value[1])


def _element(ctx: BuildContext, element: dict[str, Any]) -> Sketch:
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
    raise FeatureError(
        f"Neznámý tvar „{shape}“, povolené: rectangle, circle, circle_pattern, "
        "regular_polygon, slot, polygon."
    )


@feature("sketch", "Skica")
def build_sketch(ctx: BuildContext, feature: dict[str, Any]) -> None:
    plane = _resolve_plane(ctx, feature)
    elements = required(feature, "elements")
    if not isinstance(elements, list) or not elements:
        raise FeatureError("Skica potřebuje neprázdný seznam „elements“.")
    sketch: Sketch | None = None
    for element in elements:
        if not isinstance(element, dict):
            raise FeatureError("Každý tvar ve skice musí být objekt.")
        mode = _choice(element, "mode", ("add", "subtract"), "add")
        shape = _element(ctx, element)
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


# --- Úpravy hran a stěn ----------------------------------------------------------


@feature("fillet", "Zaoblení")
def build_fillet(ctx: BuildContext, feature: dict[str, Any]) -> None:
    part = ctx.require_part("Zaoblení")
    radius = ctx.positive(feature, "radius", "Poloměr zaoblení")
    edges = select_edges(part, required(feature, "edges"), ctx.num)
    try:
        ctx.part = fillet(edges, radius)
    except Exception:  # noqa: BLE001
        raise FeatureError(
            f"Zaoblení R{radius:g} se nepodařilo na {len(edges)} hranách – poloměr je "
            "nejspíš větší, než dovoluje okolní geometrie."
        ) from None


@feature("chamfer", "Sražení")
def build_chamfer(ctx: BuildContext, feature: dict[str, Any]) -> None:
    part = ctx.require_part("Sražení")
    distance = ctx.positive(feature, "distance", "Velikost sražení")
    edges = select_edges(part, required(feature, "edges"), ctx.num)
    try:
        ctx.part = chamfer(edges, distance)
    except Exception:  # noqa: BLE001
        raise FeatureError(
            f"Sražení {distance:g} mm se nepodařilo na {len(edges)} hranách – je nejspíš "
            "větší, než dovoluje okolní geometrie."
        ) from None


@feature("shell", "Skořepina")
def build_shell(ctx: BuildContext, feature: dict[str, Any]) -> None:
    part = ctx.require_part("Skořepina")
    thickness = ctx.positive(feature, "thickness", "Tloušťka stěny")
    open_faces = feature.get("open_faces", [])
    if not isinstance(open_faces, list):
        raise FeatureError("„open_faces“ musí být seznam ploch, např. [\"top\"].")
    openings = [face for name in open_faces for face in select_faces(part, name)]
    try:
        ctx.part = offset(part, amount=-thickness, openings=openings)
    except Exception:  # noqa: BLE001
        raise FeatureError(
            f"Skořepina s tloušťkou {thickness:g} mm se nepodařila – stěna je nejspíš "
            "silnější, než dovolují zaoblení nebo malé detaily dílu."
        ) from None


def describe(feature: dict[str, Any]) -> str:
    """Krátký popis prvku pro výpis stromu."""
    label = FEATURE_TYPES[feature["type"]].label_cz if feature["type"] in FEATURE_TYPES else "?"
    name = feature.get("name")
    return f"{label} „{name}“" if name else f"{label} {feature['id']}"
