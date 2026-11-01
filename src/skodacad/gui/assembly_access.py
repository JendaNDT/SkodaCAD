"""Systémový výběr složky projektu před čtením dílů sestavy v macOS."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from skodacad.assembly import MAX_COMPONENTS, MAX_DEPTH, Assembly, AssemblyError
from skodacad.gui.file_dialogs import FILE_OPTIONS

IS_MACOS = sys.platform == "darwin"
_granted_projects: set[Path] = set()  # paměť procesu, bez ukládání bookmarků


class _ProjectNeeded(Exception):
    def __init__(self, folder: Path) -> None:
        super().__init__(str(folder))
        self.folder = folder


def _covered(folder: Path) -> bool:
    return any(folder.is_relative_to(root) for root in _granted_projects)


def _locate_in_project(folder: Path, relative: str) -> Path | None:
    """Kontrola rozsahu před každým listdir a před čtením zdroje.

    Stejný výběr velikosti písmen jako locate; vlastní sestavení dál připraví
    jeho upozornění. Resolve ověřuje skutečné cíle odkazů; recepty neotevírá.
    """
    current = folder
    try:
        for name in relative.split("/"):
            if name == "..":
                current = current.parent
                continue
            current = current.resolve()
            if not _covered(current):
                raise _ProjectNeeded(current)
            names = os.listdir(current)
            match = name if name in names else next(
                (n for n in names if n.casefold() == name.casefold()), None)
            if match is None:
                return None
            current = current / match
        current = current.resolve()
        if not _covered(current.parent):
            raise _ProjectNeeded(current.parent)
        return current if current.is_file() else None
    except (OSError, RuntimeError):  # chybějící soubor / cyklus symlinků ohlásí sestavení
        return None


def _check_subassemblies(assembly: Assembly, file: Path) -> None:
    """Čte jen zdroje ve vybraném projektu, cykly i opakované díly navštíví jednou."""
    visited = {file.resolve()}
    count = 0

    def walk(level: Assembly, path: Path, depth: int) -> None:
        nonlocal count
        for component in level.components:
            count += 1
            if count > MAX_COMPONENTS:
                raise AssemblyError(f"Kontrola souborů sestavy přesáhla {MAX_COMPONENTS} "
                                    "komponent. Rozděl projekt na menší sestavy.")
            target = _locate_in_project(path.parent, component.path)
            if target is None or target in visited:
                continue
            visited.add(target)
            try:
                nested = Assembly.load(target)
            except (AssemblyError, OSError, UnicodeError):
                continue  # díl nebo vadný zdroj; běžná kontrola sestavy jej vyhodnotí
            if depth + 1 < MAX_DEPTH:
                walk(nested, target, depth + 1)

    walk(assembly, file, 0)


def request_project_access(parent: QWidget, file: str | Path) -> bool:
    """Interaktivní Otevřít: samotný výběr JSONu nezpřístupní složky jeho dílů.

    Před prvním panelem se čte jen uživatelem vybraný JSON. Podsestavy se pak
    kontrolují ve vybraném rozsahu; vnější odkaz vyžádá širší složku před I/O.
    Chybu receptu dál ohlásí běžné otevření sestavy.
    """
    if not IS_MACOS:
        return True
    file = Path(os.path.abspath(file))  # lexikálně, bez resolve/listdir v chráněné složce
    try:
        assembly = Assembly.load(file)
    except (AssemblyError, OSError, UnicodeError):
        return True
    folders = [file.parent, *(Path(os.path.abspath(file.parent / c.path)).parent
                              for c in assembly.components)]
    required = Path(os.path.commonpath(folders))
    while True:
        if not _covered(required):
            chosen = QFileDialog.getExistingDirectory(
                parent, "Složka projektu – pro sestavu i podsestavy vyber společnou složku",
                str(required), options=FILE_OPTIONS | QFileDialog.Option.ShowDirsOnly)
            if not chosen:
                return False
            folder = Path(os.path.abspath(chosen))
            if not required.is_relative_to(folder):
                QMessageBox.warning(parent, "Složka projektu nestačí",
                                    f"Sestava a její díly potřebují složku {required}. "
                                    "Otevři sestavu znovu a vyber tuto složku nebo její "
                                    "nadřazenou složku projektu.")
                return False
            _granted_projects.update((folder, folder.resolve()))
        try:
            _check_subassemblies(assembly, file)
        except _ProjectNeeded as need:
            required = Path(os.path.commonpath([file.parent, need.folder]))
        except AssemblyError as exc:
            QMessageBox.warning(parent, "Sestavu nejde otevřít", str(exc))
            return False
        else:
            return True
