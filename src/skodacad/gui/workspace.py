"""The chosen 'model tree + right editor' workspace, with one visible tool panel."""

import logging

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from skodacad.gui.ui_colors import secondary_color
from skodacad.gui.window_state import PANELS, fit_geometry, load_state, save_state

log = logging.getLogger(__name__)


class Section(QWidget):
    toggled = Signal(bool)

    def __init__(self, title, content, expanded=False):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.button = QToolButton()
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setChecked(expanded)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setAutoRaise(True)
        self.content = content
        layout.addWidget(self.button)
        layout.addWidget(content)
        self.button.toggled.connect(self.set_expanded)
        self.set_expanded(expanded)

    def set_expanded(self, expanded):
        if self.button.isChecked() != expanded:
            self.button.setChecked(expanded)
            return  # toggled calls us once with the updated state
        self.button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)
        self.toggled.emit(expanded)

    @property
    def expanded(self):
        return self.button.isChecked()


class Workspace:
    def __init__(self, window, path=None):
        self.window = window
        self.path = path
        self.state = load_state(path)
        self.docks = dict(zip(PANELS, (window.editor_dock, window.measure_dock, window.map_dock,
                         window.section_dock, window.ndt_dock, window.audit_dock,
                         window.design_dock, window.assistant_dock), strict=True))
        self.active = None
        self.last_panel = "editor"
        self._changing = False
        self._restored = False
        self._palette_key = None
        self.panels_menu = QMenu("Panely", window)
        self.actions = {}
        for key, dock in self.docks.items():
            action = QAction(dock.windowTitle(), window)
            action.setObjectName(f"panel_{key}")
            action.setCheckable(True)
            action.triggered.connect(lambda checked, k=key: self.show_panel(k) if checked
                                     else self.close_panel())
            self.actions[key] = action
            self.panels_menu.addAction(action)
            dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
            dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
            dock.setMinimumWidth(300)
            dock.visibilityChanged.connect(lambda visible, k=key: self._visibility(k, visible))
            header = QWidget()
            row = QHBoxLayout(header)
            row.setContentsMargins(6, 3, 6, 3)
            title = QToolButton()
            title.setText(dock.windowTitle())
            title.setAutoRaise(True)
            title.setMenu(self.panels_menu)
            title.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            title.setAccessibleName("Zvolit pravý panel")
            row.addWidget(title)
            row.addStretch(1)
            close = QToolButton()
            close.setText("×")
            close.setAutoRaise(True)
            close.setAccessibleName("Zavřít pravý panel")
            close.setToolTip("Zavřít panel; znovu jej otevřeš přes Zobrazení → Panely")
            close.clicked.connect(self.close_panel)
            row.addWidget(close)
            dock.setTitleBarWidget(header)
        self.actions["editor"].setShortcut("F4")
        self.model_action = window._action("Strom modelu", self._toggle_model, "F9")
        self.model_action.setCheckable(True)
        self.model_action.setChecked(True)
        window.model_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        window.model_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        window.model_dock.setMinimumWidth(230)
        window.model_dock.visibilityChanged.connect(self._model_visibility)
        self.reset_action = window._action("Obnovit rozložení", self.reset)
        self.collapse_action = window._action("Sbalit pás nástrojů", self.toggle_ribbon,
                                              "Ctrl+F1")
        self.collapse_action.setCheckable(True)
        self.appearance_menu = QMenu("Vzhled", window)
        self.appearance_group = QActionGroup(window)
        self.appearance_actions = {}
        for key, label in (("system", "Podle systému"), ("light", "Světlý"), ("dark", "Tmavý")):
            action = self.appearance_menu.addAction(label)
            action.setCheckable(True)
            self.appearance_group.addAction(action)
            action.triggered.connect(lambda _checked=False, k=key: self.set_appearance(k))
            self.appearance_actions[key] = action
        if QApplication.instance().property("skodacadAppearance") is None:
            self.set_appearance(self.state.get("appearance", "system"))
        self.show_panel(self.state.get("panel", "editor"))

    def _visibility(self, key, visible):
        if self._changing or not self.window.isVisible():
            return
        if visible:
            self.show_panel(key)
        elif self.docks[key].isHidden() and self.active == key:
            self.active = None
            self.actions[key].setChecked(False)

    def show_panel(self, key):
        if key is None:
            self.close_panel()
            return
        if key not in self.docks:
            raise ValueError("Neznámý panel okna.")
        self._changing = True
        try:
            for name, dock in self.docks.items():
                dock.setVisible(name == key)
                self.actions[name].setChecked(name == key)
            self.docks[key].raise_()
            self.active = self.last_panel = key
        finally:
            self._changing = False

    def close_panel(self):
        self._changing = True
        try:
            for key, dock in self.docks.items():
                dock.hide()
                self.actions[key].setChecked(False)
            self.active = None
        finally:
            self._changing = False

    def _toggle_model(self):
        self.window.model_dock.setVisible(self.model_action.isChecked())

    def _model_visibility(self, visible):
        if self.window.isVisible():
            self.model_action.setChecked(not self.window.model_dock.isHidden())

    def toggle_ribbon(self):
        self.window.ribbon.set_collapsed(not self.window.ribbon.collapsed)

    def set_appearance(self, key):
        if key not in self.appearance_actions:
            return
        app = QApplication.instance()
        app.setProperty("skodacadAppearance", key)
        if key == "system":
            app.styleHints().unsetColorScheme()
        else:
            app.styleHints().setColorScheme(Qt.ColorScheme.Light if key == "light"
                                            else Qt.ColorScheme.Dark)
        self.appearance_actions[key].setChecked(True)

    def refresh_palette(self):
        palette = QApplication.palette()
        key = (palette.color(QPalette.ColorRole.Window).rgba(),
               palette.color(QPalette.ColorRole.WindowText).rgba())
        if self._palette_key == key:
            return
        self._palette_key = key
        color = secondary_color(palette).name()
        self.window.setStyleSheet(f"QLabel[secondaryText=\"true\"] {{ color: {color}; }}")
        appearance = QApplication.instance().property("skodacadAppearance") or "system"
        self.appearance_actions[appearance].setChecked(True)
        self.window._refresh_ui_icons()
        self.window._refresh_tree()

    def reset(self):
        window = self.window
        window.ribbon.select_page("model")
        window.ribbon.set_collapsed(False)
        self.show_panel("editor")
        compact = window.width() < 1180
        window.model_dock.setVisible(not compact)
        self.model_action.setChecked(not compact)
        for key, section in window.sidebar_sections.items():
            section.set_expanded(key == "parameters")
        window.resizeDocks([window.model_dock, window.editor_dock], [250, 350],
                           Qt.Orientation.Horizontal)
        if compact:
            window.statusBar().showMessage("Menší okno: strom otevřeš tlačítkem Model nebo F9.",
                                           10000)

    def restore(self):
        if self._restored:
            return
        self._restored = True
        window = self.window
        if not self.state:
            self.reset()
            return
        geometry = self.state.get("geometry")
        if geometry:
            client, frame = window.geometry(), window.frameGeometry()
            margins = (client.left() - frame.left(), client.top() - frame.top(),
                       frame.right() - client.right(), frame.bottom() - client.bottom())
            screens = [s.availableGeometry().adjusted(margins[0], margins[1],
                       -margins[2], -margins[3]) for s in QApplication.screens()]
            window.setGeometry(fit_geometry(QRect(*geometry), screens))
        window.model_dock.setVisible(self.state.get("model_visible", True))
        self.model_action.setChecked(self.state.get("model_visible", True))
        self.show_panel(self.state.get("panel", "editor"))
        for key, section in window.sidebar_sections.items():
            section.set_expanded(self.state.get("sections", {}).get(key, key == "parameters"))
        dock = self.docks[self.active or self.last_panel]
        window.resizeDocks([window.model_dock, dock],
                           [self.state.get("model_width", 250),
                            self.state.get("editor_width", 350)], Qt.Orientation.Horizontal)
        window.ribbon.select_page(self.state.get("page", "model"))
        window.ribbon.set_collapsed(self.state.get("ribbon_collapsed", False))
        if self.state.get("maximized"):
            window.showMaximized()

    def save(self):
        window = self.window
        geometry = window.normalGeometry() if window.isMaximized() else window.geometry()
        state = {"geometry": [geometry.x(), geometry.y(), geometry.width(), geometry.height()],
                 "maximized": window.isMaximized(),
                 "model_visible": not window.model_dock.isHidden(),
                 "model_width": window.model_dock.width(),
                 "editor_width": self.docks[self.active or self.last_panel].width(),
                 "panel": self.active, "page": window.ribbon.page,
                 "ribbon_collapsed": window.ribbon.collapsed,
                 "appearance": QApplication.instance().property("skodacadAppearance") or "system",
                 "sections": {key: section.expanded
                              for key, section in window.sidebar_sections.items()}}
        try:
            save_state(self.path, state)
        except (OSError, ValueError):
            log.warning("Rozložení okna se nepodařilo uložit.", exc_info=True)
