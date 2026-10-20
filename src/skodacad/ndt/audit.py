"""Předběžný NDT audit – zpráva o geometrickém posouzení (etapa 14).

Návrh a schválené hranice jsou v ``docs/ndt/25-navrh-etapa-14.md``. Audit nic nového nepočítá:
dostane hotové výsledky metod (mapa pokrytí UT, návrh poloh, plán dráhy, mapy PT, MT, RT, mapa
tloušťky stěny) a sjednotí je:

- každý výsledek převede na jednotná **místa** (bod, plocha nebo objem, stav, důvody),
- sousední místa se stejným stavem spojí do **problémových míst** (do 1,6 × krok sítě),
- sepíše **zprávu** (HTML, CSV míst, podrobná CSV studií) s obecným upozorněním
  a s povinným upozorněním každé zahrnuté metody doslova.

Audit nevybírá metodu ani normativní postup a nikdy nepíše „vyhovuje“. Stav studie v auditu
je spočítáno / neprovedeno / nedostupné s důvodem; „nelze spolehlivě vyhodnotit“ je stav míst
uvnitř spočítaného výsledku a ve zprávě je vždy zvlášť.
"""

from __future__ import annotations

import base64
import csv
import html
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from skodacad.ndt import (
    DISCLAIMER,
    MT_DISCLAIMER,
    PT_DISCLAIMER,
    RT_DISCLAIMER,
    UT_DISCLAIMER,
)
from skodacad.ndt.geometry import Point
from skodacad.ndt.pt import COLORS

ALGORITHM = "ndt-audit 1"
TITLE = "Předběžný NDT audit – zpráva o geometrickém posouzení"
NOTE = ("Zpráva je seznam podnětů k ověření kvalifikovanou osobou. Neobsahuje výběr metody, "
        "normativní postup ani rozhodnutí o shodě.")
NOT_INCLUDED = ("Zpráva neobsahuje výběr metody, normativní postup, rozhodnutí o shodě, "
                "detekovatelnost vad, dávku ani radiační ochranu. Popisuje jen výpočet nad "
                "modelem dílu, ne provedenou zkoušku.")
PERCENT_NOTE = ("Procenta vyjadřují jen geometrický podíl plochy nebo objemu oblasti studie, "
                "nikoli pravděpodobnost nalezení vady.")
LINK = 1.6  # dvě místa patří k jednomu problémovému místu do 1,6 × krok sítě
STATUSES = {"done": "spočítáno", "skipped": "neprovedeno", "unavailable": "nedostupné"}
GROUP_ORDER = {"blocked": 0, "uncertain": 1, "limited": 2, "ok": 3}
METHODS = {"UT": "ultrazvuková", "PT": "kapilární", "MT": "magnetická prášková",
           "RT": "radiografická", "TL": "mapa tloušťky stěny"}
DISCLAIMERS = {"UT": UT_DISCLAIMER, "PT": PT_DISCLAIMER, "MT": MT_DISCLAIMER,
               "RT": RT_DISCLAIMER}
THICKNESS_ID = "tl"  # záznam mapy tloušťky stěny (není studie)
THICKNESS_STATES = {"ok": "Tloušťka aspoň mez", "blocked": "Pod mezí",
                    "uncertain": "Tloušťku nejde změřit"}
UT_GROUPS = {"covered": "ok", "uncovered": "blocked", "uncertain": "uncertain"}
UT_UNCOVERED = "z žádné spočítané polohy sondy paprsek místo nezasáhne"


class AuditError(ValueError):
    """Chybný vstup auditu (zpráva je česky)."""


def _dec(value: float, digits: int = 1) -> str:
    text = f"{value:.{digits}f}"
    if text.startswith("-") and float(text) == 0:
        text = text[1:]  # bez „-0,0“
    return text.replace(".", ",")


def _cz(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}".replace(".", ",")


# --- jednotná místa výsledku ------------------------------------------------------------------


