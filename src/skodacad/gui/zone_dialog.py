"""Dialog *Zakázané zóny…* plánu dráhy sondy (etapa 10).

Zóna je kvádr v souřadnicích dílu (mm), do kterého sonda nesmí zasáhnout žádnou částí těla
(štítek, upínka, poškozený povrch). Dialog jen upravuje čísla v tabulce; uloží je okno přes
``ModelSession.set_ndt_zones`` (jeden krok Zpět). *Z výběru* přidá kvádr kolem ploch či hran
vybraných ve 3D. Čísla jsou text (ne číselník), aby se nezaokrouhlila – nezměněné *OK*
vrátí totéž.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.ndt.plan import PlanError, Zone

COLUMNS = ("Název", "min x", "min y", "min z", "max x", "max y", "max z")


def _text(value: float) -> str:
    return f"{value:g}".replace(".", ",")


class ZoneDialog(QDialog):
    def __init__(self, parent: QWidget | None, zones: list[dict[str, Any]],
                 from_selection: Callable[[], dict[str, Any]] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zakázané zóny plánu dráhy")
        self._from_selection = from_selection
        layout = QVBoxLayout(self)
        hint = QLabel("Kvádr v souřadnicích dílu [mm], do kterého sonda nesmí zasáhnout žádnou "
                      "částí těla. Plán dráhy se po uložení znovu ověří.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("ndt_zones_table")
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        for zone in zones:
            self._add_row(zone)
        row = QHBoxLayout()
        self.add_button = QPushButton("Přidat")
        self.add_button.clicked.connect(lambda: self._add_row(
            {"name": f"zóna {self.table.rowCount() + 1}", "min": [0, 0, 0], "max": [10, 10, 10]}))
        self.selection_button = QPushButton("Z výběru")
        self.selection_button.setToolTip("Kvádr kolem ploch nebo hran vybraných ve 3D "
                                         "(o 1 mm větší na každou stranu)")
        self.selection_button.setEnabled(from_selection is not None)
        self.selection_button.clicked.connect(self._add_from_selection)
        self.remove_button = QPushButton("Smazat")
        self.remove_button.clicked.connect(self._remove_row)
        for button in (self.add_button, self.selection_button, self.remove_button):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.error = QLabel()
        self.error.setObjectName("ndt_zones_error")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c0392b;")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(640, 320)

    def _add_row(self, zone: dict[str, Any]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [zone.get("name", ""), *map(_text, zone["min"]), *map(_text, zone["max"])]
        for column, value in enumerate(values):
            self.table.setItem(row, column, QTableWidgetItem(str(value)))

    def _remove_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _add_from_selection(self) -> None:
        try:
            self._add_row(self._from_selection())
            self.error.setText("")
        except DocumentError as exc:
            self.error.setText(str(exc))

    def zones(self) -> list[dict[str, Any]]:
        """Zóny z tabulky (zkontrolované); chyba = ``PlanError`` s číslem řádku."""
        result = []
        for row in range(self.table.rowCount()):
            cells = [(self.table.item(row, c).text() if self.table.item(row, c) else "")
                     for c in range(len(COLUMNS))]
            try:
                numbers = [float(text.strip().replace(",", ".")) for text in cells[1:]]
            except ValueError:
                raise PlanError(f"Zóna {row + 1}: souřadnice musí být čísla v mm.") from None
            zone = Zone.from_dict({"name": cells[0].strip(), "min": numbers[:3],
                                   "max": numbers[3:]}, row + 1)
            result.append(zone.to_dict())
        return result

    def accept(self) -> None:
        try:
            self.zones()
        except PlanError as exc:
            self.error.setText(str(exc))  # dialog zůstane otevřený s chybou
            return
        super().accept()
