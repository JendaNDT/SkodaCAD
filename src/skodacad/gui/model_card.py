"""Levá karta Prvky | Parametry | Díl (P7.51, návrh hlavního okna 1a).

Sloučí dřívější sekce postranního panelu („Díl a materiál“, „Parametry dílu“, „Strom
prvků“, „Vlastnosti dílu“) do segmentového přepínače se třemi stránkami. Data řádků
stromu (text se stavem, id, sloupec počtu těles) zůstávají stejná – čtou je testy,
hledání ve stromu i čtečky obrazovky. Mění se jen kreslení: ikona typu prvku vlevo,
stav (a počet těles) vpravo, řádek 26 px, vybraný řádek ``--accentbg`` a tučně.
"""

from PySide6.QtCore import QObject, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from skodacad.gui import ui_theme
from skodacad.gui.main_bar import SegmentTabs

TABS = (("features", "Prvky"), ("parameters", "Parametry"), ("part", "Díl"))
ROW_HEIGHT = 26
STATUS_ROLE = Qt.ItemDataRole.UserRole + 41  # "ok" / "error" / "skipped" / "pending"
# Klíč nastavené ikony řádku („druh|barva“): QIcon nejde porovnat, takže by každé nové
# nastavení hlásilo změnu a sloupec s ResizeToContents by přeměřil všechny řádky (P8.5).
ICON_ROLE = Qt.ItemDataRole.UserRole + 42
# Řádek náhledu nového nebo upravovaného prvku (P7.54, rám 3a): rámeček 1 px a kurzíva.
PREVIEW_ROLE = Qt.ItemDataRole.UserRole + 44
PREVIEW_COLOR = "#4782d1"  # duch náhledu ve 3D (viewer.py 0,28 / 0,51 / 0,82)
# Krátký název a údaj vpravo podle rámu 2a („Upínání · M6 ×4“, P7.59). Text položky
# (celý popis „✓  Díra „Upínání“ – M6 …“) a počet těles ve sloupci 1 zůstávají – testy,
# filtr, bublina a přístupnost; delegát jen kreslí kratší podobu.
NAME_ROLE = Qt.ItemDataRole.UserRole + 45
SUMMARY_ROLE = Qt.ItemDataRole.UserRole + 46
GLYPHS = {"ok": "✓", "error": "✕", "skipped": "·", "pending": "⏳"}
# Ikona Duo podle typu prvku (stejné druhy jako v paletě příkazů).
FEATURE_ICONS = {"sketch": "sketch", "extrude": "extrude", "revolve": "revolve",
                 "sweep": "sweep", "loft": "loft", "guided_loft": "loft", "hole": "hole",
                 "fillet": "fillet", "variable_fillet": "fillet", "chamfer": "chamfer",
                 "shell": "shell", "pattern": "pattern", "mirror": "mirror",
                 "move_face": "edit", "face_diameter": "edit", "step_import": "open"}


def count_text(count: int) -> str:
    """„1 prvek“, „3 prvky“, „6 prvků“ (patička stromu)."""
    if count == 1:
        return "1 prvek"
    return f"{count} prvky" if 2 <= count <= 4 else f"{count} prvků"


def holes_text(count: int) -> str:
    """„1 díra“, „4 díry“, „6 děr“."""
    if count == 1:
        return "1 díra"
    return f"{count} díry" if 2 <= count <= 4 else f"{count} děr"


def selection_summary(feature: dict, summary: str) -> str:
    """Údaj pilulky u prvku vybraného ve stromu (rám 2a): u díry „4 díry M6“, jinak
    krátký údaj řádku stromu (``summary`` = ``features.tree_summary``)."""
    if feature.get("type") == "hole" and isinstance(feature.get("size"), str):
        count = len(feature.get("positions") or [None])
        return f"{holes_text(count)} {feature['size']}"
    return summary


class ModelTabs(QWidget):
    """Segment Prvky | Parametry | Díl nad stránkami levé karty."""

    changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 0)
        layout.setSpacing(8)
        self.tabs = SegmentTabs("model_tabs", "Levá karta", background="card", expanding=True)
        layout.addWidget(self.tabs)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self._keys: list[str] = []
        self.tabs.currentChanged.connect(self._changed)

    def add(self, key: str, title: str, page: QWidget) -> None:
        self._keys.append(key)
        self.stack.addWidget(page)
        self.tabs.addTab(title)

    def select(self, key: str) -> None:
        if key in self._keys:
            self.tabs.setCurrentIndex(self._keys.index(key))

    @property
    def current(self) -> str:
        index = self.tabs.currentIndex()
        return self._keys[index] if 0 <= index < len(self._keys) else self._keys[0]

    def _changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if 0 <= index < len(self._keys):
            self.changed.emit(self._keys[index])


class TabSection(QObject):
    """Náhrada sekce „Parametry dílu“: rozbalená = otevřená záložka Parametry.

    Rozhraní jako ``workspace.Section`` (``expanded``, ``set_expanded``, ``toggled``),
    takže Ctrl+Shift+F, uložené rozložení a testy fungují beze změny."""

    toggled = Signal(bool)

    def __init__(self, tabs: ModelTabs, key: str, fallback: str = "features") -> None:
        super().__init__(tabs)
        self._tabs, self._key, self._fallback = tabs, key, fallback
        self._last = self.expanded
        tabs.changed.connect(self._changed)

    @property
    def expanded(self) -> bool:
        return self._tabs.current == self._key

    def set_expanded(self, expanded: bool) -> None:
        if expanded:
            self._tabs.select(self._key)
        elif self.expanded:
            self._tabs.select(self._fallback)

    def _changed(self, _key: str) -> None:
        if self.expanded != self._last:
            self._last = self.expanded
            self.toggled.emit(self._last)


