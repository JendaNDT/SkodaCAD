"""Systémový výběr složky projektu před čtením dílů sestavy v macOS."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from skodacad.assembly import Assembly, AssemblyError
from skodacad.gui.file_dialogs import FILE_OPTIONS

IS_MACOS = sys.platform == "darwin"
_granted_projects: set[Path] = set()  # jen po dobu tohoto procesu; žádné trvalé oprávnění


def request_project_access(parent: QWidget, file: str | Path) -> bool:
    """Interaktivní Otevřít: samotný výběr JSONu nezpřístupní složky jeho dílů.

    Před systémovým panelem se čte jen uživatelem vybraný JSON, nikoli adresáře
    ani zdroje komponent. Chybu receptu dál ohlásí běžné otevření sestavy.
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
    if any(required.is_relative_to(folder) for folder in _granted_projects):
        return True
    chosen = QFileDialog.getExistingDirectory(
        parent, "Složka projektu – pro načtení dílů sestavy vyber jejich společnou složku",
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
    _granted_projects.add(folder)
    return True
