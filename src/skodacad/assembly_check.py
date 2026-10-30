"""Kontroly sestavy (P5.4, rozhodnutí K1–K12): kolize, vůle, kusovník, export STEP.

Kolize (K1): každá dvojice kopií dílů (i v podsestavách) – nejdřív síto obalových kvádrů,
pak přesný průnik jádrem **nedestruktivně** (``ndt.geometry._common``, kopie sdílí tvar).
Kolize = objem průniku nad 0,001 mm³; průnik, který jádro nespočítá, je „nelze ověřit“,
nikdy „bez kolize“. Vůle (K2): u dvojic bez kolize nejmenší vzdálenost těles; hlásí se
0 < vzdálenost < mez, vzdálenost do 1·10⁻⁶ mm je dotyk. Přijatá kolize (K3) zůstane přijatá,
dokud se objem nezmění o víc než 1 % (nejméně 0,01 mm³).

Kusovník (K6) je rozbalený, řádek = soubor dílu. Export STEP (K8) zapíše strom: kořen =
sestava, výrobek = soubor dílu (jednou), kopie = id komponenty s polohou; názvy bez
diakritiky. Kontrola, kusovník do souboru i export jdou jen z úplné sestavy (S9).

V sestavě se nic NDT nepočítá (K9) – studie dílu platí jen pro samotný díl.
"""

from __future__ import annotations

import csv
import math
import os
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from itertools import combinations
from pathlib import Path
from typing import Any

from skodacad.assembly import Accepted, AssemblyError, Checks
from skodacad.assembly_build import AssemblyResult, Instance, read_source

COLLISION_MM3 = 0.001  # průnik do této meze je dotyk, ne kolize (jako u NDT)
TOUCH_MM = 1e-6  # vzdálenost do této meze = dotyk
ACCEPT_RELATIVE = 0.01  # přijatá kolize platí, dokud se objem nezmění o víc než 1 % …
ACCEPT_MM3 = 0.01  # … nejméně však 0,01 mm³
NDT_NOTE = ("NDT studie dílů platí jen pro samotný díl – v sestavě se nepřepočítávají "
            "(sousední díl může sondě, jhu nebo zdroji zavazet).")
KINDS = {"collision": "kolize", "changed": "kolize – přijatá se změnila",
         "unknown": "nelze ověřit", "accepted": "přijatá kolize", "clearance": "malá vůle"}
PROBLEMS = ("collision", "changed", "unknown")


# --- kolize a vůle ---------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """Nález kontroly mezi dvěma kopiemi (cesty id od kořene sestavy)."""

    kind: str  # klíč z KINDS
    a: tuple[str, ...]
    b: tuple[str, ...]
    a_label: str
    b_label: str
    volume: float | None = None  # mm³ (kolize)
    distance: float | None = None  # mm (vůle)
    center: tuple[float, float, float] | None = None  # těžiště průniku (kolize)
    note: str = ""  # poznámka přijaté kolize
    reason: str = ""

    @property
    def label(self) -> str:
        return KINDS[self.kind]

    @property
    def pair(self) -> str:
        return f"{self.a_label} × {self.b_label}"

    @property
    def text(self) -> str:
        """Nález česky na jeden řádek."""
        if self.kind == "clearance":
            return f"{self.pair}: vůle {_dec(self.distance, 3)} mm"
        if self.kind == "unknown":
            return f"{self.pair}: {self.reason}"
        line = f"{self.pair}: průnik {_dec(self.volume, 3)} mm³"
        if self.kind == "accepted":
            line += f" (přijato{': ' + self.note if self.note else ''})"
        elif self.kind == "changed":
            line += f" – {self.reason}"
        return line


