"""MT – přiložení jha a směry magnetizace (etapa 12).

Závazné vymezení je v ``docs/ndt/22-vymezeni-mt.md``: jen geometrie zkoušky jhem – kam lze
přiložit zjednodušený model jha, kterou část povrchu zasáhne účinná oblast mezi póly a jakým
orientačním směrem tam vede pole, zda místo pokryjí dva směry magnetizace a zda je místo
přístupné pro nanesení a prohlídku (kontroly PT). Žádná intenzita ani rozložení pole,
citlivost ani detekovatelnost vad. Návrh, výchozí hodnoty a ručně spočítané výsledky jsou
v ``docs/ndt/21-navrh-etapa-12.md``.

Jho se zkouší ze středů na mřížce ploch u studie v osmi směrech po 22,5° (pevně, žádná
náhoda) a hranice platných poloh se dohledá půlením. Místo pólu = první dotyk kružnice
o poloměru d/2 sklápěné od kolmice; pól dosedá stejným výpočtem jako přímá sonda (etapa 03).
O tom, že se jho vejde, rozhoduje přesný průnik s tělesem OCCT – paprsky jsou jen síto.
Nejisté se nikdy nepočítá jako pokryté.
"""

from __future__ import annotations

import csv
import json
import math
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from skodacad.materials import DISPLAY_NAMES, material_key
from skodacad.ndt import MT_DISCLAIMER, MT_MAP
from skodacad.ndt.devices import DeviceError, Probe, place, reuse_placements
from skodacad.ndt.geometry import OVERLAP_TOL, GeometryError, PartGeometry, Point, overlap
from skodacad.ndt.pt import COLORS, GRADES, PtError, PtSettings, Sampler
from skodacad.thickness_map import MapError, _Surface

ALGORITHM = "ndt-mt-jho 1"
DIRECTIONS = 8  # směry jha po 22,5° (jho je souměrné, 180° stačí)
DIRECTION_STEP = 180.0 / DIRECTIONS
SHOWN = (0, 2, 4, 6)  # směry v přepínači mapy: 0°, 45°, 90°, 135°
SHOE_MM = 15.0  # botka pólu přiléhá k ploše; zbytek nohy vede ve směru jha (ke tělu)
SWEEP_DEG = 5.0  # krok sklápění kružnice při hledání místa pólu
SWEEP_ITER = 18  # půlení úhlu kružnice (5° / 2^18 – setiny mikrometru)
REFINE_MM = 0.5  # hranice platných poloh jha se dohledá na tuto přesnost
SIGHT_MM = 2.0  # místo mimo rovinu středu o víc než tolik musí být ze středu vidět
FACING = 0.5  # plocha místa a plocha středu jha svírají nejvýš 60° (cos 60°)
# Místo mimo tečnou rovinu středu leží nejvýš 45° pod ní nebo nad ní (|w| ≤ vzdálenost v rovině):
# převýšení svaru a koutový svar ano, dno kapsy pod jhem stojícím vedle ní ne.
UNCLEAR = 0.5  # sklopený směr pole kratší než polovina → směr pole v místě nejasný
ORIENT_STEP = 0.5  # orientace vad se zkouší po půl stupni
TARGET_SAMPLES = 1000  # automatický krok sítě míst
TARGET_CENTERS = 190  # automatický krok středů: asi 1500 poloh jha (190 × 8)
MAX_SAMPLES = 20_000
MAX_CENTERS = 5_000
MIN_STEP = 0.5  # mm
MIN_CENTER_STEP = 2.0  # mm
_AREA_PER_STEP2 = 0.2  # síť mapy tloušťky: trojúhelník ≈ 0,2 · krok²
SECONDS_PER_PLACEMENT = 0.05  # odhad (změřeno 19. 10. 2026 v cloudu: 13–80 ms na polohu)
SECONDS_PER_SAMPLE = 0.03  # nanesení a prohlídka z PT

STATES = {"ok": "Pokryto ve všech orientacích vad", "limited": "Jen část orientací nebo omezeně",
          "blocked": "Nepokryto", "uncertain": "Nelze spolehlivě vyhodnotit"}
FIELD = {"ok": "všechny orientace", "limited": "jen část orientací", "blocked": "jho se nevejde",
         "uncertain": "nejisté"}
VIEWS = {None: "Celkem", "d0": "Pole 0°", "d2": "Pole 45°", "d4": "Pole 90°", "d6": "Pole 135°",
         "apply": "Nanesení", "inspect": "Prohlídka"}
FAILURES = {  # druh nevyhovujícího přiložení jha → krátký popis do souhrnu
    "no_room": "nad místem není volno pro jho",
    "no_site": "pól nemá kam dosednout",
    "wall": "mezi místem a pólem je stěna",
    "overhang": "pól přesahuje okraj",
    "lift_off": "mezera pod pólem",
    "shoe": "pól naráží do dílu",
    "legs": "nohy svírají příliš velký úhel",
    "body": "noha nebo tělo jha naráží",
}
REASONS = {  # druh důvodu místa → popis v souhrnu
    "field_blocked": "jho se nevejde v žádném směru",
    "field_limited": "jen část orientací vad (chybí druhý směr pole)",
    "apply_blocked": "nanesení nejde", "apply_limited": "nanesení jen šikmo",
    "inspect_blocked": "bez výhledu", "inspect_eye": "oko se nevejde do vzdálenosti prohlídky",
    "inspect_limited": "prohlídka jen šikmo nebo se zrcátkem",
    "unclear": "směr pole v místě nejasný", "uncertain": "nejistý výpočet",
}
FERROMAGNETIC = {"ocel": "yes", "litina": "yes", "nerez": "confirm", "hlinik": "no",
                 "mosaz": "no", "med": "no", "titan": "no", "pla": "no", "petg": "no", "abs": "no"}
MATERIAL_SOURCE = ("ASTM E1444 / E3024: MT jen pro feromagnetické materiály, pro austenitické "
                   "nerezové oceli ne")
CHOSEN = "zvoleno pro výpočet, ne z normy"
ZONE_SOURCE = "ISO 17638:2016, obr. 4 (z veřejných výňatků, plný text neověřen)"
DETECT_SOURCE = ("ISO 9934-1 (tok účinný do 60° od optimálního směru) a ISO 17638 (dva směry, "
                 "odchylka od kolmých nejvýš 30°)")
PERCENT_NOTE = ("Procento vyjadřuje jen geometrický podíl plochy, nikoli pravděpodobnost "
                "nalezení vady.")
FIELD_NOTE = ("Směr pole je jen orientační – přímka mezi póly sklopená do plochy; skutečné "
              "siločáry kolem otvorů, hran a v rozích se nepočítají, intenzita pole také ne.")
LIGHT_NOTE = "Osvětlení a UV-A pro prohlídku (ISO 3059) program nepočítá – ověř je na místě."
ANGLE_NOTE = "Úhel 0° = průmět osy +X do plochy (u plochy kolmé na X osa +Y), kladně proti " \
             "směru hodin při pohledu zvenku."


class MtError(ValueError):
    """Mapa MT nejde spočítat nebo má chybné nastavení (zpráva je česky)."""


