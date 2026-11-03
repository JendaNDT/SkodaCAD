"""Samostatný 3D náhled pracovní dávky; do hlavního zobrazení nikdy nekreslí."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from skodacad.assembly import AssemblyError
from skodacad.expressions import evaluate


def placement_changes(preview):
    """Skutečné číselné polohy po řešení vazeb v této úrovni, nikoli změny textu."""
    rows = []
    for component in preview.assembly.components:
        old = preview.original.component(component.id)
        before = [evaluate(v, preview.original_result.parameters)
                  for v in (*old.position, *old.rotation)]
        after = [evaluate(v, preview.result.parameters)
                 for v in (*component.position, *component.rotation)]
        if any(not math.isclose(a, b, abs_tol=1e-7, rel_tol=0)
               for a, b in zip(before, after, strict=True)):
            rows.append((component.id, component.label, before, after))
    return rows


class AssemblyParameterPreviewDialog(QDialog):
    def __init__(self, preview, apply, viewer_factory, parent=None, *,
                 visible_ids=None, transparency=None):
        super().__init__(parent)
        self.preview = preview
        self._apply = apply
        self._visible_ids = visible_ids
        self._transparency = transparency or {}
        self._displayed = False
        self._display_timer = QTimer(self)
        self._display_timer.setInterval(20)
        self._display_timer.timeout.connect(self._initial_display)
        self.setWindowTitle("Náhled změn parametrů sestavy")
        self.resize(1000, 750)
        layout = QVBoxLayout(self)
        self.heading = QLabel("Náhled – nepotvrzené změny")
        layout.addWidget(self.heading)
        note = QLabel("Prohlédni si nové polohy a stav vazeb. Hlavní sestava zůstává beze změny. "
                      "Zpět k parametrům ponechá rozepsané hodnoty; Použít změny je přijme "
                      "najednou, jako jeden krok Zpět.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.original_box = QCheckBox("Zobrazit původní sestavu pro porovnání")
        self.original_box.setToolTip("Mění se pouze tento náhled; kamera hlavního okna zůstává.")
        layout.addWidget(self.original_box, alignment=Qt.AlignmentFlag.AlignLeft)
        self.viewer = viewer_factory()
        self.viewer.setMinimumHeight(280)
        layout.addWidget(self.viewer, 1)
        changes = placement_changes(preview)
        self.changed_ids = {row[0] for row in changes}
        self.summary = QLabel(f"Počet komponent se změnou polohy nebo otočení: {len(changes)}. "
                              f"Vazby: {sum(c.state == 'ok' for c in preview.result.constraints)}"
                              f"/{len(preview.result.constraints)} splněno. "
                              "Tabulka ukazuje polohy v této úrovni sestavy po řešení vazeb.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.changes = QTableWidget(len(changes), 5)
        self.changes.setAccessibleName("Změny poloh v náhledu parametrů")
        self.changes.setHorizontalHeaderLabels(["Komponenta", "Původní posun [mm]",
                                               "Nový posun [mm]", "Původní otočení [°]",
                                               "Nové otočení [°]"])
        self.changes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.changes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.changes.verticalHeader().hide()
        self.changes.setMaximumHeight(145)
        def fmt(values):
            return "; ".join(f"{v:.8g}".replace(".", ",") for v in values)

        for row, (id_, label, before, after) in enumerate(changes):
            values = (f"{label} ({id_})", fmt(before[:3]), fmt(after[:3]),
                      fmt(before[3:]), fmt(after[3:]))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.changes.setItem(row, column, item)
        layout.addWidget(self.changes)
        self.message = QLabel("Změněné komponenty jsou zvýrazněné. "
                              "Náhled respektuje skrytí, izolaci a průhlednost hlavního okna.")
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.apply_button.setText("Použít změny")
        self.back_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.back_button.setText("Zpět k parametrům")
        for button in self.buttons.buttons():
            button.setAutoDefault(False)
            button.setDefault(False)
        layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.original_box.toggled.connect(self._show_model)

    def showEvent(self, event):  # noqa: N802 -- Qt API
        super().showEvent(event)
        if not self._displayed:
            self._initial_display()
            if not self._displayed:
                self._display_timer.start()

    def _initial_display(self):
        if self._displayed or not self.isVisible():
            self._display_timer.stop()
            return
        if not getattr(self.viewer, "ready", True):
            return
        self._display_timer.stop()
        self._displayed = True
        self._show_model(fit=True)

    def _show_model(self, _checked=False, *, fit=False):
        original = self.original_box.isChecked()
        result = self.preview.original_result if original else self.preview.result
        visible = [i for i in result.instances
                   if self._visible_ids is None or i.ids in self._visible_ids]
        self.viewer.show_part(result.compound(visible_ids={i.ids for i in visible})
                              if visible else None, fit=fit,
                              transparent=[(i.part, self._transparency[i.ids]/100)
                                           for i in visible if self._transparency.get(i.ids, 0)])
        self.viewer.disable_model_selection()
        self.viewer.highlight([edge.wrapped for i in visible if i.ids[0] in self.changed_ids
                               for edge in i.part.edges()])
        self.heading.setText("Původní sestava – pro porovnání" if original
                             else "Náhled – nepotvrzené změny")

    def accept(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._apply(self.preview)
        except AssemblyError as exc:
            self.message.setText(str(exc))
            self.message.setStyleSheet("color: #bf3030;")
            self.apply_button.setEnabled(False)
            return
        finally:
            QApplication.restoreOverrideCursor()
        super().accept()
