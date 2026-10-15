"""Úpravy obrysu (tvar ``profile``) pro skicář – bez okna, aby šly testovat.

Skicář v okně jen převádí kliknutí na volání těchto funkcí: přidej bod,
úsečku, oblouk, kružnici, smaž, přidej vazbu podle výběru, změř aktuální hodnotu kóty.
Obrys je obyčejný slovník jako v JSON modelu (viz ``solver.py``).
"""

from __future__ import annotations

import copy
import math
from collections.abc import Iterable
from typing import Any

from skodacad.solver import CONSTRAINT_LABELS, ORIGIN, REFERENCE_POINTS, ROUND

# Vazba podle výběru: druh → co musí být vybrané (popis do hlášky).
NEEDS = {
    "horizontal": "jednu úsečku nebo dva body",
    "vertical": "jednu úsečku nebo dva body",
    "parallel": "dvě úsečky",
    "perpendicular": "dvě úsečky",
    "tangent": "dvě čáry, z nichž aspoň jedna je oblouk nebo kružnice",
    "equal": "dvě úsečky, nebo dva oblouky či kružnice",
    "coincident": "bod a druhý bod, úsečku, oblouk nebo kružnici (i počátek)",
    "midpoint": "bod a úsečku",
    "concentric": "dva oblouky nebo kružnice",
    "symmetric": "dva body a úsečku (osu souměrnosti)",
    "fix": "jeden nebo víc bodů",
    "dimension": "úsečku (délka), oblouk (poloměr), kružnici (průměr), dva body nebo bod "
                 "a úsečku (vzdálenost), nebo dvě úsečky (úhel)",
}


class EditError(ValueError):
    """Úprava nejde provést (zpráva česky, ukáže se ve stavovém řádku skicáře)."""


def empty_profile() -> dict[str, Any]:
    return {"shape": "profile", "points": {}, "segments": {}, "constraints": []}


def next_name(taken: Iterable[str], prefix: str) -> str:
    taken = set(taken)
    number = 1
    while f"{prefix}{number}" in taken:
        number += 1
    return f"{prefix}{number}"


