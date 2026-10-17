"""Pomocné cílové objemy NDT (07A); nikdy se nepřidávají do výrobního tělesa.

Profil má souřadnice napříč / výška, výška = across × axis. Objem je tažen od
počátku ve směru axis. Svar musí být celý v materiálu; obecný hranol se s dílem protíná.
Rozměry jsou v mm a °. Nejde o rozpoznání skutečné hranice natavení nebo HAZ.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

ALGORITHM = "ndt-cilovy-objem 1"
MAX_VERTICES = 256
MAX_SIZE = 1_000_000.0  # ochrana geometrického jádra před extrémními vstupy [mm]
EPS = 1e-7
# Směry, které nabízí editor cíle (07C); jiný uložený směr zůstane beze změny.
DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "+X": (1.0, 0.0, 0.0), "-X": (-1.0, 0.0, 0.0), "+Y": (0.0, 1.0, 0.0),
    "-Y": (0.0, -1.0, 0.0), "+Z": (0.0, 0.0, 1.0), "-Z": (0.0, 0.0, -1.0)}
WELD_TYPES = {"butt_v": "tupý svar V", "fillet": "koutový svar"}
DIMENSION_LABELS = {
    "leg_across_mm": "Rameno svaru napříč", "leg_height_mm": "Rameno svaru na výšku",
    "thickness_mm": "Tloušťka plechu", "angle_deg": "Rozevření úkosu",
    "root_gap_mm": "Kořenová mezera", "cap_width_mm": "Šířka převýšení u plechu",
    "cap_top_width_mm": "Šířka vrcholu převýšení", "cap_height_mm": "Výška převýšení",
    "root_width_mm": "Šířka podkořene u plechu", "root_tip_width_mm": "Šířka konce podkořene",
    "root_height_mm": "Výška podkořene",
}


class TargetError(ValueError):
    """Neplatné zadání cíle nebo vazba na materiál dílu."""


def _keys(data: Any, allowed: set[str], where: str) -> None:
    if not isinstance(data, dict):
        raise TargetError(f"{where} musí být objekt.")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise TargetError(f"{where}: neznámá položka „{unknown[0]}“.")


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if (isinstance(value, bool) or not isinstance(value, int | float)
            or not math.isfinite(value) or abs(value) > MAX_SIZE
            or (positive and value <= EPS)):
        suffix = "kladné " if positive else ""
        raise TargetError(f"{label} musí být {suffix}konečné číslo do {MAX_SIZE:g} mm/°.")
    return float(value)


def _vector(value: Any, label: str, *, unit: bool = False) -> list[float]:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise TargetError(f"{label} musí mít tři souřadnice.")
    vector = [_number(v, label) for v in value]
    if unit:
        length = math.hypot(*vector)
        if length <= EPS:
            raise TargetError(f"{label} nesmí být nulový vektor.")
        if abs(length - 1) > 1e-14:
            vector = [v / length for v in vector]
    return vector


def _cross2(a: list[float], b: list[float], c: list[float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: list, b: list, p: list) -> bool:
    return (abs(_cross2(a, b, p)) <= EPS
            and all(min(a[i], b[i]) - EPS <= p[i] <= max(a[i], b[i]) + EPS for i in (0, 1)))


def _intersects(a: list, b: list, c: list, d: list) -> bool:
    sides = (_cross2(a, b, c), _cross2(a, b, d), _cross2(c, d, a), _cross2(c, d, b))
    return (sides[0] * sides[1] < 0 and sides[2] * sides[3] < 0
            or _on_segment(a, b, c) or _on_segment(a, b, d)
            or _on_segment(c, d, a) or _on_segment(c, d, b))


def _profile(value: Any) -> list[list[float]]:
    if not isinstance(value, list) or not 3 <= len(value) <= MAX_VERTICES + 1:
        raise TargetError(f"Průřez musí mít 3–{MAX_VERTICES} vrcholů.")
    points = []
    for raw in value:
        if not isinstance(raw, list | tuple) or len(raw) != 2:
            raise TargetError("Vrchol průřezu musí mít dvě souřadnice v mm.")
        points.append([_number(v, "Souřadnice průřezu") for v in raw])
    if points[-1] == points[0]:
        points.pop()
    if not 3 <= len(points) <= MAX_VERTICES:
        raise TargetError(f"Průřez musí mít 3–{MAX_VERTICES} různých vrcholů.")
    n = len(points)
    for i, a in enumerate(points):
        b = points[(i + 1) % n]
        if math.dist(a, b) <= EPS:
            raise TargetError("Průřez obsahuje nulovou hranu.")
        c = points[(i + 2) % n]
        # Zpáteční překrytí sousedních hran není jednoduchý polygon.
        if abs(_cross2(a, b, c)) <= EPS and sum(
                (b[k] - a[k]) * (c[k] - b[k]) for k in (0, 1)) < 0:
            raise TargetError("Hrany průřezu se překrývají.")
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _intersects(a, b, points[j], points[(j + 1) % n]):
                raise TargetError("Průřez se protíná nebo dotýká sám sebe.")
    area2 = sum(a[0] * b[1] - a[1] * b[0]
                for a, b in zip(points, points[1:] + points[:1], strict=True))
    if abs(area2) <= EPS:
        raise TargetError("Průřez má nulový obsah.")
    return points if area2 > 0 else points[::-1]


def _weld_dimensions(kind: Any, raw: Any) -> dict[str, float]:
    if kind == "fillet":
        names = {"leg_across_mm", "leg_height_mm"}
        _keys(raw, names, "Rozměry koutového svaru")
        return {k: _number(raw.get(k), DIMENSION_LABELS[k], positive=True) for k in sorted(names)}
    if kind != "butt_v":
        raise TargetError("Typ svaru musí být butt_v (tupý V) nebo fillet (koutový).")
    required = {"thickness_mm", "angle_deg", "root_gap_mm"}
    optional = {"cap_width_mm", "cap_top_width_mm", "cap_height_mm",
                "root_width_mm", "root_tip_width_mm", "root_height_mm"}
    _keys(raw, required | optional, "Rozměry tupého svaru V")
    dims = {k: _number(raw.get(k), DIMENSION_LABELS[k], positive=k != "root_gap_mm")
            for k in sorted(required)}
    dims.update({k: _number(raw.get(k, 0), DIMENSION_LABELS[k]) for k in sorted(optional)})
    if dims["root_gap_mm"] < 0 or any(dims[k] < 0 for k in optional):
        raise TargetError("Mezera, převýšení a podkořen nesmějí mít záporné rozměry.")
    if not 0 < dims["angle_deg"] < 180:
        raise TargetError("Rozevření svaru V musí být větší než 0° a menší než 180°.")
    for prefix, tip in (("cap", "cap_top_width_mm"), ("root", "root_tip_width_mm")):
        height, width = dims[f"{prefix}_height_mm"], dims[f"{prefix}_width_mm"]
        if height == 0 and (width != 0 or dims[tip] != 0) or height > 0 and width <= EPS:
            raise TargetError("Převýšení/podkořen potřebuje výšku a šířku, nebo všechny rozměry 0.")
    return dims


def normalize_target(target: Any) -> dict[str, Any]:
    """Validovaná kopie čistých JSON dat, se směry normalizovanými na jednotkové."""
    if not isinstance(target, dict) or target.get("kind") not in ("volume", "weld"):
        raise TargetError("Objemový cíl musí mít kind volume nebo weld.")
    kind = target["kind"]
    allowed = {"kind", "frame", "length_mm"} | (
        {"profile_mm"} if kind == "volume" else {"weld_type", "dimensions"})
    _keys(target, allowed, "Cílový objem")
    frame = target.get("frame")
    _keys(frame, {"origin", "axis", "across"}, "Souřadný systém cíle")
    origin = _vector(frame.get("origin"), "Počátek cíle")
    axis = _vector(frame.get("axis"), "Osa cíle", unit=True)
    across = _vector(frame.get("across"), "Směr napříč", unit=True)
    if abs(sum(a * b for a, b in zip(axis, across, strict=True))) > 1e-8:
        raise TargetError("Osa cíle a směr napříč musí být kolmé.")
    result = {"kind": kind, "frame": {"origin": origin, "axis": axis, "across": across},
              "length_mm": _number(target.get("length_mm"), "Délka cíle", positive=True)}
    if kind == "volume":
        result["profile_mm"] = _profile(target.get("profile_mm"))
    else:
        result["weld_type"] = target.get("weld_type")
        result["dimensions"] = _weld_dimensions(result["weld_type"], target.get("dimensions"))
        # Odvozený profil ověřit také, aby extrémní rozevření neobešlo omezení rozměrů.
        for profile in _weld_profiles(result):
            _profile(profile)
    return result


def _weld_profiles(target: dict) -> list[list[list[float]]]:
    d = target["dimensions"]
    if target["weld_type"] == "fillet":
        return [[[0, 0], [d["leg_across_mm"], 0], [0, d["leg_height_mm"]]]]
    t, gap = d["thickness_mm"], d["root_gap_mm"]
    half = gap / 2 + t * math.tan(math.radians(d["angle_deg"] / 2))
    body = [[-gap / 2, 0], [gap / 2, 0], [half, t], [-half, t]]
    if gap == 0:
        body.pop(0)
    result = [body]
    for prefix, level, sign, tip in (("cap", t, 1, "cap_top_width_mm"),
                                      ("root", 0, -1, "root_tip_width_mm")):
        h, w, end = d[f"{prefix}_height_mm"], d[f"{prefix}_width_mm"], d[tip]
        if h > 0:
            profile = [[-w / 2, level], [w / 2, level],
                       [end / 2, level + sign * h], [-end / 2, level + sign * h]]
            if end == 0:
                profile.pop()
            result.append(profile)
    return result


def direction_name(vector: Any) -> str | None:
    """„+X“ … pro směr rovnoběžný s osou souřadnic, jinak None (šikmý směr ze souboru)."""
    length = math.hypot(*vector)
    if length <= EPS:
        return None
    unit = [v / length for v in vector]
    return next((name for name, axis in DIRECTIONS.items()
                 if all(abs(a - b) <= 1e-9 for a, b in zip(unit, axis, strict=True))), None)


def height_direction(axis: Any, across: Any) -> tuple[float, float, float]:
    """Směr výšky průřezu = napříč × osa (pravidlo 07A)."""
    return (across[1] * axis[2] - across[2] * axis[1],
            across[2] * axis[0] - across[0] * axis[2],
            across[0] * axis[1] - across[1] * axis[0])


def target_profiles(target: dict[str, Any]) -> list[list[list[float]]]:
    """Polygony průřezu (napříč, výška) ověřeného cíle – svar může mít tělo, převýšení
    a podkořen jako samostatné polygony, které se dotýkají jen hranou."""
    saved = normalize_target(target)
    return [saved["profile_mm"]] if saved["kind"] == "volume" else _weld_profiles(saved)


def section_area(profiles: list[list[list[float]]]) -> float:
    """Obsah průřezu [mm²] – Gaussův vzorec pro každý polygon."""
    return math.fsum(abs(math.fsum(a[0] * b[1] - a[1] * b[0]
                                   for a, b in zip(p, p[1:] + p[:1], strict=True))) / 2
                     for p in profiles)


def nominal_volume(target: dict[str, Any]) -> float:
    """Zadaný objem ze vzorce: průřez × délka [mm³] (bez průniku s dílem)."""
    saved = normalize_target(target)
    return section_area(target_profiles(saved)) * saved["length_mm"]


@dataclass(frozen=True)
class TargetVolume:
    """Pomocná tělesa zůstávají v procesu výpočtu; do dokumentu se neserializují."""

    requested: Any
    shape: Any
    requested_volume_mm3: float
    volume_mm3: float
    outside_volume_mm3: float


def resolve_target(part: Any, target: dict[str, Any]) -> TargetVolume:
    """Skutečný účinný objem v materiálu; nepřijme prázdný cíl ani oříznutý svar."""
    from build123d import Plane, Polygon, extrude

    saved = normalize_target(target)
    if part is None:
        raise TargetError("Model nemá těleso – cílový objem nelze ověřit.")
    frame = saved["frame"]
    plane = Plane(origin=frame["origin"], x_dir=frame["across"],
                  z_dir=[-v for v in frame["axis"]])
    profiles = ([saved["profile_mm"]] if saved["kind"] == "volume" else _weld_profiles(saved))
    try:
        solids = [extrude(plane * Polygon(*(tuple(v) for v in _profile(p)), align=None),
                          amount=saved["length_mm"], dir=frame["axis"]) for p in profiles]
        requested = solids[0]
        for solid in solids[1:]:
            requested = requested + solid
        if not requested.is_valid or not requested.solids():
            raise TargetError("Cílový objem se nepodařilo sestavit jako platné těleso.")
        if saved["kind"] == "weld" and len(requested.solids()) != 1:
            raise TargetError("Části zadaného svaru netvoří jedno souvislé těleso.")
        effective = requested & part
        volume = effective.volume if effective is not None else 0.0
        if effective is None or not effective.is_valid or volume <= EPS:
            raise TargetError("Cílový objem nemá žádný společný objem s materiálem dílu.")
        nominal = requested.volume
        outside = max(0.0, nominal - volume)
        if saved["kind"] == "weld" and outside > max(1e-6, nominal * 1e-8):
            raise TargetError(f"Zadaný svar není celý v materiálu dílu – chybí {outside:.6g} mm³.")
        return TargetVolume(requested, effective, nominal, volume, outside)
    except TargetError:
        raise
    except Exception as exc:  # noqa: BLE001 – česká chyba místo pádu geometrického jádra
        raise TargetError(f"Cílový objem nelze geometricky ověřit: {exc}") from None
