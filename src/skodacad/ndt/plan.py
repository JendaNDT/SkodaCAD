"""Plán dráhy UT sondy (etapa 10, docs/ndt/18-navrh-etapa-10.md).

**Průchod** = rovinná kontaktní plocha + stálý směr paprsku + úhel β + počet odrazů (totéž co
varianta etapy 09). Plán ho projede **řádky** tam a zpět (cik-cak) s roztečí r:

1. mřížka průchodu po rozteči zarovnaná se směrem paprsku (oba vzory řádků ji sdílejí),
2. **dosah** – z uzlu se spustí paprsek bez přiložení; uzly, odkud žádné rameno nevede blízko
   cíle, odpadnou (síto jako 2. kolo etapy 09, ale proti bodům skutečného cíle – obalový
   kvádr V svaru je mnohem větší než svar),
3. **přiložení** jen v okolí uzlů v dosahu; platný uzel = přiloženo a mimo zakázané zóny,
4. **úseky** = souvislé běhy platných uzlů řádku oříznuté na dosah; konec u překážky se
   dohledá půlením na 0,5 mm,
5. **kontrola po 1 mm** (``check_step``) celé jízdy po povrchu; neplatná poloha úsek rozdělí,
6. pořadí cik-cak; přesun po povrchu jen přes platné polohy, jinak **přestavení** s kontrolou
   **nájezdu** (tělo sondy prodloužené o výšku nájezdu nesmí narazit do dílu ani do zóny),
7. **pokrytí** stávajícím výpočtem (etapa 06 / 07B) v režimu ``plan``: polohy plánu po
   rozteči a mezipolohy jen v pásech úseků (``coverage.PlanRegion``) – řádky se počítají
   jako spojitě projetý pás šířky rozteče, stejně jako pojezd po ploše.

Jen geometrie: plán nepopisuje zjistitelnost vad, čas, rychlost ani techniku pohybu.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from skodacad.ndt import UT_ACCESS, UT_DISCLAIMER
from skodacad.ndt.access import _segment_reaches, target_box, union
from skodacad.ndt.coverage import (
    PERCENT_NOTE,
    CoverageMap,
    PlanRegion,
    auto_tolerance,
    compute,
)
from skodacad.ndt.devices import (
    STATES as PLACEMENT_STATES,
)
from skodacad.ndt.devices import (
    Aim,
    DeviceError,
    Placement,
    Probe,
    aim,
    place,
    reuse_placements,
)
from skodacad.ndt.geometry import OVERLAP_TOL, GeometryError, PartGeometry, Point
from skodacad.ndt.ut import BeamError, trace_beam
from skodacad.ndt.volume_coverage import VolumeCoverageMap, compute_volume

ALGORITHM = "ndt-ut-plan-drahy 1"
PLAN_NOTE = ("Plán dráhy popisuje jen geometrii pohybu sondy a geometrické pokrytí, "
             "nikoli zjistitelnost vad.")
PATTERNS = {"toward": "k cíli a zpět", "along": "podél", "manual": "ručně"}
PATTERN_CHOICES = {"auto": "automaticky", "toward": PATTERNS["toward"],
                   "along": PATTERNS["along"]}
STEP_KINDS = {"scan": "úsek", "slide": "přesun po povrchu", "air": "přestavení"}
STEP_COLORS = {"scan": (0.10, 0.60, 0.20), "slide": (0.45, 0.45, 0.45),
               "air": (0.95, 0.55, 0.10)}  # kresba ve 3D (okno) – legenda panelu NDT
ZONE_COLOR = (0.85, 0.20, 0.15)
DEFAULT_ROW_STEP = 5.0
DEFAULT_APPROACH = 20.0
DEFAULT_CHECK_STEP = 1.0
REFINE_MM = 0.5  # přesnost dohledání konce úseku u překážky
EDGE_MM = 1.0  # boční rezerva pod 1 mm = poloha „na hraně“
LENGTH_TIE = 0.05  # vzory s délkou do 5 % od sebe rozhodne počet řádků
MAX_PASSES = 10
MAX_SEGMENTS = 2_000  # úseků v jednom průchodu
MAX_NODES = 20_000  # uzlů mřížky jednoho průchodu
MAX_CHECKS = 20_000  # kontrolních přiložení (po 1 mm) v celém plánu
_DECIMALS = 6  # souřadnice plánu: přesnost 1 nm, uložené = počítané
# Odhad času (změřeno 18. 10. 2026 v cloudu, celý V svar 100 mm): uzel mřížky ~0,3 ms
# (paprsek) až 30 ms (přiložení), pokrytí jednoho průchodu 33–125 s.
_NODE_SECONDS = (0.003, 0.05)
_PASS_SECONDS = (20.0, 180.0)

Progress = Callable[[str, int, int], None]


class PlanError(ValueError):
    """Plán nejde sestavit, načíst nebo spočítat (česky, s radou co změnit)."""


# --- pomocné výpočty -----------------------------------------------------------------------


def _num(value: float, digits: int = 1) -> str:
    value = round(float(value), digits)
    return f"{0.0 if value == 0 else value:g}".replace(".", ",")


def _plural(n: int, one: str, few: str, many: str) -> str:
    return f"{n} {one if n == 1 else few if 2 <= n <= 4 else many}"


def _add(a: Point, b: Point, k: float = 1.0) -> Point:
    return (a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k)


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a: Point) -> Point | None:
    length = math.sqrt(_dot(a, a))
    return None if length < 1e-12 else (a[0] / length, a[1] / length, a[2] / length)


def _r(point: Any) -> Point:
    """Souřadnice plánu zaokrouhlené na 1 nm – uložený plán dá při přepočtu tytéž polohy."""
    return tuple(round(float(v), _DECIMALS) + 0.0 for v in point)


def _clean(value: float) -> float | int:
    value = round(float(value), _DECIMALS) + 0.0
    return int(value) if value.is_integer() else value


def _xyz(text: str, value: Any) -> Point:
    if (not isinstance(value, list | tuple) or len(value) != 3
            or any(isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v)
                   for v in value)):
        raise PlanError(f"{text} musí být tři čísla [x, y, z] v mm.")
    return tuple(float(v) for v in value)


def _number(value: Any, text: str, low: float, high: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, int | float)
            or not math.isfinite(value) or not low <= value <= high):
        raise PlanError(f"{text} musí být číslo {_num(low, 3)}–{_num(high, 3)}.")
    return float(value)


def _overlap(a: Any, b: Any) -> float | None:
    """Objem průniku dvou těles; None = průnik nejde spočítat (bere se jako kolize)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    common = BRepAlgoAPI_Common(a, b)
    if not common.IsDone():  # OCCT 8: chyby hlásí jen IsDone
        return None
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(common.Shape(), props)
    return abs(props.Mass())


# --- zakázané zóny ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Zone:
    """Zakázaná zóna: kvádr v souřadnicích dílu, do kterého sonda nesmí zasáhnout žádnou
    částí těla (štítek, upínka, poškozený povrch …)."""

    name: str
    low: Point
    high: Point

    @classmethod
    def from_dict(cls, data: Any, index: int = 1) -> Zone:
        where = f"Zakázaná zóna {index}"
        if not isinstance(data, dict):
            raise PlanError(f'{where} musí být objekt {{"name", "min", "max"}}.')
        unknown = sorted(set(data) - {"name", "min", "max"})
        if unknown:
            raise PlanError(f"{where}: neznámá položka „{unknown[0]}“ (umím: name, min, max).")
        name = data.get("name", "")
        if not isinstance(name, str) or len(name) > 100:
            raise PlanError(f"{where}: název musí být text (nejvýš 100 znaků).")
        low = _xyz(f"{where}: „min“", data.get("min"))
        high = _xyz(f"{where}: „max“", data.get("max"))
        if any(h - lo < 1e-6 for lo, h in zip(low, high, strict=True)):
            raise PlanError(f"{where}: „max“ musí být v každé ose větší než „min“.")
        return cls(name, low, high)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "min": [_clean(v) for v in self.low],
                "max": [_clean(v) for v in self.high]}

    def label(self, index: int = 0) -> str:
        return f"„{self.name}“" if self.name else f"zóna {index + 1}"

    def solid(self) -> Any:
        from build123d import Align, Box, Pos

        size = [h - lo for lo, h in zip(self.low, self.high, strict=True)]
        return Pos(*self.low) * Box(*size, align=(Align.MIN, Align.MIN, Align.MIN))


