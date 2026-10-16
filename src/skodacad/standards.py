"""Normalizované díly: šrouby, matice, podložky, ložiska, kolíky, pera a ocelové profily.

Rozměry jsou z tabulek ověřených 16. 10. 2026 porovnáním více zdrojů (normy samotné jsou
placené; stránky šlo porovnat jen přes výsledky vyhledávání) – zdroje jsou u každé tabulky.
Plochy průřezů IPE, UPN a L jsou navíc přepočtené z rozměrů a souhlasí s tabulkovými.

Závit je jen **vyznačený** (dřík má jmenovitý průměr, jako díra nese údaj o závitu). Tvary
jsou zjednodušené tam, kde to pro modelování nevadí: bez sražení hlav a matic, kuličkové
ložisko jako prstenec, vnitřní šestihran s rovným dnem.

Díl stojí v místních souřadnicích na rovině z = 0 tak, jak sedí na ploše dílu (+Z = ven
z plochy):

* šroub s válcovou nebo šestihrannou hlavou – hlava nad rovinou, dřík do materiálu (−Z),
* zápustný šroub – hlava zapuštěná, její horní plocha v rovině,
* matice, podložka, ložisko, kolík, tyč z profilu – leží na rovině a míří ven (+Z),
* těsné pero – v drážce hřídele: spodek v hloubce t1 pod rovinou, délka podél osy X.

Pro **kapsu** (odebrání) se bere obrys dílu bez děr (matice bez díry, ložisko jako válec,
šroub bez vnitřního šestihranu), zvětšený o vůli na každou stranu.

Všechny rozměry v mm.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from build123d import (
    Align,
    Circle,
    Cylinder,
    Kind,
    Part,
    Polygon,
    Pos,
    Rectangle,
    RectangleRounded,
    RegularPolygon,
    Sketch,
    SlotOverall,
    chamfer,
    extrude,
    fillet,
    loft,
    offset,
)
from build123d import Plane as _Plane


class StandardError(ValueError):
    """Neznámý nebo nesmyslný normalizovaný díl (zpráva je česky pro uživatele)."""


# --- Spojovací materiál --------------------------------------------------------------------
# Zdroje: ISO 4762 – fasten.it, engineeringhardware.com, Holo-Krome, Accu (M2.5, M30);
# ISO 4017 – fasten.it, fasteners.eu, Fuller Fasteners (pozor: DIN 933 má jiné klíče, M10 17);
# ISO 10642 – Engineers Edge (BS EN ISO 10642), Nordic Fastening Group, globalfastener
# (délka l je celková i s hlavou – bolts.co.uk, Accu); ISO 4032 – fasteners.eu, Engineers
# Edge, AmesWeb; ISO 7089 – fasten.it, Ferrofast, Westfield Fasteners, MechaHandbook.

# ISO 4762 – šroub s válcovou hlavou a vnitřním šestihranem: (dk, k, s, t).
SOCKET_HEAD = {
    "M2": (3.8, 2.0, 1.5, 1.0), "M2.5": (4.5, 2.5, 2.0, 1.1), "M3": (5.5, 3.0, 2.5, 1.3),
    "M4": (7.0, 4.0, 3.0, 2.0), "M5": (8.5, 5.0, 4.0, 2.5), "M6": (10.0, 6.0, 5.0, 3.0),
    "M8": (13.0, 8.0, 6.0, 4.0), "M10": (16.0, 10.0, 8.0, 5.0), "M12": (18.0, 12.0, 10.0, 6.0),
    "M16": (24.0, 16.0, 14.0, 8.0), "M20": (30.0, 20.0, 17.0, 10.0),
    "M24": (36.0, 24.0, 19.0, 12.0), "M30": (45.0, 30.0, 22.0, 15.5),
}
# ISO 4017 – šroub se šestihrannou hlavou: (s, k).
HEX_HEAD = {
    "M2": (4.0, 1.4), "M2.5": (5.0, 1.7), "M3": (5.5, 2.0), "M4": (7.0, 2.8), "M5": (8.0, 3.5),
    "M6": (10.0, 4.0), "M8": (13.0, 5.3), "M10": (16.0, 6.4), "M12": (18.0, 7.5),
    "M16": (24.0, 10.0), "M20": (30.0, 12.5), "M24": (36.0, 15.0), "M30": (46.0, 18.7),
}
# ISO 10642 – zápustný šroub s vnitřním šestihranem (hlava 90°): (dk, k, s, t).
COUNTERSUNK_HEAD = {
    "M3": (6.72, 1.86, 2.0, 1.1), "M4": (8.96, 2.48, 2.5, 1.5), "M5": (11.2, 3.1, 3.0, 1.9),
    "M6": (13.44, 3.72, 4.0, 2.2), "M8": (17.92, 4.96, 5.0, 3.0), "M10": (22.4, 6.2, 6.0, 3.6),
    "M12": (26.88, 7.44, 8.0, 4.3), "M16": (33.6, 8.8, 10.0, 4.8),
    "M20": (40.32, 10.16, 12.0, 5.6),
}
# ISO 4032 – šestihranná matice: (s, m).
NUT = {
    "M2": (4.0, 1.6), "M2.5": (5.0, 2.0), "M3": (5.5, 2.4), "M4": (7.0, 3.2), "M5": (8.0, 4.7),
    "M6": (10.0, 5.2), "M8": (13.0, 6.8), "M10": (16.0, 8.4), "M12": (18.0, 10.8),
    "M16": (24.0, 14.8), "M20": (30.0, 18.0), "M24": (36.0, 21.5), "M30": (46.0, 25.6),
}
# ISO 7089 – plochá podložka: (d1, d2, h).
WASHER = {
    "M2": (2.2, 5.0, 0.3), "M2.5": (2.7, 6.0, 0.5), "M3": (3.2, 7.0, 0.5),
    "M4": (4.3, 9.0, 0.8), "M5": (5.3, 10.0, 1.0), "M6": (6.4, 12.0, 1.6),
    "M8": (8.4, 16.0, 1.6), "M10": (10.5, 20.0, 2.0), "M12": (13.0, 24.0, 2.5),
    "M16": (17.0, 30.0, 3.0), "M20": (21.0, 37.0, 3.0), "M24": (25.0, 44.0, 4.0),
    "M30": (31.0, 56.0, 4.0),
}

# --- Ložiska, kolíky, pera ------------------------------------------------------------------

# Kuličková ložiska (otevřená): (d, D, B). Zdroje: SKF (6000, 6200, 618/8), katalog
# valiveloziska.sk, ISK, Rubix, NSK. 688 otevřené je 8 × 16 × 4 (zakryté 688ZZ má šířku 5).
BEARING = {
    "623": (3, 10, 4), "624": (4, 13, 5), "625": (5, 16, 5), "626": (6, 19, 6),
    "608": (8, 22, 7), "688": (8, 16, 4),
    "6000": (10, 26, 8), "6001": (12, 28, 8), "6002": (15, 32, 9), "6003": (17, 35, 10),
    "6004": (20, 42, 12), "6005": (25, 47, 12), "6006": (30, 55, 13), "6007": (35, 62, 14),
    "6008": (40, 68, 15), "6009": (45, 75, 16), "6010": (50, 80, 16),
    "6200": (10, 30, 9), "6201": (12, 32, 10), "6202": (15, 35, 11), "6203": (17, 40, 12),
    "6204": (20, 47, 14), "6205": (25, 52, 15), "6206": (30, 62, 16), "6207": (35, 72, 17),
    "6208": (40, 80, 18), "6209": (45, 85, 19), "6210": (50, 90, 20),
}
# ISO 2338 – válcový kolík: průměr → sražení konců c. Zdroje: Boltport, fasten.it.
PIN = {"2": 0.35, "3": 0.5, "4": 0.63, "5": 0.8, "6": 1.2, "8": 1.6, "10": 2.0, "12": 2.5,
       "16": 3.0, "20": 3.5}
# DIN 6885-1 tvar A – těsné pero: b×h → (hřídel nad, do, t1 v hřídeli, t2 v náboji).
# Zdroje: fasten.it, Ganter (katalog DIN 6885-1), JW Winco.
KEY = {
    "2x2": (6, 8, 1.2, 1.0), "3x3": (8, 10, 1.8, 1.4), "4x4": (10, 12, 2.5, 1.8),
    "5x5": (12, 17, 3.0, 2.3), "6x6": (17, 22, 3.5, 2.8), "8x7": (22, 30, 4.0, 3.3),
    "10x8": (30, 38, 5.0, 3.3), "12x8": (38, 44, 5.0, 3.3), "14x9": (44, 50, 5.5, 3.8),
    "16x10": (50, 58, 6.0, 4.3), "18x11": (58, 65, 7.0, 4.4), "20x12": (65, 75, 7.5, 4.9),
    "22x14": (75, 85, 9.0, 5.4), "25x14": (85, 95, 9.0, 5.4), "28x16": (95, 110, 10.0, 6.4),
}

# --- Ocelové profily ------------------------------------------------------------------------

# IPE (EN 10365): (h, b, tw, tf, r, A [cm²]). Zdroje: STAD (technické listy IPE),
# beamdimensions.com, steel-insdag; A = 2·b·tf + (h − 2·tf)·tw + (4 − π)·r² sedí na ±0,05 cm².
IPE = {
    80: (80, 46, 3.8, 5.2, 5, 7.64), 100: (100, 55, 4.1, 5.7, 7, 10.3),
    120: (120, 64, 4.4, 6.3, 7, 13.2), 140: (140, 73, 4.7, 6.9, 7, 16.4),
    160: (160, 82, 5.0, 7.4, 9, 20.1), 180: (180, 91, 5.3, 8.0, 9, 23.9),
    200: (200, 100, 5.6, 8.5, 12, 28.5), 220: (220, 110, 5.9, 9.2, 12, 33.4),
    240: (240, 120, 6.2, 9.8, 15, 39.1), 270: (270, 135, 6.6, 10.2, 15, 45.9),
    300: (300, 150, 7.1, 10.7, 15, 53.8), 330: (330, 160, 7.5, 11.5, 18, 62.6),
    360: (360, 170, 8.0, 12.7, 18, 72.7), 400: (400, 180, 8.6, 13.5, 21, 84.5),
}
# UPN (EN 10279/DIN 1026-1): (h, b, tw, tf, r1, r2, A [cm²]). Sklon vnitřní strany pásnice
# 8 % (do výšky 300), tf platí v polovině šířky b od hřbetu. Zdroje: projectmaterials,
# cad-steel.net, Fistco, ArcelorMittal „Fers U normaux européens“.
UPN = {
    80: (80, 45, 6.0, 8.0, 8.0, 4.0, 11.0), 100: (100, 50, 6.0, 8.5, 8.5, 4.5, 13.5),
    120: (120, 55, 7.0, 9.0, 9.0, 4.5, 17.0), 140: (140, 60, 7.0, 10.0, 10.0, 5.0, 20.4),
    160: (160, 65, 7.5, 10.5, 10.5, 5.5, 24.0), 180: (180, 70, 8.0, 11.0, 11.0, 5.5, 28.0),
    200: (200, 75, 8.5, 11.5, 11.5, 6.0, 32.2), 220: (220, 80, 9.0, 12.5, 12.5, 6.5, 37.4),
    240: (240, 85, 9.5, 13.0, 13.0, 6.5, 42.3),
}
UPN_SLOPE = 0.08
# Rovnoramenný úhelník L (EN 10056-1): (a, t) → (r1, r2 = r1/2, A [cm²]). Zdroje: Roymech,
# Engineers Edge, europanels.pl; A = t·(2a − t) + (1 − π/4)·(r1² − 2·r2²).
ANGLE = {
    (20, 3): (3.5, 1.75, 1.12), (25, 3): (3.5, 1.75, 1.42), (30, 3): (5.0, 2.5, 1.74),
    (40, 4): (6.0, 3.0, 3.08), (50, 5): (7.0, 3.5, 4.80), (60, 6): (8.0, 4.0, 6.91),
    (70, 7): (9.0, 4.5, 9.40), (80, 8): (10.0, 5.0, 12.3), (90, 9): (11.0, 5.5, 15.5),
    (100, 10): (12.0, 6.0, 19.2), (120, 12): (13.0, 6.5, 27.5),
}
# Jekly tvářené za studena (EN 10219-2): (B, H, t) – běžně skladované rozměry (Ferona,
# Tata Hybox, eHorst). Rohy podle normy (výpočtové hodnoty), viz rhs_radii.
RHS = ((20, 20, 2), (25, 25, 2), (30, 30, 2), (30, 30, 3), (40, 40, 2), (40, 40, 3),
       (50, 50, 2), (50, 50, 3), (60, 60, 3), (60, 60, 4), (80, 80, 3), (80, 80, 4),
       (80, 80, 5), (100, 100, 4), (100, 100, 5), (120, 120, 6), (30, 20, 2), (40, 20, 2),
       (50, 25, 2), (50, 30, 3), (60, 40, 2), (60, 40, 3), (60, 40, 4), (80, 40, 2),
       (80, 40, 3), (100, 50, 4), (100, 60, 5), (120, 60, 4), (120, 80, 5))
# Trubky (EN 10219/10210): (D, t) – běžné rozměry.
CHS = ((21.3, 2.0), (26.9, 2.0), (26.9, 2.3), (33.7, 2.6), (42.4, 2.6), (42.4, 3.0),
       (48.3, 2.6), (48.3, 3.2), (48.3, 5.0), (60.3, 2.9), (60.3, 3.2), (60.3, 4.5),
       (76.1, 2.9), (76.1, 4.0), (88.9, 3.2), (88.9, 4.0), (114.3, 3.6), (114.3, 5.0),
       (139.7, 4.0), (139.7, 5.0), (168.3, 4.5), (168.3, 6.3), (219.1, 8.0))


def rhs_radii(t: float) -> tuple[float, float]:
    """Vnější a vnitřní poloměr rohu jeklu tvářeného za studena podle tloušťky stěny
    (výpočtové hodnoty EN 10219-2: 2t / 2,5t / 3t; skutečný roh smí být 1,6–2,4t …)."""
    outer = 2.0 * t if t <= 6 else 2.5 * t if t <= 10 else 3.0 * t
    return outer, outer - t


def _number(value: float) -> str:
    return f"{value:g}"


def _comma(value: float) -> str:
    return f"{value:g}".replace(".", ",")


SECTIONS: dict[str, str] = {}  # klíč profilu → popisek v okně
for _h in IPE:
    SECTIONS[f"IPE {_h}"] = f"IPE {_h}"
for _h in UPN:
    SECTIONS[f"UPN {_h}"] = f"U {_h} (UPN)"
for _a, _t in ANGLE:
    SECTIONS[f"L {_a}x{_t}"] = f"L {_a} × {_t}"
for _b, _hh, _t in RHS:
    SECTIONS[f"RHS {_b}x{_hh}x{_t}"] = f"jekl {_b} × {_hh} × {_t}"
for _d, _t in CHS:
    SECTIONS[f"CHS {_number(_d)}x{_number(_t)}"] = f"trubka Ø{_comma(_d)} × {_comma(_t)}"


@dataclass(frozen=True)
class PartKind:
    """Druh normalizovaného dílu: název v okně, velikosti a zda má délku."""

    label: str
    sizes: dict[str, str]  # klíč velikosti → popisek v okně
    length: str = ""  # popis délky; prázdné = díl délku nemá


def _thread_sizes(table: dict) -> dict[str, str]:
    return {size: size for size in table}


KINDS: dict[str, PartKind] = {
    "socket_screw": PartKind("šroub s válcovou hlavou, imbus – ISO 4762",
                             _thread_sizes(SOCKET_HEAD), "délka dříku pod hlavou"),
    "hex_screw": PartKind("šroub se šestihrannou hlavou – ISO 4017", _thread_sizes(HEX_HEAD),
                          "délka dříku pod hlavou"),
    "countersunk_screw": PartKind("zápustný šroub, imbus – ISO 10642",
                                  _thread_sizes(COUNTERSUNK_HEAD), "celková délka i s hlavou"),
    "nut": PartKind("šestihranná matice – ISO 4032", _thread_sizes(NUT)),
    "washer": PartKind("podložka – ISO 7089", _thread_sizes(WASHER)),
    "bearing": PartKind("kuličkové ložisko",
                        {key: f"{key} ({d} × {big} × {width})"
                         for key, (d, big, width) in BEARING.items()}),
    "pin": PartKind("válcový kolík – ISO 2338", {key: f"Ø{key}" for key in PIN}, "délka kolíku"),
    "key": PartKind("těsné pero – DIN 6885 tvar A",
                    {key: f"{key.replace('x', ' × ')} (hřídel {low}–{high})"
                     for key, (low, high, _t1, _t2) in KEY.items()}, "délka pera"),
    "profile": PartKind("ocelový profil – tyč", SECTIONS, "délka tyče"),
}


def kind_of(kind: str) -> PartKind:
    if kind not in KINDS:
        raise StandardError(f"Neznámý normalizovaný díl „{kind}“, povolené: "
                            f"{', '.join(KINDS)}.")
    return KINDS[kind]


def normalize_section(text: str) -> str:
    """„l 50×5“, „IPE100“ → klíč profilu („L 50x5“, „IPE 100“)."""
    cleaned = re.sub(r"\s*[x×*X]\s*", "x", str(text).strip()).replace(",", ".")
    match = re.fullmatch(r"([A-Za-z]+)\s*([0-9.x]+)", cleaned)
    if not match:
        return str(text)
    return f"{match.group(1).upper()} {match.group(2)}"


def _size(kind: str, size: str) -> str:
    sizes = kind_of(kind).sizes
    key = normalize_section(size) if kind == "profile" else str(size).strip()
    if kind == "key":
        key = key.replace("×", "x").replace(" ", "")
    if key not in sizes:
        shown = ", ".join(list(sizes)[:8]) + (" …" if len(sizes) > 8 else "")
        raise StandardError(f"{kind_of(kind).label}: velikost „{size}“ v tabulce není "
                            f"(jsou: {shown}).")
    return key


def nominal(size: str) -> float:
    """Jmenovitý průměr závitu („M6“ → 6)."""
    return float(size.removeprefix("M"))


# --- Profily (2D) ---------------------------------------------------------------------------


def section_sketch(designation: str) -> Sketch:
    """Průřez ocelového profilu ve vlastní rovině, střed obalového obdélníku v počátku.

    IPE a U stojí na výšku (výška podél Y), U má hřbet stojiny vlevo, úhelník L roh vlevo
    dole."""
    key = _size("profile", designation)
    family, size = key.split(" ")
    if family == "IPE":
        shape = _ipe(*IPE[int(size)][:5])
    elif family == "UPN":
        shape = _upn(*UPN[int(size)][:6])
    elif family == "L":
        a, t = (int(v) for v in size.split("x"))
        shape = _angle(a, t, *ANGLE[(a, t)][:2])
    elif family == "RHS":
        width, height, t = (float(v) for v in size.split("x"))
        outer, inner = rhs_radii(t)
        shape = (RectangleRounded(width, height, outer)
                 - RectangleRounded(width - 2 * t, height - 2 * t, inner))
    else:  # CHS
        diameter, t = (float(v) for v in size.split("x"))
        shape = Circle(diameter / 2) - Circle(diameter / 2 - t)
    box = shape.bounding_box()
    return Sketch() + Pos(-box.center().X, -box.center().Y) * shape


def section_area(designation: str) -> float | None:
    """Plocha průřezu z tabulky [mm²] (u IPE, UPN, L), jinak None – pro kontrolu tvaru."""
    family, size = _size("profile", designation).split(" ")
    if family == "IPE":
        return IPE[int(size)][5] * 100
    if family == "UPN":
        return UPN[int(size)][6] * 100
    if family == "L":
        a, t = (int(v) for v in size.split("x"))
        return ANGLE[(a, t)][2] * 100
    return None


def _corners(shape: Sketch, points: list[tuple[float, float]]) -> list:
    return [v for v in shape.vertices()
            if any(abs(v.X - x) < 1e-6 and abs(v.Y - y) < 1e-6 for x, y in points)]


def _ipe(h: float, b: float, tw: float, tf: float, r: float) -> Sketch:
    side = (b - tw) / 2
    shape = Rectangle(b, h)
    for sign in (-1, 1):
        shape -= Pos(sign * (tw / 2 + side / 2), 0) * Rectangle(side, h - 2 * tf)
    roots = [(sx * tw / 2, sy * (h / 2 - tf)) for sx in (-1, 1) for sy in (-1, 1)]
    return fillet(_corners(shape, roots), r)


def _upn(h: float, b: float, tw: float, tf: float, r1: float, r2: float) -> Sketch:
    """U s pásnicemi zúženými ke kraji (sklon 8 %); tloušťka tf platí v polovině šířky pásnice
    od hřbetu (x = b/2), hřbet stojiny je v x = 0."""
    def inner_y(x: float) -> float:  # vnitřní strana horní pásnice
        return h / 2 - tf - UPN_SLOPE * (b / 2 - x)

    top = [(0, h / 2), (b, h / 2), (b, inner_y(b)), (tw, inner_y(tw))]
    bottom = [(x, -y) for x, y in reversed(top)]
    shape = Sketch() + Polygon(*top, *bottom, align=None)
    shape = fillet(_corners(shape, [(tw, inner_y(tw)), (tw, -inner_y(tw))]), r1)
    return fillet(_corners(shape, [(b, inner_y(b)), (b, -inner_y(b))]), r2)


def _angle(a: float, t: float, r1: float, r2: float) -> Sketch:
    points = [(0, 0), (a, 0), (a, t), (t, t), (t, a), (0, a)]
    shape = Sketch() + Polygon(*points, align=None)
    shape = fillet(_corners(shape, [(t, t)]), r1)
    return fillet(_corners(shape, [(a, t), (t, a)]), r2)


def _outline(shape: Sketch) -> Sketch:
    """Obrys bez děr (trubka → kruh) – pro kapsu."""
    return Sketch() + [face.__class__(face.outer_wire()) for face in shape.faces()]


# --- Díly (3D) ------------------------------------------------------------------------------


def part_shape(kind: str, size: str, length: float | None = None, pocket: bool = False,
               clearance: float = 0.0) -> Part:
    """Normalizovaný díl v místních souřadnicích (viz popis modulu).

    ``pocket`` = obrys bez děr pro kapsu, zvětšený o ``clearance`` na každou stranu."""
    spec = kind_of(kind)
    key = _size(kind, size)
    if spec.length:
        if length is None:
            raise StandardError(f"{spec.label}: chybí délka ({spec.length}).")
        if length <= 0:
            raise StandardError(f"{spec.label}: délka musí být kladná (je {length:g}).")
    if clearance < 0:
        raise StandardError(f"Vůle kapsy nesmí být záporná (je {clearance:g}).")
    g = clearance if pocket else 0.0
    return _BUILDERS[kind](key, length, pocket, g)


def _cylinder(radius: float, z0: float, z1: float) -> Part:
    return Pos(0, 0, z0) * Cylinder(radius, z1 - z0,
                                    align=(Align.CENTER, Align.CENTER, Align.MIN))


def _prism(sketch: Sketch, z0: float, z1: float) -> Part:
    return extrude(_Plane.XY.offset(z0) * sketch, z1 - z0)


def _hexagon(across_flats: float) -> Sketch:
    return Sketch() + RegularPolygon(across_flats / 2, 6, major_radius=False)


def _socket(s: float, top: float, depth: float) -> Part:
    return _prism(_hexagon(s), top - depth, top + 1e-3)


def _socket_screw(size: str, length: float, pocket: bool, g: float) -> Part:
    dk, k, s, t = SOCKET_HEAD[size]
    d = nominal(size)
    head = _cylinder(dk / 2 + g, -g, k + g)
    if not pocket:
        head -= _socket(s, k, t)
    return head + _cylinder(d / 2 + g, -length - g, 0)


def _hex_screw(size: str, length: float, pocket: bool, g: float) -> Part:
    s, k = HEX_HEAD[size]
    d = nominal(size)
    return _prism(_hexagon(s + 2 * g), -g, k + g) + _cylinder(d / 2 + g, -length - g, 0)


def _countersunk_screw(size: str, length: float, pocket: bool, g: float) -> Part:
    dk, k, s, t = COUNTERSUNK_HEAD[size]
    d = nominal(size)
    if length <= k:
        raise StandardError(f"Zápustný šroub {size}: celková délka {length:g} musí být větší "
                            f"než výška hlavy {k:g}.")
    top = _Plane.XY * Circle(dk / 2 + g)
    bottom = _Plane.XY.offset(-k) * Circle(d / 2 + g)
    head = loft([bottom.faces()[0], top.faces()[0]])  # kužel 90°
    if pocket and g:
        head += _cylinder(dk / 2 + g, 0, g)
    elif not pocket:
        head -= _socket(s, 0, t)
    return head + _cylinder(d / 2 + g, -length - g, -k)


def _nut(size: str, length: float | None, pocket: bool, g: float) -> Part:
    s, m = NUT[size]
    body = _prism(_hexagon(s + 2 * g), -g, m + g)
    return body if pocket else body - _cylinder(nominal(size) / 2, -1, m + 1)


def _washer(size: str, length: float | None, pocket: bool, g: float) -> Part:
    d1, d2, h = WASHER[size]
    body = _cylinder(d2 / 2 + g, -g, h + g)
    return body if pocket else body - _cylinder(d1 / 2, -1, h + 1)


def _bearing(size: str, length: float | None, pocket: bool, g: float) -> Part:
    d, big, width = BEARING[size]
    body = _cylinder(big / 2 + g, -g, width + g)
    return body if pocket else body - _cylinder(d / 2, -1, width + 1)


def _pin(size: str, length: float, pocket: bool, g: float) -> Part:
    c = PIN[size]
    d = float(size)
    body = _cylinder(d / 2 + g, -g, length + g)
    if pocket:
        return body
    if 2 * c >= length:
        raise StandardError(f"Kolík Ø{size}: délka {length:g} je kratší než obě sražení.")
    return chamfer(body.edges(), c)


def _key(size: str, length: float, pocket: bool, g: float) -> Part:
    b, h = (float(v) for v in size.split("x"))
    t1 = KEY[size][2]
    if length < b:
        raise StandardError(f"Pero {size.replace('x', ' × ')}: délka {length:g} musí být aspoň "
                            f"šířka pera {b:g}.")
    outline = Sketch() + SlotOverall(length + 2 * g, b + 2 * g)
    return _prism(outline, -t1 - g, h - t1 + g)


def _profile(size: str, length: float, pocket: bool, g: float) -> Part:
    shape = section_sketch(size)
    if pocket:
        shape = _outline(shape)
        if g:
            shape = Sketch() + offset(shape, g, kind=Kind.INTERSECTION)
    return _prism(shape, -g, length + g)


_BUILDERS = {
    "socket_screw": _socket_screw, "hex_screw": _hex_screw,
    "countersunk_screw": _countersunk_screw, "nut": _nut, "washer": _washer,
    "bearing": _bearing, "pin": _pin, "key": _key, "profile": _profile,
}


def summary(kind: str, size: str, length: float | str | None = None, count: int = 1) -> str:
    """Krátký popis do stromu, např. „ISO 4762 M6 × 20, 4 ks“."""
    label = kind_of(kind).label if kind in KINDS else str(kind)
    norm = label.rsplit(" – ", 1)[-1] if " – " in label else label
    shown = KINDS[kind].sizes.get(size, str(size)) if kind in KINDS else str(size)
    if kind in ("bearing",):
        text = f"ložisko {shown}"
    elif kind == "profile":
        text = shown
    elif kind == "pin":
        text = f"kolík {shown}"
    elif kind == "key":
        text = f"pero {str(size).replace('x', ' × ')}"
    else:
        text = f"{norm} {shown}"
    if KINDS.get(kind) and KINDS[kind].length and length is not None:
        text += f" × {length}"
    return text + (f", {count} ks" if count > 1 else "")