def references_of(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Promítnuté hrany dílu v obrysu (jméno → odkaz, viz ``projection.py``)."""
    return profile.get("references") or {}


def reference_point_names(profile: dict[str, Any]) -> list[str]:
    return [f"{name}.{key}" for name, ref in references_of(profile).items()
            for key in REFERENCE_POINTS.get(ref.get("kind"), ())]


def _names(profile: dict[str, Any]) -> set[str]:
    return {ORIGIN, *profile["points"], *profile["segments"], *references_of(profile),
            *reference_point_names(profile)}


def _reference_point(profile: dict[str, Any], name: str) -> tuple[float, float] | None:
    base, _, key = str(name).rpartition(".")
    ref = references_of(profile).get(base)
    if ref is None or key not in REFERENCE_POINTS.get(ref.get("kind"), ()):
        return None
    x, y = ref["center"] if key == "center" else ref["points"][0 if key == "start" else 1]
    return float(x), float(y)


def is_fixed(profile: dict[str, Any], name: str) -> bool:
    """Počátek, promítnutá hrana nebo její bod – řešič s nimi nehýbe."""
    return (name == ORIGIN or name in references_of(profile)
            or _reference_point(profile, name) is not None)


def segment_view(profile: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Čára obrysu, nebo promítnutá hrana jako čára (body „r1.start“, „r1.center“ …)."""
    if name in profile["segments"]:
        return profile["segments"][name]
    ref = references_of(profile).get(name)
    if ref is None:
        return None
    view: dict[str, Any] = {"type": ref["kind"], "reference": True}
    view.update({key: f"{name}.{key}" for key in REFERENCE_POINTS[ref["kind"]]})
    if "radius" in ref:
        view["radius"] = ref["radius"]
    return view


def kind_of(profile: dict[str, Any], name: str) -> str | None:
    """„point“, „line“, „arc“, „circle“ nebo None (i pro promítnuté hrany a jejich body)."""
    if name == ORIGIN or name in profile["points"] or _reference_point(profile, name):
        return "point"
    segment = segment_view(profile, name)
    return segment["type"] if segment else None


def point_xy(profile: dict[str, Any], name: str) -> tuple[float, float]:
    if name == ORIGIN:
        return 0.0, 0.0
    fixed = _reference_point(profile, name)
    if fixed is not None:
        return fixed
    x, y = profile["points"][name]
    return float(x), float(y)


# --- kreslení -----------------------------------------------------------------------------


def add_point(profile: dict[str, Any], x: float, y: float) -> str:
    name = next_name(_names(profile), "P")
    profile["points"][name] = [round(x, 4), round(y, 4)]
    return name


def add_line(profile: dict[str, Any], start: str, end: str) -> str:
    if start == end:
        raise EditError("Úsečka potřebuje dva různé body.")
    name = next_name(_names(profile), "s")
    profile["segments"][name] = {"type": "line", "start": start, "end": end}
    return name


def add_arc(profile: dict[str, Any], start: str, end: str, center: str) -> str:
    if len({start, end, center}) != 3:
        raise EditError("Oblouk potřebuje začátek, konec a střed – tři různé body.")
    name = next_name(_names(profile), "a")
    profile["segments"][name] = {"type": "arc", "start": start, "end": end, "center": center}
    return name


def add_circle(profile: dict[str, Any], center: str, radius: float) -> str:
    if radius <= 1e-6:
        raise EditError("Kružnice potřebuje poloměr – druhým kliknutím urči bod na obvodu.")
    name = next_name(_names(profile), "k")
    profile["segments"][name] = {"type": "circle", "center": center,
                                 "radius": round(radius, 4)}
    return name


def add_reference(profile: dict[str, Any], reference: dict[str, Any]) -> str:
    """Přidá promítnutou hranu; stejná hrana (stejný popis) se nepřidá dvakrát."""
    refs = profile.setdefault("references", {})
    for name, existing in refs.items():
        if existing.get("edge") == reference.get("edge"):
            return name
    name = next_name(_names(profile), "r")
    refs[name] = copy.deepcopy(reference)
    return name


def convert_references(profile: dict[str, Any], names: Iterable[str]) -> list[str]:
    """„Převzít do obrysu“: z promítnutých hran udělá skutečné čáry obrysu navázané na díl
    (body leží na bodech promítnutých hran, kružnice má stejný průměr). Navazující hrany
    sdílejí body, takže z obrysu plochy vznikne uzavřená smyčka."""
    refs = references_of(profile)
    chosen = [name for name in names if name in refs]
    if not chosen:
        raise EditError("Vyber promítnuté hrany (fialové), které se mají převzít do obrysu.")
    made: dict[tuple[float, float], str] = {}

    def point_for(ref_point: str) -> str:
        x, y = point_xy(profile, ref_point)
        key = (round(x, 4), round(y, 4))
        if key not in made:
            made[key] = add_point(profile, x, y)
            profile["constraints"].append({"type": "coincident", "point": made[key],
                                           "on": ref_point})
        return made[key]

    created = []
    for name in chosen:
        ref = refs[name]
        if ref["kind"] == "line":
            created.append(add_line(profile, point_for(f"{name}.start"),
                                    point_for(f"{name}.end")))
        elif ref["kind"] == "arc":
            created.append(add_arc(profile, point_for(f"{name}.start"), point_for(f"{name}.end"),
                                   point_for(f"{name}.center")))
        else:
            circle = add_circle(profile, point_for(f"{name}.center"), float(ref["radius"]))
            profile["constraints"].append({"type": "equal", "segments": [circle, name]})
            created.append(circle)
    return created


def arc_through(start: tuple, end: tuple, through: tuple) -> tuple[tuple[float, float], bool]:
    """Střed kružnice třemi body a zda oblouk od ``start`` přes ``through`` do ``end`` vede
    proti směru hodin (True), nebo se musí začátek a konec prohodit (False)."""
    (ax, ay), (bx, by), (cx, cy) = start, through, end
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        raise EditError("Tři body oblouku leží na přímce – třetím kliknutím urči, kudy vede.")
    sa, sb, sc = ax**2 + ay**2, bx**2 + by**2, cx**2 + cy**2
    ux = (sa * (by - cy) + sb * (cy - ay) + sc * (ay - by)) / d
    uy = (sa * (cx - bx) + sb * (ax - cx) + sc * (bx - ax)) / d
    # Trojúhelník začátek → průchozí bod → konec obíhá proti směru hodin = oblouk také.
    counter_clockwise = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > 0
    return (ux, uy), counter_clockwise


def auto_constraints(profile: dict[str, Any], line: str, tolerance_deg: float = 2.0) -> list[dict]:
    """Skoro vodorovná / svislá úsečka dostane vazbu sama (jako v běžných CAD)."""
    segment = profile["segments"][line]
    (x1, y1), (x2, y2) = point_xy(profile, segment["start"]), point_xy(profile, segment["end"])
    angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1))) % 180
    if min(angle, 180 - angle) <= tolerance_deg:
        return [{"type": "horizontal", "segment": line}]
    if abs(angle - 90) <= tolerance_deg:
        return [{"type": "vertical", "segment": line}]
    return []


