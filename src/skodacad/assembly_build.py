"""Sestavení sestavy: najde soubory komponent, postaví každý zdroj jednou a dá kopie do poloh.

Stavy komponenty (S9): ``ok``, ``missing`` (soubor nenalezen), ``unreadable`` (není JSON,
není ŠkodaCAD, novější verze, chybná struktura), ``error`` (díl nedopadl celý ``ok`` jako
u exportu dílu, chybná poloha, příliš hluboko) a ``cycle`` (podsestava vede zpět na sebe).
Vadná komponenta v sestavě zůstane a jen se nekreslí; záznam v souboru se nikdy nemění.

Kopie téhož dílu sdílí tvar a liší se jen polohou (OCCT ``Location``). Průniky mezi nimi
proto smí jít jen nedestruktivně (``ndt.geometry._common``) – výchozí průnik zapisuje do
sdílených hran (P5.1, průzkum P4).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skodacad.assembly import MAX_COMPONENTS, MAX_DEPTH, Assembly, AssemblyError
from skodacad.assembly import fingerprint as assembly_fingerprint
from skodacad.document import ASSEMBLY_KIND, FORMAT, Document, DocumentError
from skodacad.expressions import ExpressionError, evaluate, resolve_parameters

LABELS = {"ok": "ok", "missing": "chybí", "unreadable": "nečitelná", "error": "chyba dílu",
          "cycle": "cyklus"}
ANGLE_DIGITS = 9  # úhly z tlačítek se ukládají zaokrouhlené (90, ne 89,99999999999999)

Matrix = tuple[tuple[float, float, float], tuple[float, float, float],
               tuple[float, float, float]]


# --- otočení kolem pevných os X → Y → Z -------------------------------------------------


def _cos_sin(degrees: float) -> tuple[float, float]:
    """Přesné hodnoty pro násobky 90° (cos 90° jinak vyjde 6·10⁻¹⁷)."""
    if degrees % 90 == 0:
        return ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))[int(degrees // 90) % 4]
    radians = math.radians(degrees)
    return math.cos(radians), math.sin(radians)


def _multiply(a: Matrix, b: Matrix) -> Matrix:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
                 for i in range(3))  # type: ignore[return-value]


def axis_matrix(axis: str, degrees: float) -> Matrix:
    c, s = _cos_sin(degrees)
    if axis == "x":
        return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))
    if axis == "y":
        return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))
    if axis == "z":
        return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))
    raise AssemblyError(f"Neznámá osa „{axis}“, povolené: x, y, z.")


def rotation_matrix(angles: Sequence[float]) -> Matrix:
    """Otočení o úhly [rx, ry, rz] kolem pevných os: nejdřív X, pak Y, pak Z (R = Rz·Ry·Rx)."""
    rx, ry, rz = angles
    return _multiply(axis_matrix("z", rz), _multiply(axis_matrix("y", ry), axis_matrix("x", rx)))


def _clean(degrees: float) -> float:
    value = round(degrees, ANGLE_DIGITS) + 0.0  # bez „-0“
    if value <= -180.0:
        value += 360.0
    return int(value) if value.is_integer() else value


def angles_of(matrix: Matrix) -> list[float]:
    """Zpět na úhly [rx, ry, rz] (pevné osy X → Y → Z), zaokrouhlené na 1e-9°."""
    sy = -matrix[2][0]
    if abs(sy) >= 1 - 1e-12:  # osa Y otočená o ±90°: X a Z splynou, X dostane 0
        ry = 90.0 if sy > 0 else -90.0
        rx = 0.0
        rz = math.degrees(math.atan2(-matrix[0][1], matrix[1][1]))
    else:
        ry = math.degrees(math.asin(max(-1.0, min(1.0, sy))))
        rx = math.degrees(math.atan2(matrix[2][1], matrix[2][2]))
        rz = math.degrees(math.atan2(matrix[1][0], matrix[0][0]))
    return [_clean(rx), _clean(ry), _clean(rz)]


def turned(angles: Sequence[float], axis: str, degrees: float) -> list[float]:
    """Úhly po otočení o ``degrees`` kolem pevné osy sestavy (tlačítka ±90°)."""
    return angles_of(_multiply(axis_matrix(axis, degrees), rotation_matrix(angles)))


def location(position: Sequence[float], angles: Sequence[float]) -> Any:
    """Poloha build123d z posunu a úhlů – matice se sestaví přímo, bez pořadí build123d
    (to je jiné: Intrinsic.XYZ by dalo jinou polohu)."""
    from build123d import Location
    from OCP.gp import gp_Trsf

    m = rotation_matrix(angles)
    trsf = gp_Trsf()
    trsf.SetValues(*m[0], float(position[0]), *m[1], float(position[1]),
                   *m[2], float(position[2]))
    return Location(trsf)


# --- výsledek ------------------------------------------------------------------------


@dataclass
class ComponentStatus:
    """Stav jedné komponenty (i uvnitř podsestavy – ``ids`` je cesta id od kořene)."""

    ids: tuple[str, ...]
    label: str
    source: str  # cesta, jak je zapsaná v sestavě
    state: str = "ok"
    reason: str = ""
    kind: str = ""  # "part" / "assembly" / "" (nepodařilo se zjistit)
    fingerprint: str = ""  # otisk receptu, jak je teď v souboru
    changed: bool = False  # liší se od otisku uloženého v sestavě (S5)
    warnings: list[str] = field(default_factory=list)
    file: Path | None = None  # skutečný soubor zdroje
    fixed: bool = False

    @property
    def depth(self) -> int:
        return len(self.ids) - 1


@dataclass
class Instance:
    """Kopie dílu v poloze: tvar sdílí se zdrojem, liší se jen polohou."""

    ids: tuple[str, ...]
    file: Path
    part: Any  # build123d Part posunutý do polohy
    material: str
    volume_mm3: float
    mass_kg: float | None


@dataclass
class AssemblyResult:
    statuses: list[ComponentStatus] = field(default_factory=list)
    instances: list[Instance] = field(default_factory=list)
    parameters: dict[str, float] = field(default_factory=dict)
    error: str = ""  # chyba celé sestavy (parametry, příliš mnoho komponent)

    @property
    def complete(self) -> bool:
        """Úplná sestava: bez chyby a všechny komponenty ok (export a kontroly jen tehdy)."""
        return not self.error and all(status.state == "ok" for status in self.statuses)

    @property
    def problems(self) -> list[str]:
        lines = [self.error] if self.error else []
        for status in self.statuses:
            if status.state != "ok":
                lines.append(f"{status.label} ({status.source}): {LABELS[status.state]} – "
                             f"{status.reason}")
        return lines

    @property
    def warnings(self) -> list[str]:
        return [f"{status.label}: {warning}" for status in self.statuses
                for warning in status.warnings]

    @property
    def volume_mm3(self) -> float:
        return sum(instance.volume_mm3 for instance in self.instances)

    @property
    def mass_kg(self) -> float | None:
        """Součet hmotností; None, když některý materiál nemá známou hustotu."""
        masses = [instance.mass_kg for instance in self.instances]
        return None if any(mass is None for mass in masses) else sum(masses)  # type: ignore

    def status(self, ids: str | Sequence[str]) -> ComponentStatus:
        key = (ids,) if isinstance(ids, str) else tuple(ids)
        for status in self.statuses:
            if status.ids == key:
                return status
        raise AssemblyError(f"Sestava nemá komponentu {' / '.join(key)}.")

    def compound(self) -> Any:
        """Všechny kopie v polohách jako jeden tvar (pro kreslení a obálku)."""
        from build123d import Compound

        return Compound([instance.part for instance in self.instances])

    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
        if not self.instances:
            return None
        box = self.compound().bounding_box()
        return tuple(box.min), tuple(box.max)  # type: ignore[return-value]


# --- nalezení a načtení zdrojů ---------------------------------------------------------


def locate(folder: Path, relative: str) -> tuple[Path | None, str]:
    """Najde soubor komponenty s přesnou velikostí písmen (S4).

    Vrací (soubor nebo None, upozornění). Na systému, který velikost písmen nerozlišuje,
    se soubor najde i s jinou – pak upozornění, že jinde by se nenašel."""
    current = folder
    mismatch: list[str] = []
    for part in relative.split("/"):
        if part == "..":
            current = current.parent
            continue
        try:
            names = os.listdir(current)
        except OSError:
            return None, ""
        if part in names:
            current = current / part
            continue
        similar = [name for name in names if name.casefold() == part.casefold()]
        if not similar:
            return None, ""
        mismatch.append(f"„{part}“ je na disku „{similar[0]}“")
        current = current / similar[0]
    if not current.is_file():
        return None, ""
    if mismatch:
        return current, ("velikost písmen v cestě nesouhlasí (" + ", ".join(mismatch)
                         + ") – na systému, který rozlišuje velká a malá písmena, by se "
                         "soubor nenašel")
    return current, ""


@dataclass
class Source:
    """Načtený zdroj komponenty: díl, nebo podsestava."""

    file: Path
    digest: str  # SHA-256 bajtů souboru – klíč mezipaměti sestavených dílů
    document: Document | None = None
    assembly: Assembly | None = None

    @property
    def kind(self) -> str:
        return "assembly" if self.assembly is not None else "part"

    @property
    def fingerprint(self) -> str:
        if self.assembly is not None:
            return assembly_fingerprint(self.assembly)
        from skodacad.ndt.study import part_fingerprint

        return part_fingerprint(self.document)


def read_source(file: Path) -> Source:
    """Načte soubor dílu nebo sestavy; chyba = ``AssemblyError`` s českým důvodem."""
    try:
        raw = file.read_bytes()
    except OSError as exc:
        raise AssemblyError(f"soubor nejde přečíst ({exc.strerror or exc}).") from None
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AssemblyError("soubor není platný JSON.") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise AssemblyError("soubor není model ŠkodaCAD.")
    try:
        if data.get("kind") == ASSEMBLY_KIND:
            return Source(file, digest, assembly=Assembly.from_dict(data))
        return Source(file, digest, document=Document.from_dict(data))
    except DocumentError as exc:
        raise AssemblyError(str(exc)) from None


# --- sestavení -----------------------------------------------------------------------


@dataclass
class Built:
    """Sestavený díl v mezipaměti (podle souboru a jeho bajtů)."""

    part: Any = None
    problem: str = ""
    material: str = ""
    volume_mm3: float = 0.0
    mass_kg: float | None = None


def build_part(document: Document) -> Built:
    """Postaví díl; použije se jen úplný díl (stejné pravidlo jako export dílu, P1.4 E1)."""
    from skodacad.properties import compute
    from skodacad.rebuild import part_problem, rebuild

    result = rebuild(document)
    problem = part_problem(result)
    if problem:
        return Built(problem=problem)
    properties = compute(result.part, document.material)
    return Built(part=result.part, material=document.material,
                 volume_mm3=properties.volume_mm3, mass_kg=properties.mass_kg)


Builder = Callable[[Document], Built]


class Cache:
    """Mezipaměť sestavených dílů: klíč = skutečný soubor + SHA-256 jeho bajtů.

    Změněný soubor má jiný otisk bajtů, takže se postaví znovu; nezměněný jen jednou,
    ať je v sestavě kolikrát chce."""

    def __init__(self, builder: Builder = build_part) -> None:
        self.builder = builder
        self._parts: dict[tuple[str, str], Built] = {}

    def part(self, source: Source) -> Built:
        key = (str(source.file), source.digest)
        if key not in self._parts:
            # Staré verze téhož souboru už neplatí – drží jen paměť.
            for old in [k for k in self._parts if k[0] == key[0]]:
                del self._parts[old]
            self._parts[key] = self.builder(source.document)
        return self._parts[key]


def build(assembly: Assembly, file: str | Path, cache: Cache | None = None) -> AssemblyResult:
    """Sestaví sestavu ze souboru ``file`` – cesty komponent jsou vůči jeho složce.

    Soubor nemusí obsahovat ``assembly`` (může jít o neuložené úpravy), slouží jako
    počátek cest a první článek řetězu, podle kterého se pozná cyklus."""
    cache = cache or Cache()
    result = AssemblyResult()
    try:
        result.parameters = resolve_parameters(assembly.parameters)
    except ExpressionError as exc:
        result.error = f"Parametry sestavy: {exc}"
        return result
    root = Path(file).resolve()
    _build_level(assembly, root.parent, (), None, [root], result, cache, result.parameters)
    if len(result.statuses) > MAX_COMPONENTS:
        result.error = (f"Sestava má po rozbalení podsestav {len(result.statuses)} komponent, "
                        f"nejvýš {MAX_COMPONENTS}.")
        result.instances.clear()
    return result


def _build_level(assembly: Assembly, folder: Path, prefix: tuple[str, ...], parent: Any,
                 chain: list[Path], result: AssemblyResult, cache: Cache,
                 parameters: dict[str, float]) -> None:
    for component in assembly.components:
        if len(result.statuses) > MAX_COMPONENTS:
            return
        status = ComponentStatus(ids=(*prefix, component.id), label=component.label,
                                 source=component.path, fixed=component.fixed)
        result.statuses.append(status)
        file, warning = locate(folder, component.path)
        if warning:
            status.warnings.append(warning)
        if file is None:
            status.state, status.reason = "missing", f"soubor {component.path} se nenašel"
            continue
        status.file = file.resolve()
        if status.file in chain:
            names = " → ".join(p.name for p in [*chain, status.file])
            status.state, status.reason = "cycle", f"podsestava vede zpět na sebe: {names}"
            continue
        try:
            source = read_source(status.file)  # skutečný soubor = jeden klíč mezipaměti
        except AssemblyError as exc:
            status.state, status.reason = "unreadable", str(exc)
            continue
        status.kind = source.kind
        status.fingerprint = source.fingerprint
        if component.fingerprint and component.fingerprint != status.fingerprint:
            status.changed = True
            status.warnings.append("zdroj se od posledního uložení sestavy změnil – "
                                   "zkontroluj polohy")
        try:
            position = [evaluate(value, parameters) for value in component.position]
            angles = [evaluate(value, parameters) for value in component.rotation]
        except ExpressionError as exc:
            status.state, status.reason = "error", f"poloha: {exc}"
            continue
        if not all(math.isfinite(value) for value in (*position, *angles)):
            status.state, status.reason = "error", "poloha není konečné číslo"
            continue
        placed = location(position, angles)
        world = placed if parent is None else parent * placed
        if source.assembly is not None:
            if len(status.ids) >= MAX_DEPTH:
                status.state = "error"
                status.reason = f"příliš mnoho úrovní podsestav (nejvýš {MAX_DEPTH})"
                continue
            try:
                inner = resolve_parameters(source.assembly.parameters)
            except ExpressionError as exc:
                status.state, status.reason = "error", f"parametry podsestavy: {exc}"
                continue
            _build_level(source.assembly, status.file.parent, status.ids, world,
                         [*chain, status.file], result, cache, inner)
            continue
        built = cache.part(source)
        if built.problem:
            status.state, status.reason = "error", built.problem
            continue
        result.instances.append(Instance(ids=status.ids, file=status.file,
                                         part=built.part.moved(world),
                                         material=built.material,
                                         volume_mm3=built.volume_mm3, mass_kg=built.mass_kg))



def reachable(assembly: Assembly, file: str | Path) -> set[Path]:
    """Soubory, na které sestava vede (i přes podsestavy) – jen čte, díly nestaví.
    Slouží ke kontrole cyklu před vložením podsestavy."""
    found: set[Path] = set()

    def walk(level: Assembly, folder: Path, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        for component in level.components:
            target, _warning = locate(folder, component.path)
            if target is None:
                continue
            target = target.resolve()
            if target in found:
                continue
            found.add(target)
            try:
                source = read_source(target)
            except AssemblyError:
                continue
            if source.assembly is not None:
                walk(source.assembly, target.parent, depth + 1)

    walk(assembly, Path(file).resolve().parent, 1)
    return found
