"""Řešič vazeb skici: obrys z úseček a oblouků (tvar skici ``profile``).

Uživatel nakreslí obrys jen přibližně a vazbami řekne, co platí („vodorovně“,
„tečně“, „délka = sirka“). Řešič SolveSpace (balík ``slvs``) z toho spočítá
přesné polohy bodů. Hodnoty kót mohou být výrazy s parametry, takže obrys se
po změně parametru přepočítá.

Formát (v JSON modelu je to jeden tvar v ``elements`` skici)::

    {"shape": "profile",
     "points": {"A": [0, 0], "B": [40, 0], "C": [40, 30], "M": [30, 30]},
     "segments": {
        "s1": {"type": "line", "start": "A", "end": "B"},
        "s2": {"type": "arc", "start": "B", "end": "C", "center": "M"},
        "s3": {"type": "line", "start": "C", "end": "A", "construction": true}},
     "constraints": [
        {"type": "coincident", "point": "A", "on": "origin"},
        {"type": "horizontal", "segment": "s1"},
        {"type": "length", "segment": "s1", "value": "sirka"},
        {"type": "radius", "segment": "s2", "value": 10}]}

* ``points`` – přibližné polohy [x, y]; po vyřešení se do nich ukládá výsledek.
* oblouk vede **proti směru hodinových ručiček** od ``start`` do ``end``.
* ``construction`` – pomocná čára: účastní se vazeb, ale není součástí obrysu.
* bod ``origin`` je vždy počátek skici [0, 0] a nehýbe se.

Pozor: knihovna slvs při nesmyslném volání shodí celý program (nevyhodí výjimku).
Proto se všechno nejdřív zkontroluje tady v Pythonu a do slvs jde jen ověřená
kombinace – každou hlídá test.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import slvs

ORIGIN = "origin"
SEGMENT_TYPES = ("line", "arc")

# Druh vazby → český název (pro chybové hlášky a okno).
CONSTRAINT_LABELS = {
    "fix": "pevný bod",
    "coincident": "bod na bodě / na čáře",
    "horizontal": "vodorovně",
    "vertical": "svisle",
    "parallel": "rovnoběžně",
    "perpendicular": "kolmo",
    "tangent": "tečně",
    "equal": "stejně velké",
    "midpoint": "bod uprostřed čáry",
    "length": "délka",
    "distance": "vzdálenost",
    "radius": "poloměr",
    "angle": "úhel",
}
DIMENSIONS = ("length", "distance", "radius", "angle")  # vazby s hodnotou (kóty)

_BASE_GROUP = 1  # pracovní rovina a počátek – řešič s nimi nehýbe
_GROUP = 2  # body a čáry obrysu


class SolveError(ValueError):
    """Obrys nejde vyřešit (zpráva česky). ``failed`` = indexy vazeb, které vadí."""

    def __init__(self, message: str, failed: list[int] | None = None) -> None:
        super().__init__(message)
        self.failed = failed or []


@dataclass
class SolveResult:
    points: dict[str, tuple[float, float]]  # vyřešené polohy bodů (bez „origin“)
    dof: int  # kolik rozměrů ještě chybí, aby byl obrys plně určený (0 = hotovo)
    redundant: bool = False  # některá vazba je navíc (nic nemění, ale nevadí)
    warnings: list[str] = field(default_factory=list)


def constraint_text(index: int, constraint: Any) -> str:
    """Vazba česky pro hlášky: „vazba 3 (tečně s1, s2)“."""
    if not isinstance(constraint, dict):
        return f"vazba {index + 1}"
    kind = constraint.get("type")
    label = CONSTRAINT_LABELS.get(kind, str(kind))
    refs = []
    for key in ("point", "on", "segment"):
        if key in constraint:
            refs.append(str(constraint[key]))
    for key in ("points", "segments"):
        if isinstance(constraint.get(key), list):
            refs.extend(str(item) for item in constraint[key])
    refs = ["počátek" if ref == ORIGIN else ref for ref in refs]
    value = f" = {constraint['value']}" if "value" in constraint else ""
    return f"vazba {index + 1} ({label} {', '.join(refs)}{value})"


# --- kontrola struktury ----------------------------------------------------------------


def _points(profile: dict[str, Any], evaluate: Callable[[Any], float]) -> dict[str, tuple]:
    raw = profile.get("points")
    if not isinstance(raw, dict) or not raw:
        raise SolveError("Obrys nemá žádné body („points“).")
    points = {}
    for name, value in raw.items():
        if name == ORIGIN:
            raise SolveError("Bod se nesmí jmenovat „origin“ – to je počátek skici.")
        if not isinstance(value, list | tuple) or len(value) != 2:
            raise SolveError(f"Bod „{name}“ musí mít souřadnice [x, y].")
        points[name] = (evaluate(value[0]), evaluate(value[1]))
    return points


def _segments(profile: dict[str, Any], points: dict[str, tuple]) -> dict[str, dict[str, Any]]:
    raw = profile.get("segments")
    if not isinstance(raw, dict) or not raw:
        raise SolveError("Obrys nemá žádné čáry („segments“).")
    for name, segment in raw.items():
        if name in points or name == ORIGIN:
            raise SolveError(f"Čára „{name}“ má stejné jméno jako bod – jména musí být různá.")
        if not isinstance(segment, dict) or segment.get("type") not in SEGMENT_TYPES:
            raise SolveError(f"Čára „{name}“ musí mít „type“ line (úsečka) nebo arc (oblouk).")
        keys = ("start", "end", "center") if segment["type"] == "arc" else ("start", "end")
        for key in keys:
            if segment.get(key) not in points:
                raise SolveError(f"Čára „{name}“: bod „{segment.get(key)}“ ({key}) v obrysu není.")
        if len({segment[key] for key in keys}) != len(keys):
            raise SolveError(f"Čára „{name}“ používá jeden bod víckrát.")
    return raw


def _kind(name: Any, points: dict, segments: dict) -> str | None:
    if name == ORIGIN or name in points:
        return "point"
    if name in segments:
        return segments[name]["type"]
    return None


def _shared_point(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return bool({a["start"], a["end"]} & {b["start"], b["end"]})


def _check_constraint(index: int, c: Any, points: dict, segments: dict) -> None:
    """Každá vazba musí odkazovat na správné druhy bodů a čar – jinak by slvs spadl."""
    where = constraint_text(index, c)
    if not isinstance(c, dict) or c.get("type") not in CONSTRAINT_LABELS:
        known = ", ".join(CONSTRAINT_LABELS)
        raise SolveError(f"Vazba {index + 1}: neznámý druh, povolené: {known}.", [index])

    def need(key: str, kinds: tuple[str, ...], count: int | None = None) -> list[Any]:
        value = c.get(key)
        items = value if count is not None else [value]
        if count is not None and (not isinstance(value, list) or len(value) != count):
            raise SolveError(f"{where}: „{key}“ musí být {count} položky.", [index])
        for item in items:
            if _kind(item, points, segments) not in kinds:
                what = {"point": "bod", "line": "úsečka", "arc": "oblouk"}
                expected = " nebo ".join(what[k] for k in kinds)
                raise SolveError(f"{where}: „{item}“ není {expected} obrysu.", [index])
        return items

    kind = c["type"]
    if kind in DIMENSIONS and "value" not in c:
        raise SolveError(f"{where}: chybí hodnota („value“).", [index])
    if kind == "fix":
        need("point", ("point",))
    elif kind == "coincident":
        need("point", ("point",))
        need("on", ("point", "line", "arc"))
        if c["point"] == c["on"]:
            raise SolveError(f"{where}: bod nemůže ležet sám na sobě.", [index])
    elif kind in ("horizontal", "vertical"):
        if "segment" in c:
            need("segment", ("line",))
        else:
            first, second = need("points", ("point",), 2)
            if first == second:
                raise SolveError(f"{where}: potřebuje dva různé body.", [index])
    elif kind in ("parallel", "perpendicular", "angle"):
        first, second = need("segments", ("line",), 2)
        if first == second:
            raise SolveError(f"{where}: potřebuje dvě různé úsečky.", [index])
    elif kind == "tangent":
        first, second = need("segments", ("line", "arc"), 2)
        if "arc" not in (segments[first]["type"], segments[second]["type"]):
            raise SolveError(f"{where}: tečnost má smysl jen s obloukem.", [index])
        if first == second or not _shared_point(segments[first], segments[second]):
            raise SolveError(f"{where}: tečně jde jen u čar, které na sebe navazují "
                             "(mají společný koncový bod).", [index])
    elif kind == "equal":
        first, second = need("segments", ("line", "arc"), 2)
        if first == second or segments[first]["type"] != segments[second]["type"]:
            raise SolveError(f"{where}: stejně velké mohou být dvě úsečky (délka) nebo dva "
                             "oblouky (poloměr).", [index])
    elif kind == "midpoint":
        need("point", ("point",))
        need("segment", ("line",))
    elif kind == "length":
        need("segment", ("line",))
    elif kind == "radius":
        need("segment", ("arc",))
    elif kind == "distance":
        if "segment" in c:
            need("point", ("point",))
            need("segment", ("line",))
        else:
            first, second = need("points", ("point",), 2)
            if first == second:
                raise SolveError(f"{where}: potřebuje dva různé body.", [index])


# --- řešení -----------------------------------------------------------------------------


def solve(profile: dict[str, Any], evaluate: Callable[[Any], float]) -> SolveResult:
    """Vyřeší obrys. Při chybě vyvolá ``SolveError`` s českou zprávou."""
    points = _points(profile, evaluate)
    segments = _segments(profile, points)
    constraints = profile.get("constraints", [])
    if not isinstance(constraints, list):
        raise SolveError("„constraints“ musí být seznam vazeb.")
    for index, constraint in enumerate(constraints):
        _check_constraint(index, constraint, points, segments)
    values = {}
    for index, constraint in enumerate(constraints):
        if constraint["type"] in DIMENSIONS:
            value = evaluate(constraint["value"])
            if constraint["type"] != "angle" and value <= 0:
                raise SolveError(f"{constraint_text(index, constraint)}: hodnota musí být "
                                 f"kladná (je {value:g}).", [index])
            values[index] = value

    slvs.clear_sketch()
    try:
        return _solve(points, segments, constraints, values)
    finally:
        slvs.clear_sketch()


def _solve(points: dict, segments: dict, constraints: list, values: dict) -> SolveResult:
    wp = slvs.add_base_2d(_BASE_GROUP)
    normal = slvs.add_normal_3d(_BASE_GROUP, *slvs.make_quaternion(1, 0, 0, 0, 1, 0))
    entities = {ORIGIN: slvs.add_point_2d(_BASE_GROUP, 0.0, 0.0, wp)}
    for name, (x, y) in points.items():
        entities[name] = slvs.add_point_2d(_GROUP, float(x), float(y), wp)
    for name, segment in segments.items():
        if segment["type"] == "line":
            entities[name] = slvs.add_line_2d(_GROUP, entities[segment["start"]],
                                              entities[segment["end"]], wp)
        else:
            entities[name] = slvs.add_arc(_GROUP, normal, entities[segment["center"]],
                                          entities[segment["start"]], entities[segment["end"]],
                                          wp)

    owners: dict[int, int] = {}  # číslo vazby v řešiči → index vazby v obrysu
    for index, c in enumerate(constraints):
        made = _add_constraint(c, entities, wp, values.get(index), segments)
        owners[made["h"]] = index

    result, failed = slvs.solve_sketch(_GROUP, True)
    code = result["result"]
    if code in (slvs.ResultFlag.OKAY, slvs.ResultFlag.REDUNDANT_OKAY):
        solved = {name: (slvs.get_param_value(entities[name]["param"][0]),
                         slvs.get_param_value(entities[name]["param"][1])) for name in points}
        return SolveResult(solved, int(result["dof"]),
                           redundant=code == slvs.ResultFlag.REDUNDANT_OKAY)
    bad = sorted({owners[h] for h in failed if h in owners})
    if code == slvs.ResultFlag.INCONSISTENT:
        listed = ", ".join(constraint_text(i, constraints[i]) for i in bad) or "neznámo které"
        raise SolveError(f"Vazby si odporují: {listed}. Jednu z nich smaž nebo změň.", bad)
    if code == slvs.ResultFlag.TOO_MANY_UNKNOWNS:
        raise SolveError("Obrys je na řešič příliš velký – rozděl ho na víc obrysů.")
    raise SolveError("Řešič nenašel řešení. Zkus body nakreslit blíž požadovanému tvaru "
                     "nebo zkontroluj hodnoty kót.", bad)


def _add_constraint(c: dict[str, Any], e: dict[str, Any], wp: Any, value: float | None,
                    segments: dict[str, dict[str, Any]]) -> Any:
    kind = c["type"]
    g = _GROUP
    if kind == "fix":
        return slvs.dragged(g, e[c["point"]], wp)
    if kind == "coincident":
        return slvs.coincident(g, e[c["point"]], e[c["on"]], wp)
    if kind in ("horizontal", "vertical"):
        make = slvs.horizontal if kind == "horizontal" else slvs.vertical
        if "segment" in c:
            return make(g, e[c["segment"]], wp)
        first, second = c["points"]
        return make(g, e[first], wp, e[second])
    if kind == "parallel":
        return slvs.parallel(g, *(e[name] for name in c["segments"]), wp)
    if kind == "perpendicular":
        return slvs.perpendicular(g, *(e[name] for name in c["segments"]), wp)
    if kind == "tangent":
        # slvs chce oblouk jako první – úsečka napřed by shodila celý program.
        first, second = sorted(c["segments"], key=lambda name: segments[name]["type"] != "arc")
        return slvs.tangent(g, e[first], e[second], wp)
    if kind == "equal":
        return slvs.equal(g, *(e[name] for name in c["segments"]), wp)
    if kind == "midpoint":
        return slvs.midpoint(g, e[c["point"]], e[c["segment"]], wp)
    if kind == "angle":
        return slvs.angle(g, *(e[name] for name in c["segments"]), float(value), wp)
    if kind == "radius":
        return slvs.diameter(g, e[c["segment"]], 2 * float(value))
    if kind == "length":
        line = segments[c["segment"]]
        return slvs.distance(g, e[line["start"]], e[line["end"]], float(value), wp)
    if kind == "distance":
        if "segment" in c:
            return slvs.distance(g, e[c["point"]], e[c["segment"]], float(value), wp)
        first, second = c["points"]
        return slvs.distance(g, e[first], e[second], float(value), wp)
    raise SolveError(f"Neznámý druh vazby „{kind}“.")  # pojistka – kontrola to už vyloučila


# --- obrys jako uzavřená smyčka ---------------------------------------------------------


def outline(profile: dict[str, Any], points: dict[str, tuple[float, float]]) -> list[tuple]:
    """Čáry obrysu (bez pomocných) seřazené do uzavřené smyčky.

    Vrací seznam ``("line", start, end)`` nebo ``("arc", start, end, center)`` se
    souřadnicemi (oblouk vždy proti směru hodin od start do end). Když obrys není
    uzavřený, vyvolá ``SolveError`` s vysvětlením.
    """
    segments = {name: s for name, s in profile["segments"].items() if not s.get("construction")}
    if not segments:
        raise SolveError("Obrys má jen pomocné čáry – nakresli aspoň jednu skutečnou.")
    uses: dict[str, list[str]] = {}
    for name, segment in segments.items():
        for key in ("start", "end"):
            uses.setdefault(segment[key], []).append(name)
    for point, names in uses.items():
        if len(names) != 2:
            problem = "volný konec" if len(names) == 1 else f"rozvětvení ({len(names)} čáry)"
            raise SolveError(f"Obrys není uzavřený: v bodě „{point}“ je {problem}. Každý bod "
                             "obrysu musí spojovat právě dvě čáry.")

    first = next(iter(segments))
    ordered, current, point = [], first, segments[first]["start"]
    while True:
        segment = segments[current]
        forward = segment["start"] == point
        ordered.append((current, forward))
        point = segment["end"] if forward else segment["start"]
        current = next(name for name in uses[point] if name != current)
        if current == first:
            break
    if len(ordered) != len(segments):
        raise SolveError("Obrys se skládá z několika oddělených smyček – každou nakresli jako "
                         "samostatný obrys.")

    loop = []
    for name, forward in ordered:
        segment = segments[name]
        start, end = points[segment["start"]], points[segment["end"]]
        if segment["type"] == "line":
            loop.append(("line", start, end) if forward else ("line", end, start))
        else:
            loop.append(("arc", start, end, points[segment["center"]]))
    return loop


def arc_midpoint(start: tuple, end: tuple, center: tuple) -> tuple[float, float]:
    """Bod uprostřed oblouku vedeného proti směru hodin od ``start`` do ``end``."""
    radius = math.dist(start, center)
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    if a1 <= a0:
        a1 += 2 * math.pi
    middle = (a0 + a1) / 2
    return center[0] + radius * math.cos(middle), center[1] + radius * math.sin(middle)