def zone_hit(body: Any, zones: tuple[Zone, ...] | list[Zone],
             solids: dict[int, Any] | None = None) -> Zone | None:
    """První zóna, do které těleso (tělo sondy) zasahuje; nespočítaný průnik = zasahuje.
    ``solids`` = paměť těles zón podle pořadí (plánovač ji drží celou dobu výpočtu)."""
    if not zones or body is None:
        return None
    solids = {} if solids is None else solids
    box = body.bounding_box()
    for i, zone in enumerate(zones):
        if (box.min.X > zone.high[0] or box.max.X < zone.low[0]
                or box.min.Y > zone.high[1] or box.max.Y < zone.low[1]
                or box.min.Z > zone.high[2] or box.max.Z < zone.low[2]):
            continue
        solid = solids.get(i)
        if solid is None:
            solid = solids[i] = zone.solid()
        volume = _overlap(body.wrapped, solid.wrapped)
        if volume is None or volume > OVERLAP_TOL:
            return zone
    return None


def probe_fingerprint(probe: Probe) -> str:
    """Otisk rozměrů a mezí sondy (16 znaků) – plán na nich závisí; úhel a odrazy nese každý
    průchod sám."""
    values = [probe.kind, *(round(float(getattr(probe, key)), 6) for key in (
        "diameter", "length", "width", "height", "front", "max_gap", "reserve"))]
    text = json.dumps(values, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def zones_from(data: Any) -> tuple[Zone, ...]:
    """Zóny studie (``zones``) z JSON; chybějící = žádné."""
    if data is None:
        return ()
    if not isinstance(data, list):
        raise PlanError("Zakázané zóny („zones“) musí být seznam kvádrů.")
    return tuple(Zone.from_dict(item, i) for i, item in enumerate(data, start=1))


# --- plán (ukládá se do studie, formát 18) -----------------------------------------------


@dataclass(frozen=True)
class PlanSegment:
    """Úsek řádku: sonda jede po povrchu od ``start`` do ``end`` se stálým směrem paprsku."""

    start: Point
    end: Point

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)

    def reversed(self) -> PlanSegment:
        return PlanSegment(self.end, self.start)


@dataclass(frozen=True)
class PlanPass:
    """Průchod: plocha (odkaz významem – bod a směr), směr paprsku, úhel β, odrazy, úseky."""

    face: dict[str, Any]
    angle_deg: float
    beta: float  # 0 = přímá sonda
    bounces: int
    pattern: str  # toward / along / manual
    segments: tuple[PlanSegment, ...]

    @property
    def label(self) -> str:
        beam = "přímá sonda" if self.beta == 0 else f"β {_num(self.beta)}°"
        return (f"plocha ({'; '.join(_num(v) for v in self.face['at'])}), směr "
                f"{_num(self.angle_deg, 0)}°, {beam}, odrazy {self.bounces}")

    def to_dict(self) -> dict[str, Any]:
        return {"face": dict(self.face), "angle_deg": _clean(self.angle_deg),
                "beta": _clean(self.beta), "bounces": self.bounces, "pattern": self.pattern,
                "segments": [{"start": [_clean(v) for v in s.start],
                              "end": [_clean(v) for v in s.end]} for s in self.segments]}

    @classmethod
    def from_dict(cls, data: Any, index: int = 1) -> PlanPass:
        where = f"Plán dráhy, průchod {index}"
        if not isinstance(data, dict):
            raise PlanError(f"{where} musí být objekt.")
        known = {"face", "angle_deg", "beta", "bounces", "pattern", "segments"}
        unknown = sorted(set(data) - known)
        if unknown:
            raise PlanError(f"{where}: neznámá položka „{unknown[0]}“ (umím: "
                            f"{', '.join(sorted(known))}).")
        face = data.get("face")
        if not isinstance(face, dict) or "at" not in face or "normal" not in face:
            raise PlanError(f'{where}: plocha („face“) musí mít „at“ a „normal“.')
        _xyz(f"{where}: bod plochy „at“", face["at"])
        if _unit(_xyz(f"{where}: směr plochy „normal“", face["normal"])) is None:
            raise PlanError(f"{where}: směr plochy „normal“ nesmí být nulový.")
        angle = _number(data.get("angle_deg"), f"{where}: směr paprsku [°]", -360, 720) % 360.0
        beta = _number(data.get("beta", 0), f"{where}: úhel β [°]", 0, 85)
        if 0 < beta < 1:
            raise PlanError(f"{where}: úhel β musí být 0 (přímá sonda) nebo 1–85°.")
        bounces = data.get("bounces", 0)
        if isinstance(bounces, bool) or not isinstance(bounces, int) or not 0 <= bounces <= 10:
            raise PlanError(f"{where}: počet odrazů musí být celé číslo 0–10.")
        pattern = data.get("pattern", "manual")
        if pattern not in PATTERNS:
            raise PlanError(f"{where}: vzor řádků musí být {', '.join(PATTERNS)}.")
        raw = data.get("segments")
        if not isinstance(raw, list) or len(raw) > MAX_SEGMENTS:
            raise PlanError(f"{where}: úseky („segments“) musí být seznam (nejvýš "
                            f"{MAX_SEGMENTS}).")
        segments = []
        for k, item in enumerate(raw, start=1):
            if not isinstance(item, dict) or set(item) != {"start", "end"}:
                raise PlanError(f'{where}, úsek {k}: musí mít jen „start“ a „end“.')
            segments.append(PlanSegment(_r(_xyz(f"{where}, úsek {k}: „start“", item["start"])),
                                        _r(_xyz(f"{where}, úsek {k}: „end“", item["end"]))))
        return cls(dict(face), angle, beta, bounces, pattern, tuple(segments))


@dataclass(frozen=True)
class Plan:
    """Plán dráhy studie (``plan``). Otisky (``part``, ``target``, ``probe``) doplní
    ``ModelSession`` – podle nich je plán platný, nebo zastaralý. Sám se nikdy neposune."""

    passes: tuple[PlanPass, ...]
    pattern: str = "auto"  # nastavení při sestavení (auto / toward / along)
    row_step_mm: float = DEFAULT_ROW_STEP
    approach_mm: float = DEFAULT_APPROACH
    check_step_mm: float = DEFAULT_CHECK_STEP
    part: str = ""
    target: str = ""
    probe: str = ""
    edited: bool = False

    @property
    def segment_count(self) -> int:
        return sum(len(p.segments) for p in self.passes)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"pattern": self.pattern, "row_step_mm": _clean(self.row_step_mm),
                                "approach_mm": _clean(self.approach_mm),
                                "check_step_mm": _clean(self.check_step_mm),
                                "passes": [p.to_dict() for p in self.passes]}
        for key in ("part", "target", "probe"):
            if getattr(self, key):
                data[key] = getattr(self, key)
        data["edited"] = self.edited
        return data

    @classmethod
    def from_dict(cls, data: Any) -> Plan:
        if not isinstance(data, dict):
            raise PlanError('Plán dráhy („plan“) musí být objekt {"passes": […], …}.')
        known = {"pattern", "row_step_mm", "approach_mm", "check_step_mm", "passes", "part",
                 "target", "probe", "edited"}
        unknown = sorted(set(data) - known)
        if unknown:
            raise PlanError(f"Plán dráhy: neznámá položka „{unknown[0]}“ (umím: "
                            f"{', '.join(sorted(known))}).")
        pattern = data.get("pattern", "auto")
        if pattern not in PATTERN_CHOICES:
            raise PlanError(f"Plán dráhy: vzor musí být {', '.join(PATTERN_CHOICES)}.")
        row = _number(data.get("row_step_mm", DEFAULT_ROW_STEP), "Plán dráhy: rozteč [mm]",
                      0.5, 100)
        approach = _number(data.get("approach_mm", DEFAULT_APPROACH),
                           "Plán dráhy: výška nájezdu [mm]", 0, 500)
        check = _number(data.get("check_step_mm", DEFAULT_CHECK_STEP),
                        "Plán dráhy: kontrolní krok [mm]", 0.1, 10)
        raw = data.get("passes")
        if not isinstance(raw, list) or len(raw) > MAX_PASSES:
            raise PlanError(f"Plán dráhy: průchody („passes“) musí být seznam (nejvýš "
                            f"{MAX_PASSES}).")
        texts = {}
        for key in ("part", "target", "probe"):
            value = data.get(key, "")
            if not isinstance(value, str) or len(value) > 64:
                raise PlanError(f"Plán dráhy: otisk „{key}“ musí být text.")
            texts[key] = value
        edited = data.get("edited", False)
        if not isinstance(edited, bool):
            raise PlanError("Plán dráhy: „edited“ musí být true nebo false.")
        return cls(tuple(PlanPass.from_dict(p, i) for i, p in enumerate(raw, start=1)),
                   pattern, row, approach, check, edited=edited, **texts)


# --- nastavení a vstupy ------------------------------------------------------------------


