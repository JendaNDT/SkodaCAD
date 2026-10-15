"""Skicář: 2D editor obrysu z úseček a oblouků s vazbami a kótami.

Okno nic nepočítá samo – kreslení a vazby jdou přes ``skodacad.profile_edit``
(úpravy slovníku obrysu) a řešení přes ``ModelSession.solve_profile``. Po každé
úpravě se obrys vyřeší a vyřešené polohy bodů se uloží zpět do obrysu.

Ovládání: kolečko = zoom, prostřední/pravé tlačítko táhnout = posun,
Esc = konec kreslení, Delete = smazat vybrané, Ctrl+Z = zpět.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from skodacad import profile_edit as edit
from skodacad.profile_edit import EditError
from skodacad.solver import DIMENSIONS, ORIGIN, SolveError, arc_midpoint, constraint_text, loops

SNAP_PIXELS = 10  # klik blíž než tolik pixelů k bodu = ten bod
HIT_PIXELS = 7  # klik blíž než tolik pixelů k čáře = ta čára

COLOR_FREE = QColor("#1f5fbf")  # obrys ještě není plně určený
COLOR_DONE = QColor("#1b1b1b")
COLOR_SELECTED = QColor("#ff8c00")
COLOR_FAILED = QColor("#c0392b")
COLOR_CONSTRUCTION = QColor("#8a8a8a")
COLOR_GRID = QColor("#ececec")
COLOR_TEXT = QColor("#666666")

# Vazba → značka u čáry na kreslicí ploše.
GLYPHS = {"horizontal": "H", "vertical": "V", "parallel": "∥", "perpendicular": "⊥",
          "tangent": "T", "equal": "=", "midpoint": "½", "fix": "⚓", "coincident": "●"}

TOOL_HELP = {
    "select": "Klik = vybrat (Ctrl+klik přidá), tažením posuneš bod. Pak tlačítkem vlevo "
              "přidej vazbu nebo kótu.",
    "line": "Klikej body obrysu jeden po druhém. Klik na existující bod = napojení. "
            "Esc nebo pravé tlačítko = konec čáry.",
    "arc": "Oblouk: klikni začátek, konec a pak bod, kudy má oblouk vést.",
}


def _plural(n: int, one: str, few: str, many: str) -> str:
    return one if n == 1 else few if 1 < n < 5 else many


class SketchCanvas(QWidget):
    """Kreslicí plocha. Souřadnice světa jsou v mm, osa Y míří nahoru."""

    def __init__(self, dialog: SketcherDialog) -> None:
        super().__init__(dialog)
        self.dialog = dialog
        self.setMinimumSize(560, 420)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.scale = 6.0  # pixelů na mm
        self.center = QPointF(20, 15)  # bod světa uprostřed plochy
        self._pan_from: QPointF | None = None

    # --- převody souřadnic ----------------------------------------------------------

    def transform(self) -> QTransform:
        t = QTransform()
        t.translate(self.width() / 2, self.height() / 2)
        t.scale(self.scale, -self.scale)
        t.translate(-self.center.x(), -self.center.y())
        return t

    def to_screen(self, x: float, y: float) -> QPointF:
        return self.transform().map(QPointF(x, y))

    def to_world(self, pos: QPointF) -> tuple[float, float]:
        point = self.transform().inverted()[0].map(pos)
        return point.x(), point.y()

    def fit(self) -> None:
        """Celý obrys (a počátek) do okna."""
        profile = self.dialog.profile
        coordinates = [(0.0, 0.0)] + [(float(x), float(y)) for x, y in profile["points"].values()]
        for name in profile["segments"]:  # oblouky se vyboulí za své body
            coordinates += self.dialog.polyline(name)
        xs, ys = [x for x, _ in coordinates], [y for _, y in coordinates]
        if len(coordinates) == 1:
            xs, ys = [0.0, 60.0], [0.0, 40.0]
        width, height = max(xs) - min(xs), max(ys) - min(ys)
        self.center = QPointF((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2)
        self.scale = max(0.05, min((self.width() - 120) / max(width, 1.0),
                                   (self.height() - 120) / max(height, 1.0)))
        self.update()

    # --- myš --------------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.setFocus()
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._pan_from = event.position()
            self._pan_moved = False
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.dialog.press(*self.to_world(event.position()), event.modifiers())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._pan_from is not None:
            delta = event.position() - self._pan_from
            if delta.manhattanLength() > 2:
                self._pan_moved = True
            self.center -= QPointF(delta.x() / self.scale, -delta.y() / self.scale)
            self._pan_from = event.position()
            self.update()
            return
        self.dialog.move(*self.to_world(event.position()))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._pan_from is not None:
            moved = self._pan_moved
            self._pan_from = None
            if event.button() == Qt.MouseButton.RightButton and not moved:
                self.dialog.finish_drawing()  # pravý klik bez tažení = konec čáry
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.dialog.release(*self.to_world(event.position()))

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        before = self.to_world(event.position())
        factor = 1.15 ** (event.angleDelta().y() / 120)
        self.scale = max(0.05, min(500.0, self.scale * factor))
        after = self.to_world(event.position())
        self.center += QPointF(before[0] - after[0], before[1] - after[1])
        self.update()

    # --- kreslení ---------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("white"))
        self._paint_grid(painter)
        dialog = self.dialog
        profile = dialog.profile
        failed_refs = dialog.failed_references()
        marked = set(dialog.selection) | dialog.listed_references()
        done = dialog.solution is not None and dialog.solution.ok and dialog.solution.dof == 0
        base = COLOR_DONE if done else COLOR_FREE

        for name, segment in profile["segments"].items():
            color = base
            if segment.get("construction"):
                color = COLOR_CONSTRUCTION
            if name in failed_refs:
                color = COLOR_FAILED
            if name in marked:
                color = COLOR_SELECTED
            pen = QPen(color, 3 if name in marked else 2)
            if segment.get("construction"):
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawPolyline(QPolygonF([self.to_screen(*p) for p in dialog.polyline(name)]))

        self._paint_preview(painter)
        self._paint_labels(painter)

        for name in [ORIGIN, *profile["points"]]:
            x, y = edit.point_xy(profile, name)
            pos = self.to_screen(x, y)
            if name == ORIGIN:
                color = COLOR_SELECTED if name in marked else QColor("#2e7d32")
                painter.setPen(QPen(color, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(pos, 6, 6)
                continue
            color = (COLOR_SELECTED if name in marked
                     else COLOR_FAILED if name in failed_refs else base)
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            painter.drawRect(QRectF(pos.x() - 3.5, pos.y() - 3.5, 7, 7))
        painter.end()

    def _paint_grid(self, painter: QPainter) -> None:
        step = 10 ** math.floor(math.log10(max(25 / self.scale, 1e-6)))
        for factor in (1, 2, 5, 10):
            if step * factor * self.scale >= 25:
                step *= factor
                break
        x0, y1 = self.to_world(QPointF(0, 0))
        x1, y0 = self.to_world(QPointF(self.width(), self.height()))
        painter.setPen(QPen(COLOR_GRID, 1))
        x = math.floor(x0 / step) * step
        while x <= x1:
            painter.drawLine(self.to_screen(x, y0), self.to_screen(x, y1))
            x += step
        y = math.floor(y0 / step) * step
        while y <= y1:
            painter.drawLine(self.to_screen(x0, y), self.to_screen(x1, y))
            y += step
        painter.setPen(QPen(QColor("#e57373"), 1))
        painter.drawLine(self.to_screen(x0, 0), self.to_screen(x1, 0))
        painter.setPen(QPen(QColor("#81c784"), 1))
        painter.drawLine(self.to_screen(0, y0), self.to_screen(0, y1))
        painter.setPen(COLOR_TEXT)
        painter.drawText(8, self.height() - 8, f"mřížka {step:g} mm")

    def _paint_preview(self, painter: QPainter) -> None:
        dialog = self.dialog
        if dialog.hover is None:
            return
        pen = QPen(COLOR_SELECTED, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        hover = dialog.snap(*dialog.hover)[1]
        if dialog.tool == "line" and dialog.chain_start:
            start = edit.point_xy(dialog.profile, dialog.chain_start)
            painter.drawLine(self.to_screen(*start), self.to_screen(*hover))
        elif dialog.tool == "arc" and len(dialog.arc_points) == 1:
            start = edit.point_xy(dialog.profile, dialog.arc_points[0])
            painter.drawLine(self.to_screen(*start), self.to_screen(*hover))
        elif dialog.tool == "arc" and len(dialog.arc_points) == 2:
            start, end = (edit.point_xy(dialog.profile, n) for n in dialog.arc_points)
            try:
                center, ccw = edit.arc_through(start, end, hover)
            except EditError:
                return
            a, b = (start, end) if ccw else (end, start)
            points = _arc_points(a, b, center)
            painter.drawPolyline(QPolygonF([self.to_screen(*p) for p in points]))

    def _paint_labels(self, painter: QPainter) -> None:
        dialog = self.dialog
        profile = dialog.profile
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1))
        painter.setFont(small)
        glyphs: dict[str, list[str]] = {}
        for index, constraint in enumerate(profile["constraints"]):
            kind = constraint["type"]
            color = COLOR_FAILED if index in dialog.failed() else QColor("#7b1fa2")
            if kind in DIMENSIONS:
                anchor, text = dialog.dimension_label(constraint)
                if anchor is not None:
                    pos = self.to_screen(*anchor) + self._label_offset(constraint)
                    painter.setPen(color)
                    painter.drawText(QRectF(pos.x() - 60, pos.y() - 9, 120, 18),
                                     Qt.AlignmentFlag.AlignCenter, text)
            elif kind in GLYPHS:
                for ref in edit.references(constraint):
                    glyphs.setdefault(ref, []).append(GLYPHS[kind])
        painter.setPen(COLOR_TEXT)
        for name in profile["segments"]:
            mid = dialog.midpoint(name)
            pos = self.to_screen(*mid)
            label = name + ("  " + " ".join(glyphs.get(name, [])) if glyphs.get(name) else "")
            painter.drawText(QPointF(pos.x() + 6, pos.y() + 14), label)
        for name in profile["points"]:
            pos = self.to_screen(*edit.point_xy(profile, name))
            label = name + (" " + " ".join(glyphs[name]) if name in glyphs else "")
            painter.drawText(QPointF(pos.x() + 6, pos.y() - 6), label)


    def _label_offset(self, constraint: dict[str, Any]) -> QPointF:
        """Popisek kóty délky kousek vedle čáry (ne přes ni): nad vodorovnou, vpravo od
        svislé. Ostatní kóty o kousek nahoru."""
        if constraint["type"] != "length":
            return QPointF(0, -13)
        segment = self.dialog.profile["segments"].get(constraint["segment"])
        if segment is None:
            return QPointF(0, -13)
        a = self.to_screen(*edit.point_xy(self.dialog.profile, segment["start"]))
        b = self.to_screen(*edit.point_xy(self.dialog.profile, segment["end"]))
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        if abs(ny) < 0.3:  # skoro svislá čára → popisek vpravo
            nx, ny = abs(nx), ny
        elif ny > 0:  # jinak nad čáru (na obrazovce y roste dolů)
            nx, ny = -nx, -ny
        distance = 13 if abs(ny) >= 0.3 else 30
        return QPointF(nx * distance, ny * distance)


def _arc_points(start: tuple, end: tuple, center: tuple, steps: int = 48) -> list[tuple]:
    radius = math.dist(start, center)
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    if a1 <= a0:
        a1 += 2 * math.pi
    return [(center[0] + radius * math.cos(a0 + (a1 - a0) * i / steps),
             center[1] + radius * math.sin(a0 + (a1 - a0) * i / steps)) for i in range(steps + 1)]


def _distance_to_segment(p: tuple, a: tuple, b: tuple) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    length2 = (bx - ax) ** 2 + (by - ay) ** 2
    if length2 == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / length2))
    return math.dist(p, (ax + t * (bx - ax), ay + t * (by - ay)))


class SketcherDialog(QDialog):
    """Skicář obrysu. ``solve`` = ``ModelSession.solve_profile``."""

    def __init__(self, profile: dict[str, Any], solve: Callable[[dict], Any],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Skicář – obrys z úseček a oblouků")
        self.resize(1180, 760)
        self.profile = copy.deepcopy(profile)
        for key, empty in (("points", {}), ("segments", {}), ("constraints", [])):
            self.profile.setdefault(key, copy.deepcopy(empty))
        self._solve = solve
        self.solution = None
        self.tool = "select"
        self.selection: list[str] = []
        self.chain_start: str | None = None
        self.arc_points: list[str] = []
        self.hover: tuple[float, float] | None = None
        self._drag: str | None = None
        self._drag_moved = False
        self._history: list[dict[str, Any]] = []

        self.canvas = SketchCanvas(self)
        self._build()
        self.set_tool("line" if not self.profile["segments"] else "select")
        self._resolve()

    # --- stavba okna -------------------------------------------------------------------

    def _act(self, text: str, slot: Callable[[], object], shortcut: str | None = None,
             tip: str = "") -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.setToolTip(f"{tip or text} ({shortcut})" if shortcut else (tip or text))
        action.triggered.connect(lambda _checked=False: slot())  # bez „checked“ (viz CLAUDE.md)
        self.addAction(action)
        return action

    def _group(self, title: str, actions: list[QAction], columns: int = 2) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        grid.setSpacing(4)
        for index, action in enumerate(actions):
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            grid.addWidget(button, index // columns, index % columns)
        return box

    def _build(self) -> None:
        self.tool_actions = {
            "select": self._act("Výběr", lambda: self.set_tool("select"), "S"),
            "line": self._act("Úsečka", lambda: self.set_tool("line"), "L"),
            "arc": self._act("Oblouk", lambda: self.set_tool("arc"), "A"),
        }
        for action in self.tool_actions.values():
            action.setCheckable(True)
        self.constraint_actions = {
            "horizontal": self._act("Vodorovně", lambda: self.apply_constraint("horizontal"), "H"),
            "vertical": self._act("Svisle", lambda: self.apply_constraint("vertical"), "V"),
            "parallel": self._act("Rovnoběžně", lambda: self.apply_constraint("parallel"), "P"),
            "perpendicular": self._act("Kolmo", lambda: self.apply_constraint("perpendicular"),
                                       "K"),
            "tangent": self._act("Tečně", lambda: self.apply_constraint("tangent"), "T"),
            "equal": self._act("Stejně velké", lambda: self.apply_constraint("equal"), "E"),
            "coincident": self._act("Na bodě/čáře", lambda: self.apply_constraint("coincident"),
                                    "C", "Bod leží na jiném bodě, čáře nebo v počátku"),
            "midpoint": self._act("Uprostřed", lambda: self.apply_constraint("midpoint"), "M"),
            "fix": self._act("Pevný bod", lambda: self.apply_constraint("fix"), "F"),
        }
        self.dimension_action = self._act("Kóta…", self.add_dimension, "D",
                                          "Délka úsečky, poloměr oblouku, vzdálenost, úhel")
        self.construction_action = self._act("Pomocná čára", self.toggle_construction, "G",
                                             "Čára jen pro vazby – nebude součástí obrysu")
        self.delete_action = self._act("Smazat", self.delete_selected, "Delete")
        self.undo_action = self._act("Zpět", self.undo, "Ctrl+Z")
        self.fit_action = self._act("Celý obrys", self.canvas.fit, "0")

        tools = QVBoxLayout()
        tools.addWidget(self._group("Kreslení", list(self.tool_actions.values()), columns=3))
        tools.addWidget(self._group("Vazby (na vybrané)", list(self.constraint_actions.values())))
        tools.addWidget(self._group("Kóty a úpravy", [self.dimension_action,
                                                       self.construction_action,
                                                       self.delete_action, self.undo_action,
                                                       self.fit_action]))
        self.help_label = QLabel()
        self.help_label.setWordWrap(True)
        self.help_label.setStyleSheet("color: #555;")
        tools.addWidget(self.help_label)
        tools.addStretch(1)
        tools_widget = QWidget()
        tools_widget.setLayout(tools)
        tools_widget.setFixedWidth(250)

        side = QVBoxLayout()
        side.addWidget(QLabel("Vazby a kóty (dvojklik = změnit hodnotu):"))
        self.constraint_list = QListWidget()
        self.constraint_list.setObjectName("constraint_list")
        self.constraint_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.constraint_list.itemDoubleClicked.connect(
            lambda item: self.edit_constraint_value(self.constraint_list.row(item)))
        self.constraint_list.itemSelectionChanged.connect(self.canvas.update)
        side.addWidget(self.constraint_list, stretch=1)
        self.delete_constraint_action = self._act("Smazat vazbu", self.delete_constraints)
        button = QToolButton()
        button.setDefaultAction(self.delete_constraint_action)
        side.addWidget(button)
        self.status = QLabel()
        self.status.setObjectName("sketch_status")
        self.status.setWordWrap(True)
        side.addWidget(self.status)
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(300)

        middle = QHBoxLayout()
        middle.addWidget(tools_widget)
        middle.addWidget(self.canvas, stretch=1)
        middle.addWidget(side_widget)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Hotovo")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(middle, stretch=1)
        layout.addWidget(self.buttons)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self.canvas.fit)  # až po rozvržení okna (známá velikost plochy)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # Esc nesmí zavřít skicář (ztratila by se práce) – jen ukončí kreslení / výběr.
        if event.key() == Qt.Key.Key_Escape:
            if self.chain_start or self.arc_points:
                self.finish_drawing()
            elif self.selection:
                self.selection = []
                self.canvas.update()
            else:
                self.set_tool("select")
            return
        super().keyPressEvent(event)

    # --- veřejné API (okno i testy) --------------------------------------------------

    def result_profile(self) -> dict[str, Any]:
        return copy.deepcopy(self.profile)

    def set_tool(self, tool: str) -> None:
        self.finish_drawing()
        self.tool = tool
        for name, action in self.tool_actions.items():
            action.setChecked(name == tool)
        self.help_label.setText(TOOL_HELP[tool])
        self.canvas.setCursor(Qt.CursorShape.ArrowCursor if tool == "select"
                              else Qt.CursorShape.CrossCursor)
        self.canvas.update()

    def click(self, x: float, y: float, ctrl: bool = False) -> None:
        """Klik do plochy (souřadnice v mm) – pro testy; myš volá press/release."""
        self.press(x, y, Qt.KeyboardModifier.ControlModifier if ctrl else None)
        self.release(x, y)

    def press(self, x: float, y: float, modifiers: Any = None) -> None:
        if self.tool == "select":
            hit = self.hit(x, y)
            toggle = modifiers is not None and bool(
                modifiers & (Qt.KeyboardModifier.ControlModifier
                             | Qt.KeyboardModifier.ShiftModifier))
            if hit is None:
                if not toggle:
                    self.selection = []
            elif toggle:
                if hit in self.selection:
                    self.selection.remove(hit)
                else:
                    self.selection.append(hit)
            elif hit not in self.selection:
                self.selection = [hit]
            if hit in self.profile["points"] and not toggle:
                self._drag, self._drag_moved = hit, False
            self.canvas.update()
        elif self.tool == "line":
            self._line_click(x, y)
        elif self.tool == "arc":
            self._arc_click(x, y)

    def move(self, x: float, y: float) -> None:
        self.hover = (x, y)
        if self._drag is not None:
            if not self._drag_moved:
                self._remember()
                self._drag_moved = True
            self.profile["points"][self._drag] = [round(x, 4), round(y, 4)]
            self._resolve(hold=self._drag)
        self.canvas.update()

    def release(self, x: float, y: float) -> None:
        if self._drag is not None and self._drag_moved:
            self._resolve()
        self._drag = None

    def finish_drawing(self) -> None:
        self.chain_start = None
        self.arc_points = []
        self.canvas.update()

    def select(self, names: list[str]) -> None:
        self.selection = list(names)
        self.canvas.update()

    def apply_constraint(self, kind: str) -> None:
        try:
            new = edit.constraints_for(self.profile, kind, self.selection)
        except EditError as exc:
            self._message(str(exc), error=True)
            return
        self._remember()
        self.profile["constraints"].extend(new)
        self.selection = []
        self._resolve()

    def add_dimension(self) -> None:
        try:
            [constraint] = edit.constraints_for(self.profile, "dimension", self.selection)
        except EditError as exc:
            self._message(str(exc), error=True)
            return
        value = self._ask_value(constraint, constraint["value"])
        if value is None:
            return
        self._remember()
        constraint["value"] = value
        self.profile["constraints"].append(constraint)
        self.selection = []
        self._resolve()

    def edit_constraint_value(self, index: int) -> None:
        if not 0 <= index < len(self.profile["constraints"]):
            return
        constraint = self.profile["constraints"][index]
        if constraint["type"] not in DIMENSIONS:
            self._message("Tahle vazba nemá hodnotu – změnit jde jen kóta.", error=False)
            return
        value = self._ask_value(constraint, constraint["value"])
        if value is None:
            return
        self._remember()
        constraint["value"] = value
        self._resolve()

    def delete_selected(self) -> None:
        if not self.selection:
            self.delete_constraints()
            return
        self._remember()
        edit.remove(self.profile, self.selection)
        self.selection = []
        self._resolve()

    def delete_constraints(self) -> None:
        rows = sorted({self.constraint_list.row(item)
                       for item in self.constraint_list.selectedItems()})
        if not rows:
            self._message("Vyber vazbu v seznamu vpravo (nebo body a čáry v ploše).", error=False)
            return
        self._remember()
        edit.remove_constraints(self.profile, rows)
        self._resolve()

    def toggle_construction(self) -> None:
        try:
            edit.toggle_construction(copy.deepcopy(self.profile), self.selection)
        except EditError as exc:
            self._message(str(exc), error=True)
            return
        self._remember()
        edit.toggle_construction(self.profile, self.selection)
        self._resolve()

    def undo(self) -> None:
        if self._history:
            self.profile = self._history.pop()
            self.selection = []
            self.finish_drawing()
            self._resolve()

    # --- kreslení ---------------------------------------------------------------------

    def snap(self, x: float, y: float) -> tuple[str | None, tuple[float, float]]:
        """Nejbližší bod (i počátek) v dosahu kliknutí, jinak None a místo kliknutí."""
        tolerance = SNAP_PIXELS / self.canvas.scale
        best, best_distance = None, tolerance
        for name in [ORIGIN, *self.profile["points"]]:
            distance = math.dist((x, y), edit.point_xy(self.profile, name))
            if distance <= best_distance:
                best, best_distance = name, distance
        if best is None:
            return None, (x, y)
        return best, edit.point_xy(self.profile, best)

    def _point_at(self, x: float, y: float) -> str:
        """Bod pro kreslení: existující v dosahu, nebo nový. Počátek → nový bod na něm."""
        name, _ = self.snap(x, y)
        if name == ORIGIN:
            new = edit.add_point(self.profile, 0.0, 0.0)
            self.profile["constraints"].append({"type": "coincident", "point": new,
                                                "on": ORIGIN})
            return new
        return name if name is not None else edit.add_point(self.profile, x, y)

    def _line_click(self, x: float, y: float) -> None:
        if self.chain_start is None:
            self._remember()
            self.chain_start = self._point_at(x, y)
            self.canvas.update()
            return
        target, _ = self.snap(x, y)
        if target == self.chain_start:
            return
        self._remember()
        end = self._point_at(x, y)
        line = edit.add_line(self.profile, self.chain_start, end)
        self.profile["constraints"].extend(edit.auto_constraints(self.profile, line))
        closed = target is not None and target != ORIGIN
        self.chain_start = None if closed else end
        self._resolve()

    def _arc_click(self, x: float, y: float) -> None:
        if len(self.arc_points) < 2:
            if not self.arc_points:
                self._remember()
            name = self._point_at(x, y)
            if self.arc_points and name == self.arc_points[0]:
                return
            self.arc_points.append(name)
            self.canvas.update()
            return
        start, end = (edit.point_xy(self.profile, n) for n in self.arc_points)
        try:
            center, ccw = edit.arc_through(start, end, (x, y))
        except EditError as exc:
            self._message(str(exc), error=True)
            return
        first, second = self.arc_points if ccw else self.arc_points[::-1]
        middle = edit.add_point(self.profile, *center)
        edit.add_arc(self.profile, first, second, middle)
        self.arc_points = []
        self._resolve()

    # --- výpočet a zobrazení ---------------------------------------------------------

    def _remember(self) -> None:
        self._history.append(copy.deepcopy(self.profile))
        del self._history[:-100]

    def _resolve(self, hold: str | None = None) -> None:
        """Vyřeší obrys; při úspěchu uloží vyřešené polohy bodů zpět do obrysu."""
        profile = self.profile
        if not profile["points"]:
            self.solution = None
        else:
            target = profile
            if hold is not None:  # tažený bod drží na místě myši, zbytek se přizpůsobí
                target = copy.deepcopy(profile)
                target["constraints"].append({"type": "fix", "point": hold})
            self.solution = self._solve(target)
            if hold is not None and not self.solution.ok:
                self.solution = self._solve(profile)  # bod je plně určený – nepohne se
            if self.solution.ok:
                for name, (x, y) in self.solution.points.items():
                    profile["points"][name] = [round(x, 6) + 0.0, round(y, 6) + 0.0]
                for name, radius in self.solution.radii.items():
                    profile["segments"][name]["radius"] = round(radius, 6) + 0.0
        self._refresh_list()
        self._refresh_status()
        self.canvas.update()

    def failed(self) -> set[int]:
        if self.solution is None or self.solution.ok:
            return set()
        return set(self.solution.failed)

    def failed_references(self) -> set[str]:
        """Body a čáry vazeb, které si odporují (kreslí se červeně)."""
        return self._references(self.failed())

    def listed_references(self) -> set[str]:
        """Body a čáry vazeb vybraných v seznamu vpravo (kreslí se oranžově)."""
        return self._references({self.constraint_list.row(item)
                                 for item in self.constraint_list.selectedItems()})

    def _references(self, indexes: set[int]) -> set[str]:
        refs: set[str] = set()
        for index in indexes:
            if index < len(self.profile["constraints"]):
                refs |= set(edit.references(self.profile["constraints"][index]))
        return refs

    def _refresh_list(self) -> None:
        failed = self.failed()
        self.constraint_list.blockSignals(True)
        self.constraint_list.clear()
        for index, constraint in enumerate(self.profile["constraints"]):
            item = QListWidgetItem(constraint_text(index, constraint))
            if index in failed:
                item.setForeground(COLOR_FAILED)
            self.constraint_list.addItem(item)
        self.constraint_list.blockSignals(False)

    def _refresh_status(self) -> None:
        solution = self.solution
        if solution is None:
            self._message("Prázdná skica – vyber nástroj Úsečka a klikej body obrysu.")
            return
        if not solution.ok:
            self._message(solution.message, error=True)
            return
        try:
            loops(self.profile, {name: tuple(p) for name, p in self.profile["points"].items()})
            closed = ""
        except SolveError as exc:
            closed = f"<br><span style='color:#b26a00'>{exc}</span>"
        collapsed = [name for name, segment in self.profile["segments"].items()
                     if segment["type"] == "line"
                     and math.dist(*self.polyline(name)) < 1e-6]
        if collapsed:
            closed += ("<br><span style='color:#c0392b'>Čára " + ", ".join(collapsed)
                       + " má nulovou délku – vazby ji smrskly do bodu (třeba vodorovně i "
                       "svisle zároveň). Vrať to tlačítkem Zpět.</span>")
        if solution.dof == 0:
            text = "<span style='color:#1b7f3b'>✓ Obrys je plně určený.</span>"
        else:
            word = _plural(solution.dof, "rozměr", "rozměry", "rozměrů")
            text = (f"<span style='color:#1f5fbf'>Zbývá určit {solution.dof} {word} – přidej "
                    "vazby nebo kóty (modrý obrys jde ještě posunout tažením bodu).</span>")
        self.status.setText(text + closed)

    def _message(self, text: str, error: bool = False) -> None:
        color = "#c0392b" if error else "#555"
        self.status.setText(f"<span style='color:{color}'>{text}</span>")

    def _ask_value(self, constraint: dict[str, Any], current: Any) -> Any | None:
        label = constraint_text(len(self.profile["constraints"]), constraint).split("(", 1)[-1]
        unit = "°" if constraint["type"] == "angle" else "mm"
        text, ok = QInputDialog.getText(
            self, "Kóta", f"Hodnota ({label.rstrip(')')}) v {unit} – číslo nebo výraz "
            "s parametry (např. sirka/2):", text=str(current))
        if not ok or not text.strip():
            return None
        text = text.strip().replace(",", ".") if _is_number(text) else text.strip()
        if _is_number(text):
            number = float(text)
            return int(number) if number.is_integer() else number
        return text

    # --- geometrie pro kreslení a výběr -------------------------------------------------

    def polyline(self, name: str) -> list[tuple[float, float]]:
        segment = self.profile["segments"][name]
        start = edit.point_xy(self.profile, segment["start"])
        end = edit.point_xy(self.profile, segment["end"])
        if segment["type"] == "line":
            return [start, end]
        return _arc_points(start, end, edit.point_xy(self.profile, segment["center"]))

    def midpoint(self, name: str) -> tuple[float, float]:
        segment = self.profile["segments"][name]
        start = edit.point_xy(self.profile, segment["start"])
        end = edit.point_xy(self.profile, segment["end"])
        if segment["type"] == "line":
            return (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        return arc_midpoint(start, end, edit.point_xy(self.profile, segment["center"]))

    def hit(self, x: float, y: float) -> str | None:
        name, _ = self.snap(x, y)
        if name is not None:
            return name
        tolerance = HIT_PIXELS / self.canvas.scale
        best, best_distance = None, tolerance
        for segment in self.profile["segments"]:
            points = self.polyline(segment)
            distance = min(_distance_to_segment((x, y), a, b)
                           for a, b in zip(points, points[1:], strict=False))
            if distance <= best_distance:
                best, best_distance = segment, distance
        return best

    def dimension_label(self, constraint: dict[str, Any]) -> tuple[tuple | None, str]:
        kind, value = constraint["type"], constraint["value"]
        try:
            if kind in ("length", "radius"):
                anchor = self.midpoint(constraint["segment"])
            elif kind == "distance" and "points" in constraint:
                a, b = (edit.point_xy(self.profile, n) for n in constraint["points"])
                anchor = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            elif kind == "distance":
                anchor = edit.point_xy(self.profile, constraint["point"])
            else:
                anchor = self.midpoint(constraint["segments"][0])
        except KeyError:
            return None, ""
        prefix = {"radius": "R", "angle": "∠ "}.get(kind, "")
        suffix = "°" if kind == "angle" else ""
        text = f"{prefix}{value}{suffix}"
        if isinstance(value, str):  # výraz s parametrem: číslo a v závorce výraz („R20 (R)“)
            try:
                text = f"{prefix}{edit.measure(self.profile, constraint):g}{suffix} ({value})"
            except (EditError, KeyError, ZeroDivisionError):
                pass
        return anchor, text


def _is_number(text: str) -> bool:
    try:
        float(text.strip().replace(",", "."))
    except ValueError:
        return False
    return True