@dataclass(frozen=True)
class Spot:
    """Jedno místo výsledku metody: bod (u objemu může chybět), váha, stav, důvody."""

    point: Point | None
    weight: float  # mm², mm³ nebo 1 (body bez plochy)
    state: str  # stav metody (klíč)
    reasons: tuple[tuple[str, str], ...] = ()  # (krátký popis, celá věta)


@dataclass
class Layer:
    """Výsledek jedné metody převedený na jednotná místa."""

    states: dict[str, str]  # stav metody → český název (od nejlepšího)
    groups: dict[str, str]  # stav metody → skupina barvy ok / limited / blocked / uncertain
    spots: list[Spot]
    unit: str
    step: float
    algorithms: tuple[str, ...]

    @property
    def total(self) -> float:
        return sum(s.weight for s in self.spots)

    def amount(self, state: str) -> float:
        return sum(s.weight for s in self.spots if s.state == state)

    def percent(self, state: str) -> float:
        total = self.total
        return 100 * self.amount(state) / total if total else 0.0

    def group_percent(self, group: str) -> float:
        return sum(self.percent(state) for state in self.states
                   if self.groups.get(state) == group)


def _coverage_layer(result: Any) -> Layer:
    """Mapa geometrického pokrytí UT (plochy nebo body, Etapa 06)."""
    from skodacad.ndt import coverage, geometry, ut

    weighted = result.total_area > 0
    spots = []
    for point, area, state, reason in zip(result.centers, result.areas, result.states,
                                          result.reasons, strict=True):
        reasons: tuple[tuple[str, str], ...] = ()
        if state == "uncovered":
            reasons = ((UT_UNCOVERED, reason or UT_UNCOVERED),)
        elif state == "uncertain":
            label = reason or "nejistý zásah"
            reasons = ((label, label),)
        spots.append(Spot(tuple(point), area if weighted else 1.0, state, reasons))
    return Layer(dict(coverage.STATES), dict(UT_GROUPS), spots, "mm²" if weighted else "bodů",
                 float(result.assumptions.get("target_step_mm") or 1.0),
                 (coverage.ALGORITHM, ut.ALGORITHM, geometry.ALGORITHM))


def _volume_layer(result: Any) -> Layer:
    """Objemové pokrytí cíle UT (07B)."""
    from skodacad.ndt import coverage, geometry, ut, volume_coverage, welds

    spots = []
    for sample, state, reason in zip(result.samples, result.states, result.reasons,
                                     strict=True):
        reasons: tuple[tuple[str, str], ...] = ()
        if state == "uncovered":
            reasons = ((UT_UNCOVERED, reason or UT_UNCOVERED),)
        elif state == "uncertain":
            label = reason or sample.reason or "nejistý zásah"
            reasons = ((label, label),)
        point = tuple(sample.point) if sample.point is not None else None
        spots.append(Spot(point, sample.volume_mm3, state, reasons))
    return Layer(dict(coverage.STATES), dict(UT_GROUPS), spots, "mm³",
                 float(result.assumptions.get("target_step_mm") or 1.0),
                 (volume_coverage.ALGORITHM, coverage.ALGORITHM, ut.ALGORITHM, welds.ALGORITHM,
                  geometry.ALGORITHM))


def _sample_layer(result: Any, module: Any, unit: str, extra: tuple[str, ...]) -> Layer:
    """Mapa PT nebo MT: vzorky s plochou, stavem a důvody (druh, věta)."""
    spots = [Spot(tuple(s.point), s.area, s.state,
                  tuple((module.REASONS.get(kind, kind), text) for kind, text in s.reasons))
             for s in result.samples]
    return Layer(dict(module.STATES), {state: state for state in module.STATES}, spots, unit,
                 float(result.step_mm), (module.ALGORITHM, *extra))


