"""PT – geometrická přístupnost povrchu pro kapilární zkoušku (etapa 11).

Závazné vymezení je v ``docs/ndt/20-vymezeni-pt.md``: jen geometrie – kam vede volná přímka
zvenku (nástřik, výhled), kam se vejde nástroj (kulička špičky a dřík) a jak široká je mezera
proti protější stěně. Žádná smáčivost, vzlínání, citlivost ani detekovatelnost vad. Návrh,
výchozí hodnoty a ručně spočítané výsledky jsou v ``docs/ndt/19-navrh-etapa-11.md``.

Plochy PT studie se rozdělí na trojúhelníky (síť mapy tloušťky). V těžišti každého se zkouší
pevná sada 65 směrů (kolmice + spirála rovnoměrně po polokouli, žádná náhoda); když kolmice
volná není, dohledá se nejmenší volný úhel půlením. O tom, že se nástroj vejde, rozhoduje
přesný průnik dříku s tělesem OCCT – paprsky jsou jen síto. Nejisté se nikdy nepočítá jako
přístupné.
"""

from __future__ import annotations

import csv
import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from skodacad.ndt import PT_DISCLAIMER, PT_MAP
from skodacad.ndt.geometry import OVERLAP_TOL, GeometryError, PartGeometry, Point, overlap
from skodacad.thickness_map import MapError, _Surface

ALGORITHM = "ndt-pt-pristupnost 1"
DIRECTIONS = 64  # spirála po polokouli; s kolmicí 65 směrů (otevřenost jen ze spirály)
RING = 16  # prstenec těsně u roviny plochy – úzký volný pruh podél stěny (štěrbina, otvor)
RING_DEG = 88.0
REFINE_DEG = 0.1  # přesnost dohledání nejmenšího volného úhlu [°]
TARGET_SAMPLES = 1500  # automatický krok sítě: zhruba tolik vzorků (1–2 min)
MAX_SAMPLES = 20_000
MIN_STEP = 0.2  # mm
_AREA_PER_STEP2 = 0.2  # první odhad: rovinná plocha po půlení má trojúhelník ≈ 0,2 · krok²
TOUCH = 1e-3  # mm – kulička nástroje se místa dotýká, menší průnik do dílu není kolize
SHANK = 0.98  # dřík je o 2 % užší než špička – přesný dotyk se stěnou by byl nejistý průnik
RIM = 0.9  # síto dříku: paprsky z 0,9 poloměru dříku
MAX_EXACT = 8  # nejvýš tolik přesných kontrol dříku na nástroj a vzorek
CLIMB_DEG = (22.5, 11.25, 5.625, 2.8125)  # natočení kolem kolmice při dohledání do stran
MAX_CLIMB = 12  # nejvýš tolik dohledání po poledníku při natáčení
MAX_EYE = 8  # nejvýš tolik směrů zkusí oko
EYE_STEPS = (1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.1, 0.05)  # podíly vzdálenosti oka
SECONDS_PER_SAMPLE = 0.08  # odhad doby (změřeno 19. 10. 2026 v cloudu: 20–95 ms na vzorek)

STATES = {"ok": "Přístupné", "limited": "Omezené", "blocked": "Nepřístupné",
          "uncertain": "Nelze spolehlivě vyhodnotit"}
COLORS = {"ok": (0.15, 0.70, 0.25), "limited": (0.95, 0.60, 0.10),
          "blocked": (0.85, 0.20, 0.15), "uncertain": (0.60, 0.60, 0.60)}
CHECKS = {"spray": "Nástřik", "tool": "Otření nástrojem", "view": "Prohlídka"}
GRADES = {"ok": "jde", "limited": "omezeně", "blocked": "nejde", "uncertain": "nejisté",
          "off": "nepočítá se"}
GRADE_COLORS = {**COLORS, "off": (0.80, 0.80, 0.80)}
CLEANING = {"wipe": "otřením (rozpouštědlový postup, v ISO 3452-1 metoda C)",
            "rinse": "oplachem (vodou omyvatelný postup, v ISO 3452-1 metoda A)"}
REASONS = {  # druh důvodu → popis v souhrnu
    "spray_blocked": "nástřik nejde", "spray_limited": "nástřik jen šikmo",
    "tool_blocked": "nástroj se nevejde", "tool_limited": "vejde se jen jemný nástroj",
    "view_blocked": "bez výhledu", "view_eye": "oko se nevejde do vzdálenosti prohlídky",
    "view_limited": "prohlídka jen šikmo nebo se zrcátkem",
    "gap": "mezera užší než hlavní nástroj", "slit": "úzká štěrbina",
    "deep": "hluboké nebo zakryté místo", "uncertain": "nejistý výpočet",
}
WARNINGS = ("gap", "slit", "deep")  # upozornění: zelenou mění na oranžovou, nikdy na červenou
CHOSEN = "zvoleno pro výpočet, ne z normy"
VIEW_SOURCE = "ASME BPVC V čl. 9 a BINDT CP25, příloha A"
PERCENT_NOTE = ("Procento vyjadřuje jen geometrický podíl plochy, nikoli pravděpodobnost "
                "nalezení vady.")
