"""Editor čistého JSON zadání; tělesa ověřuje výhradně ModelSession na pozadí."""

from __future__ import annotations

import copy
import math

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.ndt import UT_DISCLAIMER
from skodacad.ndt.welds import DIMENSION_LABELS, _weld_profiles, normalize_target

PRESETS = {"+X": [1, 0, 0], "−X": [-1, 0, 0], "+Y": [0, 1, 0],
           "−Y": [0, -1, 0], "+Z": [0, 0, 1], "−Z": [0, 0, -1]}
V_DEFAULTS = {"thickness_mm": 10, "angle_deg": 60, "root_gap_mm": 2,
              "cap_width_mm": 0, "cap_top_width_mm": 0, "cap_height_mm": 0,
              "root_width_mm": 0, "root_tip_width_mm": 0, "root_height_mm": 0}


def number(text: str) -> float:
    try:
        result = float(text.strip().replace(",", "."))
        if not math.isfinite(result):
            raise ValueError
        return result
    except ValueError:
        raise ValueError("Vyplň konečné číslo; čárka i tečka jsou povolené.") from None


class NumberEdit(QLineEdit):
    def __init__(self, value: float) -> None:
        super().__init__(repr(value))

    def value(self) -> float:
        return number(self.text())


class ProfilePreview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.profiles: list = []
        self.setMinimumHeight(110)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f3f6fa"))
        points = [p for polygon in self.profiles for p in polygon]
        if not points:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Průřez: napříč →, výška ↑")
            return
        left, right = min(p[0] for p in points), max(p[0] for p in points)
        bottom, top = min(p[1] for p in points), max(p[1] for p in points)
        scale = min((self.width() - 24) / max(1, right - left),
                    (self.height() - 24) / max(1, top - bottom))
        painter.setBrush(QColor("#91bff0"))
        painter.setPen(QColor("#205b96"))
        for polygon in self.profiles:
            painter.drawPolygon(QPolygonF([QPointF(12 + (x - left) * scale,
                                                    self.height() - 12 - (y - bottom) * scale)
                                            for x, y in polygon]))


