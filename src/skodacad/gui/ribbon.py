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
    QMenu,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QWidget,
)

from skodacad.gui.main_bar import ActivityTabs

BUTTON_WIDTH = 56  # položka palety podle návrhu: ikona 24 px nad popiskem 11 px
COMPACT_WIDTH = 34  # úzké okno: jen ikona, název v bublině (P7.64)
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
            self.setToolTip(text)  # i jen s ikonou musí být poznat, co tlačítko dělá
            self.setAccessibleName(text)
        if menu is not None:
            # Akce, která sama je nabídkou (menuAction), už nabídku nese; druhé setMenu
            # by v Qt zrušilo akci i nabídku a tlačítko by nic neotevřelo (P7.64).
            if action is None or action.menu() is not menu:
                self.setMenu(menu)
            self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setMinimumWidth(BUTTON_WIDTH)

    def set_compact(self, compact: bool) -> None:
        """Úzké okno (P7.64): jen ikona, název zůstává v bublině a pro čtečky.

        Tlačítko bez ikony si popisek nechá – jinak by z něj nic nezbylo."""
        compact = compact and not self.icon().isNull()
        style = (Qt.ToolButtonStyle.ToolButtonIconOnly if compact
                 else Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        if self.toolButtonStyle() != style:
            self.setToolButtonStyle(style)
            self.setMinimumWidth(COMPACT_WIDTH if compact else BUTTON_WIDTH)

    def _update_label(self):
        action = self.defaultAction()
        if self._label is not None:
            self.setText(self._label)
        # Akce bez textu (nabídka „Další prvky“) dostane název z popisku tlačítka – jen
        # s ikonou (P7.64) by jinak nebylo poznat, co tlačítko dělá.
        name = action.text().replace("&", "") or (self._label or "")
        self.setAccessibleName(name)
        shortcut = action.shortcut().toString()
        self.setToolTip((action.toolTip() or name) + (f" ({shortcut})" if shortcut else ""))


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
        self._groups = []  # po stránkách: [(oddělovač nebo None, [tlačítka])]
        self._more = []  # po stránkách: tlačítko „Další“ s příkazy, které se nevešly
        self._fitted = None  # (stránka, místo, sbalení, šířka oblíbených) poslední úpravy
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
        page_groups = []
        for index, (label, commands) in enumerate(groups):
            self.command_groups.append(((title, label),
                                        [action for action, _text, _menu in commands
                                         if action is not None]))
            separator = None
            if index:
                separator = _separator()
                row_layout.addSpacing(6)
                row_layout.addWidget(separator)
                row_layout.addSpacing(6)
            members = []
            for action, text, menu in commands:
                button = RibbonButton(action, text, menu, row)
                button.setAccessibleDescription(label)  # popisek skupiny pro čtečky
                row_layout.addWidget(button)
                self.buttons.append(button)
                members.append(button)
            page_groups.append((separator, members))
        more = QToolButton(row)  # P7.64: příkazy, které se do úzkého okna nevešly
        more.setObjectName("palette_more")
        more.setText("»")
        more.setAutoRaise(True)
        more.setToolTip("Další příkazy – nevešly se do úzkého okna")
        more.setAccessibleName("Další příkazy")
        more.setMenu(QMenu(more))
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more.setMinimumWidth(COMPACT_WIDTH)
        more.hide()
        row_layout.addWidget(more)
        self._groups.append(page_groups)
        self._more.append(more)
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

    def fit_width(self, room: int) -> None:
        """Responzivní paleta (P7.64): plné popisky → jen ikony → zbytek v nabídce „»“.

        Volá ji rozmístění karet s místem, které paleta má; vodorovný posuvník se tak
        neukáže. Skrytá tlačítka zůstávají v ``buttons`` (hledání, oblíbené, zkratky)."""
        index = self.stack.currentIndex()
        if not 0 <= index < len(self._rows):
            return
        key = (index, room, self._collapsed, self._trailing.sizeHint().width())
        if key == self._fitted:
            return
        self._fitted = key
        groups, more, row = self._groups[index], self._more[index], self._rows[index]
        buttons = [button for _separator, members in groups for button in members]
        for button in buttons:
            button.show()
            button.set_compact(False)
        more.hide()
        hidden: list[RibbonButton] = []

        def width() -> int:
            for separator, members in groups:
                if separator is not None:
                    separator.setVisible(any(not b.isHidden() for b in members))
            row.layout().invalidate()
            row.setMinimumWidth(row.sizeHint().width())
            return self.preferred_width()

        if width() > room and not self._collapsed:
            for button in buttons:
                button.set_compact(True)
            if width() > room:
                more.show()
                for button in reversed(buttons[1:]):
                    if width() <= room:
                        break
                    button.hide()
                    hidden.insert(0, button)
        menu = more.menu()
        menu.clear()
        for button in hidden:
            action = button.defaultAction()
            source = button.menu() or (action.menu() if action is not None else None)
            if source is not None:  # vlastní podnabídka se stejnými akcemi
                menu.addMenu(button.text()).addActions(source.actions())
            elif action is not None:
                menu.addAction(button.defaultAction())
        width()
        self.updateGeometry()
        self._fit_height()

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
        if self.stack.maximumHeight() != needed:  # jinak výška nejvyšší stránky (P7.64)
            self.stack.setFixedHeight(needed)
            self.updateGeometry()

    def _page_changed(self, index):
        self._fitted = None
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
        self._fitted = None
        self.stack.setVisible(not self._collapsed)
        self.updateGeometry()
        if changed:
            self.collapsed_changed.emit(self._collapsed)