def toggle_construction(profile: dict[str, Any], names: Iterable[str]) -> None:
    lines = [name for name in names if name in profile["segments"]]
    if not lines:
        raise EditError("Vyber čáru, ze které má být pomocná (nebo zase skutečná).")
    for name in lines:
        segment = profile["segments"][name]
        if segment.get("construction"):
            segment.pop("construction")
        else:
            segment["construction"] = True


# --- mazání -------------------------------------------------------------------------------


def references(constraint: dict[str, Any]) -> list[str]:
    """Jména bodů a čar, na které vazba odkazuje."""
    refs = [constraint[key] for key in ("point", "on", "segment") if key in constraint]
    for key in ("points", "segments"):
        if isinstance(constraint.get(key), list):
            refs.extend(constraint[key])
    return refs


def remove(profile: dict[str, Any], names: Iterable[str]) -> None:
    """Smaže body a čáry (s bodem i čáry, které ho používají) a vazby, které na ně odkazují.
    Body, které po smazání čar zůstanou nepoužité, zmizí také. Bod promítnuté hrany smaže
    celou promítnutou hranu."""
    names = set(names) - {ORIGIN}
    refs = references_of(profile)
    dropped = {name for name in names if name in refs}
    dropped |= {name.rpartition(".")[0] for name in names if _reference_point(profile, name)}
    gone_refs = set()
    for name in dropped:
        kind = refs.pop(name)["kind"]
        gone_refs |= {name, *(f"{name}.{key}" for key in REFERENCE_POINTS[kind])}
    if gone_refs:
        profile["constraints"] = [c for c in profile["constraints"]
                                  if not set(references(c)) & gone_refs]
    points, segments = profile["points"], profile["segments"]
    removed_segments = {name for name in names if name in segments}
    removed_segments |= {name for name, s in segments.items()
                         if names & {s.get("start"), s.get("end"), s.get("center")}}
    loose = set()
    for name in removed_segments:
        segment = segments.pop(name)
        loose |= {segment[key] for key in ("start", "end", "center") if key in segment}
    used = {s[key] for s in segments.values() for key in ("start", "end", "center") if key in s}
    removed_points = {name for name in names if name in points} | (loose - used)
    for name in removed_points:
        points.pop(name, None)
    gone = removed_points | removed_segments
    profile["constraints"] = [c for c in profile["constraints"] if not set(references(c)) & gone]


def remove_constraints(profile: dict[str, Any], indexes: Iterable[int]) -> None:
    drop = set(indexes)
    profile["constraints"] = [c for i, c in enumerate(profile["constraints"]) if i not in drop]


# --- vazby z výběru ---------------------------------------------------------------------


