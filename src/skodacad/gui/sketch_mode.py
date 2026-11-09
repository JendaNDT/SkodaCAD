"""Skicář jako režim hlavního okna (P7.57, rám 2d návrhu 1a).

Logika skicáře (kreslení, vazby, kóty, řešič ``slvs`` přes ``ModelSession``, vlastní Zpět)
zůstává v ``SketcherDialog``. Režim si od něj jen vypůjčí:

* **plátno** – místo 3D pohledu (dítě prohlížeče, pod kartami, nad nativní plochou OCCT),
* **akce** – plovoucí paleta Skica: Výběr S, Úsečka L, Oblouk A, Kružnice R, Pomocná G |
  Kóta D, Promítnout U, Převzít W | Zrušit, Hotovo; zkratky platí v celém okně,
* **seznam vazeb** – skupina „Vazby skici“ v levé kartě pod stromem,
* **pravou kartu „Výběr“** – vazby, které pro výběr dávají smysl (doporučená primární,
  ostatní ve sbalené sekci), Kóta… a stav obrysu,
* **pilulku** – „Zbývá určit: N rozměrů“ nebo „✓ plně určeno“.

Okno mezitím čeká v místní smyčce událostí (jako dřív ``QDialog.exec``), takže volající
dostane obrys stejně jako z dialogu: Hotovo = jeden krok Zpět v modelu, Zrušit nic
nemění. Esc ukončí řetěz čar, druhé Esc zruší výběr. Ostatní akce okna jsou zamčené.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QEventLoop, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from skodacad import profile_edit as edit
from skodacad.gui import ui_theme
from skodacad.gui.cad_icons import icon as cad_icon
from skodacad.gui.ribbon import RibbonButton
from skodacad.gui.sketcher import COLOR_REFERENCE, TOOL_HELP, SketcherDialog, _plural
from skodacad.gui.status_pill import ViewSwitcher
from skodacad.gui.tool_cards import FlowLayout
from skodacad.gui.workspace import Section
from skodacad.profile_edit import EditError
from skodacad.solver import CONSTRAINT_LABELS, ORIGIN

if TYPE_CHECKING:
    from skodacad.gui.main_window import MainWindow

# Pořadí doporučení: první vazba, která pro výběr dává smysl, je primární (rám 2d).
RECOMMENDED = ("tangent", "coincident", "concentric", "equal", "symmetric", "perpendicular",
               "parallel", "horizontal", "vertical", "midpoint", "fix")
TOP_COUNT = 4  # vazeb v mřížce nahoře, další ve sbalené sekci „Ostatní vazby“
KIND_WORDS = {"point": ("bod", "body", "bodů"), "origin": ("počátek",) * 3,
              "line": ("úsečka", "úsečky", "úseček"), "arc": ("oblouk", "oblouky", "oblouků"),
              "circle": ("kružnice", "kružnice", "kružnic"),
              "reference": ("promítnutá hrana", "promítnuté hrany", "promítnutých hran")}
PALETTE = (("tool", "select", "Výběr", "select"), ("tool", "line", "Úsečka", "line"),
           ("tool", "arc", "Oblouk", "arc"), ("tool", "circle", "Kružnice", "circle"),
           ("construction", None, "Pomocná", "construction"), None,
           ("dimension", None, "Kóta", "dimension"), ("tool", "project", "Promítnout", "project"),
           ("convert", None, "Převzít", "convert"))


def selection_title(dialog: SketcherDialog) -> str:
    """„Úsečka a kružnice“, „2 body“ – co je ve skicáři vybráno (hlavička pravé karty)."""
    profile = dialog.profile
    references = set(edit.references_of(profile))
    counts: dict[str, int] = {}
    for name in dialog.selection:
        if name == ORIGIN:
            kind = "origin"
        elif name in references:
            kind = "reference"
        elif name in profile["segments"]:
            kind = profile["segments"][name]["type"]
        else:
            kind = "point"
        counts[kind] = counts.get(kind, 0) + 1
    words = [KIND_WORDS.get(kind, (kind,) * 3)[0] if n == 1
             else f"{n} {_plural(n, *KIND_WORDS.get(kind, (kind,) * 3))}"
             for kind, n in counts.items()]
    if not words:
        return "Bez výběru"
    text = words[0] if len(words) == 1 else ", ".join(words[:-1]) + " a " + words[-1]
    return text[0].upper() + text[1:]


def applicable(dialog: SketcherDialog) -> list[str]:
    """Vazby, které jádro pro aktuální výběr přijme (zkouší se na kopii obrysu)."""
    if not dialog.selection:
        return []
    found = []
    for kind in RECOMMENDED:
        try:
            edit.constraints_for(copy.deepcopy(dialog.profile), kind, list(dialog.selection))
        except EditError:
            continue
        except Exception:  # noqa: BLE001 – neznámý výběr = vazba se nenabídne
            continue
        found.append(kind)
    return found


# Značka druhu vazby vlevo v řádku (rám 2d); jen obecně dostupné znaky.
KIND_GLYPHS = {
    "fix": "▪", "coincident": "●", "horizontal": "─", "vertical": "│", "parallel": "∥",
    "perpendicular": "⊥", "tangent": "⌒", "equal": "=", "midpoint": "⊙", "concentric": "○",
    "symmetric": "⇔", "length": "↔", "distance": "↔", "radius": "R", "diameter": "Ø",
    "angle": "∠",
}
GLYPH_WIDTH = 20


class ConstraintRowDelegate(QStyledItemDelegate):
    """Řádek „Vazby skici“ (rám 2d): vlevo druh vazby, vpravo hodnota kóty nebo čeho se
    týká; text položky (``constraint_text``) se nemění – čtou ho testy i čtečky."""

    def __init__(self, dialog: SketcherDialog) -> None:
        super().__init__(dialog.constraint_list)
        self.dialog = dialog

    def sizeHint(self, option, index):  # noqa: N802
        return QSize(option.rect.width(), 24)

    def paint(self, painter, option, index):
        constraints = self.dialog.profile["constraints"]
        row = index.row()
        constraint = constraints[row] if 0 <= row < len(constraints) else {}
        kind = constraint.get("type") if isinstance(constraint, dict) else None
        label = CONSTRAINT_LABELS.get(kind, str(kind or ""))
        label = label[:1].upper() + label[1:]
        refs = []
        for key in ("point", "on", "segment"):
            if key in constraint:
                refs.append(str(constraint[key]))
        for key in ("points", "segments"):
            if isinstance(constraint.get(key), list):
                refs.extend(str(item) for item in constraint[key])
        refs = ["počátek" if ref == ORIGIN else ref for ref in refs]
        value = (f"{constraint['value']:g}" if isinstance(constraint.get("value"), (int, float))
                 else str(constraint["value"]) if "value" in constraint else ", ".join(refs))
        t = ui_theme.tokens()
        failed = row in self.dialog.failed()
        rect = option.rect.adjusted(6, 0, -6, 0)
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ui_theme.opaque(t["accentbg"], ui_theme.card_color()))
            painter.drawRoundedRect(option.rect.adjusted(0, 1, 0, -1), 6, 6)
        small = QFont(option.font)
        small.setPixelSize(11)
        painter.setFont(small)
        painter.setPen(ui_theme.color(t["err"] if failed else t["fg3"]))
        metrics = painter.fontMetrics()
        room = max(rect.width() // 2, 40)
        shown = metrics.elidedText(value, Qt.TextElideMode.ElideLeft, room)
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                         shown)
        glyph = KIND_GLYPHS.get(kind, "")
        glyph_rect = rect.adjusted(0, 0, 0, 0)
        glyph_rect.setWidth(GLYPH_WIDTH)
        painter.setFont(option.font)
        painter.setPen(ui_theme.color(t["err"] if failed else t["fg3"]))
        painter.drawText(glyph_rect, int(Qt.AlignmentFlag.AlignCenter), glyph)
        painter.setPen(ui_theme.color(t["err"] if failed else t["fg"]))
        left = rect.adjusted(GLYPH_WIDTH + 4, 0, -metrics.horizontalAdvance(shown) - 8, 0)
        painter.drawText(left, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight,
                                                          left.width()))
        painter.restore()


class SelectionPanel(QWidget):
    """Pravá karta „Výběr“: vazby pro výběr, Kóta…, Smazat / Zpět a stav obrysu."""

    def __init__(self, dialog: SketcherDialog) -> None:
        super().__init__()
        self.setObjectName("sketch_selection")
        self.dialog = dialog
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 10)
        layout.setSpacing(6)
        self.hint = QLabel()
        self.hint.setObjectName("sketch_hint")
        self.hint.setWordWrap(True)
        self.hint.setProperty("cardHint", True)
        layout.addWidget(self.hint)
        self.add_label = QLabel("Přidat vazbu")
        layout.addWidget(self.add_label)
        grid_box = QWidget()
        self.grid = QGridLayout(grid_box)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        layout.addWidget(grid_box)
        other_box = QWidget()
        self.other = FlowLayout(other_box)
        self.others_section = Section("Ostatní vazby", other_box)
        layout.addWidget(self.others_section)
        self.top: dict[str, QPushButton] = {}
        self.rest: dict[str, QPushButton] = {}
        for kind in RECOMMENDED:
            action = dialog.constraint_actions[kind]
            for store in (self.top, self.rest):
                button = QPushButton(action.text())
                button.setObjectName(f"sketch_{kind}")
                button.setProperty("role", "secondary")
                button.setToolTip(action.toolTip())
                button.clicked.connect(lambda _c=False, a=action: a.trigger())
                button.hide()
                store[kind] = button
            self.other.addWidget(self.rest[kind])
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: palette(mid);")
        layout.addWidget(line)
        dimension = QHBoxLayout()
        label = QLabel("Rozměr mezi výběrem")
        label.setProperty("cardHint", True)
        dimension.addWidget(label, 1)
        self.dimension = QPushButton("Kóta… D")
        self.dimension.setObjectName("sketch_dimension")
        self.dimension.setProperty("role", "secondary")
        self.dimension.setToolTip(dialog.dimension_action.toolTip())
        self.dimension.clicked.connect(lambda _c=False: dialog.dimension_action.trigger())
        dimension.addWidget(self.dimension)
        layout.addLayout(dimension)
        edits = QHBoxLayout()
        for text, action in (("Smazat", dialog.delete_action),
                             ("Zpět ve skice", dialog.undo_action),
                             ("Celý obrys", dialog.fit_action)):
            button = QPushButton(text)
            button.setProperty("role", "secondary")
            button.setToolTip(action.toolTip())
            button.clicked.connect(lambda _c=False, a=action: a.trigger())
            edits.addWidget(button)
        edits.addStretch()
        layout.addLayout(edits)
        self.status = QLabel()
        self.status.setObjectName("sketch_card_status")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.RichText)
        self.status.setProperty("cardState", "info")
        layout.addWidget(self.status)
        layout.addStretch(1)

    def refresh(self) -> list[str]:
        dialog = self.dialog
        kinds = applicable(dialog)
        shown_top, shown_rest = kinds[:TOP_COUNT], kinds[TOP_COUNT:]
        while self.grid.count():
            self.grid.takeAt(0)
        for index, kind in enumerate(shown_top):
            button = self.top[kind]
            role = "primary" if index == 0 else "secondary"
            if button.property("role") != role:
                button.setProperty("role", role)
                button.style().unpolish(button)
                button.style().polish(button)
            self.grid.addWidget(button, index // 2, index % 2)
        for kind, button in self.top.items():
            button.setVisible(kind in shown_top)
        for kind, button in self.rest.items():
            button.setVisible(kind in shown_rest)
        self.others_section.set_count(len(shown_rest) or "")
        self.others_section.setVisible(bool(shown_rest))
        self.add_label.setVisible(bool(kinds))
        self.hint.setText(TOOL_HELP[dialog.tool] if not dialog.selection else
                          "" if kinds else "Pro tenhle výběr žádná vazba nejde – zkus jiné "
                          "body nebo čáry, nebo dej Kótu.")
        self.hint.setVisible(bool(self.hint.text()))
        # P7.75, rám 2d: karta ukáže jen varování a chyby; „Zbývá určit…“ je v pilulce
        self.status.setText(dialog.warnings)
        self.status.setVisible(bool(dialog.warnings))
        return kinds


class SketchPalette(QWidget):
    """Plovoucí paleta Skica (rám 2d): nástroje, kóty a převzetí, Zrušit a Hotovo."""

    def __init__(self, dialog: SketcherDialog) -> None:
        super().__init__()
        self.setObjectName("sketch_palette")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        self.buttons: dict[str, RibbonButton] = {}
        actions = {"construction": dialog.construction_action,
                   "dimension": dialog.dimension_action, "convert": dialog.convert_action}
        color = QApplication.palette().color(QPalette.ColorRole.Link).name()
        for item in PALETTE:
            if item is None:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.VLine)
                line.setStyleSheet("color: palette(mid);")
                line.setContentsMargins(0, 6, 0, 6)
                layout.addWidget(line)
                continue
            source, key, label, icon = item
            action = dialog.tool_actions[key] if source == "tool" else actions[source]
            tint = (COLOR_REFERENCE.name() if icon in ("project", "convert")
                    else QApplication.palette().color(QPalette.ColorRole.PlaceholderText).name()
                    if icon == "construction" else color)
            action.setIcon(cad_icon(icon, tint))
            button = RibbonButton(action, label)
            shortcut = action.shortcut().toString()
            button.setToolTip(f"{action.toolTip()}")
            button.setAccessibleName(f"{label} ({shortcut})" if shortcut else label)
            self.buttons[key or source] = button
            layout.addWidget(button)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet("color: palette(mid);")
        layout.addWidget(line)
        self.cancel = QPushButton("Zrušit")
        self.cancel.setObjectName("sketch_cancel")
        self.cancel.setProperty("role", "secondary")
        self.cancel.setToolTip("Zahodí úpravy skici; model se nezmění")
        self.cancel.clicked.connect(dialog.reject)
        self.done = QPushButton("Hotovo")
        self.done.setObjectName("sketch_done")
        self.done.setProperty("role", "primary")
        self.done.setToolTip("Převezme obrys do modelu (jeden krok Zpět)")
        self.done.clicked.connect(dialog.accept)
        layout.addWidget(self.cancel)
        layout.addWidget(self.done)

    def fit_width(self, room: int) -> None:
        """Úzké okno (P7.64): nástroje jen ikonami, Zrušit a Hotovo zůstávají s textem."""
        for button in self.buttons.values():
            button.set_compact(False)
        self.layout().invalidate()
        if self.sizeHint().width() + 2 > room:
            for button in self.buttons.values():
                button.set_compact(True)
            self.layout().invalidate()
        self.updateGeometry()


class SketchMode(QObject):
    """Jeden běh skicáře v hlavním okně; ``run()`` vrací výsledek jako ``QDialog.exec``."""

    def __init__(self, window: MainWindow, dialog: SketcherDialog) -> None:
        super().__init__(window)
        self.window, self.dialog = window, dialog
        self.canvas = dialog.canvas
        self.loop = QEventLoop()
        self._states: list[tuple[QAction, bool]] = []
        self._restore: dict = {}
        self.escape_action = QAction("Ukončit čáru / zrušit výběr", window)
        self.escape_action.setShortcut("Esc")
        self.escape_action.triggered.connect(lambda _c=False: dialog.escape())

    # --- běh ---------------------------------------------------------------------------

    def run(self) -> int:
        window, dialog = self.window, self.dialog
        window._sketch_mode = self
        self._enter()
        dialog.finished.connect(self.loop.quit)
        dialog.changed.connect(self.refresh)
        QTimer.singleShot(0, self._fit)
        try:
            if dialog.result() == 0 and not self._closed():
                self.loop.exec()
        finally:
            self._leave()
            window._sketch_mode = None
        return dialog.result()

    def _closed(self) -> bool:
        return not isValid(self.dialog)

    def _fit(self) -> None:
        if isValid(self.canvas) and self.canvas.isVisible():
            self.window.card_layer.relayout()
            self._margins()
            self.canvas.fit()

    def _center_origin(self) -> None:
        if isValid(self.canvas):
            self._margins()
            self.canvas.center_origin()

    def _margins(self) -> None:
        """Karty zakrývají okraje plochy – „Celý obrys“ se vejde mezi ně."""
        free = self.window.card_layer.free_rect()
        view = self.window.viewer.rect()
        top = max((c.geometry().bottom() + 1 for c in self.window.card_layer.cards
                   if c.side == "top" and not c.isHidden()), default=0)
        bottom = max((view.height() - c.geometry().top() for c in self.window.card_layer.cards
                      if c.side in ("bottom", "corner") and not c.isHidden()), default=0)
        self.canvas.margins = (free.left(), top, view.width() - free.right() - 1, bottom)

    # --- vstup a výstup ----------------------------------------------------------------

    def _enter(self) -> None:
        window, dialog = self.window, self.dialog
        viewer = window.viewer
        workspace = window.workspace
        self._restore = {
            "page": window.ribbon.page, "panel": workspace.active,
            "palette": not window.palette_card.isHidden(),
            "view": not window.view_card.isHidden(), "tab": window.model_tabs.current,
            "message": window.statusBar().currentMessage(),
        }
        # akce okna zamknout (jako u náhledu prvku); vlastní akce skicáře ne
        own = set(dialog.actions())
        self._states = [(a, a.isEnabled()) for a in window.findChildren(QAction)
                        if a not in own and a is not self.escape_action]
        self.lock()
        for action in (*dialog.actions(), self.escape_action):
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            window.addAction(action)
        # plátno místo 3D: dítě prohlížeče pod kartami
        self.canvas.setParent(viewer)
        self.canvas.setMinimumSize(0, 0)
        self.canvas.setGeometry(viewer.rect())
        self.canvas.show()
        self.canvas.raise_()
        viewer.installEventFilter(self)
        # paleta Skica místo palety příkazů
        window.ribbon.select_page("sketch")
        window.palette_card.hide()
        window.view_card.hide()
        # P7.71: přepínač pohledů skicáře vpravo dole jako v rámu 2d
        views = getattr(window, "sketch_view_card", None)
        if views is None:
            views = window.sketch_view_card = window.card_layer.card(
                "Pohledy skici", "sketch_view_card", "corner")
        self.origin_action = QAction("Kolmo na skicu – počátek doprostřed", dialog)
        self.origin_action.triggered.connect(self._center_origin)
        self.views = ViewSwitcher({}, None, entries=[
            ("normal", "Kolmo na skicu", self.origin_action),
            ("fit", "Celá skica", dialog.fit_action)])
        old = views.widget()
        views.setWidget(self.views)
        if old is not None:
            old.deleteLater()
        views.show()
        card = getattr(window, "sketch_palette_card", None)
        if card is None:
            card = window.sketch_palette_card = window.card_layer.card(
                "Skica", "sketch_palette_card", "top")
        self.palette = SketchPalette(dialog)
        old = card.widget()
        card.setWidget(self.palette)
        if old is not None:
            old.deleteLater()
        card.show()
        # levá karta: strom a vazby skici
        window.model_tabs.select("features")
        holder = window.sketch_group_list
        holder.addWidget(dialog.constraint_list)
        listing = dialog.constraint_list
        listing.setFrameShape(QFrame.Shape.NoFrame)
        listing.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        listing.setStyleSheet("QListWidget { background: transparent; }")
        listing.setItemDelegate(ConstraintRowDelegate(dialog))
        listing.setToolTip("Dvojklik změní hodnotu kóty; Smazat vazbu smaže vybrané.")
        window.sketch_group.show()
        window._compact_tree()
        # pravá karta „Výběr“
        self.panel = SelectionPanel(dialog)
        window.editor_stack.addWidget(self.panel)
        window.editor_stack.setCurrentWidget(self.panel)
        workspace.show_panel("editor")
        window.card_layer.relayout()
        self.canvas.raise_()
        window.card_layer.relayout()  # karty zase nad plátno
        self.canvas.setFocus()
        self.refresh()

    def _leave(self) -> None:
        window = self.window
        window.viewer.removeEventFilter(self)
        for action in (*self.dialog.actions(), self.escape_action):
            if isValid(action):
                window.removeAction(action)
        for action, enabled in self._states:
            if isValid(action):
                action.setEnabled(enabled)
        self._states = []
        if isValid(self.canvas):
            self.canvas.hide()
            self.canvas.setParent(self.dialog if isValid(self.dialog) else None)
        if isValid(self.dialog) and isValid(self.dialog.constraint_list):
            self.dialog.constraint_list.setParent(self.dialog)
        window.sketch_group.hide()
        window.editor_stack.removeWidget(self.panel)
        self.panel.hide()
        self.panel.deleteLater()
        window.sketch_palette_card.hide()
        window.sketch_view_card.hide()
        window.palette_card.setVisible(self._restore["palette"])
        window.view_card.setVisible(self._restore["view"])
        window.ribbon.select_page(self._restore["page"])
        window.workspace.set_heading("editor")
        window._sketch_focus = None
        window._compact_tree()
        if window.feature_preview is None:
            window.workspace.show_panel(self._restore["panel"])
            window._refresh_actions()
        else:
            window.editor_stack.setCurrentWidget(window.feature_preview)
            window._editor_heading(window.feature_preview.preview.session.feature(
                window.feature_preview.preview.feature_id), window.feature_preview.kind_title)
            window._lock_preview_actions()
        window._refresh_pill_focus()
        window.statusBar().showMessage(self._restore["message"])
        window.card_layer.relayout()

    def lock(self) -> None:
        """Akce okna zůstanou během skicáře zamčené (i po obnově okna)."""
        own = set(self.dialog.actions())
        for action, _enabled in self._states:
            if isValid(action) and action not in own:
                action.setEnabled(False)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.window.viewer and event.type() == QEvent.Type.Resize:
            self.canvas.setGeometry(self.window.viewer.rect())
            QTimer.singleShot(0, self._margins)
        return False

    # --- stav --------------------------------------------------------------------------

    def refresh(self) -> None:
        """Pravá karta, nadpis a pilulka podle obrysu, výběru a nástroje."""
        if not isValid(self.dialog) or self.window._sketch_mode is not self:
            return
        dialog, window = self.dialog, self.window
        self.panel.refresh()
        window.workspace.set_heading("editor", selection_title(dialog), "Výběr")
        count = len(dialog.profile["constraints"])
        window.sketch_group_title.setText(f"Vazby skici · {count}")
        solution = dialog.solution
        if solution is None:
            focus = ("sketch", "Prázdná skica")
            message = TOOL_HELP[dialog.tool].split(". ")[0]
        elif not solution.ok:
            focus = ("error", "✕ Vazby si odporují")
            message = "Červené vazby si odporují – smaž jednu nebo dej Zpět ve skice"
        elif solution.dof == 0:
            focus = ("measure", "✓ plně určeno")
            message = "Hotovo převezme obrys do modelu"
        else:
            word = _plural(solution.dof, "rozměr", "rozměry", "rozměrů")
            focus = ("sketch", f"Zbývá určit: {solution.dof} {word}")
            message = ("Modrý obrys jde ještě táhnout myší" if dialog.tool == "select"
                       else TOOL_HELP[dialog.tool].split(". ")[0])
        window._sketch_focus = focus
        window._refresh_pill_focus()
        window.statusBar().showMessage(message)
        self.palette.cancel.setEnabled(True)
        window.card_layer.schedule()
