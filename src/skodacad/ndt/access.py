"""Návrh poloh UT sondy a mapa problémových zón (etapa 09, docs/ndt/17-navrh-etapa-09.md).

Varianta = rovinná kontaktní plocha × směr paprsku × úhel β × počet odrazů. Analýza je
vyzkouší ve třech kolech:

1. **přístupnost** – přiložení sondy v mřížce poloh plochy (krok analýzy) v každém směru,
2. **dosah** – vede některé rameno paprsku z platné polohy do obalového kvádru cíle?
3. **pokrytí** – stávající výpočet etapy 06 / 07B (``coverage.compute`` /
   ``volume_coverage.compute_volume``) krokem analýzy; vlastní model svazku nemá.

Mřížka prvního kola je táž jako mřížka pojezdu třetího kola, takže se přiložení sondy
počítá jen jednou (``devices.reuse_placements``). Varianty se seřadí, složí se kombinace
nejvýš tří a jejich mapy se sjednotí vzorek po vzorku (stejná mřížka cíle).

Jen geometrie: pořadí vyjadřuje geometrické pokrytí a přístupnost, nikoli zjistitelnost
vad. Analýza je pohled – nic neukládá a díl nemění.
"""

from __future__ import annotations

import csv
import json
import math
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from skodacad.ndt import UT_ACCESS, UT_DISCLAIMER
from skodacad.ndt.coverage import (
    PERCENT_NOTE,
    CoverageError,
    CoverageMap,
    _grid_face,
    auto_tolerance,
    compute,
)
from skodacad.ndt.devices import (
    STATES as PLACEMENT_STATES,
)
from skodacad.ndt.devices import (
    DeviceError,
    Placement,
    Probe,
    aim,
    direction_angle,
    place,
    reuse_placements,
)
from skodacad.ndt.geometry import GeometryError, PartGeometry, Point
from skodacad.ndt.ut import BeamError, trace_beam
from skodacad.ndt.volume_coverage import VolumeCoverageMap, compute_volume
from skodacad.ndt.welds import TargetError, direction_name, normalize_target, resolve_target

ALGORITHM = "ndt-ut-navrh-poloh 1"
ORDER_NOTE = ("Pořadí variant vyjadřuje jen geometrické pokrytí a přístupnost, "
              "nikoli zjistitelnost vad.")
NOT_FOUND_NOTE = ("Nenalezeno neznamená nemožné: výsledek platí jen pro vyzkoušené plochy, "
                  "směry, úhly, odrazy, krok a rozměry sondy.")
CURVED_NOTE = ("Zakřivené plochy se jako kontaktní nezkoušejí – pokrytí z nich zatím nejde "
               "spolehlivě vyhodnotit.")
ALTERNATIVE_ANGLES = (45.0, 60.0, 70.0)
DIRECTION_STEPS = (30.0, 45.0, 90.0)
MAX_VARIANTS = 40  # nejvýš variant ve 3. kole
MAX_FACE_POSITIONS = 500  # nejvýš poloh 1. kola na jedné ploše
MAX_PLACEMENTS = 20_000  # nejvýš přiložení v 1. kole celkem
COMBINATION_SIZE = 3
MIN_GAIN = 1.0  # p. b. – menší přírůstek už kombinaci nerozšíří
TIE = 1.0  # p. b. – v tomto rozdílu pokrytí rozhoduje počet platných poloh
ANGLE_MERGE = 0.5  # ° – bližší směry jsou tentýž směr
STATES = {"covered": "Geometricky pokryto", "uncovered": "Geometricky nepokryto",
          "uncertain": "Nelze spolehlivě vyhodnotit"}
KINDS = {"curved": "zakřivená plocha", "small": "malá plocha", "access": "sonda se nevejde",
         "reach": "paprsek k cíli nedosáhne", "limit": "nad limit", "error": "chyba výpočtu"}
CONTACT_STATES = {"all": "sonda se vejde ve všech směrech mířících k cíli",
                  "some": "sonda se vejde jen v některých směrech mířících k cíli",
                  "none": "paprsek by k cíli mířil, ale sonda se nevejde",
                  "away": "odsud paprsek k cíli nemíří"}
CONTACT_COLORS = {"all": (0.15, 0.70, 0.25), "some": (0.95, 0.55, 0.10),
                  "none": (0.85, 0.20, 0.15), "away": (0.60, 0.60, 0.60)}
_CURVED = {"CYLINDER": "válec", "CONE": "kužel", "SPHERE": "koule", "TORUS": "anuloid"}
# Odhad času (změřeno 18. 10. 2026 v cloudu na výřezu V svaru): zamíření a paprsky 1. a 2.
# kola i s přiložením tam, odkud paprsek míří k cíli, ~6 ms na polohu a směr; jedna
# varianta 3. kola ~7 s (přiložení 30 ms, paprsek 0,6 ms).
_AIM_SECONDS = (0.004, 0.01)
_VARIANT_SECONDS = (4.0, 12.0)

Progress = Callable[[str, int, int], None]


class AccessError(ValueError):
    """Analýzu nejde spustit (česky, s radou co změnit)."""