@dataclass(frozen=True)
class PlanOptions:
    """Nastavení sestavení a výpočtu plánu (mm, °)."""

    pattern: str = "auto"
    row_step_mm: float = DEFAULT_ROW_STEP
    approach_mm: float = DEFAULT_APPROACH
    check_step_mm: float = DEFAULT_CHECK_STEP
    target_step_mm: float | None = None  # objem: None = doporučený (07B); plochy: rozteč
    tolerance_mm: float | None = None  # None = automatická jako pojezd po ploše
    spread_deg: float = 0.0
    compare: bool = False  # srovnání s pojezdem po celých plochách průchodů
    robustness: bool = False  # pokrytí po posunu všech řádků o ± půl rozteče

    def checked(self) -> PlanOptions:
        if self.pattern not in PATTERN_CHOICES:
            raise PlanError(f"Vzor řádků musí být {', '.join(PATTERN_CHOICES)}.")
        row = _number(self.row_step_mm, "Rozteč řádků [mm]", 0.5, 100)
        check = _number(self.check_step_mm, "Kontrolní krok [mm]", 0.1, 10)
        if check > row + 1e-9:
            raise PlanError("Kontrolní krok nesmí být větší než rozteč řádků.")
        target = (None if self.target_step_mm is None
                  else _number(self.target_step_mm, "Krok cíle [mm]", 0.1, 1000))
        tolerance = (None if self.tolerance_mm is None
                     else _number(self.tolerance_mm, "Tolerance zachycení [mm]", 0, 1000))
        return replace(self, row_step_mm=row, check_step_mm=check, target_step_mm=target,
                       tolerance_mm=tolerance,
                       approach_mm=_number(self.approach_mm, "Výška nájezdu [mm]", 0, 500),
                       spread_deg=_number(self.spread_deg, "Rozevření [°]", 0, 45))

    @classmethod
    def for_plan(cls, plan: Plan, **changes: Any) -> PlanOptions:
        """Nastavení, se kterým se uložený plán ověří a spočítá znovu."""
        return cls(pattern=plan.pattern, row_step_mm=plan.row_step_mm,
                   approach_mm=plan.approach_mm, check_step_mm=plan.check_step_mm, **changes)


@dataclass(frozen=True)
class PassSpec:
    """Co naplánovat: rovinná plocha (tvar dílu), kotva mřížky na ní (přiložená sonda nebo
    nejlepší poloha varianty), směr paprsku, úhel β a odrazy."""

    face: Any
    point: Point
    angle_deg: float
    beta: float
    bounces: int


# --- výsledky ----------------------------------------------------------------------------


@dataclass(frozen=True)
class PatternDraft:
    """Vzor řádků průchodu spočítaný z mřížky (před kontrolou po 1 mm)."""

    pass_index: int
    pattern: str
    rows: int
    segments: int
    lifts: int
    length_mm: float
    chosen: bool = False

    @property
    def text(self) -> str:
        return (f"{PATTERNS[self.pattern]}: {_plural(self.rows, 'řádek', 'řádky', 'řádků')}, "
                f"{_plural(self.lifts, 'přestavení', 'přestavení', 'přestavení')}, "
                f"asi {_num(self.length_mm, 0)} mm")


@dataclass(frozen=True)
class PlanStep:
    """Krok jízdy: ``scan`` (úsek), ``slide`` (přesun po povrchu), ``air`` (přestavení –
    zvednout, přenést, spustit)."""

    kind: str
    pass_index: int
    segment: int  # úsek průchodu (u přesunů úsek, ke kterému vede); −1 = mezi průchody
    start: Point
    end: Point
    normals: tuple[Point, Point]  # směr ven z plochy na začátku a na konci (kresba nájezdu)

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)


@dataclass(frozen=True)
class PlanPosition:
    """Poloha tabulky (po rozteči podél úseků) s výsledkem kontroly."""

    index: int
    pass_index: int
    segment: int
    point: Point
    state: str  # stav přiložení (devices.STATES) nebo „zone“
    clearance: float | None
    margin: float | None  # boční rezerva [mm]; None = nezměřeno
    margin_capped: bool  # rezerva je aspoň polovina rozteče (dál se neměří)
    note: str

    @property
    def ok(self) -> bool:
        return self.state == "ok"

    @property
    def on_edge(self) -> bool:
        return self.margin is not None and self.margin < EDGE_MM - 1e-9


@dataclass(frozen=True)
class PlanCheck:
    """Ověření plánu: kroky jízdy, tabulka poloh, problémy a hodnocení (bez pokrytí)."""

    steps: tuple[PlanStep, ...]
    positions: tuple[PlanPosition, ...]
    problems: tuple[str, ...]  # proč plán neplatí (česky); prázdné = platný
    checked: int  # kolikrát se sonda kontrolně přiložila (po kontrolním kroku)
    lifts: int  # přestavení uvnitř průchodů
    pass_changes: int
    angle_changes: int
    min_clearance: float | None
    min_margin: float | None
    margin_capped: bool
    edge_positions: int
    seconds: float

    @property
    def valid(self) -> bool:
        return not self.problems and bool(self.positions)

    def length(self, kind: str) -> float:
        return sum(s.length for s in self.steps if s.kind == kind)

    def lines(self) -> list[str]:
        lines = [f"Úseky {_num(self.length('scan'), 0)} mm, přesuny po povrchu "
                 f"{_num(self.length('slide'), 0)} mm, přestavení "
                 f"{_plural(self.lifts, 'krát', 'krát', 'krát')} (vzduchem "
                 f"{_num(self.length('air'), 0)} mm); "
                 f"{_plural(len(self.positions), 'poloha', 'polohy', 'poloh')} v tabulce."]
        if self.pass_changes:
            lines.append(f"Změna průchodu (jiná plocha nebo směr): {self.pass_changes}×"
                         + (f", z toho jiný úhel (jiná sonda) {self.angle_changes}×."
                            if self.angle_changes else "."))
        robust = []
        if self.min_margin is not None:
            value = (f"aspoň {_num(self.min_margin)} mm" if self.margin_capped
                     else f"{_num(self.min_margin)} mm")
            robust.append(f"nejmenší boční rezerva {value}")
        if self.edge_positions:
            robust.append(f"{_plural(self.edge_positions, 'poloha', 'polohy', 'poloh')} na "
                          f"hraně (rezerva pod {_num(EDGE_MM)} mm)")
        robust.append("nejmenší volno k překážce " + (
            f"{_num(self.min_clearance)} mm" if self.min_clearance is not None
            else "– nad rovinou přiložení žádná překážka"))
        lines.append("Robustnost: " + ", ".join(robust) + ".")
        return lines


@dataclass(frozen=True)
class PlanCoverage:
    """Pokrytí plánu (sjednocení průchodů vzorek po vzorku) a srovnání."""

    coverage: CoverageMap | VolumeCoverageMap
    first_position: tuple[int | None, ...]  # vzorek → index polohy plánu s prvním zásahem
    face_coverage: CoverageMap | VolumeCoverageMap | None
    robustness: tuple[float, float] | None  # pokryto po posunu o ± půl rozteče [%]
    seconds: float

    @property
    def covered(self) -> float:
        return self.coverage.percent("covered")

    def until(self, index: int) -> list[str]:
        """Stavy vzorků po projetí polohy ``index`` (přehrávání): co ještě nikdo nezasáhl,
        je zatím nepokryté."""
        states = []
        for state, first in zip(self.coverage.states, self.first_position, strict=True):
            if state in ("covered", "uncertain") and (first is None or first > index):
                states.append("uncovered")
            else:
                states.append(state)
        return states


    def segment_hits(self, check: PlanCheck) -> dict[tuple[int, int], int]:
        """Úsek (průchod, úsek) → kolik vzorků cíle z něj paprsek zasáhl jako první. Úsek
        s nulou nic nepokrývá sám (každý jeho zásah má dřívější úsek) – jde ho smazat."""
        counts = {(p.pass_index, p.segment): 0 for p in check.positions}
        for first in self.first_position:
            if first is not None:
                position = check.positions[first]
                counts[(position.pass_index, position.segment)] += 1
        return counts


@dataclass(frozen=True)
class PlanEstimate:
    nodes: int
    passes: int
    seconds: tuple[float, float]
    ok: bool
    text: str


