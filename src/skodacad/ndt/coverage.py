"""Mapa geometrického pokrytí UT: vzorky ploch/bodů, platné polohy a geometrická ramena.

Tolerance je numerický poloměr zachycení, nikoli fyzikální šířka paprsku. Procenta ploch
jsou vážená obsahy trojúhelníků. Bodové dotazy se počítají odděleně, bez fiktivní plochy.

Na ploše přiložení se nepočítá zásah prvního ramene: paprsek z ní jen vychází, do místa
nemíří (rozhodnutí autora 19. 10. 2026 k otázce z etapy 09). Odražené rameno, které se na
plochu vrátí (celý krok), se počítá dál.
"""

from __future__ import annotations

import csv
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skodacad.ndt import UT_COVERAGE, UT_DISCLAIMER
from skodacad.ndt.devices import Placement, place
from skodacad.ndt.geometry import PartGeometry, Point
from skodacad.ndt.ut import BeamLeg, BeamPath, Refraction, trace_beam
from skodacad.thickness_map import _Surface

ALGORITHM = "ndt-ut-pokryti 2"  # 2: bez zásahu 1. ramene na ploše přiložení (19. 10. 2026)
PERCENT_NOTE = ("Procento vyjadřuje pouze geometrický podíl zasažené oblasti, "
                "nikoli pravděpodobnost nalezení vady.")
CONTACT_NOTE = ("Místa na ploše přiložení: nepočítá se, odkud paprsek vychází (první rameno), "
                "jen odražený paprsek, který se na plochu vrátí.")
STATES = {"covered": "Geometricky pokryto", "uncovered": "Geometricky nepokryto",
          "uncertain": "Nelze spolehlivě vyhodnotit"}
COLORS = {"covered": (0.15, 0.70, 0.25), "uncovered": (0.85, 0.20, 0.15),
          "uncertain": (0.90, 0.75, 0.15)}
MAX_POSITIONS = 20_000
MAX_COMPARISONS = 80_000_000
# Pravidlo porovnání kroků (docs/ndt/15-rozbor-citlivosti-v-svaru.md, oddíl 8): na rovinném
# pojezdu je tolerance jen poloměr hledání (každý zásah se přesně ověří), hrubý běh proto
# hledá aspoň tak hustě jako jemný – jinak by část paprsků jen „nenašel“.
CONVERGENCE_RULE = "ndt-ut-porovnani 2: tolerance hrubého běhu ≥ jeho automatická tolerance"


class CoverageError(ValueError):
    """Výpočet není možný nebo nastavení není platné (česky)."""


@dataclass(frozen=True)
class PlanRegion:
    """Pásy úseků plánu dráhy (etapa 10, režim pojezdu ``plan``).

    Řádky plánu s roztečí r se počítají jako spojitě projetý pás šířky r – stejný předpoklad
    jako pojezd po ploše. Mezipoloha sondy, kterou výpočet dohledá mezi polohami plánu, proto
    smí ležet jen v pásu některého úseku: podél od začátku do konce, napříč ± ``half``.
    ``allowed`` navíc vyřadí přiložení, které plán zakazuje (zakázané zóny)."""

    strips: tuple[tuple[Point, Point, float, Point, float], ...]  # začátek, směr, délka,
    # směr napříč (jednotkové vektory v rovině plochy), polovina šířky pásu [mm]
    allowed: Callable[[Placement], bool] | None = None

    def contains(self, point: Point) -> bool:
        for start, along, length, across, half in self.strips:
            offset = tuple(p - s for p, s in zip(point, start, strict=True))
            a = sum(o * d for o, d in zip(offset, along, strict=True))
            b = sum(o * d for o, d in zip(offset, across, strict=True))
            if -1e-6 <= a <= length + 1e-6 and abs(b) <= half + 1e-6:
                return True
        return False

    def allows(self, placed: Placement) -> bool:
        return self.allowed is None or self.allowed(placed)


@dataclass(frozen=True)
class CoverageHit:
    leg: int
    distance: float
    origin: Point


