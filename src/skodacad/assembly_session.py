"""Otevřená sestava bez okna: úpravy komponent, Zpět/Znovu, uložení (P5.2).

Jako ``ModelSession`` u dílu: každá úprava jde přes ``_change`` (kopie → kontrola → přijetí),
nezměněná úprava není krok Zpět. Sestava nikdy nezapisuje do souborů dílů (S11) – uloží
jen svůj soubor. Nová sestava se hned uloží, protože cesty komponent se počítají vůči
její složce (S4).
"""

from __future__ import annotations

import copy
import os
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from skodacad.assembly import Assembly, AssemblyError, Component, check_path
from skodacad.assembly_build import (
    AssemblyResult,
    Cache,
    axis_matrix,
    build,
    locate,
    reachable,
    read_source,
    turned,
)
from skodacad.expressions import ExpressionError, resolve_parameters

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

    def save(self, path: str | Path | None = None) -> None:
        """Uloží sestavu; otisky zdrojů v pořádku se zapíšou podle souborů (S5).

        Uložení do jiné složky (Uložit jako) cesty přepočítá, aby dál vedly na tytéž
        soubory; soubor, který se nenašel, nechá tak, jak byl zapsaný."""
        assembly = self._require()
        target = Path(path).resolve() if path is not None else self._require_path()
        current = self.result if self.result is not None else self.rebuild()
        saved = copy.deepcopy(assembly)
        for component in saved.components:
            try:
                status = current.status(component.id)
            except AssemblyError:
                continue
            if status.fingerprint:  # zdroj se přečetl; chybějící nechá uložený otisk
                component.fingerprint = status.fingerprint
            if status.file is not None and target != self.path:
                component.path = relative_path(status.file, target)
        saved.save(target)
        self.assembly, self.path, self.dirty = saved, target, False
        self.rebuild()

    # --- sestavení ------------------------------------------------------------------

    def rebuild(self) -> AssemblyResult:
        """Sestaví znovu – soubory dílů se čtou vždy, staví se jen ty změněné."""
        self.result = build(self._require(), self._require_path(), self.cache)
        return self.result

    # --- úpravy ---------------------------------------------------------------------

    def _change(self, mutate: Callable[[Assembly], None]) -> AssemblyResult:
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
        self._undo.append(current)
        overflow = max(0, len(self._undo) - _UNDO_LIMIT)
        del self._undo[:overflow]
        if self._group is not None:
            self._group = max(0, self._group - overflow)
        self._redo.clear()
        self.assembly = candidate
        self.dirty = True
        return self.rebuild()

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
        self._require().component(component_id)
        return self._change(lambda a: a.components.remove(a.component(component_id)))

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
        moved = [_tidy(v + float(d)) for v, d in zip(values, delta, strict=True)]
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


def _tidy(value: float) -> float:
    value = round(value, 9) + 0.0
    return int(value) if value.is_integer() else value
