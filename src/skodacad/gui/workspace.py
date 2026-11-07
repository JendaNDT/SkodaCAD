"""Strom modelu a jeden pravý panel – od P7.49 jako plovoucí karty nad 3D (návrh 1a)."""

import logging

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from skodacad.gui import ui_theme
from skodacad.gui.ui_colors import secondary_color
from skodacad.gui.window_state import PANELS, fit_geometry, load_state, save_state

log = logging.getLogger(__name__)


class Section(QWidget):
    """Sbalitelná sekce podle návrhu 1a (P7.52): linka nahoře, ▶/▼, titulek 600, počet."""

    toggled = Signal(bool)

    def __init__(self, title, content, expanded=False):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: palette(mid);")
        layout.addWidget(line)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.button = QToolButton()
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setChecked(expanded)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setAutoRaise(True)
        self.button.setStyleSheet("QToolButton { border: none; background: transparent;"
                                  " font-weight: 600; padding: 3px 0px; }")
        self.count_label = QLabel()
        self.count_label.setProperty("secondaryText", True)
        self.count_label.hide()
        row.addWidget(self.button)
        row.addStretch(1)  # počet (nebo zkratka) vpravo v řádku sekce
        row.addWidget(self.count_label)
        self.content = content
        layout.addLayout(row)
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

    def set_count(self, text):
        """Počet nebo souhrn vpravo v řádku sekce (prázdné = nic)."""
        self.count_label.setText(str(text) if text not in (None, "") else "")
        self.count_label.setVisible(bool(self.count_label.text()))


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
        self.headings = {}  # velké titulky karet (P7.52)
        self.menu_buttons = {}  # malé titulky karet s nabídkou panelů
        self.badges = {}  # štítky stavu v hlavičce karty (P7.55)
        for key, dock in self.docks.items():
            action = QAction(dock.windowTitle(), window)
            action.setObjectName(f"panel_{key}")
            action.setCheckable(True)
            action.triggered.connect(lambda checked, k=key: self.show_panel(k) if checked
                                     else self.close_panel())
            self.actions[key] = action
            self.panels_menu.addAction(action)
            dock.visibilityChanged.connect(lambda visible, k=key: self._visibility(k, visible))
            # P7.52: hlavička karty podle návrhu 1a – malý titulek panelu s ▾ (výběr
            # panelu), velký titulek 15/700 s kontextem (např. název prvku) a ×.
            header = QWidget()
            column = QVBoxLayout(header)
            column.setContentsMargins(10, 6, 8, 2)
            column.setSpacing(0)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            title = QToolButton()
            title.setObjectName("card_panel_menu")
            title.setText(dock.windowTitle())
            title.setAutoRaise(True)
            title.setMenu(self.panels_menu)
            title.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            title.setAccessibleName("Zvolit pravý panel")
            row.addWidget(title)
            row.addStretch(1)
            badge = QLabel()  # štítek stavu (P7.55: „⚠ neúplná“ / „✓ platná“ studie NDT)
            badge.setObjectName("card_badge")
            badge.hide()
            row.addWidget(badge)
            self.badges[key] = badge
            close = QToolButton()
            close.setObjectName("card_close")
            close.setText("×")
            close.setAutoRaise(True)
            close.setAccessibleName("Zavřít pravý panel")
            close.setToolTip("Zavřít panel; znovu jej otevřeš přes Zobrazení → Panely")
            close.clicked.connect(self.close_panel)
            row.addWidget(close)
            self.menu_buttons[key] = title
            column.addLayout(row)
            heading = QLabel(dock.windowTitle())
            heading.setObjectName("card_heading")
            heading.setTextFormat(Qt.TextFormat.PlainText)
            heading.setWordWrap(True)
            heading.setContentsMargins(4, 0, 0, 0)
            column.addWidget(heading)
            self.headings[key] = heading
            dock.setTitleBarWidget(header)
        self.actions["editor"].setShortcut("F4")
        self.model_action = window._action("Strom modelu", self._toggle_model, "F9")
        self.model_action.setCheckable(True)
        self.model_action.setChecked(True)
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
        else:
            ui_theme.apply()
        self.show_panel(self.state.get("panel", "editor"))

    def set_heading(self, key, text=None, kind=None):
        """Velký titulek pravé karty (kontext, např. název prvku) a malý titulek nad ním.

        Bez textu velký titulek = název panelu; ``kind`` mění malý titulek (např.
        „Nový prvek · náhled“), bez něj je to opět název panelu s ▾."""
        label = self.headings[key]
        label.setText(text or self.docks[key].windowTitle())
        self.menu_buttons[key].setText(kind or self.docks[key].windowTitle())

    def set_badge(self, key, text, kind):
        """Štítek stavu v hlavičce karty (``ok`` / ``warn`` / ``err`` / ``info``); prázdný
        text ho skryje."""
        badge = self.badges[key]
        badge.setText(text)
        badge.setVisible(bool(text))
        if badge.property("cardBadge") != kind:
            badge.setProperty("cardBadge", kind)
            badge.style().unpolish(badge)
            badge.style().polish(badge)

    def heading(self, key):
        return self.headings[key].text()

    def _visibility(self, key, visible):
        # Karta se schová i při rušení okna (P7.49) – to už nesmí sahat na okno.
        if self._changing or not isValid(self.window) or not self.window.isVisible():
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
        self._panel_changed()

    def _panel_changed(self):
        """Pilulka ukazuje hodnotu měření jen s otevřeným panelem Měření (P7.54)."""
        refresh = getattr(self.window, "_refresh_pill_focus", None)
        if refresh is not None and isValid(self.window):
            refresh()

    def close_panel(self):
        if self.window.feature_preview is not None:
            self.window.cancel_feature_preview()
        self._changing = True
        try:
            for key, dock in self.docks.items():
                dock.hide()
                self.actions[key].setChecked(False)
            self.active = None
        finally:
            self._changing = False
        self._panel_changed()

    def _toggle_model(self):
        self.window.model_dock.setVisible(self.model_action.isChecked())

    def _model_visibility(self, visible):
        if isValid(self.window) and self.window.isVisible():
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
        ui_theme.apply(app)

    def refresh_palette(self):
        palette = QApplication.palette()
        key = (palette.color(QPalette.ColorRole.Window).rgba(),
               palette.color(QPalette.ColorRole.WindowText).rgba())
        if self._palette_key == key:
            return
        self._palette_key = key
        color = secondary_color(palette).name()
        t = ui_theme.tokens()
        card = ui_theme.card_color()
        field = ui_theme.opaque(t["sep"], card).name()
        # P7.51: strom leží přímo na kartě, filtry jsou zaoblená pole --sep (návrh 1a).
        line = ui_theme.opaque(t["sep2"], ui_theme.color(t["ctl"])).name()
        muted = ui_theme.opaque(t["sep2"], card).name()
        info = ui_theme.opaque(t["accentbg"], card).name()
        note = ui_theme.opaque(t["sep"], card).name()  # šedý rámeček „řez je jen pohled“
        tinted = {kind: ui_theme.opaque(t[f"{kind}bg"], card).name() for kind in ("ok", "warn")}
        err = ui_theme.color(t["err"])
        err.setAlphaF(0.12)
        tinted["err"] = ui_theme.opaque(err, card).name()
        step = ui_theme.opaque(t["ctl"], card).name()
        # P7.51/P7.52: strom na kartě, filtry --sep, pole 22 px --ctl s linkou --sep2
        # a fokusem --accent, tlačítka 24 px (primární --btn), hlavička karty 11 + 15/700.
        self.window.setStyleSheet(
            f"QLabel[secondaryText=\"true\"] {{ color: {color}; }}"
            f"QTreeWidget#feature_tree {{ background: transparent; border: none; }}"
            f"FloatingCard QLineEdit {{ background: {t['ctl']}; color: {t['fg']};"
            f" border: 1px solid {line}; border-radius: 5px; min-height: 22px;"
            f" padding: 0px 6px; }}"
            f"FloatingCard QLineEdit:focus {{ border: 1px solid {t['accent']}; }}"
            f"QLineEdit[cardFilter=\"true\"] {{ background: {field}; border: none;"
            f" border-radius: 6px; min-height: 24px; padding: 0px 6px; }}"
            f"QLabel#card_heading {{ font-size: 15px; font-weight: 700; color: {t['fg']}; }}"
            f"QToolButton#card_panel_menu {{ font-size: 11px; color: {t['fg3']};"
            f" border: none; padding: 0px 12px 0px 0px; }}"
            f"QToolButton#card_panel_menu::menu-indicator {{ subcontrol-position: right center;"
            f" subcontrol-origin: padding; width: 9px; }}"
            f"QToolButton#card_close {{ font-size: 15px; color: {t['fg3']}; border: none; }}"
            f"QPushButton[role=\"primary\"] {{ background: {t['btn']}; color: #ffffff;"
            f" border: none; border-radius: 6px; min-height: 24px; padding: 0px 14px;"
            f" font-weight: 500; }}"
            f"QPushButton[role=\"primary\"]:disabled {{ background: {muted};"
            f" color: {t['fg3']}; }}"
            f"QPushButton[role=\"secondary\"] {{ background: {t['ctl']}; color: {t['fg']};"
            f" border: 1px solid {line}; border-radius: 6px; min-height: 24px;"
            f" padding: 0px 12px; }}"
            f"QLabel[cardHint=\"true\"] {{ font-size: 12px; color: {t['fg3']}; }}"
            f"QPushButton[role=\"secondary\"]:disabled {{ color: {t['fg3']};"
            f" border: 1px solid {muted}; }}"
            f"QLabel[cardInfo=\"true\"] {{ background: {info}; color: {t['fg']};"
            f" border-radius: 6px; padding: 3px 8px; }}"
            f"QLabel[cardNote=\"true\"] {{ background: {note}; color: {t['fg2']};"
            f" border-radius: 6px; padding: 6px 10px; }}"
            # P7.55: stav studie v hlavičce, rámečky stavu, NDT kroky a upozornění (R7)
            + "".join(f"QLabel[cardBadge=\"{kind}\"] {{ background: {tinted[kind]};"
                      f" color: {t[kind]}; border-radius: 5px; padding: 1px 6px;"
                      f" font-size: 11px; font-weight: 600; }}"
                      f"QLabel[cardState=\"{kind}\"] {{ background: {tinted[kind]};"
                      f" color: {t['fg']}; border-radius: 6px; padding: 6px 10px; }}"
                      for kind in ("ok", "warn", "err"))
            + f"QLabel[cardBadge=\"info\"] {{ color: {t['fg3']}; font-size: 11px; }}"
            f"QLabel[cardState=\"info\"] {{ background: {note}; color: {t['fg2']};"
            f" border-radius: 6px; padding: 6px 10px; }}"
            f"QLabel[ndtWarning=\"true\"] {{ font-size: 12px; color: {t['fg2']}; }}"
            f"QFrame#ndt_step[stepState=\"active\"] {{ background: {step};"
            f" border: 1px solid {line}; border-radius: 10px; }}"
            f"QPushButton#ndt_step_change {{ color: {t['accent']}; border: none;"
            f" background: transparent; padding: 0px; }}")
        self.window.model_tabs.tabs.refresh_style()
        appearance = QApplication.instance().property("skodacadAppearance") or "system"
        self.appearance_actions[appearance].setChecked(True)
        self.window._refresh_ui_icons()
        self.window.main_bar.refresh_style()
        for name in ("status_pill", "view_switcher"):  # během stavby okna ještě nejsou
            if hasattr(self.window, name):
                getattr(self.window, name).refresh_style()
        self.window._refresh_tree()
        self.window.viewer.set_dark_background(ui_theme.is_dark())

    def reset(self):
        window = self.window
        window.ribbon.select_page("model")
        window.ribbon.set_collapsed(False)
        self.show_panel("editor")
        compact = window.width() < 1180
        window.model_dock.setVisible(not compact)
        self.model_action.setChecked(not compact)
        for key, section in window.sidebar_sections.items():
            section.set_expanded(key != "parameters")  # Díl: obě sekce otevřené
        window.model_tabs.select("features")  # levá karta začíná stromem prvků (P7.51)
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
            section.set_expanded(self.state.get("sections", {}).get(key, key != "parameters"))
        window.model_tabs.select(self.state.get("sidebar_tab", window.model_tabs.current))
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
                 # Karty mají šířku z návrhu 1a (P7.49); klíče zůstávají kvůli verzi 1.
                 "model_width": window.card_layer.width_of(window.model_dock),
                 "editor_width": window.card_layer.width_of(
                     self.docks[self.active or self.last_panel]),
                 "panel": self.active, "page": window.ribbon.page,
                 "ribbon_collapsed": window.ribbon.collapsed,
                 "appearance": QApplication.instance().property("skodacadAppearance") or "system",
                 "sections": {key: section.expanded
                              for key, section in window.sidebar_sections.items()},
                 "sidebar_tab": window.model_tabs.current}
        try:
            save_state(self.path, state)
        except (OSError, ValueError):
            log.warning("Rozložení okna se nepodařilo uložit.", exc_info=True)