class TargetDialog(QDialog):
    def __init__(self, window, study_id: str | None = None) -> None:
        super().__init__(window)
        self.window, self.session, self.study_id = window, window.session, study_id
        self.applied_id: str | None = None
        self._waiting = False
        self._ready = False
        self.setWindowTitle("Cílová oblast UT" if study_id else "Nová objemová studie UT")
        self.resize(620, 790)
        raw = self.session.ndt_study(study_id).get("target", {}) if study_id else {}
        self.original = copy.deepcopy(raw)
        target = raw if raw.get("kind") in ("volume", "weld") else {
            "kind": "volume", "frame": {"origin": [0, 0, 0], "axis": [0, 1, 0],
                                         "across": [1, 0, 0]},
            "length_mm": 10, "profile_mm": [[0, 0], [10, 0], [10, 10], [0, 10]]}
        outer = QVBoxLayout(self)
        warning = QLabel(UT_DISCLAIMER)
        warning.setWordWrap(True)
        outer.addWidget(warning)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.kind = QComboBox()
        for text, key in (("Tupý V svar", "butt_v"), ("Koutový svar", "fillet"),
                          ("Kontrolovaný objem", "volume")):
            self.kind.addItem(text, key)
        self.kind.setCurrentIndex(self.kind.findData(target.get("weld_type", "volume")))
        form.addRow("Druh cíle", self.kind)
        self.origin = [NumberEdit(v) for v in target["frame"]["origin"]]
        form.addRow("Počátek X, Y, Z [mm]", self._row(self.origin))
        pick = QPushButton("Převzít bod z 3D")
        pick.setToolTip("Převezme poslední bod vybraný ve 3D před otevřením dialogu.")
        pick.clicked.connect(self._pick)
        form.addRow(pick)
        self.directions: dict = {}
        for key, label in (("axis", "Podélná osa"), ("across", "Směr napříč")):
            combo = QComboBox()
            combo.addItems([*PRESETS, "Vlastní vektor"])
            values = target["frame"][key]
            combo.setCurrentText(next((k for k, v in PRESETS.items() if v == values),
                                       "Vlastní vektor"))
            fields = [NumberEdit(v) for v in values]
            for edit in fields:
                edit.setEnabled(combo.currentText() == "Vlastní vektor")
            self.directions[key] = (combo, fields)
            form.addRow(label, combo)
            form.addRow("Vektor X, Y, Z", self._row(fields))
            combo.currentTextChanged.connect(lambda _text, k=key: self._direction(k))
        form.addRow(QLabel("Výška průřezu = směr napříč × podélná osa; směry musí být kolmé."))
        self.length = NumberEdit(target["length_mm"])
        form.addRow("Délka cíle [mm]", self.length)
        self.weld = QWidget()
        weld_form = QFormLayout(self.weld)
        d = target.get("dimensions", {})
        self.dimensions = {k: NumberEdit(d.get(k, v)) for k, v in
                           (V_DEFAULTS | {"leg_across_mm": 7, "leg_height_mm": 7}).items()}
        self.dimension_labels = {}
        self.optional_groups = {}
        self.optional_widgets = {}
        for prefix, label in (("cap", "Převýšení (volitelné; všechny rozměry 0 = bez něj)"),
                               ("root", "Podkořen (volitelné; všechny rozměry 0 = bez něj)")):
            group = QGroupBox(label)
            self.optional_widgets[prefix] = group
            self.optional_groups[prefix] = QFormLayout(group)
        for key, field in self.dimensions.items():
            label = QLabel(DIMENSION_LABELS[key] + (" [°]" if key == "angle_deg" else " [mm]"))
            self.dimension_labels[key] = label
            prefix = ("cap" if key.startswith("cap_") else
                      "root" if key.startswith("root_") and key != "root_gap_mm" else "")
            (self.optional_groups[prefix] if prefix else weld_form).addRow(label, field)
        for group_form in self.optional_groups.values():
            weld_form.addRow(group_form.parentWidget())
        form.addRow(self.weld)
        self.volume = QWidget()
        volume_form = QFormLayout(self.volume)
        self.profile_mode = QComboBox()
        self.profile_mode.addItems(["Polygon", "Obdélník od počátku"])
        volume_form.addRow("Průřez", self.profile_mode)
        self.width, self.height = NumberEdit(10), NumberEdit(10)
        volume_form.addRow("Šířka / výška [mm]", self._row([self.width, self.height]))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Napříč [mm]", "Výška [mm]"])
        self.table.setMinimumHeight(140)
        for point in target.get("profile_mm", [[0, 0], [10, 0], [10, 10], [0, 10]]):
            self._add_point(point)
        volume_form.addRow(self.table)
        add, remove = QPushButton("Přidat vrchol"), QPushButton("Odebrat vrchol")
        add.clicked.connect(lambda: self._add_point([0, 0]))
        remove.clicked.connect(self._remove_point)
        volume_form.addRow(self._row([add, remove]))
        form.addRow(self.volume)
        self.profile = ProfilePreview()
        form.addRow(self.profile)
        self.status = QLabel("Ověř náhled před použitím. Zavření dialogu zadání neuloží.")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(65)
        outer.addWidget(self.status)
        self.preview_button = QPushButton("Ověřit a zobrazit náhled")
        self.preview_button.clicked.connect(self.preview)
        outer.addWidget(self.preview_button)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText("Použít")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        for edit in self.findChildren(QLineEdit):
            edit.textChanged.connect(self._changed)
        for combo in (self.kind, self.profile_mode):
            combo.currentIndexChanged.connect(self._changed)
        self.table.cellChanged.connect(self._changed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(80)
        self._changed()

    @staticmethod
    def _row(widgets: list) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        for child in widgets:
            layout.addWidget(child)
        return widget

    def _direction(self, key: str) -> None:
        combo, fields = self.directions[key]
        if combo.currentText() in PRESETS:
            for edit, value in zip(fields, PRESETS[combo.currentText()], strict=True):
                edit.setText(str(value))
        for edit in fields:
            edit.setEnabled(combo.currentText() == "Vlastní vektor")
        self._changed()

    def _pick(self) -> None:
        point = self.window.viewer.picked_point
        if point is None:
            self.status.setText("Bod není vybraný. Zavři dialog a nejprve klikni ve 3D na díl.")
        else:
            for edit, value in zip(self.origin, point, strict=True):
                edit.setText(repr(float(value)))

    def _add_point(self, point: list) -> None:
        if self.table.rowCount() >= 256:
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        for i, value in enumerate(point):
            self.table.setItem(row, i, QTableWidgetItem(repr(value)))

    def _remove_point(self) -> None:
        if self.table.rowCount() > 3:
            self.table.removeRow(max(0, self.table.currentRow()))
            self._changed()

    def values(self) -> dict:
        kind = self.kind.currentData()
        target = {"kind": "volume" if kind == "volume" else "weld",
                  "length_mm": self.length.value(),
                  "frame": {"origin": [v.value() for v in self.origin],
                            **{k: [v.value() for v in fields]
                               for k, (_, fields) in self.directions.items()}}}
        if kind == "volume":
            if self.profile_mode.currentIndex() == 1:
                w, h = self.width.value(), self.height.value()
                if w <= 0 or h <= 0:
                    raise ValueError("Šířka a výška obdélníku musí být kladné.")
                target["profile_mm"] = [[0, 0], [w, 0], [w, h], [0, h]]
            else:
                target["profile_mm"] = [[number(self.table.item(r, c).text())
                                          for c in range(2)] for r in range(self.table.rowCount())]
        else:
            keys = V_DEFAULTS if kind == "butt_v" else ("leg_across_mm", "leg_height_mm")
            target.update(weld_type=kind, dimensions={k: self.dimensions[k].value() for k in keys})
        return target

    def _changed(self, *args) -> None:
        self._ready = self._waiting = False
        self.session.cancel_ndt_preview()
        self.apply_button.setEnabled(False)
        self.preview_button.setEnabled(True)
        self.window.viewer.show_target_preview([], [], [], None)
        kind = self.kind.currentData()
        self.weld.setVisible(kind != "volume")
        self.volume.setVisible(kind == "volume")
        for group_form in self.optional_groups.values():
            group_form.parentWidget().setVisible(kind == "butt_v")
        for key, field in self.dimensions.items():
            shown = key in (V_DEFAULTS if kind == "butt_v" else ("leg_across_mm", "leg_height_mm"))
            field.setVisible(shown)
            self.dimension_labels[key].setVisible(shown)
        try:
            target = normalize_target(self.values())
            self.profile.profiles = ([target["profile_mm"]] if kind == "volume"
                                      else _weld_profiles(target))
            self.status.setText("Zadání změněno – ověř náhled před použitím.")
        except (ValueError, AttributeError) as exc:
            self.profile.profiles = []
            self.status.setText(str(exc))
        self.profile.update()

    def preview(self) -> None:
        try:
            self.session.start_ndt_target_preview(self.values(), self.study_id)
            self._waiting = True
            self.preview_button.setEnabled(False)
            self.status.setText("Ověřuji cíl na pozadí…")
        except (DocumentError, ValueError, AttributeError) as exc:
            self.status.setText(str(exc))

    def _poll(self) -> None:
        if not self._waiting or self.session.computing:
            return
        self._waiting = False
        self.preview_button.setEnabled(True)
        preview = self.session.ndt_target_preview
        if preview is None:
            self.status.setText(self.session.presentation_error or
                                "Náhled byl zrušen; ověř ho znovu.")
            return
        response = preview[2]
        numbers = response["numbers"]
        self.status.setText(f"Účinný objem {numbers['volume_mm3']:.9g} mm³; zadaný "
                            f"{numbers['requested_volume_mm3']:.9g} mm³; mimo materiál "
                            f"{numbers['outside_volume_mm3']:.9g} mm³. "
                            "Náhled nepotvrzuje zastaralou studii ani odborné ověření.")
        self.window.viewer.show_target_preview(*response["mesh"].mesh(),
                                               response["target"]["frame"])
        self._ready = True
        self.apply_button.setEnabled(True)

    def apply(self) -> None:
        if not self._ready:
            return
        try:
            self.applied_id = self.session.apply_ndt_target_preview()
            self.accept()
        except DocumentError as exc:
            self.status.setText(str(exc))
            self.apply_button.setEnabled(False)

    def done(self, result: int) -> None:
        self.timer.stop()
        self.session.cancel_ndt_preview()
        self.window.viewer.show_target_preview([], [], [], None)
        super().done(result)
