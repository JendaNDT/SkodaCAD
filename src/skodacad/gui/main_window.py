"""Hlavní okno: 3D prohlížeč uprostřed, vlevo díl, parametry, strom prvků a vlastnosti,
vpravo úprava vybraného prvku.

Okno nikdy nemodeluje samo – všechno jde přes ``ModelSession`` (jádro).
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QColor, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.features import REPEATABLE_FEATURES, describe, short_label
from skodacad.gui.feature_editor import FeatureEditor
from skodacad.gui.sketcher import SketcherDialog
from skodacad.gui.viewer_views import VIEW_LABELS
from skodacad.inspection import number
from skodacad.materials import DENSITIES_G_CM3, DISPLAY_NAMES, material_key
from skodacad.profile_edit import empty_profile
from skodacad.schema import FEATURE_SCHEMAS
from skodacad.session import SELECTION_FEATURES, ModelSession, format_parameter_value

if TYPE_CHECKING:
    from skodacad.worker import BackgroundRebuilder

log = logging.getLogger(__name__)

HELP_HINT = ("Levé tlačítko: otáčení  ·  Prostřední/pravé: posun  ·  Kolečko: zoom  ·  "
             "Klik: výběr plochy/hrany (Ctrl+klik: další)  ·  Pravý klik: co s výběrem  ·  "
             "Dvojklik: celý díl")

# Nový prvek z výběru ve 3D: typ → text akce.
SELECTION_ACTIONS = {
    "fillet": "Zaoblit vybrané hrany",
    "chamfer": "Srazit vybrané hrany",
    "sketch": "Skica na vybrané ploše",
    "hole": "Díra na vybrané ploše",
    "shell": "Skořepina – otevřít vybrané plochy",
}

_STATUS_ICONS = {"ok": "✓", "error": "✕", "skipped": "·", "pending": "⏳"}
_STATUS_COLORS = {"ok": QColor("#1b7f3b"), "error": QColor("#c0392b"), "skipped": QColor("#888"),
                  "pending": QColor("#8a8a8a")}
PENDING_DELAY = 0.25  # s – kratší přepočet se v okně neukazuje (žádné blikání)
_INVALID_STYLE = "QLineEdit { border: 2px solid #c0392b; background: #fdecea; }"
_FEATURE_ID = Qt.ItemDataRole.UserRole

EXPORT_FORMATS = [
    ("step", "STEP – pro jiné CAD programy"),
    ("stl", "STL – 3D tisk"),
    ("3mf", "3MF – 3D tisk (modernější)"),
]


class MainWindow(QMainWindow):
    def __init__(self, viewer_factory: Callable[[], QWidget] | None = None,
                 examples_dir: Path | None = None, user_dir: Path | None = None,
                 runner: BackgroundRebuilder | None = None) -> None:
        super().__init__()
        # S ``runner`` se model přepočítává na pozadí v pomocném procesu (okno je živé).
        self._runner = runner
        self.session = ModelSession(runner)
        self._pending_shown = False  # okno ukazuje „Přepočítávám…“
        self._shown_result = None  # výsledek, jehož díl je právě v prohlížeči
        self.examples_dir = examples_dir
        self.user_dir = user_dir or Path.home()
        self._param_fields: dict[str, QLineEdit] = {}
        self._selected_id: str | None = None
        self._picked: list = []  # plochy a hrany vybrané ve 3D (tvary OCCT z prohlížeče)

        if viewer_factory is None:
            from skodacad.gui.viewer import OccViewer

            viewer_factory = OccViewer
        self.viewer = viewer_factory()
        self.viewer.selection_changed.connect(self._selection_changed)
        self.viewer.context_menu_requested.connect(self._show_context_menu)
        self.setCentralWidget(self.viewer)

        self._create_actions()
        self._build_side_panel()
        self._build_editor_panel()
        self._build_menus()
        self.resize(1400, 860)
        self.resizeDocks([self.model_dock, self.editor_dock], [380, 360],
                         Qt.Orientation.Horizontal)
        self._had_part = False
        self._build_progress()
        self._reload_all()
        self.statusBar().showMessage(HELP_HINT)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        if runner is not None:
            self._poll_timer.start(50)

    # --- akce (tlačítka a položky menu) ------------------------------------------------

    def _action(self, text: str, slot: Callable[[], object],
                shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        # Signál triggered posílá navíc hodnotu „checked“ (False). Lambda s výchozím parametrem
        # (lambda k=key: …) by ji dostala místo svého k – proto slot voláme vždy bez argumentů.
        action.triggered.connect(lambda _checked=False: slot())
        return action

    def _create_actions(self) -> None:
        self.new_action = self._action("Nový", self.new_model, "Ctrl+N")
        self.open_action = self._action("Otevřít…", self.open_dialog, "Ctrl+O")
        self.save_action = self._action("Uložit", self.save, "Ctrl+S")
        self.save_as_action = self._action("Uložit jako…", self.save_as, "Ctrl+Shift+S")
        self.undo_action = self._action("Zpět", self.undo, "Ctrl+Z")
        self.redo_action = self._action("Znovu", self.redo, "Ctrl+Y")
        self.rebuild_action = self._action("Přepočítat", self.rebuild, "F5")
        self.add_feature_actions = {
            key: self._action(schema.label, lambda k=key: self.add_feature(k))
            for key, schema in FEATURE_SCHEMAS.items()
        }
        self.profile_sketch_action = self._action("Skica – nakreslit obrys…",
                                                  self.add_profile_sketch)
        self.profile_sketch_action.setToolTip(
            "Skicář: obrys z úseček a oblouků s vazbami a kótami")
        self.delete_feature_action = self._action("Smazat prvek", self.delete_feature, "Delete")
        self.move_up_action = self._action("Posunout nahoru", lambda: self.move_feature(-1))
        self.move_down_action = self._action("Posunout dolů", lambda: self.move_feature(+1))
        self.add_parameter_action = self._action("Přidat parametr…", self.add_parameter)
        self.delete_parameter_action = self._action("Smazat parametr…", self.delete_parameter)
        # Krátké popisky pro malá tlačítka v panelu (v menu zůstává celý text).
        for action, short in ((self.delete_feature_action, "Smazat"),
                              (self.move_up_action, "▲"), (self.move_down_action, "▼"),
                              (self.add_parameter_action, "+ Parametr"),
                              (self.delete_parameter_action, "− Parametr")):
            action.setIconText(short)
            action.setToolTip(action.text())
        self.fit_action = self._action("Celý díl", lambda: self.viewer.fit_all(), "F")
        self.selection_actions = {
            key: self._action(text, lambda k=key: self.add_from_selection(k))
            for key, text in SELECTION_ACTIONS.items()
        }
        self.add_to_feature_action = self._action("Přidat výběr do vybraného prvku",
                                                  self.apply_selection)
        self.replace_in_feature_action = self._action(
            "Nahradit hrany vybraného prvku výběrem", lambda: self.apply_selection(replace=True))
        self.clear_selection_action = self._action("Zrušit výběr ve 3D",
                                                   lambda: self.viewer.clear_selection(), "Esc")
        self.stop_action = self._action("Zastavit přepočet", self.stop_rebuild)
        self.stop_action.setToolTip("Zastaví pomalý přepočet a vrátí model do posledního "
                                    "spočítaného stavu (Znovu změnu vrátí)")
        self.stop_action.setEnabled(False)

    # --- stavba okna ---------------------------------------------------------------

    def _build_side_panel(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        info_box = QGroupBox("Díl")
        info_form = QFormLayout(info_box)
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("part_name")
        self.name_edit.editingFinished.connect(self._name_edited)
        info_form.addRow("Název", self.name_edit)
        self.material_combo = QComboBox()
        self.material_combo.setObjectName("part_material")
        for key, density in DENSITIES_G_CM3.items():
            self.material_combo.addItem(f"{DISPLAY_NAMES[key]} ({density} g/cm³)",
                                        DISPLAY_NAMES[key])
        self.material_combo.currentIndexChanged.connect(self._material_changed)
        info_form.addRow("Materiál", self.material_combo)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: #555;")
        info_form.addRow(self.description_label)
        layout.addWidget(info_box)

        params_box = QGroupBox("Parametry (Enter = přepočítat)")
        params_layout = QVBoxLayout(params_box)
        self.params_form = QFormLayout()
        params_layout.addLayout(self.params_form)
        params_buttons = QHBoxLayout()
        for action in (self.add_parameter_action, self.delete_parameter_action):
            params_buttons.addWidget(self._tool_button(action))
        params_buttons.addStretch()
        params_layout.addLayout(params_buttons)
        layout.addWidget(params_box)

        tree_box = QGroupBox("Strom prvků")
        tree_layout = QVBoxLayout(tree_box)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.currentItemChanged.connect(self._tree_selection_changed)
        tree_layout.addWidget(self.tree)
        tree_buttons = QHBoxLayout()
        self.add_feature_button = QToolButton()
        self.add_feature_button.setText("Přidat prvek")
        self.add_feature_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        add_menu = QMenu(self.add_feature_button)
        for action in self.add_feature_actions.values():
            add_menu.addAction(action)
            if action is self.add_feature_actions["sketch"]:
                add_menu.addAction(self.profile_sketch_action)
        self.add_feature_button.setMenu(add_menu)
        tree_buttons.addWidget(self.add_feature_button)
        for action in (self.delete_feature_action, self.move_up_action, self.move_down_action):
            tree_buttons.addWidget(self._tool_button(action))
        tree_buttons.addStretch()
        tree_layout.addLayout(tree_buttons)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #c0392b; font-weight: bold;")
        self.error_label.hide()
        tree_layout.addWidget(self.error_label)
        layout.addWidget(tree_box, stretch=1)

        props_box = QGroupBox("Vlastnosti dílu")
        props_layout = QVBoxLayout(props_box)
        self.props_label = QLabel()
        self.props_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        props_layout.addWidget(self.props_label)
        layout.addWidget(props_box)

        self.model_dock = self._add_dock("Model", "model_dock", panel,
                                         Qt.DockWidgetArea.LeftDockWidgetArea)

    def _build_editor_panel(self) -> None:
        self.feature_editor = FeatureEditor(profile_editor=self.edit_profile)
        self.feature_editor.changed.connect(self._feature_edited)
        self.feature_editor.invalid.connect(
            lambda message: self.statusBar().showMessage(message, 10000))
        self.editor_dock = self._add_dock("Úprava prvku", "editor_dock", self.feature_editor,
                                          Qt.DockWidgetArea.RightDockWidgetArea)

    def _add_dock(self, title: str, name: str, content: QWidget,
                  area: Qt.DockWidgetArea) -> QDockWidget:
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(scroll)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        dock.setMinimumWidth(340)
        self.addDockWidget(area, dock)
        return dock

    def _tool_button(self, action: QAction) -> QToolButton:
        button = QToolButton()
        button.setDefaultAction(action)  # bez ikony ukazuje action.iconText()
        return button

    def _build_menus(self) -> None:
        bar = self.menuBar()
        toolbar = self.addToolBar("Hlavní")
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)

        file_menu = bar.addMenu("&Soubor")
        for action in (self.new_action, self.open_action):
            file_menu.addAction(action)
            toolbar.addAction(action)
        examples_menu = file_menu.addMenu("Otevřít ukázku")
        for path in sorted(self.examples_dir.glob("*.json")) if self.examples_dir else []:
            examples_menu.addAction(
                self._action(path.stem, lambda p=path: self.open_model(p, template=True))
            )
        examples_menu.setEnabled(not examples_menu.isEmpty())
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        toolbar.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        export_menu = file_menu.addMenu("Exportovat")
        for fmt, label in EXPORT_FORMATS:
            export_menu.addAction(self._action(label + "…", lambda f=fmt: self.export_dialog(f)))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Konec", self.close, "Ctrl+Q"))
        toolbar.addSeparator()

        edit_menu = bar.addMenu("Ú&pravy")
        for action in (self.undo_action, self.redo_action):
            edit_menu.addAction(action)
            toolbar.addAction(action)
        edit_menu.addSeparator()
        add_menu = edit_menu.addMenu("Přidat prvek")
        for action in self.add_feature_actions.values():
            add_menu.addAction(action)
            if action is self.add_feature_actions["sketch"]:
                add_menu.addAction(self.profile_sketch_action)
        for action in (self.delete_feature_action, self.move_up_action, self.move_down_action):
            edit_menu.addAction(action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.add_parameter_action)
        edit_menu.addAction(self.delete_parameter_action)
        toolbar.addSeparator()

        model_menu = bar.addMenu("&Model")
        model_menu.addAction(self.rebuild_action)
        model_menu.addAction(self.stop_action)
        toolbar.addAction(self.rebuild_action)
        toolbar.addSeparator()
        selection_menu = model_menu.addMenu("Z výběru ve 3D")
        self._fill_selection_menu(selection_menu)

        view_menu = bar.addMenu("&Zobrazení")
        view_menu.addAction(self.fit_action)
        toolbar.addAction(self.fit_action)
        for key, (label, shortcut) in VIEW_LABELS.items():
            action = self._action(label, lambda k=key: self.viewer.set_standard_view(k), shortcut)
            view_menu.addAction(action)
            if key in ("iso", "top", "front", "right"):
                toolbar.addAction(action)

        help_menu = bar.addMenu("&Nápověda")
        help_menu.addAction(self._action("Ovládání", self.show_controls))
        help_menu.addAction(self._action("O aplikaci", self.show_about))

    def _fill_selection_menu(self, menu: QMenu) -> None:
        for action in self.selection_actions.values():
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.add_to_feature_action)
        menu.addAction(self.replace_in_feature_action)
        menu.addSeparator()
        menu.addAction(self.clear_selection_action)

    # --- práce se souborem -------------------------------------------------------

    def new_model(self) -> bool:
        if not self._confirm_discard():
            return False
        self.session.new_document()
        self._selected_id = None
        self._reload_all(fit=True)
        self.statusBar().showMessage("Nový díl – začni tlačítkem „Přidat prvek“ → Skica.", 10000)
        return True

    def open_model(self, path: str | Path, template: bool = False) -> bool:
        if not self._confirm_discard():
            return False
        try:
            self._busy(lambda: (self.session.open_template(path) if template
                                else self.session.open(path)))
        except DocumentError as exc:
            self._error("Model nejde otevřít", str(exc))
            return False
        log.info("Otevřen model %s", path)
        self._selected_id = None
        self._reload_all(fit=True)
        return True

    def open_dialog(self) -> None:
        start = str(self.session.path.parent if self.session.path else self.user_dir)
        path, _ = QFileDialog.getOpenFileName(self, "Otevřít model", start,
                                              "Model ŠkodaCAD (*.json)")
        if path:
            self.open_model(path)

    def save(self) -> bool:
        if self.session.document is None:
            return False
        if self.session.path is None:
            return self.save_as()
        return self._save_to(self.session.path)

    def save_as(self) -> bool:
        if self.session.document is None:
            return False
        suggested = self.session.path or self.user_dir / f"{self._stem()}.json"
        path, _ = QFileDialog.getSaveFileName(self, "Uložit model", str(suggested),
                                              "Model ŠkodaCAD (*.json)")
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".json"
        return self._save_to(Path(path))

    def _save_to(self, path: Path) -> bool:
        try:
            self.session.save(path)
        except (DocumentError, OSError) as exc:
            self._error("Uložení se nepodařilo", str(exc))
            return False
        self.statusBar().showMessage(f"Uloženo: {path}", 8000)
        self._refresh_title()
        return True

    def export_dialog(self, fmt: str) -> None:
        if self.session.computing:
            self.statusBar().showMessage("Model se ještě přepočítává – export půjde, až bude "
                                         "hotovo (nebo přepočet zastav).", 10000)
            return
        if self.session.result is None or self.session.result.part is None:
            self._error("Není co exportovat", "Model zatím nemá žádné těleso.")
            return
        folder = self.session.path.parent if self.session.path else self.user_dir
        suggested = folder / f"{self._stem()}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.upper()}", str(suggested),
                                              f"{fmt.upper()} (*.{fmt})")
        if not path:
            return
        if not path.lower().endswith(f".{fmt}"):
            path += f".{fmt}"
        try:
            self._busy(lambda: self.session.export(path))
        except (DocumentError, OSError, RuntimeError, ValueError) as exc:
            self._error("Export se nepodařil", str(exc))
            return
        self.statusBar().showMessage(f"Exportováno: {path}", 8000)

    def _stem(self) -> str:
        if self.session.path:
            return self.session.path.stem
        name = self.session.document.name if self.session.document else "model"
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name).strip("_") or "model"

    # --- úpravy modelu -------------------------------------------------------------

    def _apply(self, change: Callable[[], object], structural: bool = True) -> bool:
        """Provede úpravu přes ModelSession; chybu ukáže česky a model nechá beze změny."""
        if self.session.document is None:
            return False
        try:
            self._busy(change)
        except DocumentError as exc:
            self._error("Úprava nejde provést", str(exc))
            return False
        if structural:
            self._reload_all()
        else:
            self._refresh_all()
        return True

    def add_feature(self, feature_type: str) -> None:
        if self.session.document is None:
            self.session.new_document()
        new_id: list[str] = []
        if self._apply(lambda: new_id.append(
                self.session.add_feature(feature_type, after_id=self._selected_id)),
                structural=False):
            self._selected_id = new_id[0]
            self._reload_all()

    def edit_profile(self, profile: dict) -> dict | None:
        """Otevře skicář nad obrysem; vrátí upravený obrys, nebo None (Zrušit)."""
        dialog = SketcherDialog(profile, self.session.solve_profile, self)
        try:
            if self._exec_dialog(dialog) == QDialog.DialogCode.Accepted:
                return dialog.result_profile()
            return None
        finally:
            dialog.deleteLater()  # jinak by po každém otevření zůstalo skryté okno v paměti

    def _exec_dialog(self, dialog: QDialog) -> int:
        return dialog.exec()  # samostatně, aby ho test mohl nahradit (jinak čeká na klik)

    def add_profile_sketch(self) -> None:
        """Nová skica s obrysem nakresleným ve skicáři (jeden krok pro Zpět)."""
        if self.session.document is None:
            self.session.new_document()
            self._reload_all()
        profile = self.edit_profile(empty_profile())
        if profile is None:
            return
        if not profile["segments"]:
            self.statusBar().showMessage("Skicář byl prázdný – skica nevznikla.", 10000)
            return
        new_id: list[str] = []
        if self._apply(lambda: new_id.append(self.session.add_feature(
                "sketch", after_id=self._selected_id, values={"elements": [profile]})),
                structural=False):
            self._selected_id = new_id[0]
            self._reload_all()
            self.statusBar().showMessage(
                "Skica s obrysem přidána – teď ji vysuň (Přidat prvek → Vysunutí).", 10000)

    def add_from_selection(self, feature_type: str) -> None:
        """Nový prvek z výběru ve 3D (zaoblení kliknutých hran, skica na ploše …)."""
        picked, point = list(self._picked), getattr(self.viewer, "picked_point", None)
        new_id: list[str] = []
        if self._apply(lambda: new_id.append(
                self.session.add_from_selection(feature_type, picked, point)),
                structural=False):
            self._selected_id = new_id[0]
            self._reload_all()
            self.statusBar().showMessage(
                f"Přidáno: {describe(self.session.feature(new_id[0]))} – hodnoty uprav vpravo.",
                10000)

    def apply_selection(self, replace: bool = False) -> None:
        """Výběr ve 3D do prvku vybraného ve stromu (hrany zaoblení, rovina skici …)."""
        if self._selected_id is None:
            return
        picked = list(self._picked)
        point = getattr(self.viewer, "picked_point", None)
        if self._apply(lambda: self.session.apply_selection(self._selected_id, picked, replace,
                                                            point=point), structural=False):
            self._load_editor()

    def delete_feature(self) -> None:
        if self._selected_id is None:
            return
        index = self.session.feature_index(self._selected_id)
        if self._apply(lambda: self.session.delete_feature(self._selected_id), structural=False):
            features = self.session.document.features
            self._selected_id = features[max(index - 1, 0)]["id"] if features else None
            self._reload_all()

    def move_feature(self, offset: int) -> None:
        if self._selected_id is not None:
            self._apply(lambda: self.session.move_feature(self._selected_id, offset))

    def _feature_edited(self, feature_id: str, feature: dict) -> None:
        # Formulář zůstává, jak ho uživatel vyplnil – přestavět jen strom, 3D a vlastnosti.
        self._apply(lambda: self.session.update_feature(feature_id, feature), structural=False)

    def add_parameter(self) -> None:
        if self.session.document is None:
            return
        name, ok = QInputDialog.getText(self, "Přidat parametr",
                                        "Název parametru (např. D, tloustka, roztec):")
        if not ok or not name.strip():
            return
        value, ok = QInputDialog.getText(self, "Přidat parametr",
                                         f"Hodnota parametru {name.strip()} (číslo nebo výraz):",
                                         text="10")
        if ok:
            self._apply(lambda: self.session.add_parameter(name, value))

    def delete_parameter(self) -> None:
        if not self.session.document or not self.session.document.parameters:
            return
        names = list(self.session.document.parameters)
        name, ok = QInputDialog.getItem(self, "Smazat parametr", "Parametr:", names, 0, False)
        if ok and name:
            self._apply(lambda: self.session.delete_parameter(name))

    def _name_edited(self) -> None:
        document = self.session.document
        if document is not None and self.name_edit.text().strip() != document.name:
            self._apply(lambda: self.session.set_info(name=self.name_edit.text()),
                        structural=False)

    def _material_changed(self) -> None:
        document = self.session.document
        material = self.material_combo.currentData()
        if document is not None and material_key(material) != material_key(document.material):
            self._apply(lambda: self.session.set_info(material=material), structural=False)

    def undo(self) -> None:
        if self.session.can_undo:
            self._busy(self.session.undo)
            self._reload_all()

    def redo(self) -> None:
        if self.session.can_redo:
            self._busy(self.session.redo)
            self._reload_all()

    # --- parametry a přepočet ------------------------------------------------------

    def _rebuild_param_fields(self) -> None:
        while self.params_form.rowCount():
            self.params_form.removeRow(0)
        self._param_fields.clear()
        if self.session.document is None:
            return
        for name, value in self.session.document.parameters.items():
            field = QLineEdit(format_parameter_value(value))
            field.setObjectName(f"param_{name}")
            field.editingFinished.connect(lambda n=name: self._parameter_edited(n))
            self.params_form.addRow(name, field)
            self._param_fields[name] = field

    def _parameter_edited(self, name: str) -> None:
        field = self._param_fields[name]
        current = format_parameter_value(self.session.document.parameters[name])
        if field.text().strip() == current and not field.styleSheet():
            return
        try:
            self._busy(lambda: self.session.set_parameter(name, field.text()))
        except DocumentError as exc:
            field.setStyleSheet(_INVALID_STYLE)
            field.setToolTip(str(exc))
            self.statusBar().showMessage(f"Parametr {name}: {exc}", 10000)
            return
        field.setStyleSheet("")
        field.setToolTip("")
        field.setText(format_parameter_value(self.session.document.parameters[name]))
        self._refresh_all()

    def rebuild(self) -> None:
        if self.session.document is not None:
            self._busy(self.session.rebuild)
            self._refresh_all()

    # --- obnovení zobrazení --------------------------------------------------------

    def _reload_all(self, fit: bool = False) -> None:
        """Po změně struktury (otevření, přidání/smazání prvku, Zpět …) obnov vše."""
        self._rebuild_param_fields()
        self._reload_info()
        self._refresh_all(fit=fit)
        self._load_editor()

    def _refresh_all(self, fit: bool = False) -> None:
        self._refresh_title()
        self._refresh_tree()
        self._refresh_properties()
        result = self.session.result
        if result is not self._shown_result or fit:  # díl se kreslí znovu jen když je nový
            self._picked = []  # → starý výběr ve 3D už neplatí
            part = result.part if result else None
            # Když těleso vznikne poprvé (nový díl), přizpůsobit pohled – jinak zůstane kamera.
            self.viewer.show_part(part, fit=fit or (part is not None and not self._had_part))
            self._had_part = part is not None
            self._shown_result = result
        self._refresh_actions()
        self._refresh_progress()
        self._update_highlight()

    # --- přepočet na pozadí ----------------------------------------------------------

    def _build_progress(self) -> None:
        """Ve stavovém řádku: „Přepočítávám… 3 s“, běžící pruh a tlačítko Zastavit."""
        self.progress_label = QLabel()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # neurčitý průběh (běžící pruh)
        self.progress_bar.setMaximumWidth(120)
        self.progress_bar.setMaximumHeight(14)
        self.stop_button = self._tool_button(self.stop_action)
        for widget in (self.progress_label, self.progress_bar, self.stop_button):
            self.statusBar().addPermanentWidget(widget)
            widget.hide()

    def _poll(self) -> None:
        """Časovač: převezme hotový přepočet z pozadí, nebo obnoví ukazatel průběhu."""
        if self.session.poll():
            self._pending_shown = False
            self._refresh_all()
            if self.session.failure:
                self._error("Přepočet se nepovedl", self.session.failure)
        elif self.session.computing and not self._pending_shown \
                and self.session.computing_seconds >= PENDING_DELAY:
            self._pending_shown = True
            self._refresh_tree()
            self._refresh_properties()
            self._refresh_progress()
        elif self._pending_shown:
            self._refresh_progress()

    def _refresh_progress(self) -> None:
        computing = self.session.computing
        if not computing:
            self._pending_shown = False
        shown = computing and self._pending_shown
        self.progress_label.setText(
            f"⏳ Přepočítávám… {self.session.computing_seconds:.0f} s" if shown else "")
        for widget in (self.progress_label, self.progress_bar, self.stop_button):
            widget.setVisible(shown)
        self.stop_action.setEnabled(computing)

    def stop_rebuild(self) -> None:
        if self.session.cancel():
            self._pending_shown = False
            self._reload_all()
            self.statusBar().showMessage("Přepočet zastaven – model je zpět v posledním "
                                         "spočítaném stavu (Znovu změnu vrátí).", 10000)

    def _update_highlight(self) -> None:
        """Ve 3D zvýraznit, co používá prvek vybraný ve stromu (hrany zaoblení, skicu …)."""
        shapes = self.session.feature_highlight(self._selected_id) if self._selected_id else []
        self.viewer.highlight(shapes)

    def _refresh_title(self) -> None:
        self.setWindowTitle(self.session.title)

    def _reload_info(self) -> None:
        document = self.session.document
        for widget in (self.name_edit, self.material_combo):
            widget.blockSignals(True)
        self.name_edit.setText(document.name if document else "")
        self.name_edit.setEnabled(document is not None)
        self.material_combo.setEnabled(document is not None)
        if document is not None:
            keys = [material_key(self.material_combo.itemData(i))
                    for i in range(self.material_combo.count())]
            key = material_key(document.material)
            self.material_combo.setCurrentIndex(keys.index(key) if key in keys else 0)
        for widget in (self.name_edit, self.material_combo):
            widget.blockSignals(False)
        self.description_label.setText(document.description if document else
                                       "Začni přes Soubor → Nový, nebo otevři ukázku.")
        self.description_label.setVisible(bool(self.description_label.text()))

    def _refresh_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        result = self.session.result
        document = self.session.document
        if document is None or (result is None and not self.session.computing):
            self.error_label.hide()
            self.tree.blockSignals(False)
            return
        old = {s.id: s for s in result.statuses} if result else {}
        if self.session.computing:  # strom podle modelu, stavy z posledního přepočtu
            rows = [(f["id"], describe(f), old[f["id"]].status if f["id"] in old else "pending",
                     "") for f in document.features]
            if self._pending_shown:
                rows = [(key, label, "pending", "Přepočítává se…") for key, label, _, _ in rows]
        else:
            rows = [(s.id, s.label, s.status, s.message) for s in result.statuses]
        for key, label, status, message in rows:
            item = QTreeWidgetItem([f"{_STATUS_ICONS[status]}  {label}"])
            item.setData(0, _FEATURE_ID, key)
            item.setForeground(0, _STATUS_COLORS[status])
            item.setToolTip(0, message or key)
            self.tree.addTopLevelItem(item)
            if key == self._selected_id:
                self.tree.setCurrentItem(item)
        if self._selected_id not in {row[0] for row in rows}:
            self._selected_id = None
        self.tree.blockSignals(False)
        if self.session.computing or result is None:
            if self._pending_shown:
                self.error_label.hide()
            return
        error = result.first_error
        if error is None:
            self.error_label.hide()
        else:
            self.error_label.setText(f"✕ {error.label}: {error.message}")
            self.error_label.show()

    def _refresh_actions(self) -> None:
        has_document = self.session.document is not None
        selected = self._selected_id is not None
        self.undo_action.setEnabled(self.session.can_undo)
        self.redo_action.setEnabled(self.session.can_redo)
        for action in (self.delete_feature_action, self.move_up_action, self.move_down_action):
            action.setEnabled(selected)
        for action in (self.save_action, self.save_as_action, self.add_parameter_action):
            action.setEnabled(has_document)
        self.delete_parameter_action.setEnabled(
            has_document and bool(self.session.document.parameters))
        self._refresh_selection_actions()

    def _refresh_selection_actions(self) -> None:
        info = self.session.selection_info(self._picked)
        has_part = (self.session.result is not None and self.session.result.part is not None
                    and not self.session.computing)  # výběr jen na hotovém dílu
        flat = info.faces > 0 and info.flat_faces == info.faces
        needs = {"fillet": info.edges > 0, "chamfer": info.edges > 0,
                 "sketch": info.faces == 1 and flat, "hole": info.faces == 1 and flat,
                 "shell": flat}
        for key, action in self.selection_actions.items():
            action.setEnabled(has_part and needs[key])
        document = self.session.document
        feature = next((copy.deepcopy(f) for f in document.features
                        if f["id"] == self._selected_id), None) if document else None
        kind = feature["type"] if feature else None
        texts = {"fillet": "Přidat vybrané hrany do: ", "chamfer": "Přidat vybrané hrany do: ",
                 "sketch": "Přesunout na vybranou plochu: ",
                 "hole": "Přidat díru v místě kliknutí do: ",
                 "shell": "Otevřít vybrané plochy v: "}
        if kind in SELECTION_FEATURES:
            self.add_to_feature_action.setText(texts[kind] + describe(feature))
        else:
            self.add_to_feature_action.setText("Přidat výběr do vybraného prvku")
        self.add_to_feature_action.setEnabled(has_part and kind in SELECTION_FEATURES
                                              and needs[kind])
        self.replace_in_feature_action.setEnabled(has_part and kind in ("fillet", "chamfer")
                                                  and info.edges > 0)
        self.clear_selection_action.setEnabled(bool(self._picked))

    def _tree_selection_changed(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        self._selected_id = current.data(0, _FEATURE_ID) if current is not None else None
        self._refresh_actions()
        self._load_editor()
        self._update_highlight()

    def _load_editor(self) -> None:
        if self._selected_id is None or self.session.document is None:
            self.feature_editor.show_feature(None)
            return
        features = self.session.document.features
        index = self.session.feature_index(self._selected_id)
        sketches = [(f["id"], describe(f)) for f in features[:index] if f["type"] == "sketch"]
        repeatable = [(f["id"], short_label(f)) for f in features[:index]
                      if f["type"] in REPEATABLE_FEATURES]
        self.feature_editor.show_feature(self.session.feature(self._selected_id), sketches,
                                         repeatable)

    def _refresh_properties(self) -> None:
        props = self.session.properties
        if props is None:
            self.props_label.setText("⏳ Přepočítávám…" if self.session.computing else "—")
            return
        sx, sy, sz = props.size_mm
        cx, cy, cz = props.center_of_mass_mm
        mass = (f"{number(props.mass_kg, 3)} kg ({props.material})" if props.mass_kg is not None
                else f"neznámý materiál „{props.material}“")
        lines = [
            f"Objem:  {number(props.volume_mm3, 0)} mm³",
            f"Povrch:  {number(props.area_mm2, 0)} mm²",
            f"Hmotnost:  {mass}",
            f"Rozměry:  {number(sx)} × {number(sy)} × {number(sz)} mm",
            f"Těžiště:  X {number(cx)}  Y {number(cy)}  Z {number(cz)}",
        ]
        if props.solids != 1:
            lines.append(f"Pozor: {props.solids} samostatná tělesa")
        if self._pending_shown:
            lines.insert(0, "⏳ Přepočítává se – hodnoty jsou z minulého stavu:")
        self.props_label.setText("\n".join(lines))

    def _selection_changed(self, shapes: list) -> None:
        """Prohlížeč hlásí nový výběr ve 3D: popis do stavového řádku, akce povolit."""
        self._picked = list(shapes)
        self._refresh_selection_actions()
        info = self.session.selection_info(self._picked)
        if not info.text:
            self.statusBar().showMessage(HELP_HINT)
            return
        hints = []
        if info.edges:
            hints.append("pravým tlačítkem zaoblit nebo srazit")
        if info.faces == 1 and info.flat_faces == 1:
            hints.append("pravým tlačítkem skica nebo díra na ploše")
        hints.append("Ctrl+klik přidá další")
        self.statusBar().showMessage(f"{info.text}  ·  " + ", ".join(hints))

    def _show_context_menu(self, position: QPoint | None = None) -> None:
        """Pravý klik do 3D: co jde s výběrem udělat."""
        menu = QMenu(self)
        if not self._picked:
            title = menu.addAction("Nic není vybrané – klikni na hranu nebo plochu")
            title.setEnabled(False)
            menu.addSeparator()
        self._fill_selection_menu(menu)
        menu.addSeparator()
        menu.addAction(self.fit_action)
        self._exec_menu(menu, position if position is not None else QCursor.pos())

    def _exec_menu(self, menu: QMenu, position: QPoint) -> None:
        menu.exec(position)  # samostatně, aby ho test mohl nahradit (jinak čeká na klik)

    # --- dialogy a pomocné ---------------------------------------------------------

    def show_controls(self) -> None:
        QMessageBox.information(self, "Ovládání", HELP_HINT.replace("  ·  ", "\n"))

    def show_about(self) -> None:
        QMessageBox.about(
            self, "O aplikaci ŠkodaCAD",
            "<b>ŠkodaCAD</b> – osobní parametrický 3D CAD.<br><br>"
            "Geometrické jádro: <b>Open CASCADE Technology</b> (LGPL 2.1 s výjimkou), "
            "přes knihovnu build123d (Apache 2.0).<br>"
            "Grafické rozhraní: Qt / PySide6 (LGPL 3).",
        )

    def _busy(self, work: Callable[[], object]) -> object:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return work()
        finally:
            QApplication.restoreOverrideCursor()

    def _error(self, title: str, message: str) -> None:
        log.warning("%s: %s", title, message)
        QMessageBox.warning(self, title, message)

    def _confirm_discard(self) -> bool:
        """Při neuložených změnách se zeptá; False = uživatel akci zrušil."""
        if not self.session.dirty:
            return True
        answer = QMessageBox.question(
            self, "Neuložené změny", "Model má neuložené změny. Uložit je?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._confirm_discard():
            self._poll_timer.stop()
            if self._runner is not None:
                self._runner.close()  # pomocné procesy přepočtu
            event.accept()
        else:
            event.ignore()
