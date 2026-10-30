"""Sestavení sestavy: najde soubory komponent, postaví každý zdroj jednou a dá kopie do poloh.

Stavy komponenty (S9): ``ok``, ``missing`` (soubor nenalezen), ``unreadable`` (není JSON,
není ŠkodaCAD, novější verze, chybná struktura), ``error`` (díl nedopadl celý ``ok`` jako
u exportu dílu, chybná poloha, příliš hluboko) a ``cycle`` (podsestava vede zpět na sebe).
Vadná komponenta v sestavě zůstane a jen se nekreslí; záznam v souboru se nikdy nemění.

Kopie téhož dílu sdílí tvar a liší se jen polohou (OCCT ``Location``). Průniky mezi nimi
proto smí jít jen nedestruktivně (``ndt.geometry._common``) – výchozí průnik zapisuje do
sdílených hran (P5.1, průzkum P4).

Vazby (P5.3) se řeší po úrovních: každá komponenta se nejdřív postaví ve svých
souřadnicích, řešič (``assembly_solve``) dopočítá polohy a teprve potom se kopie umístí.
Nové polohy jsou v ``AssemblyResult.solved``; zapisuje je ``AssemblySession`` (M9).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from skodacad.assembly import (
    BASE_AXES,
    BASE_PLANES,
    CONSTRAINT_TYPES,
    MAX_COMPONENTS,
    MAX_DEPTH,
    Assembly,
    AssemblyError,
    Component,
)
from skodacad.assembly import fingerprint as assembly_fingerprint
from skodacad.document import ASSEMBLY_KIND, FORMAT, Document, DocumentError
from skodacad.expressions import ExpressionError, evaluate, resolve_parameters

LABELS = {"ok": "ok", "missing": "chybí", "unreadable": "nečitelná", "error": "chyba dílu",
          "cycle": "cyklus", "pending": "počítá se"}
CONSTRAINT_LABELS = {"ok": "splněna", "conflict": "ve sporu", "missing": "odkaz nenalezen",
                     "pending": "počítá se", "error": "chyba"}
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


def tidy(value: float) -> float:
    """Číslo polohy pro soubor: zaokrouhlené na 1e-9, celé bez „.0“ a bez „-0“."""
    value = round(value, 9) + 0.0
    return int(value) if value.is_integer() else value


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
    freedom: tuple[int, int] | None = None  # (posuny, otočení), které vazby neurčují (M6)
    held: str = ""  # vazby s ní nehýbou: "fixed" / "anchor" (drží skupinu) / "expression"
    conflict: bool = False  # vazby její skupiny jsou ve sporu

    @property
    def depth(self) -> int:
        return len(self.ids) - 1

    @property
    def freedom_text(self) -> str:
        """Stav komponenty podle vazeb česky; prázdný, když na ni žádná vazba nevede."""
        if self.conflict:
            return "ve sporu"
        if self.held:
            return {"fixed": "pevná", "anchor": "drží polohu skupiny vazeb",
                    "expression": "poloha výrazem – vazby s ní nehýbou"}[self.held]
        if self.freedom is None:
            return ""
        translations, rotations = self.freedom
        if not translations and not rotations:
            return "plně určená"
        parts = []
        if translations:
            parts.append(f"{translations} {_plural(translations, 'posun', 'posuny', 'posunů')}")
        if rotations:
            parts.append(f"{rotations} otočení")
        return "volná: " + ", ".join(parts)


def _plural(count: int, one: str, few: str, many: str) -> str:
    return one if count == 1 else few if 2 <= count <= 4 else many


@dataclass
class ConstraintStatus:
    """Stav jedné vazby (``ids`` = cesta id komponent od kořene + id vazby)."""

    ids: tuple[str, ...]
    label: str
    type: str
    components: tuple[str, str]
    state: str = "ok"
    reason: str = ""
    residual: float = 0.0  # zbytek rovnic vazby po řešení (mm / bez jednotky)

    @property
    def depth(self) -> int:
        return len(self.ids) - 1

    @property
    def type_label(self) -> str:
        return CONSTRAINT_TYPES[self.type]


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
    constraints: list[ConstraintStatus] = field(default_factory=list)
    # Polohy podle vazeb, které se liší od zapsaných: cesta id → (posun, úhly) pro soubor.
    solved: dict[tuple[str, ...], tuple[list[float], list[float]]] = field(
        default_factory=dict)
    # Tvar komponent nejvyšší úrovně v jejich vlastních souřadnicích (odkazy vazeb z okna).
    local_shapes: dict[str, Any] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        """Úplná sestava: bez chyby, všechny komponenty ok a všechny vazby splněné
        (export a kontroly jen tehdy)."""
        return (not self.error and all(status.state == "ok" for status in self.statuses)
                and all(status.state == "ok" for status in self.constraints))

    @property
    def problems(self) -> list[str]:
        lines = [self.error] if self.error else []
        for status in self.statuses:
            if status.state != "ok":
                lines.append(f"{status.label} ({status.source}): {LABELS[status.state]} – "
                             f"{status.reason}")
        for constraint in self.constraints:
            if constraint.state != "ok":
                lines.append(f"Vazba {constraint.label}: "
                             f"{CONSTRAINT_LABELS[constraint.state]} – {constraint.reason}")
        return lines

    def constraint(self, ids: str | Sequence[str]) -> ConstraintStatus:
        key = (ids,) if isinstance(ids, str) else tuple(ids)
        for status in self.constraints:
            if status.ids == key:
                return status
        raise AssemblyError(f"Sestava nemá vazbu {' / '.join(key)}.")

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
    pending: bool = False  # čeká na výpočet v pomocném procesu (okno)

    @classmethod
    def from_result(cls, document: Document, result: Any) -> Built:
        """Z výsledku přepočtu dílu; použije se jen úplný díl (pravidlo P1.4 E1)."""
        from skodacad.properties import compute
        from skodacad.rebuild import part_problem

        problem = part_problem(result)
        if problem:
            return cls(problem=problem)
        properties = compute(result.part, document.material)
        return cls(part=result.part, material=document.material,
                   volume_mm3=properties.volume_mm3, mass_kg=properties.mass_kg)


def build_part(document: Document) -> Built:
    """Postaví díl hned (testy, příkazová řádka)."""
    from skodacad.rebuild import rebuild

    return Built.from_result(document, rebuild(document))


Builder = Callable[[Document], Built]


class Cache:
    """Mezipaměť sestavených dílů: klíč = skutečný soubor + SHA-256 jeho bajtů.

    Změněný soubor má jiný otisk bajtů, takže se postaví znovu; nezměněný jen jednou,
    ať je v sestavě kolikrát chce."""

    def __init__(self, builder: Builder | None = build_part) -> None:
        """``builder=None``: díly se nestaví hned – čekají v ``waiting``, okno je spočítá
        v pomocném procesu a uloží přes ``store`` (S12, okno nestojí)."""
        self.builder = builder
        self._parts: dict[tuple[str, str], Built] = {}
        self.waiting: dict[tuple[str, str], Source] = {}

    @staticmethod
    def key(source: Source) -> tuple[str, str]:
        return str(source.file), source.digest

    def part(self, source: Source) -> Built:
        key = self.key(source)
        if key not in self._parts:
            if self.builder is None:
                self.waiting[key] = source
                return Built(pending=True)
            self.store(source, self.builder(source.document))
        return self._parts[key]

    def store(self, source: Source, built: Built) -> None:
        key = self.key(source)
        # Staré verze téhož souboru už neplatí – drží jen paměť.
        for old in [k for k in self._parts if k[0] == key[0] and k != key]:
            del self._parts[old]
        self._parts[key] = built
        self.waiting.pop(key, None)


def build(assembly: Assembly, file: str | Path, cache: Cache | None = None) -> AssemblyResult:
    """Sestaví sestavu ze souboru ``file`` – cesty komponent jsou vůči jeho složce.

    Soubor nemusí obsahovat ``assembly`` (může jít o neuložené úpravy), slouží jako
    počátek cest a první článek řetězu, podle kterého se pozná cyklus."""
    cache = cache or Cache()
    cache.waiting.clear()  # čeká jen to, co tato sestava opravdu potřebuje
    result = AssemblyResult()
    try:
        result.parameters = resolve_parameters(assembly.parameters)
    except ExpressionError as exc:
        result.error = f"Parametry sestavy: {exc}"
        return result
    root = Path(file).resolve()
    result.instances = _build_level(assembly, root.parent, (), [root], result, cache,
                                    result.parameters)
    if len(result.statuses) > MAX_COMPONENTS:
        result.error = (f"Sestava má po rozbalení podsestav {len(result.statuses)} komponent, "
                        f"nejvýš {MAX_COMPONENTS}.")
        result.instances.clear()
    for ids in result.solved:
        if len(ids) > 1:  # podsestavu sestava nikdy nepřepisuje (S11)
            status = result.status(ids[:-1])
            note = ("polohy uvnitř podsestavy se podle jejích vazeb přepočítaly – otevři ji "
                    "a ulož")
            if note not in status.warnings:
                status.warnings.append(note)
    return result


@dataclass
class _Piece:
    """Komponenta jedné úrovně: kopie v jejích vlastních souřadnicích a její poloha."""

    component: Component
    status: ComponentStatus
    instances: list[Instance] = field(default_factory=list)
    position: list[float] | None = None  # vyhodnocená poloha (None = nejde umístit)
    angles: list[float] | None = None
    pending: bool = False  # díl (nebo díl v podsestavě) se ještě počítá
    _shape: Any = None

    @property
    def expression(self) -> bool:
        return any(isinstance(value, str)
                   for value in (*self.component.position, *self.component.rotation))

    def shape(self) -> Any:
        """Tvar komponenty v jejích souřadnicích (díl, nebo celá podsestava)."""
        if self._shape is None:
            if self.status.kind == "part":
                self._shape = self.instances[0].part
            else:
                from build123d import Compound

                self._shape = Compound([instance.part for instance in self.instances])
        return self._shape


def _build_level(assembly: Assembly, folder: Path, prefix: tuple[str, ...],
                 chain: list[Path], result: AssemblyResult, cache: Cache,
                 parameters: dict[str, float]) -> list[Instance]:
    """Postaví jednu úroveň sestavy; vrátí kopie dílů umístěné v souřadnicích úrovně."""
    pieces: list[_Piece] = []
    for component in assembly.components:
        if len(result.statuses) > MAX_COMPONENTS:
            break
        status = ComponentStatus(ids=(*prefix, component.id), label=component.label,
                                 source=component.path, fixed=component.fixed)
        result.statuses.append(status)
        piece = _Piece(component, status)
        pieces.append(piece)
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
        piece.position, piece.angles = position, angles
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
            first = len(result.statuses)
            piece.instances = _build_level(source.assembly, status.file.parent, status.ids,
                                           [*chain, status.file], result, cache, inner)
            piece.pending = any(inner_status.state == "pending"
                                for inner_status in result.statuses[first:])
            continue
        built = cache.part(source)
        if built.pending:
            status.state, status.reason = "pending", "díl se počítá"
            piece.pending = True
            continue
        if built.problem:
            status.state, status.reason = "error", built.problem
            continue
        piece.instances = [Instance(ids=status.ids, file=status.file, part=built.part,
                                    material=built.material, volume_mm3=built.volume_mm3,
                                    mass_kg=built.mass_kg)]
    if assembly.constraints:
        _solve_level(assembly, pieces, prefix, result, parameters)
    if not prefix:
        result.local_shapes = {piece.component.id: piece.shape() for piece in pieces
                               if piece.instances and not piece.pending}
    placed: list[Instance] = []
    for piece in pieces:
        if piece.position is None or piece.angles is None or not piece.instances:
            continue
        where = location(piece.position, piece.angles)
        placed.extend(replace(instance, part=instance.part.moved(where))
                      for instance in piece.instances)
    return placed


# --- vazby ---------------------------------------------------------------------------


class _Unresolved(Exception):
    """Odkaz vazby nejde použít (``state`` = stav vazby, zpráva česky)."""

    def __init__(self, state: str, text: str) -> None:
        super().__init__(text)
        self.state = state


def _vector(value: Any) -> Any:
    import numpy as np

    return np.array([float(v) for v in value], dtype=float)


def _feature(pieces: dict[str, _Piece], reference: dict[str, Any]) -> tuple[Any, Any]:
    """Odkaz vazby → (bod, směr) v souřadnicích komponenty: normála roviny, nebo osa."""
    from skodacad.selectors import SelectionError

    component_id = reference["component"]
    piece = pieces.get(component_id)
    if piece is None:
        raise _Unresolved("missing", f"komponenta „{component_id}“ v sestavě není")
    label = piece.status.label
    if piece.pending:
        raise _Unresolved("pending", f"díl „{label}“ se ještě počítá")
    if piece.status.state != "ok" or piece.position is None or not piece.instances:
        state = LABELS[piece.status.state] if piece.status.state != "ok" else "nic nekreslí"
        raise _Unresolved("missing", f"komponenta „{label}“ se nesestavila ({state})")
    try:
        return feature_of(piece.shape(), reference)
    except SelectionError as exc:
        raise _Unresolved("missing", f"„{label}“: {exc}") from None


def feature_of(shape: Any, reference: dict[str, Any]) -> tuple[Any, Any]:
    """(bod, směr) odkazu v souřadnicích tvaru komponenty; plocha, která zmizela,
    = ``SelectionError``."""
    from skodacad.selectors import find_face

    if "plane" in reference:
        point, normal = BASE_PLANES[reference["plane"]]
        return _vector(point), _vector(normal)
    if "axis" in reference:
        point, direction = BASE_AXES[reference["axis"]]
        return _vector(point), _vector(direction)
    spec = reference["face"]
    face, on_face = find_face(shape, spec)
    if spec["type"] == "plane":
        return _vector(on_face), _vector(face.normal_at(on_face))
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    axis = BRepAdaptor_Surface(face.wrapped).Cylinder().Axis()
    origin, direction = axis.Location(), axis.Direction()
    return (_vector((origin.X(), origin.Y(), origin.Z())),
            _vector((direction.X(), direction.Y(), direction.Z())))


def _number(value: float) -> str:
    return f"{value:.3g}".replace(".", ",")


def _solve_level(assembly: Assembly, pieces: list[_Piece], prefix: tuple[str, ...],
                 result: AssemblyResult, parameters: dict[str, float]) -> None:
    """Vyřeší vazby jedné úrovně a nové polohy zapíše do ``pieces`` a ``result.solved``."""
    import numpy as np

    from skodacad.assembly_solve import SATISFIED, Body, Link, solve

    by_id = {piece.component.id: piece for piece in pieces}
    bodies = {
        piece.component.id: Body(
            id=piece.component.id,
            rotation=np.array(rotation_matrix(piece.angles), dtype=float),
            position=_vector(piece.position),
            movable=not (piece.component.fixed or piece.expression))
        for piece in pieces if piece.position is not None and piece.angles is not None}
    links: list[Link] = []
    statuses: dict[str, ConstraintStatus] = {}
    for constraint in assembly.constraints:
        status = ConstraintStatus(ids=(*prefix, constraint.id), label=constraint.label,
                                  type=constraint.type, components=constraint.components)
        result.constraints.append(status)
        try:
            value = 0.0
            if constraint.type == "distance":
                try:
                    value = evaluate(constraint.value, parameters)
                except ExpressionError as exc:
                    raise _Unresolved("error", f"hodnota: {exc}") from None
                if not math.isfinite(value):
                    raise _Unresolved("error", "hodnota není konečné číslo")
            (pa, na), (pb, nb) = (_feature(by_id, side) for side in (constraint.a, constraint.b))
        except _Unresolved as exc:
            status.state, status.reason = exc.state, str(exc)
            continue
        a, b = constraint.components
        links.append(Link(id=constraint.id, kind=constraint.type, a=a, pa=pa,
                          na=na / np.linalg.norm(na), b=b, pb=pb, nb=nb / np.linalg.norm(nb),
                          value=value))
        statuses[constraint.id] = status
    if not links:
        return
    solution = solve(bodies, links)
    for group in solution.groups:
        names = [by_id[body_id].status.label for body_id in group.held
                 if by_id[body_id].expression]
        worst = {link.id for link in group.links if solution.residuals[link.id] > SATISFIED}
        for link in group.links:
            status = statuses[link.id]
            status.residual = solution.residuals[link.id]
            if group.satisfied or (worst and link.id not in worst):
                continue
            status.state = "conflict"
            status.reason = (f"vazby nejdou splnit současně (zbytek {_number(group.residual)} "
                             "mm)")
            if not group.bodies and not group.anchor:
                status.reason += " – obě komponenty jsou pevné nebo mají polohu výrazem"
            for name in names:
                status.reason += (f"; poloha „{name}“ je zadaná výrazem – vazby s ní nehýbou, "
                                  "nahraď výraz číslem")
        for body_id in group.held:
            piece = by_id[body_id]
            piece.status.held = "fixed" if piece.component.fixed else "expression"
        if group.anchor:
            by_id[group.anchor].status.held = "anchor"
        if not group.satisfied:
            for body_id in (*group.bodies, *([group.anchor] if group.anchor else [])):
                by_id[body_id].status.conflict = True
    for body_id, freedom in solution.freedom.items():
        by_id[body_id].status.freedom = (freedom.translations, freedom.rotations)
    for body_id, (rotation, position) in solution.poses.items():
        piece = by_id[body_id]
        new_position = [tidy(float(v)) for v in position]
        old_rotation = bodies[body_id].rotation
        same_rotation = bool(np.allclose(rotation, old_rotation, atol=1e-10, rtol=0))
        new_angles = (list(piece.component.rotation) if same_rotation
                      else angles_of(tuple(tuple(float(v) for v in row) for row in rotation)))
        if same_rotation and new_position == [tidy(v) for v in piece.position]:
            continue
        piece.position = [float(v) for v in new_position]
        piece.angles = [float(v) for v in new_angles]
        result.solved[piece.status.ids] = (new_position, new_angles)


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