def constraints_for(profile: dict[str, Any], kind: str, selection: list[str]) -> list[dict]:
    """Vazby druhu ``kind`` pro vybrané body/čáry. Kóta (``dimension``) dostane hodnotu
    podle současného tvaru – okno ji pak nabídne ke změně."""
    kinds = [kind_of(profile, name) for name in selection]
    if None in kinds:
        raise EditError("Vybraný prvek už v obrysu není.")
    if selection and all(is_fixed(profile, name) for name in selection):
        raise EditError("Vyber aspoň jeden prvek obrysu – počátek a promítnuté hrany jsou "
                        "pevné, vazba mezi nimi nic neurčí.")
    lines = [n for n, k in zip(selection, kinds, strict=True) if k == "line"]
    rounds = [n for n, k in zip(selection, kinds, strict=True) if k in ROUND]
    points = [n for n, k in zip(selection, kinds, strict=True) if k == "point"]
    problem = EditError(f"{CONSTRAINT_LABELS.get(kind, 'Kóta').capitalize()}: vyber "
                        f"{NEEDS[kind]}.")

    if kind in ("horizontal", "vertical"):
        if kinds == ["line"]:
            return [{"type": kind, "segment": lines[0]}]
        if kinds == ["point", "point"]:
            return [{"type": kind, "points": points}]
    elif kind in ("parallel", "perpendicular"):
        if kinds == ["line", "line"]:
            return [{"type": kind, "segments": lines}]
    elif kind == "tangent":
        if len(selection) == 2 and rounds and not points:
            return [{"type": "tangent", "segments": list(selection)}]
    elif kind == "equal":
        if kinds == ["line", "line"] or len(rounds) == len(selection) == 2:
            return [{"type": "equal", "segments": list(selection)}]
    elif kind == "concentric":
        if len(rounds) == len(selection) == 2:
            return [{"type": "concentric", "segments": list(selection)}]
    elif kind == "symmetric":
        if len(selection) == 3 and len(points) == 2 and len(lines) == 1:
            return [{"type": "symmetric", "points": points, "segment": lines[0]}]
    elif kind == "coincident":
        if len(selection) == 2 and kinds[0] == "point":
            return [{"type": "coincident", "point": selection[0], "on": selection[1]}]
        if len(selection) == 2 and kinds[1] == "point":
            return [{"type": "coincident", "point": selection[1], "on": selection[0]}]
    elif kind == "midpoint":
        if sorted(kinds) == ["line", "point"]:
            return [{"type": "midpoint", "point": points[0], "segment": lines[0]}]
    elif kind == "fix":
        movable = [name for name in points if not is_fixed(profile, name)]
        if movable and len(movable) == len(selection):
            return [{"type": "fix", "point": name} for name in movable]
    elif kind == "dimension":
        constraint = _dimension(profile, selection, kinds)
        if constraint is not None:
            constraint["value"] = measure(profile, constraint)
            return [constraint]
    raise problem


def _dimension(profile: dict, selection: list[str], kinds: list[str]) -> dict | None:
    if kinds == ["line"]:
        return {"type": "length", "segment": selection[0]}
    if kinds == ["arc"]:
        return {"type": "radius", "segment": selection[0]}
    if kinds == ["circle"]:
        return {"type": "diameter", "segment": selection[0]}
    if kinds == ["point", "point"]:
        return {"type": "distance", "points": list(selection)}
    if sorted(kinds) == ["line", "point"]:
        point = selection[kinds.index("point")]
        return {"type": "distance", "point": point, "segment": selection[kinds.index("line")]}
    if kinds == ["line", "line"]:
        return {"type": "angle", "segments": list(selection)}
    return None


def measure(profile: dict[str, Any], constraint: dict[str, Any]) -> float:
    """Současná hodnota kóty (pro předvyplnění), zaokrouhlená na setiny."""
    kind = constraint["type"]
    segments = {name: segment_view(profile, name)
                for name in (*profile["segments"], *references_of(profile))}

    def xy(name: str) -> tuple[float, float]:
        return point_xy(profile, name)

    if kind == "length":
        s = segments[constraint["segment"]]
        value = math.dist(xy(s["start"]), xy(s["end"]))
    elif kind in ("radius", "diameter"):
        s = segments[constraint["segment"]]
        value = s["radius"] if s["type"] == "circle" else math.dist(xy(s["center"]),
                                                                     xy(s["start"]))
        value *= 2 if kind == "diameter" else 1
    elif kind == "distance" and "segment" in constraint:
        s = segments[constraint["segment"]]
        (ax, ay), (bx, by), (px, py) = xy(s["start"]), xy(s["end"]), xy(constraint["point"])
        value = abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / math.dist((ax, ay), (bx, by))
    elif kind == "distance":
        value = math.dist(*(xy(name) for name in constraint["points"]))
    elif kind == "angle":
        directions = []
        for name in constraint["segments"]:
            (ax, ay), (bx, by) = xy(segments[name]["start"]), xy(segments[name]["end"])
            directions.append(math.atan2(by - ay, bx - ax))
        value = abs(math.degrees(directions[1] - directions[0])) % 360
        value = min(value, 360 - value)
    else:
        raise EditError(f"„{kind}“ není kóta.")
    rounded = round(value, 2)
    return int(rounded) if float(rounded).is_integer() else rounded