LIGHT_NOTE = "Osvětlení a UV-A pro prohlídku (ISO 3059) program nepočítá – ověř je na místě."
CORNER_NOTE = ("Ostré vnitřní rohy modelu jsou ideální; skutečný přechod má zaoblení, výsledek "
               "v úzkém pásu u rohu je proto přísnější než skutečnost.")
DIRECTIONS_NOTE = (f"Odhad z {DIRECTIONS + 1 + RING} pevných směrů (kolmice, spirála po "
                   f"polokouli a prstenec {RING} směrů {RING_DEG:g}° od kolmice): velmi úzký "
                   "volný kužel se může minout.")
SLIT_TEXT = ("přebytek penetrantu z ní nejde spolehlivě odstranit, hrozí falešná indikace "
             "(jen geometrické upozornění)")


class PtError(ValueError):
    """Mapa PT nejde spočítat nebo má chybné nastavení (zpráva je česky)."""


def _n(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _dec(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


# --- nastavení -------------------------------------------------------------------------------

_LIMITS = {  # klíč: (český popis, nejméně, nejvýš)
    "step_mm": ("Krok sítě [mm]", MIN_STEP, 100.0),
    "tool_mm": ("Hlavní nástroj – průměr [mm]", 0.5, 200.0),
    "fine_tool_mm": ("Jemný nástroj – průměr [mm]", 0.0, 200.0),
    "tool_length_mm": ("Délka dříku nástroje [mm]", 1.0, 2000.0),
    "spray_deg": ("Nástřik – nejvýš od kolmice [°]", 0.0, 89.0),
    "spray_limit_deg": ("Nástřik šikmo – nejvýš od kolmice [°]", 0.0, 89.9),
    "view_deg": ("Prohlídka – aspoň k povrchu [°]", 1.0, 90.0),
    "view_limit_deg": ("Prohlídka šikmo – aspoň k povrchu [°]", 0.1, 90.0),
    "view_distance_mm": ("Vzdálenost oka – nejvýš [mm]", 1.0, 10000.0),
    "eye_mm": ("Volný prostor pro oko – průměr [mm]", 0.0, 1000.0),
    "open_warning": ("Upozornit pod otevřeností [%]", 0.0, 100.0),
}


@dataclass(frozen=True)
class PtSettings:
    """Nastavení mapy PT uložené v PT studii (``pt``, formát 19). Chybějící = výchozí."""

    step_mm: float | None = None  # None = automaticky (asi TARGET_SAMPLES vzorků)
    cleaning: str = "wipe"  # "wipe" = otřením (kontrola nástroje), "rinse" = oplachem
    tool_mm: float = 10.0
    fine_tool_mm: float = 3.0  # 0 = bez jemného nástroje
    tool_length_mm: float = 100.0
    spray_deg: float = 60.0
    spray_limit_deg: float = 85.0
    view_deg: float = 30.0
    view_limit_deg: float = 5.0
    view_distance_mm: float = 600.0
    eye_mm: float = 50.0
    open_warning: float = 10.0

    def __post_init__(self) -> None:
        if self.cleaning not in CLEANING:
            raise PtError("Postup čištění musí být „wipe“ (otřením) nebo „rinse“ (oplachem).")
        for key, (label, low, high) in _LIMITS.items():
            value = getattr(self, key)
            if key == "step_mm" and value is None:
                continue
            if (isinstance(value, bool) or not isinstance(value, int | float)
                    or not math.isfinite(value) or not low <= value <= high):
                raise PtError(f"{label} musí být číslo {_n(low)}–{_n(high)}.")
        if 0 < self.fine_tool_mm < 0.1 or self.fine_tool_mm > self.tool_mm:
            raise PtError("Jemný nástroj musí být 0 (bez něj) nebo 0,1 mm až průměr hlavního "
                          "nástroje.")
        if self.spray_limit_deg < self.spray_deg:
            raise PtError("Nástřik šikmo musí povolit aspoň tak velký úhel od kolmice jako "
                          "běžný nástřik.")
        if self.view_limit_deg > self.view_deg:
            raise PtError("Prohlídka šikmo musí mít úhel k povrchu nejvýš stejný jako běžná "
                          "prohlídka.")

    @classmethod
    def from_dict(cls, data: Any) -> PtSettings:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise PtError("Nastavení PT („pt“) musí být objekt, např. {\"tool_mm\": 10}.")
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise PtError(f"Nastavení PT nezná {', '.join(unknown)} "
                          f"(zná {', '.join(sorted(known))}).")
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data["step_mm"] is None:
            del data["step_mm"]
        return data

    def lines(self) -> list[str]:
        """Předpoklady výpočtu česky (souhrn, CSV)."""
        lines = [f"Čištění a odstranění přebytku: {CLEANING[self.cleaning]}.",
                 f"Nástřik: jde do {_n(self.spray_deg)}° od kolmice, šikmo do "
                 f"{_n(self.spray_limit_deg)}° ({CHOSEN})."]
        if self.cleaning == "wipe":
            fine = (f", jemný Ø {_n(self.fine_tool_mm)} mm" if self.fine_tool_mm
                    else ", bez jemného nástroje")
            lines.append(f"Nástroje: hlavní Ø {_n(self.tool_mm)} mm{fine}, dřík "
                         f"{_n(self.tool_length_mm)} mm s libovolným sklonem ({CHOSEN}).")
        lines += [f"Prohlídka: aspoň {_n(self.view_deg)}° k povrchu (šikmo aspoň "
                  f"{_n(self.view_limit_deg)}°), oko do {_n(self.view_distance_mm)} mm "
                  f"({VIEW_SOURCE}); volný prostor pro oko Ø {_n(self.eye_mm)} mm ({CHOSEN}).",
                  f"Upozornění na hluboké místo pod otevřeností {_n(self.open_warning)} % "
                  f"({CHOSEN})."]
        return lines


# --- směry -----------------------------------------------------------------------------------


def _spiral(count: int) -> tuple[Point, ...]:
    """Směry rovnoměrně po polokouli (stejný podíl prostorového úhlu), osa z = kolmice."""
    golden = math.pi * (3 - math.sqrt(5))
    out = []
    for k in range(count):
        z = 1 - (k + 0.5) / count
        r = math.sqrt(max(0.0, 1 - z * z))
        out.append((r * math.cos(golden * k), r * math.sin(golden * k), z))
    return tuple(out)


SPIRAL = _spiral(DIRECTIONS)
_RING_Z = math.cos(math.radians(RING_DEG))
_RING_R = math.sin(math.radians(RING_DEG))
RING_DIRS = tuple((_RING_R * math.cos(2 * math.pi * k / RING),
                   _RING_R * math.sin(2 * math.pi * k / RING), _RING_Z) for k in range(RING))


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v: Point) -> Point | None:
    length = math.sqrt(_dot(v, v))
    return None if length < 1e-12 else (v[0] / length, v[1] / length, v[2] / length)


def _along(p: Point, d: Point, t: float) -> Point:
    return (p[0] + d[0] * t, p[1] + d[1] * t, p[2] + d[2] * t)


def _frame(normal: Point) -> tuple[Point, Point, Point]:
    """Dva kolmé směry v rovině kolmé na ``normal`` (pevná volba, bez náhody)."""
    helper = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
    t1 = _unit(_cross(normal, helper))
    return t1, _cross(normal, t1), normal


def _world(frame: tuple[Point, Point, Point], local: Point) -> Point:
    t1, t2, n = frame
    return tuple(local[0] * t1[i] + local[1] * t2[i] + local[2] * n[i] for i in range(3))


def _rotate(v: Point, axis: Point, angle: float) -> Point:
    """Otočení vektoru kolem jednotkové osy (Rodriguesův vzorec)."""
    c, s = math.cos(angle), math.sin(angle)
    k = _cross(axis, v)
    d = _dot(axis, v) * (1 - c)
    return tuple(v[i] * c + k[i] * s + axis[i] * d for i in range(3))


def _angle(direction: Point, normal: Point) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, _dot(direction, normal)))))


