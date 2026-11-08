"""Hlavní lišta okna podle návrhu 1a (P7.50).

Výška 52 px: vlevo název dílu (13/700) s podtitulkem (soubor · materiál · upraveno),
uprostřed segmentový přepínač činností (záložky ``Ribbon.tabs``), vpravo Zpět/Znovu
a pole „Najít příkaz…“ se zkratkou. Lišta jen spouští stávající ``QAction``;
model mění výhradně akce okna přes ``ModelSession``.
"""

import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QKeySequence, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from skodacad.gui import ui_theme
from skodacad.gui.cad_icons import icon as cad_icon

HEIGHT = 52
SEARCH_SIZE = QSize(220, 26)
SEARCH_WIDTHS = {"full": 220, "short": 120, "icon": 30}  # úzké okno (P7.65)


def _pixel_font(widget: QWidget, size: int, weight=QFont.Weight.Normal) -> QFont:
    font = QFont(widget.font())
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def shortcut_text(action) -> str:
    """Zkratka tak, jak ji píše systém (⌘⇧P na Macu, Ctrl+Shift+P jinde)."""
    return action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)


class SearchField(QPushButton):
    """Tlačítko vzhledu pole: lupa, „Najít příkaz…“ a vpravo zkratka. Klik spustí akci."""

    def __init__(self, action, parent=None) -> None:
        super().__init__(parent)
        self.action = action
        self.setObjectName("command_search_field")
        self.setFixedSize(SEARCH_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(action.text().replace("…", ""))
        self.setToolTip(f"{action.text()} ({shortcut_text(action)})")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        self.glyph = QLabel()
        self.text_label = QLabel(action.text())
        self.text_label.setFont(_pixel_font(self, 12))
        self.key_label = QLabel(shortcut_text(action))
        self.key_label.setFont(_pixel_font(self, 11))
        for label in (self.glyph, self.text_label, self.key_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(label)
        layout.insertStretch(2, 1)
        self.clicked.connect(action.trigger)
        self.mode = "full"
        self.refresh_style()

    def set_mode(self, mode: str) -> None:
        """Responzivní pole (P7.65): ``full`` s textem a zkratkou, ``short`` jen „Najít…“,
        ``icon`` jen lupa. Bublina i název pro čtečky zůstávají celé."""
        if mode == self.mode:
            return
        self.mode = mode
        self.setFixedWidth(SEARCH_WIDTHS[mode])
        self.text_label.setText(self.action.text() if mode == "full" else "Najít…")
        self.text_label.setVisible(mode != "icon")
        self.key_label.setVisible(mode == "full")

    def refresh_style(self) -> None:
        t = ui_theme.tokens()
        card = ui_theme.card_color()
        field = ui_theme.opaque(t["sep"], ui_theme.color(t["tb"])).name()
        self.setStyleSheet(
            f"QPushButton#command_search_field {{ background: {field}; border: none;"
            f" border-radius: 7px; }}"
            f"QPushButton#command_search_field:focus {{ border: 2px solid"
            f" {ui_theme.opaque(t['accentbg'], card).name()}; }}"
            f"QLabel {{ color: {t['fg3']}; background: transparent; }}")
        self.glyph.setPixmap(cad_icon("search", t["fg3"]).pixmap(14, 14))


class SegmentTabs(QTabBar):
    """Segmentový přepínač podle návrhu 1a: podklad ``--sep``, aktivní položka ``--ctl``."""

    def __init__(self, name: str, accessible: str, background: str = "tb",
                 expanding: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self._background = background  # token, na kterém přepínač leží
        self.setExpanding(expanding)
        self.setDrawBase(False)
        self.setDocumentMode(True)
        self.setAccessibleName(accessible)
        self.setFont(_pixel_font(self, 13))
        self.refresh_style()

    def refresh_style(self) -> None:
        t = ui_theme.tokens()
        under = (ui_theme.card_color() if self._background == "card"
                 else ui_theme.color(t[self._background]))
        track = ui_theme.opaque(t["sep"], under).name()
        name = self.objectName()
        self.setStyleSheet(
            f"QTabBar#{name} {{ background: {track}; border-radius: 7px; }}"
            f"QTabBar#{name}::tab {{ background: transparent; color: {t['fg']};"
            f" border: none; padding: 3px 12px; margin: 2px 0px; border-radius: 5px; }}"
            f"QTabBar#{name}::tab:first {{ margin-left: 2px; }}"
            f"QTabBar#{name}::tab:last {{ margin-right: 2px; }}"
            f"QTabBar#{name}::tab:selected {{ background: {t['ctl']}; font-weight: 500;"
            f" border: 1px solid {ui_theme.opaque(t['sep'], ui_theme.color(t['ctl'])).name()};"
            f" }}")


class ActivityTabs(SegmentTabs):
    """Segmentový přepínač činností (nahrazuje záložky pásu, P7.50)."""

    def __init__(self, parent=None) -> None:
        super().__init__("ribbon_tabs", "Činnosti", parent=parent)


class MainBar(QWidget):
    """Lišta 52 px nad 3D pohledem (na Macu sjednocená s titulkem okna)."""

    def __init__(self, tabs: QTabBar, undo_action, redo_action, search_action,
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("main_bar")
        self.setFixedHeight(HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        # Na Macu je vlevo semafor okna (sjednocený titulek), proto větší odstup.
        layout.setContentsMargins(84 if sys.platform == "darwin" else 20, 0, 16, 0)
        layout.setSpacing(18)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel("ŠkodaCAD")
        self.title_label.setObjectName("main_bar_title")
        self.title_label.setFont(_pixel_font(self, 13, QFont.Weight.Bold))
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("main_bar_subtitle")
        self.subtitle_label.setFont(_pixel_font(self, 11))
        names.addStretch(1)
        names.addWidget(self.title_label)
        names.addWidget(self.subtitle_label)
        names.addStretch(1)
        title = QWidget()
        title.setLayout(names)
        title.setMinimumWidth(150)
        title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addWidget(title, 1)
        self.tabs = tabs
        tabs.setParent(self)
        layout.addWidget(tabs, 0, Qt.AlignmentFlag.AlignVCenter)
        right = QHBoxLayout()
        right.setSpacing(4)
        right.addStretch(1)
        self.history_buttons = []
        for action in (undo_action, redo_action):
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setIconSize(QSize(20, 20))
            button.setAutoRaise(True)
            button.setAccessibleName(action.text())
            right.addWidget(button)
            self.history_buttons.append(button)
        right.addSpacing(10)
        self.search = SearchField(search_action)
        right.addWidget(self.search)
        holder = QWidget()
        holder.setLayout(right)
        layout.addWidget(holder, 1)
        self._title = title
        self._right = right

    def needed_width(self, mode: str) -> int:
        """Šířka lišty, při které se záložky vejdou celé a hledání má podobu ``mode``."""
        layout = self.layout()
        margins = layout.contentsMargins()
        history = sum(b.sizeHint().width() for b in self.history_buttons)
        inner = self._right.contentsMargins()
        right = (history + self._right.spacing() * len(self.history_buttons) + 10
                 + inner.left() + inner.right())
        return (margins.left() + margins.right() + 2 * layout.spacing()
                + self._title.minimumWidth() + self.tabs.sizeHint().width()
                + right + SEARCH_WIDTHS[mode] + 4)  # 4 px rezerva na zaokrouhlení

    def resizeEvent(self, event) -> None:  # noqa: N802
        # P7.65: v úzkém okně ustoupí nejdřív hledání (bez zkratky, pak jen lupa), aby
        # záložky činností zůstaly celé a bez šipek pro posouvání.
        self.fit(event.size().width())
        super().resizeEvent(event)

    def fit(self, width: int) -> None:
        """Podoba hledání pro lištu široké ``width`` px (nejširší, při které se záložky
        vejdou celé)."""
        mode = next((m for m in ("full", "short") if self.needed_width(m) <= width), "icon")
        self.search.set_mode(mode)

    def set_document(self, name: str, subtitle: str) -> None:
        self.title_label.setText(name)
        self.subtitle_label.setText(subtitle)
        self.title_label.setToolTip(f"{name}\n{subtitle}")

    def refresh_style(self) -> None:
        t = ui_theme.tokens()
        self.subtitle_label.setStyleSheet(f"color: {t['fg3']};")
        self.title_label.setStyleSheet(f"color: {t['fg']};")
        self.tabs.refresh_style() if hasattr(self.tabs, "refresh_style") else None
        self.search.refresh_style()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        t = ui_theme.tokens()
        painter.fillRect(self.rect(), ui_theme.color(t["tb"]))
        line = ui_theme.opaque(t["sep2"], ui_theme.color(t["tb"]))
        painter.setPen(QPen(line, 1))
        painter.drawLine(self.rect().bottomLeft(), self.rect().bottomRight())

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (event.Type.PaletteChange,) and self.palette().color(
                QPalette.ColorRole.Window).isValid():
            self.refresh_style()