@dataclass
class CheckResult:
    """Výsledek kontroly (pohled – neukládá se). ``raw`` jsou nálezy před přijetím kolizí."""

    raw: list[Finding]
    pairs: int  # dvojic kopií celkem
    candidates: int  # dvojic po sítu obalových kvádrů
    touches: int  # dvojic, které se jen dotýkají
    clearance: float  # mez vůle, se kterou se počítalo (mm)
    seconds: float = 0.0
    findings: list[Finding] = field(default_factory=list)
    gone: list[Accepted] = field(default_factory=list)  # přijaté kolize, které už nejsou

    @property
    def problems(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.kind in PROBLEMS]

    @property
    def clean(self) -> bool:
        return not self.problems

    def with_accepted(self, checks: Checks) -> CheckResult:
        """Nálezy podle přijatých kolizí (K3) – bez nového výpočtu geometrie."""
        findings, seen = [], set()
        for finding in self.raw:
            if finding.kind != "collision":
                findings.append(finding)
                continue
            accepted = checks.find(finding.a, finding.b)
            if accepted is None:
                findings.append(finding)
                continue
            seen.add(accepted.key)
            limit = max(ACCEPT_MM3, ACCEPT_RELATIVE * accepted.volume)
            if abs((finding.volume or 0.0) - accepted.volume) <= limit:
                findings.append(replace(finding, kind="accepted", note=accepted.note))
            else:
                findings.append(replace(
                    finding, kind="changed", note=accepted.note,
                    reason=f"objem se změnil z {_dec(accepted.volume, 3)} mm³ – zkontroluj "
                           "ji a přijmi znovu"))
        order = {"collision": 0, "changed": 0, "unknown": 1, "clearance": 2, "accepted": 3}
        findings.sort(key=lambda f: order[f.kind])
        gone = [item for item in checks.accepted if item.key not in seen]
        return replace(self, findings=findings, gone=gone)

    def summary(self) -> list[str]:
        """Souhrn česky (okno, příkazová řádka)."""
        count = {kind: sum(1 for f in self.findings if f.kind == kind) for kind in KINDS}
        lines = [f"Dvojic kopií {self.pairs}, po sítu obálek {self.candidates}; kolize "
                 f"{count['collision'] + count['changed']}, nelze ověřit {count['unknown']}, "
                 f"vůle pod {_dec(self.clearance, 3)} mm {count['clearance']}, dotyků "
                 f"{self.touches}, přijatých kolizí {count['accepted']} "
                 f"({_dec(self.seconds, 1)} s)."]
        lines.extend(f"{finding.label.capitalize()}: {finding.text}"
                     for finding in self.findings)
        lines.extend(f"Přijatá kolize {' / '.join(item.a)} × {' / '.join(item.b)} už není – "
                     "záznam můžeš zrušit." for item in self.gone)
        if self.clean:
            lines.append("Žádná nepřijatá kolize.")
        return lines


def labels(result: AssemblyResult, ids: Sequence[str]) -> str:
    """Názvy komponent po úrovních („Podsestava / Šroub 1“)."""
    names = []
    for index in range(1, len(ids) + 1):
        try:
            names.append(result.status(ids[:index]).label)
        except AssemblyError:
            names.append(ids[index - 1])
    return " / ".join(names)


def _box(instance: Instance) -> tuple[tuple[float, ...], tuple[float, ...]]:
    box = instance.part.bounding_box(optimal=False)
    return tuple(box.min), tuple(box.max)


def _near(a: tuple, b: tuple, margin: float) -> bool:
    (amin, amax), (bmin, bmax) = a, b
    return all(amin[i] - margin <= bmax[i] and bmin[i] - margin <= amax[i] for i in range(3))


def intersection(a: Any, b: Any) -> tuple[float | None, tuple[float, float, float] | None]:
    """Objem průniku [mm³] a jeho těžiště; (None, None) = jádro průnik nespočítalo."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    from skodacad.ndt.geometry import _common

    common = _common(a, b)
    if not common.IsDone():  # OCCT 8 hlásí chyby jen přes IsDone
        return None, None
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(common.Shape(), props)
    volume = abs(props.Mass())
    if volume <= COLLISION_MM3:
        return volume, None
    point = props.CentreOfMass()
    return volume, (point.X(), point.Y(), point.Z())


def distance(a: Any, b: Any) -> float | None:
    """Nejmenší vzdálenost dvou těles [mm]; None = nejde spočítat."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    tool = BRepExtrema_DistShapeShape(getattr(a, "wrapped", a), getattr(b, "wrapped", b))
    tool.Perform()
    return tool.Value() if tool.IsDone() else None