def _n(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _dec(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


# --- nastavení -------------------------------------------------------------------------------

_LIMITS = {  # klíč: (český popis, nejméně, nejvýš)
    "step_mm": ("Krok sítě [mm]", MIN_STEP, 100.0),
    "center_step_mm": ("Krok středů jha [mm]", MIN_CENTER_STEP, 200.0),
    "spacing_mm": ("Rozteč pólů [mm]", 20.0, 1000.0),
    "min_spacing_mm": ("Nejmenší rozteč pólů [mm]", 20.0, 1000.0),
    "pole_zone_mm": ("Oblast u pólu, která se nepočítá [mm]", 0.0, 500.0),
    "pole_mm": ("Pól – průměr [mm]", 1.0, 200.0),
    "leg_mm": ("Výška nohy (od plochy k tělu) [mm]", SHOE_MM + 1.0, 1000.0),
    "body_mm": ("Tělo jha – průřez [mm]", 1.0, 500.0),
    "body_overhang_mm": ("Přesah těla za nohy [mm]", 0.0, 500.0),
    "max_gap_mm": ("Mezera pod pólem – nejvýš [mm]", 0.0, 20.0),
    "leg_angle_deg": ("Úhel mezi nohami – nejvýš [°]", 0.0, 179.0),
    "step_over_mm": ("Spojnice místa a pólu nad povrchem [mm]", 0.0, 200.0),
    "detect_deg": ("Nejmenší úhel vady k poli [°]", 1.0, 89.0),
    "spray_deg": ("Nanesení – nejvýš od kolmice [°]", 0.0, 89.0),
    "spray_limit_deg": ("Nanesení šikmo – nejvýš od kolmice [°]", 0.0, 89.9),
    "view_deg": ("Prohlídka – aspoň k povrchu [°]", 1.0, 90.0),
    "view_limit_deg": ("Prohlídka šikmo – aspoň k povrchu [°]", 0.1, 90.0),
    "view_distance_mm": ("Vzdálenost oka – nejvýš [mm]", 1.0, 10000.0),
    "eye_mm": ("Volný prostor pro oko – průměr [mm]", 0.0, 1000.0),
}
_OPTIONAL = ("step_mm", "center_step_mm")


@dataclass(frozen=True)
class MtSettings:
    """Nastavení mapy MT uložené v MT studii (``mt``, formát 20). Chybějící = výchozí."""

    step_mm: float | None = None  # None = automaticky (asi TARGET_SAMPLES míst)
    center_step_mm: float | None = None  # None = automaticky (asi 1500 poloh jha)
    spacing_mm: float = 100.0
    min_spacing_mm: float = 75.0  # záloha, když rozteč spacing_mm nejde (= spacing → bez zálohy)
    pole_zone_mm: float = 25.0
    pole_mm: float = 20.0
    leg_mm: float = 60.0
    body_mm: float = 40.0
    body_overhang_mm: float = 20.0
    max_gap_mm: float = 1.0
    leg_angle_deg: float = 90.0
    step_over_mm: float = 10.0
    detect_deg: float = 30.0
    ferromagnetic: bool | None = None  # True = potvrzeno uživatelem (nerez, neuvedený)
    apply: bool = True  # kontrola nanesení detekčního prostředku (nástřik z PT)
    inspect: bool = True  # kontrola prohlídky (z PT)
    spray_deg: float = 60.0
    spray_limit_deg: float = 85.0
    view_deg: float = 30.0
    view_limit_deg: float = 5.0
    view_distance_mm: float = 600.0
    eye_mm: float = 50.0

    def __post_init__(self) -> None:
        for key, (label, low, high) in _LIMITS.items():
            value = getattr(self, key)
            if key in _OPTIONAL and value is None:
                continue
            if (isinstance(value, bool) or not isinstance(value, int | float)
                    or not math.isfinite(value) or not low <= value <= high):
                raise MtError(f"{label} musí být číslo {_n(low)}–{_n(high)}.")
        for key in ("apply", "inspect"):
            if not isinstance(getattr(self, key), bool):
                raise MtError(f"Nastavení MT „{key}“ musí být true nebo false.")
        if self.ferromagnetic is not None and not isinstance(self.ferromagnetic, bool):
            raise MtError("Potvrzení feromagnetického materiálu musí být true, false nebo "
                          "chybět.")
        if self.min_spacing_mm > self.spacing_mm:
            raise MtError("Nejmenší rozteč pólů musí být nejvýš rozteč pólů.")
        if self.min_spacing_mm <= 2 * self.pole_zone_mm:
            raise MtError("Rozteč pólů musí být větší než dvojnásobek oblasti u pólu – jinak "
                          "mezi póly nezbude účinná oblast.")
        if self.min_spacing_mm < self.pole_mm:
            raise MtError("Rozteč pólů musí být aspoň průměr pólu.")
        if self.spray_limit_deg < self.spray_deg:
            raise MtError("Nanesení šikmo musí povolit aspoň tak velký úhel od kolmice jako "
                          "běžné nanesení.")
        if self.view_limit_deg > self.view_deg:
            raise MtError("Prohlídka šikmo musí mít úhel k povrchu nejvýš stejný jako běžná "
                          "prohlídka.")

    @classmethod
    def from_dict(cls, data: Any) -> MtSettings:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise MtError("Nastavení MT („mt“) musí být objekt, např. {\"spacing_mm\": 100}.")
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise MtError(f"Nastavení MT nezná {', '.join(unknown)} "
                          f"(zná {', '.join(sorted(known))}).")
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in (*_OPTIONAL, "ferromagnetic"):
            if data[key] is None:
                del data[key]
        return data

    @property
    def spacings(self) -> tuple[float, ...]:
        """Rozteče, které se zkouší (hlavní, pak záloha)."""
        if self.min_spacing_mm < self.spacing_mm:
            return (self.spacing_mm, self.min_spacing_mm)
        return (self.spacing_mm,)

    def pt_settings(self) -> PtSettings:
        """Nanesení a prohlídka se počítají kontrolami PT (bez nástroje)."""
        try:
            return PtSettings(cleaning="rinse", spray_deg=self.spray_deg,
                              spray_limit_deg=self.spray_limit_deg, view_deg=self.view_deg,
                              view_limit_deg=self.view_limit_deg,
                              view_distance_mm=self.view_distance_mm, eye_mm=self.eye_mm)
        except PtError as exc:
            raise MtError(str(exc)) from None

    def lines(self) -> list[str]:
        """Předpoklady výpočtu česky (souhrn, CSV)."""
        fallback = (f", když nejde, zkusí se {_n(self.min_spacing_mm)} mm (ISO 17638: aspoň "
                    f"75 mm)" if self.min_spacing_mm < self.spacing_mm else "")
        lines = [f"Jho: rozteč pólů {_n(self.spacing_mm)} mm{fallback}; pól Ø {_n(self.pole_mm)} "
                 f"mm (botka {_n(SHOE_MM)} mm přiléhá k ploše), výška nohy {_n(self.leg_mm)} mm, "
                 f"tělo {_n(self.body_mm)} × {_n(self.body_mm)} mm s přesahem "
                 f"{_n(self.body_overhang_mm)} mm ({CHOSEN}).",
                 f"Přiložení: mezera pod pólem nejvýš {_n(self.max_gap_mm)} mm, nohy svírají "
                 f"nejvýš {_n(self.leg_angle_deg)}°, spojnice místa a pólu "
                 f"{_n(self.step_over_mm)} mm nad povrchem bez stěny ({CHOSEN}).",
                 f"Účinná oblast: obdélník (d − {_n(2 * self.pole_zone_mm)} mm) × d/2 mezi póly, "
                 f"u každého pólu se {_n(self.pole_zone_mm)} mm nepočítá ({ZONE_SOURCE}).",
                 f"Orientace vad: vada se počítá, když je k poli skloněná aspoň o "
                 f"{_n(self.detect_deg)}°; všechny orientace pokryjí dva směry pole aspoň "
                 f"{_n(2 * self.detect_deg)}° od sebe ({DETECT_SOURCE}).",
                 f"Směry jha: {DIRECTIONS} po {_n(DIRECTION_STEP)}°."]
        if self.apply:
            lines.append(f"Nanesení detekčního prostředku: jde do {_n(self.spray_deg)}° od "
                         f"kolmice, šikmo do {_n(self.spray_limit_deg)}° (kontrola nástřiku PT, "
                         f"{CHOSEN}).")
        if self.inspect:
            lines.append(f"Prohlídka: aspoň {_n(self.view_deg)}° k povrchu (šikmo aspoň "
                         f"{_n(self.view_limit_deg)}°), oko do {_n(self.view_distance_mm)} mm, "
                         f"volný prostor pro oko Ø {_n(self.eye_mm)} mm (kontrola prohlídky PT).")
        return lines


# --- materiál --------------------------------------------------------------------------------


def material_status(material: str | None, confirmed: bool | None = None) -> tuple[str, str]:
    """Je materiál dílu feromagnetický? („ok“ / „confirmed“ / „confirm“ / „no“, věta česky)."""
    key = material_key(material or "")
    name = DISPLAY_NAMES.get(key, material) if key else "neuvedený materiál"
    status = FERROMAGNETIC.get(key, "confirm") if key else "confirm"
    if status == "yes":
        return "ok", f"Materiál {name} je feromagnetický – MT lze geometricky posoudit."
    if status == "no":
        return "no", f"MT nelze použít – {name} není feromagnetický ({MATERIAL_SOURCE})."
    if confirmed:
        return "confirmed", f"Materiál {name}: feromagnetický – potvrzeno uživatelem."
    if key == "nerez":
        return "confirm", ("U nerezi záleží na druhu: austenitická (např. 1.4301) feromagnetická "
                           "není, feritická a martenzitická ano. Když je materiál feromagnetický, "
                           "potvrď to v nastavení MT.")
    return "confirm", (f"Feromagnetičnost materiálu ({name}) nejde z tabulky určit – když je "
                       "feromagnetický, potvrď to v nastavení MT.")


# --- vektory ---------------------------------------------------------------------------------


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v: Point) -> Point | None:
    length = math.sqrt(_dot(v, v))
    return None if length < 1e-12 else (v[0] / length, v[1] / length, v[2] / length)


def _add(a: Point, b: Point, k: float = 1.0) -> Point:
    return (a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k)


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _base(normal: Point) -> Point:
    """Směr 0° v tečné rovině: průmět osy +X, u plochy kolmé na X osa +Y (jako sonda UT)."""
    for axis in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)):
        projected = _add(axis, normal, -_dot(axis, normal))
        unit = _unit(projected)
        if unit is not None and math.sqrt(_dot(projected, projected)) > 1e-6:
            return unit
    return (0.0, 0.0, 1.0)