def _rt_layer(result: Any) -> Layer:
    from skodacad.ndt import geometry, rt

    names = [p.setup.name for p in result.projections]
    spots = []
    for s in result.samples:
        reasons = []
        for name, shot in zip(names, s.shots, strict=True):
            if shot.state == "ok":
                continue
            reasons += [(rt.REASONS.get(kind, kind), f"{name}: {text}")
                        for kind, text in shot.reasons]
        point = tuple(s.point) if s.point is not None else None
        spots.append(Spot(point, s.weight, s.state, tuple(reasons) if s.state != "ok" else ()))
    return Layer(dict(rt.STATES), {state: state for state in rt.STATES}, spots, result.unit,
                 float(result.step_mm), (rt.ALGORITHM, geometry.ALGORITHM))


def _thickness_layer(result: Any) -> Layer:
    limit = result.settings.limit
    if limit is None:
        raise AuditError("Mapa tloušťky stěny nemá nastavenou mez – v auditu nemá co hledat.")
    spots = []
    below = f"tloušťka pod mezí {_dec(limit, 2)} mm"
    unknown = "tloušťku nejde změřit (za plochou chybí protější stěna nebo koncové echo)"
    for point, value, area in zip(result.centers, result.values, result.areas, strict=True):
        if value is None:
            spots.append(Spot(tuple(point), area, "uncertain", ((unknown, unknown),)))
        elif value < limit:
            spots.append(Spot(tuple(point), area, "blocked",
                              ((below, f"tloušťka {_dec(value, 2)} mm < {_dec(limit, 2)} mm"),)))
        else:
            spots.append(Spot(tuple(point), area, "ok"))
    return Layer(dict(THICKNESS_STATES), {state: state for state in THICKNESS_STATES}, spots,
                 "mm²", float(result.step), ("mapa tloušťky stěny (paprsek s koncovým echem)",))


def layer_of(result: Any) -> Layer:
    """Výsledek libovolné metody → jednotná místa. Neznámý výsledek = ``AuditError``."""
    from skodacad.ndt import geometry, mt, pt
    from skodacad.ndt.access import ALGORITHM as ACCESS
    from skodacad.ndt.access import AccessResult
    from skodacad.ndt.coverage import CoverageMap
    from skodacad.ndt.mt import MtMap
    from skodacad.ndt.plan import ALGORITHM as PLAN
    from skodacad.ndt.plan import PlanResult
    from skodacad.ndt.pt import PtMap
    from skodacad.ndt.rt import RtMap
    from skodacad.ndt.volume_coverage import VolumeCoverageMap
    from skodacad.thickness_map import ThicknessMap

    if isinstance(result, AccessResult):
        if result.union is None:
            raise AuditError("Návrh poloh nenašel žádnou použitelnou variantu – není co shrnout.")
        found = layer_of(result.union)
        found.algorithms = (ACCESS, *found.algorithms)
        return found
    if isinstance(result, PlanResult):
        if result.coverage is None:
            raise AuditError("Plán dráhy byl ověřen bez pokrytí – není co shrnout.")
        found = layer_of(result.coverage.coverage)
        found.algorithms = (PLAN, *found.algorithms)
        return found
    if isinstance(result, CoverageMap):
        return _coverage_layer(result)
    if isinstance(result, VolumeCoverageMap):
        return _volume_layer(result)
    if isinstance(result, PtMap):
        return _sample_layer(result, pt, "mm²", (geometry.ALGORITHM,))
    if isinstance(result, MtMap):
        return _sample_layer(result, mt, "mm²", (pt.ALGORITHM, geometry.ALGORITHM))
    if isinstance(result, RtMap):
        return _rt_layer(result)
    if isinstance(result, ThicknessMap):
        return _thickness_layer(result)
    raise AuditError(f"Výsledek typu {type(result).__name__} audit neumí shrnout.")