def check(result: AssemblyResult, checks: Checks,
          progress: Callable[[int, int], None] | None = None,
          intersect: Callable[[Any, Any], tuple] = intersection,
          measure: Callable[[Any, Any], float | None] = distance) -> CheckResult:
    """Kolize a vůle všech dvojic kopií úplné sestavy (K1, K2, K3)."""
    if not result.complete:
        raise AssemblyError("Kontrolu kolizí jde spustit jen u úplné sestavy – nejdřív oprav "
                            "chybějící komponenty, chyby dílů a vazby ve sporu.")
    start = time.perf_counter()
    instances = result.instances
    boxes = [_box(instance) for instance in instances]
    pairs = list(combinations(range(len(instances)), 2))
    candidates = [(i, j) for i, j in pairs if _near(boxes[i], boxes[j], checks.clearance)]
    raw: list[Finding] = []
    touches = 0
    for done, (i, j) in enumerate(candidates, 1):
        a, b = instances[i], instances[j]
        base = dict(a=a.ids, b=b.ids, a_label=labels(result, a.ids),
                    b_label=labels(result, b.ids))
        volume, center = intersect(a.part, b.part)
        if volume is None:
            raw.append(Finding(kind="unknown", reason="průnik nejde spočítat – kolizi nelze "
                               "vyloučit", **base))
        elif volume > COLLISION_MM3:
            raw.append(Finding(kind="collision", volume=volume, center=center, **base))
        else:
            gap = measure(a.part, b.part)
            if gap is None:
                raw.append(Finding(kind="unknown", reason="vzdálenost nejde spočítat – vůli "
                                   "nelze ověřit", **base))
            elif gap <= TOUCH_MM:
                touches += 1
            elif gap < checks.clearance:
                raw.append(Finding(kind="clearance", distance=gap, **base))
        if progress is not None:
            progress(done, len(candidates))
    outcome = CheckResult(raw=raw, pairs=len(pairs), candidates=len(candidates),
                          touches=touches, clearance=checks.clearance,
                          seconds=time.perf_counter() - start)
    return outcome.with_accepted(checks)


def geometry_key(result: AssemblyResult) -> tuple:
    """Co z výsledku sestavy určuje kontrolu: komponenty, recepty dílů a polohy kopií."""
    def placement(instance: Instance) -> tuple[float, ...]:
        trsf = instance.part.location.wrapped.Transformation()
        return tuple(round(trsf.Value(r, c), 9) for r in range(1, 4) for c in range(1, 5))

    return (tuple((s.ids, s.state, s.fingerprint) for s in result.statuses),
            tuple((i.ids, placement(i)) for i in result.instances))


# --- kusovník ----------------------------------------------------------------------------


@dataclass
class BomRow:
    """Řádek kusovníku (K6): jeden soubor dílu."""

    position: int
    name: str
    path: str  # soubor vůči složce sestavy
    count: int
    material: str
    mass_kg: float | None  # 1 ks; None = neznámá hustota
    volume_mm3: float  # 1 ks
    components: list[str] = field(default_factory=list)
    ndt: int = 0  # počet NDT studií v dílu (platí jen pro díl)

    @property
    def total_kg(self) -> float | None:
        return None if self.mass_kg is None else self.mass_kg * self.count


def bill(result: AssemblyResult, assembly_file: str | Path) -> list[BomRow]:
    """Rozbalený kusovník: díly i z podsestav, řádek = soubor dílu, pořadí výskytu."""
    folder = Path(assembly_file).resolve().parent
    rows: dict[Path, BomRow] = {}
    for instance in result.instances:
        row = rows.get(instance.file)
        if row is None:
            try:
                document = read_source(instance.file).document
            except AssemblyError:
                document = None
            try:
                path = Path(os.path.relpath(instance.file, folder)).as_posix()
            except ValueError:  # jiný disk ve Windows
                path = str(instance.file)
            studies = (document.ndt or {}).get("studies", []) if document is not None else []
            row = rows[instance.file] = BomRow(
                position=len(rows) + 1,
                name=document.name if document is not None else instance.file.stem,
                path=path, count=0, material=instance.material, mass_kg=instance.mass_kg,
                volume_mm3=instance.volume_mm3, ndt=len(studies))
        row.count += 1
        row.components.append(" / ".join(instance.ids))
    return list(rows.values())


def total_mass(rows: Sequence[BomRow]) -> float | None:
    masses = [row.total_kg for row in rows]
    return None if any(mass is None for mass in masses) else sum(masses)  # type: ignore


