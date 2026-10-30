"""Otevřená sestava bez okna: úpravy komponent a vazeb, Zpět/Znovu, uložení (P5.2, P5.3).

Jako ``ModelSession`` u dílu: každá úprava jde přes ``_change`` (kopie → kontrola → přijetí),
nezměněná úprava není krok Zpět. Sestava nikdy nezapisuje do souborů dílů (S11) – uloží
jen svůj soubor. Nová sestava se hned uloží, protože cesty komponent se počítají vůči
její složce (S4).

Vazby (M7, M9, M11): polohy, které dopočítá řešič, se zapíšou do ``placement`` v téže
změně (jeden krok Zpět). Úprava, po které by vazby byly ve sporu, se nepřijme. Když se
polohy změní při sestavení (změněný soubor dílu), sestava je neuložená a ``notice`` to řekne.
"""

from __future__ import annotations

import copy
import os
import re
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from skodacad.assembly import (
    Accepted,
    Assembly,
    AssemblyError,
    Component,
    Constraint,
    check_path,
    reference_shape,
)
from skodacad.assembly_build import (
    AssemblyResult,
    Cache,
    axis_matrix,
    build,
    feature_of,
    locate,
    reachable,
    read_source,
    rotation_matrix,
    tidy,
    turned,
)
from skodacad.expressions import ExpressionError, evaluate, resolve_parameters

_UNDO_LIMIT = 100


def relative_path(file: str | Path, assembly_file: str | Path) -> str:
    """Cesta k souboru vůči složce sestavy v zápisu S4 (oddělovač „/“)."""
    target = Path(file).resolve()
    folder = Path(assembly_file).resolve().parent
    try:
        text = os.path.relpath(target, folder)
    except ValueError:
        raise AssemblyError(
            f"Soubor {target} je na jiném disku než sestava – relativní cesta nejde. "
            "Zkopíruj díl do složky projektu sestavy a vlož ho odtud.") from None
    return check_path(Path(text).as_posix())


def _base_id(file: Path) -> str:
    base = re.sub(r"[^0-9a-z]+", "_", file.stem.casefold()).strip("_")
    return base or "komponenta"