class FeatureRowDelegate(QStyledItemDelegate):
    """Kresba řádku stromu podle návrhu; data položky se nemění."""

    def sizeHint(self, option, index):  # noqa: N802
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(), ROW_HEIGHT))

    def initStyleOption(self, option, index):  # noqa: N802
        super().initStyleOption(option, index)
        status = index.siblingAtColumn(0).data(STATUS_ROLE) or "pending"
        t = ui_theme.tokens()
        first = index.siblingAtColumn(0)
        if index.column() == 0:
            glyph = GLYPHS.get(status, "")
            text = option.text
            if glyph and text.startswith(glyph):
                option.text = text[len(glyph):].lstrip()  # stav se kreslí vpravo
            if first.data(NAME_ROLE):
                option.text = first.data(NAME_ROLE)  # krátký název (rám 2a)
            if status != "error":  # název běžnou barvou, chyba zůstane červená
                option.palette.setColor(QPalette.ColorRole.Text, ui_theme.color(t["fg"]))
        else:
            glyph = GLYPHS.get(status, "")
            if first.data(NAME_ROLE) is not None:  # údaj prvku místo počtu těles (v bublině)
                option.text = first.data(SUMMARY_ROLE) or ""
                if status == "ok":  # rám 2a: údaj a ✓ šedě, chyba dál barvou stavu
                    option.palette.setColor(QPalette.ColorRole.Text, ui_theme.color(t["fg3"]))
            option.text = f"{option.text}  {glyph}".strip() if option.text else glyph
            option.displayAlignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            font = QFont(option.font)
            font.setPixelSize(11)
            option.font = font
        if index.siblingAtColumn(0).data(PREVIEW_ROLE):
            font = QFont(option.font)
            font.setItalic(index.column() == 0)
            option.font = font
            if index.column() == 1:
                option.text = "náhled"
            option.palette.setColor(QPalette.ColorRole.Text, QColor(PREVIEW_COLOR))
        if option.state & QStyle.StateFlag.State_Selected:
            font = QFont(option.font)
            font.setWeight(QFont.Weight.DemiBold)
            option.font = font
            option.palette.setColor(QPalette.ColorRole.Highlight,
                                    ui_theme.opaque(t["accentbg"], ui_theme.card_color()))
            text = option.palette.color(QPalette.ColorRole.Text)
            option.palette.setColor(QPalette.ColorRole.HighlightedText, text)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if not index.siblingAtColumn(0).data(PREVIEW_ROLE):
            return
        view = self.parent()
        row = view.visualRect(index.siblingAtColumn(0)).united(
            view.visualRect(index.siblingAtColumn(1)))
        painter.save()
        painter.setClipRect(option.rect)  # každá buňka kreslí svou část rámečku řádku
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(PREVIEW_COLOR))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(row).adjusted(1.5, 1.5, -1.5, -1.5), 6, 6)
        painter.restore()


# Skupina „NDT studie“ v levé kartě (P7.55, rám 2c): stav vpravo, barva podle stavu.
STUDY_STATES = {"ok": ("✓ platná", "ok"), "stale": ("⚠ zastaralá", "warn"),
                "incomplete": ("⚠ neúplná", "warn"), "broken": ("✕ neplatná vazba", "err"),
                "pending": ("⏳", "fg3")}


class StudyRowDelegate(QStyledItemDelegate):
    """Řádek studie: ikona metody, název, vpravo stav 11 px (⚠ neúplná / ✓ platná)."""

    def sizeHint(self, option, index):  # noqa: N802
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(), ROW_HEIGHT))

    def paint(self, painter, option, index):
        state = index.data(STATUS_ROLE) or "pending"
        text, token = STUDY_STATES.get(state, ("", "fg3"))
        t = ui_theme.tokens()
        font = QFont(option.font)
        font.setPixelSize(11)
        width = QFontMetrics(font).horizontalAdvance(text) + 12
        opt = type(option)(option)
        self.initStyleOption(opt, index)
        if opt.state & QStyle.StateFlag.State_Selected:
            bold = QFont(opt.font)
            bold.setWeight(QFont.Weight.DemiBold)
            opt.font = bold
            opt.palette.setColor(QPalette.ColorRole.Highlight,
                                 ui_theme.opaque(t["accentbg"], ui_theme.card_color()))
            opt.palette.setColor(QPalette.ColorRole.HighlightedText, ui_theme.color(t["fg"]))
        opt.palette.setColor(QPalette.ColorRole.Text, ui_theme.color(t["fg"]))
        opt.rect = option.rect.adjusted(0, 0, -width, 0)
        style = opt.widget.style() if opt.widget is not None else None
        if style is not None and opt.state & QStyle.StateFlag.State_Selected:
            full = type(option)(opt)
            full.rect = option.rect
            full.text = ""
            full.icon = type(opt.icon)()
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, full, painter, opt.widget)
        super().paint(painter, opt, index)
        painter.save()
        painter.setFont(font)
        painter.setPen(ui_theme.color(t.get(token, t["fg3"])))
        painter.drawText(option.rect.adjusted(0, 0, -6, 0),
                         int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), text)
        painter.restore()