# --- výsledky --------------------------------------------------------------------------------


@dataclass(frozen=True)
class PtSample:
    """Jeden vzorek povrchu (těžiště trojúhelníku) a jeho tři kontroly."""

    point: Point
    normal: Point
    area: float  # mm²
    state: str  # STATES
    spray: str  # GRADES
    tool: str
    view: str
    spray_angle: float | None  # nejmenší volný úhel od kolmice (jistý paprsek) [°]
    view_angle: float | None  # úhel výhledu k povrchu, pod kterým se oko vejde [°]
    tool_mm: float | None  # průměr nástroje, který se vejde
    gap: float | None  # mezera po kolmici k protější stěně [mm]
    openness: float  # podíl volných směrů [%]
    reasons: tuple[tuple[str, str], ...]  # (druh, česká věta)

    def grade(self, check: str | None) -> str:
        return self.state if check is None else getattr(self, check)


@dataclass(frozen=True)
class PtMap:
    """Mapa geometrické přístupnosti PT (jen pohled, neukládá se)."""

    nodes: list[Point]
    triangles: list[tuple[int, int, int]]
    samples: list[PtSample]
    settings: PtSettings
    step_mm: float
    faces: int
    seconds: float

    @property
    def total_area(self) -> float:
        return sum(s.area for s in self.samples)

    def area(self, state: str, check: str | None = None) -> float:
        return sum(s.area for s in self.samples if s.grade(check) == state)

    def percent(self, state: str, check: str | None = None) -> float:
        total = self.total_area
        return 100 * self.area(state, check) / total if total else 0.0

    def mesh(self, check: str | None = None) -> tuple[list, list, list]:
        """Oddělené uzly každé plošky (barva celého trojúhelníku), ``check`` = jedna kontrola."""
        colors_of = COLORS if check is None else GRADE_COLORS
        nodes, triangles, colors = [], [], []
        for tri, sample in zip(self.triangles, self.samples, strict=True):
            start = len(nodes)
            nodes.extend(self.nodes[i] for i in tri)
            triangles.append((start, start + 1, start + 2))
            colors.extend([colors_of[sample.grade(check)]] * 3)
        return nodes, triangles, colors

    def nearest(self, point: Point) -> int | None:
        """Vzorek nejblíž bodu (klik do mapy)."""
        if not self.samples:
            return None
        return min(range(len(self.samples)),
                   key=lambda i: sum((a - b) ** 2 for a, b in zip(self.samples[i].point, point,
                                                                    strict=True)))

    def describe(self, index: int) -> list[str]:
        """Stav vzorku a důvody česky (panel po kliknutí do mapy)."""
        s = self.samples[index]
        lines = [f"{STATES[s.state]} – " + ", ".join(
            f"{label.lower()} {GRADES[s.grade(key)]}" for key, label in CHECKS.items())]
        lines += [text for _, text in s.reasons]
        extra = [f"otevřenost {_dec(s.openness)} %"]
        if s.gap is not None:
            extra.append(f"mezera {_dec(s.gap)} mm")
        lines.append("Místo " + "; ".join(_dec(v) for v in s.point) + " mm, "
                     + ", ".join(extra) + ".")
        return lines

    def reason_areas(self) -> list[tuple[str, float]]:
        """Druhy důvodů podle zasažené plochy (mm²), největší napřed."""
        areas: dict[str, float] = {}
        for s in self.samples:
            for kind in dict.fromkeys(k for k, _ in s.reasons):
                areas[kind] = areas.get(kind, 0.0) + s.area
        return sorted(areas.items(), key=lambda item: -item[1])

    def summary(self) -> list[str]:
        total = self.total_area
        lines = [PT_MAP, PT_DISCLAIMER, PERCENT_NOTE,
                 f"Plochy: {self.faces}, vzorků {len(self.samples)}, krok sítě "
                 f"{_n(round(self.step_mm, 2))} mm, celkem {_dec(total)} mm²."]
        for state, label in STATES.items():
            lines.append(f"{label}: {_dec(self.percent(state), 2)} % "
                         f"({_dec(self.area(state))} mm²).")
        for key, label in CHECKS.items():
            parts = [f"{GRADES[g]} {_dec(self.percent(g, key), 2)} %" for g in GRADES
                     if self.area(g, key) > 0]
            lines.append(f"{label}: {', '.join(parts)}.")
        reasons = self.reason_areas()
        if reasons:
            lines.append("Důvody: " + "; ".join(
                f"{REASONS[kind]} {_dec(100 * area / total)} %" for kind, area in reasons[:6])
                + ".")
        gaps = [s.gap for s in self.samples if s.gap is not None]
        if gaps:
            lines.append(f"Nejužší mezera {_dec(min(gaps), 2)} mm.")
        if self.samples:
            lowest = min(s.openness for s in self.samples)
            lines.append(f"Nejnižší otevřenost {_dec(lowest)} % směrů.")
        lines += [*self.settings.lines(), LIGHT_NOTE, CORNER_NOTE, DIRECTIONS_NOTE,
                  f"Výpočet {_dec(self.seconds)} s; algoritmus {ALGORITHM}."]
        return lines

    def assumptions(self) -> dict[str, Any]:
        return {"algorithm": ALGORITHM, "directions": DIRECTIONS + 1 + RING,
                "step_mm": self.step_mm, "refine_deg": REFINE_DEG, "shank_ratio": SHANK,
                **self.settings.to_dict()}

    def write_csv(self, path: str | Path) -> Path:
        path = Path(path)

        def cz(value: float | None) -> str:
            return "" if value is None else f"{value:.6f}".replace(".", ",")

        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            for text in (PT_MAP, PT_DISCLAIMER, PERCENT_NOTE, *self.settings.lines(),
                         LIGHT_NOTE, CORNER_NOTE, DIRECTIONS_NOTE,
                         json.dumps(self.assumptions(), ensure_ascii=False, sort_keys=True)):
                writer.writerow([text])
            writer.writerow(["x [mm]", "y [mm]", "z [mm]", "obsah [mm²]", "nx", "ny", "nz",
                             "stav", "nástřik", "otření", "prohlídka", "úhel nástřiku [°]",
                             "úhel výhledu [°]", "nástroj [mm]", "mezera [mm]",
                             "otevřenost [%]", "důvody"])
            for s in self.samples:
                writer.writerow([*(cz(v) for v in s.point), cz(s.area),
                                 *(cz(v) for v in s.normal), STATES[s.state],
                                 GRADES[s.spray], GRADES[s.tool], GRADES[s.view],
                                 cz(s.spray_angle), cz(s.view_angle), cz(s.tool_mm),
                                 cz(s.gap), cz(s.openness),
                                 " | ".join(text for _, text in s.reasons)])
        return path