# --- problémová místa ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Place:
    """Problémové místo: sousední místa jedné studie se stejným stavem."""

    id: str  # např. „S2-03“
    study_id: str
    study_name: str
    method: str
    state: str
    label: str  # český název stavu metody
    group: str  # ok / limited / blocked / uncertain (barva)
    amount: float
    unit: str
    share: float  # % z oblasti studie
    count: int
    center: Point | None
    low: Point | None
    high: Point | None
    reasons: tuple[tuple[str, float], ...]  # (důvod, % místa)
    example: str  # celá věta nejčastějšího důvodu

    def reason_text(self) -> str:
        return "; ".join(f"{label} ({_dec(share, 0)} %)" for label, share in self.reasons)


def _clusters(spots: list[Spot], link: float) -> list[list[Spot]]:
    """Spojí místa se vzájemnou vzdáleností do ``link`` (mřížka buněk + sjednocování)."""
    located = [s for s in spots if s.point is not None]
    parent = list(range(len(located)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cells: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for i, spot in enumerate(located):
        cells[tuple(math.floor(v / link) for v in spot.point)].append(i)
    limit = link * link
    for (cx, cy, cz), members in cells.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    others = cells.get((cx + dx, cy + dy, cz + dz))
                    if not others:
                        continue
                    for i in members:
                        a = located[i].point
                        for j in others:
                            if j <= i:
                                continue
                            b = located[j].point
                            if sum((p - q) ** 2 for p, q in zip(a, b, strict=True)) <= limit:
                                ri, rj = root(i), root(j)
                                if ri != rj:
                                    parent[rj] = ri
    groups: dict[int, list[Spot]] = defaultdict(list)
    for i, spot in enumerate(located):
        groups[root(i)].append(spot)
    out = list(groups.values())
    loose = [s for s in spots if s.point is None]
    if loose:
        out.append(loose)
    return out


def find_places(layer: Layer, study_id: str, study_name: str, method: str) -> list[Place]:
    """Problémová místa jedné studie, seřazená červená → šedá → oranžová, pak podle velikosti."""
    total = layer.total
    raw = []
    by_state: dict[str, list[Spot]] = defaultdict(list)
    for spot in layer.spots:
        if layer.groups.get(spot.state, "ok") != "ok":
            by_state[spot.state].append(spot)
    for state, spots in by_state.items():
        for cluster in _clusters(spots, LINK * layer.step):
            weight = sum(s.weight for s in cluster)
            counts: dict[str, float] = defaultdict(float)
            examples: dict[str, str] = {}
            for spot in cluster:
                for label, text in dict(spot.reasons).items():
                    counts[label] += spot.weight
                    examples.setdefault(label, text)
            reasons = tuple(sorted(((label, 100 * w / weight if weight else 0.0)
                                    for label, w in counts.items()), key=lambda r: -r[1]))
            points = [s.point for s in cluster if s.point is not None]
            if points:
                weights = [s.weight or 1.0 for s in cluster if s.point is not None]
                center = tuple(sum(p[k] * w for p, w in zip(points, weights, strict=True))
                               / sum(weights) for k in range(3))
                low = tuple(min(p[k] for p in points) for k in range(3))
                high = tuple(max(p[k] for p in points) for k in range(3))
            else:
                center = low = high = None
            raw.append((state, weight, len(cluster), center, low, high, reasons,
                        examples.get(reasons[0][0], "") if reasons else ""))
    raw.sort(key=lambda r: (GROUP_ORDER.get(layer.groups.get(r[0], "ok"), 9), -r[1]))
    prefix = study_id.upper()
    return [Place(f"{prefix}-{n:02d}", study_id, study_name, method, state,
                  layer.states.get(state, state), layer.groups.get(state, "ok"), weight,
                  layer.unit, 100 * weight / total if total else 0.0, count, center, low, high,
                  reasons, example)
            for n, (state, weight, count, center, low, high, reasons, example)
            in enumerate(raw, start=1)]


# --- záznam studie a celý audit -------------------------------------------------------------------


@dataclass
class AuditEntry:
    """Jedna studie (nebo mapa tloušťky) v auditu."""

    study_id: str
    name: str
    method: str  # UT / PT / MT / RT / TL
    status: str  # done / skipped / unavailable
    reason: str = ""  # proč neprovedeno / nedostupné, co udělat
    source: str = ""  # co se spočítalo a odkud
    study_state: str = ""  # platná / zastaralá …
    verified: str = ""
    target: str = ""  # popis oblasti
    record: dict[str, Any] | None = None  # celý záznam studie z modelu
    result: Any = None  # výsledek metody (souhrn, CSV, mapa ve 3D)
    seconds: float = 0.0

    @cached_property
    def layer(self) -> Layer | None:
        return layer_of(self.result) if self.status == "done" and self.result is not None \
            else None

    @cached_property
    def places(self) -> list[Place]:
        layer = self.layer
        return [] if layer is None else find_places(layer, self.study_id, self.name,
                                                    self.method)

    def summary(self) -> list[str]:
        """Souhrn metody – tytéž řádky jako v panelu a CSV."""
        return list(self.result.summary()) if self.result is not None else []

    def shares(self) -> list[tuple[str, str, float]]:
        """(stav, český název, %) – v pořadí stavů metody."""
        layer = self.layer
        if layer is None:
            return []
        return [(state, label, layer.percent(state)) for state, label in layer.states.items()]

    def uncertain_percent(self) -> float:
        layer = self.layer
        return 0.0 if layer is None else layer.group_percent("uncertain")

    def csv_name(self) -> str:
        if self.study_id == THICKNESS_ID:
            return "mapa-tloustky.csv"
        return f"studie-{self.study_id}-{self.method.lower()}.csv"


@dataclass
class AuditResult:
    """Výsledek auditu: hlavička, záznamy studií, problémová místa, zpráva."""

    model: str
    path: str
    fingerprint: str
    material: str
    created: str
    build: str
    libraries: str
    entries: list[AuditEntry]
    operator: str = ""
    complete: bool = True
    seconds: float = 0.0

    def methods(self) -> list[str]:
        """Zahrnuté metody v pevném pořadí UT, PT, MT, RT."""
        present = {e.method for e in self.entries}
        return [m for m in DISCLAIMERS if m in present]

    def disclaimers(self) -> list[str]:
        """Obecné upozornění a povinné upozornění každé zahrnuté metody, doslova."""
        return [DISCLAIMER, *(DISCLAIMERS[m] for m in self.methods())]

    def places(self) -> list[Place]:
        found = [p for e in self.entries for p in e.places]
        return sorted(found, key=lambda p: (GROUP_ORDER.get(p.group, 9), -p.share, p.id))

    def entry(self, study_id: str) -> AuditEntry:
        for e in self.entries:
            if e.study_id == study_id:
                return e
        raise AuditError(f"Studie „{study_id}“ v auditu není.")

    def header(self) -> list[str]:
        lines = [f"Model: {self.model}" + (f" ({self.path})" if self.path else ""),
                 f"Otisk dílu: {self.fingerprint}; materiál: {self.material or 'neuvedený'}.",
                 f"Vytvořeno: {self.created}; {self.build}; {self.libraries}.",
                 f"Algoritmus zprávy: {ALGORITHM}."]
        if self.operator:
            lines.append(f"Zpracoval(a): {self.operator}.")
        if not self.complete:
            lines.append("Audit byl zastaven – nedokončené studie jsou „neprovedeno“.")
        return lines

    def overview(self, entry: AuditEntry) -> str:
        """Jeden řádek přehledu studie (CLI, panel)."""
        head = (f"{entry.study_id} {entry.name} ({METHODS.get(entry.method, entry.method)}): "
                f"{STATUSES[entry.status]}")
        if entry.status != "done":
            return f"{head} – {entry.reason}"
        shares = ", ".join(f"{label} {_dec(pct, 2)} %" for _state, label, pct in entry.shares())
        return f"{head} – {shares}; problémových míst {len(entry.places)}."

    def summary(self) -> list[str]:
        """Text pro příkazovou řádku: upozornění, hlavička, přehled, problémová místa."""
        lines = [TITLE, *self.disclaimers(), NOTE, PERCENT_NOTE, *self.header(), "Studie:"]
        lines += [f"  {self.overview(e)}" for e in self.entries]
        places = self.places()
        lines.append(f"Problémová místa: {len(places)}.")
        for p in places:
            where = ("poloha neurčena" if p.center is None
                     else "střed " + "; ".join(_dec(v) for v in p.center) + " mm")
            lines.append(f"  {p.id} {p.label}: {_dec(p.amount)} {p.unit} ({_dec(p.share)} % "
                         f"studie), {where}; {p.reason_text()}")
        lines.append(NOT_INCLUDED)
        return lines

    # --- výstupy -----------------------------------------------------------------------

    def write_csv(self, path: str | Path) -> Path:
        """CSV problémových míst (středník, desetinná čárka, nahoře povinná upozornění)."""
        path = Path(path)
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            for text in (TITLE, *self.disclaimers(), NOTE, PERCENT_NOTE, *self.header()):
                writer.writerow([text])
            writer.writerow(["označení", "studie", "název studie", "metoda", "stav", "velikost",
                             "jednotka", "podíl ze studie [%]", "bodů", "střed x [mm]",
                             "střed y [mm]", "střed z [mm]", "od x [mm]", "od y [mm]",
                             "od z [mm]", "do x [mm]", "do y [mm]", "do z [mm]", "důvody",
                             "příklad důvodu", "nastavení"])
            for p in self.places():
                source = (f"zpráva, oddíl studie {p.study_id}; "
                          f"{self.entry(p.study_id).csv_name()}")
                writer.writerow([p.id, p.study_id, p.study_name, p.method, p.label,
                                 _cz(p.amount), p.unit, _cz(p.share), p.count,
                                 *(_cz(v) for v in (p.center or (None,) * 3)),
                                 *(_cz(v) for v in (p.low or (None,) * 3)),
                                 *(_cz(v) for v in (p.high or (None,) * 3)),
                                 p.reason_text(), p.example, source])
        return path

    def rt_previews(self) -> dict[str, list[tuple[str, bytes]]]:
        """Náhledy prozařované tloušťky RT studií (PNG v paměti, bez Qt)."""
        from skodacad.ndt.rt import RtMap, png_bytes, preview_rgb

        out: dict[str, list[tuple[str, bytes]]] = {}
        for e in self.entries:
            if e.status != "done" or not isinstance(e.result, RtMap):
                continue
            for i, (projection, image) in enumerate(zip(e.result.projections, e.result.images,
                                                        strict=True)):
                if image is None:
                    continue
                scale = max(1, 480 // max(image.columns, 1))
                radius = 0.45 * e.result.step_mm * (projection.magnification or 1)
                if e.result.kind == "volume":
                    radius = 0.75 * e.result.step_mm * (projection.magnification or 1)
                png = png_bytes(*preview_rgb(image, e.result.marks(i), scale, radius))
                out.setdefault(e.study_id, []).append(
                    (f"Náhled prozařované tloušťky – projekce {projection.setup.name} (není "
                     "radiografický snímek)", png))
        return out

    def html(self, images: dict[str, list[tuple[str, bytes]]] | None = None) -> str:
        """Zpráva jako jeden soubor HTML (styl i obrázky uvnitř, tiskne se na A4)."""
        pictures: dict[str, list[tuple[str, bytes]]] = defaultdict(list)
        for key, items in (images or {}).items():
            pictures[key] += items
        for key, items in self.rt_previews().items():
            pictures[key] += items
        e = html.escape
        out = ["<!doctype html>", '<html lang="cs"><head><meta charset="utf-8">',
               f"<title>{e(TITLE)} – {e(self.model)}</title>", f"<style>{_CSS}</style>",
               "</head><body>", f"<h1>{e(TITLE)}</h1>",
               "<p class=meta>" + "<br>".join(e(line) for line in self.header()) + "</p>",
               '<section class=warn><h2>Povinná upozornění</h2>']
        out += [f"<p>{e(text)}</p>" for text in (*self.disclaimers(), NOTE, PERCENT_NOTE)]
        out.append("</section>")
        out += ["<h2>Přehled studií</h2>", "<table><tr><th>Studie</th><th>Metoda</th>"
                "<th>Oblast</th><th>Stav studie</th><th>Ověření</th><th>Audit</th>"
                "<th>Výsledek</th><th>Nelze spolehlivě vyhodnotit</th><th>Doba</th></tr>"]
        for entry in self.entries:
            result = ("<br>".join(f'<span class="dot {_group(entry, s)}">■</span> {e(label)} '
                                  f"{_dec(pct, 2)} %" for s, label, pct in entry.shares())
                      if entry.status == "done" else e(entry.reason))
            uncertain = f"{_dec(entry.uncertain_percent(), 2)} %" if entry.status == "done" \
                else "–"
            out.append(f'<tr><td><a href="#{_anchor(entry)}">{e(entry.study_id)}</a> '
                       f"{e(entry.name)}</td><td>{e(METHODS.get(entry.method, entry.method))}"
                       f"</td><td>{e(entry.target)}</td><td>{e(entry.study_state)}</td>"
                       f"<td>{e(entry.verified)}</td><td class={entry.status}>"
                       f"{e(STATUSES[entry.status])}</td><td>{result}</td><td>{uncertain}</td>"
                       f"<td>{_dec(entry.seconds)} s</td></tr>")
        out.append("</table>")
        places = self.places()
        out.append(f"<h2>Problémová místa ({len(places)})</h2>")
        if places:
            out.append("<table><tr><th>Místo</th><th>Studie</th><th>Stav</th><th>Velikost</th>"
                       "<th>Podíl</th><th>Střed [mm]</th><th>Rozsah [mm]</th><th>Důvody</th></tr>")
            for p in places:
                center = "neurčen" if p.center is None else "; ".join(_dec(v) for v in p.center)
                span = ("–" if p.low is None else
                        " až ".join("; ".join(_dec(v) for v in q) for q in (p.low, p.high)))
                out.append(f'<tr><td>{e(p.id)}</td><td><a href="#{e("studie-" + p.study_id)}">'
                           f"{e(p.study_id)}</a></td><td><span class=\"dot {p.group}\">■</span> "
                           f"{e(p.label)}</td><td>{_dec(p.amount)} {e(p.unit)}</td>"
                           f"<td>{_dec(p.share)} %</td><td>{e(center)}</td><td>{e(span)}</td>"
                           f"<td>{e(p.reason_text())}<br><small>{e(p.example)}</small></td></tr>")
            out.append("</table>")
        else:
            out.append("<p>Žádné problémové místo ve spočítaných studiích.</p>")
        missing = [x for x in self.entries if x.status != "done"]
        if missing:
            out.append("<h2>Neprovedeno a nedostupné</h2><ul>")
            out += [f"<li><b>{e(x.study_id)} {e(x.name)}</b> – {e(STATUSES[x.status])}: "
                    f"{e(x.reason)}</li>" for x in missing]
            out.append("</ul>")
        out.append("<h2>Studie podrobně</h2>")
        for entry in self.entries:
            out.append(f'<section class=study id="{_anchor(entry)}">')
            out.append(f"<h3>{e(entry.study_id)} – {e(entry.name)} "
                       f"({e(METHODS.get(entry.method, entry.method))})</h3>")
            out.append(f"<p><b>Audit:</b> {e(STATUSES[entry.status])}"
                       + (f" – {e(entry.reason)}" if entry.reason else "") + "</p>")
            if entry.source:
                out.append(f"<p><b>Spočítáno:</b> {e(entry.source)}</p>")
            if entry.layer is not None:
                out.append(f"<p><b>Algoritmy:</b> {e(', '.join(entry.layer.algorithms))}; "
                           f"krok sítě {_dec(entry.layer.step, 2)} mm; podrobná data "
                           f"{e(entry.csv_name())}.</p>")
            for caption, png in pictures.get(entry.study_id, []):
                data = base64.b64encode(png).decode("ascii")
                out.append(f'<figure><img alt="{e(caption)}" src="data:image/png;base64,{data}">'
                           f"<figcaption>{e(caption)}</figcaption></figure>")
            if entry.places:
                out.append("<p><b>Problémová místa:</b> " + ", ".join(
                    f"{e(p.id)} ({e(p.label)}, {_dec(p.share)} %)" for p in entry.places)
                    + "</p>")
            lines = entry.summary()
            if lines:
                out.append("<details open><summary>Souhrn metody (předpoklady, zdroje "
                           "hodnot)</summary><ul>")
                out += [f"<li>{e(line)}</li>" for line in lines]
                out.append("</ul></details>")
            if entry.record is not None:
                out.append("<details><summary>Záznam studie z modelu (JSON – z něj jde výpočet "
                           "zopakovat)</summary><pre>"
                           + e(json.dumps(entry.record, ensure_ascii=False, indent=2))
                           + "</pre></details>")
            out.append("</section>")
        out += [f"<h2>Co zpráva neobsahuje</h2><p>{e(NOT_INCLUDED)}</p>",
                f"<p class=meta>{e(self.build)} · {e(ALGORITHM)}</p>", "</body></html>"]
        return "\n".join(out)

    def write_folder(self, folder: str | Path,
                     images: dict[str, list[tuple[str, bytes]]] | None = None) -> list[Path]:
        """Složka se zprávou: ``zprava.html``, ``mista.csv`` a podrobná CSV studií."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        report = folder / "zprava.html"
        report.write_text(self.html(images), encoding="utf-8")
        written = [report, self.write_csv(folder / "mista.csv")]
        for entry in self.entries:
            if entry.status == "done" and hasattr(entry.result, "write_csv"):
                written.append(entry.result.write_csv(folder / entry.csv_name()))
        return written


def _anchor(entry: AuditEntry) -> str:
    return f"studie-{entry.study_id}"


def _group(entry: AuditEntry, state: str) -> str:
    return entry.layer.groups.get(state, "ok") if entry.layer is not None else "ok"


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(255 * v):02x}" for v in rgb)


_CSS = (
    "body{font-family:Arial,Helvetica,sans-serif;font-size:10pt;margin:16mm;color:#222}"
    "h1{font-size:16pt}h2{font-size:13pt;margin-top:18pt}h3{font-size:11pt}"
    "table{border-collapse:collapse;width:100%;margin:6pt 0}"
    "th,td{border:1px solid #bbb;padding:3pt 5pt;vertical-align:top;text-align:left}"
    "th{background:#eee}.meta{color:#555}.warn{border:1px solid #c90;background:#fff8e6;"
    "padding:4pt 10pt}.warn p{margin:4pt 0;font-style:italic}"
    "td.skipped,td.unavailable{color:#b45309;font-weight:bold}td.done{color:#166534}"
    "pre{white-space:pre-wrap;font-size:8pt;background:#f6f6f6;padding:6pt}"
    "figure{margin:6pt 0}img{max-width:100%;border:1px solid #ccc}"
    "figcaption{font-size:9pt;color:#555}.study{page-break-inside:avoid}"
    "small{color:#555}@page{size:A4;margin:12mm}"
    + "".join(f".dot.{k}{{color:{_hex(v)}}}" for k, v in COLORS.items())
)
