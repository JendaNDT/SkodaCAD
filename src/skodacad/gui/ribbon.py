"""A task ribbon using the application's existing QAction instances."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class RibbonButton(QToolButton):
    def __init__(self, action, text=None, menu=None, parent=None):
        super().__init__(parent)
        self._label = text
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(26, 26))
        self.setAutoRaise(True)
        if action is not None:
            self.setDefaultAction(action)
            action.changed.connect(self._update_label)
            self._update_label()
        elif text:
            self.setText(text)
        if menu is not None:
            self.setMenu(menu)
            self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setMinimumWidth(52)

    def _update_label(self):
        action = self.defaultAction()
        if self._label is not None:
            self.setText(self._label)
        self.setAccessibleName(action.text().replace("&", ""))
        shortcut = action.shortcut().toString()
        self.setToolTip(action.toolTip() + (f" ({shortcut})" if shortcut else ""))


class Ribbon(QWidget):
    collapsed_changed = Signal(bool)
    page_changed = Signal(str)

    def __init__(self, quick_actions, parent=None):
        super().__init__(parent)
        self.setObjectName("cad_ribbon")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._keys = []
        self._pages = []
        self._collapsed = False
        self.buttons = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setSpacing(3)
        for action in quick_actions:
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setIconSize(QSize(16, 16))
            button.setAccessibleName(action.text())
            header.addWidget(button)
        self.tabs = QTabBar()
        self.tabs.setObjectName("ribbon_tabs")
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setAccessibleName("Činnosti")
        self.tabs.currentChanged.connect(self._page_changed)
        self.tabs.tabBarClicked.connect(lambda _index: self.set_collapsed(False))
        self.tabs.tabBarDoubleClicked.connect(
            lambda _index: self.set_collapsed(not self._collapsed))
        header.addWidget(self.tabs, 1)
        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("ribbon_collapse")
        self.collapse_button.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        header.addWidget(self.collapse_button)
        layout.addLayout(header)
        self.stack = QStackedWidget()
        self.stack.setObjectName("ribbon_pages")
        layout.addWidget(self.stack)
        self._update_collapse_button()

    def add_page(self, key, title, groups):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 3, 4, 3)
        row_layout.setSpacing(10)
        for label, commands in groups:
            group = QWidget()
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(2)
            tools = QHBoxLayout()
            tools.setSpacing(2)
            for action, text, menu in commands:
                button = RibbonButton(action, text, menu, group)
                tools.addWidget(button)
                self.buttons.append(button)
            group_layout.addLayout(tools)
            caption = QLabel(label)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setStyleSheet("color: palette(text);")
            group_layout.addWidget(caption)
            row_layout.addWidget(group)
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.VLine)
            separator.setStyleSheet("color: palette(mid);")
            row_layout.addWidget(separator)
        row_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(row)
        row.setMinimumWidth(row.sizeHint().width())
        scroll.setFixedHeight(row.sizeHint().height() + 16)
        self._keys.append(key)
        self._pages.append(scroll)
        self.stack.addWidget(scroll)
        self.tabs.addTab(title)

    def _page_changed(self, index):
        self.stack.setCurrentIndex(index)
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
        self._update_collapse_button()
        self.updateGeometry()
        if changed:
            self.collapsed_changed.emit(self._collapsed)

    def _update_collapse_button(self):
        self.collapse_button.setArrowType(Qt.ArrowType.DownArrow if self._collapsed
                                          else Qt.ArrowType.UpArrow)
        text = "Rozbalit pás nástrojů" if self._collapsed else "Sbalit pás nástrojů"
        self.collapse_button.setToolTip(text)
        self.collapse_button.setAccessibleName(text)