def _plural(n: int, one: str, few: str, many: str) -> str:
    return f"{n} {one if n == 1 else few if 2 <= n <= 4 else many}"


def _num(value: float, digits: int = 1) -> str:
    value = round(float(value), digits)
    return f"{0.0 if value == 0 else value:g}".replace(".", ",")


@dataclass(frozen=True)
class AccessOptions:
    """Rozsah vyzkoušených variant a kroky (mm, °)."""

    step_mm: float = 10.0  # krok analýzy = pojezd 3. kola i mřížka 1. kola (u ploch i cíl)
    direction_step_deg: float = 45.0
    alternative_angles: bool = False  # i 45°, 60°, 70° (stejné rozměry sondy)
    bounces: tuple[int, ...] = (0, 1)
    target_step_mm: float | None = None  # objem: None = doporučený (07B); plochy: krok analýzy
    tolerance_mm: float | None = None  # None = automatická jako v panelu
    spread_deg: float = 0.0

    def checked(self) -> AccessOptions:
        def number(value: Any, label: str, low: float, high: float) -> float:
            if (isinstance(value, bool) or not isinstance(value, int | float)
                    or not math.isfinite(value) or not low <= value <= high):
                raise AccessError(f"{label} musí být číslo {_num(low)}–{_num(high)}.")
            return float(value)

        step = number(self.step_mm, "Krok analýzy [mm]", 0.5, 1000)
        if self.direction_step_deg not in DIRECTION_STEPS:
            raise AccessError("Směry se zkoušejí po 30°, 45° nebo 90°.")
        bounces = tuple(sorted(set(self.bounces)))
        if not bounces or any(isinstance(b, bool) or not isinstance(b, int) or not 0 <= b <= 2
                              for b in bounces):
            raise AccessError("Odrazy vyber z 0, 1 a 2.")
        target = (None if self.target_step_mm is None
                  else number(self.target_step_mm, "Krok cíle [mm]", 0.1, 1000))
        tolerance = (None if self.tolerance_mm is None
                     else number(self.tolerance_mm, "Tolerance zachycení [mm]", 0, 1000))
        spread = number(self.spread_deg, "Rozevření [°]", 0, 45)
        return replace(self, step_mm=step, bounces=bounces, target_step_mm=target,
                       tolerance_mm=tolerance, spread_deg=spread)


@dataclass(frozen=True)
class Variant:
    """Jedna vyzkoušená kombinace; ``reference`` = kontaktní plocha významem (bod a směr)."""

    face: str
    reference: dict[str, Any] = field(compare=False)
    angle_deg: float  # směr paprsku jako ``place(angle=…)``
    direction: str
    beta: float  # 0 = přímá sonda
    bounces: int

    @property
    def label(self) -> str:
        beam = "přímá sonda" if self.beta == 0 else f"β {_num(self.beta)}°"
        return f"{self.face}; směr {self.direction}; {beam}; odrazy {self.bounces}"


@dataclass(frozen=True)
class Rejected:
    """Vyřazená varianta, směr nebo celá plocha a český důvod."""

    kind: str  # curved / small / access / reach / limit / error
    face: str
    reason: str
    direction: str = ""
    beta: float | None = None
    bounces: int | None = None

    @property
    def label(self) -> str:
        parts = [self.face]
        if self.direction:
            parts.append(f"směr {self.direction}")
        if self.beta is not None:
            parts.append("přímá sonda" if self.beta == 0 else f"β {_num(self.beta)}°")
        if self.bounces is not None:
            parts.append(f"odrazy {self.bounces}")
        return "; ".join(parts)


@dataclass(frozen=True)
class ContactPoint:
    """Poloha mřížky 1. kola: z kolika směrů míří paprsek k cíli (``tried``) a v kolika
    z nich se sonda vešla (``fits``). ``tried == 0`` = odsud k cíli nemíří nic."""

    point: Point
    fits: int
    tried: int

    @property
    def state(self) -> str:
        if not self.tried:
            return "away"
        return "all" if self.fits == self.tried else "some" if self.fits else "none"


@dataclass(frozen=True)
class AccessEstimate:
    faces: int
    positions: int  # polohy × směry 1. kola (přiloží se jen ty, odkud paprsek míří k cíli)
    variants: int
    seconds: tuple[float, float]
    ok: bool
    text: str


@dataclass(frozen=True)
class Preparation:
    """Výsledek 1. a 2. kola – jen data, přenese se z pomocného procesu."""

    candidates: list[Variant]
    reach: list[int]  # z kolika platných poloh míří paprsek k cíli (pro každou kandidátní)
    # 1. kolo přikládá sondu jen tam, odkud paprsek některé varianty míří k cíli.
    rejected: list[Rejected]
    contact: list[ContactPoint]
    faces: int  # vyzkoušené rovinné plochy
    placements: int
    assumptions: dict[str, Any]
    seconds: float