# --- výpočet ---------------------------------------------------------------------------------


def auto_step(faces: list[Any]) -> float:
    """Krok sítě pro zhruba ``TARGET_SAMPLES`` vzorků na plochách studie."""
    area = sum(face.area for face in faces)
    return max(MIN_STEP, round(math.sqrt(area / (TARGET_SAMPLES * _AREA_PER_STEP2)), 1))


def study_faces(geo: PartGeometry, record: dict[str, Any]) -> list[Any]:
    """Plochy PT studie (odkazy významem); jiná metoda nebo cílový objem = česká chyba."""
    if record.get("method") != "PT":
        raise PtError("Mapa PT jde spočítat jen pro PT (kapilární) studii.")
    target = record.get("target") or {}
    if target.get("kind", "faces") != "faces":
        raise PtError("PT posuzuje povrch – vyber plochy (cílový objem ani svar PT nepočítá).")
    faces, problems = geo.faces_of(target)
    if problems:
        raise PtError(" ".join(problems))
    if not faces:
        raise PtError("PT studie nemá plochy – vyber plochy povrchu, který se má kontrolovat.")
    return faces


def _surface(part: Any, faces: list[Any], settings: PtSettings) -> _Surface:
    """Síť ploch studie; automatický krok se po prvním pokusu upraví podle skutečného počtu
    vzorků (síť je levná proti výpočtu)."""
    if not faces:
        raise PtError("PT studie nemá plochy – vyber plochy povrchu, který se má kontrolovat.")
    step = settings.step_mm or auto_step(faces)
    try:
        surface = _Surface(part, step, faces)
        for _ in range(3 if settings.step_mm is None else 0):
            count = len(surface.centers)
            if count <= 1.3 * TARGET_SAMPLES:
                break
            step = round(step * math.sqrt(count / TARGET_SAMPLES) + 0.05, 1)
            surface = _Surface(part, step, faces)
    except MapError as exc:
        raise PtError(str(exc)) from None
    if len(surface.centers) > MAX_SAMPLES:
        raise PtError(f"Mapa PT by měla {len(surface.centers)} vzorků (nejvýš {MAX_SAMPLES}) – "
                      f"zvol větší krok sítě (teď {_n(round(step, 2))} mm).")
    return surface


