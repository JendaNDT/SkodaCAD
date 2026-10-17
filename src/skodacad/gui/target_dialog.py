"""Editor cílového objemu NDT studie (07C): tupý svar V, koutový svar nebo obecný hranol.

Dialog jen sestaví JSON cíle (formát 16, stejný jako v 07A). Kontrolu a výpočty dělá
``ModelSession``: ``ndt_target_outline`` (zadání, průřez a objem ze vzorce – bez geometrie
dílu) a ``check_ndt_volume_target`` (účinný objem v materiálu, bez změny modelu). Nákres
průřezu je obyčejné kreslení Qt. Směry nabízí jen ±X/±Y/±Z; šikmý směr uložený v souboru
ukáže jako „vlastní“ a ponechá ho, dokud ho uživatel sám nepřepne.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.inspection import number
from skodacad.ndt.welds import DIMENSION_LABELS, DIRECTIONS, direction_name, height_direction

if TYPE_CHECKING:
    from skodacad.session import ModelSession

# Položka nabídky → (kind, weld_type); klíč je text, Qt neumí najít položku podle n-tice.
KINDS = {"butt_v": ("Tupý svar V", "weld", "butt_v"), "fillet": ("Koutový svar", "weld", "fillet"),
         "volume": ("Obecný hranol", "volume", None)}
DIMENSIONS = {"butt_v": ("thickness_mm", "angle_deg", "root_gap_mm", "cap_width_mm",
                         "cap_top_width_mm", "cap_height_mm", "root_width_mm",
                         "root_tip_width_mm", "root_height_mm"),
              "fillet": ("leg_across_mm", "leg_height_mm")}
DEFAULT_DIMENSIONS = {"thickness_mm": 10, "angle_deg": 60, "root_gap_mm": 2,
                      "leg_across_mm": 5, "leg_height_mm": 5}
DEFAULT_PROFILE = [[0, 0], [10, 0], [10, 10], [0, 10]]
# Výchozí zadání nového cíle – vždy je potřeba ho přepsat podle dílu.
DEFAULT_TARGET: dict[str, Any] = {
    "kind": "weld", "weld_type": "butt_v", "length_mm": 100,
    "frame": {"origin": [0, 0, 0], "axis": [0, 1, 0], "across": [1, 0, 0]},
    "dimensions": {key: DEFAULT_DIMENSIONS.get(key, 0) for key in DIMENSIONS["butt_v"]}}
ORIGIN_HINTS = {
    "butt_v": "Počátek = střed kořenové mezery na straně kořene. Tělo svaru sahá od 0 do "
              "tloušťky plechu ve směru výšky; převýšení je nad ním, podkořen pod ním. "
              "Převýšení a podkořen mohou mít všechny rozměry 0.",
    "fillet": "Počátek = kořen koutu (kde se potkají obě plochy). Rameno napříč leží podél "
              "jedné plochy, rameno na výšku podél druhé.",
    None: "Vrcholy průřezu se zadávají v rovině (napříč, výška) od počátku. Do výpočtu se "
          "počítá jen část hranolu uvnitř materiálu dílu.",
}
_OK, _ERROR = "#1b7f3b", "#c0392b"


def _fmt(value: float) -> str:
    text = f"{float(value):.10g}"
    return "0" if text == "-0" else text


def _direction_label(vector: Any) -> str:
    name = direction_name(vector)
    if name is not None:
        return name.replace("-", "−")
    return "vlastní (" + "; ".join(_fmt(v) for v in vector) + ")"


class _Number(QLineEdit):
    """Číslo v mm nebo ° – přijme desetinnou čárku i tečku, zobrazí bez zbytečných nul."""

    def __init__(self, label: str, value: float = 0.0) -> None:
        super().__init__()
        self.label = label
        self.setObjectName(f"target_{label}")
        self.setValue(value)

    def setValue(self, value: float) -> None:  # noqa: N802 – jako u ostatních polí Qt
        self.setText(_fmt(value))

    def value(self) -> float:
        try:
            return float(self.text().strip().replace(",", "."))
        except ValueError:
            raise ValueError(f"Pole „{self.label}“ musí být číslo (desetinná čárka i tečka "
                             "platí).") from None


class ProfilePreview(QWidget):
    """Nákres průřezu cíle v rovině (napříč, výška) s osami a počátkem."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("target_preview")
        self.setMinimumSize(260, 190)
        self.profiles: list[list[list[float]]] = []
        self.height_name = ""

    def set_profiles(self, profiles: list[list[list[float]]], height_name: str) -> None:
        self.profiles = profiles
        self.height_name = height_name
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("white"))
        painter.setPen(QPen(QColor("#999999")))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if not self.profiles:
            painter.setPen(QColor("#777777"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Průřez se ukáže po správném zadání.")
            return
        points = [p for profile in self.profiles for p in profile] + [[0.0, 0.0]]
        low = [min(p[i] for p in points) for i in (0, 1)]
        high = [max(p[i] for p in points) for i in (0, 1)]
        margin = 30
        span = [max(high[i] - low[i], 1e-9) for i in (0, 1)]
        scale = min((self.width() - 2 * margin) / span[0],
                    (self.height() - 2 * margin) / span[1])
        middle = [(low[i] + high[i]) / 2 for i in (0, 1)]

        def at(a: float, h: float) -> QPointF:
            return QPointF(self.width() / 2 + (a - middle[0]) * scale,
                           self.height() / 2 - (h - middle[1]) * scale)

        origin = at(0, 0)
        painter.setPen(QPen(QColor("#b0b0b0"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(4, origin.y()), QPointF(self.width() - 4, origin.y()))
        painter.drawLine(QPointF(origin.x(), 4), QPointF(origin.x(), self.height() - 4))
        painter.setPen(QPen(QColor("#1f3f7a"), 1.5))
        painter.setBrush(QColor(51, 115, 217, 90))
        for profile in self.profiles:
            painter.drawPolygon(QPolygonF([at(a, h) for a, h in profile]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_ERROR))
        painter.drawEllipse(origin, 4, 4)
        painter.setPen(QColor("#333333"))
        painter.drawText(6, self.height() - 6, f"{_fmt(round(span[0], 3))} × "
                         f"{_fmt(round(span[1], 3))} mm")
        painter.drawText(self.rect().adjusted(0, 0, -6, -6),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, "napříč →")
        painter.drawText(6, 16, f"výška ↑ ({self.height_name})")


class TargetDialog(QDialog):
    """Cílový objem studie. ``edge`` = počátek, směr a délka z vybrané rovné hrany
    (``ModelSession.ndt_frame_from_edge``), nebo None."""

    def __init__(self, session: ModelSession, target: dict[str, Any] | None = None,
                 edge: dict[str, Any] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cílový objem NDT studie")
        self.session = session
        self.edge = edge
        self._loading = True
        outer = QVBoxLayout(self)
        note = QLabel("Svar je <b>nominální zadaná oblast</b>, ne rozpoznaná hranice natavení. "
                      "Díl se nemění – cíl patří jen ke studii.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        outer.addWidget(note)
        columns = QHBoxLayout()
        outer.addLayout(columns)
        form = QFormLayout()
        columns.addLayout(form, stretch=3)
        self.kind = QComboBox()
        self.kind.setObjectName("target_kind")
        for key, (label, _kind, _weld_type) in KINDS.items():
            self.kind.addItem(label, key)
        form.addRow("Typ cíle", self.kind)
        self.origin = [_Number(f"Počátek {axis} [mm]") for axis in "XYZ"]
        row = QHBoxLayout()
        for field in self.origin:
            row.addWidget(field)
        form.addRow("Počátek X, Y, Z [mm]", row)
        self.axis = QComboBox()
        self.axis.setObjectName("target_axis")
        form.addRow("Směr podél svaru", self.axis)
        self.across = QComboBox()
        self.across.setObjectName("target_across")
        form.addRow("Směr napříč", self.across)
        self.height_label = QLabel()
        self.height_label.setObjectName("target_height")
        form.addRow("Výška průřezu míří do", self.height_label)
        self.length = _Number("Délka [mm]", 100)
        form.addRow("Délka [mm]", self.length)
        self.dimensions: dict[str, _Number] = {}
        self._dimension_labels: dict[str, QLabel] = {}
        for key in (*DIMENSIONS["butt_v"], *DIMENSIONS["fillet"]):
            unit = "°" if key.endswith("_deg") else "mm"
            label = f"{DIMENSION_LABELS[key]} [{unit}]"
            self.dimensions[key] = _Number(label, DEFAULT_DIMENSIONS.get(key, 0))
            self._dimension_labels[key] = QLabel(label)
            form.addRow(self._dimension_labels[key], self.dimensions[key])
        self.profile_box = QWidget()
        box = QVBoxLayout(self.profile_box)
        box.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 2)
        self.table.setObjectName("target_profile")
        self.table.setHorizontalHeaderLabels(["napříč [mm]", "výška [mm]"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(120)
        box.addWidget(self.table)
        buttons = QHBoxLayout()
        self.add_vertex = QPushButton("Přidat vrchol")
        self.remove_vertex = QPushButton("Odebrat vrchol")
        buttons.addWidget(self.add_vertex)
        buttons.addWidget(self.remove_vertex)
        buttons.addStretch()
        box.addLayout(buttons)
        self.profile_label = QLabel("Průřez hranolu")
        form.addRow(self.profile_label, self.profile_box)

        right = QVBoxLayout()
        columns.addLayout(right, stretch=2)
        self.preview = ProfilePreview()
        right.addWidget(self.preview, stretch=1)
        self.volume_label = QLabel()
        self.volume_label.setObjectName("target_volume")
        self.volume_label.setWordWrap(True)
        right.addWidget(self.volume_label)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #555;")
        right.addWidget(self.hint)
        self.error_label = QLabel()
        self.error_label.setObjectName("target_error")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {_ERROR};")
        outer.addWidget(self.error_label)
        self.check_label = QLabel()
        self.check_label.setObjectName("target_check")
        self.check_label.setWordWrap(True)
        outer.addWidget(self.check_label)
        bottom = QHBoxLayout()
        self.edge_button = QPushButton("Podle vybrané hrany")
        self.edge_button.setEnabled(edge is not None)
        self.edge_button.setToolTip(
            "Směr podél, délka a počátek na začátku rovné hrany vybrané ve 3D; počátek pak "
            "posuň do kořene svaru." if edge is not None else
            "Před otevřením dialogu vyber ve 3D právě jednu rovnou hranu podél svaru.")
        self.check_button = QPushButton("Zkontrolovat v dílu")
        self.check_button.setToolTip("Spočítá účinný objem v materiálu dílu – model se nemění.")
        bottom.addWidget(self.edge_button)
        bottom.addWidget(self.check_button)
        bottom.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        bottom.addWidget(self.buttons)
        outer.addLayout(bottom)

        self._load(target or DEFAULT_TARGET)
        self.kind.currentIndexChanged.connect(lambda _index: self._kind_changed())
        self.axis.currentIndexChanged.connect(lambda _index: self._axis_changed())
        self.across.currentIndexChanged.connect(lambda _index: self._update())
        for field in (*self.origin, self.length, *self.dimensions.values()):
            field.textChanged.connect(lambda _text: self._update())
        self.table.itemChanged.connect(lambda _item: self._update())
        self.add_vertex.clicked.connect(self._add_vertex)
        self.remove_vertex.clicked.connect(self._remove_vertex)
        self.edge_button.clicked.connect(self.use_edge)
        self.check_button.clicked.connect(self.check)
        self._loading = False
        self._kind_changed()
        self.resize(820, 560)

    # --- načtení a sestavení JSON --------------------------------------------------------

    def _load(self, target: dict[str, Any]) -> None:
        key = target.get("weld_type") if target.get("kind") == "weld" else "volume"
        self.kind.setCurrentIndex(max(0, self.kind.findData(key)))
        frame = target["frame"]
        for field, value in zip(self.origin, frame["origin"], strict=True):
            field.setValue(value)
        self._fill_axis(frame["axis"])
        self._fill_across(frame["across"])
        self.length.setValue(target["length_mm"])
        for key, value in (target.get("dimensions") or {}).items():
            if key in self.dimensions:
                self.dimensions[key].setValue(value)
        self._set_profile(target.get("profile_mm") or DEFAULT_PROFILE)

    def target(self) -> dict[str, Any]:
        """Zadání z polí jako JSON cíle; ValueError = pole, které není číslo."""
        _label, kind, weld_type = KINDS[self.kind.currentData()]
        result: dict[str, Any] = {
            "kind": kind,
            "frame": {"origin": [field.value() for field in self.origin],
                      "axis": list(self._vector(self.axis)),
                      "across": list(self._vector(self.across))},
            "length_mm": self.length.value()}
        if kind == "volume":
            result["profile_mm"] = self._profile()
        else:
            result["weld_type"] = weld_type
            result["dimensions"] = {key: self.dimensions[key].value()
                                    for key in DIMENSIONS[weld_type]}
        return result

    @staticmethod
    def _vector(combo: QComboBox) -> tuple[float, float, float]:
        data = combo.currentData()
        return DIRECTIONS[data] if isinstance(data, str) else tuple(data)

    def _fill_axis(self, vector: Any) -> None:
        self.axis.blockSignals(True)
        self.axis.clear()
        for name in DIRECTIONS:
            self.axis.addItem(_direction_label(DIRECTIONS[name]), name)
        name = direction_name(vector)
        if name is None:
            self.axis.addItem(_direction_label(vector), tuple(float(v) for v in vector))
            self.axis.setCurrentIndex(self.axis.count() - 1)
        else:
            self.axis.setCurrentIndex(self.axis.findData(name))
        self.axis.blockSignals(False)

    def _fill_across(self, preferred: Any = None) -> None:
        """Nabídka směrů napříč – jen kolmé na osu; ponechá dosavadní, je-li pořád kolmý."""
        axis = self._vector(self.axis)
        current = preferred if preferred is not None else (
            self._vector(self.across) if self.across.count() else None)
        self.across.blockSignals(True)
        self.across.clear()
        for name, vector in DIRECTIONS.items():
            if abs(sum(a * b for a, b in zip(axis, vector, strict=True))) < 1e-8:
                self.across.addItem(_direction_label(vector), name)
        if current is not None and abs(sum(a * b for a, b in zip(axis, current,
                                                                  strict=True))) < 1e-8:
            name = direction_name(current)
            if name is None:
                self.across.addItem(_direction_label(current), tuple(float(v) for v in current))
                self.across.setCurrentIndex(self.across.count() - 1)
            elif self.across.findData(name) >= 0:
                self.across.setCurrentIndex(self.across.findData(name))
        if self.across.count() == 0:  # šikmá osa ze souboru – kolmý směr dopočítat
            helper = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (1.0, 0.0, 0.0)
            vector = height_direction(helper, axis)
            length = sum(v * v for v in vector) ** 0.5
            vector = tuple(round(v / length, 12) for v in vector)
            self.across.addItem(_direction_label(vector), vector)
        self.across.blockSignals(False)

    def _set_profile(self, points: list[list[float]]) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for a, h in points:
            self._append_row(a, h)
        self.table.blockSignals(False)

    def _append_row(self, a: float, h: float) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value in enumerate((a, h)):
            self.table.setItem(row, column, QTableWidgetItem(_fmt(value)))

    def _profile(self) -> list[list[float]]:
        points = []
        for row in range(self.table.rowCount()):
            vertex = []
            for column in (0, 1):
                item = self.table.item(row, column)
                text = (item.text() if item is not None else "").strip().replace(",", ".")
                try:
                    vertex.append(float(text))
                except ValueError:
                    raise ValueError(f"Vrchol {row + 1} průřezu: zadej obě souřadnice "
                                     "jako čísla.") from None
            points.append(vertex)
        return points

    # --- reakce na změny ---------------------------------------------------------------

    def _kind_changed(self) -> None:
        _label, kind, weld_type = KINDS[self.kind.currentData()]
        for key, field in self.dimensions.items():
            shown = weld_type is not None and key in DIMENSIONS[weld_type]
            field.setVisible(shown)
            self._dimension_labels[key].setVisible(shown)
        self.profile_box.setVisible(kind == "volume")
        self.profile_label.setVisible(kind == "volume")
        self.hint.setText(ORIGIN_HINTS[weld_type])
        self._update()

    def _axis_changed(self) -> None:
        self._fill_across()
        self._update()

    def _add_vertex(self) -> None:
        last = self._safe_last_vertex()
        self.table.blockSignals(True)
        self._append_row(last[0] + 1, last[1])
        self.table.blockSignals(False)
        self._update()

    def _safe_last_vertex(self) -> list[float]:
        try:
            points = self._profile()
        except ValueError:
            return [0.0, 0.0]
        return points[-1] if points else [0.0, 0.0]

    def _remove_vertex(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows or [self.table.rowCount() - 1]:
            if row >= 0:
                self.table.removeRow(row)
        self._update()

    def use_edge(self) -> None:
        """Směr podél, délka a počátek ze zvolené rovné hrany (napříč a výšku nechá)."""
        if self.edge is None:
            return
        self._loading = True
        for field, value in zip(self.origin, self.edge["origin"], strict=True):
            field.setValue(value)
        self._fill_axis(self.edge["axis"])
        self._fill_across()
        self.length.setValue(self.edge["length_mm"])
        self._loading = False
        self._update()

    def _update(self) -> None:
        """Nákres, objem ze vzorce a chyby po každé změně pole (bez geometrie dílu)."""
        if self._loading:
            return
        self.check_label.setText("")  # starší kontrola v dílu už neplatí
        try:
            axis, across = self._vector(self.axis), self._vector(self.across)
            self.height_label.setText(_direction_label(height_direction(axis, across)))
            _saved, profiles, volume = self.session.ndt_target_outline(self.target())
        except (ValueError, DocumentError) as exc:
            self.preview.set_profiles([], "")
            self.volume_label.setText("")
            self.error_label.setText(str(exc))
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            self.check_button.setEnabled(False)
            return
        self.preview.set_profiles(profiles, self.height_label.text())
        self.volume_label.setText(f"Zadaný objem (průřez × délka): <b>{number(volume, 3)} "
                                  "mm³</b>")
        self.error_label.setText("")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self.check_button.setEnabled(True)

    def check(self) -> bool:
        """Zkontroluje cíl v aktuálním dílu (model se nemění). True = platný."""
        try:
            resolved = self.session.check_ndt_volume_target(self.target())
        except (ValueError, DocumentError) as exc:
            self.check_label.setStyleSheet(f"color: {_ERROR};")
            self.check_label.setText(f"V dílu nejde použít: {exc}")
            return False
        self.check_label.setStyleSheet(f"color: {_OK};")
        self.check_label.setText(
            f"V dílu v pořádku: účinný objem v materiálu {number(resolved.volume_mm3, 3)} mm³ "
            f"(zadaný {number(resolved.requested_volume_mm3, 3)} mm³, mimo materiál "
            f"{number(resolved.outside_volume_mm3, 3)} mm³).")
        return True

    def accept(self) -> None:
        """OK jen pro cíl, který jádro v dílu přijme – jinak dialog zůstane otevřený."""
        if self.check():
            super().accept()