@dataclass(frozen=True)
class CoverageMap:
    nodes: list[Point]
    triangles: list[tuple[int, int, int]]
    centers: list[Point]
    areas: list[float]
    states: list[str]
    hits: list[CoverageHit | None]
    reasons: list[str]
    positions: int
    valid_positions: int
    uncertain_positions: int
    assumptions: dict[str, Any]
    seconds: float

    @property
    def total_area(self) -> float:
        return sum(self.areas)

    def area(self, state: str) -> float:
        return sum(a for a, s in zip(self.areas, self.states, strict=True) if s == state)

    def percent(self, state: str) -> float:
        if self.total_area:
            return 100 * self.area(state) / self.total_area
        return 100 * self.states.count(state) / len(self.states) if self.states else 0.0

    def mesh(self) -> tuple[list, list, list]:
        """Oddělené uzly každé plošky: žádná interpolace mezi třemi stavy."""
        nodes, triangles, colors = [], [], []
        for tri, state in zip(self.triangles, self.states, strict=False):
            start = len(nodes)
            nodes.extend(self.nodes[i] for i in tri)
            triangles.append((start, start + 1, start + 2))
            colors.extend([COLORS[state]] * 3)
        return nodes, triangles, colors

    def summary(self) -> list[str]:
        lines = [UT_COVERAGE, UT_DISCLAIMER, PERCENT_NOTE,
                 f"Polohy sondy: {self.positions}, platné {self.valid_positions}, "
                 f"nejisté {self.uncertain_positions}."]
        for state, label in STATES.items():
            quantity = (f"{self.area(state):.1f} mm²" if self.total_area
                        else f"{self.states.count(state)} bodů")
            lines.append(f"{label}: {self.percent(state):.2f} % ({quantity}).")
        direct = sum(s == "covered" and h is not None and h.leg == 1
                     for s, h in zip(self.states, self.hits, strict=True))
        reflected = self.states.count("covered") - direct
        lines += [f"První zásah: přímé rameno {direct} vzorků, odraz {reflected} vzorků.",
                  f"Krok pojezdu {self.assumptions['scan_step_mm']:g} mm, "
                  f"cíle {self.assumptions['target_step_mm']:g} mm, "
                  f"tolerance {self.assumptions['tolerance_mm']:g} mm, "
                  f"rozevření {self.assumptions['spread_deg']:g}°.",
                  *self.assumptions.get("device_lines", []),
                  *([self.assumptions["tolerance_warning"]]
                    if self.assumptions.get("tolerance_warning") else []),
                  *([CONTACT_NOTE] if self.assumptions.get("contact_samples") else []),
                  *([self.assumptions["convergence_text"]]
                    if self.assumptions.get("convergence_text") else []),
                  f"Výpočet {self.seconds:.1f} s; algoritmus {ALGORITHM}."]
        lines.extend(dict.fromkeys(r for r in self.reasons if r))
        return lines

    def write_csv(self, path: str | Path) -> Path:
        path = Path(path)
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            for text in (UT_COVERAGE, UT_DISCLAIMER, PERCENT_NOTE,
                         *([CONTACT_NOTE] if self.assumptions.get("contact_samples") else []),
                         *self.assumptions.get("device_lines", []),
                         json.dumps(self.assumptions, ensure_ascii=False, sort_keys=True)):
                writer.writerow([text])
            writer.writerow(["x [mm]", "y [mm]", "z [mm]", "obsah [mm²]", "stav", "důvod",
                             "rameno", "dráha [mm]", "sonda x [mm]", "sonda y [mm]",
                             "sonda z [mm]"])

            def cz(value: float) -> str:
                return f"{value:.6f}".replace(".", ",")

            for p, a, state, hit, reason in zip(self.centers, self.areas, self.states,
                                               self.hits, self.reasons, strict=True):
                extra = ([hit.leg, cz(hit.distance), *(cz(v) for v in hit.origin)]
                         if hit else [""] * 5)
                writer.writerow([*(cz(v) for v in p), cz(a), STATES[state], reason, *extra])
        return path


def auto_tolerance(mode: str, scan_step: float, target_step: float = 0.0) -> float:
    """Automatická tolerance zachycení: polovina úhlopříčky mřížky pojezdu (po čáře 0,6 kroku),
    nejméně polovina úhlopříčky kroku cíle (ve 2D je nejvzdálenější bod buňky půl úhlopříčky).
    Plán dráhy (``plan``) má polohy po rozteči v obou směrech jako pojezd po ploše."""
    return max(target_step * math.sqrt(0.5),
               scan_step * (math.sqrt(0.5) if mode in ("face", "plan") else 0.6))