def estimate(part: Any, faces: list[Any], settings: PtSettings | None = None
             ) -> tuple[int, float, float]:
    """Odhad před spuštěním: (počet vzorků, krok sítě, doba v s)."""
    settings = settings or PtSettings()
    surface = _surface(part, faces, settings)
    count = len(surface.centers)
    return count, surface.step, count * SECONDS_PER_SAMPLE


def compute(part: Any, faces: list[Any], settings: PtSettings | None = None,
            progress: Callable[[int, int], None] | None = None) -> PtMap:
    """Mapa PT pro plochy ``faces`` dílu ``part``; ``progress(hotovo, celkem)`` průběžně."""
    settings = settings or PtSettings()
    started = time.monotonic()
    surface = _surface(part, faces, settings)
    try:
        sampler = Sampler(PartGeometry(part), settings)
    except GeometryError as exc:
        raise PtError(str(exc)) from None
    total = len(surface.centers)
    samples = []
    for i, (point, normal, area) in enumerate(zip(surface.centers, surface.normals,
                                                  surface.areas, strict=True)):
        samples.append(sampler.sample(point, normal, area))
        if progress is not None and (i % 10 == 9 or i + 1 == total):
            progress(i + 1, total)
    return PtMap(surface.nodes, surface.triangles, samples, settings, surface.step, len(faces),
                 time.monotonic() - started)