@dataclass(frozen=True)
class VariantResult:
    """Varianta spočítaná stávajícím výpočtem pokrytí (krokem analýzy)."""

    variant: Variant
    coverage: CoverageMap | VolumeCoverageMap
    clearance: float | None  # nejmenší volno platných poloh 1. kola (None = žádná překážka)
    best: Point | None  # poloha mřížky, ze které je pokryto nejvíc vzorků
    best_reference: dict[str, Any] | None = field(compare=False)
    note: str
    seconds: float

    @property
    def covered(self) -> float:
        return self.coverage.percent("covered")

    @property
    def uncertain(self) -> float:
        return self.coverage.percent("uncertain")


@dataclass(frozen=True)
class AccessResult:
    preparation: Preparation
    variants: list[VariantResult]  # seřazené
    rejected: list[Rejected]  # 1.–3. kolo
    combination: list[int]  # indexy do ``variants``
    gains: list[float]  # p. b., první = pokrytí první varianty
    union: CoverageMap | VolumeCoverageMap | None
    complete: bool
    expected: int  # kolik variant mělo 3. kolo spočítat
    seconds: float

    @property
    def combined(self) -> float:
        return self.union.percent("covered") if self.union is not None else 0.0

    def combination_text(self) -> str:
        if not self.combination:
            return ""
        names = " + ".join(f"#{i + 1}" for i in self.combination)
        parts = [f"#{self.combination[0] + 1} {_num(self.gains[0], 2)} %"]
        parts += [f"#{i + 1} přidá {_num(g, 2)} p. b."
                  for i, g in zip(self.combination[1:], self.gains[1:], strict=True)]
        if len(self.combination) == 1:
            return (f"Kombinace: jen #{self.combination[0] + 1} ({_num(self.combined, 2)} %) – "
                    f"další varianta by přidala méně než {_num(MIN_GAIN)} p. b.")
        return f"Kombinace {names}: {_num(self.combined, 2)} % ({', '.join(parts)})."

    def summary(self, top: int = 10) -> list[str]:
        prep = self.preparation
        a = prep.assumptions
        lines = [f"{UT_ACCESS} – návrh poloh sondy", UT_DISCLAIMER, ORDER_NOTE, PERCENT_NOTE,
                 *a.get("device_lines", [])]
        if not self.complete:
            lines.append(f"Neúplná analýza – zastavena po {len(self.variants)} z "
                         f"{self.expected} variant.")
        lines.append(f"Vyzkoušeno: "
                     f"{_plural(prep.faces, 'rovinná plocha', 'rovinné plochy', 'rovinných ploch')}"
                     f", {prep.placements} přiložení sondy, "
                     f"{_plural(self.expected, 'varianta', 'varianty', 'variant')} ve 3. kole.")
        for rank, result in enumerate(self.variants[:top], start=1):
            lines.append(f"#{rank} {result.variant.label}: pokryto {_num(result.covered, 2)} %, "
                         f"nejisté {_num(result.uncertain, 2)} %, platné polohy "
                         f"{result.coverage.valid_positions}/{result.coverage.positions}."
                         + (f" {result.note}" if result.note else ""))
        if len(self.variants) > top:
            lines.append(f"… a dalších {len(self.variants) - top} variant (všechny v CSV).")
        if self.combination:
            lines.append(self.combination_text())
        elif self.variants:
            lines.append("Žádná vyzkoušená varianta z cíle nic geometricky nepokryje.")
        else:
            lines.append("Žádnou variantu, ze které by sonda šla přiložit a paprsek mířil "
                         "k cíli, jsem nenašel.")
        counts = Counter(r.kind for r in self.rejected)
        if counts:
            lines.append("Vyřazeno: " + ", ".join(f"{KINDS[k]} {n}" for k, n in counts.items())
                         + ".")
            groups: dict[tuple[str, str], list[Rejected]] = {}
            for rejected in self.rejected:
                if rejected.kind != "curved":
                    groups.setdefault((rejected.face, rejected.kind), []).append(rejected)
            for (face, kind), items in groups.items():
                directions = list(dict.fromkeys(r.direction for r in items if r.direction))
                where = f" – směry {', '.join(directions)}" if directions else ""
                lines.append(f"– {face}: {KINDS[kind]}{where}; např. {items[0].reason}.")
        if counts.get("curved"):
            lines.append(CURVED_NOTE)
        lines += [NOT_FOUND_NOTE,
                  f"Krok analýzy {_num(a['step_mm'])} mm, směry po "
                  f"{_num(a['direction_step_deg'])}°, odrazy "
                  f"{', '.join(map(str, a['bounces']))}, rozevření {_num(a['spread_deg'])}°; "
                  f"výpočet {self.seconds:.1f} s; algoritmus {ALGORITHM}."]
        return lines

    def write_csv(self, path: str | Path) -> Path:
        path = Path(path)

        def cz(value: float | None, digits: int = 6) -> str:
            return "" if value is None else f"{value:.{digits}f}".replace(".", ",")

        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            for text in (f"{UT_ACCESS} – návrh poloh sondy", UT_DISCLAIMER, ORDER_NOTE,
                         PERCENT_NOTE, *self.preparation.assumptions.get("device_lines", []),
                         *([self.combination_text()] if self.combination else []),
                         NOT_FOUND_NOTE,
                         json.dumps(self.preparation.assumptions, ensure_ascii=False,
                                    sort_keys=True)):
                writer.writerow([text])
            writer.writerow(["pořadí", "plocha", "směr [°]", "popis směru", "β [°]", "odrazy",
                             "stav", "pokryto [%]", "nejisté [%]", "platné polohy",
                             "polohy pojezdu", "nejmenší volno [mm]", "sonda x [mm]",
                             "sonda y [mm]", "sonda z [mm]", "poznámka / důvod"])
            for rank, r in enumerate(self.variants, start=1):
                v = r.variant
                best = r.best or (None, None, None)
                writer.writerow([rank, v.face, cz(v.angle_deg, 3), v.direction,
                                 cz(v.beta, 3), v.bounces, "vyhodnoceno", cz(r.covered, 4),
                                 cz(r.uncertain, 4), r.coverage.valid_positions,
                                 r.coverage.positions, cz(r.clearance, 3),
                                 *(cz(c, 3) for c in best), r.note])
            for rejected in self.rejected:
                writer.writerow(["", rejected.face, "", rejected.direction,
                                 cz(rejected.beta, 3), "" if rejected.bounces is None
                                 else rejected.bounces, "vyřazeno", "", "", "", "", "",
                                 "", "", "", rejected.reason])
        return path