def direction(normal: Point, angle: float) -> Point:
    """Směr jha v tečné rovině pod úhlem ``angle`` [°] od směru 0°."""
    base = _base(normal)
    side = _cross(normal, base)
    a = math.radians(angle)
    return _unit(_add(_add((0.0, 0.0, 0.0), base, math.cos(a)), side, math.sin(a)))


def _axial(a: float, b: float) -> float:
    """Ostrý úhel mezi dvěma osovými směry (mod 180°)."""
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


# --- jho -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class YokePlacement:
    """Jedno přiložení jha (střed, směr, rozteč) a jeho výsledek."""

    center: Point
    normal: Point
    direction: Point  # spojnice pólů v tečné rovině středu
    spacing: float
    ok: bool
    uncertain: bool  # platné, ale rozhodoval nejistý výpočet (nikdy se nepočítá jako pokryté)
    kind: str  # "ok" nebo druh z FAILURES
    text: str  # česky, proč jho nejde (nebo popis platného přiložení)
    poles: tuple[Point, ...] = ()
    pole_normals: tuple[Point, ...] = ()
    shapes: tuple[Any, ...] = field(default=(), compare=False, repr=False)

    def zone(self, settings: MtSettings) -> tuple[float, float, float]:
        """(poloviční délka podél spojnice, poloviční šířka, hloubka) účinné oblasti [mm]."""
        return (self.spacing - 2 * settings.pole_zone_mm) / 2, self.spacing / 4, self.spacing / 4

    def outline(self, settings: MtSettings, lift: float = 0.5) -> list[Point]:
        """Obrys účinné oblasti v tečné rovině středu (pro kresbu), uzavřený."""
        half_u, half_v, _ = self.zone(settings)
        side = _cross(self.normal, self.direction)
        base = _add(self.center, self.normal, lift)
        corners = [_add(_add(base, self.direction, su * half_u), side, sv * half_v)
                   for su, sv in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
        return [*corners, corners[0]]


class Yoker:
    """Přiložení virtuálního kloubového jha (dva póly, nohy, tělo) k dílu."""

    def __init__(self, geo: PartGeometry, settings: MtSettings) -> None:
        self.geo = geo
        self.settings = settings
        self.shape = geo.part.wrapped
        self.probe = Probe("straight", diameter=settings.pole_mm, height=SHOE_MM,
                           max_gap=settings.max_gap_mm, reserve=0.0)

    def best(self, center: Point, normal: Point, along: Point, shapes: bool = False
             ) -> YokePlacement:
        """Hlavní rozteč, a když nejde, záloha (menší rozteč)."""
        first = self.place(center, normal, along, self.settings.spacing_mm, shapes)
        if first.ok or len(self.settings.spacings) == 1:
            return first
        second = self.place(center, normal, along, self.settings.spacings[1], shapes)
        if second.ok:
            return second
        text = (f"{first.text} Ani rozteč {_n(second.spacing)} mm nejde: "
                f"{second.text[0].lower()}{second.text[1:]}")
        return YokePlacement(first.center, first.normal, first.direction, first.spacing, False,
                             False, first.kind, text, first.poles, first.pole_normals,
                             first.shapes)

    def place(self, center: Point, normal: Point, along: Point, spacing: float,
              shapes: bool = False) -> YokePlacement:
        """Jedno přiložení: místa pólů, stěna, dosednutí pólů, úhel nohou, kolize nohou a těla."""
        s = self.settings
        normal = _unit(normal)
        along = _unit(_add(along, normal, -_dot(along, normal)))
        poles, normals, placed_shapes, uncertain = [], [], [], False

        def fail(kind: str, text: str) -> YokePlacement:
            return YokePlacement(center, normal, along, spacing, False, False, kind, text,
                                 tuple(poles), tuple(normals), tuple(placed_shapes))

        if along is None:
            return fail("no_site", "Směr jha leží kolmo k ploše.")
        for sign in (1.0, -1.0):
            site = self._site(center, normal, (along[0] * sign, along[1] * sign,
                                               along[2] * sign), spacing / 2)
            if site == "room":
                return fail("no_room", "Nad místem není volno pro jho (kolmo nad ním je díl).")
            if site is None:
                return fail("no_site", f"Pól nemá kam dosednout – ve vzdálenosti "
                                       f"{_n(spacing / 2)} mm od místa už není povrch (okraj).")
            try:
                surface = self.geo.surface_at(site)
            except GeometryError as exc:
                return fail("no_site", str(exc))
            q, nq = surface.point, surface.normal
            a = _add(center, normal, s.step_over_mm)
            b = _add(q, nq, s.step_over_mm)
            gap = _sub(b, a)
            length = math.sqrt(_dot(gap, gap))
            if length > 1e-9 and self.geo.cast(a, _unit(gap), length).hits:
                return fail("wall", "Mezi místem a pólem je stěna (spojnice "
                                    f"{_n(s.step_over_mm)} mm nad povrchem narazí do dílu).")
            try:
                pole = place(self.geo, self.probe, q, angle=0.0, face=surface.face,
                             measure_clearance=False)
            except DeviceError as exc:
                return fail("no_site", str(exc))
            poles.append(q)
            normals.append(nq)
            if shapes:
                placed_shapes.append(pole.body)
            if pole.state == "collision":
                return fail("shoe", f"Pól naráží do dílu (průnik {pole.volume:.0f} mm³).")
            if pole.state == "overhang":
                return fail("overhang", f"Pól přesahuje okraj ({pole.overhang * 100:.0f} % "
                                        "plochy pólu nemá pod sebou povrch).")
            if pole.state == "lift_off":
                return fail("lift_off", f"Mezera pod pólem {_dec(pole.gap or 0, 2)} mm, "
                                        f"dovoleno {_n(s.max_gap_mm)} mm.")
            if pole.state == "uncertain":
                uncertain = True
        (q1, q2), (n1, n2) = poles, normals
        legs = math.degrees(math.acos(max(-1.0, min(1.0, _dot(n1, n2)))))
        up = _unit(_add(n1, n2))
        if legs > s.leg_angle_deg + 1e-9 or up is None:
            return fail("legs", f"Nohy svírají {legs:.0f}° (nejvýš {_n(s.leg_angle_deg)}°) – "
                                "plochy pod póly jsou k sobě příliš skloněné.")
        rise = s.leg_mm - SHOE_MM
        tops = [_add(q, n, SHOE_MM) for q, n in ((q1, n1), (q2, n2))]
        solids = [_cylinder(top, up, s.pole_mm / 2, rise) for top in tops]
        ends = [_add(top, up, rise) for top in tops]
        solids.append(_body(ends[0], ends[1], up, s.body_mm, s.body_overhang_mm))
        volume = overlap(self.shape, _compound(solids))
        if shapes:
            placed_shapes.extend(solids)
        if volume is None:
            uncertain = True
        elif volume > OVERLAP_TOL:
            return fail("body", f"Noha nebo tělo jha naráží do dílu (průnik {volume:.0f} mm³).")
        text = (f"Jho se vejde – rozteč {_n(spacing)} mm, nohy svírají {legs:.0f}°"
                + (" (nejisté)." if uncertain else "."))
        return YokePlacement(center, normal, along, spacing, True, uncertain, "ok", text,
                             tuple(poles), tuple(normals), tuple(placed_shapes))

    def _site(self, center: Point, normal: Point, along: Point, radius: float
              ) -> Point | str | None:
        """Místo pólu: kružnice o poloměru ``radius`` v rovině (směr, normála) se sklápí od
        kolmice (90°) k tečně a dál dolů; první vstup do materiálu = první překážka."""

        def at(angle: float) -> Point:
            c, si = math.cos(angle), math.sin(angle)
            return tuple(center[i] + radius * (along[i] * c + normal[i] * si) for i in range(3))

        def inside(angle: float) -> bool:
            return self.geo.classify(at(angle)) != "outside"

        step = math.radians(SWEEP_DEG)
        a_out = math.pi / 2
        if inside(a_out):
            return "room"
        a_in = a_out - step
        while not inside(a_in):
            a_out, a_in = a_in, a_in - step
            if a_in < -math.pi / 2 - 1e-9:
                return None
        for _ in range(SWEEP_ITER):
            mid = (a_in + a_out) / 2
            if inside(mid):
                a_in = mid
            else:
                a_out = mid
        return at(a_in)


def _cylinder(origin: Point, axis: Point, radius: float, length: float) -> Any:
    from build123d import Plane, Solid

    return Solid.make_cylinder(radius, length, Plane(origin=origin, z_dir=axis))


def _body(a: Point, b: Point, up: Point, size: float, overhang: float) -> Any:
    """Tělo jha: kvádr nad horními konci nohou (průřez ``size``), přesah ``overhang`` na
    obou koncích."""
    from build123d import Box, Location, Plane

    axis = _unit(_sub(b, a)) or _base(up)
    side = _unit(_add(up, axis, -_dot(up, axis))) or _base(axis)
    middle = _add(_add(a, _sub(b, a), 0.5), side, size / 2)
    length = math.sqrt(_dot(_sub(b, a), _sub(b, a))) + 2 * overhang
    return Location(Plane(origin=middle, x_dir=axis, z_dir=side)) * Box(length, size, size)


def _compound(solids: list[Any]) -> Any:
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for solid in solids:
        builder.Add(compound, solid.wrapped)
    return compound


# --- výsledky --------------------------------------------------------------------------------


@dataclass(frozen=True)
class MtSample:
    """Jedno místo povrchu (těžiště trojúhelníku): směry pole, nanesení, prohlídka."""

    point: Point
    normal: Point
    area: float  # mm²
    state: str  # STATES
    field: str  # FIELD (ok / limited / blocked / uncertain)
    apply: str  # pt.GRADES
    inspect: str
    angles: tuple[float, ...]  # platné směry pole v místě [°, 0–180), jisté
    uncertain_angles: tuple[float, ...]  # jen z nejistých poloh
    missing: tuple[tuple[float, float], ...]  # nepokryté orientace vad (od, do) [°]
    directions: tuple[str, ...]  # 8 směrů: "ok" / "uncertain" / druh z FAILURES / "" (nezkoušeno)
    failures: tuple[str, ...]  # 8 směrů: česká věta, proč jho v tom směru nejde ("" = nic)
    reasons: tuple[tuple[str, str], ...]  # (druh z REASONS, česká věta)

    def grade(self, view: str | None) -> str:
        """Stav místa pro přepínač mapy (``VIEWS``)."""
        if view is None:
            return self.state
        if view == "apply":
            return self.apply
        if view == "inspect":
            return self.inspect
        bin_ = int(view[1:])
        state = self.directions[bin_]
        return state if state in ("ok", "uncertain") else "blocked"


@dataclass(frozen=True)
class MtMap:
    """Mapa geometrické proveditelnosti a směrového pokrytí MT (jen pohled, neukládá se)."""

    nodes: list[Point]
    triangles: list[tuple[int, int, int]]
    samples: list[MtSample]
    settings: MtSettings
    step_mm: float
    center_step_mm: float
    faces: int
    centers: int
    placements: int  # zkoušených poloh jha (s dohledáním hranic)
    valid: int  # z toho platných
    material: str  # věta o materiálu
    seconds: float

    @property
    def total_area(self) -> float:
        return sum(s.area for s in self.samples)

    def area(self, state: str, view: str | None = None) -> float:
        return sum(s.area for s in self.samples if s.grade(view) == state)

    def percent(self, state: str, view: str | None = None) -> float:
        total = self.total_area
        return 100 * self.area(state, view) / total if total else 0.0

    def mesh(self, view: str | None = None) -> tuple[list, list, list]:
        """Oddělené uzly každé plošky (barva celého trojúhelníku) pro přepínač ``VIEWS``."""
        colors = {**COLORS, "off": (0.80, 0.80, 0.80)}
        nodes, triangles, out = [], [], []
        for tri, sample in zip(self.triangles, self.samples, strict=True):
            start = len(nodes)
            nodes.extend(self.nodes[i] for i in tri)
            triangles.append((start, start + 1, start + 2))
            out.extend([colors[sample.grade(view)]] * 3)
        return nodes, triangles, out

    def nearest(self, point: Point) -> int | None:
        """Místo nejblíž bodu (klik do mapy)."""
        if not self.samples:
            return None
        return min(range(len(self.samples)),
                   key=lambda i: sum((a - b) ** 2 for a, b in zip(self.samples[i].point, point,
                                                                    strict=True)))

    def describe(self, index: int) -> list[str]:
        """Stav místa, platné směry, nepokryté orientace a důvody česky (klik do mapy)."""
        s = self.samples[index]
        lines = [f"{STATES[s.state]} – pole: {FIELD[s.field]}, nanesení {GRADES[s.apply]}, "
                 f"prohlídka {GRADES[s.inspect]}."]
        if s.angles:
            lines.append("Platné směry pole: " + ", ".join(f"{_n(a)}°" for a in s.angles) + ".")
        if s.missing:
            lines.append("Nepokryté orientace vad: " + _ranges(s.missing) + ".")
        lines += [text for _, text in s.reasons]
        for k in SHOWN:
            if s.failures[k] and s.directions[k] not in ("ok", "uncertain"):
                lines.append(f"Pole {_n(k * DIRECTION_STEP)}°: {s.failures[k]}")
        lines.append("Místo " + "; ".join(_dec(v) for v in s.point) + " mm. " + ANGLE_NOTE)
        return lines

    def reason_areas(self) -> list[tuple[str, float]]:
        areas: dict[str, float] = {}
        for s in self.samples:
            for kind in dict.fromkeys(k for k, _ in s.reasons):
                areas[kind] = areas.get(kind, 0.0) + s.area
        return sorted(areas.items(), key=lambda item: -item[1])

    def failure_areas(self) -> list[tuple[str, float]]:
        """Druhy nevyhovujících přiložení jha podle plochy (mm²) – kde jho v některém z
        ukázaných směrů nejde."""
        areas: dict[str, float] = {}
        for s in self.samples:
            kinds = {s.directions[k] for k in SHOWN} & set(FAILURES)
            for kind in kinds:
                areas[kind] = areas.get(kind, 0.0) + s.area
        return sorted(areas.items(), key=lambda item: -item[1])

    def summary(self) -> list[str]:
        total = self.total_area
        lines = [MT_MAP, MT_DISCLAIMER, PERCENT_NOTE, self.material,
                 f"Plochy: {self.faces}, míst {len(self.samples)}, krok sítě "
                 f"{_n(round(self.step_mm, 2))} mm, celkem {_dec(total)} mm²; středy jha "
                 f"{self.centers} po {_n(round(self.center_step_mm, 2))} mm, poloh jha "
                 f"{self.placements} (platných {self.valid})."]
        for state, label in STATES.items():
            lines.append(f"{label}: {_dec(self.percent(state), 2)} % "
                         f"({_dec(self.area(state))} mm²).")
        lines.append("Směry pole (jho se vejde): " + ", ".join(
            f"{_n(k * DIRECTION_STEP)}° {_dec(self.percent('ok', f'd{k}'), 2)} %"
            for k in SHOWN) + ".")
        for key, label, on in (("apply", "Nanesení", self.settings.apply),
                               ("inspect", "Prohlídka", self.settings.inspect)):
            if on:
                parts = [f"{GRADES[g]} {_dec(self.percent(g, key), 2)} %" for g in GRADES
                         if self.area(g, key) > 0]
                lines.append(f"{label}: {', '.join(parts)}.")
        reasons = self.reason_areas()
        if reasons:
            lines.append("Důvody: " + "; ".join(
                f"{REASONS[kind]} {_dec(100 * area / total)} %" for kind, area in reasons[:6])
                + ".")
        failures = self.failure_areas()
        if failures:
            lines.append("Kde se jho nevejde (aspoň v jednom ukázaném směru): " + "; ".join(
                f"{FAILURES[kind]} {_dec(100 * area / total)} %"
                for kind, area in failures[:5]) + ".")
        lines += [*self.settings.lines(), FIELD_NOTE, ANGLE_NOTE]
        if self.settings.inspect:
            lines.append(LIGHT_NOTE)
        lines.append(f"Výpočet {_dec(self.seconds)} s; algoritmus {ALGORITHM}.")
        return lines

    def assumptions(self) -> dict[str, Any]:
        return {"algorithm": ALGORITHM, "directions": DIRECTIONS, "shoe_mm": SHOE_MM,
                "refine_mm": REFINE_MM, "step_mm": self.step_mm,
                "center_step_mm": self.center_step_mm, **self.settings.to_dict()}

    def write_csv(self, path: str | Path) -> Path:
        path = Path(path)

        def cz(value: float | None) -> str:
            return "" if value is None else f"{value:.6f}".replace(".", ",")

        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            for text in (MT_MAP, MT_DISCLAIMER, PERCENT_NOTE, self.material,
                         *self.settings.lines(), FIELD_NOTE, ANGLE_NOTE,
                         *((LIGHT_NOTE,) if self.settings.inspect else ()),
                         json.dumps(self.assumptions(), ensure_ascii=False, sort_keys=True)):
                writer.writerow([text])
            writer.writerow(["x [mm]", "y [mm]", "z [mm]", "obsah [mm²]", "nx", "ny", "nz",
                             "stav", "směry pole", "platné směry [°]",
                             "nepokryté orientace vad [°]", "nanesení", "prohlídka", "důvody"])
            for s in self.samples:
                writer.writerow([*(cz(v) for v in s.point), cz(s.area),
                                 *(cz(v) for v in s.normal), STATES[s.state], FIELD[s.field],
                                 " ".join(_n(a) for a in s.angles), _ranges(s.missing),
                                 GRADES[s.apply], GRADES[s.inspect],
                                 " | ".join(text for _, text in s.reasons)])
        return path


def _ranges(missing: Iterable[tuple[float, float]]) -> str:
    return ", ".join(f"{_n(lo)}° až {_n(hi)}°" for lo, hi in missing)


# --- výpočet ---------------------------------------------------------------------------------


def study_faces(geo: PartGeometry, record: dict[str, Any]) -> list[Any]:
    """Plochy MT studie (odkazy významem); jiná metoda nebo cílový objem = česká chyba."""
    if record.get("method") != "MT":
        raise MtError("Mapa MT jde spočítat jen pro MT (magnetickou práškovou) studii.")
    target = record.get("target") or {}
    if target.get("kind", "faces") != "faces":
        raise MtError("MT posuzuje povrch – vyber plochy (cílový objem ani svar MT nepočítá).")
    faces, problems = geo.faces_of(target)
    if problems:
        raise MtError(" ".join(problems))
    if not faces:
        raise MtError("MT studie nemá plochy – vyber plochy povrchu, který se má kontrolovat.")
    return faces


def _surface(part: Any, faces: list[Any], settings: MtSettings) -> _Surface:
    if not faces:
        raise MtError("MT studie nemá plochy – vyber plochy povrchu, který se má kontrolovat.")
    area = sum(face.area for face in faces)
    step = settings.step_mm or max(MIN_STEP, round(math.sqrt(
        area / (TARGET_SAMPLES * _AREA_PER_STEP2)), 1))
    try:
        surface = _Surface(part, step, faces)
        for _ in range(3 if settings.step_mm is None else 0):
            count = len(surface.centers)
            if count <= 1.3 * TARGET_SAMPLES:
                break
            step = round(step * math.sqrt(count / TARGET_SAMPLES) + 0.05, 1)
            surface = _Surface(part, step, faces)
    except MapError as exc:
        raise MtError(str(exc)) from None
    if len(surface.centers) > MAX_SAMPLES:
        raise MtError(f"Mapa MT by měla {len(surface.centers)} míst (nejvýš {MAX_SAMPLES}) – "
                      f"zvol větší krok sítě (teď {_n(round(step, 2))} mm).")
    return surface


@dataclass
class _Grid:
    """Mřížka středů jha na jedné ploše dílu (uzly v parametrech u, v)."""

    face: Any
    adaptor: Any
    u: tuple[float, float]
    v: tuple[float, float]
    counts: tuple[int, int]
    nodes: dict[tuple[int, int], int]  # (i, j) → index středu


@dataclass(frozen=True)
class _Center:
    point: Point
    normal: Point
    uv: tuple[float, float]
    grid: int


def _face_points(face: Any, step: float) -> tuple[Any, tuple, tuple, tuple, list]:
    """Uzly mřížky v parametrech plochy (body mimo ořezanou plochu vynechá)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON

    adaptor = BRepAdaptor_Surface(face.wrapped)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face.wrapped)

    def intervals(axis: int) -> int:
        lengths = []
        for cross in range(5):
            fixed = v0 + (v1 - v0) * cross / 4 if axis == 0 else u0 + (u1 - u0) * cross / 4
            low, high = (u0, u1) if axis == 0 else (v0, v1)
            pts = [adaptor.Value(low + (high - low) * i / 32, fixed) if axis == 0
                   else adaptor.Value(fixed, low + (high - low) * i / 32) for i in range(33)]
            lengths.append(sum(a.Distance(b) for a, b in zip(pts, pts[1:], strict=False)))
        return max(1, math.ceil(max(lengths) / step))

    nu, nv = intervals(0), intervals(1)
    if (nu + 1) * (nv + 1) > 50 * MAX_CENTERS:
        raise MtError("Mřížka středů jha by byla příliš hustá – zvětši krok středů.")
    classifier = BRepClass_FaceClassifier()
    out = []
    for i in range(nu + 1):
        for j in range(nv + 1):
            uv = (u0 + (u1 - u0) * i / nu, v0 + (v1 - v0) * j / nv)
            p = adaptor.Value(*uv)
            classifier.Perform(face.wrapped, p, 1e-7)
            if classifier.State() in (TopAbs_IN, TopAbs_ON):
                out.append(((i, j), uv, (p.X(), p.Y(), p.Z())))
    return adaptor, (u0, u1), (v0, v1), (nu, nv), out


class _Field:
    """Směrové pokrytí: polohy jha ze středů mřížky, jejich účinné oblasti a směry pole."""

    def __init__(self, geo: PartGeometry, settings: MtSettings, points: list[Point],
                 normals: list[Point]) -> None:
        import numpy as np

        self.np = np
        self.geo = geo
        self.settings = settings
        self.yoker = Yoker(geo, settings)
        self.P = np.asarray(points, dtype=float).reshape(-1, 3)
        self.N = np.asarray(normals, dtype=float).reshape(-1, 3)
        bases = [_base(tuple(n)) for n in self.N]
        self.B = np.asarray(bases, dtype=float).reshape(-1, 3)
        self.S = np.cross(self.N, self.B) if len(self.N) else self.B
        count = len(self.P)
        self.certain: list[set[float]] = [set() for _ in range(count)]
        self.loose: list[set[float]] = [set() for _ in range(count)]
        self.unclear = [False] * count
        self.fails: list[list[dict[str, list]]] = [[{} for _ in range(DIRECTIONS)]
                                                   for _ in range(count)]
        self.tried = [[False] * DIRECTIONS for _ in range(count)]
        self.covered = np.zeros((count, DIRECTIONS), dtype=bool)  # jistě pokryto v tom směru
        self.sight: dict[tuple[int, int], bool] = {}
        self.grids: list[_Grid] = []
        self.centers: list[_Center] = []
        self.placements = 0
        self.valid = 0

    # --- středy ------------------------------------------------------------------------------

    def build_centers(self, step: float) -> None:
        np = self.np
        s = self.settings
        reach = s.spacing_mm / 4 + s.pole_mm / 2
        if not len(self.P):
            return
        low, high = self.P.min(axis=0) - reach, self.P.max(axis=0) + reach
        self.grids, self.centers = [], []
        for face in self.geo.part.faces():
            box = face.bounding_box()
            if (np.any(np.array([box.max.X, box.max.Y, box.max.Z]) < low)
                    or np.any(np.array([box.min.X, box.min.Y, box.min.Z]) > high)):
                continue
            adaptor, u, v, counts, nodes = _face_points(face, step)
            if not nodes:
                continue
            pts = np.asarray([p for _, _, p in nodes], dtype=float)
            near = np.zeros(len(pts), dtype=bool)
            reached: list[list[int]] = [[] for _ in range(len(pts))]
            for start in range(0, len(self.P), 2000):
                chunk = self.P[start:start + 2000]
                d2 = ((pts[:, None, :] - chunk[None, :, :]) ** 2).sum(axis=2)
                hits = d2 <= reach * reach
                near |= hits.any(axis=1)
                for row in np.nonzero(hits.any(axis=1))[0]:
                    reached[row].extend(int(c) + start for c in np.nonzero(hits[row])[0])
            grid = _Grid(face, adaptor, u, v, counts, {})
            index = len(self.grids)
            for row, (keep, (ij, uv, point)) in enumerate(zip(near, nodes, strict=True)):
                if not keep:
                    continue
                try:
                    surface = self.geo.surface_at(point, face)
                except GeometryError:
                    continue
                facing = self.N[reached[row]] @ np.asarray(surface.normal)
                if not (facing >= FACING - 1e-9).any():
                    continue  # plocha odvrácená od míst v dosahu (spodek, bok desky) nic nepokryje
                grid.nodes[ij] = len(self.centers)
                self.centers.append(_Center(surface.point, surface.normal, uv, index))
                if len(self.centers) > MAX_CENTERS:
                    raise MtError(f"Středů jha by bylo přes {MAX_CENTERS} – zvětši krok "
                                  f"středů (teď {_n(round(step, 2))} mm).")
            self.grids.append(grid)

    # --- polohy ------------------------------------------------------------------------------

    def run(self, directions: Iterable[int], progress: Callable[[int], None] | None = None
            ) -> None:
        directions = tuple(directions)
        results: dict[tuple[int, int], bool] = {}
        with reuse_placements(self.geo):
            for index, center in enumerate(self.centers):
                for k in directions:
                    placed = self.yoker.best(center.point, center.normal,
                                             direction(center.normal, k * DIRECTION_STEP))
                    results[(index, k)] = placed.ok and not placed.uncertain
                    self.apply(placed, index)
                if progress is not None:
                    progress(len(directions))
            pairs = self._boundaries(results, directions)
            for grid, (ij_ok, ij_bad), k in pairs:
                if not self._gain(self.centers[grid.nodes[ij_bad]], k):
                    continue
                edge = self._refine(grid, self.centers[grid.nodes[ij_ok]].uv,
                                    self.centers[grid.nodes[ij_bad]].uv, k)
                if edge is not None:
                    self._corners(grid, edge, ij_ok, ij_bad, k)
            if progress is not None and pairs:
                progress(0)

    def _boundaries(self, results: dict, directions: tuple[int, ...]) -> list:
        out = []
        for grid in self.grids:
            for (i, j), index in grid.nodes.items():
                for other in ((i + 1, j), (i, j + 1)):
                    neighbour = grid.nodes.get(other)
                    if neighbour is None:
                        continue
                    for k in directions:
                        a, b = results.get((index, k)), results.get((neighbour, k))
                        if a is None or b is None or a == b:
                            continue
                        out.append((grid, ((i, j), other) if a else (other, (i, j)), k))
        return out

    def _gain(self, center: _Center, k: int) -> bool:
        """Má smysl dohledat hranici? Jen když by jho u neplatného uzlu zasáhlo místo, které
        v tom směru ještě není jistě pokryté (jinak by dohledání nic nezměnilo)."""
        np = self.np
        if not len(self.P):
            return False
        s = self.settings
        n = np.asarray(center.normal)
        t = np.asarray(direction(center.normal, k * DIRECTION_STEP))
        d = self.P - np.asarray(center.point)
        half_u = (s.spacing_mm - 2 * s.pole_zone_mm) / 2
        mask = ((np.abs(d @ t) <= half_u + REFINE_MM) & (np.abs(d @ np.cross(n, t))
                                                        <= s.spacing_mm / 4 + REFINE_MM)
                & (np.abs(d @ n) <= s.spacing_mm / 4 + 1e-9) & (self.N @ n >= FACING - 1e-9))
        return bool((mask & ~self.covered[:, k]).any())

    def _refine(self, grid: _Grid, uv_lo: tuple[float, float], uv_hi: tuple[float, float],
                k: int) -> tuple[float, float] | None:
        """Půlení mezi platnou a neplatnou polohou středu (v parametrech plochy) do
        ``REFINE_MM``; vrátí poslední platný bod, když se hranice posunula."""
        lo, hi = self._point(grid, uv_lo), self._point(grid, uv_hi)
        if lo is None or hi is None:
            return None
        span = math.dist(lo.point, hi.point)
        steps = max(1, math.ceil(math.log2(max(span, REFINE_MM) / REFINE_MM)))
        found = None
        for _ in range(steps):
            uv = ((uv_lo[0] + uv_hi[0]) / 2, (uv_lo[1] + uv_hi[1]) / 2)
            if self._try(grid, uv, k):
                uv_lo = found = uv
            else:
                uv_hi = uv
        return found

    def _corners(self, grid: _Grid, edge: tuple[float, float], ij_ok: tuple[int, int],
                 ij_bad: tuple[int, int], k: int) -> None:
        """Roh oblasti platných středů: z dohledaného bodu hranice se zkusí i kolmý směr
        (jinak by mřížka rohy oblasti, např. u šikmého jha, uřízla)."""
        along_u = ij_ok[1] == ij_bad[1]
        du = (grid.u[1] - grid.u[0]) / grid.counts[0]
        dv = (grid.v[1] - grid.v[0]) / grid.counts[1]
        for sign in (1.0, -1.0):
            other = ((edge[0], edge[1] + sign * dv) if along_u
                     else (edge[0] + sign * du, edge[1]))
            if not (grid.u[0] - 1e-12 <= other[0] <= grid.u[1] + 1e-12
                    and grid.v[0] - 1e-12 <= other[1] <= grid.v[1] + 1e-12):
                continue
            point = self._point(grid, other)
            if point is None or not self._gain(point, k) or self._try(grid, other, k):
                continue
            self._refine(grid, edge, other, k)

    def _point(self, grid: _Grid, uv: tuple[float, float]) -> _Center | None:
        p = grid.adaptor.Value(*uv)
        try:
            surface = self.geo.surface_at((p.X(), p.Y(), p.Z()), grid.face)
        except GeometryError:
            return None
        if surface.distance > 1e-3:
            return None  # mimo ořezanou plochu
        return _Center(surface.point, surface.normal, uv, -1)

    def _try(self, grid: _Grid, uv: tuple[float, float], k: int) -> bool:
        center = self._point(grid, uv)
        if center is None:
            return False
        placed = self.yoker.best(center.point, center.normal,
                                 direction(center.normal, k * DIRECTION_STEP))
        self.apply(placed, None)
        return placed.ok and not placed.uncertain

    # --- účinná oblast -----------------------------------------------------------------------

    def apply(self, placed: YokePlacement, center_index: int | None) -> None:
        """Místa v účinné oblasti dostanou směr pole (platné jho), nebo důvod (neplatné)."""
        np = self.np
        s = self.settings
        self.placements += 1
        if not len(self.P):
            return
        c = np.asarray(placed.center)
        n = np.asarray(placed.normal)
        t = np.asarray(placed.direction)
        b = np.cross(n, t)
        d = self.P - c
        u, v, w = d @ t, d @ b, d @ n
        half_u, half_v, depth = placed.zone(s)
        mask = ((np.abs(u) <= half_u + 1e-9) & (np.abs(v) <= half_v + 1e-9)
                & (np.abs(w) <= depth + 1e-9) & (self.N @ n >= FACING - 1e-9)
                & (np.abs(w) <= np.maximum(SIGHT_MM, np.hypot(u, v)) + 1e-9))
        index = np.nonzero(mask)[0]
        if not len(index):
            return
        f = t[None, :] - (self.N[index] @ t)[:, None] * self.N[index]
        length = np.linalg.norm(f, axis=1)
        angles = np.degrees(np.arctan2((f * self.S[index]).sum(axis=1),
                                       (f * self.B[index]).sum(axis=1))) % 180.0
        if placed.ok:
            self.valid += 1
        for i, wi, li, angle in zip(index, w[index], length, angles, strict=True):
            i = int(i)
            if abs(wi) > SIGHT_MM and not self._seen(placed, center_index, i):
                continue
            if li < UNCLEAR:
                if placed.ok:
                    self.unclear[i] = True
                continue
            bin_ = int(round(angle / DIRECTION_STEP)) % DIRECTIONS
            self.tried[i][bin_] = True
            if placed.ok:
                key = round(2 * angle) / 2 % 180.0
                (self.loose if placed.uncertain else self.certain)[i].add(key)
                if not placed.uncertain:
                    self.covered[i, bin_] = True
            else:
                entry = self.fails[i][bin_].setdefault(placed.kind, [0, placed.text])
                entry[0] += 1

    def _seen(self, placed: YokePlacement, center_index: int | None, i: int) -> bool:
        """Místo mimo rovinu středu: je ze středu vidět (spojnice nad povrchem bez dílu)?"""
        key = (center_index, i) if center_index is not None else None
        if key is not None and key in self.sight:
            return self.sight[key]
        lift = self.settings.step_over_mm
        a = _add(placed.center, placed.normal, lift)
        b = _add(tuple(self.P[i]), tuple(self.N[i]), lift)
        gap = _sub(b, a)
        length = math.sqrt(_dot(gap, gap))
        seen = length < 1e-9 or not self.geo.cast(a, _unit(gap), length).hits
        if key is not None:
            self.sight[key] = seen
        return seen

    # --- výsledek místa ----------------------------------------------------------------------

    def field_of(self, i: int) -> tuple[str, tuple, tuple, tuple, tuple, tuple, list]:
        """(stav pole, jisté směry, nejisté směry, nepokryté orientace, 8 stavů směrů,
        8 důvodů, důvody místa)."""
        detect = self.settings.detect_deg
        certain = tuple(sorted(self.certain[i]))
        loose = tuple(sorted(self.loose[i] - self.certain[i]))
        missing = _missing(certain, detect)
        full_all = not _missing(certain + loose, detect)
        reasons: list[tuple[str, str]] = []
        if certain and not missing:
            state = "ok"
        elif certain and not full_all:
            state = "limited"
            reasons.append(("field_limited", f"Jen část orientací vad – nepokryté vady ve směru "
                                             f"{_ranges(missing)} (chybí pole napříč k nim)."))
        elif certain or loose:
            state = "uncertain"
            reasons.append(("uncertain", "Rozhodující přiložení jha je nejisté (pól přes hranu, "
                                         "tečně nebo nespočítaný průnik)."))
        elif self.unclear[i]:
            state = "uncertain"
            reasons.append(("unclear", "Směr pole v místě je nejasný – spojnice pólů míří skoro "
                                       "kolmo do plochy."))
        else:
            state = "blocked"
            reasons.append(("field_blocked", "Jho se nevejde v žádném směru tak, aby místo "
                                             "zasáhla účinná oblast mezi póly."))
        states, texts = [], []
        for k in range(DIRECTIONS):
            centre = k * DIRECTION_STEP
            if any(_axial(a, centre) <= DIRECTION_STEP / 2 + 1e-9 for a in certain):
                states.append("ok")
                texts.append("")
            elif any(_axial(a, centre) <= DIRECTION_STEP / 2 + 1e-9 for a in loose):
                states.append("uncertain")
                texts.append("")
            elif self.fails[i][k]:
                kind, (_, text) = max(self.fails[i][k].items(), key=lambda item: item[1][0])
                states.append(kind)
                texts.append(text)
            else:
                states.append("" if not self.tried[i][k] else "blocked")
                texts.append("Účinná oblast žádného jha v tomto směru místo nezasáhne.")
        return state, certain, loose, missing, tuple(states), tuple(texts), reasons


def _missing(angles: tuple[float, ...], detect: float) -> tuple[tuple[float, float], ...]:
    """Orientace vad (osové, 0–180°), které žádný směr pole nepokryje: vada se počítá, když je
    k poli skloněná aspoň o ``detect``°. Úseky (od, do) s přesnými hranicemi φ ± ``detect``;
    úsek přes 0° má začátek záporný (např. −7,5° až 7,5°)."""
    if not angles:
        return ((0.0, 180.0),)
    count = int(round(180.0 / ORIENT_STEP))
    bad = [all(_axial(k * ORIENT_STEP, a) < detect - 1e-9 for a in angles) for k in range(count)]
    if not any(bad):
        return ()
    marks = sorted({(a + sign * detect) % 180.0 for a in angles for sign in (1.0, -1.0)})

    def snap(value: float, side: int) -> float:
        """Hranice úseku: značka φ ± detect nejvýš o krok vně krajního nepokrytého vzorku."""
        found = None
        for mark in marks:
            for cand in (mark - 180.0, mark, mark + 180.0):
                low, high = ((value - ORIENT_STEP, value) if side < 0
                             else (value, value + ORIENT_STEP))
                if low - 1e-9 <= cand <= high + 1e-9 and (
                        found is None or (cand > found if side < 0 else cand < found)):
                    found = cand
        return value if found is None else found

    first = bad.index(False)
    runs, start = [], None
    for j in range(1, count + 1):
        k = first + j
        if bad[k % count] and start is None:
            start = k
        elif not bad[k % count] and start is not None:
            runs.append((start, k - 1))
            start = None
    out = []
    for lo_k, hi_k in runs:
        lo, hi = snap(lo_k * ORIENT_STEP, -1), snap(hi_k * ORIENT_STEP, 1)
        while lo >= 180.0 - 1e-9:
            lo, hi = lo - 180.0, hi - 180.0
        if hi > 180.0 + 1e-9:
            lo, hi = lo - 180.0, hi - 180.0
        out.append((round(lo, 2), round(hi, 2)))
    return tuple(sorted(out))


def auto_center_step(field_: _Field) -> float:
    """Krok středů pro zhruba ``TARGET_CENTERS`` středů (asi 1500 poloh jha); středy
    zůstanou postavené pro vrácený krok."""
    step = 10.0
    for _ in range(3):
        field_.build_centers(step)
        count = len(field_.centers)
        if 0.5 * TARGET_CENTERS <= count <= 1.3 * TARGET_CENTERS:
            return step
        new = round(step * math.sqrt(max(count, 1) / TARGET_CENTERS) * 2) / 2
        new = min(200.0, max(MIN_CENTER_STEP, new))
        if new == step:
            return step
        step = new
    field_.build_centers(step)
    return step


def _prepare(part: Any, faces: list[Any], settings: MtSettings, material: str | None,
             points: list[Point] | None = None, normals: list[Point] | None = None,
             center_step: float | None = None) -> tuple[PartGeometry, Any, _Field, float, str]:
    status, text = material_status(material, settings.ferromagnetic)
    if status in ("no", "confirm"):
        raise MtError(text)
    try:
        geo = PartGeometry(part)
    except GeometryError as exc:
        raise MtError(str(exc)) from None
    surface = None
    if points is None:
        surface = _surface(part, faces, settings)
        points, normals = surface.centers, surface.normals
    field_ = _Field(geo, settings, points, normals)
    if settings.center_step_mm or center_step:
        step = settings.center_step_mm or center_step
        field_.build_centers(step)
    else:
        step = auto_center_step(field_)
    return geo, surface, field_, step, text


def estimate(part: Any, faces: list[Any], settings: MtSettings | None = None,
             material: str | None = None) -> tuple[int, float, int, float, float]:
    """Odhad před spuštěním: (místa, krok sítě, středy jha, krok středů, doba v s)."""
    settings = settings or MtSettings()
    _, surface, field_, step, _ = _prepare(part, faces, settings, material)
    samples = len(surface.centers)
    access = SECONDS_PER_SAMPLE * samples if settings.apply or settings.inspect else 0.0
    seconds = len(field_.centers) * DIRECTIONS * SECONDS_PER_PLACEMENT * 1.3 + access
    return samples, surface.step, len(field_.centers), step, seconds


def compute(part: Any, faces: list[Any], settings: MtSettings | None = None,
            material: str | None = None, progress: Callable[[int, int], None] | None = None,
            directions: Iterable[int] = range(DIRECTIONS)) -> MtMap:
    """Mapa MT pro plochy ``faces`` dílu ``part``; ``progress(hotovo, celkem)`` průběžně.
    ``directions`` (indexy směrů po 22,5°) zúží výpočet – jen pro testy."""
    settings = settings or MtSettings()
    started = time.monotonic()
    geo, surface, field_, step, text = _prepare(part, faces, settings, material)
    directions = tuple(directions)
    samples = _evaluate(geo, settings, field_, surface.centers, surface.normals, surface.areas,
                        directions, progress)
    return MtMap(surface.nodes, surface.triangles, samples, settings, surface.step, step,
                 len(faces), len(field_.centers), field_.placements, field_.valid, text,
                 time.monotonic() - started)


def check_points(part: Any, points: list[Point], normals: list[Point],
                 settings: MtSettings | None = None, material: str | None = "ocel",
                 directions: Iterable[int] = range(DIRECTIONS)) -> list[MtSample]:
    """Směrové pokrytí, nanesení a prohlídka v zadaných bodech (testy, hranice); středy jha
    se hledají jen v dosahu těchto bodů."""
    settings = settings or MtSettings()
    geo, _, field_, _, _ = _prepare(part, [], settings, material, list(points), list(normals),
                                    center_step=10.0)
    return _evaluate(geo, settings, field_, list(points), list(normals),
                     [0.0] * len(points), tuple(directions), None)


def _evaluate(geo: PartGeometry, settings: MtSettings, field_: _Field, points: list[Point],
              normals: list[Point], areas: list[float], directions: tuple[int, ...],
              progress: Callable[[int, int], None] | None) -> list[MtSample]:
    access_on = settings.apply or settings.inspect
    total = len(field_.centers) * len(directions) + (len(points) if access_on else 0)
    done, reported = 0, -1
    every = max(1, total // 200)

    def tick(count: int) -> None:
        nonlocal done, reported
        done = min(total, done + count)
        if progress is not None and (done - reported >= every or done == total):
            reported = done
            progress(done, total)

    field_.run(directions, tick)
    sampler = Sampler(geo, settings.pt_settings()) if access_on else None
    out = []
    for i, (point, normal, area) in enumerate(zip(points, normals, areas, strict=True)):
        state_field, certain, loose, missing, states, texts, reasons = field_.field_of(i)
        apply, inspect = "off", "off"
        if sampler is not None:
            access = sampler.access(point, normal)
            if settings.apply:
                apply = access.spray
                reasons += [("apply_" + kind.split("_", 1)[1], text.replace("Nástřik", "Nanesení"))
                            for kind, text in access.reasons if kind.startswith("spray_")]
            if settings.inspect:
                inspect = access.view
                reasons += [("inspect_" + kind.split("_", 1)[1], text)
                            for kind, text in access.reasons if kind.startswith("view_")]
            if "uncertain" in (apply, inspect):
                reasons.append(("uncertain", "Rozhodující paprsek nanesení nebo prohlídky je "
                                             "nejistý – prochází hranou nebo se plochy jen "
                                             "dotýká."))
            tick(1)
        grades = [state_field, *(g for g in (apply, inspect) if g != "off")]
        if "blocked" in grades:
            state = "blocked"
        elif "limited" in grades:
            state = "limited"
        elif "uncertain" in grades:
            state = "uncertain"
        else:
            state = "ok"
        out.append(MtSample(tuple(point), tuple(normal), area, state, state_field, apply,
                            inspect, certain, loose, missing, states, texts,
                            tuple(dict.fromkeys(reasons))))
    return out


def place_yoke(part: Any, point: Point, normal: Point, angle: float,
               settings: MtSettings | None = None, shapes: bool = True) -> YokePlacement:
    """Přiložení jha do bodu pod úhlem ``angle`` [°] (Přiložit jho sem, Ukázat jho)."""
    settings = settings or MtSettings()
    yoker = Yoker(PartGeometry(part), settings)
    return yoker.best(point, normal, direction(_unit(normal), angle), shapes)


def self_check(folder: Any) -> tuple[bool, str]:
    """Rychlá kontrola MT (self-test aplikace, i ve Windows): na desce 200 × 100 se jho
    vejde podél X (rozteč 100), podél Y jen s roztečí 75; do kapsy se nevejde."""
    from skodacad.document import Document
    from skodacad.rebuild import rebuild

    deska = rebuild(Document.load(Path(folder) / "deska.json")).part
    yoker = Yoker(PartGeometry(deska), MtSettings())
    along = yoker.best((0.0, 0.0, 20.0), (0, 0, 1), (1.0, 0.0, 0.0))
    across = yoker.best((0.0, 0.0, 20.0), (0, 0, 1), (0.0, 1.0, 0.0))
    kapsa = rebuild(Document.load(Path(folder) / "kapsa.json")).part
    pocket = Yoker(PartGeometry(kapsa), MtSettings()).best((0.0, 0.0, 15.0), (0, 0, 1),
                                                           (1.0, 0.0, 0.0))
    got = [(along.ok, along.spacing), (across.ok, across.spacing), pocket.ok]
    if got == [(True, 100.0), (True, 75.0), False]:
        return True, "MT jho: OK (deska – podél X rozteč 100, podél Y 75; kapsa – nevejde se)"
    return False, f"MT jho: {got} (čekáno podél X 100, podél Y 75, kapsa nevejde)"