class Sampler:
    """Tři kontroly v jednom bodě povrchu (bod na ploše, normála ven z materiálu)."""

    def __init__(self, geo: PartGeometry, settings: PtSettings) -> None:
        self.geo = geo
        self.settings = settings
        self.shape = geo.part.wrapped

    # --- jeden vzorek ------------------------------------------------------------------------

    def sample(self, point: Point, normal: Point, area: float = 0.0) -> PtSample:
        s = self.settings
        normal = _unit(normal)
        frame = _frame(normal)
        local = (*SPIRAL, *RING_DIRS)
        dirs = [normal, *(_world(frame, d) for d in local)]
        angles = [0.0, *(math.degrees(math.acos(min(1.0, d[2]))) for d in local)]
        rays = [self.geo.visible(point, d) for d in dirs]
        reasons: list[tuple[str, str]] = []

        openness = 100 * sum(r.visible for r in rays[1:DIRECTIONS + 1]) / DIRECTIONS
        gap = rays[0].distance if not rays[0].visible and rays[0].distance else None

        free = sorted((a, d) for a, d, r in zip(angles, dirs, rays, strict=True)
                      if r.visible and r.certain)
        loose = min((a for a, r in zip(angles, rays, strict=True) if r.visible), default=None)
        best = self._best_free(point, normal, free)
        alpha = best[0][0] if best else None

        # nástřik
        spray = _grade(alpha, loose, s.spray_deg, s.spray_limit_deg)
        if spray == "blocked":
            reasons.append(("spray_blocked", f"Nástřik nejde – žádný volný směr do "
                                             f"{_n(s.spray_limit_deg)}° od kolmice."))
        elif spray == "limited":
            reasons.append(("spray_limited", f"Nástřik jen šikmo – nejmenší volný úhel "
                                             f"{alpha:.0f}° od kolmice (mez "
                                             f"{_n(s.spray_deg)}°)."))

        # prohlídka
        view, view_angle = self._view(point, best, loose)
        if view == "blocked":
            if view_angle == "eye":
                reasons.append(("view_eye", f"Prohlídka nejde – oko (Ø {_n(s.eye_mm)} mm) se "
                                            f"nevejde blíž než {_n(s.view_distance_mm)} mm."))
            else:
                reasons.append(("view_blocked", f"Prohlídka nejde – žádný výhled pod úhlem "
                                                f"aspoň {_n(s.view_limit_deg)}° k povrchu."))
            view_angle = None
        elif view == "limited":
            reasons.append(("view_limited", f"Prohlídka jen šikmo nebo se zrcátkem – nejlepší "
                                            f"úhel {view_angle:.0f}° k povrchu (mez "
                                            f"{_n(s.view_deg)}°)."))
        if view == "uncertain":
            view_angle = None

        # otření nástrojem
        tool, tool_mm = "off", None
        if s.cleaning == "wipe":
            tool, tool_mm, why = self._tools(point, normal, dirs, rays, best)
            if tool in ("limited", "blocked"):
                reasons.append(("tool_limited" if tool == "limited" else "tool_blocked", why))
            elif tool == "uncertain":
                reasons.append(("uncertain", why))

        if "uncertain" in (spray, view):
            reasons.append(("uncertain", "Rozhodující paprsek je nejistý – prochází hranou "
                                         "nebo se plochy jen dotýká."))

        # upozornění
        if gap is not None and gap < s.tool_mm:
            if s.fine_tool_mm and gap < s.fine_tool_mm:
                reasons.append(("slit", f"Úzká štěrbina {_dec(gap)} mm – {SLIT_TEXT}."))
            else:
                reasons.append(("gap", f"Mezera {_dec(gap)} mm – nástroj Ø {_n(s.tool_mm)} se "
                                       f"nevejde."))
        if openness < s.open_warning:
            reasons.append(("deep", f"Hluboké nebo zakryté místo – otevřené jen do "
                                    f"{_dec(openness)} % směrů; nanesení vývojky a prohlídka "
                                    f"jsou obtížné."))

        grades = [g for g in (spray, tool, view) if g != "off"]
        if "blocked" in grades:
            state = "blocked"
        elif "limited" in grades or any(kind in WARNINGS for kind, _ in reasons):
            state = "limited"
        elif "uncertain" in grades:
            state = "uncertain"
        else:
            state = "ok"
        return PtSample(point, normal, area, state, spray, tool, view, alpha,
                        view_angle if isinstance(view_angle, float) else None, tool_mm,
                        gap, openness, tuple(dict.fromkeys(reasons)))

    # --- směry -------------------------------------------------------------------------------

    def _free(self, point: Point, direction: Point) -> bool:
        ray = self.geo.visible(point, direction)
        return ray.visible and ray.certain

    def _best_free(self, point: Point, normal: Point, free: list[tuple[float, Point]]
                   ) -> list[tuple[float, Point]]:
        """Volné jisté směry podle úhlu od kolmice. Když kolmice volná není, dohledá se nejmenší
        volný úhel půlením po poledníku – od nejbližšího volného směru i od středu volných."""
        if not free or free[0][0] == 0.0:
            return free
        found = list(free)
        starts = [free[0][1]]
        mean = _unit(tuple(sum(d[i] for _, d in free) for i in range(3)))
        if mean is not None and _dot(mean, normal) > 1e-6 and self._free(point, mean):
            found.append((_angle(mean, normal), mean))
            starts.append(mean)
        for start in starts:
            refined = self._refine(point, normal, start)
            if refined is not None:
                found.append(refined)
        found.sort()
        climbed = self._climb(point, normal, found[0])
        if climbed[0] < found[0][0]:
            found.insert(0, climbed)
        return found

    def _climb(self, point: Point, normal: Point, best: tuple[float, Point]
               ) -> tuple[float, Point]:
        """Dohledání do stran: směr se natočí kolem kolmice (o něco šikměji, aby byl volný)
        a znovu se dohledá po poledníku; menší úhel se přijme. Kroky natočení se zmenšují."""
        angle, direction = best
        tries = 0
        for delta in CLIMB_DEG:
            moved = True
            while moved and tries < MAX_CLIMB:
                moved = False
                for sign in (1.0, -1.0):
                    side = _unit(tuple(direction[i] - _dot(direction, normal) * normal[i]
                                       for i in range(3)))
                    if side is None:
                        return angle, direction
                    wider = math.radians(min(angle + 3.0, 89.9))
                    start = tuple(math.cos(wider) * normal[i] + math.sin(wider) * side[i]
                                  for i in range(3))
                    turned = _rotate(start, normal, math.radians(sign * delta))
                    if not self._free(point, turned):
                        continue
                    tries += 1
                    refined = self._refine(point, normal, turned)
                    if refined is not None and refined[0] < angle - REFINE_DEG / 2:
                        angle, direction = refined
                        moved = True
                        break
        return angle, direction

    def _refine(self, point: Point, normal: Point, start: Point
                ) -> tuple[float, Point] | None:
        cos_start = _dot(start, normal)
        side = _unit(tuple(start[i] - cos_start * normal[i] for i in range(3)))
        if side is None:
            return None
        lo, hi = 0.0, math.acos(max(-1.0, min(1.0, cos_start)))  # kolmice zavřená, start volný

        def direction(angle: float) -> Point:
            return tuple(math.cos(angle) * normal[i] + math.sin(angle) * side[i]
                         for i in range(3))

        while hi - lo > math.radians(REFINE_DEG):
            mid = (lo + hi) / 2
            if self._free(point, direction(mid)):
                hi = mid
            else:
                lo = mid
        return math.degrees(hi), direction(hi)

    # --- prohlídka ---------------------------------------------------------------------------

    def _view(self, point: Point, best: list[tuple[float, Point]], loose: float | None
              ) -> tuple[str, Any]:
        """(stav, úhel k povrchu) – nebo („blocked“, „eye“), když je výhled, ale oko se
        nevejde."""
        s = self.settings
        ok_angle, limit_angle = 90 - s.view_deg, 90 - s.view_limit_deg
        tried = 0
        eye_failed = False
        for angle, direction in best:
            if angle > limit_angle + 1e-9 or tried >= MAX_EYE:
                break
            tried += 1
            if self._eye_fits(point, direction):
                grade = _grade(angle, loose, ok_angle, limit_angle)
                return grade, 90 - angle
            eye_failed = True
        if loose is not None and loose <= limit_angle and not eye_failed:
            return "uncertain", None
        return "blocked", "eye" if eye_failed else None

    def _eye_fits(self, point: Point, direction: Point) -> bool:
        """Najde se na volném paprsku do vzdálenosti prohlídky místo s volnou koulí oka?"""
        s = self.settings
        radius = s.eye_mm / 2
        if radius <= 0:
            return True  # oko jako bod: stačí volný paprsek
        for share in EYE_STEPS:
            distance = s.view_distance_mm * share
            if distance < radius:
                continue
            clearance = self._distance(_along(point, direction, distance))
            if clearance is not None and clearance >= radius - TOUCH:
                return True
        return False

    # --- nástroj -----------------------------------------------------------------------------

    def _tools(self, point: Point, normal: Point, dirs: list[Point], rays: list[Any],
               best: list[tuple[float, Point]]) -> tuple[str, float | None, str]:
        s = self.settings
        main, main_why = self._tool(point, normal, s.tool_mm, dirs, rays, best)
        if main is True:
            return "ok", s.tool_mm, ""
        main_text = _tool_text(s.tool_mm, main_why, s.tool_length_mm)
        if s.fine_tool_mm:
            fine, fine_why = self._tool(point, normal, s.fine_tool_mm, dirs, rays, best)
            if fine is True:
                return ("limited", s.fine_tool_mm,
                        f"Vejde se jen jemný nástroj Ø {_n(s.fine_tool_mm)} – {main_text}.")
            if main is None or fine is None:
                return "uncertain", None, ("Průnik nástroje s dílem jádro nespočítalo – nejde "
                                           "rozhodnout, jestli se nástroj vejde.")
            return ("blocked", None, f"Nástroj se nevejde – {main_text}; "
                    f"{_tool_text(s.fine_tool_mm, fine_why, s.tool_length_mm)}.")
        if main is None:
            return "uncertain", None, ("Průnik nástroje s dílem jádro nespočítalo – nejde "
                                       "rozhodnout, jestli se nástroj vejde.")
        return "blocked", None, f"Nástroj se nevejde – {main_text}."

    def _tool(self, point: Point, normal: Point, diameter: float, dirs: list[Point],
              rays: list[Any], best: list[tuple[float, Point]]) -> tuple[bool | None, str]:
        """Vejde se nástroj (kulička špičky dotýkající se místa + dřík)? (True/False/None =
        nejisté, důvod „tip“ / „shank“)."""
        radius = diameter / 2
        center = _along(point, normal, radius)
        where = self.geo.classify(center)
        if where in ("inside", "surface"):
            return False, "tip"
        clearance = self._distance(center)
        if where == "unknown" or clearance is None:
            return None, "unknown"
        if clearance < radius - TOUCH:
            return False, "tip"
        length = self.settings.tool_length_mm
        candidates: dict[Point, tuple[bool, float]] = {}  # směr → (zavřený z místa, úhel)
        for angle, direction in best:
            candidates.setdefault(direction, (False, angle))
        for direction, ray in zip(dirs, rays, strict=True):
            clear = ray.visible or (ray.distance is not None and ray.distance > length + radius)
            candidates.setdefault(direction, (not clear, _angle(direction, normal)))
        exact, uncertain = 0, False
        for direction, _ in sorted(candidates.items(), key=lambda item: item[1]):
            if exact >= MAX_EXACT:
                break
            if not self._shank_sieve(center, direction, radius * SHANK, length):
                continue
            exact += 1
            volume = overlap(self.shape, _cylinder(center, direction, radius * SHANK, length))
            if volume is None:
                uncertain = True
            elif volume <= OVERLAP_TOL:
                return True, ""
        return (None, "unknown") if uncertain else (False, "shank")

    def _shank_sieve(self, center: Point, direction: Point, radius: float,
                     length: float) -> bool:
        """Rychlé síto dříku: osa a čtyři přímky po obvodu (0,9 poloměru) bez dílu."""
        t1, t2, _ = _frame(direction)
        origins = [center, *(tuple(center[i] + RIM * radius * (c * t1[i] + s * t2[i])
                                   for i in range(3))
                             for c, s in ((1, 0), (0, 1), (-1, 0), (0, -1)))]
        for origin in origins:
            if not self.geo.visible(origin, direction, length).visible:
                return False
        return True

    def _distance(self, point: Point) -> float | None:
        """Nejmenší vzdálenost bodu od dílu [mm] (None = jádro nespočítalo)."""
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.gp import gp_Pnt

        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
        distance = BRepExtrema_DistShapeShape(vertex, self.shape)
        if not distance.IsDone() or not distance.NbSolution():
            return None
        return distance.Value()