def union(maps: list[CoverageMap | VolumeCoverageMap],
          labels: list[str] | None = None) -> CoverageMap | VolumeCoverageMap:
    """Sjednocení map téže mřížky cíle vzorek po vzorku: pokryto, když je pokryto aspoň
    jednou; nejisté, když nikde pokryto a aspoň jednou nejisté; jinak nepokryto. Váhy
    (obsahy, objemy) se nemění ani nepřenormovávají."""
    if not maps:
        raise AccessError("Není co sjednotit.")
    first = maps[0]

    def identity(m: Any) -> list:
        if isinstance(m, VolumeCoverageMap):
            return [(s.cell, s.piece, s.volume_mm3) for s in m.samples]
        return [*m.centers, *m.areas]

    reference = identity(first)
    if any(type(m) is not type(first) or identity(m) != reference for m in maps[1:]):
        raise AccessError("Mapy nemají stejnou mřížku cíle – sjednotit nejdou.")
    states, hits, reasons = [], [], []
    for k in range(len(first.states)):
        covered = next((m for m in maps if m.states[k] == "covered"), None)
        unsure = next((m for m in maps if m.states[k] == "uncertain"), None)
        source = covered or unsure or first
        states.append(source.states[k])
        hits.append(source.hits[k])
        reasons.append("" if covered else source.reasons[k])
    assumptions = {**first.assumptions, "access_algorithm": ALGORITHM,
                   "combination": list(labels or [])}
    return replace(first, states=states, hits=hits, reasons=reasons,
                   positions=sum(m.positions for m in maps),
                   valid_positions=sum(m.valid_positions for m in maps),
                   uncertain_positions=sum(m.uncertain_positions for m in maps),
                   assumptions=assumptions, seconds=sum(m.seconds for m in maps))


def _segment_reaches(start: Point, direction: Point, length: float, low: Point, high: Point,
                     margin: float) -> bool:
    """Protne úsečka obalový kvádr zvětšený o ``margin``? (metoda vrstev)"""
    t0, t1 = 0.0, length
    for a, d, lo, hi in zip(start, direction, low, high, strict=True):
        lo, hi = lo - margin, hi + margin
        if abs(d) < 1e-12:
            if a < lo or a > hi:
                return False
            continue
        ta, tb = (lo - a) / d, (hi - a) / d
        if ta > tb:
            ta, tb = tb, ta
        t0, t1 = max(t0, ta), min(t1, tb)
        if t0 > t1:
            return False
    return True


def _xyz(vector: Any) -> Point:
    return (float(vector.X), float(vector.Y), float(vector.Z))


def _key(point: Point) -> tuple:
    return tuple(round(v, 6) for v in point)


def _face_label(face: Any) -> str:
    center = face.center()
    normal = face.normal_at(center)
    side = direction_name((normal.X, normal.Y, normal.Z))
    if side is None:
        side = f"({_num(normal.X, 2)}; {_num(normal.Y, 2)}; {_num(normal.Z, 2)})"
    return f"rovina {side}, střed ({_num(center.X)}; {_num(center.Y)}; {_num(center.Z)})"


def rank(results: list[VariantResult], study_beta: float) -> list[VariantResult]:
    """Pořadí: pokrytí; v rozdílu do 1 p. b. víc platných poloh, méně nejistého, méně odrazů,
    úhel beze změny. Pravidlo, ne souhrnné skóre."""
    remaining = list(results)
    ordered = []
    while remaining:
        best = max(r.covered for r in remaining)
        group = [r for r in remaining if r.covered >= best - TIE - 1e-9]
        pick = min(group, key=lambda r: (-r.coverage.valid_positions, round(r.uncertain, 9),
                                         r.variant.bounces,
                                         abs(r.variant.beta - study_beta) > 1e-9,
                                         remaining.index(r)))
        ordered.append(pick)
        remaining.remove(pick)
    return ordered