@dataclass(frozen=True)
class PlanResult:
    plan: Plan
    check: PlanCheck
    coverage: PlanCoverage | None
    drafts: tuple[PatternDraft, ...]
    dropped: tuple[str, ...]  # vynechané úseky a průchody při sestavení (česky)
    assumptions: dict[str, Any]
    seconds: float

    def summary(self) -> list[str]:
        a = self.assumptions
        lines = [f"{UT_ACCESS} – plán dráhy sondy", UT_DISCLAIMER, PLAN_NOTE, PERCENT_NOTE,
                 strip_note(self.plan.row_step_mm), *a.get("device_lines", [])]
        lines.append("Plán platí." if self.check.valid else
                     "Plán NEPLATÍ: " + " ".join(self.check.problems[:5])
                     + (f" … a dalších {len(self.check.problems) - 5}."
                        if len(self.check.problems) > 5 else ""))
        for k, plan_pass in enumerate(self.plan.passes, start=1):
            lines.append(f"Průchod {k}: {plan_pass.label}; vzor {PATTERNS[plan_pass.pattern]}, "
                         f"{_plural(len(plan_pass.segments), 'úsek', 'úseky', 'úseků')}.")
        for draft in self.drafts:
            lines.append(f"– průchod {draft.pass_index + 1}, {draft.text}"
                         + (" (zvolen)" if draft.chosen else ""))
        lines += self.check.lines()
        if self.coverage is not None:
            cov = self.coverage
            lines.append(f"Geometricky pokryto {_num(cov.covered, 2)} %, nelze spolehlivě "
                         f"vyhodnotit {_num(cov.coverage.percent('uncertain'), 2)} %.")
            if cov.face_coverage is not None:
                lines.append(f"Srovnání: pojezd po celých plochách průchodů "
                             f"{_num(cov.face_coverage.percent('covered'), 2)} %.")
            if cov.robustness is not None:
                low, high = cov.robustness
                lines.append(f"Odolnost: po posunu řádků o ± {_num(self.plan.row_step_mm / 2)} "
                             f"mm pokryto {_num(low, 2)}–{_num(high, 2)} %.")
        else:
            lines.append("Pokrytí plánu zatím není spočítané.")
        useless = self.useless_segments()
        if useless:
            lines.append(f"Úseky bez přínosu (žádný vzorek cíle nezasáhnou jako první): "
                         f"{len(useless)} – jde je smazat, pokrytí se tím nezmenší.")
        lines += list(self.dropped)
        lines.append(f"Rozteč {_num(self.plan.row_step_mm)} mm, kontrolní krok "
                     f"{_num(self.plan.check_step_mm)} mm, výška nájezdu "
                     f"{_num(self.plan.approach_mm)} mm"
                     + (f", zakázané zóny {len(a.get('zones', []))}" if a.get("zones") else "")
                     + f"; výpočet {self.seconds:.1f} s; algoritmus {ALGORITHM}.")
        return lines

    def useless_segments(self) -> list[tuple[int, int]]:
        """Úseky, ze kterých paprsek žádný vzorek nezasáhne jako první (jen se spočítaným
        pokrytím)."""
        if self.coverage is None:
            return []
        return [key for key, count in self.coverage.segment_hits(self.check).items()
                if not count]

    def write_csv(self, path: str | Path) -> Path:
        path = Path(path)

        def cz(value: float | None, digits: int = 3) -> str:
            return "" if value is None else f"{value:.{digits}f}".replace(".", ",")

        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            for text in [*self.summary(), json.dumps(self.assumptions, ensure_ascii=False,
                                                     sort_keys=True, default=str)]:
                writer.writerow([text])
            writer.writerow([])
            writer.writerow(["krok", "druh", "průchod", "úsek", "od x [mm]", "od y [mm]",
                             "od z [mm]", "do x [mm]", "do y [mm]", "do z [mm]", "délka [mm]"])
            for k, step in enumerate(self.check.steps, start=1):
                writer.writerow([k, STEP_KINDS[step.kind], step.pass_index + 1,
                                 step.segment + 1 if step.segment >= 0 else "",
                                 *(cz(v) for v in step.start), *(cz(v) for v in step.end),
                                 cz(step.length)])
            writer.writerow([])
            writer.writerow(["poloha", "průchod", "úsek", "x [mm]", "y [mm]", "z [mm]",
                             "směr [°]", "stav", "volno [mm]", "boční rezerva [mm]",
                             "první zásahy vzorků", "poznámka"])
            firsts = Counter(self.coverage.first_position) if self.coverage else Counter()
            for p in self.check.positions:
                plan_pass = self.plan.passes[p.pass_index]
                margin = cz(p.margin, 2)
                if p.margin_capped and margin:
                    margin = "≥ " + margin
                writer.writerow([p.index + 1, p.pass_index + 1, p.segment + 1,
                                 *(cz(v) for v in p.point), cz(plan_pass.angle_deg, 1),
                                 _state_label(p.state), cz(p.clearance, 2), margin,
                                 firsts.get(p.index, 0) if self.coverage else "", p.note])
        return path


def strip_note(row_step: float) -> str:
    return (f"Řádky s roztečí {_num(row_step)} mm se počítají jako spojitě projetý pás šířky "
            "rozteče – stejný předpoklad jako pojezd po ploše.")


def _state_label(state: str) -> str:
    return "v zakázané zóně" if state == "zone" else PLACEMENT_STATES.get(state, state)


# --- plánovač ----------------------------------------------------------------------------


@dataclass
class _Frame:
    """Souřadný systém průchodu: počátek na ploše, směr paprsku ``ex``, napříč ``ey``,
    normála ven ``n`` (na rovině všude stejné)."""

    origin: Point
    ex: Point
    ey: Point
    n: Point

    def axes(self, pattern: str) -> tuple[Point, Point]:
        """(podél řádku, napříč) podle vzoru."""
        return (self.ey, self.ex) if pattern == "along" else (self.ex, self.ey)


@dataclass
class _Lattice:
    frame: _Frame
    step: float
    inside: dict[tuple[int, int], Point]
    reach: dict[tuple[int, int], bool] = field(default_factory=dict)
    valid: dict[tuple[int, int], bool] = field(default_factory=dict)


