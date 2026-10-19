"""RT – geometrie projekce a expozice (etapa 13).

Závazné vymezení je v ``docs/ndt/24-vymezeni-rt.md``: jen geometrie projekce – kam lze umístit
zjednodušený model zdroje a detektoru, kudy vedou přímé paprsky z ohniska dílem a jakou
tloušťku prozařují, kam se oblast promítne na detektor, geometrické zvětšení a neostrost
a geometrická pravidla ISO 17636-1 (poměr tloušťky, nejmenší vzdálenost zdroje). Žádná dávka
ani radiační ochrana, expozice, kvalita obrazu, citlivost ani detekovatelnost vad. Návrh,
výchozí hodnoty a ručně spočítané výsledky jsou v ``docs/ndt/23-navrh-etapa-13.md``.

Projekce = bodový zdroj (ohnisko) a plochý detektor. Pro každé místo oblasti se vede paprsek
z ohniska přes místo na rovinu detektoru. Prozařovaná tloušťka sčítá **všechny** úseky
v materiálu (jádro etapy 02 – úsek podél povrchu nebo přes hranu se započte, paprsek se ale
označí jako nejistý; bez toho by paprsek otřený o stěnu otvoru „prošel vzduchem“). O kolizi
zdroje a detektoru rozhoduje přesný průnik s tělesem OCCT. Nejisté se nikdy nepočítá jako
promítnuté. Výpočet je pevný (síť, mřížka), žádná náhoda.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

from skodacad.ndt import RT_DISCLAIMER, RT_MAP
from skodacad.ndt.geometry import OVERLAP_TOL, GeometryError, PartGeometry, Point, overlap
from skodacad.ndt.mt import _add, _base, _cross, _dot, _sub, _unit
from skodacad.ndt.pt import COLORS
from skodacad.thickness_map import MapError, _Surface

ALGORITHM = "ndt-rt-projekce 1"
CLASS_FACTOR = {"A": 7.5, "B": 15.0}  # f/d ≥ k · b^(2/3) (ISO 17636-1, ISO 5579; vzorec pro film)
RATIO_LIMIT = {"A": 1.2, "B": 1.1}  # prozařovaná tloušťka okraj / střed svazku (ISO 17636-1)
THIN_FACTOR = 1.2  # b < 1,2 · t → do vzorce f_min se dosadí t (ISO 5579)
REFERENCE_SHARE = 0.8  # střední paprsek tenčí než 0,8 × medián oblasti = nemíří do materiálu
CROSSING_GAP_MM = 0.5  # jiný průchod oblastí = dál než tolik od místa (překryv obrazů)
PUSH_MAX_MM = 50.0  # detektor na ploše se při nárazu odsune nejvýš o tolik
PUSH_TOL_MM = 0.01  # přesnost odsunutí detektoru
FACING_DETECTOR = 0.1  # plocha výstupu svírá se středním paprskem aspoň asi 6°
TARGET_SAMPLES = 1000  # automatický krok sítě míst (plochy)
MAX_SAMPLES = 20_000
MAX_PROJECTIONS = 20
MAX_IMAGE_CELLS = 60_000
MIN_STEP = 0.5  # mm
_AREA_PER_STEP2 = 0.2  # síť mapy tloušťky: trojúhelník ≈ 0,2 · krok²
SECONDS_PER_RAY = 0.0004  # odhad (změřeno 19. 10. 2026 v cloudu: 0,24 ms na paprsek)
SECONDS_PER_PROJECTION = 0.3  # přiložení detektoru a kolize
SECONDS_PER_CELL = 0.011  # ořez buňky objemu 07B (V svar po 2,5 mm: 1 920 buněk asi 20 s)

STATES = {"ok": "Promítne se – geometrická pravidla platí",
          "limited": "Promítne se jen omezeně",
          "blocked": "Nepromítne se", "uncertain": "Nelze spolehlivě vyhodnotit"}
SHORT = {"ok": "promítne se", "limited": "omezeně", "blocked": "nepromítne se",
         "uncertain": "nejisté"}
ORDER = ("ok", "limited", "uncertain", "blocked")  # sjednocení projekcí: lepší stav vyhrává
REASONS = {  # druh důvodu místa → popis v souhrnu
    "setup": "projekce nejde (zdroj nebo detektor)",
    "beam": "mimo svazek", "detector": "mimo detektor", "behind": "místo za detektorem",
    "ratio": "poměr tloušťky nad mezí", "distance": "zdroj blíž než nejmenší vzdálenost",
    "overlap": "obraz se překrývá s jinou částí oblasti",
    "uncertain": "nejistý paprsek (přes hranu nebo tečně)",
    "reference": "poměr tloušťky nelze určit", "point": "vnitřní bod objemu nenalezen",
}
SETUP_FAILURES = {
    "source_inside": "zdroj je v materiálu",
    "housing": "tělo zdroje naráží do dílu",
    "no_exit": "střední paprsek dílem neprochází",
    "exit_face": "plocha výstupu je skoro rovnoběžná se svazkem",
    "detector": "detektor naráží do dílu",
}
CHOSEN = "zvoleno pro výpočet, ne z normy"
RATIO_SOURCE = "ISO 17636-1 (z veřejných výňatků, plný text neověřen)"
FMIN_SOURCE = "ISO 17636-1 a ISO 5579, vzorec pro film (z veřejných výňatků, plný text neověřen)"
FILM_SOURCE = "běžný formát filmu 10 × 24 cm"
PERCENT_NOTE = ("Procento vyjadřuje jen geometrický podíl plochy nebo objemu, nikoli "
                "pravděpodobnost nalezení vady.")
PENETRATION_NOTE = ("Zda zdroj danou tloušťku prozáří (energie, expozice), program nepočítá; "
                    "radiační ochranu také ne.")
DIGITAL_NOTE = ("Nejmenší vzdálenost zdroje se počítá vzorcem pro film (ISO 17636-1); pro "
                "digitální detektory má ISO 17636-2 upravený vzorec s vlastní neostrostí "
                "detektoru – ten se nepočítá.")
ANGLE_NOTE = ("Sklon a natočení: 0° = průmět osy +X do plochy (u plochy kolmé na X osa +Y), "
              "kladně proti směru hodin při pohledu zvenku (jako úhel sondy UT).")
REFERENCE_HINT = ("střední paprsek nemíří do plného materiálu – zamiř ho do oblasti nebo zadej "
                  "u projekce jmenovitou tloušťku")


class RtError(ValueError):
    """Projekce RT nejde spočítat nebo má chybné nastavení (zpráva je česky)."""


def _n(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _dec(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _point_text(point: Point) -> str:
    return "(" + "; ".join(_dec(v) for v in point) + ")"


def _rotate(v: Point, axis: Point, angle_deg: float) -> Point:
    """Otočení vektoru kolem jednotkové osy (kladně proti směru hodin při pohledu proti ose)."""
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    k = _cross(axis, v)
    d = _dot(axis, v) * (1 - c)
    return (v[0] * c + k[0] * s + axis[0] * d, v[1] * c + k[1] * s + axis[1] * d,
            v[2] * c + k[2] * s + axis[2] * d)


def tilted(normal: Point, tilt_deg: float, turn_deg: float) -> Point:
    """Směr ke zdroji: normála plochy sklopená o ``tilt_deg`` ve směru ``turn_deg`` (0° =
    průmět osy +X do plochy) – stejné úhly jako sonda UT."""
    n = _unit(normal)
    if n is None:
        raise RtError("Normála plochy je nulová.")
    toward = _rotate(_base(n), n, turn_deg)
    a = math.radians(tilt_deg)
    return _unit(_add(_add((0.0, 0.0, 0.0), n, math.cos(a)), toward, math.sin(a))) or n


def angles_of(normal: Point, direction: Point) -> tuple[float, float]:
    """Opak ``tilted``: (sklon od normály, natočení) směru ke zdroji vůči ploše [°]."""
    n, d = _unit(normal), _unit(direction)
    if n is None or d is None:
        return 0.0, 0.0
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, _dot(n, d)))))
    side = _add(d, n, -_dot(d, n))
    if math.sqrt(_dot(side, side)) < 1e-9:
        return tilt, 0.0
    base = _base(n)
    turn = math.degrees(math.atan2(_dot(side, _cross(n, base)), _dot(side, base))) % 360.0
    return tilt, turn


def along_angle(normal: Point, along: Point) -> float:
    """Natočení delší strany detektoru [°, 0–180), aby ležela podél ``along`` (osa svaru)."""
    return round(angles_of(normal, along)[1] % 180.0, 6) % 180.0 + 0.0


# --- nastavení -------------------------------------------------------------------------------

_LIMITS = {  # klíč: (český popis, nejméně, nejvýš)
    "focal_mm": ("Rozměr ohniska [mm]", 0.0, 50.0),
    "cone_deg": ("Kužel svazku [°]", 1.0, 360.0),
    "housing_diameter_mm": ("Tělo zdroje – průměr [mm]", 0.0, 2000.0),
    "housing_length_mm": ("Tělo zdroje – délka [mm]", 0.0, 5000.0),
    "detector_width_mm": ("Detektor – šířka [mm]", 1.0, 2000.0),
    "detector_length_mm": ("Detektor – délka [mm]", 1.0, 2000.0),
    "detector_thickness_mm": ("Detektor – tloušťka kazety nebo panelu [mm]", 0.0, 200.0),
    "step_mm": ("Krok sítě míst [mm]", MIN_STEP, 100.0),
    "image_step_mm": ("Krok náhledu na detektoru [mm]", 0.2, 50.0),
}
_PROJECTION_LIMITS = {
    "distance_mm": ("Vzdálenost zdroje od zaměřeného bodu [mm]", 1.0, 100_000.0),
    "detector_angle_deg": ("Natočení detektoru [°]", -360.0, 360.0),
    "detector_distance_mm": ("Vzdálenost detektoru od zdroje [mm]", 1.0, 100_000.0),
    "reference_mm": ("Jmenovitá prozařovaná tloušťka [mm]", 0.01, 10_000.0),
}
DETECTOR_MODES = {"contact": "na ploše, kudy střední paprsek vystupuje",
                  "free": "volně, kolmo ke střednímu paprsku"}


def _number(value: Any, label: str, low: float, high: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, int | float)
            or not math.isfinite(value) or not low <= value <= high):
        raise RtError(f"{label} musí být číslo {_n(low)}–{_n(high)}.")
    return float(value)


def _vector(value: Any, label: str) -> Point:
    if (not isinstance(value, list | tuple) or len(value) != 3
            or not all(isinstance(v, int | float) and not isinstance(v, bool)
                       and math.isfinite(v) for v in value)):
        raise RtError(f"{label} musí být trojice čísel [x, y, z].")
    return (float(value[0]), float(value[1]), float(value[2]))


@dataclass(frozen=True)
class Projection:
    """Jedna projekce (expozice): zaměřený bod, směr ke zdroji, vzdálenost, detektor."""

    name: str
    aim: Point  # zaměřený bod na straně zdroje (obvykle střed svaru)
    direction: Point  # jednotkový směr od zaměřeného bodu ke zdroji
    distance_mm: float = 500.0  # zdroj = aim + distance · direction
    detector: str = "contact"
    detector_angle_deg: float = 0.0  # natočení delší strany (0° = průmět osy +X)
    detector_distance_mm: float | None = None  # u volného detektoru: od zdroje
    reference_mm: float | None = None  # ručně zadaná jmenovitá prozařovaná tloušťka

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise RtError("Projekce musí mít název, např. „P1“.")
        object.__setattr__(self, "name", self.name.strip())
        aim = _vector(self.aim, f"Projekce {self.name}: zaměřený bod")
        given = _vector(self.direction, f"Projekce {self.name}: směr ke zdroji")
        length = math.sqrt(_dot(given, given))
        if length < 1e-12:
            raise RtError(f"Projekce {self.name}: směr ke zdroji nesmí být nulový.")
        # Jednotkový směr se nepřepočítává – uložený a znovu načtený záznam je totožný.
        direction = given if abs(length - 1) < 1e-12 else _unit(given)
        object.__setattr__(self, "aim", aim)
        object.__setattr__(self, "direction", direction)
        for key, (label, low, high) in _PROJECTION_LIMITS.items():
            value = getattr(self, key)
            if value is None and key in ("detector_distance_mm", "reference_mm"):
                continue
            object.__setattr__(self, key, _number(value, f"Projekce {self.name}: {label}",
                                                  low, high))
        if self.detector not in DETECTOR_MODES:
            raise RtError(f"Projekce {self.name}: detektor musí být „contact“ (na ploše) nebo "
                          "„free“ (volně).")
        if self.detector == "free":
            if self.detector_distance_mm is None:
                raise RtError(f"Projekce {self.name}: u volného detektoru zadej jeho vzdálenost "
                              "od zdroje.")
            if self.detector_distance_mm <= self.distance_mm:
                raise RtError(f"Projekce {self.name}: detektor musí být dál od zdroje než "
                              "zaměřený bod.")

    @property
    def source(self) -> Point:
        return _add(self.aim, self.direction, self.distance_mm)

    @classmethod
    def from_dict(cls, data: Any) -> Projection:
        if not isinstance(data, dict):
            raise RtError("Projekce RT musí být objekt, např. {\"name\": \"P1\", \"aim\": "
                          "[0, 0, 20], \"direction\": [0, 0, 1]}.")
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise RtError(f"Projekce RT nezná {', '.join(unknown)} "
                          f"(zná {', '.join(sorted(known))}).")
        missing = [key for key in ("name", "aim", "direction") if key not in data]
        if missing:
            raise RtError(f"Projekci RT chybí {', '.join(missing)}.")
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["aim"] = list(self.aim)
        data["direction"] = list(self.direction)
        for key in ("detector_distance_mm", "reference_mm"):
            if data[key] is None:
                del data[key]
        return data


@dataclass(frozen=True)
class RtSettings:
    """Nastavení RT uložené v RT studii (``rt``, formát 21). Chybějící = výchozí."""

    test_class: str = "B"  # v souboru „class“: A základní, B zlepšená (ISO 17636-1)
    focal_mm: float = 3.0
    cone_deg: float = 40.0  # vrcholový úhel kuželu svazku; 360 = panoramatický zdroj
    housing_diameter_mm: float = 120.0  # 0 = jen bod (bez těla zdroje)
    housing_length_mm: float = 300.0
    detector_width_mm: float = 100.0
    detector_length_mm: float = 240.0
    detector_thickness_mm: float = 2.0
    step_mm: float | None = None  # None = automaticky (plochy asi TARGET_SAMPLES míst)
    image_step_mm: float = 2.0
    projections: tuple[Projection, ...] = ()

    def __post_init__(self) -> None:
        if self.test_class not in CLASS_FACTOR:
            raise RtError("Třída zkoušky musí být „A“ (základní) nebo „B“ (zlepšená).")
        for key, (label, low, high) in _LIMITS.items():
            value = getattr(self, key)
            if key == "step_mm" and value is None:
                continue
            object.__setattr__(self, key, _number(value, label, low, high))
        projections = tuple(self.projections)
        if not all(isinstance(p, Projection) for p in projections):
            raise RtError("Projekce RT musí být seznam projekcí.")
        if len(projections) > MAX_PROJECTIONS:
            raise RtError(f"Projekcí může být nejvýš {MAX_PROJECTIONS}.")
        names = [p.name for p in projections]
        duplicate = next((n for n in names if names.count(n) > 1), None)
        if duplicate:
            raise RtError(f"Název projekce „{duplicate}“ je dvakrát – každá projekce musí mít "
                          "jiný název.")
        object.__setattr__(self, "projections", projections)

    @classmethod
    def from_dict(cls, data: Any) -> RtSettings:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise RtError("Nastavení RT („rt“) musí být objekt, např. {\"class\": \"B\"}.")
        known = {f.name for f in fields(cls) if f.name != "test_class"} | {"class"}
        unknown = sorted(set(data) - known)
        if unknown:
            raise RtError(f"Nastavení RT nezná {', '.join(unknown)} "
                          f"(zná {', '.join(sorted(known))}).")
        values = {key: value for key, value in data.items() if key not in ("class",
                                                                           "projections")}
        if "class" in data:
            values["test_class"] = data["class"]
        projections = data.get("projections", [])
        if not isinstance(projections, list):
            raise RtError("Projekce RT („projections“) musí být seznam.")
        values["projections"] = tuple(Projection.from_dict(p) for p in projections)
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"class": self.test_class}
        for f in fields(self):
            if f.name in ("test_class", "projections"):
                continue
            value = getattr(self, f.name)
            if f.name == "step_mm" and value is None:
                continue
            data[f.name] = value
        data["projections"] = [p.to_dict() for p in self.projections]
        return data

    def projection(self, name: str) -> Projection:
        found = next((p for p in self.projections if p.name == name), None)
        if found is None:
            raise RtError(f"Projekce „{name}“ ve studii není.")
        return found

    def with_projections(self, projections: list[Projection] | tuple[Projection, ...]
                         ) -> RtSettings:
        return replace(self, projections=tuple(projections))

    @property
    def ratio_limit(self) -> float:
        return RATIO_LIMIT[self.test_class]

    def f_min(self, b: float, thickness: float | None, test_class: str | None = None) -> float:
        """Nejmenší vzdálenost zdroje od předmětu $k \\cdot d \\cdot b^{2/3}$ [mm]; když
        $b < 1{,}2\\,t$, dosadí se $t$ (ISO 5579)."""
        if thickness is not None and b < THIN_FACTOR * thickness:
            b = thickness
        return CLASS_FACTOR[test_class or self.test_class] * self.focal_mm * max(b, 0.0) ** (2 / 3)

    def lines(self) -> list[str]:
        """Předpoklady výpočtu česky (souhrn, CSV)."""
        housing = (f"tělo zdroje válec Ø {_n(self.housing_diameter_mm)} × "
                   f"{_n(self.housing_length_mm)} mm za ohniskem v ose svazku"
                   if self.housing_diameter_mm > 0 and self.housing_length_mm > 0
                   else "bez těla zdroje (jen bod)")
        cone = ("panoramatický zdroj (kužel 360°)" if self.cone_deg >= 360
                else f"kužel svazku {_n(self.cone_deg)}°")
        return [f"Zdroj: ohnisko {_n(self.focal_mm)} mm, {cone}, {housing} ({CHOSEN}).",
                f"Detektor: plochý {_n(self.detector_width_mm)} × "
                f"{_n(self.detector_length_mm)} mm ({FILM_SOURCE}), kazeta nebo panel "
                f"{_n(self.detector_thickness_mm)} mm ({CHOSEN}).",
                f"Třída zkoušky {self.test_class}: poměr prozařované tloušťky k tloušťce "
                f"na středu svazku nejvýš {_n(self.ratio_limit)} – {RATIO_SOURCE}.",
                f"Nejmenší vzdálenost zdroje f_min = {_n(CLASS_FACTOR[self.test_class])} · d · "
                f"b^(2/3); když b < {_n(THIN_FACTOR)} · t, dosadí se t – {FMIN_SOURCE}.",
                "Prozařovaná tloušťka = všechny úseky v materiálu na spojnici ohnisko–detektor; "
                "paprsek přes hranu nebo tečně je nejistý."]


def next_projection_name(settings: RtSettings) -> str:
    """První volný název projekce „P1“, „P2“ …"""
    names = {p.name for p in settings.projections}
    return next(f"P{i}" for i in range(1, len(names) + 2) if f"P{i}" not in names)


# --- projekce: zdroj a detektor --------------------------------------------------------------


@dataclass(frozen=True)
class Setup:
    """Spočítaná projekce: zdroj, střední paprsek a přiložený detektor (jen čísla, přenosné
    pomocným procesem; tvary pro kresbu dá ``setup_shapes``)."""

    name: str
    ok: bool
    kind: str  # "" nebo druh z SETUP_FAILURES
    text: str
    source: Point
    axis: Point  # jednotkový směr středního paprsku (od zdroje)
    entry: float | None  # kde střední paprsek vstoupí do dílu [mm od zdroje]
    w0: float  # prozařovaná tloušťka středního paprsku [mm]
    w0_certain: bool
    mode: str  # contact / free
    center: Point  # střed aktivní plochy detektoru
    normal: Point  # normála roviny detektoru (od zdroje pryč)
    long: Point  # delší strana detektoru
    short: Point
    offset: float  # odsunutí detektoru od plochy kvůli nárazu [mm]
    plane: float  # vzdálenost roviny detektoru od zdroje po středním paprsku [mm]

    @property
    def f(self) -> float | None:
        return self.entry

    @property
    def b(self) -> float | None:
        return None if self.entry is None else self.plane - self.entry


def _box(center: Point, normal: Point, long: Point, settings: RtSettings, offset: float) -> Any:
    """Deska detektoru: aktivní plocha v rovině ``center + offset · normal``, tloušťka za ní."""
    from build123d import Box, Location, Plane

    thickness = max(settings.detector_thickness_mm, 0.01)
    origin = _add(center, normal, offset + thickness / 2)
    return Location(Plane(origin=origin, x_dir=long, z_dir=normal)) * Box(
        settings.detector_length_mm, settings.detector_width_mm, thickness)


def _housing(source: Point, axis: Point, settings: RtSettings) -> Any | None:
    from build123d import Plane, Solid

    if settings.housing_diameter_mm <= 0 or settings.housing_length_mm <= 0:
        return None
    back = (-axis[0], -axis[1], -axis[2])
    return Solid.make_cylinder(settings.housing_diameter_mm / 2, settings.housing_length_mm,
                               Plane(origin=source, z_dir=back))


def setup_shapes(setup: Setup, settings: RtSettings) -> tuple[Any | None, Any | None]:
    """Tělo zdroje a deska detektoru jako tvary build123d (kresba v okně)."""
    housing = _housing(setup.source, setup.axis, settings)
    if setup.plane <= 0:
        return housing, None
    return housing, _box(setup.center, setup.normal, setup.long, settings, 0.0)


def _overlap_volume(part: Any, solid: Any) -> float | None:
    return overlap(part.wrapped, solid.wrapped)


def prepare(geo: PartGeometry, settings: RtSettings, projection: Projection) -> Setup:
    """Zdroj, střední paprsek a přiložení detektoru jedné projekce (s kolizemi)."""
    source = projection.source
    axis = (-projection.direction[0], -projection.direction[1], -projection.direction[2])

    def failed(kind: str, text: str, **known: Any) -> Setup:
        base = {"entry": None, "w0": 0.0, "w0_certain": False, "center": projection.aim,
                "normal": axis, "long": _base(axis), "short": _cross(axis, _base(axis)),
                "offset": 0.0, "plane": 0.0}
        base.update(known)
        return Setup(projection.name, False, kind, text, source, axis,
                     mode=projection.detector, **base)

    if geo.classify(source) == "inside":
        return failed("source_inside", "Zdroj je v materiálu dílu – zvětši vzdálenost nebo změň "
                                       "směr ke zdroji.")
    housing = _housing(source, axis, settings)
    if housing is not None:
        volume = _overlap_volume(geo.part, housing)
        if volume is None or volume > OVERLAP_TOL:
            amount = "nejde spočítat" if volume is None else f"průnik {volume:.0f} mm³"
            return failed("housing", f"Tělo zdroje naráží do dílu ({amount}) – zvětši "
                                     "vzdálenost, změň směr nebo zmenši tělo zdroje.")
    ray = geo.cast(source, axis)
    entry = ray.segments[0].start if ray.segments else None
    if projection.detector == "contact":
        if not ray.segments:
            return failed("no_exit", "Střední paprsek dílem neprochází (míří do otvoru nebo "
                                     "mimo díl) – detektor na ploše nejde přiložit; přilož ho "
                                     "volně nebo zamiř zdroj na díl.")
        exit_at = ray.segments[-1].end
        exit_point = ray.point_at(exit_at)
        try:
            surface = geo.surface_at(exit_point)
        except GeometryError as exc:
            return failed("no_exit", f"Plochu výstupu středního paprsku nejde určit: {exc}")
        normal = _unit(surface.normal) or axis
        if _dot(normal, axis) < FACING_DETECTOR:
            return failed("exit_face", "Plocha, kudy střední paprsek vystupuje, je skoro "
                                       "rovnoběžná se svazkem – přilož detektor volně.")
        long = _unit(_rotate(_base(normal), normal, projection.detector_angle_deg)) or \
            _base(normal)

        def plane_at(offset: float) -> float:
            """Vzdálenost (odsunuté) roviny detektoru od zdroje po středním paprsku."""
            return _dot(_sub(_add(exit_point, normal, offset), source), normal) / _dot(axis,
                                                                                        normal)

        def clash(offset: float) -> float | None:
            center = _add(source, axis, plane_at(offset))
            return _overlap_volume(geo.part, _box(center, normal, long, settings, 0.0))

        offset = 0.0
        volume = clash(0.0)
        if volume is None or volume > OVERLAP_TOL:
            far = clash(PUSH_MAX_MM)
            if far is None or far > OVERLAP_TOL:
                amount = "nejde spočítat" if far is None else f"průnik {far:.0f} mm³"
                return failed("detector", f"Detektor nejde přiložit – naráží do dílu i po "
                                          f"odsunutí o {_n(PUSH_MAX_MM)} mm ({amount}).")
            low, high = 0.0, PUSH_MAX_MM
            while high - low > PUSH_TOL_MM:
                middle = (low + high) / 2
                found = clash(middle)
                if found is None or found > OVERLAP_TOL:
                    low = middle
                else:
                    high = middle
            offset = high
        plane = plane_at(offset)
        center = _add(source, axis, plane)
    else:
        plane = float(projection.detector_distance_mm or 0.0)
        normal = axis
        long = _unit(_rotate(_base(axis), axis, projection.detector_angle_deg)) or _base(axis)
        center = _add(source, axis, plane)
        volume = _overlap_volume(geo.part, _box(center, normal, long, settings, 0.0))
        if volume is None or volume > OVERLAP_TOL:
            amount = "nejde spočítat" if volume is None else f"průnik {volume:.0f} mm³"
            return failed("detector", f"Detektor naráží do dílu ({amount}) – zvětši jeho "
                                      "vzdálenost od zdroje.", entry=entry)
        offset = 0.0
    central = geo.cast(source, axis, plane)
    w0 = sum(segment.length for segment in central.segments)
    short = _cross(normal, long)
    text = (f"Zdroj {_point_text(source)} mm, detektor {DETECTOR_MODES[projection.detector]}"
            + (f" (odsunut o {_dec(offset, 2)} mm – deska narazila)" if offset > 0 else "")
            + ".")
    return Setup(projection.name, True, "", text, source, axis, entry, w0, central.certain,
                 projection.detector, center, normal, long, short, offset, plane)


# --- místa oblasti ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Shot:
    """Místo v jedné projekci."""

    state: str  # STATES
    thickness: float | None  # prozařovaná tloušťka [mm]
    ratio: float | None
    unsharpness: float | None  # U_g místa [mm]
    magnification: float | None
    on_detector: tuple[float, float] | None  # (podél, napříč) od středu detektoru [mm]
    reasons: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RtSample:
    """Jedno místo oblasti (těžiště trojúhelníku plochy nebo vnitřní bod buňky objemu)."""

    point: Point | None
    normal: Point | None
    weight: float  # mm² (plochy) nebo mm³ (objem)
    shots: tuple[Shot, ...]
    state: str  # celkem za projekce
    covered: int  # kolik projekcí místo promítne zeleně

    def grade(self, view: str | None) -> str:
        """Stav pro přepínač mapy: None = celkem, „p0“, „p1“ … = projekce."""
        if view is None:
            return self.state
        return self.shots[int(view[1:])].state


@dataclass(frozen=True)
class ProjectionResult:
    """Čísla projekce pro souhrn: vzdálenosti normy, tloušťka na středu, počty."""

    setup: Setup
    reference: float | None  # tloušťka na středu svazku použitá pro poměr [mm]
    reference_manual: bool
    reference_ok: bool
    f: float | None  # zdroj → strana předmětu u zdroje (po středním paprsku) [mm]
    b: float | None  # strana předmětu u zdroje → detektor [mm]
    f_min_a: float | None
    f_min_b: float | None
    unsharpness: float | None
    magnification: float | None
    test_class: str = "B"

    @property
    def distance_ok(self) -> bool:
        f_min = self.f_min_b if self.test_class == "B" else self.f_min_a
        return self.f is None or f_min is None or self.f >= f_min - 1e-9


@dataclass(frozen=True)
class RtImage:
    """Náhled prozařované tloušťky na aktivní ploše detektoru (jen délky v materiálu)."""

    columns: int  # podél delší strany
    rows: int  # napříč
    cell_long: float
    cell_short: float
    thickness: tuple[float, ...]  # [mm], po řádcích (řádek = jedna poloha napříč)
    flags: str  # znak na buňku: „o“ paprsek jistý, „u“ nejistý, „b“ mimo svazek
    max_mm: float

    def value(self, column: int, row: int) -> tuple[float, str]:
        index = row * self.columns + column
        return self.thickness[index], self.flags[index]


def _own(ray: Any, at: float) -> tuple[float, float]:
    """Úsek materiálu na paprsku, ve kterém místo leží (stejná stěna). Průchod oblastí jinde
    ve stejném úseku (kořen a převýšení téhož svaru) překryv obrazů není – ten vzniká, až
    když je mezi průchody vzduch (protější stěna trubky, druhý svar)."""
    for segment in ray.segments:
        if segment.start - CROSSING_GAP_MM <= at <= segment.end + CROSSING_GAP_MM:
            return segment.start - CROSSING_GAP_MM, segment.end + CROSSING_GAP_MM
    return at - CROSSING_GAP_MM, at + CROSSING_GAP_MM


def _faces_crossings(target_faces: list[Any]) -> Callable[[Any, float], int]:
    """Kolikrát paprsek projde plochami oblasti v jiném kusu materiálu než místo."""

    def count(ray: Any, at: float) -> int:
        low, high = _own(ray, at)
        spots = sorted(hit.distance for hit in ray.hits if hit.face is not None
                       and not low <= hit.distance <= high
                       and any(hit.face.wrapped.IsSame(face.wrapped) for face in target_faces))
        groups: list[float] = []
        for spot in spots:
            if not groups or spot - groups[-1] > CROSSING_GAP_MM:
                groups.append(spot)
        return len(groups)

    return count


def _volume_crossings(target: PartGeometry) -> Callable[[Any, float], int]:
    """Kolikrát paprsek projde cílovým objemem v jiném kusu materiálu než místo."""

    def count(ray: Any, at: float) -> int:
        low, high = _own(ray, at)
        inner = target.cast(ray.origin, ray.direction, ray.max_length)
        others = [segment for segment in inner.segments
                  if segment.end < low or segment.start > high]
        pieces: list[list[float]] = []
        for segment in others:
            if pieces and segment.start - pieces[-1][1] <= CROSSING_GAP_MM:
                pieces[-1][1] = segment.end
            else:
                pieces.append([segment.start, segment.end])
        return len(pieces)

    return count


@dataclass(frozen=True)
class _Raw:
    """Místo v projekci před rozhodnutím o stavu (tloušťka na středu je známá až potom)."""

    blocked: tuple[str, str] | None
    thickness: float | None = None
    certain: bool = True
    unsharpness: float | None = None
    magnification: float | None = None
    on_detector: tuple[float, float] | None = None
    crossings: int = 0
    angle: float = 0.0  # od středního paprsku [°]
    entry: float | None = None  # kde paprsek vstoupí do dílu, po středním paprsku [mm]


def _shoot(geo: PartGeometry, setup: Setup, settings: RtSettings, point: Point,
           crossings: Callable[[Any, float], int] | None) -> _Raw:
    if not setup.ok:
        return _Raw(("setup", setup.text))
    v = _sub(point, setup.source)
    distance = math.sqrt(_dot(v, v))
    if distance < 1e-9:
        return _Raw(("beam", "Místo leží v ohnisku zdroje."))
    d = (v[0] / distance, v[1] / distance, v[2] / distance)
    angle = math.degrees(math.acos(max(-1.0, min(1.0, _dot(d, setup.axis)))))
    if settings.cone_deg < 360 and angle > settings.cone_deg / 2 + 1e-9:
        return _Raw(("beam", f"Mimo svazek – {_dec(angle)}° od středního paprsku (kužel "
                             f"{_n(settings.cone_deg)}°)."))
    toward = _dot(d, setup.normal)
    if toward <= 1e-9:
        return _Raw(("detector", "Mimo detektor – paprsek k rovině detektoru nemíří."))
    reach = _dot(_sub(setup.center, setup.source), setup.normal) / toward
    if reach < distance - 1e-6:
        return _Raw(("behind", "Místo leží za rovinou detektoru."))
    hit = _add(setup.source, d, reach)
    along = _dot(_sub(hit, setup.center), setup.long)
    across = _dot(_sub(hit, setup.center), setup.short)
    excess = max(abs(along) - settings.detector_length_mm / 2,
                 abs(across) - settings.detector_width_mm / 2)
    if excess > 1e-9:
        return _Raw(("detector", f"Mimo detektor o {_dec(excess)} mm."),
                    on_detector=(along, across))
    ray = geo.cast(setup.source, d, reach)
    thickness = sum(segment.length for segment in ray.segments)
    behind = reach - distance
    entry = _entry(setup, ray, d)
    return _Raw(None, thickness, ray.certain, settings.focal_mm * behind / distance,
                reach / distance, (along, across),
                crossings(ray, distance) if crossings is not None else 0, angle, entry)


def _entry(setup: Setup, ray: Any, d: Point) -> float | None:
    """Kde paprsek vstoupí do dílu, převedeno na střední paprsek: průsečík středního paprsku
    s tečnou rovinou plochy vstupu (na šikmém plechu nezávisí na tom, jak daleko od osy místo
    leží); u plochy skoro rovnoběžné se svazkem jen průmět bodu vstupu."""
    if not ray.segments:
        return None
    first = ray.segments[0]
    hit = first.entry
    if hit is not None:
        facing = _dot(setup.axis, hit.normal)
        if abs(facing) > 0.1:
            return _dot(_sub(hit.point, setup.source), hit.normal) / facing
    return first.start * _dot(d, setup.axis)


def _reference(setup: Setup, projection: Projection, raws: list[_Raw]
               ) -> tuple[float | None, bool, bool, str]:
    """Tloušťka na středu svazku pro poměr: (hodnota, ručně, použitelná, důvod nepoužití)."""
    if projection.reference_mm is not None:
        return projection.reference_mm, True, True, ""
    if not setup.ok:
        return None, False, False, ""
    good = [r.thickness for r in raws if r.blocked is None and r.certain and r.thickness]
    median = statistics.median(good) if good else None
    if setup.w0 <= 0 or not setup.w0_certain or (median is not None
                                                  and setup.w0 < REFERENCE_SHARE * median):
        return setup.w0, False, False, REFERENCE_HINT
    return setup.w0, False, True, ""


def _distances(setup: Setup, settings: RtSettings, raws: list[_Raw], reference: float | None,
               usable: bool) -> tuple[float | None, float | None, float | None, float | None,
                                      str | None]:
    """f, b, f_min (A, B) a věta o nedodržené vzdálenosti. Strana předmětu u zdroje se bere
    z paprsku k místu oblasti nejblíž středu svazku (u plného plechu totéž co střední paprsek;
    střední paprsek do otvoru by dal nesmyslné b), jinak ze středního paprsku."""
    if not setup.ok:
        return None, None, None, None, None
    near = [r for r in raws if r.blocked is None and r.entry is not None]
    f = min(near, key=lambda r: r.angle).entry if near else setup.entry
    if f is None:
        return None, None, None, None, None
    b = setup.plane - f
    thickness = reference if usable else None
    f_min_a = settings.f_min(b, thickness, "A")
    f_min_b = settings.f_min(b, thickness, "B")
    needed = f_min_a if settings.test_class == "A" else f_min_b
    text = None
    if f < needed - 1e-9:
        text = (f"Zdroj je blíž, než dovoluje ISO 17636-1 pro třídu {settings.test_class} "
                f"(f = {_dec(f)} mm < f_min = {_dec(needed)} mm).")
    return f, b, f_min_a, f_min_b, text


def _finish(raw: _Raw, settings: RtSettings, reference: float | None, reference_ok: bool,
            distance_text: str | None) -> Shot:
    if raw.blocked is not None:
        state = "uncertain" if raw.blocked[0] == "point" else "blocked"
        return Shot(state, None, None, None, None, raw.on_detector, (raw.blocked,))
    reasons: list[tuple[str, str]] = []
    ratio = (raw.thickness / reference if reference_ok and reference and raw.thickness
             is not None else None)
    if not raw.certain:
        reasons.append(("uncertain", "Nejistý paprsek – vede přes hranu nebo tečně k ploše."))
    if not reference_ok:
        reasons.append(("reference", f"Poměr tloušťky nelze určit – {REFERENCE_HINT}."))
    if ratio is not None and ratio > settings.ratio_limit + 1e-9:
        reasons.append(("ratio", f"Poměr tloušťky {_dec(ratio, 3)} > {_n(settings.ratio_limit)} "
                                 f"(třída {settings.test_class})."))
    if distance_text:
        reasons.append(("distance", distance_text))
    if raw.crossings:
        reasons.append(("overlap", f"Obraz se překrývá s jinou částí oblasti – paprsek jí "
                                   f"prochází ještě {raw.crossings}×."))
    kinds = {kind for kind, _ in reasons}
    if kinds & {"uncertain", "reference"}:
        state = "uncertain"
    elif kinds & {"ratio", "distance", "overlap"}:
        state = "limited"
    else:
        state = "ok"
    return Shot(state, raw.thickness, ratio, raw.unsharpness, raw.magnification,
                raw.on_detector, tuple(reasons))


def _image(geo: PartGeometry, setup: Setup, settings: RtSettings) -> RtImage | None:
    """Prozařovaná tloušťka v síti buněk aktivní plochy detektoru (paprsek do středu buňky)."""
    if not setup.ok:
        return None
    columns = max(1, round(settings.detector_length_mm / settings.image_step_mm))
    rows = max(1, round(settings.detector_width_mm / settings.image_step_mm))
    while columns * rows > MAX_IMAGE_CELLS:
        columns, rows = max(1, columns // 2), max(1, rows // 2)
    cell_long = settings.detector_length_mm / columns
    cell_short = settings.detector_width_mm / rows
    values, flags = [], []
    for row in range(rows):
        across = -settings.detector_width_mm / 2 + (row + 0.5) * cell_short
        for column in range(columns):
            along = -settings.detector_length_mm / 2 + (column + 0.5) * cell_long
            target = _add(_add(setup.center, setup.long, along), setup.short, across)
            v = _sub(target, setup.source)
            length = math.sqrt(_dot(v, v))
            d = (v[0] / length, v[1] / length, v[2] / length)
            angle = math.degrees(math.acos(max(-1.0, min(1.0, _dot(d, setup.axis)))))
            if settings.cone_deg < 360 and angle > settings.cone_deg / 2 + 1e-9:
                values.append(0.0)
                flags.append("b")
                continue
            ray = geo.cast(setup.source, d, length)
            values.append(sum(segment.length for segment in ray.segments))
            flags.append("o" if ray.certain else "u")
    return RtImage(columns, rows, cell_long, cell_short, tuple(values), "".join(flags),
                   max(values) if values else 0.0)


# --- výsledek --------------------------------------------------------------------------------


@dataclass
class RtMap:
    """Mapa geometrického promítnutí oblasti RT (jen pohled, neukládá se)."""

    kind: str  # faces / volume
    nodes: list[Point]
    triangles: list[tuple[int, int, int]]
    samples: list[RtSample]
    settings: RtSettings
    projections: tuple[ProjectionResult, ...]
    images: tuple[RtImage | None, ...]
    step_mm: float
    faces: int
    material: str
    seconds: float
    volume_samples: list[Any] = field(default_factory=list)  # buňky 07B (kresba objemu)

    @property
    def unit(self) -> str:
        return "mm²" if self.kind == "faces" else "mm³"

    @property
    def total(self) -> float:
        return sum(s.weight for s in self.samples)

    def amount(self, state: str, view: str | None = None) -> float:
        return sum(s.weight for s in self.samples if s.grade(view) == state)

    def percent(self, state: str, view: str | None = None) -> float:
        total = self.total
        return 100 * self.amount(state, view) / total if total else 0.0

    def views(self) -> dict[str | None, str]:
        """Přepínač mapy: celkem a každá projekce."""
        return {None: "Celkem", **{f"p{i}": f"Projekce {p.setup.name}"
                                   for i, p in enumerate(self.projections)}}

    def mesh(self, view: str | None = None) -> tuple[list, list, list]:
        """Oddělené uzly každé plošky (barva celého trojúhelníku) – jen oblast z ploch."""
        if self.kind != "faces":
            return [], [], []
        nodes, triangles, out = [], [], []
        for tri, sample in zip(self.triangles, self.samples, strict=True):
            start = len(nodes)
            nodes.extend(self.nodes[i] for i in tri)
            triangles.append((start, start + 1, start + 2))
            out.extend([COLORS[sample.grade(view)]] * 3)
        return nodes, triangles, out

    def nearest(self, point: Point) -> int | None:
        """Místo nejblíž bodu (klik do mapy)."""
        found = [i for i, s in enumerate(self.samples) if s.point is not None]
        if not found:
            return None
        return min(found, key=lambda i: sum((a - b) ** 2 for a, b in zip(
            self.samples[i].point, point, strict=True)))

    def describe(self, index: int) -> list[str]:
        """Stav místa v každé projekci s čísly a důvody česky (klik do mapy)."""
        s = self.samples[index]
        lines = [f"{STATES[s.state]} – projekcí, které místo promítnou: {s.covered} "
                 f"z {len(self.projections)}."]
        for result, shot in zip(self.projections, s.shots, strict=True):
            parts = [f"{result.setup.name}: {SHORT[shot.state]}"]
            if shot.thickness is not None:
                parts.append(f"prozařovaná tloušťka {_dec(shot.thickness, 2)} mm")
            if shot.ratio is not None:
                parts.append(f"poměr {_dec(shot.ratio, 3)}")
            if shot.unsharpness is not None:
                parts.append(f"neostrost {_dec(shot.unsharpness, 2)} mm")
            if shot.on_detector is not None and shot.state != "blocked":
                parts.append(f"na detektoru {_dec(shot.on_detector[0])}; "
                             f"{_dec(shot.on_detector[1])} mm od středu")
            lines.append(", ".join(parts) + ".")
            lines += [f"  {text}" for _, text in shot.reasons]
        if s.point is not None:
            lines.append("Místo " + "; ".join(_dec(v) for v in s.point) + " mm.")
        return lines

    def reason_amounts(self) -> list[tuple[str, float]]:
        """Důvody, proč místa nejsou zelená v žádné projekci (podle plochy nebo objemu)."""
        amounts: dict[str, float] = {}
        for s in self.samples:
            if s.state == "ok":
                continue
            kinds = dict.fromkeys(kind for shot in s.shots for kind, _ in shot.reasons)
            for kind in kinds:
                amounts[kind] = amounts.get(kind, 0.0) + s.weight
        return sorted(amounts.items(), key=lambda item: -item[1])

    def projection_lines(self) -> list[str]:
        lines = []
        for i, result in enumerate(self.projections):
            setup = result.setup
            if not setup.ok:
                lines.append(f"{setup.name}: projekce nejde – {setup.text}")
                continue
            parts = [f"{setup.name}: {setup.text}"]
            if result.f is not None and result.b is not None:
                parts.append(f"f = {_dec(result.f)} mm, b = {_dec(result.b)} mm, f_min "
                             f"A {_dec(result.f_min_a or 0)} mm / B {_dec(result.f_min_b or 0)} "
                             "mm – " + ("vyhoví" if result.distance_ok else "nevyhoví")
                             + f" třídě {self.settings.test_class}; neostrost U_g "
                             f"{_dec(result.unsharpness or 0, 2)} mm, zvětšení "
                             f"{_dec(result.magnification or 0, 3)}.")
            else:
                parts.append("paprsky ke středu svazku dílem neprochází – f a b nejde určit.")
            if result.reference is not None and result.reference_ok:
                parts.append(f"Tloušťka na středu svazku {_dec(result.reference, 2)} mm"
                             + (" (zadaná ručně)." if result.reference_manual else "."))
            else:
                parts.append(f"Tloušťku na středu svazku nejde použít – {REFERENCE_HINT}.")
            view = f"p{i}"
            shares = ", ".join(f"{SHORT[state]} {_dec(self.percent(state, view), 2)} %"
                               for state in STATES if self.amount(state, view) > 0)
            parts.append(shares[:1].upper() + shares[1:] + ".")
            lines.append(" ".join(parts))
        return lines

    def summary(self) -> list[str]:
        total = self.total
        what = (f"plochy {self.faces}, míst {len(self.samples)}" if self.kind == "faces"
                else f"cílový objem, buněk {len(self.samples)}")
        lines = [RT_MAP, RT_DISCLAIMER, PERCENT_NOTE, f"{self.material} {PENETRATION_NOTE}",
                 f"Oblast: {what}, krok sítě {_n(round(self.step_mm, 2))} mm, celkem "
                 f"{_dec(total)} {self.unit}; projekcí {len(self.projections)}."]
        for state, label in STATES.items():
            lines.append(f"{label}: {_dec(self.percent(state), 2)} % "
                         f"({_dec(self.amount(state))} {self.unit}).")
        counts: dict[int, float] = {}
        for s in self.samples:
            counts[s.covered] = counts.get(s.covered, 0.0) + s.weight
        if total and len(self.projections) > 1:
            lines.append("Počet projekcí, které místo promítnou: " + ", ".join(
                f"{count} – {_dec(100 * amount / total)} %"
                for count, amount in sorted(counts.items())) + ".")
        lines += self.projection_lines()
        reasons = self.reason_amounts()
        if reasons and total:
            lines.append("Důvody: " + "; ".join(
                f"{REASONS[kind]} {_dec(100 * amount / total)} %"
                for kind, amount in reasons[:6]) + ".")
        lines += [*self.settings.lines(), DIGITAL_NOTE, ANGLE_NOTE,
                  f"Výpočet {_dec(self.seconds)} s; algoritmus {ALGORITHM}."]
        return lines

    def assumptions(self) -> dict[str, Any]:
        return {"algorithm": ALGORITHM, "step_mm": self.step_mm,
                "ratio_limit": self.settings.ratio_limit,
                "class_factor": CLASS_FACTOR[self.settings.test_class],
                "thin_factor": THIN_FACTOR, "reference_share": REFERENCE_SHARE,
                **self.settings.to_dict()}

    def write_csv(self, path: str | Path) -> Path:
        path = Path(path)

        def cz(value: float | None) -> str:
            return "" if value is None else f"{value:.6f}".replace(".", ",")

        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            for text in (RT_MAP, RT_DISCLAIMER, PERCENT_NOTE,
                         f"{self.material} {PENETRATION_NOTE}", *self.projection_lines(),
                         *self.settings.lines(), DIGITAL_NOTE, ANGLE_NOTE,
                         json.dumps(self.assumptions(), ensure_ascii=False, sort_keys=True)):
                writer.writerow([text])
            amount = "obsah" if self.kind == "faces" else "objem"
            header = ["x [mm]", "y [mm]", "z [mm]", f"{amount} [{self.unit}]", "stav",
                      "projekcí promítne"]
            for result in self.projections:
                name = result.setup.name
                header += [f"{name} stav", f"{name} tloušťka [mm]", f"{name} poměr",
                           f"{name} neostrost [mm]", f"{name} podél [mm]", f"{name} napříč [mm]",
                           f"{name} důvody"]
            writer.writerow(header)
            for s in self.samples:
                row = [*(cz(v) for v in (s.point or (None, None, None))), cz(s.weight),
                       STATES[s.state], s.covered]
                for shot in s.shots:
                    spot = shot.on_detector or (None, None)
                    row += [SHORT[shot.state], cz(shot.thickness), cz(shot.ratio),
                            cz(shot.unsharpness), cz(spot[0]), cz(spot[1]),
                            " | ".join(text for _, text in shot.reasons)]
                writer.writerow(row)
        return path


# --- výpočet ---------------------------------------------------------------------------------


@dataclass
class _Target:
    kind: str
    points: list[Point | None]
    normals: list[Point | None]
    weights: list[float]
    step: float
    faces: list[Any]
    nodes: list[Point] = field(default_factory=list)
    triangles: list[tuple[int, int, int]] = field(default_factory=list)
    volume_samples: list[Any] = field(default_factory=list)
    shape: Any = None  # účinný cílový objem (překryv obrazů)


def study_target(geo: PartGeometry, record: dict[str, Any]) -> tuple[str, Any]:
    """Oblast RT studie: („faces“, plochy) nebo („volume“, cílový objem); česká chyba jinak."""
    if record.get("method") != "RT":
        raise RtError("Projekci RT jde spočítat jen pro RT (radiografickou) studii.")
    target = record.get("target") or {}
    kind = target.get("kind", "faces")
    if kind in ("volume", "weld"):
        return "volume", target
    faces, problems = geo.faces_of(target)
    if problems:
        raise RtError(" ".join(problems))
    if not faces:
        raise RtError("RT studie nemá oblast – vyber plochy nebo zadej cílový objem svaru.")
    return "faces", faces


def _target(geo: PartGeometry, kind: str, target: Any, settings: RtSettings) -> _Target:
    if kind == "faces":
        faces = list(target)
        area = sum(face.area for face in faces)
        step = settings.step_mm or max(MIN_STEP, round(math.sqrt(
            area / (TARGET_SAMPLES * _AREA_PER_STEP2)), 1))
        try:
            surface = _Surface(geo.part, step, faces)
            for _ in range(3 if settings.step_mm is None else 0):
                count = len(surface.centers)
                if count <= 1.3 * TARGET_SAMPLES:
                    break
                step = round(step * math.sqrt(count / TARGET_SAMPLES) + 0.05, 1)
                surface = _Surface(geo.part, step, faces)
        except MapError as exc:
            raise RtError(str(exc)) from None
        if len(surface.centers) > MAX_SAMPLES:
            raise RtError(f"Oblast RT by měla {len(surface.centers)} míst (nejvýš "
                          f"{MAX_SAMPLES}) – zvol větší krok sítě.")
        return _Target("faces", list(surface.centers), list(surface.normals),
                       list(surface.areas), surface.step, faces, list(surface.nodes),
                       list(surface.triangles))
    from skodacad.ndt.coverage import CoverageError
    from skodacad.ndt.volume_coverage import _sample_volume, recommended_target_step
    from skodacad.ndt.welds import TargetError

    try:
        step = settings.step_mm or recommended_target_step(target)
        cells, resolved, _meta = _sample_volume(geo, target, step, 1, 1)
    except (CoverageError, TargetError) as exc:
        raise RtError(str(exc)) from None
    return _Target("volume", [c.point for c in cells], [None] * len(cells),
                   [c.volume_mm3 for c in cells], step, [], volume_samples=cells,
                   shape=resolved.shape)


def _material_text(material: str | None) -> str:
    from skodacad.materials import DISPLAY_NAMES, material_key

    key = material_key(material or "")
    name = DISPLAY_NAMES.get(key, material) if key else "neuvedený materiál"
    return f"Prozařovaná tloušťka je v mm materiálu dílu ({name})."


def estimate(part: Any, record: dict[str, Any], settings: RtSettings
             ) -> tuple[int, float, int, float]:
    """Odhad před spuštěním: (míst oblasti, krok sítě, projekcí, doba v s). U objemu jsou
    místa buňky mřížky před ořezem cílem (nejvýš tolik) – přesný ořez je pomalý a dělá ho
    až výpočet."""
    geo = PartGeometry(part)
    kind, target = study_target(geo, record)
    if kind == "volume":
        from skodacad.ndt.coverage import CoverageError
        from skodacad.ndt.volume_coverage import MAX_CELLS, grid_extent, recommended_target_step
        from skodacad.ndt.welds import TargetError

        try:
            step = settings.step_mm or recommended_target_step(target)
            count = math.prod(grid_extent(target, step)[2])
        except (CoverageError, TargetError) as exc:
            raise RtError(str(exc)) from None
        if count > MAX_CELLS:
            raise RtError(f"Objemová mřížka by měla {count} buněk (nejvýš {MAX_CELLS}) – "
                          "zvol větší krok sítě.")
        clipping = count * SECONDS_PER_CELL
    else:
        found = _target(geo, kind, target, settings)
        count, step, clipping = len(found.points), found.step, 0.0
    projections = len(settings.projections)
    cells = (max(1, round(settings.detector_length_mm / settings.image_step_mm))
             * max(1, round(settings.detector_width_mm / settings.image_step_mm)))
    rays = projections * (count * (2 if kind == "volume" else 1) + min(cells, MAX_IMAGE_CELLS))
    seconds = clipping + rays * SECONDS_PER_RAY + projections * SECONDS_PER_PROJECTION
    return count, step, projections, seconds


def compute(part: Any, record: dict[str, Any], settings: RtSettings,
            material: str | None = None,
            progress: Callable[[int, int], None] | None = None) -> RtMap:
    """Mapa promítnutí oblasti RT studie pro všechny projekce a náhledy na detektoru."""
    started = time.monotonic()
    if not settings.projections:
        raise RtError("RT studie nemá projekci – přidej ji tlačítkem „Zdroj nad vybrané "
                      "místo“.")
    try:
        geo = PartGeometry(part)
    except GeometryError as exc:
        raise RtError(str(exc)) from None
    kind, target = study_target(geo, record)
    found = _target(geo, kind, target, settings)
    crossings = (_faces_crossings(found.faces) if kind == "faces"
                 else _volume_crossings(PartGeometry(found.shape)))
    total = len(settings.projections) * (len(found.points) + 1)
    done = 0
    results, images, columns = [], [], []
    for projection in settings.projections:
        setup = prepare(geo, settings, projection)
        raws = [(_shoot(geo, setup, settings, point, crossings) if point is not None
                 else _Raw(("point", "Vnitřní bod buňky objemu nebyl nalezen – místo nejde "
                                     "vyhodnotit.")))
                for point in found.points]
        reference, manual, usable, _why = _reference(setup, projection, raws)
        f, b, f_min_a, f_min_b, distance_text = _distances(setup, settings, raws, reference,
                                                           usable)
        unsharpness = settings.focal_mm * b / f if f and b is not None else None
        magnification = (f + b) / f if f and b is not None else None
        shots = [_finish(raw, settings, reference, usable, distance_text) for raw in raws]
        columns.append(shots)
        results.append(ProjectionResult(setup, reference, manual, usable, f, b, f_min_a,
                                        f_min_b, unsharpness, magnification,
                                        settings.test_class))
        images.append(_image(geo, setup, settings))
        done += len(found.points) + 1
        if progress is not None:
            progress(done, total)
    samples = []
    for i, point in enumerate(found.points):
        shots = tuple(column[i] for column in columns)
        state = min((shot.state for shot in shots), key=ORDER.index)
        samples.append(RtSample(point, found.normals[i], found.weights[i], shots, state,
                                sum(1 for shot in shots if shot.state == "ok")))
    return RtMap(kind, found.nodes, found.triangles, samples, settings, tuple(results),
                 tuple(images), found.step, len(found.faces), _material_text(material),
                 time.monotonic() - started, found.volume_samples)


def check_points(part: Any, points: list[Point], settings: RtSettings,
                 faces: list[Any] | None = None) -> list[list[Shot]]:
    """Stav zadaných bodů v každé projekci (testy, hranice): řádek na projekci. ``faces`` =
    plochy oblasti pro kontrolu překryvu obrazů."""
    geo = PartGeometry(part)
    crossings = _faces_crossings(faces) if faces else None
    out = []
    for projection in settings.projections:
        setup = prepare(geo, settings, projection)
        raws = [_shoot(geo, setup, settings, point, crossings) for point in points]
        reference, _manual, usable, _why = _reference(setup, projection, raws)
        *_numbers, distance_text = _distances(setup, settings, raws, reference, usable)
        out.append([_finish(raw, settings, reference, usable, distance_text) for raw in raws])
    return out


def image_of(part: Any, settings: RtSettings, name: str) -> RtImage | None:
    """Náhled prozařované tloušťky jedné projekce (testy, CLI)."""
    geo = PartGeometry(part)
    return _image(geo, prepare(geo, settings, settings.projection(name)), settings)


def self_check(folder: Any) -> tuple[bool, str]:
    """Rychlá kontrola RT (self-test aplikace, i ve Windows): deska s otvorem prozářená kolmo –
    plech 20 mm šikmo k okraji o něco víc, otvor průhledný, projekce bez kolize."""
    from skodacad.document import Document
    from skodacad.rebuild import rebuild

    part = rebuild(Document.load(Path(folder) / "otvor.json")).part
    settings = RtSettings(projections=(Projection("P1", (0.0, 0.0, 20.0), (0.0, 0.0, 1.0),
                                                  500.0, "free", 0.0, 520.0, 20.0),))
    [[plate, hole]] = check_points(part, [(50.0, 0.0, 20.0), (0.0, 0.0, 10.0)], settings)
    geo = PartGeometry(part)
    setup = prepare(geo, settings, settings.projections[0])
    expected = 20 / math.cos(math.atan(52 / 520))
    got = (setup.ok, plate.state, round(plate.thickness or 0, 3), hole.thickness)
    if (setup.ok and plate.state == "ok" and abs((plate.thickness or 0) - expected) < 1e-3
            and hole.thickness is not None and hole.thickness < 1e-6):
        return True, (f"RT projekce: OK (deska s otvorem – plech {_dec(plate.thickness, 2)} mm, "
                      "otvor průhledný, bez kolize)")
    return False, f"RT projekce: {got} (čekáno plech {expected:.3f} mm, otvor 0 mm)"