def _number(value: float, label: str, minimum: float, maximum: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, int | float)
            or not math.isfinite(value) or not minimum <= value <= maximum):
        raise CoverageError(f"{label} musí být konečné číslo {minimum:g}–{maximum:g}.")
    return float(value)


def _grid_face(face: Any, step: float) -> list[Point]:
    """Mřížka v parametrech plochy, body mimo ořezanou plochu (včetně otvorů) vynechává."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON

    surface = BRepAdaptor_Surface(face.wrapped)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face.wrapped)

    def intervals(axis: int) -> int:
        # Nejdelší z pěti izokřivek, měřeno po úsecích (válcový obvod není tětiva).
        lengths = []
        for cross in range(5):
            fixed = (v0 + (v1 - v0) * cross / 4 if axis == 0
                     else u0 + (u1 - u0) * cross / 4)
            low, high = (u0, u1) if axis == 0 else (v0, v1)
            pts = [surface.Value(low + (high - low) * i / 32, fixed) if axis == 0
                   else surface.Value(fixed, low + (high - low) * i / 32) for i in range(33)]
            lengths.append(sum(a.Distance(b) for a, b in zip(pts, pts[1:], strict=False)))
        return max(1, math.ceil(max(lengths) / step))

    nu, nv = intervals(0), intervals(1)
    if (nu + 1) * (nv + 1) > MAX_POSITIONS:
        raise CoverageError("Pojezd by měl příliš mnoho poloh – zvětši krok výpočtu.")
    classifier = BRepClass_FaceClassifier()
    result = []
    for i in range(nu + 1):
        for j in range(nv + 1):
            p = surface.Value(u0 + (u1 - u0) * i / nu, v0 + (v1 - v0) * j / nv)
            classifier.Perform(face.wrapped, p, 1e-7)
            if classifier.State() in (TopAbs_IN, TopAbs_ON):
                result.append((p.X(), p.Y(), p.Z()))
    return result


def _resolve_axis_hit(geo: PartGeometry, placed: Placement, point: Point, beam: BeamPath,
                      leg: BeamLeg, options: dict[str, Any], source: Point, mode: str,
                      length: float, step: float, angle: float,
                      cache: dict, region: PlanRegion | None = None
                      ) -> tuple[CoverageHit, bool] | None:
    """Numerická blízkost sama nezakryje slepé místo u překážky.

    Na rovinném pojezdu dopočítá mezi uzly polohu osového paprsku, znovu ověří otisk,
    kolizi i celou dráhu. Na zakřivené ploše tento rovinný důkaz nelze použít.
    """
    # Rozvinout odrazy zpět k přímému rameni. Posun zdroje neposouvá odražené
    # rameno stejným vektorem (na boční stěně se znaménko obrací).
    unfolded = point
    for previous in reversed(beam.legs[:leg.index - 1]):
        hit = previous.hit
        if hit is None:
            return None
        distance = sum((t - a) * n
                       for t, a, n in zip(unfolded, hit.point, hit.normal, strict=True))
        unfolded = tuple(t - 2 * distance * n
                         for t, n in zip(unfolded, hit.normal, strict=True))
    # Tečné roviny zakřivených odrazů jsou jen návrh; rozhoduje opětovné trasování.
    direction = beam.legs[0].direction
    normal = placed.z_dir
    denominator = sum(d * n for d, n in zip(direction, normal, strict=True))
    if abs(denominator) < 1e-9:
        return None
    distance = sum((t - a) * n
                   for t, a, n in zip(unfolded, placed.origin, normal, strict=True))
    distance /= denominator
    shift = tuple(t - a - d * distance
                  for t, a, d in zip(unfolded, placed.origin, direction, strict=True))
    if math.sqrt(sum(v * v for v in shift)) > step * 1.5:
        return None
    origin = tuple(o + delta for o, delta in zip(placed.origin, shift, strict=True))
    if mode == "line":
        offset = tuple(o - s for o, s in zip(origin, source, strict=True))
        along = sum(v * d for v, d in zip(offset, placed.x_dir, strict=True))
        off_line = sum((v - along * d)**2
                       for v, d in zip(offset, placed.x_dir, strict=True))
        if not -1e-6 <= along <= length + 1e-6 or off_line > 1e-10:
            return None
    if mode == "plan" and (region is None or not region.contains(origin)):
        return None  # mimo pásy úseků plánu sonda nejede
    key = tuple(round(v, 7) for v in origin)
    if key not in cache:
        surface = geo.surface_at(origin, placed.surface.face)
        if surface.distance > 1e-6:
            cache[key] = None
        else:
            candidate = place(geo, placed.probe, origin, angle=angle, face=placed.surface.face)
            usable = candidate.ok or candidate.state == "uncertain"
            if usable and region is not None and not region.allows(candidate):
                usable = False  # zakázaná zóna plánu
            cache[key] = trace_beam(geo, candidate, **options) if usable else None
    beam = cache[key]
    if beam is None:
        return None
    for candidate in beam.legs:
        offset = tuple(t - a for t, a in zip(point, candidate.start, strict=True))
        along = sum(v * d for v, d in zip(offset, candidate.direction, strict=True))
        residual = sum((v - along * d)**2
                       for v, d in zip(offset, candidate.direction, strict=True))
        if -1e-6 <= along <= candidate.length + 1e-6 and residual < 1e-10:
            hit = CoverageHit(candidate.index, candidate.cumulative_length - candidate.length
                              + max(0, along), beam.placement.origin)
            return hit, beam.placement.ok and candidate.certain
    return None


def _line_triangle_point(nodes: list[Point], triangle: tuple[int, int, int],
                         placed: Placement, leg: Any) -> Point | None:
    """Průnik plošky rovinou osového pojezdu: čára se vykreslí jako zasažené plošky.

    Bodový dotaz vyžaduje zásah bodu; u plošky stačí zásah uvnitř trojúhelníku, ne nutně
    přes jeho těžiště. Šířka takového pásu se při zjemňování sítě zmenšuje.
    """
    ax, ay, az = placed.x_dir
    bx, by, bz = leg.direction
    normal = (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
    vertices = [nodes[i] for i in triangle]
    distances = [sum((v - a) * n for v, a, n in zip(p, leg.start, normal, strict=True))
                 for p in vertices]
    cuts = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        a, b = distances[i], distances[j]
        if abs(a) < 1e-9:
            cuts.append(vertices[i])
        if a * b < 0:
            t = a / (a - b)
            cuts.append(tuple(v + t * (w - v)
                              for v, w in zip(vertices[i], vertices[j], strict=True)))
    if not cuts:
        return None
    return tuple(sum(p[i] for p in cuts) / len(cuts) for i in range(3))


def compute(geo: PartGeometry, placement: Placement, *, faces: list[Any] | None = None,
            points: list[Point] | None = None, mode: str = "face", scan_step: float = 5.0,
            target_step: float = 4.0, length_mm: float = 50.0, angle_deg: float = 0.0,
            tolerance_mm: float | None = None, spread_deg: float = 0.0,
            beta: float | None = None, bounces: int | None = None,
            max_length: float | None = None, refraction: Refraction | None = None,
            positions: list[Point] | None = None,
            region: PlanRegion | None = None) -> CoverageMap:
    """Pokrytí cílových ploch NEBO bodů. Neplatná poloha nikdy nepřispívá k pokrytí.

    Výpočet je diskrétní: 85,5 % pro desku je limit osového spojitého pojezdu bez tolerance,
    nikoli přesná hodnota při libovolné mřížce a nenulové toleranci. Režim ``plan`` (etapa 10)
    bere polohy sondy z plánu dráhy (``positions`` v pořadí jízdy) a mezipolohy jen z pásů
    ``region``.
    """
    started = time.monotonic()
    scan_step = _number(scan_step, "Krok pojezdu [mm]", 0.1, 1000)
    target_step = _number(target_step, "Krok cíle [mm]", 0.1, 1000)
    length_mm = _number(length_mm, "Délka pojezdu [mm]", 0, 100000)
    angle_deg = _number(angle_deg, "Směr sondy [°]", -36000, 36000)
    spread_deg = _number(spread_deg, "Rozevření [°]", 0, 45)
    default_tolerance = auto_tolerance(mode, scan_step, target_step)
    tolerance = default_tolerance if tolerance_mm is None else _number(
        tolerance_mm, "Tolerance zachycení [mm]", 0, 1000)
    if mode not in ("line", "face", "plan"):
        raise CoverageError("Zvol pojezd po ploše (face) nebo po přímce (line).")
    if mode == "plan" and (not positions or region is None):
        raise CoverageError("Plán dráhy nemá žádnou polohu sondy.")
    if bool(faces) == bool(points):
        raise CoverageError("Vyber cílové plochy, nebo kontrolované body (právě jednu možnost).")
    # Ověřit parametry paprsku i tehdy, když na pojezdu nebude žádná platná poloha.
    initial_beam = trace_beam(geo, placement, beta, bounces, max_length, refraction)
    if faces:
        surface = _Surface(geo.part, target_step, faces)
        nodes, triangles = surface.nodes, surface.triangles
        centers, areas = surface.centers, surface.areas
        reasons = [""] * len(centers)
    else:
        nodes, triangles, centers, areas, reasons = [], [], [], [], []
        for raw in points:
            if len(raw) != 3 or any(isinstance(v, bool) or not math.isfinite(v) for v in raw):
                raise CoverageError("Kontrolovaný bod musí mít tři konečné souřadnice.")
            point = tuple(float(v) for v in raw)
            state = geo.classify(point)
            if state == "outside":
                raise CoverageError("Kontrolovaný bod leží mimo materiál dílu.")
            reason = "Geometrie bodu není jednoznačná." if state == "unknown" else ""
            if state == "surface":
                reason = " ".join(geo.surface_at(point).reasons)
            centers.append(point)
            areas.append(0.0)
            reasons.append(reason)
    if not centers:
        raise CoverageError("Kontrolovanou oblast se nepodařilo rozdělit – vyber jinou plochu.")
    candidates = (plan_positions(positions) if mode == "plan"
                  else _scan_positions(placement, mode, scan_step, length_mm))
    result = _evaluate_samples(geo, placement, centers, reasons, candidates, initial_beam,
                               mode=mode, scan_step=scan_step, target_step=target_step,
                               length_mm=length_mm, angle_deg=angle_deg, tolerance=tolerance,
                               spread_deg=spread_deg, beta=beta, bounces=bounces,
                               max_length=max_length, refraction=refraction,
                               nodes=nodes, triangles=triangles, faces=bool(faces),
                               region=region)
    covered = CoverageMap(nodes, triangles, centers, areas, *result,
                          time.monotonic() - started)
    search = auto_tolerance(mode, scan_step)  # krok cíle hledání paprsků nezhustí
    if tolerance < search - 1e-9:
        covered.assumptions["tolerance_warning"] = (
            f"Tolerance zachycení {tolerance:g} mm je menší než krok pojezdu × "
            f"{'0,71' if mode in ('face', 'plan') else '0,6'} = {search:.3g} mm – hledání "
            "nemusí najít všechny paprsky a pokrytí může vyjít nižší.")
    return covered


def plan_positions(positions: Any) -> list[Point]:
    """Polohy plánu dráhy jako trojice čísel (v pořadí jízdy) se stejnou mezí jako pojezd."""
    candidates = [tuple(float(v) for v in p) for p in positions or ()]
    if len(candidates) > MAX_POSITIONS:
        raise CoverageError("Plán dráhy má příliš mnoho poloh – zvětši rozteč.")
    return candidates


def _scan_positions(placement: Placement, mode: str, scan_step: float,
                    length_mm: float) -> list[Point]:
    """Společná mřížka pojezdu; lze ověřit ještě před objemovými průniky."""
    face = placement.surface.face
    if mode == "face":
        candidates = _grid_face(face, scan_step)
        # Na malé kruhové/ořezané ploše mohou všechny rohy hrubé UV buňky ležet vně.
        # Skutečně přiložená sonda je rovněž známá kandidátní poloha.
        if not any(math.dist(p, placement.origin) < 1e-6 for p in candidates):
            candidates.append(placement.origin)
    else:
        count = math.ceil(length_mm / scan_step)
        if count + 1 > MAX_POSITIONS:
            raise CoverageError("Přímá dráha má příliš mnoho poloh – zvětši krok výpočtu.")
        candidates = [tuple(o + d * min(i * scan_step, length_mm)
                            for o, d in zip(placement.origin, placement.x_dir, strict=True))
                      for i in range(count + 1)]
    if len(candidates) > MAX_POSITIONS:
        raise CoverageError("Pojezd má příliš mnoho poloh – zvětši krok výpočtu.")
    return candidates


def _on_contact(geo: PartGeometry, face: Any, centers: list[Point | None]) -> set[int]:
    """Vzorky ležící na ploše přiložení. První rameno paprsku z nich jen vychází – do místa
    nemíří, takže ho nepokrývá (jinak by sonda „pokryla“ plochu, na které stojí)."""
    from build123d import Face

    face = face if isinstance(face, Face) else Face(face)
    box = face.bounding_box()
    low = (box.min.X - 1e-6, box.min.Y - 1e-6, box.min.Z - 1e-6)
    high = (box.max.X + 1e-6, box.max.Y + 1e-6, box.max.Z + 1e-6)
    found = set()
    for k, point in enumerate(centers):
        if point is None or not all(lo <= v <= hi for v, lo, hi in zip(point, low, high,
                                                                     strict=True)):
            continue
        if geo.surface_at(point, face).distance < 1e-6:
            found.add(k)
    return found


def _evaluate_samples(geo: PartGeometry, placement: Placement,
                      centers: list[Point | None], reasons: list[str], candidates: list[Point],
                      initial_beam: BeamPath, *, mode: str, scan_step: float,
                      target_step: float, length_mm: float, angle_deg: float, tolerance: float,
                      spread_deg: float, beta: float | None, bounces: int | None,
                      max_length: float | None, refraction: Refraction | None,
                      nodes: list | None = None, triangles: list | None = None,
                      faces: bool = False, region: PlanRegion | None = None) -> tuple:
    """Stejné ověřování přiložení a ramen pro plochy, body i objemové vzorky.

    None znamená známou objemovou váhu bez spolehlivého vnitřního bodu.
    Důvod nejistoty takového vzorku nelze paprskem přepsat.
    """
    if (len(candidates) > MAX_POSITIONS
            or len(candidates) * len(centers) * (initial_beam.bounces + 1) > MAX_COMPARISONS):
        raise CoverageError("Výpočet je příliš jemný – zvětši krok nebo zmenši cílovou oblast.")
    face = placement.surface.face
    on_contact = _on_contact(geo, face, centers)  # první rameno z nich jen vychází
    states = ["uncertain" if r else "uncovered" for r in reasons]
    hits: list[CoverageHit | None] = [None] * len(centers)
    valid, uncertain = 0, 0
    slope = math.tan(math.radians(spread_deg))
    resolved: dict = {}
    beam_options = dict(beta=beta, bounces=bounces, max_length=max_length, refraction=refraction)
    for candidate in candidates:
        # Přímka nesmí přichytit bod mimo ořezanou plochu k jejímu okraji.
        surf = geo.surface_at(candidate, face)
        if surf.distance > 1e-6:
            continue
        placed = place(geo, placement.probe, candidate, angle=angle_deg, face=face)
        if not placed.ok and placed.state != "uncertain":
            continue
        if region is not None and not region.allows(placed):
            continue  # zakázaná zóna plánu
        valid += int(placed.ok)
        uncertain += int(not placed.ok)
        beam = trace_beam(geo, placed, beta, bounces, max_length, refraction)
        for leg in beam.legs:
            ax, ay, az = leg.start
            dx, dy, dz = leg.direction
            previous = leg.cumulative_length - leg.length
            skip = on_contact if leg.index == 1 else ()
            for k, point in enumerate(centers):
                if point is None or states[k] == "covered" or k in skip:
                    continue
                tx, ty, tz = point
                vx, vy, vz = tx - ax, ty - ay, tz - az
                projection = vx * dx + vy * dy + vz * dz
                # Disk osy/kužele na rameni, bez kulového prodloužení za konce ramene.
                if projection < -1e-7 or projection > leg.length + 1e-7:
                    continue
                along = min(leg.length, max(0.0, projection))
                radius = tolerance + (previous + along) * slope
                h2 = (vx - along * dx)**2 + (vy - along * dy)**2 + (vz - along * dz)**2
                if h2 > radius**2 + 1e-12:
                    continue
                certain = placed.ok and leg.certain and not reasons[k]
                hit = CoverageHit(leg.index, previous + along, placed.origin)
                physical_radius = (previous + along) * slope
                if h2 > physical_radius**2 + 1e-10:
                    target = (tx, ty, tz)
                    if faces and mode == "line" and spread_deg == 0:
                        target = _line_triangle_point(nodes, triangles[k], placed, leg)
                        if target is None:
                            continue
                    if placed.surface.kind == "plane":
                        verified = _resolve_axis_hit(geo, placed, target, beam, leg, beam_options,
                                                     placement.origin, mode, length_mm,
                                                     scan_step, angle_deg, resolved, region)
                        if verified is None:
                            continue
                        hit, verified_certain = verified
                        certain = verified_certain and not reasons[k]
                    else:
                        certain = False
                states[k] = "covered" if certain else "uncertain"
                hits[k] = hit
    for k, state in enumerate(states):
        if state == "uncertain" and not reasons[k]:
            reasons[k] = ("Zásah jen v numerické toleranci na zakřivené ploše, "
                          "z nejistého přiložení nebo nejistého ramene paprsku.")
    assumptions = {**initial_beam.assumptions, "coverage_algorithm": ALGORITHM,
                   "mode": mode, "scan_step_mm": scan_step, "target_step_mm": target_step,
                   "length_mm": length_mm, "angle_deg": angle_deg, "tolerance_mm": tolerance,
                   "spread_deg": spread_deg, "probe": placement.probe.to_dict(),
                   "source": placement.origin, "interpolated_positions_checked": len(resolved),
                   "contact_samples": len(on_contact)}
    return states, hits, reasons, len(candidates), valid, uncertain, assumptions


@dataclass(frozen=True)
class Convergence:
    fine_pct: float
    coarse_pct: float
    delta_pct: float
    stable: bool
    tolerances: tuple[float, float] = (0.0, 0.0)  # tolerance jemného a hrubého běhu [mm]

    @property
    def text(self) -> str:
        return (f"Citlivost na krok: největší rozdíl tří stavů {self.delta_pct:.2f} "
                "procentního bodu "
                f"(pokryto {self.fine_pct:.2f} % / {self.coarse_pct:.2f} % při 2× kroku, "
                f"tolerance {self.tolerances[0]:.3g} / {self.tolerances[1]:.3g} mm); "
                + ("stabilní do 1 p. b." if self.stable else "zjemni krok výpočtu."))


def check_convergence(geo: PartGeometry, placement: Placement, *,
                      fine: CoverageMap | None = None, **kwargs: Any) -> Convergence:
    """Porovná krok a dvojnásobný krok (CLI předá již spočítaný jemný běh). Hrubý běh hledá
    aspoň tak hustě jako jemný: tolerance = max(tolerance jemného běhu, automatická tolerance
    hrubých kroků). Na rovině se každý zásah přesně ověří, takže větší poloměr hledání
    pokrytí nezvětší neprávem; na zakřivené ploše dává jen „nelze spolehlivě vyhodnotit“."""
    if fine is None:
        fine = compute(geo, placement, **kwargs)
    a = fine.assumptions
    steps = (a["scan_step_mm"] * 2, a["target_step_mm"] * 2)
    coarse_tolerance = max(a["tolerance_mm"], auto_tolerance(a["mode"], *steps))
    coarse = compute(geo, placement, **(kwargs | {
        "scan_step": steps[0], "target_step": steps[1], "tolerance_mm": coarse_tolerance}))
    delta = max(abs(fine.percent(s) - coarse.percent(s)) for s in STATES)
    result = Convergence(fine.percent("covered"), coarse.percent("covered"), delta, delta <= 1,
                         (a["tolerance_mm"], coarse_tolerance))
    a.update(convergence={"fine_pct": {s: fine.percent(s) for s in STATES},
                          "coarse_pct": {s: coarse.percent(s) for s in STATES},
                          "delta_pp": delta, "coarse_steps_mm": steps,
                          "tolerance_mm": a["tolerance_mm"],
                          "coarse_tolerance_mm": coarse_tolerance, "rule": CONVERGENCE_RULE},
             convergence_text=result.text)
    return result