def finish(preparation: Preparation, results: list[VariantResult | Rejected],
           complete: bool = True, seconds: float | None = None) -> AccessResult:
    """Pořadí, kombinace a sjednocení z hotových variant (i po zastavení – ``complete``)."""
    done = [r for r in results if isinstance(r, VariantResult)]
    failed = [r for r in results if isinstance(r, Rejected)]
    ordered = rank(done, preparation.assumptions.get("study_beta", 0.0))
    combination: list[int] = []
    gains: list[float] = []
    current = None
    if ordered and ordered[0].covered > 0:
        combination, gains, current = [0], [ordered[0].covered], ordered[0].coverage
        while len(combination) < COMBINATION_SIZE:
            base = current.percent("covered")
            best = None
            for i, r in enumerate(ordered):
                if i in combination:
                    continue
                merged = union([current, r.coverage])
                gain = merged.percent("covered") - base
                if best is None or gain > best[0] + 1e-9:
                    best = (gain, i, merged)
            if best is None or best[0] < MIN_GAIN - 1e-9:
                break
            combination.append(best[1])
            gains.append(best[0])
            current = best[2]
    merged = (union([ordered[i].coverage for i in combination],
                    [f"#{i + 1} {ordered[i].variant.label}" for i in combination])
              if combination else None)
    total = preparation.seconds + sum(r.seconds for r in done) if seconds is None else seconds
    return AccessResult(preparation, ordered, [*preparation.rejected, *failed], combination,
                        gains, merged, complete, len(preparation.candidates), total)


