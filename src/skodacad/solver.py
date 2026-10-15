"""Řešič vazeb skici: obrys z úseček, oblouků a kružnic (tvar skici ``profile``).

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
        "s3": {"type": "line", "start": "C", "end": "A", "construction": true},
        "k1": {"type": "circle", "center": "M", "radius": 4}},
     "constraints": [
        {"type": "coincident", "point": "A", "on": "origin"},
        {"type": "horizontal", "segment": "s1"},
        {"type": "length", "segment": "s1", "value": "sirka"},
        {"type": "radius", "segment": "s2", "value": 10}]}

* ``points`` – přibližné polohy [x, y]; po vyřešení se do nich ukládá výsledek.
* oblouk vede **proti směru hodinových ručiček** od ``start`` do ``end``.
* kružnice má střed a přibližný poloměr ``radius``; po vyřešení se do něj ukládá výsledek
  (rozměr se určuje vazbou „diameter“ nebo „radius“).
* obrys může mít víc uzavřených smyček – smyčka uvnitř jiné je díra (kružnice uvnitř
  obdélníku = otvor), smyčka uvnitř díry je zase materiál.
* ``references`` – hrany dílu promítnuté do skici (viz ``projection.py``). Jsou pevné
  jako počátek; vazby na ně odkazují jménem („r1“) a jejich body „r1.start“, „r1.end“,
  „r1.center“. Do obrysu (smyček) se nepočítají.
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
SEGMENT_TYPES = ("line", "arc", "circle")
ROUND = ("arc", "circle")  # čáry se středem a poloměrem
# Body promítnuté hrany podle jejího tvaru (jméno bodu = „r1.start“ …).
REFERENCE_POINTS = {"line": ("start", "end"), "circle": ("center",),
                    "arc": ("start", "end", "center")}

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
    "concentric": "soustředně",
    "symmetric": "souměrně podle čáry",
    "length": "délka",
    "distance": "vzdálenost",
    "radius": "poloměr",
    "diameter": "průměr",
    "angle": "úhel",
}
DIMENSIONS = ("length", "distance", "radius", "diameter", "angle")  # vazby s hodnotou (kóty)

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
    radii: dict[str, float] = field(default_factory=dict)  # vyřešené poloměry kružnic


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
        if "." in str(name):
            raise SolveError(f"Jméno bodu „{name}“ nesmí obsahovat tečku (ta je vyhrazená "
                             "pro body promítnutých hran).")
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
            raise SolveError(f"Čára „{name}“ musí mít „type“ line (úsečka), arc (oblouk) "
                             "nebo circle (kružnice).")
        keys = {"line": ("start", "end"), "arc": ("start", "end", "center"),
                "circle": ("center",)}[segment["type"]]
        if segment["type"] == "circle":
            radius = segment.get("radius")
            if isinstance(radius, bool) or not isinstance(radius, int | float) or radius <= 0:
                raise SolveError(f"Kružnice „{name}“ musí mít kladný poloměr („radius“).")
        for key in keys:
            if segment.get(key) not in points:
                raise SolveError(f"Čára „{name}“: bod „{segment.get(key)}“ ({key}) v obrysu není.")
        if len({segment[key] for key in keys}) != len(keys):
            raise SolveError(f"Čára „{name}“ používá jeden bod víckrát.")
    return raw


def _references(profile: dict[str, Any], points: dict, segments: dict) -> tuple[dict, dict]:
    """Promítnuté hrany → pevné body a čáry (řešič s nimi nehýbe, jako s počátkem)."""
    raw = profile.get("references") or {}
    if not isinstance(raw, dict):
        raise SolveError("„references“ musí být objekt {jméno: promítnutá hrana}.")
    ref_points: dict[str, tuple[float, float]] = {}
    ref_segments: dict[str, dict[str, Any]] = {}
    for name, ref in raw.items():
        if name in points or name in segments or name == ORIGIN or "." in str(name):
            raise SolveError(f"Promítnutá hrana „{name}“ má stejné jméno jako jiný prvek "
                             "obrysu (nebo tečku ve jméně).")
        kind = ref.get("kind") if isinstance(ref, dict) else None
        if kind not in REFERENCE_POINTS:
            raise SolveError(f"Promítnutá hrana „{name}“ nemá platný tvar („kind“: line, "
                             "circle nebo arc).")
        segment: dict[str, Any] = {"type": kind, "reference": True}
        try:
            if kind != "circle":
                for key, (x, y) in zip(("start", "end"), ref["points"], strict=True):
                    ref_points[f"{name}.{key}"] = (float(x), float(y))
            if kind != "line":
                x, y = ref["center"]
                ref_points[f"{name}.center"] = (float(x), float(y))
                segment["radius"] = float(ref["radius"])
                if segment["radius"] <= 0:
                    raise ValueError
        except (KeyError, TypeError, ValueError):
            raise SolveError(f"Promítnutá hrana „{name}“ má chybné souřadnice.") from None
        segment.update({key: f"{name}.{key}" for key in REFERENCE_POINTS[kind]})
        ref_segments[name] = segment
    return ref_points, ref_segments


def _kind(name: Any, points: dict, segments: dict) -> str | None:
    if name == ORIGIN or name in points:
        return "point"
    if name in segments:
        return segments[name]["type"]
    return None


def _shared_point(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if "start" not in a or "start" not in b:  # kružnice nemá koncové body
        return False
    return bool({a["start"], a["end"]} & {b["start"], b["end"]})


def _check_constraint(index: int, c: Any, points: dict, segments: dict,
                      fixed: frozenset = frozenset()) -> None:
    """Každá vazba musí odkazovat na správné druhy bodů a čar – jinak by slvs spadl.
    ``fixed`` = jména pevných prvků (promítnuté hrany a jejich body)."""
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
                what = {"point": "bod", "line": "úsečka", "arc": "oblouk", "circle": "kružnice"}
                expected = " nebo ".join(what[k] for k in kinds)
                raise SolveError(f"{where}: „{item}“ není {expected} obrysu.", [index])
        return items

    kind = c["type"]
    refs = [c[key] for key in ("point", "on", "segment") if key in c]
    refs += [item for key in ("points", "segments") if isinstance(c.get(key), list)
             for item in c[key]]
    if refs and all(ref == ORIGIN or ref in fixed for ref in refs):
        raise SolveError(f"{where}: spojuje jen pevné prvky (počátek, promítnuté hrany) – nic "
                         "neurčí. Vyber aspoň jeden prvek obrysu.", [index])
    if kind in DIMENSIONS and "value" not in c:
        raise SolveError(f"{where}: chybí hodnota („value“).", [index])
    if kind == "fix":
        need("point", ("point",))
    elif kind == "coincident":
        need("point", ("point",))
        need("on", ("point", "line", "arc", "circle"))
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
        first, second = need("segments", ("line", "arc", "circle"), 2)
        a, b = segments[first], segments[second]
        if first == second or (a["type"] == "line" and b["type"] == "line"):
            raise SolveError(f"{where}: tečnost má smysl jen s obloukem nebo kružnicí.", [index])
        if a.get("center") is not None and a.get("center") == b.get("center"):
            raise SolveError(f"{where}: soustředné kružnice se nemůžou dotýkat.", [index])
    elif kind == "equal":
        first, second = need("segments", ("line", "arc", "circle"), 2)
        types = {segments[first]["type"], segments[second]["type"]}
        if first == second or ("line" in types and len(types) > 1):
            raise SolveError(f"{where}: stejně velké mohou být dvě úsečky (délka) nebo dva "
                             "oblouky či kružnice (průměr).", [index])
    elif kind == "concentric":
        first, second = need("segments", ROUND, 2)
        if segments[first]["center"] == segments[second]["center"]:
            raise SolveError(f"{where}: „{first}“ a „{second}“ už mají společný střed.",
                             [index])
    elif kind == "symmetric":
        first, second = need("points", ("point",), 2)
        need("segment", ("line",))
        if first == second:
            raise SolveError(f"{where}: potřebuje dva různé body.", [index])
    elif kind == "midpoint":
        need("point", ("point",))
        need("segment", ("line",))
    elif kind == "length":
        need("segment", ("line",))
    elif kind in ("radius", "diameter"):
        need("segment", ROUND)
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
    ref_points, ref_segments = _references(profile, points, segments)
    constraints = profile.get("constraints", [])
    if not isinstance(constraints, list):
        raise SolveError("„constraints“ musí být seznam vazeb.")
    fixed = frozenset(ref_points) | frozenset(ref_segments)
    for index, constraint in enumerate(constraints):
        _check_constraint(index, constraint, {**points, **ref_points},
                          {**segments, **ref_segments}, fixed)
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
        return _solve(points, segments, ref_points, ref_segments, constraints, values)
    finally:
        slvs.clear_sketch()


def _solve(points: dict, segments: dict, ref_points: dict, ref_segments: dict,
           constraints: list, values: dict) -> SolveResult:
    wp = slvs.add_base_2d(_BASE_GROUP)
    normal = slvs.add_normal_3d(_BASE_GROUP, *slvs.make_quaternion(1, 0, 0, 0, 1, 0))
    entities = {ORIGIN: slvs.add_point_2d(_BASE_GROUP, 0.0, 0.0, wp)}
    for name, (x, y) in ref_points.items():  # promítnuté hrany jsou pevné jako počátek
        entities[name] = slvs.add_point_2d(_BASE_GROUP, float(x), float(y), wp)
    for name, (x, y) in points.items():
        entities[name] = slvs.add_point_2d(_GROUP, float(x), float(y), wp)
    radii = {}  # kružnice obrysu → entita poloměru (její hodnotu řešič mění)
    for group, shapes in ((_BASE_GROUP, ref_segments), (_GROUP, segments)):
        for name, segment in shapes.items():
            if segment["type"] == "line":
                entities[name] = slvs.add_line_2d(group, entities[segment["start"]],
                                                  entities[segment["end"]], wp)
            elif segment["type"] == "arc":
                entities[name] = slvs.add_arc(group, normal, entities[segment["center"]],
                                              entities[segment["start"]],
                                              entities[segment["end"]], wp)
            else:
                radius = slvs.add_distance(group, float(segment["radius"]), wp)
                entities[name] = slvs.add_circle(group, normal, entities[segment["center"]],
                                                 radius, wp)
                if group == _GROUP:
                    radii[name] = radius

    shape = _Shape({**points, **ref_points}, {**segments, **ref_segments}, entities, wp)
    owners: dict[int, int] = {}  # číslo vazby v řešiči → index vazby v obrysu
    for index, c in enumerate(constraints):
        for made in _add_constraint(c, shape, values.get(index)):
            owners[made["h"]] = index

    result, failed = slvs.solve_sketch(_GROUP, True)
    code = result["result"]
    if code in (slvs.ResultFlag.OKAY, slvs.ResultFlag.REDUNDANT_OKAY):
        solved = {name: (slvs.get_param_value(entities[name]["param"][0]),
                         slvs.get_param_value(entities[name]["param"][1])) for name in points}
        solved_radii = {name: abs(slvs.get_param_value(entity["param"][0]))
                        for name, entity in radii.items()}
        return SolveResult(solved, int(result["dof"]),
                           redundant=code == slvs.ResultFlag.REDUNDANT_OKAY,
                           radii=solved_radii)
    bad = sorted({owners[h] for h in failed if h in owners})
    if code == slvs.ResultFlag.INCONSISTENT:
        listed = ", ".join(constraint_text(i, constraints[i]) for i in bad) or "neznámo které"
        raise SolveError(f"Vazby si odporují: {listed}. Jednu z nich smaž nebo změň.", bad)
    if code == slvs.ResultFlag.TOO_MANY_UNKNOWNS:
        raise SolveError("Obrys je na řešič příliš velký – rozděl ho na víc obrysů.")
    raise SolveError("Řešič nenašel řešení. Zkus body nakreslit blíž požadovanému tvaru "
                     "nebo zkontroluj hodnoty kót.", bad)


@dataclass
class _Shape:
    """Obrys v řešiči: výchozí polohy (pro odhad bodu dotyku) a entity slvs."""

    points: dict[str, tuple[float, float]]
    segments: dict[str, dict[str, Any]]
    entities: dict[str, Any]
    wp: Any

    def xy(self, name: str) -> tuple[float, float]:
        return (0.0, 0.0) if name == ORIGIN else self.points[name]

    def radius(self, name: str) -> float:
        segment = self.segments[name]
        if segment["type"] == "circle":
            return float(segment["radius"])
        return math.dist(self.xy(segment["center"]), self.xy(segment["start"]))


def _add_constraint(c: dict[str, Any], shape: _Shape, value: float | None) -> list[Any]:
    """Vazbu převede na jednu či víc vazeb řešiče (všechny ověřené – viz test pádů)."""
    kind = c["type"]
    g, e, wp, segments = _GROUP, shape.entities, shape.wp, shape.segments
    if kind == "fix":
        return [slvs.dragged(g, e[c["point"]], wp)]
    if kind == "coincident":
        return [slvs.coincident(g, e[c["point"]], e[c["on"]], wp)]
    if kind in ("horizontal", "vertical"):
        make = slvs.horizontal if kind == "horizontal" else slvs.vertical
        if "segment" in c:
            return [make(g, e[c["segment"]], wp)]
        first, second = c["points"]
        return [make(g, e[first], wp, e[second])]
    if kind == "parallel":
        return [slvs.parallel(g, *(e[name] for name in c["segments"]), wp)]
    if kind == "perpendicular":
        return [slvs.perpendicular(g, *(e[name] for name in c["segments"]), wp)]
    if kind == "tangent":
        first, second = (segments[name] for name in c["segments"])
        if _shared_point(first, second):
            # slvs chce oblouk jako první – úsečka napřed by shodila celý program.
            a, b = sorted(c["segments"], key=lambda name: segments[name]["type"] != "arc")
            return [slvs.tangent(g, e[a], e[b], wp)]
        return _touch(shape, *c["segments"])
    if kind == "equal":
        return [slvs.equal(g, *(e[name] for name in c["segments"]), wp)]
    if kind == "midpoint":
        return [slvs.midpoint(g, e[c["point"]], e[c["segment"]], wp)]
    if kind == "concentric":
        first, second = (segments[name]["center"] for name in c["segments"])
        return [slvs.coincident(g, e[first], e[second], wp)]
    if kind == "symmetric":
        first, second = c["points"]
        return [slvs.symmetric(g, e[first], e[second], e[c["segment"]], wp)]
    if kind == "angle":
        return [slvs.angle(g, *(e[name] for name in c["segments"]), float(value), wp)]
    if kind == "radius":
        return [slvs.diameter(g, e[c["segment"]], 2 * float(value))]
    if kind == "diameter":
        return [slvs.diameter(g, e[c["segment"]], float(value))]
    if kind == "length":
        line = segments[c["segment"]]
        return [slvs.distance(g, e[line["start"]], e[line["end"]], float(value), wp)]
    if kind == "distance":
        if "segment" in c:
            # Řešič bere vzdálenost od čáry se znaménkem (kladná = vpravo od směru čáry);
            # znaménko podle současné polohy, jinak by bod přeskočil na druhou stranu.
            line = segments[c["segment"]]
            (ax, ay), (bx, by) = shape.xy(line["start"]), shape.xy(line["end"])
            px, py = shape.xy(c["point"])
            side = -1.0 if (bx - ax) * (py - ay) - (by - ay) * (px - ax) > 0 else 1.0
            return [slvs.distance(g, e[c["point"]], e[c["segment"]], side * float(value), wp)]
        first, second = c["points"]
        return [slvs.distance(g, e[first], e[second], float(value), wp)]
    raise SolveError(f"Neznámý druh vazby „{kind}“.")  # pojistka – kontrola to už vyloučila


def _touch(shape: _Shape, first: str, second: str) -> list[Any]:
    """Tečnost přes skrytý bod dotyku T (řešič ji přímo umí jen u navazujících čar).

    Úsečka a kružnice: T leží na obou a spojnice střed–T je kolmá na úsečku.
    Dvě kružnice (oblouky): T leží na obou a na spojnici jejich středů. Dotyk zvenku či
    zevnitř se vybere podle toho, jak je skica právě nakreslená."""
    g, e, wp, segments = _GROUP, shape.entities, shape.wp, shape.segments
    if segments[first]["type"] == "line":
        first, second = second, first
    round_a = segments[first]
    ca = shape.xy(round_a["center"])
    if segments[second]["type"] == "line":
        line = segments[second]
        (ax, ay), (bx, by) = shape.xy(line["start"]), shape.xy(line["end"])
        length2 = (bx - ax) ** 2 + (by - ay) ** 2 or 1.0
        t = ((ca[0] - ax) * (bx - ax) + (ca[1] - ay) * (by - ay)) / length2
        guess = (ax + t * (bx - ax), ay + t * (by - ay))  # pata kolmice ze středu
    else:
        cb = shape.xy(segments[second]["center"])
        ra, rb = shape.radius(first), shape.radius(second)
        d = math.dist(ca, cb) or 1.0
        ux, uy = (cb[0] - ca[0]) / d, (cb[1] - ca[1]) / d
        sign = -1.0 if d <= max(ra, rb) and rb > ra else 1.0  # menší uvnitř větší
        guess = (ca[0] + sign * ra * ux, ca[1] + sign * ra * uy)
    point = slvs.add_point_2d(g, float(guess[0]), float(guess[1]), wp)
    made = [slvs.coincident(g, point, e[first], wp), slvs.coincident(g, point, e[second], wp)]
    if segments[second]["type"] == "line":
        radius = slvs.add_line_2d(g, e[round_a["center"]], point, wp)
        made.append(slvs.perpendicular(g, radius, e[second], wp))
    else:
        centers = slvs.add_line_2d(g, e[round_a["center"]], e[segments[second]["center"]], wp)
        made.append(slvs.coincident(g, point, centers, wp))
    return made


# --- obrys jako uzavřené smyčky ---------------------------------------------------------


def loops(profile: dict[str, Any], points: dict[str, tuple[float, float]],
          radii: dict[str, float] | None = None) -> list[list[tuple]]:
    """Čáry obrysu (bez pomocných) seřazené do uzavřených smyček.

    Každá smyčka je seznam ``("line", start, end)``, ``("arc", start, end, center)``
    (oblouk vždy proti směru hodin od start do end) nebo jediné ``("circle", center,
    radius)``. Poloměry kružnic jsou z ``radii`` (výsledek řešiče), jinak z obrysu.
    Když obrys není uzavřený, vyvolá ``SolveError`` s vysvětlením.
    """
    radii = radii or {}
    real = {name: s for name, s in profile["segments"].items() if not s.get("construction")}
    if not real:
        raise SolveError("Obrys má jen pomocné čáry – nakresli aspoň jednu skutečnou.")
    result = [[("circle", points[s["center"]], float(radii.get(name, s["radius"])))]
              for name, s in real.items() if s["type"] == "circle"]
    segments = {name: s for name, s in real.items() if s["type"] != "circle"}
    uses: dict[str, list[str]] = {}
    for name, segment in segments.items():
        for key in ("start", "end"):
            uses.setdefault(segment[key], []).append(name)
    for point, names in uses.items():
        if len(names) != 2:
            problem = "volný konec" if len(names) == 1 else f"rozvětvení ({len(names)} čáry)"
            raise SolveError(f"Obrys není uzavřený: v bodě „{point}“ je {problem}. Každý bod "
                             "obrysu musí spojovat právě dvě čáry.")

    left = dict(segments)
    while left:
        first = next(iter(left))
        ordered, current, point = [], first, segments[first]["start"]
        while True:
            segment = segments[current]
            forward = segment["start"] == point
            ordered.append((current, forward))
            left.pop(current)
            point = segment["end"] if forward else segment["start"]
            current = next(name for name in uses[point] if name != current)
            if current == first:
                break
        loop = []
        for name, forward in ordered:
            segment = segments[name]
            start, end = points[segment["start"]], points[segment["end"]]
            if segment["type"] == "line":
                loop.append(("line", start, end) if forward else ("line", end, start))
            else:
                loop.append(("arc", start, end, points[segment["center"]]))
        result.append(loop)
    return result


def arc_midpoint(start: tuple, end: tuple, center: tuple) -> tuple[float, float]:
    """Bod uprostřed oblouku vedeného proti směru hodin od ``start`` do ``end``."""
    radius = math.dist(start, center)
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    if a1 <= a0:
        a1 += 2 * math.pi
    middle = (a0 + a1) / 2
    return center[0] + radius * math.cos(middle), center[1] + radius * math.sin(middle)
