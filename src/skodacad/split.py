"""Rozříznutí dílu rovinou (P6.17, návrh ``docs/p6-17-rozriznuti.md``).

Z jednoho návrhu krabičky vzniknou základna a víčko: rovina rozdělí díl a ponechá se strana nad
rovinou (po normále), pod ní, nebo obě části, které se odsunou o zadanou mezeru. Řez je přesný
(jádro ``split`` z build123d), objem se vždy ověří – součet částí musí dát původní objem.

Rovina, která díl neprotíná (celý díl by zůstal, nebo by nezbylo nic), se **odmítne** s českou
radou; nic se potichu neodřízne ani nezahodí.

Lem a drážka (P6.18): při ``both`` jde u řezu přidat **lem** na základně a odpovídající **drážku**
ve víčku. Oba se odvodí z obrysu řezu (průřez stěn rovinou), takže se s výškou řezu přizpůsobí
samy a nepotřebují odkazy na plochy. Lem je pás šířky ``width`` podél vnitřního (``inner``) nebo
vnějšího (``outer``) okraje řezu, vysoký ``height``; drážka je týž pás o ``clearance`` širší
a hlubší.

Rozložení pro tisk (P6.19): při ``arrange`` ``print`` se víčko otočí o 180° kolem osy roviny řezu
(otevřená strana nahoru, strop na desce), položí na stejnou úroveň jako dno základny a odsune
vedle ní o ``gap``. Obě části tak jdou rovnou vytisknout na jedné desce.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from build123d import (
    Axis,
    Compound,
    Face,
    GeomType,
    Keep,
    Kind,
    Location,
    Part,
    Plane,
    extrude,
    offset,
    split,
)

KEEP = ("above", "below", "both")
FEATURE_KEYS = {"id", "type", "name", "plane", "offset", "keep", "gap", "lip_width",
                "lip_height", "lip_side", "lip_clearance", "arrange"}
ARRANGE = ("stack", "print")
LIP_SIDES = ("inner", "outer")
DEFAULT_CLEARANCE = 0.2  # mm, běžná vůle pro tisk FDM
SIDE_NAMES = {"above": "nad rovinou", "below": "pod rovinou"}
MAX_GAP = 10000.0  # mm


class SplitError(ValueError):
    """Český důvod odmítnutí rozříznutí."""


def validate(feature: dict[str, Any]) -> None:
    """Kontrola struktury zapsaného prvku (bez vyhodnocení výrazů a bez dílu)."""
    unknown = set(feature) - FEATURE_KEYS
    if unknown:
        raise SplitError("Rozříznutí: neznámý klíč " + ", ".join(sorted(map(str, unknown))) + ".")
    keep = feature.get("keep", "below")
    if keep not in KEEP:
        raise SplitError("Ponechaná část („keep“) musí být „above“ (nad rovinou), „below“ "
                         "(pod rovinou) nebo „both“ (obě).")
    gap = feature.get("gap")
    if gap not in (None, ""):
        if keep != "both":
            raise SplitError("Mezeru („gap“) jde zadat jen při ponechání obou částí („both“).")
        if isinstance(gap, bool) or not isinstance(gap, (int, float, str)):
            raise SplitError("„gap“ musí být číslo nebo výraz.")
    arrange = feature.get("arrange", "stack")
    if arrange not in ARRANGE:
        raise SplitError("Rozložení („arrange“) musí být „stack“ (nad sebou) nebo „print“ "
                         "(pro tisk vedle sebe).")
    if arrange == "print" and keep != "both":
        raise SplitError("Rozložení pro tisk jde jen při ponechání obou částí („both“).")
    width = feature.get("lip_width")
    if width in (None, ""):
        for key in ("lip_height", "lip_side", "lip_clearance"):
            if feature.get(key) not in (None, ""):
                raise SplitError(f"„{key}“ jde zadat jen s šířkou lemu („lip_width“).")
        return
    if keep != "both":
        raise SplitError("Lem a drážka jdou jen při ponechání obou částí („both“).")
    if feature.get("lip_height") in (None, ""):
        raise SplitError("Lem potřebuje výšku („lip_height“).")
    if feature.get("lip_side", "inner") not in LIP_SIDES:
        raise SplitError("Strana lemu („lip_side“) musí být „inner“ (vnitřní) nebo „outer“ "
                         "(vnější).")
    for key in ("lip_width", "lip_height", "lip_clearance"):
        value = feature.get(key)
        if value not in (None, "") and (isinstance(value, bool)
                                        or not isinstance(value, (int, float, str))):
            raise SplitError(f"„{key}“ musí být číslo nebo výraz.")


@dataclass(frozen=True)
class Lip:
    """Lem na základně a drážka ve víčku: šířka a výška lemu [mm], strana a vůle drážky [mm]."""

    width: float
    height: float
    side: str = "inner"
    clearance: float = DEFAULT_CLEARANCE


def _volume(part: Part | None) -> float:
    return 0.0 if part is None else float(sum(solid.volume for solid in part.solids()))


def _tolerance(volume: float) -> float:
    return 1e-9 * max(1.0, abs(volume))


def _side(part: Part, plane: Plane, keep: Keep) -> Part | None:
    """Jedna strana od roviny; ``None``, když na ní nic nezůstane."""
    try:
        result = split(part, bisect_by=plane, keep=keep)
    except Exception as exc:  # noqa: BLE001 – chyby jádra převádíme na lidskou zprávu
        raise SplitError(f"Rozříznutí se nepodařilo ({exc}). Zkus jinou polohu roviny.") from None
    if result is None or not result.solids():
        return None
    return result


def _on_plane(face: Face, plane: Plane, upward: bool) -> bool:
    if face.geom_type != GeomType.PLANE:
        return False
    if abs((face.center() - plane.origin).dot(plane.z_dir)) > 1e-6:
        return False
    return face.normal_at().dot(plane.z_dir) * (1 if upward else -1) > 1 - 1e-9


def _strips(sections: list[Face], width: float, side: str) -> list[Face]:
    """Pásy šířky ``width`` podél vnitřního / vnějšího okraje ploch řezu (uvnitř nich)."""
    strips: list[Face] = []
    for section in sections:
        if side == "inner":
            regions = [Face(wire) for wire in section.inner_wires()]
            grown = [(offset(region, amount=width, kind=Kind.INTERSECTION), region)
                     for region in regions]
            pieces = [(big - small) & section for big, small in grown]
        else:
            outer = Face(section.outer_wire())
            pieces = [(outer - offset(outer, amount=-width, kind=Kind.INTERSECTION)) & section]
        for piece in pieces:
            strips.extend(face for face in piece.faces() if face.area > 1e-9)
    return strips


def _lip_solids(strips: list[Face], plane: Plane, depth: float) -> list[Any]:
    return [solid for strip in strips
            for solid in extrude(strip, amount=depth, dir=plane.z_dir).solids()]


def _add_lip(lower: Part, upper: Part, plane: Plane, lip: Lip) -> tuple[Part, Part]:
    """Lem na dolní části a drážka v horní (obě z obrysu řezu)."""
    if lip.side not in LIP_SIDES:
        raise SplitError("Strana lemu musí být „inner“ (vnitřní) nebo „outer“ (vnější).")
    for name, value in (("Šířka lemu", lip.width), ("Výška lemu", lip.height)):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise SplitError(f"{name} musí být větší než 0 (je {value!r}).")
    if (not isinstance(lip.clearance, (int, float)) or not math.isfinite(lip.clearance)
            or lip.clearance < 0):
        raise SplitError(f"Vůle drážky nesmí být záporná (je {lip.clearance!r}).")
    sections = [face for face in lower.faces() if _on_plane(face, plane, upward=True)]
    if not sections:
        raise SplitError("Řez nemá žádnou rovinnou plochu, ze které by lem vyšel.")
    section_area = sum(face.area for face in sections)

    tongue = _strips(sections, lip.width, lip.side)
    if not tongue:
        raise SplitError(
            "Lem nemá kde vést – řez nemá " + ("vnitřní obrys (dutinu)" if lip.side == "inner"
            else "vnější obrys") + ". Zkus druhou stranu lemu nebo řez, který protíná stěny.")
    wide = _strips(sections, lip.width + lip.clearance, lip.side)
    for strips, what in ((tongue, "Lem"), (wide, "Drážka")):
        if sum(face.area for face in strips) >= section_area * (1 - 1e-6):
            raise SplitError(f"{what} je stejně široká jako stěna v řezu nebo širší – zmenši "
                             "šířku lemu (lem i s vůlí musí zůstat uvnitř stěny).")

    expected = sum(face.area for face in tongue) * lip.height
    fused = lower
    for solid in _lip_solids(tongue, plane, lip.height):
        fused = fused + _part([solid])
    if (len(fused.solids()) != len(lower.solids())
            or abs(_volume(fused) - _volume(lower) - expected) > 1e-6 * max(1.0, expected)):
        raise SplitError("Lem se nepodařilo spojit se základnou – zkus jinou šířku nebo výšku.")

    depth = lip.height + lip.clearance
    removed_expected = sum(face.area for face in wide) * depth
    cut = upper
    for cutter in _lip_solids(wide, plane, depth):
        cut = cut - _part([cutter])
    removed = _volume(upper) - _volume(cut)
    if (len(cut.solids()) != len(upper.solids())
            or abs(removed - removed_expected) > 1e-6 * max(1.0, removed_expected)):
        raise SplitError("Drážka je hlubší než stěna víčka nebo ji rozdělí – zmenši výšku lemu "
                         "nebo vůli.")
    return _part(list(fused.solids())), _part(list(cut.solids()))


def _part(solids: list[Any]) -> Part:
    return Part(Compound(solids).wrapped)


def _along(shape: Part, direction: Any) -> tuple[float, float]:
    """Nejmenší a největší souřadnice tvaru ve směru ``direction`` (obalový kvádr, osový směr)."""
    box = shape.bounding_box()
    values = [(x * direction.X + y * direction.Y + z * direction.Z)
              for x in (box.min.X, box.max.X) for y in (box.min.Y, box.max.Y)
              for z in (box.min.Z, box.max.Z)]
    return min(values), max(values)


def _print_layout(lower: Part, upper: Part, plane: Plane, gap: float) -> Part:
    """Víčko otočené o 180° kolem osy X roviny řezu (otevřená strana nahoru) na úrovni dna
    základny, vedle ní ve směru X roviny s mezerou ``gap``, vystředěné ve směru Y roviny."""
    for axis in (plane.x_dir, plane.y_dir, plane.z_dir):
        if max(abs(axis.X), abs(axis.Y), abs(axis.Z)) < 1 - 1e-9:
            raise SplitError("Rozložení pro tisk potřebuje rovinu rovnoběžnou s osami souřadnic.")
    turned = upper.rotate(Axis(plane.origin, plane.x_dir), 180)
    low_x1, turn_x0 = _along(lower, plane.x_dir)[1], _along(turned, plane.x_dir)[0]
    (low_y0, low_y1), (turn_y0, turn_y1) = _along(lower, plane.y_dir), _along(turned, plane.y_dir)
    (low_z0, _), (turn_z0, _) = _along(lower, plane.z_dir), _along(turned, plane.z_dir)
    shift = (plane.x_dir * (low_x1 + gap - turn_x0)
             + plane.y_dir * ((low_y0 + low_y1) / 2 - (turn_y0 + turn_y1) / 2)
             + plane.z_dir * (low_z0 - turn_z0))
    placed = turned.moved(Location(shift))
    return _part([*lower.solids(), *placed.solids()])


def apply(part: Part, plane: Plane, keep: str = "below", gap: float = 0.0,
          lip: Lip | None = None, arrange: str = "stack") -> Part:
    """Díl rozříznutý rovinou ``plane``: ``above`` ponechá stranu po normále, ``below`` opačnou,
    ``both`` obě (horní se odsune po normále o ``gap``). ``lip`` přidá u ``both`` lem na dolní
    části a drážku v horní. ``arrange`` ``print`` položí víčko otočené vedle základny."""
    if arrange not in ARRANGE:
        raise SplitError("Rozložení musí být „stack“ (nad sebou) nebo „print“ (pro tisk).")
    if arrange == "print" and keep != "both":
        raise SplitError("Rozložení pro tisk jde jen při ponechání obou částí.")
    if keep not in KEEP:
        raise SplitError("Ponechaná část musí být „above“, „below“ nebo „both“.")
    if not isinstance(gap, (int, float)) or not math.isfinite(gap) or gap < 0 or gap > MAX_GAP:
        raise SplitError(f"Mezera mezi částmi musí být od 0 do {MAX_GAP:g} mm (je {gap!r}).")
    if keep != "both" and gap:
        raise SplitError("Mezeru jde zadat jen při ponechání obou částí.")
    if lip is not None and keep != "both":
        raise SplitError("Lem a drážka jdou jen při ponechání obou částí.")

    before = _volume(part)
    tolerance = _tolerance(before)
    upper = _side(part, plane, Keep.TOP)
    lower = _side(part, plane, Keep.BOTTOM)
    upper_volume, lower_volume = _volume(upper), _volume(lower)

    if upper_volume <= tolerance or lower_volume <= tolerance:
        empty = "nad rovinou" if upper_volume <= tolerance else "pod rovinou"
        raise SplitError(
            f"Rovina díl neprotíná – {empty} není žádný materiál. Posuň rovinu do dílu "
            "(změň „Posun roviny“ nebo rovinu).")
    if abs(upper_volume + lower_volume - before) > 1e-6 * max(1.0, before):
        raise SplitError("Součet částí po řezu nesedí s původním objemem – řez je nespolehlivý, "
                         "zkus rovinu posunout o setinu milimetru.")

    if keep == "above":
        return Part(Compound(list(upper.solids())).wrapped)
    if keep == "below":
        return Part(Compound(list(lower.solids())).wrapped)
    if lip is not None:
        lower, upper = _add_lip(lower, upper, plane, lip)
    if arrange == "print":
        return _print_layout(lower, upper, plane, gap)
    moved = upper.moved(Location(plane.z_dir * gap)) if gap else upper
    return Part(Compound([*lower.solids(), *moved.solids()]).wrapped)