def write_bill(rows: Sequence[BomRow], path: str | Path, title: str) -> Path:
    """Kusovník do CSV (K7): středník, UTF-8 s BOM, desetinná čárka – jako ostatní CSV."""
    path = Path(path)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow([f"Kusovník – {title}"])
        writer.writerow([NDT_NOTE])
        writer.writerow(["Pozice", "Název", "Soubor", "Kusů", "Materiál",
                         "Hmotnost 1 ks [g]", "Hmotnost celkem [g]", "Objem 1 ks [mm³]",
                         "Komponenty", "NDT studie v dílu"])
        for row in rows:
            writer.writerow([row.position, row.name, row.path, row.count, row.material,
                             _grams(row.mass_kg), _grams(row.total_kg),
                             _dec(row.volume_mm3, 3), ", ".join(row.components),
                             f"{row.ndt} (jen pro díl)" if row.ndt else ""])
        mass = total_mass(rows)
        writer.writerow(["Celkem", "", "", sum(row.count for row in rows), "", "",
                         _grams(mass), "", "", ""])
    return path


# --- export STEP -------------------------------------------------------------------------


_REPLACE = {"–": "-", "—": "-", "×": "x", "„": '"', "“": '"', "”": '"', "°": "deg"}


def ascii_name(text: str) -> str:
    """Název pro STEP bez diakritiky („Víčko“ → „Vicko“); norma STEP počítá s jiným
    kódováním než UTF-8 a jiný CAD by češtinu mohl ukázat jako nesmysl (K8)."""
    text = "".join(_REPLACE.get(ch, ch) for ch in text)
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", text)
                    if not unicodedata.combining(ch))
    return "".join(ch if 32 <= ord(ch) < 127 else "_" for ch in plain) or "sestava"


def export_step(result: AssemblyResult, path: str | Path, name: str) -> Path:
    """Úplná sestava do STEP se stromem: kořen = sestava, výrobek = soubor dílu (jednou),
    kopie = id komponenty s polohou, podsestava = vnořená sestava; jednotky mm (K8).
    Při chybě zůstane starý soubor."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.Message import Message, Message_Gravity
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    if not result.complete:
        raise AssemblyError("Export STEP jde jen z úplné sestavy – nejdřív oprav chybějící "
                            "komponenty, chyby dílů a vazby ve sporu.")

    def named(label: Any, text: str) -> Any:
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(ascii_name(text)))
        return label

    document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    levels: dict[tuple[str, ...], Any] = {(): named(tool.NewShape(), name)}
    products: dict[Path, Any] = {}
    instances = {instance.ids: instance for instance in result.instances}
    for status in result.statuses:  # rodič je vždy před svými komponentami
        parent = levels.get(status.ids[:-1])
        where = result.locations.get(status.ids)
        if parent is None or where is None:
            continue
        if status.kind == "assembly":
            child = named(tool.NewShape(), status.file.stem if status.file else status.label)
            levels[status.ids] = child
        else:
            instance = instances.get(status.ids)
            if instance is None:
                continue
            if instance.file not in products:
                products[instance.file] = named(tool.AddShape(instance.base.wrapped, False),
                                                instance.file.stem)
            child = products[instance.file]
        named(tool.AddComponent(parent, child, where.wrapped), status.ids[-1])
    tool.UpdateAssemblies()
    for printer in Message.DefaultMessenger_s().Printers():  # bez výpisů OCCT do konzole
        printer.SetTraceLevel(Message_Gravity.Message_Fail)
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    if not writer.Transfer(document, STEPControl_AsIs):
        raise AssemblyError("Sestavu nejde převést do STEP.")
    path = Path(path)
    temporary = path.with_name(path.name + ".part")
    try:
        if writer.Write(str(temporary)) != IFSelect_RetDone:
            raise AssemblyError(f"Soubor {path.name} se nepodařilo zapsat.")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


# --- pomocné ------------------------------------------------------------------------------


def _dec(value: float | None, digits: int) -> str:
    if value is None or not math.isfinite(value):
        return "?"
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{value:.0f}"
    return (text if text not in ("-0", "") else "0").replace(".", ",")


def _grams(mass_kg: float | None) -> str:
    return "?" if mass_kg is None else f"{mass_kg * 1000:.2f}".replace(".", ",")