def check_point(part: Any, point: Point, normal: Point,
                settings: PtSettings | None = None) -> PtSample:
    """Tři kontroly v jednom bodě (testy, hranice pásů)."""
    return Sampler(PartGeometry(part), settings or PtSettings()).sample(point, normal)


def _grade(best: float | None, loose: float | None, ok: float, limit: float) -> str:
    """Stav kontroly z nejmenšího volného úhlu (jistý paprsek) a nejmenšího volného úhlu
    vůbec (i nejistý paprsek): nejisté se nikdy nepočítá jako přístupné."""
    if best is not None and best <= ok + 1e-9:
        return "ok"
    if loose is not None and loose <= ok + 1e-9:
        return "uncertain"
    if best is not None and best <= limit + 1e-9:
        return "limited"
    if loose is not None and loose <= limit + 1e-9:
        return "uncertain"
    return "blocked"


def _tool_text(diameter: float, why: str, length: float) -> str:
    if why == "tip":
        return f"Ø {_n(diameter)}: špička narazí do okolní plochy"
    if why == "shank":
        return f"Ø {_n(diameter)}: dřík {_n(length)} mm narazí ve všech zkoušených směrech"
    return f"Ø {_n(diameter)}: nejisté"


def _cylinder(center: Point, direction: Point, radius: float, length: float) -> Any:
    from build123d import Plane, Solid

    return Solid.make_cylinder(radius, length, Plane(origin=center, z_dir=direction))


def self_check(folder: Any) -> tuple[bool, str]:
    """Rychlá kontrola PT na referenční kapse (self-test aplikace, i ve Windows): střed dna
    přístupný, 2 mm od stěny jen jemný nástroj, 1 mm od stěny nástroj nevejde."""
    from skodacad.document import Document
    from skodacad.rebuild import rebuild

    part = rebuild(Document.load(Path(folder) / "kapsa.json")).part
    sampler = Sampler(PartGeometry(part), PtSettings())
    states = [sampler.sample((x, 0.0, 15.0), (0, 0, 1)).tool for x in (0.0, -18.0, -19.0)]
    if states == ["ok", "limited", "blocked"]:
        return True, "PT přístupnost: OK (dno kapsy – nástroj Ø 10, jen Ø 3, nevejde se)"
    return False, f"PT přístupnost: {states} (čekáno ok, limited, blocked)"