class Planner:
    """Plán dráhy jedné sondy k jednomu cíli (plochy, body nebo objem) na dílu ``geo``."""

    def __init__(self, geo: PartGeometry, probe: Probe, *, faces: list[Any] | None = None,
                 points: list[Point] | None = None, volume: dict[str, Any] | None = None,
                 zones: tuple[Zone, ...] | list[Zone] = (),
                 options: PlanOptions | None = None,
                 device_lines: list[str] | None = None,
                 assumptions: dict[str, Any] | None = None) -> None:
        if sum(x is not None and x != [] for x in (faces, points, volume)) != 1:
            raise PlanError("Plán potřebuje právě jeden cíl: plochy, body, nebo objem.")
        self.geo, self.probe = geo, probe
        self.faces, self.points, self.volume = faces or None, points or None, volume
        self.zones = tuple(zones)
        self.options = (options or PlanOptions()).checked()
        self.device_lines = list(device_lines or [])
        self.extra = dict(assumptions or {})
        self._memo: dict = {}
        self._zone_solids: dict[int, Any] = {}
        self._approach_memo: dict = {}
        try:
            (self._low, self._high), _, _ = target_box(geo, faces=self.faces,
                                                       points=self.points, volume=self.volume)
        except ValueError as exc:
            raise PlanError(str(exc)) from None
        step = self.options.row_step_mm
        tolerance = (self.options.tolerance_mm if self.options.tolerance_mm is not None
                     else auto_tolerance("plan", step, self.options.target_step_mm or 0.0))
        self._margin = tolerance + step  # síto dosahu jako 2. kolo etapy 09
        self._slope = math.tan(math.radians(self.options.spread_deg))
        self._checks = 0
        self._samples: Any = None  # body cíle pro síto dosahu (numpy, až při prvním použití)

    # --- sonda, přiložení, zóny, nájezd ----------------------------------------------

    def _config(self, beta: float, bounces: int) -> Probe:
        if self.probe.kind == "straight":
            return replace(self.probe, bounces=bounces)
        return replace(self.probe, beam_angle=beta, bounces=bounces)

    def _frame(self, face: Any, point: Point, angle: float) -> _Frame:
        try:
            aimed = aim(self.geo, self.probe, point, angle, face)
        except (DeviceError, GeometryError) as exc:
            raise PlanError(f"Na plochu průchodu nejde sondu zamířit: {exc}") from None
        return _Frame(aimed.origin, aimed.x_dir, aimed.y_dir, aimed.z_dir)

    def _zone_of(self, body: Any) -> Zone | None:
        return zone_hit(body, self.zones, self._zone_solids)

    def allowed(self, placed: Placement) -> bool:
        """Přiložení mimo zakázané zóny (pro ``coverage.PlanRegion``)."""
        return self._zone_of(placed.body) is None

    def _place(self, point: Point, angle: float, face: Any) -> tuple[str, Placement | None]:
        """Stav polohy: stav přiložení, „zone“ (v zakázané zóně) nebo „error“."""
        self._checks += 1
        try:
            placed = place(self.geo, self.probe, _r(point), angle=angle, face=face)
        except (DeviceError, GeometryError):
            return "error", None
        if placed.ok and self._zone_of(placed.body) is not None:
            return "zone", placed
        return placed.state, placed

    def _valid(self, point: Point, angle: float, face: Any) -> bool:
        return self._place(point, angle, face)[0] == "ok"

    def _approach(self, point: Point, frame: _Frame) -> bool:
        """Jde sondu v bodě spustit kolmo k ploše (a zase zvednout)? Tělo prodloužené
        nahoru o výšku nájezdu nesmí narazit do dílu ani do zóny."""
        height = self.options.approach_mm
        if height <= 0:
            return True
        key = (_r(point), frame.ex, frame.n)
        if key in self._approach_memo:
            return self._approach_memo[key]
        from build123d import Location, Plane, Vector

        tall = replace(self.probe, height=min(1000.0, self.probe.height + height))
        plane = Plane(origin=Vector(*_r(point)), x_dir=Vector(*frame.ex),
                      z_dir=Vector(*frame.n))
        body = Location(plane) * tall.body()
        volume = _overlap(self.geo.part.wrapped, body.wrapped)
        free = volume is not None and volume <= OVERLAP_TOL and self._zone_of(body) is None
        self._approach_memo[key] = free
        return free

    def _target_points(self) -> Any:
        """Body cíle pro síto dosahu: u ploch těžiště sítě povrchu, u objemu body mřížky
        uvnitř skutečného cíle (krok cíle), u bodů body. Rameno, které projde cílem, má
        k některému bodu blíž než polovinu úhlopříčky kroku – rezerva síta je větší."""
        if self._samples is not None:
            return self._samples
        import numpy as np

        step = self.options.target_step_mm or self.options.row_step_mm
        if self.points is not None:
            points = [tuple(float(v) for v in p) for p in self.points]
        elif self.faces is not None:
            from skodacad.thickness_map import _Surface

            points = list(_Surface(self.geo.part, step, self.faces).centers)
        else:
            from skodacad.ndt.welds import resolve_target

            shape = resolve_target(self.geo.part, self.volume).shape
            inner = PartGeometry(shape)
            counts = [max(1, math.ceil((h - lo) / step)) for lo, h in zip(self._low, self._high,
                                                                          strict=True)]
            points = []
            for i in range(counts[0] + 1):
                for j in range(counts[1] + 1):
                    for k in range(counts[2] + 1):
                        point = tuple(min(lo + n * step, h) for lo, h, n in zip(
                            self._low, self._high, (i, j, k), strict=True))
                        if inner.classify(point) != "outside":
                            points.append(point)
        self._samples = np.array(points or [self._low, self._high], dtype=float)
        return self._samples

    def _reaches(self, point: Point, frame: _Frame, config: Probe) -> bool:
        import numpy as np

        aimed = Aim(config, _r(point), frame.ex, frame.ey, frame.n)
        try:
            beam = trace_beam(self.geo, aimed)
        except (BeamError, GeometryError):
            return False
        samples = None
        for leg in beam.legs:
            margin = self._margin + leg.cumulative_length * self._slope
            if not _segment_reaches(leg.start, leg.direction, leg.length, self._low,
                                    self._high, margin):
                continue  # obalový kvádr cíle je daleko – levné síto napřed
            if samples is None:
                samples = self._target_points()
            offset = samples - np.array(leg.start)
            direction = np.array(leg.direction)
            along = np.clip(offset @ direction, 0.0, leg.length)
            gap = offset - np.outer(along, direction)
            if (np.einsum("ij,ij->i", gap, gap) <= margin * margin).any():
                return True
        return False

    # --- mřížka průchodu -------------------------------------------------------------

    def _lattice(self, spec: PassSpec) -> _Lattice:
        from OCP.BRepClass import BRepClass_FaceClassifier
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_IN, TopAbs_ON

        frame = self._frame(spec.face, spec.point, spec.angle_deg)
        step = self.options.row_step_mm
        box = spec.face.bounding_box()
        corners = [(x, y, z) for x in (box.min.X, box.max.X) for y in (box.min.Y, box.max.Y)
                   for z in (box.min.Z, box.max.Z)]
        us = [_dot(_sub(c, frame.origin), frame.ex) for c in corners]
        vs = [_dot(_sub(c, frame.origin), frame.ey) for c in corners]
        i0, i1 = math.ceil(min(us) / step - 1e-9), math.floor(max(us) / step + 1e-9)
        j0, j1 = math.ceil(min(vs) / step - 1e-9), math.floor(max(vs) / step + 1e-9)
        if (i1 - i0 + 1) * (j1 - j0 + 1) > MAX_NODES:
            raise PlanError(f"Plocha průchodu by měla přes {MAX_NODES} poloh mřížky – zvětši "
                            "rozteč řádků.")
        classifier = BRepClass_FaceClassifier()
        inside: dict[tuple[int, int], Point] = {}
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                point = _r(_add(_add(frame.origin, frame.ex, i * step), frame.ey, j * step))
                classifier.Perform(spec.face.wrapped, gp_Pnt(*point), 1e-7)
                if classifier.State() in (TopAbs_IN, TopAbs_ON):
                    inside[(i, j)] = point
        return _Lattice(frame, step, inside)

    def estimate(self, specs: list[PassSpec]) -> PlanEstimate:
        """Velikost plánu ještě před sestavením (bez přiložení a paprsků)."""
        if not specs:
            return PlanEstimate(0, 0, (0, 0), False, "Plán nemá žádný průchod.")
        nodes = 0
        try:
            for spec in specs:
                nodes += len(self._lattice(spec).inside)
        except PlanError as exc:
            return PlanEstimate(nodes, len(specs), (0, 0), False, str(exc))
        factor = 1 + self.options.compare + 2 * self.options.robustness
        low = nodes * _NODE_SECONDS[0] + len(specs) * _PASS_SECONDS[0] * factor
        high = nodes * _NODE_SECONDS[1] + len(specs) * _PASS_SECONDS[1] * factor
        text = (f"Odhad: {_plural(len(specs), 'průchod', 'průchody', 'průchodů')}, mřížka "
                f"{nodes} poloh, asi {_minutes(low)}–{_minutes(high)}.")
        return PlanEstimate(nodes, len(specs), (low, high), nodes > 0, text)

    # --- sestavení -------------------------------------------------------------------

    def _classify(self, spec: PassSpec, lattice: _Lattice) -> None:
        config = self._config(spec.beta, spec.bounces)
        for key, point in lattice.inside.items():
            lattice.reach[key] = self._reaches(point, lattice.frame, config)
        reaching = [k for k, r in lattice.reach.items() if r]
        if not reaching:
            return
        i0, i1 = min(k[0] for k in reaching) - 1, max(k[0] for k in reaching) + 1
        j0, j1 = min(k[1] for k in reaching) - 1, max(k[1] for k in reaching) + 1
        for key, point in lattice.inside.items():
            if i0 <= key[0] <= i1 and j0 <= key[1] <= j1:
                lattice.valid[key] = self._valid(point, spec.angle_deg, spec.face)

    @staticmethod
    def _runs(lattice: _Lattice, pattern: str) -> dict[int, list[tuple[int, int]]]:
        """Řádky → úseky (od, do) v indexech mřížky: souvislé běhy platných uzlů oříznuté
        na uzly v dosahu."""
        rows: dict[int, list[int]] = {}
        for (i, j), ok in lattice.valid.items():
            if ok:
                row, along = (i, j) if pattern == "along" else (j, i)
                rows.setdefault(row, []).append(along)
        result: dict[int, list[tuple[int, int]]] = {}
        for row in sorted(rows):
            indices = sorted(rows[row])
            runs: list[list[int]] = []
            for index in indices:
                if runs and index == runs[-1][-1] + 1:
                    runs[-1].append(index)
                else:
                    runs.append([index])
            for run in runs:
                hits = [a for a in run if lattice.reach.get(
                    (row, a) if pattern == "along" else (a, row), False)]
                if hits:
                    result.setdefault(row, []).append((min(hits), max(hits)))
        return result

    def _draft(self, index: int, lattice: _Lattice, pattern: str) -> PatternDraft:
        runs = self._runs(lattice, pattern)
        order = _boustrophedon(runs)
        step = lattice.step
        lifts, length = 0, 0.0
        for k, (row, a, b) in enumerate(order):
            length += abs(b - a) * step
            if k == 0:
                continue
            prow, pa, pb = order[k - 1]
            end, start = pb, a  # konec předchozího a začátek dalšího ve směru jízdy
            if abs(row - prow) == 1 and all(
                    lattice.valid.get((row, x) if pattern == "along" else (x, row), False)
                    for x in range(min(end, start), max(end, start) + 1)):
                length += step + abs(start - end) * step
            else:
                lifts += 1
        return PatternDraft(index, pattern, len(runs), len(order), lifts, length)

    def _refine(self, inner: Point, outer: Point, angle: float, face: Any) -> Point:
        """Půlením mezi platnou ``inner`` a neplatnou ``outer`` polohou najde nejvzdálenější
        platnou polohu (přesnost REFINE_MM)."""
        lo, hi = inner, outer
        while math.dist(lo, hi) > REFINE_MM + 1e-9:
            mid = _r(tuple((a + b) / 2 for a, b in zip(lo, hi, strict=True)))
            if self._valid(mid, angle, face):
                lo = mid
            else:
                hi = mid
        return _r(lo)

    def _segments(self, spec: PassSpec, lattice: _Lattice, pattern: str) -> list[PlanSegment]:
        """Úseky průchodu v pořadí jízdy (cik-cak); konce u překážky dohledané."""
        along, across = lattice.frame.axes(pattern)
        step = lattice.step
        runs = self._runs(lattice, pattern)

        def node(row: int, a: int) -> tuple[int, int]:
            return (row, a) if pattern == "along" else (a, row)

        def point(row: int, a: float) -> Point:
            origin = lattice.frame.origin
            return _r(_add(_add(origin, along, a * step), across, row * step))

        segments = []
        for row, a, b in _boustrophedon(runs):
            low, high = min(a, b), max(a, b)
            start, end = point(row, low), point(row, high)
            # Konec u překážky (sousední uzel neplatný nebo mimo plochu) se dohledá; konec
            # oříznutý dosahem (soused platný, ale nemíří k cíli) zůstane na uzlu.
            if not lattice.valid.get(node(row, low - 1), False):
                start = self._refine(start, point(row, low - 1), spec.angle_deg, spec.face)
            if not lattice.valid.get(node(row, high + 1), False):
                end = self._refine(end, point(row, high + 1), spec.angle_deg, spec.face)
            segment = PlanSegment(start, end)
            segments.append(segment if a <= b else segment.reversed())
        return segments

    def build(self, specs: list[PassSpec], progress: Progress | None = None
              ) -> tuple[Plan, list[Any], tuple[PatternDraft, ...], tuple[str, ...]]:
        """Sestaví plán (úseky v pořadí jízdy) a plochy jeho průchodů. Úseky, které
        neprojdou kontrolou po kontrolním kroku, rozdělí; na které nejde najet, vynechá."""
        if not specs:
            raise PlanError("Plán nemá žádný průchod – přilož sondu nebo vyber variantu.")
        if len(specs) > MAX_PASSES:
            raise PlanError(f"Plán může mít nejvýš {MAX_PASSES} průchodů.")
        from skodacad.measure import face_reference

        passes: list[PlanPass] = []
        drafts: list[PatternDraft] = []
        dropped: list[str] = []
        faces: list[Any] = []
        with reuse_placements(self.geo, self._memo):
            for index, spec in enumerate(specs):
                if progress:
                    progress("Mřížka, dosah a přiložení", index, len(specs))
                lattice = self._lattice(spec)
                self._classify(spec, lattice)
                if not any(lattice.reach.values()):
                    dropped.append(f"Průchod {index + 1} vynechán: paprsek z této plochy "
                                   "k cíli nemíří.")
                    continue
                options = [self._draft(index, lattice, p) for p in ("toward", "along")]
                pattern = (_choose(options) if self.options.pattern == "auto"
                           else self.options.pattern)
                options = [replace(d, chosen=d.pattern == pattern) for d in options]
                drafts += options
                segments = self._segments(spec, lattice, pattern)
                if not segments:
                    reasons = Counter(self._place(p, spec.angle_deg, spec.face)[0]
                                      for k, p in lattice.inside.items()
                                      if lattice.reach.get(k))
                    detail = ", ".join(f"{_state_label(s)} {n}" for s, n in reasons.most_common())
                    dropped.append(f"Průchod {index + 1} vynechán: sonda se nevejde v žádné "
                                   f"poloze, odkud paprsek míří k cíli ({detail}).")
                    continue
                reference = face_reference(spec.face, lattice.frame.origin)["face"]
                reference["at"] = [_clean(v) for v in lattice.frame.origin]
                passes.append(PlanPass(reference, spec.angle_deg % 360.0, float(spec.beta),
                                       int(spec.bounces), pattern, tuple(segments)))
                faces.append(spec.face)
            plan = Plan(tuple(passes), self.options.pattern, self.options.row_step_mm,
                        self.options.approach_mm, self.options.check_step_mm)
            self._budget(plan)
            # Kontrola po 1 mm a nájezd: neplatné kousky úseků se vyříznou, úseky bez
            # nájezdu vynechají. Opakuje se, dokud se plán mění (každé kolo něco ubere).
            for _ in range(2 * MAX_SEGMENTS):
                if progress:
                    progress("Kontrola dráhy po kontrolním kroku", 0, 1)
                fixed, fixed_faces, notes = self._repair(plan, faces)
                dropped += notes
                if fixed == plan:
                    break
                plan, faces = fixed, fixed_faces
        return plan, faces, tuple(drafts), tuple(dropped)

    def _budget(self, plan: Plan) -> None:
        """Ochrana proti hodinovému výpočtu: kontrolních přiložení po celé dráze."""
        step = plan.check_step_mm
        total = sum(math.ceil(s.length / step) + 1 for p in plan.passes for s in p.segments)
        if total > MAX_CHECKS:
            raise PlanError(f"Kontrola dráhy by potřebovala {total} přiložení (nejvýš "
                            f"{MAX_CHECKS}) – zvětši rozteč nebo kontrolní krok, nebo zmenši "
                            "počet průchodů.")

    def _repair(self, plan: Plan, faces: list[Any]) -> tuple[Plan, list[Any], list[str]]:
        """Jedno kolo opravy sestaveného plánu: vyřízne neplatné kousky úseků (kontrola po
        kontrolním kroku), vynechá úseky, na které nejde najet, a průchody bez úseku."""
        notes: list[str] = []
        passes, kept = [], []
        for p_index, (plan_pass, face) in enumerate(zip(plan.passes, faces, strict=True)):
            frame = self._frame(face, tuple(plan_pass.face["at"]), plan_pass.angle_deg)
            config = self._config(plan_pass.beta, plan_pass.bounces)
            segments: list[PlanSegment] = []
            for segment in plan_pass.segments:
                pieces = self._valid_pieces(segment, plan_pass, face, frame, config)
                segments += pieces
            # Nájezd: úsek, na který nejde najet shora ani dojet po povrchu, se vynechá.
            _, problems, _ = self._walk(replace(plan_pass, segments=tuple(segments)),
                                        p_index, face, frame)
            blocked = {int(p.split(":", 1)[0]) for p in problems if p[:1].isdigit()}
            for s_index in sorted(blocked, reverse=True):
                notes.append(f"Průchod {p_index + 1}: úsek od "
                             f"({'; '.join(_num(v) for v in segments[s_index].start)}) "
                             "vynechán – sonda na něj nejde spustit shora ani dojet po "
                             "povrchu.")
                del segments[s_index]
            if segments:
                passes.append(replace(plan_pass, segments=tuple(segments)))
                kept.append(face)
            else:
                notes.append(f"Průchod {p_index + 1} vynechán: žádný úsek neprošel kontrolou.")
        return replace(plan, passes=tuple(passes)), kept, notes

    def _checks_along(self, start: Point, end: Point) -> list[Point]:
        """Kontrolní polohy po kontrolním kroku od ``start`` do ``end`` (oba konce)."""
        length = math.dist(start, end)
        step = self.options.check_step_mm
        count = math.ceil(length / step - 1e-9)
        if count <= 0:
            return [start]
        direction = _unit(_sub(end, start))
        points = [_r(_add(start, direction, k * step)) for k in range(count)]
        return [*points, end]

    def _valid_pieces(self, segment: PlanSegment, plan_pass: PlanPass, face: Any,
                      frame: _Frame, config: Probe) -> list[PlanSegment]:
        checks = self._checks_along(segment.start, segment.end)
        flags = [self._valid(p, plan_pass.angle_deg, face) for p in checks]
        if all(flags):
            return [segment]
        pieces, current = [], []
        for point, ok in zip(checks, flags, strict=True):
            if ok:
                current.append(point)
            elif current:
                pieces.append(current)
                current = []
        if current:
            pieces.append(current)
        return [PlanSegment(piece[0], piece[-1]) for piece in pieces
                if any(self._reaches(p, frame, config) for p in piece)]

    # --- ověření plánu ---------------------------------------------------------------

    def _walk(self, plan_pass: PlanPass, p_index: int, face: Any, frame: _Frame
              ) -> tuple[list[PlanStep], list[str], int]:
        """Kroky jízdy průchodu (úseky, přesuny, přestavení) s nájezdem. Problémy začínají
        číslem úseku (0…) a dvojtečkou – na ten úsek nejde sondu spustit."""
        steps: list[PlanStep] = []
        problems: list[str] = []
        lifts = 0
        angle = plan_pass.angle_deg
        n = frame.n
        segments = plan_pass.segments
        trail: list[Point] = []  # projetá dráha po povrchu od posledního spuštění sondy
        for s_index, segment in enumerate(segments):
            if trail:  # přesun po povrchu, jen když projde celý
                slide = self._checks_along(trail[-1], segment.start)[1:-1]
                if all(self._valid(p, angle, face) for p in slide):
                    if math.dist(trail[-1], segment.start) > 1e-9:
                        steps.append(PlanStep("slide", p_index, s_index, trail[-1],
                                              segment.start, (n, n)))
                    trail.append(segment.start)
                else:
                    back = self._retreat(trail, frame, p_index, s_index - 1)
                    steps += back
                    lifts += 1
                    steps.append(PlanStep("air", p_index, s_index,
                                          back[-1].end if back else trail[-1], segment.start,
                                          (n, n)))
                    trail = []
            if not trail:
                entry = self._entry_point(segment, frame)
                if entry is None:
                    problems.append(f"{s_index}: na úsek {s_index + 1} nejde sondu spustit "
                                    "shora ani dojet po povrchu.")
                    entry = segment.start
                elif entry != segment.start:  # spustit dál a pod převis dojet po povrchu
                    if steps and steps[-1].kind == "air":
                        steps[-1] = replace(steps[-1], end=entry)
                    steps.append(PlanStep("slide", p_index, s_index, entry, segment.start,
                                          (n, n)))
                trail = [entry] if entry != segment.start else []
                trail.append(segment.start)
            steps.append(PlanStep("scan", p_index, s_index, segment.start, segment.end, (n, n)))
            trail.append(segment.end)
        if trail:  # konec průchodu: zvednout (případně se vrátit, kde to jde)
            steps += self._retreat(trail, frame, p_index, len(segments) - 1)
        return steps, problems, lifts

    def _entry_point(self, segment: PlanSegment, frame: _Frame) -> Point | None:
        """Kde sondu na úsek spustit: na začátku, jinak na nejbližší poloze úseku (pod
        převis pak sonda dojede po povrchu); None = nikde."""
        for point in self._checks_along(segment.start, segment.end):
            if self._approach(point, frame):
                return point
        return None

    def _retreat(self, trail: list[Point], frame: _Frame, p_index: int, s_index: int
                 ) -> list[PlanStep]:
        """Kde sondu zvednout: tam, kde stojí, jinak se vrátí po projeté dráze na nejbližší
        místo, kde to jde (pod převisem). Přesuny zpět jsou po již ověřené dráze."""
        n = frame.n
        if self._approach(trail[-1], frame):
            return []
        steps: list[PlanStep] = []
        for a, b in zip(reversed(trail[1:]), reversed(trail[:-1]), strict=True):
            for point in self._checks_along(a, b)[1:]:
                if self._approach(point, frame):
                    steps.append(PlanStep("slide", p_index, s_index, a, point, (n, n)))
                    return steps
            steps.append(PlanStep("slide", p_index, s_index, a, b, (n, n)))
        return steps

    def check(self, plan: Plan, faces: list[Any], progress: Progress | None = None,
              margins: bool = True) -> PlanCheck:
        """Ověří plán po kontrolním kroku: každá poloha úseků a přesunů po povrchu musí
        projít přiložením (a být mimo zóny), na každý úsek po přestavení musí jít najet.
        Tabulka poloh je po rozteči; boční rezerva napříč řádku (``margins``)."""
        started = time.monotonic()
        if len(faces) != len(plan.passes):
            raise PlanError("Plán dráhy a plochy průchodů si neodpovídají.")
        self._budget(plan)
        self._checks = 0
        steps: list[PlanStep] = []
        positions: list[PlanPosition] = []
        problems: list[str] = []
        lifts = pass_changes = angle_changes = 0
        clearances: list[float] = []
        margins_found: list[tuple[float, bool]] = []
        step = plan.row_step_mm
        with reuse_placements(self.geo, self._memo):
            for p_index, (plan_pass, face) in enumerate(zip(plan.passes, faces, strict=True)):
                if progress:
                    progress("Kontrola dráhy", p_index, len(plan.passes))
                frame = self._frame(face, tuple(plan_pass.face["at"]), plan_pass.angle_deg)
                if p_index:
                    pass_changes += 1
                    previous = plan.passes[p_index - 1]
                    angle_changes += abs(previous.beta - plan_pass.beta) > 1e-9
                angle = plan_pass.angle_deg
                for s_index, segment in enumerate(plan_pass.segments):
                    where = f"Průchod {p_index + 1}, úsek {s_index + 1}"
                    for point in self._checks_along(segment.start, segment.end):
                        state, placed = self._place(point, angle, face)
                        if state != "ok":
                            problems.append(f"{where}: poloha ({'; '.join(_num(v) for v in point)})"
                                            f" – {_state_label(state)}.")
                            break
                        if placed.clearance is not None:
                            clearances.append(placed.clearance)
                    along = _unit(_sub(segment.end, segment.start)) or frame.axes(
                        plan_pass.pattern)[0]
                    across = _unit(_cross(frame.n, along)) or frame.ey
                    table = _spaced(segment.start, segment.end, step)
                    for k, point in enumerate(table):  # polohy tabulky = kontrolní polohy
                        state, placed = self._place(point, angle, face)
                        note = ("začátek úseku" if k == 0 else
                                "konec úseku" if k == len(table) - 1 else "")
                        margin, capped = (None, False)
                        if margins and state == "ok":
                            margin, capped = self._side_margin(point, across, angle, face, step)
                            margins_found.append((margin, capped))
                            if margin < EDGE_MM - 1e-9:
                                note = ", ".join(x for x in (note, "na hraně") if x)
                        positions.append(PlanPosition(
                            len(positions), p_index, s_index, point, state,
                            placed.clearance if placed is not None else None, margin, capped,
                            note))
                walk, walk_problems, walk_lifts = self._walk(plan_pass, p_index, face, frame)
                lifts += walk_lifts
                if steps and walk:  # přestavení na další průchod (jiná plocha nebo směr)
                    steps.append(PlanStep("air", p_index, -1, steps[-1].end, walk[0].start,
                                          (steps[-1].normals[1], frame.n)))
                steps += walk
                for problem in walk_problems:
                    head, _, text = problem.partition(": ")
                    problems.append(f"Průchod {p_index + 1}: {text}" if head.isdigit()
                                    else problem)
        if not positions:
            problems.append("Plán nemá žádný úsek.")
        low = min(margins_found, key=lambda m: m[0]) if margins_found else None
        return PlanCheck(tuple(steps), tuple(positions), tuple(dict.fromkeys(problems)),
                         self._checks, lifts, pass_changes, angle_changes,
                         min(clearances) if clearances else None,
                         low[0] if low else None,
                         bool(low and all(c for _, c in margins_found)),
                         sum(p.on_edge for p in positions), time.monotonic() - started)

    def _side_margin(self, point: Point, across: Point, angle: float, face: Any,
                     step: float) -> tuple[float, bool]:
        """Boční rezerva: o kolik smí sonda uhnout napříč řádku (na obě strany), než narazí,
        přesáhne nebo vjede do zóny. Měří se do poloviny rozteče (víc = „aspoň“)."""
        half = step / 2
        first = min(EDGE_MM, half)
        sides = []
        for sign in (1.0, -1.0):
            if not self._valid(_add(point, across, sign * first), angle, face):
                lo, hi = 0.0, first
            elif half > first + 1e-9 and not self._valid(_add(point, across, sign * half),
                                                         angle, face):
                lo, hi = first, half
            else:
                sides.append((half, True))
                continue
            while hi - lo > REFINE_MM / 2 + 1e-9:
                mid = (lo + hi) / 2
                if self._valid(_add(point, across, sign * mid), angle, face):
                    lo = mid
                else:
                    hi = mid
            sides.append((lo, False))
        margin = min(s[0] for s in sides)
        return margin, all(c for _, c in sides)

    # --- pokrytí ---------------------------------------------------------------------

    def _region(self, plan: Plan, check: PlanCheck, p_index: int, shift: float = 0.0,
                frame: _Frame | None = None) -> tuple[list[Point], PlanRegion]:
        """Polohy průchodu (tabulka, jen platné) a pásy jeho úseků; ``shift`` posune vše
        napříč řádků (odolnost)."""
        plan_pass = plan.passes[p_index]
        half = plan.row_step_mm / 2
        strips = []
        acrosses = {}
        for s_index, segment in enumerate(plan_pass.segments):
            along = _unit(_sub(segment.end, segment.start)) or frame.axes(plan_pass.pattern)[0]
            across = _unit(_cross(frame.n, along)) or frame.ey
            acrosses[s_index] = across
            strips.append((_add(segment.start, across, shift), along, segment.length, across,
                           half))
        positions = [_r(_add(p.point, acrosses[p.segment], shift)) for p in check.positions
                     if p.pass_index == p_index and (p.ok or shift)]
        return positions, PlanRegion(tuple(strips), self.allowed if self.zones else None)

    def _pass_coverage(self, plan: Plan, check: PlanCheck, p_index: int, face: Any,
                       mode: str = "plan", shift: float = 0.0
                       ) -> CoverageMap | VolumeCoverageMap | None:
        plan_pass = plan.passes[p_index]
        frame = self._frame(face, tuple(plan_pass.face["at"]), plan_pass.angle_deg)
        positions, region = self._region(plan, check, p_index, shift, frame)
        if not positions:
            return None
        config = self._config(plan_pass.beta, plan_pass.bounces)
        seed = None
        for point in positions:
            try:
                candidate = place(self.geo, config, point, angle=plan_pass.angle_deg, face=face)
            except (DeviceError, GeometryError):
                continue
            if candidate.ok:
                seed = candidate
                break
        if seed is None:
            return None
        options = dict(mode=mode, scan_step=plan.row_step_mm, angle_deg=plan_pass.angle_deg,
                       tolerance_mm=self.options.tolerance_mm,
                       spread_deg=self.options.spread_deg)
        if mode == "plan":
            options.update(positions=positions, region=region)
        try:
            if self.volume is not None:
                return compute_volume(self.geo, seed, target=self.volume,
                                      target_step=self.options.target_step_mm, **options)
            return compute(self.geo, seed, faces=self.faces, points=self.points,
                           target_step=self.options.target_step_mm or plan.row_step_mm,
                           **options)
        except PlanError:
            raise
        except Exception as exc:  # noqa: BLE001 – česká chyba místo pádu
            raise PlanError(f"Pokrytí průchodu {p_index + 1} nejde spočítat: {exc}") from None

    def _union(self, maps: list[Any], labels: list[str]) -> Any:
        maps = [m for m in maps if m is not None]
        return union(maps, labels) if maps else None

    def coverage(self, plan: Plan, check: PlanCheck, faces: list[Any],
                 progress: Progress | None = None) -> PlanCoverage:
        """Pokrytí plánu stávajícím výpočtem: polohy tabulky v pořadí jízdy, mezipolohy jen
        v pásech úseků; průchody se sjednotí vzorek po vzorku."""
        started = time.monotonic()
        if not check.positions:
            raise PlanError("Plán nemá žádnou polohu – není z čeho počítat pokrytí.")
        labels = [f"průchod {k + 1}" for k in range(len(plan.passes))]
        runs = [("plan", 0.0)]
        if self.options.compare:
            runs.append(("face", 0.0))
        if self.options.robustness:
            runs += [("plan", plan.row_step_mm / 2), ("plan", -plan.row_step_mm / 2)]
        results: dict[tuple[str, float], Any] = {}
        total = len(runs) * len(plan.passes)
        done = 0
        with reuse_placements(self.geo, self._memo):
            for mode, shift in runs:
                maps = []
                for p_index, face in enumerate(faces):
                    if progress:
                        progress("Pokrytí plánu" if mode == "plan" and not shift else
                                 "Srovnání s celou plochou" if mode == "face" else
                                 "Odolnost (posun řádků)", done, total)
                    maps.append(self._pass_coverage(plan, check, p_index, face, mode, shift))
                    done += 1
                results[(mode, shift)] = self._union(maps, labels)
        merged = results[("plan", 0.0)]
        if merged is None:
            raise PlanError("Z žádné polohy plánu nejde sondu přiložit – pokrytí je nulové.")
        robustness = None
        if self.options.robustness:
            values = [m.percent("covered") if m is not None else 0.0
                      for key, m in results.items() if key[0] == "plan" and key[1]]
            robustness = (min(values), max(values))
        merged.assumptions.update(plan_algorithm=ALGORITHM, strip_note=strip_note(
            plan.row_step_mm), zones=[z.to_dict() for z in self.zones])
        return PlanCoverage(merged, _first_positions(merged, plan, check),
                            results.get(("face", 0.0)), robustness,
                            time.monotonic() - started)

    def run(self, specs: list[PassSpec], progress: Progress | None = None) -> PlanResult:
        """Sestavení, ověření a pokrytí najednou (příkazová řádka, pomocný proces, testy)."""
        started = time.monotonic()
        plan, faces, drafts, dropped = self.build(specs, progress)
        return self.evaluate(plan, faces, progress, drafts, dropped, started)

    def evaluate(self, plan: Plan, faces: list[Any], progress: Progress | None = None,
                 drafts: tuple[PatternDraft, ...] = (), dropped: tuple[str, ...] = (),
                 started: float | None = None, coverage: bool = True) -> PlanResult:
        """Ověření (a pokrytí) hotového plánu – i uloženého nebo ručně upraveného."""
        started = time.monotonic() if started is None else started
        check = self.check(plan, faces, progress)
        covered = (self.coverage(plan, check, faces, progress)
                   if coverage and check.positions else None)
        assumptions = {"plan_algorithm": ALGORITHM, "row_step_mm": plan.row_step_mm,
                       "check_step_mm": plan.check_step_mm, "approach_mm": plan.approach_mm,
                       "pattern": plan.pattern, "target_step_mm": self.options.target_step_mm,
                       "tolerance_mm": self.options.tolerance_mm,
                       "spread_deg": self.options.spread_deg,
                       "reach_margin_mm": self._margin, "probe": self.probe.to_dict(),
                       "zones": [z.to_dict() for z in self.zones],
                       "target_box": [list(self._low), list(self._high)],
                       "strip_note": strip_note(plan.row_step_mm),
                       "device_lines": self.device_lines, **self.extra}
        return PlanResult(plan, check, covered, tuple(drafts), tuple(dropped), assumptions,
                          time.monotonic() - started)


