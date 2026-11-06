"""Plovoucí paleta příkazů nad 3D (P7.50, návrh 1a); stránky = činnosti hlavní lišty.

Dřív pás přes celou šířku okna. Rozhraní zůstává (``add_page``, ``select_page``,
``page``, ``collapsed``/``set_collapsed``, ``command_groups``, ``buttons``, ``stack``,
``tabs``), aby hledání příkazů, přehled zkratek, oblíbené i uložené rozložení fungovaly
beze změny. Záložky (``tabs``) vkládá okno do hlavní lišty, paletu do plovoucí karty.
Tlačítka používají stávající ``QAction`` okna; model se tu nemění.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QWidget,
)

from skodacad.gui.main_bar import ActivityTabs

BUTTON_WIDTH = 56  # položka palety podle návrhu: ikona 24 px nad popiskem 11 px
ICON = 24


class RibbonButton(QToolButton):
    def __init__(self, action, text=None, menu=None, parent=None):
        super().__init__(parent)
        self._label = text
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(ICON, ICON))
        self.setAutoRaise(True)
        font = QFont(self.font())
        font.setPixelSize(11)
        self.setFont(font)
        if action is not None:
            self.setDefaultAction(action)
            action.changed.connect(self._update_label)
            self._update_label()
        elif text:
            self.setText(text)
        if menu is not None:
            self.setMenu(menu)
            self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setMinimumWidth(BUTTON_WIDTH)

    def _update_label(self):
        action = self.defaultAction()
        if self._label is not None:
            self.setText(self._label)
        self.setAccessibleName(action.text().replace("&", ""))
        shortcut = action.shortcut().toString()
        self.setToolTip(action.toolTip() + (f" ({shortcut})" if shortcut else ""))


def _separator() -> QFrame:
    line = QFrame()
    line.setObjectName("palette_separator")
    line.setFrameShape(QFrame.Shape.VLine)
    line.setStyleSheet("color: palette(mid);")
    line.setContentsMargins(0, 6, 0, 6)
    return line


class Ribbon(QWidget):
    """Paleta: jedna stránka tlačítek na činnost; skupiny dělí svislá čára."""

    collapsed_changed = Signal(bool)
    page_changed = Signal(str)

    def __init__(self, quick_actions=(), parent=None, search_action=None):
        # quick_actions a search_action jsou od P7.50 v hlavní liště (MainBar).
        super().__init__(parent)
        self.setObjectName("cad_ribbon")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._keys = []
        self._pages = []
        self._rows = []
        self._collapsed = False
        self.buttons = []
        self.command_groups = []
        self.tabs = ActivityTabs()
        self.tabs.currentChanged.connect(self._page_changed)
        self.tabs.tabBarClicked.connect(lambda _index: self.set_collapsed(False))
        self.tabs.tabBarDoubleClicked.connect(
            lambda _index: self.set_collapsed(not self._collapsed))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        self.stack = QStackedWidget()
        self.stack.setObjectName("ribbon_pages")
        layout.addWidget(self.stack, 1)
        self._trailing = QHBoxLayout()
        self._trailing.setSpacing(6)
        self._trailing.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._trailing)

    def add_page(self, key, title, groups):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        for index, (label, commands) in enumerate(groups):
            self.command_groups.append(((title, label),
                                        [action for action, _text, _menu in commands
                                         if action is not None]))
            if index:
                row_layout.addSpacing(6)
                row_layout.addWidget(_separator())
                row_layout.addSpacing(6)
            for action, text, menu in commands:
                button = RibbonButton(action, text, menu, row)
                button.setAccessibleDescription(label)  # popisek skupiny pro čtečky
                row_layout.addWidget(button)
                self.buttons.append(button)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.viewport().setAutoFillBackground(False)
        row.setAutoFillBackground(False)
        scroll.setWidget(row)
        row.setMinimumWidth(row.sizeHint().width())
        scroll.setFixedHeight(row.sizeHint().height())
        self._keys.append(key)
        self._pages.append(scroll)
        self._rows.append(row)
        self.stack.addWidget(scroll)
        self.tabs.addTab(title)

    def add_trailing(self, widget: QWidget) -> None:
        """Widget za příkazy stránky (oblíbené příkazy, R4), na všech stránkách stejný.

        Oddělovač před ním je vidět jen spolu s ním (bez připnutých příkazů nic)."""
        separator = _separator()
        separator.setVisible(not widget.isHidden())
        if hasattr(widget, "visibilityChanged"):
            widget.visibilityChanged.connect(separator.setVisible)
            widget.visibilityChanged.connect(lambda _visible: self.updateGeometry())
        self._trailing.addWidget(separator)
        self._trailing.addWidget(widget)

    def preferred_width(self) -> int:
        """Šířka palety podle aktuální stránky (QStackedWidget by vzal nejširší)."""
        margins = self.layout().contentsMargins()
        index = self.stack.currentIndex()
        width = (self._rows[index].sizeHint().width()
                 if 0 <= index < len(self._rows) and not self._collapsed else 0)
        trailing = self._trailing.sizeHint().width() if any(
            self._trailing.itemAt(i).widget() is not None
            and not self._trailing.itemAt(i).widget().isHidden()
            and self._trailing.itemAt(i).widget().objectName() != "palette_separator"
            for i in range(self._trailing.count())) else 0
        return width + trailing + margins.left() + margins.right() + (6 if trailing else 0)

    def sizeHint(self):  # noqa: N802
        hint = super().sizeHint()
        return QSize(self.preferred_width(), hint.height())

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._fit_height()

    def _fit_height(self):
        """Když se stránka nevejde a ukáže se posuvník, nesmí zakrýt popisky tlačítek."""
        index = self.stack.currentIndex()
        if not 0 <= index < len(self._rows):
            return
        scroll, row = self._pages[index], self._rows[index]
        needed = row.sizeHint().height()
        if row.sizeHint().width() > scroll.viewport().width() + 1:
            needed += scroll.horizontalScrollBar().sizeHint().height()
        if scroll.height() != needed:
            scroll.setFixedHeight(needed)
            self.updateGeometry()

    def _page_changed(self, index):
        self.stack.setCurrentIndex(index)
        self.updateGeometry()
        self._fit_height()
        if 0 <= index < len(self._keys):
            self.page_changed.emit(self._keys[index])

    def select_page(self, key):
        if key in self._keys:
            self.tabs.setCurrentIndex(self._keys.index(key))

    @property
    def page(self):
        return self._keys[self.tabs.currentIndex()] if self._keys else "model"

    @property
    def collapsed(self):
        return self._collapsed

    def set_collapsed(self, collapsed):
        changed = self._collapsed != bool(collapsed)
        self._collapsed = bool(collapsed)
        self.stack.setVisible(not self._collapsed)
        self.updateGeometry()
        if changed:
            self.collapsed_changed.emit(self._collapsed)
