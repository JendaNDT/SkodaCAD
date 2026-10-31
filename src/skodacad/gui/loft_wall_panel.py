"""Číselný přehled stěny přechodu; geometrie i platnost patří ModelSession."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from skodacad.inspection import number
from skodacad.loft_inspection import LIMITATION, MODE_LABELS, STATUS_LABELS, WallReport


class LoftWallPanel(QGroupBox):
    requested = Signal()
    selected = Signal(int)

    def __init__(self) -> None:
        super().__init__("Kontrola stěny přechodu")
        self._shown: WallReport | None = None
        self._feature_id = None
        layout = QVBoxLayout(self)
        self.button = QPushButton("Změřit stěnu")
        self.button.clicked.connect(self.requested)
        layout.addWidget(self.button)
        self.summary = QLabel("Měření zatím neproběhlo.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Bod", "mm", "Výsledek"])
        self.table.verticalHeader().hide()
        for col in (0, 1):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(120)
        self.table.setMaximumHeight(180)
        self.table.currentCellChanged.connect(self._select)
        layout.addWidget(self.table)
        self.location = QLabel()
        self.location.setWordWrap(True)
        layout.addWidget(self.location)
        self.note = QLabel("Původní plášť v aktuálním dílu. "
                           "Vzorky nejsou globální minimum ani výrobní přejímka. "
                           "Klikni na bod pro polohu ve 3D.")
        self.note.setWordWrap(True)
        self.note.setToolTip(LIMITATION)
        layout.addWidget(self.note)
        self.hide()

    @property
    def selected_index(self) -> int:
        row = self.table.currentRow()
        return row if self._shown is not None and 0 <= row < len(self._shown.samples) else -1

    def refresh(self, feature_id, report, problem: str, computing: bool) -> None:
        self.button.setEnabled(not computing)
        self.button.setText("Přeměřit stěnu" if report else "Změřit stěnu")
        if report is not None:
            values = report.lengths
            extent = (f"{number(min(values), 3)}–{number(max(values), 3)} mm" if values
                      else "žádný jistý výsledek")
            counts = report.counts
            self.summary.setText(
                f"Zadání: {number(report.requested, 3)} mm · {MODE_LABELS[report.mode]}\n"
                f"Naměřeno ve vzorcích: {extent}\n"
                f"Pod zadáním: {counts['below']} · u zadání: {counts['nominal']}\n"
                f"Delší průchod: {counts['longer']} · nejisté: {counts['unknown']}\n"
                f"Bodů: {len(report.samples)} · vynecháno u okraje/mimo plochu: {report.skipped}"
                + ("\nDosažen limit 2 000 bodů – část pláště nebyla měřena."
                   if report.truncated else ""))
        else:
            self.summary.setText(problem or "Měření zatím neproběhlo. Po změně modelu je zopakuj.")
        self.table.setVisible(report is not None)
        if report is self._shown and feature_id == self._feature_id:
            return
        self._shown, self._feature_id = report, feature_id
        self.table.blockSignals(True)
        self.table.setCurrentCell(-1, -1)
        samples = report.samples if report is not None else ()
        # Existující buňky zachovat: macOS přístupnost může držet odkazy na jejich model.
        while self.table.rowCount() < len(samples):
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col in range(3):
                self.table.setItem(row, col, QTableWidgetItem())
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, row >= len(samples))
            if row >= len(samples):
                continue
            sample = samples[row]
            values = (str(row + 1), number(sample.length, 3) if sample.length is not None else "—",
                      STATUS_LABELS[sample.status])
            tooltip = self._location(row)
            for col, text in enumerate(values):
                self.table.item(row, col).setText(text)
                self.table.item(row, col).setToolTip(tooltip)
        self.table.blockSignals(False)
        self.location.clear()
        self.selected.emit(-1)

    def _location(self, row: int) -> str:
        sample = self._shown.samples[row]
        x, y, z = sample.point
        return (f"X {number(x, 3)} · Y {number(y, 3)} · Z {number(z, 3)} mm"
                + (f"\n{sample.reason}" if sample.reason else ""))

    def _select(self, row: int, *_args) -> None:
        index = self.selected_index
        self.location.setText(self._location(index) if index >= 0 else "")
        self.selected.emit(index)