class AssemblySession:
    """Sestava otevřená k úpravám; ``result`` je poslední sestavení (synchronně)."""

    def __init__(self, cache: Cache | None = None) -> None:
        self.assembly: Assembly | None = None
        self.path: Path | None = None
        self.result: AssemblyResult | None = None
        self.dirty = False
        self.cache = cache or Cache()
        self.notice = ""  # polohy podle vazeb se při sestavení změnily (okno ukáže a smaže)
        self._checked: tuple[Any, Any] | None = None  # (klíč, výsledek kontroly) – pohled
        self._undo: list[Assembly] = []
        self._redo: list[Assembly] = []
        self._group: int | None = None

    # --- soubor ---------------------------------------------------------------------

    def new(self, path: str | Path, name: str = "Nová sestava") -> AssemblyResult:
        """Založí prázdnou sestavu a hned ji uloží (bez umístění nejde spočítat cesty)."""
        assembly = Assembly(name=name)
        assembly.save(path)
        return self._open(assembly, Path(path))

    def open(self, path: str | Path) -> AssemblyResult:
        return self._open(Assembly.load(path), Path(path))

    def _open(self, assembly: Assembly, path: Path) -> AssemblyResult:
        self.assembly, self.path = assembly, path.resolve()
        self._undo.clear()
        self._redo.clear()
        self.dirty = False
        return self.rebuild()

    def save(self, path: str | Path | None = None, copy_parts: bool = False) -> None:
        """Uloží sestavu; otisky zdrojů v pořádku se zapíšou podle souborů (S5).

        Uložení do jiné složky (Uložit jako) cesty přepočítá, aby dál vedly na tytéž
        soubory; soubor, který se nenašel, nechá tak, jak byl zapsaný. ``copy_parts``
        (uložení ukázky) zkopíruje soubory dílů do složky ``dily/`` vedle sestavy – vznikne
        samostatný projekt, který nezávisí na složce ukázek ani na disku aplikace."""
        assembly = self._require()
        target = Path(path).resolve() if path is not None else self._require_path()
        current = self.result if self.result is not None else self.rebuild()
        saved = copy.deepcopy(assembly)
        copied: dict[Path, str] = {}
        for component in saved.components:
            try:
                status = current.status(component.id)
            except AssemblyError:
                continue
            if status.fingerprint:  # zdroj se přečetl; chybějící nechá uložený otisk
                component.fingerprint = status.fingerprint
            if status.file is None:
                continue
            if copy_parts and status.kind == "part":
                component.path = _copy_part(status.file, target, copied)
            elif target != self.path:
                component.path = relative_path(status.file, target)
        saved.save(target)
        self.assembly, self.path, self.dirty = saved, target, False
        self.rebuild()

    # --- sestavení ------------------------------------------------------------------

    def rebuild(self) -> AssemblyResult:
        """Sestaví znovu – soubory dílů se čtou vždy, staví se jen ty změněné.

        Když vazby po změně dílu daly jiné polohy, zapíšou se do sestavy (bez kroku Zpět,
        není to úprava uživatele), sestava je neuložená a ``notice`` řekne, které (M11)."""
        assembly = self._require()
        result = build(assembly, self._require_path(), self.cache)
        moved = _apply_solved(assembly, result)
        if moved:
            self.dirty = True
            self.notice = ("Polohy podle vazeb se po změně dílu přepočítaly: "
                           + ", ".join(moved) + ". Zkontroluj je a ulož sestavu.")
        self.result = result
        return result

    # --- úpravy ---------------------------------------------------------------------

    def _change(self, mutate: Callable[[Assembly], None],
                require: Sequence[str] = ()) -> AssemblyResult:
        """Úprava = kopie, kontrola, sestavení s vazbami, přijetí (jeden krok Zpět).

        Nepřijme se úprava, po které by nějaká vazba byla ve sporu, jež předtím nebyla
        (M7), ani nová či změněná vazba ``require``, která nejde použít."""
        current = self._require()
        candidate = copy.deepcopy(current)
        mutate(candidate)
        if candidate == current:
            return self.result if self.result is not None else self.rebuild()
        candidate = Assembly.from_dict(candidate.to_dict())  # kontrola struktury
        try:
            resolve_parameters(candidate.parameters)
        except ExpressionError as exc:
            raise AssemblyError(str(exc)) from None
        result = build(candidate, self._require_path(), self.cache)
        self._check_constraints(result, require)
        _apply_solved(candidate, result)
        if candidate == current:  # vazby komponentu vrátily (plně určená)
            self.result = result
            return result
        self._undo.append(current)
        overflow = max(0, len(self._undo) - _UNDO_LIMIT)
        del self._undo[:overflow]
        if self._group is not None:
            self._group = max(0, self._group - overflow)
        self._redo.clear()
        self.assembly, self.result, self.dirty = candidate, result, True
        return result

    def _check_constraints(self, result: AssemblyResult, require: Sequence[str]) -> None:
        before = ({status.ids for status in self.result.constraints
                   if status.state == "conflict"} if self.result is not None else set())
        new = [status for status in result.constraints
               if status.state == "conflict" and status.ids not in before]
        for constraint_id in require:
            status = result.constraint(constraint_id)
            if status.state not in ("ok", "conflict"):
                raise AssemblyError(f"Vazbu „{status.label}“ nejde použít: {status.reason}.")
        if new:
            names = ", ".join(f"„{status.label}“" for status in new)
            raise AssemblyError(f"Vazby si odporují ({names}): {new[0].reason}. Úprava se "
                                "nepřijala, sestava zůstala beze změny.")

    def insert(self, file: str | Path, position: Sequence[Any] = (0, 0, 0),
               rotation: Sequence[Any] = (0, 0, 0), name: str = "") -> str:
        """Vloží díl nebo podsestavu ze souboru; vrátí id nové komponenty.

        První komponenta sestavy je pevná (S8). Soubor se nejdřív přečte – nečitelný,
        sestava sama nebo podsestava, která na ni vede, se nevloží vůbec."""
        assembly_file = self._require_path()
        file = Path(file).resolve()
        if file == assembly_file:
            raise AssemblyError("Sestavu nejde vložit do sebe samé.")
        path = relative_path(file, assembly_file)
        try:
            source = read_source(file)
        except AssemblyError as exc:
            raise AssemblyError(f"Soubor {file.name} nejde vložit: {exc}") from None
        if source.assembly is not None and assembly_file in reachable(source.assembly, file):
            raise AssemblyError(f"Podsestava {file.name} obsahuje tuto sestavu – vložení "
                                "by vytvořilo cyklus.")
        assembly = self._require()
        base = _base_id(file)
        numbers = [int(match.group(1)) for c in assembly.components
                   if (match := re.fullmatch(re.escape(base) + r"_(\d+)", c.id))]
        component_id = f"{base}_{max(numbers, default=0) + 1}"
        component = Component(id=component_id, path=path, position=list(position),
                              rotation=list(rotation), name=name,
                              fingerprint=source.fingerprint,
                              fixed=not assembly.components)
        self._change(lambda a: a.components.append(component))
        return component_id

    def remove(self, component_id: str) -> AssemblyResult:
        """Smaže komponentu i vazby, které na ni vedou (M10) – jeden krok Zpět."""
        self._require().component(component_id)

        def mutate(a: Assembly) -> None:
            a.components.remove(a.component(component_id))
            a.constraints = [c for c in a.constraints if component_id not in c.components]
            a.checks.accepted = [item for item in a.checks.accepted
                                 if component_id not in (item.a[0], item.b[0])]

        return self._change(mutate)

    # --- kontroly (P5.4) -----------------------------------------------------------------

    def set_clearance(self, value: float) -> AssemblyResult:
        """Mez vůle v mm (K2) – jeden krok Zpět."""
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
            raise AssemblyError("Mez vůle musí být kladné číslo v mm.")

        def mutate(a: Assembly) -> None:
            a.checks.clearance = tidy(float(value))

        return self._change(mutate)

    def accept_collision(self, a: Sequence[str], b: Sequence[str], volume: float,
                         note: str = "") -> AssemblyResult:
        """Přijme kolizi dvojice komponent s objemem průniku (K3) – jeden krok Zpět."""
        result = self.result if self.result is not None else self.rebuild()
        for ids in (a, b):
            result.status(list(ids))  # neznámá komponenta = česká chyba
        record = Accepted(a=list(a), b=list(b), volume=round(float(volume), 3),
                          note=note.strip())

        def mutate(assembly: Assembly) -> None:
            assembly.checks.accepted = [item for item in assembly.checks.accepted
                                        if item.key != record.key]
            assembly.checks.accepted.append(record)

        return self._change(mutate)

    def unaccept_collision(self, a: Sequence[str], b: Sequence[str]) -> AssemblyResult:
        key = frozenset((tuple(a), tuple(b)))
        if not any(item.key == key for item in self._require().checks.accepted):
            raise AssemblyError("Tahle dvojice komponent není mezi přijatými kolizemi.")

        def mutate(assembly: Assembly) -> None:
            assembly.checks.accepted = [item for item in assembly.checks.accepted
                                        if item.key != key]

        return self._change(mutate)

    def check(self, progress: Callable[[int, int], None] | None = None) -> Any:
        """Kolize a vůle úplné sestavy (K1, K2); výsledek si sezení pamatuje jako pohled."""
        from skodacad.assembly_check import check

        result = self.result if self.result is not None else self.rebuild()
        outcome = check(result, self._require().checks, progress=progress)
        self.store_check(outcome)
        return outcome

    def check_key(self) -> tuple | None:
        """Co určuje platnost kontroly: díly, polohy kopií a mez vůle (ne přijaté kolize)."""
        from skodacad.assembly_check import geometry_key

        if self.result is None or self.assembly is None:
            return None
        return geometry_key(self.result), self.assembly.checks.clearance

    def store_check(self, outcome: Any, key: tuple | None = None) -> bool:
        """Převezme výsledek kontroly (i z pomocného procesu). ``key`` = ``check_key`` při
        spuštění: když se sestava mezitím změnila, výsledek se nepřevezme (False)."""
        current = self.check_key()
        if current is None or current[1] != outcome.clearance or key not in (None, current):
            return False
        self._checked = (current, outcome)
        return True

    def last_check(self) -> Any:
        """Poslední kontrola, pokud pořád platí (stejné díly, polohy a mez vůle); přijaté
        kolize se do ní promítnou bez nového výpočtu. Jinak None."""
        if self._checked is None or self._checked[0] != self.check_key():
            return None
        return self._checked[1].with_accepted(self.assembly.checks)

    def bill(self) -> list[Any]:
        """Rozbalený kusovník (K6) – v okně i z neúplné sestavy (s nápisem „neúplný“)."""
        from skodacad.assembly_check import bill

        result = self.result if self.result is not None else self.rebuild()
        return bill(result, self._require_path())

    def write_bill(self, path: str | Path) -> Path:
        """Kusovník do CSV (K7) – jen z úplné sestavy."""
        from skodacad.assembly_check import write_bill

        result = self.result if self.result is not None else self.rebuild()
        if not result.complete:
            raise AssemblyError("Kusovník jde uložit jen z úplné sestavy – nejdřív oprav "
                                "chybějící komponenty, chyby dílů a vazby ve sporu.")
        return write_bill(self.bill(), path, self._require().name)

    def export_step(self, path: str | Path) -> Path:
        """Úplná sestava do STEP se stromem dílů (K8)."""
        from skodacad.assembly_check import export_step

        result = self.result if self.result is not None else self.rebuild()
        return export_step(result, path, self._require().name)

    # --- vazby (P5.3) -----------------------------------------------------------------

    def add_constraint(self, kind: str, a: dict[str, Any], b: dict[str, Any],
                       value: Any = None, name: str = "") -> str:
        """Přidá vazbu; vrátí její id. Vazba, která nejde použít nebo vede ke sporu, se
        nepřijme (česká chyba, sestava beze změny, žádný krok Zpět)."""
        assembly = self._require()
        for side in (a, b):
            if isinstance(side, dict) and isinstance(side.get("component"), str):
                assembly.component(side["component"])
        numbers = [int(match.group(1)) for c in assembly.constraints
                   if (match := re.fullmatch(r"v(\d+)", c.id))]
        data: dict[str, Any] = {"id": f"v{max(numbers, default=0) + 1}", "type": kind,
                                "a": a, "b": b}
        if name.strip():
            data["name"] = name.strip()
        if kind == "distance" or value is not None:
            data["value"] = value
        constraint = Constraint.from_dict(data, len(assembly.constraints) + 1)
        self._change(lambda x: x.constraints.append(constraint), require=[constraint.id])
        return constraint.id

    def remove_constraint(self, constraint_id: str) -> AssemblyResult:
        self._require().constraint(constraint_id)
        return self._change(
            lambda a: a.constraints.remove(a.constraint(constraint_id)))

    def set_constraint(self, constraint_id: str, value: Any = None,
                       name: str | None = None) -> AssemblyResult:
        """Nová hodnota vzdálenosti (číslo nebo výraz) nebo název vazby."""
        constraint = self._require().constraint(constraint_id)
        if value is not None and constraint.type != "distance":
            raise AssemblyError(f"Vazba „{constraint.label}“ nemá hodnotu – hodnotu má jen "
                                "vzdálenost.")

        def mutate(a: Assembly) -> None:
            target = a.constraint(constraint_id)
            if value is not None:
                target.value = value
            if name is not None:
                target.name = name.strip()

        return self._change(mutate, require=[constraint_id] if value is not None else [])

    def reference_at(self, face: Any, point: Sequence[float] | None = None) -> dict[str, Any]:
        """Kliknutá plocha kopie ve 3D → odkaz vazby v souřadnicích dílu její komponenty
        (M2): bod, směr a druh plochy, bez poloměru – najde se i po změně rozměru."""
        from skodacad.measure import face_reference
        from skodacad.picking import split_shapes
        from skodacad.selectors import SelectionError, find_face

        faces, _edges = split_shapes([face])  # kliknutí z okna je tvar OCCT
        if not faces:
            raise AssemblyError("Vazba se zadává na plochách – klikni na plochu, ne na hranu.")
        face = faces[0]
        result = self.result if self.result is not None else self.rebuild()
        instance = next((item for item in result.instances
                         if any(face.is_same(known) for known in item.part.faces())), None)
        if instance is None:
            raise AssemblyError("Kliknutá plocha nepatří k žádné komponentě – vyber ji znovu.")
        component_id = instance.ids[0]
        shape = result.local_shapes.get(component_id)
        if shape is None:
            raise AssemblyError("Komponenta se ještě počítá – zkus to za chvíli.")
        world = face_reference(face, point)["face"]
        kind = world.get("type")
        if kind not in ("plane", "cylinder"):
            raise AssemblyError("Vazby umí jen rovinné a válcové plochy – vyber jinou plochu.")
        rotation, position = self._pose(component_id)
        spec = {"at": _local(world["at"], rotation, position),
                "normal": _local(world["normal"], rotation, None), "type": kind}
        try:
            found, on_face = find_face(shape, spec)
        except SelectionError as exc:
            raise AssemblyError(str(exc)) from None
        if (on_face - type(on_face)(*spec["at"])).length > 1e-3:
            raise AssemblyError("Tuhle plochu nejde pro vazbu jednoznačně určit – klikni na ni "
                                "kousek dál od hrany.")
        return {"component": component_id, "face": spec}

    def gap(self, a: dict[str, Any], b: dict[str, Any]) -> float:
        """Dnešní vzdálenost rovin dvou odkazů ve směru normály „a“ (výchozí hodnota
        vzdálenosti, aby nová vazba díly neposunula)."""
        import numpy as np

        from skodacad.selectors import SelectionError

        result = self.result if self.result is not None else self.rebuild()
        ends = []
        for side in (a, b):
            shape = result.local_shapes.get(side["component"])
            if shape is None:
                raise AssemblyError(f"Komponenta „{side['component']}“ se nesestavila.")
            try:
                point, normal = feature_of(shape, side)
            except SelectionError as exc:
                raise AssemblyError(str(exc)) from None
            rotation, position = self._pose(side["component"])
            ends.append((rotation @ point + position, rotation @ normal))
        (pa, na), (pb, _nb) = ends
        return tidy(round(float(np.dot(pb - pa, na / np.linalg.norm(na))), 6))

    def constraint_faces(self, constraint_id: str) -> list[Any]:
        """Plochy vazby v poloze v sestavě (zvýraznění v okně); co nejde najít, vynechá."""
        from skodacad.assembly_build import location
        from skodacad.selectors import SelectionError, find_face

        constraint = self._require().constraint(constraint_id)
        result = self.result if self.result is not None else self.rebuild()
        faces = []
        for side in (constraint.a, constraint.b):
            shape = result.local_shapes.get(side["component"])
            if shape is None or "face" not in side:
                continue
            try:
                face, _point = find_face(shape, side["face"])
                rotation, position = self._pose(side["component"])
            except (SelectionError, AssemblyError):
                continue
            component = self._require().component(side["component"])
            angles = [evaluate(v, result.parameters) for v in component.rotation]
            faces.append(face.moved(location(list(position), angles)).wrapped)
        return faces

    @staticmethod
    def constraint_kinds(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
        """Druhy vazeb, které se pro dva odkazy hodí (M12)."""
        shapes = {reference_shape(a), reference_shape(b)}
        if shapes == {"plane"}:
            return ["mate", "flush", "distance"]
        if shapes == {"axis"}:
            return ["coaxial"]
        return []

    def _pose(self, component_id: str) -> tuple[Any, Any]:
        import numpy as np

        component = self._require().component(component_id)
        parameters = self.result.parameters if self.result is not None else {}
        try:
            position = [evaluate(v, parameters) for v in component.position]
            angles = [evaluate(v, parameters) for v in component.rotation]
        except ExpressionError as exc:
            raise AssemblyError(f"Poloha „{component.label}“: {exc}") from None
        return np.array(rotation_matrix(angles), dtype=float), np.array(position, dtype=float)

    def rename(self, component_id: str, name: str) -> AssemblyResult:
        def mutate(a: Assembly) -> None:
            a.component(component_id).name = name.strip()

        return self._change(mutate)

    def set_fixed(self, component_id: str, fixed: bool) -> AssemblyResult:
        def mutate(a: Assembly) -> None:
            a.component(component_id).fixed = bool(fixed)

        return self._change(mutate)

    def set_placement(self, component_id: str, position: Sequence[Any] | None = None,
                      rotation: Sequence[Any] | None = None) -> AssemblyResult:
        """Výslovná poloha z formuláře – jde i u pevné komponenty (S8)."""
        def mutate(a: Assembly) -> None:
            component = a.component(component_id)
            if position is not None:
                component.position = list(position)
            if rotation is not None:
                component.rotation = list(rotation)

        return self._change(mutate)

    def move_by(self, component_id: str, delta: Sequence[float]) -> AssemblyResult:
        """Posun o kus (tažení, šipky) – pevnou komponentu nepohne (S8)."""
        component = self._require().component(component_id)
        if component.fixed:
            raise AssemblyError(f"Komponenta „{component.label}“ je pevná – posuň ji číslem "
                                "ve formuláři, nebo zruš volbu Pevná.")
        values = self._numbers(component.position, component, "posun")
        if len(delta) != 3:
            raise AssemblyError("Posun musí být trojice [x, y, z].")
        moved = [tidy(v + float(d)) for v, d in zip(values, delta, strict=True)]
        return self.set_placement(component_id, position=moved)

    def turn(self, component_id: str, axis: str, degrees: float) -> AssemblyResult:
        """Otočí komponentu kolem osy sestavy vedené jejím počátkem (tlačítka ±90°);
        posun zůstane."""
        component = self._require().component(component_id)
        angles = self._numbers(component.rotation, component, "otočení")
        axis_matrix(axis, degrees)  # neznámá osa = česká chyba hned
        return self.set_placement(component_id, rotation=turned(angles, axis, degrees))

    def relink_warning(self, component_id: str, file: str | Path) -> str:
        """Upozornění před *Najít soubor…*: jiný otisk receptu než při uložení (S9)."""
        component = self._require().component(component_id)
        try:
            source = read_source(Path(file))
        except AssemblyError as exc:
            raise AssemblyError(f"Soubor {Path(file).name} nejde použít: {exc}") from None
        if component.fingerprint and source.fingerprint != component.fingerprint:
            return (f"Soubor {Path(file).name} má jiný recept, než měl „{component.label}“ "
                    "při posledním uložení sestavy – zkontroluj, že je to správný díl.")
        return ""

    def relink(self, component_id: str, file: str | Path) -> AssemblyResult:
        """*Najít soubor…*: změní jen cestu komponenty (jeden krok Zpět)."""
        self.relink_warning(component_id, file)  # nečitelný soubor se nepřijme
        path = relative_path(file, self._require_path())

        def mutate(a: Assembly) -> None:
            a.component(component_id).path = path

        return self._change(mutate)

    def set_parameters(self, parameters: dict[str, Any]) -> AssemblyResult:
        def mutate(a: Assembly) -> None:
            a.parameters = copy.deepcopy(parameters)

        return self._change(mutate)

    def set_info(self, name: str | None = None, description: str | None = None) -> AssemblyResult:
        def mutate(a: Assembly) -> None:
            if name is not None:
                a.name = name.strip() or a.name
            if description is not None:
                a.description = description

        return self._change(mutate)

    # --- Zpět / Znovu ------------------------------------------------------------------

    def begin_group(self) -> None:
        """Další změny (až do ``end_group``) půjdou vrátit jedním krokem Zpět."""
        self._group = len(self._undo)

    def end_group(self) -> None:
        mark, self._group = self._group, None
        if mark is not None and len(self._undo) > mark + 1:
            del self._undo[mark + 1:]  # zůstane jen stav před první změnou skupiny

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> AssemblyResult:
        if not self._undo:
            raise AssemblyError("Není co vrátit.")
        self._redo.append(self._require())
        self.assembly, self.dirty = self._undo.pop(), True
        return self.rebuild()

    def redo(self) -> AssemblyResult:
        if not self._redo:
            raise AssemblyError("Není co opakovat.")
        self._undo.append(self._require())
        self.assembly, self.dirty = self._redo.pop(), True
        return self.rebuild()

    # --- pomocné ------------------------------------------------------------------------

    def _require(self) -> Assembly:
        if self.assembly is None:
            raise AssemblyError("Není otevřená žádná sestava.")
        return self.assembly

    def _require_path(self) -> Path:
        if self.path is None:
            raise AssemblyError("Sestava ještě není uložená – ulož ji, cesty k dílům se "
                                "počítají vůči její složce.")
        return self.path

    def _numbers(self, values: Sequence[Any], component: Component, what: str) -> list[float]:
        if any(isinstance(value, str) for value in values):
            raise AssemblyError(f"{what.capitalize()} komponenty „{component.label}“ je zadané "
                                "výrazem – změň ho ve formuláři.")
        return [float(value) for value in values]

    def find(self, component_id: str) -> Path | None:
        """Soubor zdroje komponenty (pro *Otevřít díl*), nebo None, když se nenašel."""
        component = self._require().component(component_id)
        file, _warning = locate(self._require_path().parent, component.path)
        return file


def _copy_part(file: Path, target: Path, copied: dict[Path, str]) -> str:
    """Zkopíruje soubor dílu do ``dily/`` vedle sestavy ``target``; vrátí cestu podle S4.

    Stejný zdroj se kopíruje jednou. Existující soubor se stejnými bajty se použije,
    jiný se nepřepíše – kopie dostane číslo (``vicko_2.json``)."""
    if file in copied:
        return copied[file]
    folder = target.parent / "dily"
    folder.mkdir(exist_ok=True)
    raw = file.read_bytes()
    candidate, number = folder / file.name, 2
    while candidate.exists() and candidate.read_bytes() != raw:
        candidate = folder / f"{file.stem}_{number}{file.suffix}"
        number += 1
    if not candidate.exists():
        shutil.copyfile(file, candidate)
    copied[file] = f"dily/{candidate.name}"
    return copied[file]


def _apply_solved(assembly: Assembly, result: AssemblyResult) -> list[str]:
    """Zapíše polohy podle vazeb do komponent nejvyšší úrovně (M9); vrátí jejich názvy."""
    moved = []
    for ids, (position, rotation) in result.solved.items():
        if len(ids) != 1:
            continue
        component = assembly.component(ids[0])
        if component.position != position or component.rotation != rotation:
            component.position, component.rotation = list(position), list(rotation)
            moved.append(f"„{component.label}“")
    return moved


def _local(vector: Sequence[float], rotation: Any, position: Any) -> list[float]:
    """Bod (s posunem) nebo směr (bez) ze souřadnic sestavy do souřadnic komponenty."""
    import numpy as np

    value = np.array(vector, dtype=float)
    if position is not None:
        value = value - position
    local = rotation.T @ value
    return [tidy(round(float(v), 4)) for v in local]