class Analysis:
    """Návrh poloh pro jednu sondu a jeden cíl (plochy, body nebo objem) na dílu ``geo``."""

    def __init__(self, geo: PartGeometry, probe: Probe, *, faces: list[Any] | None = None,
                 points: list[Point] | None = None, volume: dict[str, Any] | None = None,
                 contact_faces: list[Any] | None = None,
                 options: AccessOptions | None = None,
                 device_lines: list[str] | None = None) -> None:
        if sum(x is not None and x != [] for x in (faces, points, volume)) != 1:
            raise AccessError("Analýza potřebuje právě jeden cíl: plochy, body, nebo objem.")
        self.geo, self.probe = geo, probe
        self.faces, self.points, self.volume = faces or None, points or None, volume
        self.options = (options or AccessOptions()).checked()
        self.device_lines = list(device_lines or [])
        self._memo: dict = {}
        self._seeds: list[tuple[Any, Placement, list[Point], int, float | None]] = []
        self._contact_faces = contact_faces
        self._grids: dict[int, list[Point]] | None = None
        self._box, self._centroid, self._across = self._target_box()

    # --- cíl -----------------------------------------------------------------------------

    def _target_box(self) -> tuple[tuple[Point, Point], Point, Point | None]:
        across = None
        if self.volume is not None:
            try:
                saved = normalize_target(self.volume)
                shape = resolve_target(self.geo.part, saved).shape
            except TargetError as exc:
                raise AccessError(str(exc)) from None
            box = shape.bounding_box()
            across = tuple(float(v) for v in saved["frame"]["across"])
            return ((_xyz(box.min), _xyz(box.max)), _xyz(shape.center()), across)
        if self.faces is not None:
            boxes = [(_xyz(b.min), _xyz(b.max)) for b in (f.bounding_box() for f in self.faces)]
            low = tuple(min(b[0][i] for b in boxes) for i in range(3))
            high = tuple(max(b[1][i] for b in boxes) for i in range(3))
            areas = [f.area for f in self.faces]
            total = sum(areas) or 1.0
            centers = [_xyz(f.center()) for f in self.faces]
            centroid = tuple(sum(a * c[i] for a, c in zip(areas, centers, strict=True)) / total
                             for i in range(3))
            return ((low, high), centroid, None)
        pts = [tuple(float(v) for v in p) for p in self.points]
        low = tuple(min(p[i] for p in pts) for i in range(3))
        high = tuple(max(p[i] for p in pts) for i in range(3))
        return ((low, high), tuple(sum(p[i] for p in pts) / len(pts) for i in range(3)), None)

    # --- varianty ------------------------------------------------------------------------

    def _betas(self) -> list[float]:
        if self.probe.kind == "straight":
            return [0.0]
        betas = [float(self.probe.beam_angle)]
        if self.options.alternative_angles:
            betas += [b for b in ALTERNATIVE_ANGLES if abs(b - betas[0]) > 1e-9]
        return betas

    def _directions(self, face: Any) -> list[tuple[float, str]]:
        if self.probe.kind == "straight":
            return [(0.0, "kolmo do materiálu")]
        center = _xyz(face.center())
        normal = _xyz(face.normal_at(face.center()))
        special: list[tuple[float, str]] = []
        toward = direction_angle(normal, tuple(c - p for c, p in zip(self._centroid, center,
                                                                     strict=True)))
        if toward is not None:
            special += [(toward, "k cíli"), ((toward + 180) % 360, "od cíle")]
        if self._across is not None:
            across = direction_angle(normal, self._across)
            if across is not None:
                name = ("kolmo na svar" if self.volume.get("kind") == "weld"
                        else "kolmo na osu cíle")
                special += [(across, name), ((across + 180) % 360, name)]
        step = self.options.direction_step_deg
        uniform = [(k * step, "") for k in range(round(360 / step))]
        result: list[tuple[float, str]] = []
        for angle, name in [*special, *uniform]:
            angle = round(angle % 360.0, 9) % 360.0
            if any(min(abs(angle - a), 360 - abs(angle - a)) < ANGLE_MERGE for a, _ in result):
                continue
            result.append((angle, f"{name} ({_num(angle, 0)}°)" if name else f"{_num(angle, 0)}°"))
        return result

    def _contact(self) -> tuple[list[Any], list[Rejected]]:
        from build123d import GeomType

        footprint = (math.pi * (self.probe.diameter / 2) ** 2 if self.probe.kind == "straight"
                     else self.probe.length * self.probe.width)
        usable, rejected = [], []
        for face in (self._contact_faces if self._contact_faces is not None
                     else self.geo.part.faces()):
            if face.geom_type != GeomType.PLANE:
                name = _CURVED.get(face.geom_type.name, "zakřivená plocha")
                box = face.bounding_box()
                rejected.append(Rejected("curved", f"{name}, střed "
                                         f"({_num(box.center().X)}; {_num(box.center().Y)}; "
                                         f"{_num(box.center().Z)})",
                                         "zakřivená plocha – jako kontaktní se nezkouší"))
            elif face.area < footprint - 1e-9:
                rejected.append(Rejected("small", _face_label(face),
                                         f"plocha ({_num(face.area)} mm²) je menší než "
                                         f"kontaktní plocha sondy ({_num(footprint)} mm²)"))
            else:
                usable.append(face)
        return usable, rejected

    def _grid(self, faces: list[Any]) -> dict[int, list[Point]]:
        if self._grids is None:
            grids = {}
            for i, face in enumerate(faces):
                try:
                    grids[i] = _grid_face(face, self.options.step_mm)
                except CoverageError:
                    grids[i] = []
            self._grids = grids
        return self._grids

    def estimate(self) -> AccessEstimate:
        """Velikost analýzy ještě před spuštěním (bez přiložení a paprsků)."""
        faces, _ = self._contact()
        grids = self._grid(faces)
        positions, variants, used = 0, 0, 0
        combos = len(self._betas()) * len(self.options.bounces)
        # Horní mez: 1. kolo přikládá jen tam, odkud paprsek míří k cíli (obvykle méně).
        for i, face in enumerate(faces):
            count = len(grids[i])
            if not count or count > MAX_FACE_POSITIONS:
                continue
            used += 1
            directions = len(self._directions(face))
            positions += count * directions
            variants += directions * combos
        variants = min(variants, MAX_VARIANTS)
        low = positions * _AIM_SECONDS[0] + variants * _VARIANT_SECONDS[0]
        high = positions * _AIM_SECONDS[1] + variants * _VARIANT_SECONDS[1]
        ok = 0 < positions <= MAX_PLACEMENTS
        if not used:
            text = "Žádná rovinná plocha není dost velká pro sondu – analýza nemá co zkoušet."
            ok = False
        else:
            text = (f"Odhad: {_plural(used, 'plocha', 'plochy', 'ploch')}, {positions} poloh "
                    f"a směrů sondy, nejvýš {_plural(variants, 'varianta', 'varianty', 'variant')}"
                    f" ve 3. kole; asi {_minutes(low)}–{_minutes(high)}.")
            if positions > MAX_PLACEMENTS:
                text += (f" To je víc než {MAX_PLACEMENTS} poloh a směrů – zvětši krok "
                         "analýzy, zkoušej méně směrů nebo vyber kontaktní plochy.")
        return AccessEstimate(used, positions, variants, (low, high), ok, text)

    # --- 1. a 2. kolo --------------------------------------------------------------------

    def prepare(self, progress: Progress | None = None) -> Preparation:
        started = time.monotonic()
        from skodacad.measure import face_reference

        faces, rejected = self._contact()
        grids = self._grid(faces)
        total = sum(len(grids[i]) * len(self._directions(f)) for i, f in enumerate(faces)
                    if len(grids[i]) <= MAX_FACE_POSITIONS)
        if total > MAX_PLACEMENTS:
            raise AccessError(f"Analýza by zkoušela {total} poloh a směrů sondy (nejvýš "
                              f"{MAX_PLACEMENTS}) – zvětši krok analýzy, zkoušej méně směrů "
                              "nebo vyber kontaktní plochy.")
        low, high = self._box
        tolerance = (self.options.tolerance_mm if self.options.tolerance_mm is not None
                     else auto_tolerance("face", self.options.step_mm,
                                         self.options.target_step_mm or 0.0))
        margin = tolerance + self.options.step_mm
        slope = math.tan(math.radians(self.options.spread_deg))
        combos = [(beta, bounces) for beta in self._betas() for bounces in self.options.bounces]
        configs = [replace(self.probe, bounces=bounces) if self.probe.kind == "straight"
                   else replace(self.probe, beam_angle=beta, bounces=bounces)
                   for beta, bounces in combos]
        candidates: list[tuple[Variant, int, tuple]] = []
        contact: list[ContactPoint] = []
        placements = 0
        tried_faces = 0
        with reuse_placements(self.geo, self._memo):
            for i, face in enumerate(faces):
                if progress:
                    progress("1. a 2. kolo: přístupnost a dosah", i, len(faces))
                label = _face_label(face)
                grid = grids[i]
                if not grid:
                    rejected.append(Rejected("small", label, "na ploše nevyšla žádná poloha "
                                             f"mřížky s krokem {_num(self.options.step_mm)} mm"))
                    continue
                if len(grid) > MAX_FACE_POSITIONS:
                    rejected.append(Rejected("limit", label, f"plocha má {len(grid)} poloh při "
                                             f"kroku {_num(self.options.step_mm)} mm (nejvýš "
                                             f"{MAX_FACE_POSITIONS}) – zvětši krok analýzy "
                                             "nebo vyber kontaktní plochy"))
                    continue
                tried_faces += 1
                directions = self._directions(face)
                fits, tried = [0] * len(grid), [0] * len(grid)
                for angle, direction in directions:
                    # 2. kolo napřed: zamíření je levné (~1 ms), přiložení drahé (~30 ms).
                    # Varianta projde, jen když existuje poloha platná A mířící k cíli –
                    # sondu proto stačí přikládat tam, odkud paprsek k cíli míří.
                    aims: list[Any] = []
                    for point in grid:
                        try:
                            aims.append(aim(self.geo, self.probe, point, angle, face))
                        except (DeviceError, GeometryError):
                            aims.append(None)
                    reaching: list[set[int]] = []
                    errors: list[str] = []
                    for probe in configs:
                        hits, error = set(), ""
                        for k, aimed in enumerate(aims):
                            if aimed is None:
                                continue
                            try:
                                beam = trace_beam(self.geo, replace(aimed, probe=probe))
                            except (BeamError, GeometryError) as exc:
                                error = str(exc)
                                continue
                            if any(_segment_reaches(leg.start, leg.direction, leg.length,
                                                    low, high,
                                                    margin + leg.cumulative_length * slope)
                                   for leg in beam.legs):
                                hits.add(k)
                        reaching.append(hits)
                        errors.append(error)
                    relevant = sorted(set().union(*reaching))
                    valid: dict[int, Placement] = {}
                    states: Counter = Counter()
                    for k in relevant:
                        placements += 1
                        tried[k] += 1
                        try:
                            placed = place(self.geo, self.probe, grid[k], angle=angle, face=face)
                        except (DeviceError, GeometryError):
                            states["error"] += 1
                            continue
                        states[placed.state] += 1
                        if placed.ok:
                            fits[k] += 1
                            valid[k] = placed
                    clearances = [p.clearance for p in valid.values() if p.clearance is not None]
                    clearance = min(clearances) if clearances else None
                    detail = ", ".join(f"{PLACEMENT_STATES.get(s, 'nejde přiložit')} {n}"
                                       for s, n in states.most_common())
                    for (beta, bounces), probe, hits, error in zip(combos, configs, reaching,
                                                                   errors, strict=True):
                        usable = [k for k in sorted(hits) if k in valid]
                        if not hits:
                            reason = (f"paprsek nejde spočítat: {error}" if error else
                                      f"paprsek z žádné z {len(grid)} poloh k cíli nemíří")
                            rejected.append(Rejected("reach", label, reason, direction,
                                                     beta, bounces))
                            continue
                        if not usable:
                            rejected.append(Rejected(
                                "access", label, f"sonda se nevejde v žádné z {len(hits)} "
                                f"poloh, odkud paprsek míří k cíli ({detail})", direction,
                                beta, bounces))
                            continue
                        seed = replace(valid[usable[0]], probe=probe)
                        variant = Variant(label, face_reference(face, grid[usable[0]]), angle,
                                          direction, beta, bounces)
                        candidates.append((variant, len(usable),
                                           (face, seed, grid, clearance)))
                contact += [ContactPoint(p, n, m) for p, n, m in zip(grid, fits, tried,
                                                                     strict=True)]
        if len(candidates) > MAX_VARIANTS:
            order = sorted(range(len(candidates)), key=lambda i: -candidates[i][1])
            keep = set(order[:MAX_VARIANTS])
            for i in order[MAX_VARIANTS:]:
                variant, reach, _ = candidates[i]
                rejected.append(Rejected("limit", variant.face,
                                         f"nad limit {MAX_VARIANTS} variant – k cíli mířilo "
                                         f"méně poloh ({reach})", variant.direction,
                                         variant.beta, variant.bounces))
            candidates = [c for i, c in enumerate(candidates) if i in keep]
        self._seeds = [c[2] for c in candidates]
        assumptions = {"access_algorithm": ALGORITHM, "step_mm": self.options.step_mm,
                       "direction_step_deg": self.options.direction_step_deg,
                       "alternative_angles": self.options.alternative_angles,
                       "bounces": list(self.options.bounces),
                       "target_step_mm": self.options.target_step_mm,
                       "tolerance_mm": self.options.tolerance_mm,
                       "spread_deg": self.options.spread_deg, "reach_margin_mm": margin,
                       "probe": self.probe.to_dict(), "study_beta": self._betas()[0],
                       "target_box": [list(low), list(high)],
                       "device_lines": self.device_lines}
        if progress:
            progress("1. a 2. kolo: přístupnost a dosah", len(faces), len(faces))
        return Preparation([c[0] for c in candidates], [c[1] for c in candidates], rejected,
                           contact, tried_faces, placements, assumptions,
                           time.monotonic() - started)

    # --- 3. kolo -------------------------------------------------------------------------

    def evaluate(self, index: int, variant: Variant) -> VariantResult | Rejected:
        """Spočítá pokrytí ``index``-té kandidátní varianty stávajícím výpočtem."""
        from skodacad.measure import face_reference

        started = time.monotonic()
        face, seed, grid, clearance = self._seeds[index]
        options = dict(mode="face", scan_step=self.options.step_mm,
                       angle_deg=variant.angle_deg, tolerance_mm=self.options.tolerance_mm,
                       spread_deg=self.options.spread_deg)
        try:
            with reuse_placements(self.geo, self._memo):
                if self.volume is not None:
                    result = compute_volume(self.geo, seed, target=self.volume,
                                            target_step=self.options.target_step_mm, **options)
                else:
                    result = compute(self.geo, seed, faces=self.faces, points=self.points,
                                     target_step=(self.options.target_step_mm
                                                  or self.options.step_mm), **options)
        except Exception as exc:  # noqa: BLE001 – jedna varianta nesmí shodit analýzu
            return Rejected("error", variant.face, f"pokrytí nejde spočítat: {exc}",
                            variant.direction, variant.beta, variant.bounces)
        best = self._best(result, face, seed, grid, variant.angle_deg)
        reference = face_reference(face, best) if best is not None else None
        if reference is not None:  # bez zaokrouhlení: přepočet z této polohy má tutéž mřížku
            reference["face"]["at"] = [float(v) for v in best]
        note = self._note(variant, result, clearance)
        return VariantResult(variant, result, clearance, best, reference, note,
                             time.monotonic() - started)

    def _best(self, result: Any, face: Any, seed: Placement, grid: list[Point],
              angle: float) -> Point | None:
        """Platná poloha mřížky, u které leží nejvíc zásahů (zásah z mezipolohy se přičte
        nejbližšímu uzlu). Jen uzel mřížky: přepočet z něj má tutéž mřížku pojezdu, a tedy
        totéž pokrytí – výchozí poloha výpočet v ploše jinak neovlivní."""
        nearest: dict[tuple, Point] = {}
        counts: Counter = Counter()
        for state, hit in zip(result.states, result.hits, strict=True):
            if state != "covered" or hit is None:
                continue
            key = _key(hit.origin)
            if key not in nearest:
                nearest[key] = min(grid, key=lambda p: math.dist(p, hit.origin))
            counts[nearest[key]] += 1
        with reuse_placements(self.geo, self._memo):
            for point, _ in counts.most_common():
                try:
                    if place(self.geo, seed.probe, point, angle=angle, face=face).ok:
                        return point
                except (DeviceError, GeometryError):
                    continue
        return None

    def _note(self, variant: Variant, result: Any, clearance: float | None) -> str:
        notes = []
        covered = [h for s, h in zip(result.states, result.hits, strict=True)
                   if s == "covered" and h is not None]
        if covered and all(h.leg > 1 for h in covered):
            notes.append("pokrytí jen přes odraz")
        elif any(h.leg > 1 for h in covered):
            notes.append("využívá odraz")
        if not covered:
            notes.append("z platných poloh nic nepokryje")
        if result.valid_positions < result.positions / 4:
            notes.append(f"sonda se vejde jen v {result.valid_positions} z {result.positions} "
                         "poloh plochy")
        if clearance is not None and clearance < 1.0:
            notes.append(f"volno jen {_num(clearance)} mm – sonda je u překážky")
        if variant.beta and abs(variant.beta - self._betas()[0]) > 1e-9:
            notes.append(f"předpokládá úhel {_num(variant.beta)}° místo "
                         f"{_num(self._betas()[0])}° ze studie (stejné rozměry sondy)")
        if result.percent("uncertain") > 0.005:
            notes.append(f"{_num(result.percent('uncertain'), 2)} % nelze spolehlivě "
                         "vyhodnotit")
        return (notes[0][0].upper() + "; ".join(notes)[1:] + ".") if notes else ""

    def run(self, progress: Progress | None = None,
            on_variant: Callable[[int, VariantResult | Rejected], None] | None = None
            ) -> AccessResult:
        """Celá analýza najednou (příkazová řádka, pomocný proces, testy)."""
        started = time.monotonic()
        preparation = self.prepare(progress)
        results = []
        for i, variant in enumerate(preparation.candidates):
            if progress:
                progress("3. kolo: pokrytí variant", i, len(preparation.candidates))
            outcome = self.evaluate(i, variant)
            results.append(outcome)
            if on_variant:
                on_variant(i, outcome)
        return finish(preparation, results, seconds=time.monotonic() - started)


def _minutes(seconds: float) -> str:
    if seconds < 90:
        return f"{max(1, round(seconds))} s"
    return f"{_num(seconds / 60, 0)} min"