# --- pomocné funkce plánu ----------------------------------------------------------------


def _boustrophedon(runs: dict[int, list[tuple[int, int]]]) -> list[tuple[int, int, int]]:
    """Řádky vzestupně, v každém druhém neprázdném řádku obráceně (cik-cak): (řádek, od, do)
    ve směru jízdy."""
    order = []
    for k, row in enumerate(sorted(runs)):
        segments = sorted(runs[row])
        if k % 2:
            order += [(row, b, a) for a, b in reversed(segments)]
        else:
            order += [(row, a, b) for a, b in segments]
    return order


def _choose(drafts: list[PatternDraft]) -> str:
    """Vzor s méně přestaveními, pak kratší (rozdíl nad 5 %), pak s méně řádky."""
    toward, along = drafts
    if toward.lifts != along.lifts:
        return "toward" if toward.lifts < along.lifts else "along"
    longest = max(toward.length_mm, along.length_mm, 1e-9)
    if abs(toward.length_mm - along.length_mm) > LENGTH_TIE * longest:
        return "toward" if toward.length_mm < along.length_mm else "along"
    return "along" if along.rows < toward.rows else "toward"


def _spaced(start: Point, end: Point, step: float) -> list[Point]:
    """Polohy tabulky po rozteči od začátku do konce úseku (konec vždy)."""
    length = math.dist(start, end)
    count = math.ceil(length / step - 1e-9)
    if count <= 0:
        return [start]
    direction = _unit(_sub(end, start))
    return [*(_r(_add(start, direction, k * step)) for k in range(count)), end]


def _first_positions(merged: Any, plan: Plan, check: PlanCheck) -> tuple[int | None, ...]:
    """Vzorek → index polohy plánu, ze které ho paprsek zasáhl poprvé (výpočet jde v pořadí
    jízdy). Zásah z mezipolohy se přičte nejbližší poloze tabulky téhož průchodu."""
    points = [p.point for p in check.positions]
    cache: dict[tuple, int] = {}
    result: list[int | None] = []
    for state, hit in zip(merged.states, merged.hits, strict=True):
        if state not in ("covered", "uncertain") or hit is None:
            result.append(None)
            continue
        key = tuple(round(v, 6) for v in hit.origin)
        if key not in cache:
            cache[key] = min(range(len(points)), key=lambda i: math.dist(points[i], hit.origin))
        result.append(cache[key])
    return tuple(result)


def _minutes(seconds: float) -> str:
    if seconds < 90:
        return f"{max(1, round(seconds))} s"
    return f"{_num(seconds / 60, 0)} min"
