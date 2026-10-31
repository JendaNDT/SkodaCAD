"""Hlavní okno: 3D prohlížeč uprostřed, vlevo díl, parametry, strom prvků a vlastnosti,
vpravo úprava vybraného prvku.

Okno nikdy nemodeluje samo – všechno jde přes ``ModelSession`` (jádro).
"""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QColor, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSlider,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.buildinfo import build_text, libraries_text
from skodacad.document import DocumentError
from skodacad.features import REPEATABLE_FEATURES, describe, short_label
from skodacad.gui.assembly_window import AssemblyWindow, is_assembly_file
from skodacad.gui.assistant_panel import AssistantPanel
from skodacad.gui.audit_panel import MARK as AUDIT_MARK
from skodacad.gui.audit_panel import AuditPanel
from skodacad.gui.design_panel import DesignPanel
from skodacad.gui.direct_edit_dialog import DirectEditDialog
from skodacad.gui.feature_editor import FeatureEditor
from skodacad.gui.file_dialogs import FILE_OPTIONS
from skodacad.gui.ndt_panel import NdtPanel
from skodacad.gui.sketcher import SketcherDialog
from skodacad.gui.viewer_views import VIEW_LABELS
from skodacad.inspection import number
from skodacad.materials import DENSITIES_G_CM3, DISPLAY_NAMES, material_key
from skodacad.measure import SavedResult, Value, format_value
from skodacad.ndt.volume_coverage import VolumeCoverageMap
from skodacad.profile_edit import empty_profile
from skodacad.schema import FEATURE_SCHEMAS
from skodacad.section import AXIS_NAMES
from skodacad.section import describe as describe_section
from skodacad.session import SELECTION_FEATURES, ModelSession, format_parameter_value
from skodacad.thickness_map import BELOW_LIMIT, NO_MATERIAL, SCALE, ThicknessMap

if TYPE_CHECKING:
    from skodacad.worker import BackgroundRebuilder

log = logging.getLogger(__name__)

HELP_HINT = ("Levé tlačítko: otáčení  ·  Prostřední/pravé nebo Shift+levé: posun  ·  "
             "Kolečko: zoom  ·  Klik: výběr plochy/hrany (Ctrl+klik: další)  ·  "
             "Pravý klik: co s výběrem  ·  Dvojklik: celý díl")

# Nový prvek z výběru ve 3D: typ → text akce.
SELECTION_ACTIONS = {
    "fillet": "Zaoblit vybrané hrany",
    "variable_fillet": "Proměnné zaoblení vybrané hrany",
    "chamfer": "Srazit vybrané hrany",
    "sketch": "Skica na vybrané ploše",
    "hole": "Díra na vybrané ploše",
    "shell": "Skořepina – otevřít vybrané plochy",
    "move_face": "Posunout vybranou plochu…",
    "face_diameter": "Změnit průměr vybrané plochy…",
}

MEASURE_HINT = ("Klikni ve 3D na plochu nebo hranu – ukáže se její velikost a tloušťka stěny "
                "v místě kliknutí. Ctrl+klik na druhou změří vzdálenost a úhel mezi nimi.")
_MEASURE_COLOR = QColor("#1b7f3b")

_SLIDER_STEPS = 1000  # jemnost posuvníku řezu

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


def _swatch(color: tuple[float, float, float]) -> str:
    r, g, b = (int(c * 255) for c in color)
    return f'<span style="color: rgb({r}, {g}, {b});">■</span>'


def _reference_parts(folder: Path) -> list[tuple[str, Path]]:
    """Referenční díly NDT do nabídky: (název modelu, soubor), seřazené podle čísla v názvu."""
    parts = []
    for path in folder.glob("*.json"):
        try:
            name = str(json.loads(path.read_text(encoding="utf-8")).get("name") or path.stem)
        except (OSError, ValueError, AttributeError):
            name = path.stem
        parts.append((name, path))
    return sorted(parts, key=lambda item: [int(t) if t.isdigit() else t
                                           for t in item[0].split()])


class MainWindow(QMainWindow):
    def __init__(self, viewer_factory: Callable[[], QWidget] | None = None,
                 examples_dir: Path | None = None, user_dir: Path | None = None,
                 runner: BackgroundRebuilder | None = None) -> None:
        super().__init__()
        # S ``runner`` se model přepočítává na pozadí v pomocném procesu (okno je živé).
        self._runner = runner
        self.session = ModelSession(runner)
        self._pending_shown = False  # okno ukazuje „Přepočítávám…“
        self._shown_key: tuple | None = None  # (výsledek, řez) právě v prohlížeči
        self.examples_dir = examples_dir
        self.user_dir = user_dir or Path.home()
        self._param_fields: dict[str, QLineEdit] = {}
        self._selected_id: str | None = None
        self._picked: list = []  # plochy a hrany vybrané ve 3D (tvary OCCT z prohlížeče)
        self._measured: list[Value] = []  # co jde na výběru změřit (panel Měření)
        self._shown_map: ThicknessMap | None = None  # mapa tloušťky právě v prohlížeči
        self._shown_coverage = None
        self._shown_probe: Any = None  # přiložená NDT sonda právě v prohlížeči
        self._shown_points: Any = None  # mapa kontaktních ploch návrhu poloh v prohlížeči
        self._shown_target: Any = None  # náhled cílového objemu NDT právě v prohlížeči
        self._shown_guides = None
        self._shown_plan: Any = None  # plán dráhy sondy a zóny právě v prohlížeči (klíč)
        self._assistant_lock: list[QAction] = []  # akce zamčené, dokud pracuje AI
        self.ai_busy = False  # AI asistent zrovna upravuje model
        self._view_actions: list[QAction] = []
        self.export_actions: list[QAction] = []

        if viewer_factory is None:
            from skodacad.gui.viewer import OccViewer

            viewer_factory = OccViewer
        self._viewer_factory = viewer_factory
        self.assembly_windows: list[AssemblyWindow] = []  # otevřené sestavy (P5.2B)
        self._assembly_runner: BackgroundRebuilder | None = None
        self.viewer = viewer_factory()
        self.viewer.selection_changed.connect(self._selection_changed)
        self.viewer.context_menu_requested.connect(self._show_context_menu)
        self.setCentralWidget(self.viewer)

        self._create_actions()
        self._build_side_panel()
        self._build_editor_panel()
        self._build_measure_panel()
        self._build_map_panel()
        self._build_section_panel()
        self._build_ndt_panel()
        self._build_audit_panel()
        self._build_design_panel()
        self._build_assistant_panel()
        self._build_menus()
        self.resize(1400, 860)
        self.resizeDocks([self.model_dock, self.editor_dock], [380, 360],
                         Qt.Orientation.Horizontal)
        self.resizeDocks([self.editor_dock, self.measure_dock], [420, 400],
                         Qt.Orientation.Vertical)
        self.tabifyDockWidget(self.measure_dock, self.map_dock)
        self.tabifyDockWidget(self.map_dock, self.section_dock)
        self.tabifyDockWidget(self.section_dock, self.ndt_dock)
        self.tabifyDockWidget(self.ndt_dock, self.audit_dock)
        self.tabifyDockWidget(self.audit_dock, self.design_dock)
        self.tabifyDockWidget(self.design_dock, self.assistant_dock)
        self.measure_dock.raise_()
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
            for key, schema in FEATURE_SCHEMAS.items() if schema.menu
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
        self.save_measurement_action = self._action("Uložit měření do modelu",
                                                    self.save_measurement)
        self.rename_measurement_action = self._action("Přejmenovat měření…",
                                                      self.rename_measurement)
        self.delete_measurement_action = self._action("Smazat měření",
                                                      self.delete_measurement)
        self.thickness_map_action = self._action("Mapa tloušťky stěny",
                                                 self.toggle_thickness_map, "M")
        self.thickness_map_action.setCheckable(True)
        self.thickness_map_action.setToolTip("Obarví celý díl podle tloušťky stěny (NDT) – "
                                             "červeně nejtenčí místa")
        self.section_action = self._action("Řez modelem", self.toggle_section, "R")
        self.assistant_action = self._action("AI asistent", self.show_assistant, "Ctrl+I")
        self.assistant_action.setToolTip("Úprava modelu podle popisu (Claude)")
        self.section_action.setCheckable(True)
        self.section_action.setToolTip("Rozřízne díl rovinou a ukáže, jak vypadá uvnitř "
                                       "(model se nemění)")
        self.section_face_action = self._action("Řez rovnoběžně s vybranou plochou",
                                                self.section_from_face)
        self.flip_section_action = self._action("Otočit stranu řezu", self.flip_section)
        self.flip_section_action.setIconText("Otočit stranu")
        self.export_section_action = self._action("Export řezu do DXF/SVG…",
                                                  self.export_section)
        self.export_section_action.setIconText("Export DXF/SVG…")
        self.export_map_action = self._action("Export bodů mapy do CSV…", self.export_map)
        self.export_map_action.setIconText("Export CSV…")
        self.export_map_action.setEnabled(False)
        for action, short in ((self.save_measurement_action, "Uložit do modelu"),
                              (self.rename_measurement_action, "Přejmenovat…"),
                              (self.delete_measurement_action, "Smazat")):
            action.setIconText(short)
            action.setToolTip(action.text())
            action.setEnabled(False)

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
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
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
        self.feature_editor.guide_selected.connect(lambda _row: self._refresh_guides())
        self.feature_editor.wall_panel.requested.connect(self.inspect_loft_wall)
        self.feature_editor.wall_panel.selected.connect(lambda _row: self._show_measure_line(None))
        self.feature_editor.invalid.connect(
            lambda message: self.statusBar().showMessage(message, 10000))
        self.editor_dock = self._add_dock("Úprava prvku", "editor_dock", self.feature_editor,
                                          Qt.DockWidgetArea.RightDockWidgetArea)

    def _build_measure_panel(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.measure_hint = QLabel(MEASURE_HINT)
        self.measure_hint.setWordWrap(True)
        self.measure_hint.setStyleSheet("color: #555;")
        layout.addWidget(self.measure_hint)
        self.measure_list = QListWidget()
        self.measure_list.setObjectName("measure_list")
        self.measure_list.setMaximumHeight(96)
        self.measure_list.currentRowChanged.connect(lambda _row: self._measure_row_changed())
        layout.addWidget(self.measure_list)
        buttons = QHBoxLayout()
        buttons.addWidget(self._tool_button(self.save_measurement_action))
        buttons.addStretch()
        layout.addLayout(buttons)

        saved_box = QGroupBox("Uložená měření (počítají se při každé změně)")
        saved_layout = QVBoxLayout(saved_box)
        self.saved_list = QListWidget()
        self.saved_list.setObjectName("saved_measurements")
        self.saved_list.currentRowChanged.connect(lambda _row: self._saved_row_changed())
        self.saved_list.itemDoubleClicked.connect(lambda _item: self.rename_measurement())
        saved_buttons = QHBoxLayout()  # nad seznamem, aby byla vidět i na malé obrazovce
        for action in (self.rename_measurement_action, self.delete_measurement_action):
            saved_buttons.addWidget(self._tool_button(action))
        saved_buttons.addStretch()
        saved_layout.addLayout(saved_buttons)
        self.saved_list.setMinimumHeight(60)
        saved_layout.addWidget(self.saved_list)
        layout.addWidget(saved_box, stretch=1)
        drawing_box = QGroupBox("Příprava kót výkresu")
        drawing_layout = QVBoxLayout(drawing_box)
        note = QLabel("Pracovní výkres vyžaduje kontrolu před výrobou. Průměr a poloměr "
                      "lze navázat na válcovou plochu otvoru vytvořeného jednou kruhovou skicou; "
                      "vzdálenost na dvě rovnoběžné plochy obdélníkového vysunutí.")
        note.setWordWrap(True)
        drawing_layout.addWidget(note)
        preview_settings = QHBoxLayout()
        self.drawing_paper = QComboBox()
        self.drawing_paper.addItems(["A4", "A3"])
        self.drawing_scale = QComboBox()
        for label, value in (("1:1", 1), ("1:2", 0.5), ("1:5", 0.2),
                             ("1:10", 0.1), ("2:1", 2), ("5:1", 5)):
            self.drawing_scale.addItem(label, value)
        # List a měřítko se ukládají s výkresem (Zpět/Znovu), okno je jen ukazuje.
        self.drawing_paper.currentIndexChanged.connect(self._drawing_sheet_changed)
        self.drawing_scale.currentIndexChanged.connect(self._drawing_sheet_changed)
        preview = QPushButton("Náhled pohledů")
        preview.clicked.connect(self.show_drawing_preview)
        preview_settings.addWidget(self.drawing_paper)
        preview_settings.addWidget(self.drawing_scale)
        preview_settings.addWidget(preview)
        export_drawing = QPushButton("Export PDF/DXF…")
        export_drawing.clicked.connect(self.export_drawing)
        preview_settings.addWidget(export_drawing)
        drawing_layout.addLayout(preview_settings)
        views_row = QHBoxLayout()
        views_row.addWidget(QLabel("Pohledy:"))
        self.drawing_view_boxes: dict[str, QCheckBox] = {}
        for label, key in (("Zepředu", "front"), ("Shora", "top"), ("Zprava", "right")):
            box = QCheckBox(label)
            box.setChecked(True)
            box.toggled.connect(self._drawing_views_changed)
            views_row.addWidget(box)
            self.drawing_view_boxes[key] = box
        views_row.addStretch()
        drawing_layout.addLayout(views_row)
        title_button = QPushButton("Popisové pole…")
        title_button.clicked.connect(self.edit_drawing_title_block)
        drawing_layout.addWidget(title_button)
        section_settings = QHBoxLayout()
        self.drawing_section_enabled = QCheckBox("Řez A–A")
        self.drawing_section_axis = QComboBox()
        self.drawing_section_axis.addItems(["X", "Y", "Z"])
        self.drawing_section_position = QDoubleSpinBox()
        self.drawing_section_position.setRange(-1000000, 1000000)
        self.drawing_section_position.setDecimals(3)
        self.drawing_section_position.setSuffix(" mm")
        self.drawing_section_flipped = QCheckBox("Otočit")
        save_section = QPushButton("Nastavit řez")
        save_section.clicked.connect(self.set_drawing_section)
        for widget in (self.drawing_section_enabled, self.drawing_section_axis,
                       self.drawing_section_position, self.drawing_section_flipped, save_section):
            section_settings.addWidget(widget)
        drawing_layout.addLayout(section_settings)
        self.drawing_kind = QComboBox()
        for label, kind, axis in (("Celkový rozměr X", "overall", "x"),
                                  ("Celkový rozměr Y", "overall", "y"),
                                  ("Celkový rozměr Z", "overall", "z"),
                                  ("Vzdálenost dvou ploch", "distance", ""),
                                  ("Průměr vybrané plochy", "diameter", ""),
                                  ("Poloměr vybrané plochy", "radius", "")):
            self.drawing_kind.addItem(label, (kind, axis))
        drawing_layout.addWidget(self.drawing_kind)
        drawing_buttons = QHBoxLayout()
        add = QPushButton("Přidat kótu")
        add.clicked.connect(self.add_drawing_dimension)
        remove = QPushButton("Odebrat kótu")
        remove.clicked.connect(self.remove_drawing_dimension)
        drawing_buttons.addWidget(add)
        drawing_buttons.addWidget(remove)
        drawing_layout.addLayout(drawing_buttons)
        self.drawing_list = QListWidget()
        self.drawing_list.setObjectName("drawing_dimensions")
        self.drawing_list.setMinimumHeight(70)
        drawing_layout.addWidget(self.drawing_list)
        self.drawing_list.currentRowChanged.connect(self._drawing_selection_changed)
        placement = QHBoxLayout()
        self.dimension_view = QComboBox()
        for label, key in (("Zepředu", "front"), ("Shora", "top"), ("Zprava", "right")):
            self.dimension_view.addItem(label, key)
        self.dimension_side = QComboBox()
        self.dimension_side.addItem("Dole / vlevo", "low")
        self.dimension_side.addItem("Nahoře / vpravo", "high")
        self.dimension_offset = QDoubleSpinBox()
        self.dimension_offset.setRange(1, 60)
        self.dimension_offset.setValue(6)
        self.dimension_offset.setSuffix(" mm")
        apply_placement = QPushButton("Umístit kótu")
        apply_placement.clicked.connect(self.set_drawing_dimension_placement)
        for widget in (self.dimension_view, self.dimension_side, self.dimension_offset,
                       apply_placement):
            placement.addWidget(widget)
        drawing_layout.addLayout(placement)
        tolerance_row = QHBoxLayout()
        self.dimension_upper = QDoubleSpinBox()
        self.dimension_lower = QDoubleSpinBox()
        for control in (self.dimension_upper, self.dimension_lower):
            control.setDecimals(6)
            control.setSuffix(" mm")
        self.dimension_upper.setRange(0, 1000000)
        self.dimension_lower.setRange(-1000000, 0)
        self.dimension_upper.setPrefix("Horní +")
        self.dimension_lower.setPrefix("Dolní ")
        save_tolerance = QPushButton("Nastavit toleranci")
        save_tolerance.clicked.connect(self.set_drawing_dimension_tolerance)
        remove_tolerance = QPushButton("Odebrat toleranci")
        remove_tolerance.clicked.connect(self.remove_drawing_dimension_tolerance)
        for widget in (self.dimension_upper, self.dimension_lower,
                       save_tolerance, remove_tolerance):
            tolerance_row.addWidget(widget)
        drawing_layout.addLayout(tolerance_row)
        layout.addWidget(drawing_box)
        self.measure_dock = self._add_dock("Měření", "measure_dock", panel,
                                           Qt.DockWidgetArea.RightDockWidgetArea)

    def _build_map_panel(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        top = QHBoxLayout()
        top.addWidget(self._tool_button(self.thickness_map_action))
        top.addWidget(self._tool_button(self.export_map_action))
        top.addStretch()
        layout.addLayout(top)
        form = QFormLayout()
        self.map_fields: dict[str, QLineEdit] = {}
        for key, label, hint in (
                ("limit", "Minimální tloušťka [mm]", "bez hranice"),
                ("step", "Krok bodů [mm]", "automaticky"),
                ("scale_max", "Horní mez škály [mm]", "nejčastější tloušťka")):
            field = QLineEdit()
            field.setObjectName(f"map_{key}")
            field.setPlaceholderText(hint)
            field.editingFinished.connect(lambda k=key: self._map_field_edited(k))
            self.map_fields[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        self.map_legend = QLabel()
        self.map_legend.setObjectName("map_legend")
        self.map_legend.setMinimumHeight(18)
        stops = ", ".join(f"stop:{t} rgb({int(r * 255)}, {int(g * 255)}, {int(b * 255)})"
                          for t, (r, g, b) in SCALE)
        self.map_legend.setStyleSheet("border: 1px solid #777; background: qlineargradient("
                                      f"x1:0, y1:0, x2:1, y2:0, {stops});")
        layout.addWidget(self.map_legend)
        self.map_scale_label = QLabel()
        layout.addWidget(self.map_scale_label)
        swatches = QLabel(f"{_swatch(BELOW_LIMIT)} pod minimem &nbsp; {_swatch(NO_MATERIAL)} "
                          "nejde změřit (u okraje jamky či hrany)")
        swatches.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(swatches)
        self.map_summary = QLabel()
        self.map_summary.setObjectName("map_summary")
        self.map_summary.setWordWrap(True)
        self.map_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.map_summary)
        layout.addStretch()
        self.map_dock = self._add_dock("Mapa tloušťky", "map_dock", panel,
                                       Qt.DockWidgetArea.RightDockWidgetArea)

    def _build_section_panel(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        top = QHBoxLayout()
        for action in (self.section_action, self.flip_section_action,
                       self.export_section_action):
            top.addWidget(self._tool_button(action))
        top.addStretch()
        layout.addLayout(top)
        form = QFormLayout()
        self.section_combo = QComboBox()
        self.section_combo.setObjectName("section_plane")
        for axis, name in AXIS_NAMES.items():
            self.section_combo.addItem(name[0].upper() + name[1:], axis)
        self.section_combo.addItem("Rovnoběžně s vybranou plochou", "face")
        self.section_combo.addItem("Kolmo na osu cíle (průřez svarem)", "target")
        self.section_combo.setCurrentIndex(self.section_combo.findData("Y"))  # výchozí podélně
        self.section_combo.activated.connect(lambda _index: self._section_kind_chosen())
        form.addRow("Rovina", self.section_combo)
        self.section_slider = QSlider(Qt.Orientation.Horizontal)
        self.section_slider.setObjectName("section_slider")
        self.section_slider.setRange(0, _SLIDER_STEPS)
        self.section_slider.valueChanged.connect(lambda _value: self._section_slider_moved())
        self.section_slider.sliderReleased.connect(self._section_slider_released)
        form.addRow("Poloha", self.section_slider)
        self.section_field = QLineEdit()
        self.section_field.setObjectName("section_position")
        self.section_field.editingFinished.connect(self._section_field_edited)
        self.section_position_label = QLabel("Poloha [mm]")
        form.addRow(self.section_position_label, self.section_field)
        self.section_range_label = QLabel()
        self.section_range_label.setStyleSheet("color: #555;")
        form.addRow("", self.section_range_label)
        layout.addLayout(form)
        self.section_info = QLabel()
        self.section_info.setObjectName("section_info")
        self.section_info.setWordWrap(True)
        self.section_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.section_info)
        layout.addStretch()
        self.section_dock = self._add_dock("Řez", "section_dock", panel,
                                           Qt.DockWidgetArea.RightDockWidgetArea)

    def _build_ndt_panel(self) -> None:
        """Panel NDT: studie nedestruktivní kontroly (stav po každém přepočtu)."""
        self.ndt_panel = NdtPanel(self)
        if hasattr(self.viewer, "probe_dragged"):
            self.viewer.probe_dragged.connect(self.ndt_panel.on_probe_dragged)
        if hasattr(self.viewer, "probe_rotated"):
            self.viewer.probe_rotated.connect(self.ndt_panel.on_probe_rotated)
        self.ndt_dock = self._add_dock("NDT", "ndt_dock", self.ndt_panel,
                                       Qt.DockWidgetArea.RightDockWidgetArea)
        self.ndt_action = self._action("Panel NDT studií", self.show_ndt)

    def _build_audit_panel(self) -> None:
        """Panel Předběžný NDT audit (etapa 14): všechny studie najednou, místa, zpráva."""
        self.audit_panel = AuditPanel(self)
        self.audit_dock = self._add_dock("NDT audit", "audit_dock", self.audit_panel,
                                         Qt.DockWidgetArea.RightDockWidgetArea)
        self.audit_dock.visibilityChanged.connect(  # záložka panelu přepnutá myší
            lambda visible: visible and self.audit_panel.refresh())
        self.audit_action = self._action("Předběžný NDT audit…", self.show_audit)
        self.audit_action.setToolTip("Spočítá všechny NDT studie jejich nastavením a složí "
                                     "zprávu o geometrickém posouzení (model se nemění)")

    def show_audit(self) -> None:
        self.audit_dock.show()
        self.audit_dock.raise_()
        self.resizeDocks([self.editor_dock, self.audit_dock], [220, 620],
                         Qt.Orientation.Vertical)
        self.audit_panel.refresh_items()
        self.audit_panel.refresh()

    def _build_design_panel(self) -> None:
        """Konstrukční srovnání NDT variant (etapa 15B)."""
        self.design_panel = DesignPanel(self)
        self.design_dock = self._add_dock("Konstrukční návrh", "design_dock",
                                          self.design_panel,
                                          Qt.DockWidgetArea.RightDockWidgetArea)
        self.design_dock.visibilityChanged.connect(
            lambda visible: visible and self.design_panel.refresh())
        self.design_action = self._action("Konstrukční návrh…", self.show_design)

    def show_design(self) -> None:
        self.design_dock.show()
        self.design_dock.raise_()
        self.resizeDocks([self.editor_dock, self.design_dock], [220, 620],
                         Qt.Orientation.Vertical)
        self.design_panel.refresh()

    def _refresh_probe(self) -> None:
        """Přiložená NDT sonda ve 3D: tělo v barvě výsledku a směr paprsku z výstupního bodu
        (u přímé sondy kolmo do materiálu)."""
        self._refresh_plan()
        self._refresh_coverage()
        placement = self.session.ndt_placement
        shown = placement if placement is not None else self.session.ndt_yoke
        rt = None
        # zdroj a detektor vybrané RT projekce (etapa 13) – také jako sonda; místo z auditu
        # ukazuje mapu, tu by deska detektoru zakryla
        if shown is None and self.audit_panel.focus() is None:
            rt = shown = self.ndt_panel.rt_box.drawing()
        if shown is self._shown_probe:
            return
        self._shown_probe = shown
        if placement is None:
            # jho MT (etapa 12) i projekce RT se kreslí stejně jako sonda
            drawing = rt if rt is not None else self.session.ndt_yoke_drawing()
            if drawing is None:
                self.viewer.hide_probe()
            else:
                body, state, start, end, text, outline = drawing
                self.viewer.show_probe(body, state, start, end, text, outline)
            return
        origin = placement.origin
        if placement.probe.kind == "straight":
            direction, reach = tuple(-v for v in placement.z_dir), 20.0
        else:
            direction, reach = placement.x_dir, 30.0
        end = tuple(o + d * reach for o, d in zip(origin, direction, strict=True))
        beam = self.session.ndt_beam
        points = beam.points if beam is not None else ()
        note = self.session.ndt_preview_note(self.session.ndt_placement_request[0])
        self.viewer.show_probe(placement.body, placement.state, origin, end,
                               (note + " " + placement.short).strip(), points)

    def _refresh_plan(self) -> None:
        """Plán dráhy vybrané studie ve 3D: úseky, přesuny, přestavení a zakázané zóny."""
        key, drawing = self.session.ndt_plan_drawing(self.ndt_panel.current_id())
        if key == self._shown_plan:
            return
        self._shown_plan = key
        if drawing is None:
            self.viewer.hide_plan()
        else:
            self.viewer.show_plan(*drawing)

    def _refresh_coverage(self) -> None:
        focus = self.audit_panel.focus()  # místo z předběžného auditu má přednost (etapa 14)
        found = None if focus is None else ("audit", id(focus[0].result),
                                            self.session.section_plane)
        if found is None:
            found = self.session.ndt_coverage
        if found is None:  # pokrytí plánu dráhy (při přehrávání narůstá)
            found = self.ndt_panel.plan_view()
        access = self.session.ndt_access
        mode = self.ndt_panel.access_map_mode()
        if found is None and access is not None and mode == "target":
            found = access.union  # návrh poloh: co pokryje kombinace (mapa pokrytí má přednost)
        pt_view = self.ndt_panel.pt_view() if found is None else None
        if pt_view is not None:  # mapa PT (etapa 11): klíč = mapa, kontrola a řez
            found = ("pt", id(pt_view[0]), pt_view[1], self.session.section_plane)
        mt_view = self.ndt_panel.mt_map_view() if found is None else None
        if mt_view is not None:  # mapa MT (etapa 12): klíč = mapa, pohled a řez
            found = ("mt", id(mt_view[0]), mt_view[1], self.session.section_plane)
        rt_view = self.ndt_panel.rt_box.map_view() if found is None else None
        if rt_view is not None:  # mapa RT (etapa 13): klíč = mapa, pohled a řez
            found = ("rt", id(rt_view[0]), rt_view[1], self.session.section_plane)
        points = (access, mode) if access is not None and mode == "contact" else None
        place = focus[1] if focus is not None else None
        if place is not None and place.center is not None:  # kulička ve středu místa auditu
            points = ("audit", place.id, place.center)
        if points != self._shown_points:
            self._shown_points = points
            if points is None:
                self.viewer.hide_points()
            elif points[0] == "audit":
                self.viewer.show_points([points[2]], [AUDIT_MARK])
            else:
                shown, colors, _states = self.session.ndt_access_points()
                self.viewer.show_points(shown, colors)
        if found is self._shown_coverage or (isinstance(found, tuple)
                                             and found == self._shown_coverage):
            return
        if found is None:
            self.viewer.hide_coverage_map()
            if self.session.map_visible:
                self._refresh_thickness_map()
        elif isinstance(found, tuple) and found[0] == "audit":
            nodes, triangles, colors, volume = self.session.ndt_audit_mesh(focus[0].study_id)
            section = self.session.section  # objem svaru uvnitř dílu: navrch, řez šedě
            self.viewer.show_coverage_map(
                nodes, triangles, colors,
                fill=section.faces if volume and section is not None else None, topmost=volume)
        elif isinstance(found, tuple) and found[0] == "mt":
            self.viewer.show_coverage_map(*self.session.ndt_mt_mesh(mt_view[1]))
        elif isinstance(found, tuple) and found[0] == "rt":
            section = self.session.section  # objem svaru uvnitř dílu: navrch, řez šedě
            volume = rt_view[0].kind == "volume"
            self.viewer.show_coverage_map(
                *self.session.ndt_rt_mesh(rt_view[1]),
                fill=section.faces if volume and section is not None else None, topmost=volume)
        elif isinstance(found, tuple):
            self.viewer.show_coverage_map(*self.session.ndt_pt_mesh(pt_view[1]))
        elif isinstance(found, VolumeCoverageMap):  # objem uvnitř dílu: navrch, řez šedě
            section = self.session.section
            self.viewer.show_coverage_map(*self.session.coverage_mesh(found),
                                          fill=section.faces if section is not None else None,
                                          topmost=True)
        else:
            self.viewer.show_coverage_map(*self.session.coverage_mesh(found))
        self._shown_coverage = found
        self._refresh_target()

    def _refresh_target(self) -> None:
        """Průhledný náhled cílového objemu (svaru) studie vybrané v panelu NDT; mapa pokrytí
        ho nahradí. Session tvar pamatuje, takže se kreslí znovu jen po změně."""
        study_id = self.ndt_panel.current_id()
        preview = (None if self._shown_coverage is not None
                   else self.session.ndt_target_preview(study_id))
        if preview is self._shown_target:
            return
        self._shown_target = preview
        if preview is None:
            self.viewer.hide_target()
        else:
            self.viewer.show_target(*preview)

    def show_ndt(self) -> None:
        self.ndt_dock.show()
        self.ndt_dock.raise_()
        # seznam studií a tlačítka potřebují místo – úprava prvku nad nimi se zmenší
        self.resizeDocks([self.editor_dock, self.ndt_dock], [220, 620],
                         Qt.Orientation.Vertical)

    def _build_assistant_panel(self) -> None:
        """Panel AI asistenta: rozhovor s Claude, který model upravuje (jeden krok Zpět)."""
        self.assistant_panel = AssistantPanel(self)
        self.assistant_dock = self._add_dock("AI asistent", "assistant_dock",
                                             self.assistant_panel,
                                             Qt.DockWidgetArea.RightDockWidgetArea,
                                             scroll=False)  # historie se posouvá sama

    def show_assistant(self) -> None:
        self.assistant_dock.show()
        self.assistant_dock.raise_()
        # rozhovor potřebuje místo – úprava prvku nad ním se zmenší
        self.resizeDocks([self.editor_dock, self.assistant_dock], [220, 620],
                         Qt.Orientation.Vertical)
        self.assistant_panel.prompt.setFocus()

    def set_assistant_busy(self, busy: bool) -> None:
        """Během práce AI se model ručně neupravuje (úpravy by se křížily) – zamknou se
        panely, nabídky i klávesové zkratky; pohledy na díl zůstanou."""
        self.ai_busy = busy
        for widget in (self.model_dock, self.editor_dock, self.ndt_dock, self.audit_dock,
                       self.design_dock, self.menuBar(), self.toolbar):
            widget.setEnabled(not busy)
        if busy:
            keep = {self.fit_action, self.assistant_action, *self._view_actions}
            self._assistant_lock = [a for a in self.findChildren(QAction)
                                    if a.parent() is self and a not in keep and a.isEnabled()]
            for action in self._assistant_lock:
                action.setEnabled(False)
        else:
            for action in self._assistant_lock:
                action.setEnabled(True)
            self._assistant_lock = []
            self._refresh_actions()

    def after_assistant_change(self) -> None:
        """AI změnila model (přes ModelSession) – obnovit strom, parametry a 3D."""
        if self._selected_id is not None and not any(
                f["id"] == self._selected_id for f in self.session.document.features):
            self._selected_id = None
        self._reload_all()

    def _add_dock(self, title: str, name: str, content: QWidget,
                  area: Qt.DockWidgetArea, scroll: bool = True) -> QDockWidget:
        if scroll:
            area_widget = QScrollArea()
            area_widget.setWidget(content)
            area_widget.setWidgetResizable(True)
            content = area_widget
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(content)
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
        toolbar = self.toolbar = self.addToolBar("Hlavní")
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)

        file_menu = bar.addMenu("&Soubor")
        for action in (self.new_action, self.open_action):
            file_menu.addAction(action)
            toolbar.addAction(action)
        file_menu.addAction(self._action("Nová sestava…", self.new_assembly_dialog))
        examples_menu = file_menu.addMenu("Otevřít ukázku")
        for path in sorted(self.examples_dir.glob("*.json")) if self.examples_dir else []:
            examples_menu.addAction(
                self._action(path.stem, lambda p=path: self.open_model(p, template=True))
            )
        ndt_folder = self.examples_dir / "ndt" if self.examples_dir else None
        for title, folder in (("NDT – referenční díly", ndt_folder),
                              ("NDT – cílové objemy", ndt_folder / "cilove_objemy"
                               if ndt_folder else None)):
            ndt_examples = _reference_parts(folder) if folder is not None else []
            if ndt_examples:
                ndt_menu = examples_menu.addMenu(title)
                for label, path in ndt_examples:
                    ndt_menu.addAction(
                        self._action(label, lambda p=path: self.open_model(p, template=True))
                    )
        assemblies = (sorted((self.examples_dir / "sestavy").glob("*.json"))
                      if self.examples_dir else [])
        if assemblies:
            assembly_menu = examples_menu.addMenu("Sestavy")
            for path in assemblies:
                assembly_menu.addAction(self._action(
                    Path(path).stem, lambda p=path: self.open_assembly(p, template=True)))
        examples_menu.setEnabled(not examples_menu.isEmpty())
        file_menu.addSeparator()
        import_action = self._action("Importovat STEP…", self.import_step_dialog)
        file_menu.addAction(import_action)
        toolbar.addAction(import_action)
        file_menu.addAction(self._action("Obnovit zdroj STEP…", self.restore_step_dialog))
        file_menu.addAction(self.save_action)
        toolbar.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        export_menu = file_menu.addMenu("Exportovat")
        for fmt, label in EXPORT_FORMATS:
            action = self._action(label + "…", lambda f=fmt: self.export_dialog(f))
            self.export_actions.append(action)
            export_menu.addAction(action)
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
        model_menu.addSeparator()
        model_menu.addAction(self.thickness_map_action)
        model_menu.addAction(self.export_map_action)
        model_menu.addSeparator()
        model_menu.addAction(self.section_action)
        model_menu.addAction(self.section_face_action)
        model_menu.addAction(self.flip_section_action)
        model_menu.addAction(self.export_section_action)
        model_menu.addSeparator()
        model_menu.addAction(self.assistant_action)
        model_menu.addAction(self.assistant_panel.settings_action)
        toolbar.addAction(self.rebuild_action)
        toolbar.addAction(self.thickness_map_action)
        toolbar.addAction(self.section_action)
        toolbar.addAction(self.assistant_action)
        toolbar.addSeparator()
        selection_menu = model_menu.addMenu("Z výběru ve 3D")
        self._fill_selection_menu(selection_menu)

        ndt_menu = bar.addMenu("&NDT")
        ndt_menu.addAction(self.ndt_action)
        ndt_menu.addAction(self.ndt_panel.new_action)
        ndt_menu.addSeparator()
        for item in (self.ndt_panel.confirm_action, self.ndt_panel.verify_action,
                     self.ndt_panel.duplicate_action, self.ndt_panel.delete_action):
            ndt_menu.addAction(item)
        ndt_menu.addSeparator()
        for item in (self.ndt_panel.probe_action, self.ndt_panel.place_action,
                     self.ndt_panel.drag_probe_action, self.ndt_panel.scan_action,
                     self.ndt_panel.remove_probe_action):
            ndt_menu.addAction(item)
        ndt_menu.addSeparator()
        for item in (self.ndt_panel.coverage_action, self.ndt_panel.clear_coverage_action,
                     self.ndt_panel.export_coverage_action):
            ndt_menu.addAction(item)
        ndt_menu.addSeparator()
        for item in (self.ndt_panel.access_action, self.ndt_panel.access_show_action,
                     self.ndt_panel.access_apply_action, self.ndt_panel.access_export_action):
            ndt_menu.addAction(item)
        ndt_menu.addSeparator()
        for item in (self.ndt_panel.plan_action, self.ndt_panel.plan_check_action,
                     self.ndt_panel.plan_zones_action, self.ndt_panel.plan_export_action):
            ndt_menu.addAction(item)
        ndt_menu.addSeparator()
        for item in (self.ndt_panel.pt_settings_action, self.ndt_panel.pt_action,
                     self.ndt_panel.pt_export_action):
            ndt_menu.addAction(item)
        ndt_menu.addSeparator()
        for item in (self.ndt_panel.mt_settings_action, self.ndt_panel.mt_action,
                     self.ndt_panel.mt_place_yoke_action, self.ndt_panel.mt_export_action):
            ndt_menu.addAction(item)
        ndt_menu.addSeparator()
        ndt_menu.addAction(self.audit_action)
        ndt_menu.addAction(self.design_action)

        view_menu = bar.addMenu("&Zobrazení")
        view_menu.addAction(self.fit_action)
        toolbar.addAction(self.fit_action)
        for key, (label, shortcut) in VIEW_LABELS.items():
            action = self._action(label, lambda k=key: self.viewer.set_standard_view(k), shortcut)
            self._view_actions.append(action)
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
        menu.addAction(self.save_measurement_action)
        menu.addAction(self.ndt_panel.new_action)
        menu.addAction(self.section_face_action)
        menu.addAction(self.clear_selection_action)

    # --- práce se souborem -------------------------------------------------------

    def new_model(self) -> bool:
        if not self._confirm_discard():
            return False
        self.session.new_document()
        self._selected_id = None
        self._reload_all(fit=True)
        self.assistant_panel.model_replaced()
        self.statusBar().showMessage("Nový díl – začni tlačítkem „Přidat prvek“ → Skica.", 10000)
        return True

    def open_model(self, path: str | Path, template: bool = False) -> bool:
        if is_assembly_file(path):  # sestava má vlastní okno, otevřený díl zůstane
            return self.open_assembly(path, template=template) is not None
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
        self.assistant_panel.model_replaced()
        return True

    def _assembly_window(self) -> AssemblyWindow:
        if self._runner is not None and self._assembly_runner is None:
            from skodacad.worker import BackgroundRebuilder

            self._assembly_runner = BackgroundRebuilder()  # vlastní – díl tu má svůj přepočet
        window = AssemblyWindow(self._viewer_factory, runner=self._assembly_runner,
                                user_dir=self.user_dir, open_part=self._open_part_of_assembly)
        self.assembly_windows = [w for w in self.assembly_windows if w.isVisible()]
        self.assembly_windows.append(window)
        return window

    def open_assembly(self, path: str | Path, template: bool = False) -> AssemblyWindow | None:
        """Otevře sestavu ve vlastním okně (ukázku jako šablonu – Uložit se zeptá kam)."""
        window = self._assembly_window()
        if not window.open_assembly(path, template=template):
            window.deleteLater()
            self.assembly_windows.remove(window)
            return None
        log.info("Otevřena sestava %s", path)
        window.show()
        return window

    def new_assembly_dialog(self) -> AssemblyWindow | None:
        window = self._assembly_window()
        window.new_dialog()
        if window.session.assembly is None:  # uživatel výběr místa zrušil
            window.deleteLater()
            self.assembly_windows.remove(window)
            return None
        window.show()
        return window

    def _open_part_of_assembly(self, path: Path) -> None:
        """*Otevřít díl* ze sestavy: díl se upravuje ve svém souboru v hlavním okně."""
        if self.open_model(path):
            self.show()
            self.raise_()
            self.activateWindow()

    def open_dialog(self) -> None:
        start = str(self.session.path.parent if self.session.path else self.user_dir)
        path, _ = QFileDialog.getOpenFileName(self, "Otevřít model", start,
                                              "Model ŠkodaCAD (*.json)", options=FILE_OPTIONS)
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
                                              "Model ŠkodaCAD (*.json)", options=FILE_OPTIONS)
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

    def import_step_dialog(self) -> None:
        """Zkontroluje STEP mimo okno, ukáže náhled a teprve pak změní model."""
        from skodacad.step_probe import StepProbeError
        from skodacad.step_task import StepTask
        from skodacad.worker import _shape_from

        document = self.session.document
        if document is None or document.features:
            self._error("Import STEP", "Nejdřív založ nový prázdný model.")
            return
        snapshot = document.to_dict()
        path, _ = QFileDialog.getOpenFileName(self, "Vybrat STEP", str(self.user_dir),
                                              "STEP (*.step *.stp)", options=FILE_OPTIONS)
        if not path:
            return
        try:
            task = StepTask(Path(path))
        except (StepProbeError, OSError, RuntimeError) as exc:
            self._error("Import STEP", str(exc))
            return
        progress = QProgressDialog("Kontroluji STEP…", "Zrušit", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        loop = QEventLoop(self)
        timer = QTimer(self)
        results = []
        canceled = []

        def poll() -> None:
            if (outcome := task.poll()) is not None:
                results.append(outcome)
                loop.quit()

        def cancel() -> None:
            canceled.append(True)
            loop.quit()

        progress.canceled.connect(cancel)
        timer.timeout.connect(poll)
        timer.start(75)
        progress.show()
        try:
            loop.exec()
        finally:
            timer.stop()
            progress.canceled.disconnect(cancel)
            progress.close()
            task.cancel()
        if canceled or not results:
            return
        outcome = results[0]
        if outcome.error:
            self._error("Import STEP", outcome.error)
            return
        data = outcome.source_bytes
        try:
            part = _shape_from(("Part", outcome.shape_bytes))
            facts = outcome.facts
            unit_name = {"millimetre": "milimetry", "metre": "metry", "inch": "palce"}[facts.unit]
            box = facts.bounds_mm
            size = (box[3] - box[0], box[4] - box[1], box[5] - box[2])
            self.viewer.show_part(part, fit=True)
            answer = QMessageBox.question(
                self, "Náhled importu STEP",
                f"Rozměry: {size[0]:g} × {size[1]:g} × {size[2]:g} mm\n"
                f"Objem: {facts.volume_mm3:g} mm³\n"
                f"Tělesa: {facts.solids}; jednotka zdroje: {unit_name}\n\n"
                "Původní parametrická historie ve STEP není dostupná.\n"
                "Vložit tento díl do modelu?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
        finally:
            self._shown_key = None
            self._refresh_all(fit=True)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.session.document is None or self.session.document.to_dict() != snapshot:
            self._error("Import STEP", "Model se během náhledu změnil. Zkus import znovu.")
            return
        self._apply(lambda: self.session.add_step_import(data, Path(path).name))

    def restore_step_dialog(self) -> None:
        """Obnoví obsah vybraného prvku pouze z totožného původního souboru."""
        from skodacad.step_probe import StepProbeError
        from skodacad.step_source import read_source_file

        if self._selected_id is None or self.session.document is None:
            self._error("Obnovení STEP", "Nejdřív ve stromu vyber import STEP.")
            return
        selected = self.session.feature(self._selected_id)
        if selected.get("type") != "step_import":
            self._error("Obnovení STEP", "Vybraný prvek není import STEP.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Najít původní STEP", str(self.user_dir),
                                              "STEP (*.step *.stp)", options=FILE_OPTIONS)
        if not path:
            return
        try:
            data = read_source_file(path)
        except StepProbeError as exc:
            self._error("Obnovení STEP", str(exc))
            return
        self._apply(lambda: self.session.restore_step_source(selected["id"], data))

    def export_dialog(self, fmt: str) -> None:
        if problem := self.session.model_problem:
            self._error("Export není dostupný", problem)
            return
        folder = self.session.path.parent if self.session.path else self.user_dir
        suggested = folder / f"{self._stem()}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.upper()}", str(suggested),
                                              f"{fmt.upper()} (*.{fmt})", options=FILE_OPTIONS)
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

    def edit_profile(self, profile: dict, new: bool = False) -> dict | None:
        """Otevře skicář nad obrysem; vrátí upravený obrys, nebo None (Zrušit).
        ``new`` = obrys nové skici (vloží se za vybraný prvek), jinak vybraná skica."""
        projection = self.session.sketch_projection(
            profile, feature_id=None if new else self._selected_id,
            after_id=self._selected_id if new else None)
        dialog = SketcherDialog(profile, self.session.solve_profile, self, projection)
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
        profile = self.edit_profile(empty_profile(), new=True)
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
        if feature_type in ("move_face", "face_diameter"):
            self.direct_edit_dialog(feature_type)
            return
        picked, point = list(self._picked), self.viewer.picked_point
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
        feature = self.session.feature(self._selected_id)
        if feature["type"] in ("move_face", "face_diameter"):
            key = "distance" if feature["type"] == "move_face" else "diameter"
            try:
                value = self.session._evaluate(feature[key])
            except (ValueError, KeyError):
                value = None
            self.direct_edit_dialog(feature["type"], value, self._selected_id)
            return
        picked = list(self._picked)
        point = getattr(self.viewer, "picked_point", None)
        if self._apply(lambda: self.session.apply_selection(self._selected_id, picked, replace,
                                                            point=point), structural=False):
            self._load_editor()

    def direct_edit_dialog(self, kind: str, value: float | None = None,
                           feature_id: str | None = None,
                           edited_feature: dict | None = None) -> bool:
        """Náhled nad kopií, potvrzení a vrácení zobrazení při zrušení."""
        dialog = DirectEditDialog(self, kind, list(self._picked), self.viewer.picked_point,
                                  value, feature_id, edited_feature)
        try:
            accepted = self._exec_dialog(dialog) == QDialog.DialogCode.Accepted
            preview = dialog.preview if accepted else None
        finally:
            dialog.deleteLater()
            self._shown_key = None
            self._refresh_all()
        if preview is None:
            return False
        new_id = []
        if not self._apply(lambda: new_id.append(self.session.apply_direct_edit(preview)),
                           structural=False):
            return False
        self._selected_id = new_id[0]
        self._reload_all()
        return True

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
        if feature["type"] in ("move_face", "face_diameter"):
            key = "distance" if feature["type"] == "move_face" else "diameter"
            if feature.get(key) != self.session.feature(feature_id).get(key):
                try:
                    value = self.session._evaluate(feature[key])
                except (ValueError, KeyError) as exc:
                    self._error("Úprava nejde provést", str(exc))
                    self._load_editor()
                    return
                self.direct_edit_dialog(feature["type"], value, feature_id, feature)
                self._load_editor()
                return
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
        section = self.session.section
        if (result, section) != self._shown_key or fit:  # kreslit znovu jen nový díl či řez
            self._picked = []  # → starý výběr ve 3D už neplatí
            part = self.session.display_part
            # Když těleso vznikne poprvé (nový díl), přizpůsobit pohled – jinak zůstane kamera.
            self.viewer.show_part(part, fit=fit or (part is not None and not self._had_part),
                                  accent=section.faces if section is not None else None)
            self._had_part = part is not None
            self._shown_key = (result, section)
            self._shown_map = None  # prohlížeč mapu s dílem smazal
            self._shown_coverage = None
            self._shown_points = None  # … i body mapy kontaktních ploch
            self._shown_probe = None  # … i sondu
            self._shown_target = None  # … i náhled cílového objemu
            self._shown_plan = None  # … i plán dráhy a zóny
            self._shown_guides = None
        self._refresh_actions()
        self._refresh_progress()
        self._update_highlight()
        self._refresh_saved_measurements()
        self._refresh_drawing_dimensions()
        self._refresh_drawing_sheet()
        self._refresh_drawing_section()
        self._refresh_thickness_map()
        self._refresh_section_panel()
        self._refresh_probe()
        self.ndt_panel.refresh()
        self.audit_panel.refresh()
        self.design_panel.refresh()
        self._refresh_loft_wall()
        self._refresh_guides()

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
            if self.session.computing:  # průběžná zpráva návrhu poloh – výpočet běží dál
                self.ndt_panel._show_access()
                self.ndt_panel._show_plan()
                self.ndt_panel._show_pt()
                self.ndt_panel._show_mt()
                self.ndt_panel.rt_box.refresh()
                self.ndt_panel.refresh_actions()
                self.audit_panel.show_progress()  # hotová studie auditu / průběh
                self.design_panel.refresh()  # hotové varianty a průběh návrhu
                self._refresh_progress()
                return
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
            (f"⏳ Měřím stěnu… {self.session.computing_seconds:.0f} s"
             if self.session.loft_wall_pending else
             f"⏳ Přepočítávám… {self.session.computing_seconds:.0f} s") if shown else "")
        for widget in (self.progress_label, self.progress_bar, self.stop_button):
            widget.setVisible(shown)
        self.stop_action.setEnabled(computing)
        if self.session.coverage_pending:
            self.ndt_panel._show_coverage()  # uplynulý čas výpočtu pokrytí v panelu
        if self.session.access_pending:
            self.ndt_panel._show_access()  # průběh návrhu poloh v panelu
        if self.session.plan_pending:
            self.ndt_panel._show_plan()  # průběh plánu dráhy v panelu
        if self.session.pt_pending:
            self.ndt_panel._show_pt()  # průběh mapy PT v panelu
        if self.session.mt_pending:
            self.ndt_panel._show_mt()  # průběh mapy MT v panelu
        if self.session.rt_pending:
            self.ndt_panel.rt_box.refresh()  # průběh projekcí RT v panelu
        if self.session.audit_pending:
            self.audit_panel.show_progress()  # průběh předběžného auditu
        if self.session.design_pending:
            self.design_panel.refresh()  # průběh konstrukčního návrhu

    def stop_rebuild(self) -> None:
        coverage = self.session.coverage_pending
        access = self.session.access_pending
        plan = self.session.plan_pending
        pt = self.session.pt_pending
        mt = self.session.mt_pending
        rt = self.session.rt_pending
        audit = self.session.audit_pending
        design = self.session.design_pending
        loft_wall = self.session.loft_wall_pending
        if self.session.cancel():
            self._pending_shown = False
            if loft_wall:
                self._refresh_all()
                self.statusBar().showMessage("Měření stěny zastaveno.", 10000)
                return
            if coverage or access or plan or pt or mt or rt or audit or design:
                # zastavený výpočet NDT – model se neměnil
                self._refresh_all()
                self.statusBar().showMessage(
                    "Konstrukční návrh zastaven – hotové varianty zůstaly." if design
                    else "Návrh poloh zastaven – hotové varianty zůstaly v tabulce." if access
                    else "Audit zastaven – spočítané studie zůstaly ve zprávě." if audit
                    else "Výpočet plánu dráhy zastaven – uložený plán zůstal beze změny."
                    if plan else "Výpočet mapy PT zastaven." if pt
                    else "Výpočet mapy MT zastaven." if mt
                    else "Výpočet projekcí RT zastaven." if rt
                    else "Výpočet mapy pokrytí zastaven.", 10000)
                return
            if self.session.map_visible and self.session.thickness_map is None:
                self.session.map_visible = False  # nedopočítaná mapa se vypne
            self._reload_all()
            self.statusBar().showMessage("Přepočet zastaven – model je zpět v posledním "
                                         "spočítaném stavu (Znovu změnu vrátí).", 10000)

    def _update_highlight(self) -> None:
        """Ve 3D zvýraznit, co používá prvek vybraný ve stromu (hrany zaoblení, skicu …),
        nebo kontrolovanou oblast studie vybrané v panelu NDT."""
        study_id = self.ndt_panel.current_id()
        if study_id is not None and (self.session.ndt_placement_request is not None
                                     or self.session.ndt_pt_map is not None
                                     or self.session.ndt_mt_map is not None
                                     or self.session.ndt_rt_map is not None
                                     or self.session.ndt_yoke is not None):
            shapes = []  # sonda, jho nebo mapa PT/MT/RT je hlavní – zvýraznění by je přebarvilo
        elif study_id is not None:
            shapes = self.session.ndt_highlight(study_id)
        elif self._selected_id:
            shapes = self.session.feature_highlight(self._selected_id)
        else:
            shapes = []
        self.viewer.highlight(shapes)
        self._refresh_target()

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
        # Cocoa AX retains references to cells. Resetting the model on an ordinary
        # edit can crash libqcocoa (macOS 27.2, also with Qt 6.11.3). Reuse rows by id.
        previous = {self.tree.topLevelItem(i).data(0, _FEATURE_ID): self.tree.topLevelItem(i)
                    for i in range(self.tree.topLevelItemCount())}
        result = self.session.result
        document = self.session.document
        old = {s.id: s for s in result.statuses} if result else {}
        if document is None or result is None and not self.session.computing:
            rows = []
        elif self.session.computing:  # strom podle modelu, stavy z posledního přepočtu
            rows = [(f["id"], describe(f), old[f["id"]].status if f["id"] in old else "pending",
                     "") for f in document.features]
            if self._pending_shown:
                rows = [(key, label, "pending", "Přepočítává se…") for key, label, _, _ in rows]
        else:
            rows = [(s.id, s.label, s.status, s.message) for s in result.statuses]
        chosen = None
        for index, (key, label, status, message) in enumerate(rows):
            text = f"{_STATUS_ICONS[status]}  {label}"
            if status == "ok" and message:
                text = f"{_STATUS_ICONS[status]}  {message} — {label}"
            item = previous.pop(key, None)
            if item is None:
                item = QTreeWidgetItem()
                item.setData(0, _FEATURE_ID, key)
            position = self.tree.indexOfTopLevelItem(item)
            if position != index:
                if position >= 0:
                    self.tree.takeTopLevelItem(position)
                self.tree.insertTopLevelItem(index, item)
            if item.text(0) != text:
                item.setText(0, text)
            item.setForeground(0, _STATUS_COLORS[status])
            item.setToolTip(0, message or key)
            if key == self._selected_id:
                chosen = item
        for item in previous.values():
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        if self.tree.currentItem() is not chosen:
            self.tree.setCurrentItem(chosen)
        if self._selected_id not in {row[0] for row in rows}:
            self._selected_id = None
        self.tree.blockSignals(False)
        problem = self.session.model_problem if document is not None else ""
        self.error_label.setText(problem)
        self.error_label.setVisible(bool(problem))

    def _refresh_actions(self) -> None:
        for action in self.export_actions:
            action.setEnabled(not self.session.model_problem and not self.ai_busy)
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
        self.audit_panel.refresh_actions()
        self.design_panel.refresh()
        for action in self._assistant_lock:  # AI pracuje – ruční úpravy počkají
            action.setEnabled(False)

    def _refresh_selection_actions(self) -> None:
        info = self.session.selection_info(self._picked)
        has_part = (self.session.result is not None and self.session.result.part is not None
                    and not self.session.computing)  # výběr jen na hotovém dílu
        flat = info.faces > 0 and info.flat_faces == info.faces
        needs = {"variable_fillet": info.edges == 1 and info.faces == 0,
                 "fillet": info.edges > 0, "chamfer": info.edges > 0,  # skica a díra jdou
                 "sketch": info.faces == 1, "hole": info.faces == 1,  # i na šikmou a válcovou
                 "shell": flat, "move_face": info.faces == 1 and info.edges == 0,
                 "face_diameter": info.faces == 1 and info.edges == 0}
        for key, action in self.selection_actions.items():
            action.setEnabled(has_part and needs[key])
        document = self.session.document
        feature = next((copy.deepcopy(f) for f in document.features
                        if f["id"] == self._selected_id), None) if document else None
        kind = feature["type"] if feature else None
        texts = {"fillet": "Přidat vybrané hrany do: ", "chamfer": "Přidat vybrané hrany do: ",
                 "variable_fillet": "Nahradit hranu v: ",
                 "sketch": "Přesunout na vybranou plochu: ",
                 "hole": "Přidat díru v místě kliknutí do: ",
                 "shell": "Otevřít vybrané plochy v: ",
                 "move_face": "Převzít vybranou plochu do: ",
                 "face_diameter": "Převzít vybranou plochu do: "}
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
        if current is not None and self.ndt_panel.current_id() is not None:
            self.ndt_panel.select(None)  # zvýraznit prvek, ne oblast studie
        self._refresh_actions()
        self._load_editor()
        self._update_highlight()
        self._refresh_measure_list()

    def _load_editor(self) -> None:
        if self._selected_id is None or self.session.document is None:
            self.feature_editor.show_feature(None)
            self._refresh_guides()
            self._refresh_loft_wall()
            return
        features = self.session.document.features
        index = self.session.feature_index(self._selected_id)
        sketches = [(f["id"], describe(f)) for f in features[:index] if f["type"] == "sketch"]
        repeatable = [(f["id"], short_label(f)) for f in features[:index]
                      if f["type"] in REPEATABLE_FEATURES]
        self.feature_editor.show_feature(self.session.feature(self._selected_id), sketches,
                                         repeatable)
        self._refresh_guides()
        self._refresh_loft_wall()

    def _refresh_guides(self) -> None:
        form = self.feature_editor.form
        selected = 0
        if form is not None and form.data.get("type") == "guided_loft":
            selected = form.widget("guides").selected_index
        key = (id(self.session.result), self._selected_id, selected, self.session.computing)
        if key != self._shown_guides:
            data = (self.session.guided_loft_display(self._selected_id, selected)
                    if self._selected_id is not None else None)
            self.viewer.show_guides(data)
            self._shown_guides = key

    def inspect_loft_wall(self) -> None:
        if self._selected_id is None:
            return
        try:
            self._busy(lambda: self.session.inspect_loft_wall(self._selected_id))
        except DocumentError as exc:
            self._error("Stěnu nelze změřit", str(exc))
        self._refresh_all()

    def _refresh_loft_wall(self) -> None:
        panel = self.feature_editor.wall_panel
        fid = self._selected_id
        feature = (next((f for f in self.session.document.features if f["id"] == fid), None)
                   if self.session.document else None)
        if feature is None or feature.get("type") != "loft":
            panel.hide()
            panel.refresh(None, None, "", self.session.computing)
            return
        panel.show()
        report = self.session.loft_wall_report(fid)
        panel.refresh(fid, report, self.session.loft_wall_problem(fid), self.session.computing)
        panel.button.setEnabled(self.session.loft_wall_available(fid))

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
            f"Počet těles: {props.solids}",
        ]
        if self.session.model_problem:
            lines.insert(0, "Diagnostický náhled – hodnoty zobrazené geometrie:")
        self.props_label.setText("\n".join(lines))

    def _selection_changed(self, shapes: list) -> None:
        """Prohlížeč hlásí nový výběr ve 3D: popis do stavového řádku, měření, akce povolit."""
        self._picked = list(shapes)
        self._refresh_selection_actions()
        self.ndt_panel.refresh_actions()
        self.ndt_panel.show_pt_pick()
        self.ndt_panel.show_mt_pick()
        self.ndt_panel.rt_box.show_pick()
        self._refresh_measure_list()
        self.section_face_action.setEnabled(
            self.session.display_part is not None
            and self.session.selection_info(self._picked).faces == 1)
        info = self.session.selection_info(self._picked)
        if not info.text:
            self.statusBar().showMessage(HELP_HINT)
            return
        text = info.text
        if self._measured and (info.faces + info.edges == 2 or self.session.map_visible):
            text += f"  ·  {self._measured[0].text}"  # hlavní hodnota měření
        hints = []
        if info.edges:
            hints.append("pravým tlačítkem zaoblit nebo srazit")
        if info.faces == 1:
            hints.append("pravým tlačítkem skica nebo díra na ploše")
        hints.append("Ctrl+klik přidá další")
        self.statusBar().showMessage(f"{text}  ·  " + ", ".join(hints))

    # --- měření ----------------------------------------------------------------------

    def _refresh_measure_list(self) -> None:
        """Panel Měření: hodnoty pro aktuální výběr ve 3D (první je hned vybraná)."""
        self._measured = self.session.measure_selection(self._picked, self.viewer.picked_point)
        self.measure_list.blockSignals(True)
        self.measure_list.clear()
        for value in self._measured:
            self.measure_list.addItem(value.text)
        self.measure_list.blockSignals(False)
        info = self.session.selection_info(self._picked)
        if self._measured:
            self.measure_hint.setText("Vyber řádek – jeho čára se ukáže ve 3D. Uložené měření "
                                      "se přepočítá při každé změně modelu.")
        elif info.faces + info.edges > 2:
            self.measure_hint.setText("Měřit jde jednu nebo dvě věci – zruš část výběru "
                                      "(Ctrl+klik vybranou věc odebere).")
        else:
            self.measure_hint.setText(MEASURE_HINT)
        if self._measured:
            self.measure_list.setCurrentRow(0)  # → čára ve 3D
        else:
            self._show_measure_line(None)
        self._refresh_measure_actions()

    def _measure_row_changed(self) -> None:
        row = self.measure_list.currentRow()
        value = self._measured[row] if 0 <= row < len(self._measured) else None
        if value is not None:
            self.saved_list.blockSignals(True)
            self.saved_list.setCurrentRow(-1)
            self.saved_list.blockSignals(False)
        self._show_measure_line(value)
        self._refresh_measure_actions()

    def _saved_row_changed(self) -> None:
        result = self._current_saved()
        if result is not None:
            self.measure_list.blockSignals(True)
            self.measure_list.setCurrentRow(-1)
            self.measure_list.blockSignals(False)
            self._show_measure_line(result.value)
        self._refresh_measure_actions()

    def _show_measure_line(self, value: Value | None) -> None:
        lines = []
        if value is not None and value.points is not None:
            lines = [(*value.points, format_value(value.value, value.unit))]
        if self._selected_id is not None:
            lines += self.session.feature_direction(self._selected_id)
            lines += self.session.loft_wall_measurement(
                self._selected_id, self.feature_editor.wall_panel.selected_index)
        self.viewer.show_measurement(lines)

    def _refresh_saved_measurements(self) -> None:
        """Seznam uložených měření s hodnotami z posledního přepočtu."""
        document = self.session.document
        records = document.measurements if document is not None else []
        selected = self._current_saved_id()
        results = {m.id: m for m in self.session.measurements}
        self.saved_list.blockSignals(True)
        self.saved_list.clear()
        for record in records:
            result = results.get(record["id"])
            if self.session.computing or result is None:
                text = f"⏳ {record.get('name') or record['id']}"
            else:
                text = result.text
            item = QListWidgetItem(text)
            item.setData(_FEATURE_ID, record["id"])
            if result is not None and result.value is None:
                item.setForeground(_STATUS_COLORS["error"])
                item.setToolTip(result.error)
            elif result is not None:
                item.setForeground(_MEASURE_COLOR)
            self.saved_list.addItem(item)
            if record["id"] == selected:
                self.saved_list.setCurrentItem(item)
        self.saved_list.blockSignals(False)
        if self._current_saved() is not None and not self._measured:
            self._show_measure_line(self._current_saved().value)  # díl je nový – čáru znovu
        self._refresh_measure_actions()

    def _refresh_drawing_dimensions(self) -> None:
        document = self.session.document
        records = (document.drawing or {}).get("dimensions", []) if document else []
        selected = self.drawing_list.currentItem()
        selected_id = selected.data(_FEATURE_ID) if selected else None
        try:
            results = {item.id: item for item in self.session.drawing_dimensions()}
        except DocumentError:
            results = {}
        self.drawing_list.clear()
        for record in records:
            kind = record["kind"]
            label = (f"Celkový rozměr {record['axis'].upper()}" if kind == "overall"
                     else "Vzdálenost ploch" if kind == "distance"
                     else "Průměr otvoru" if kind == "diameter" else "Poloměr otvoru")
            result = results.get(record["id"])
            if result is None:
                text = f"⏳ {label}"
            elif result.value is None:
                text = f"✕ {label}: {result.error}"
            else:
                text = f"{label}: {format_value(result.value, 'mm')}"
                if "tolerance" in record:
                    tol = record["tolerance"]
                    text += f" (odchylky +{tol['upper']:g} / {tol['lower']:g} mm)"
            item = QListWidgetItem(f"{record['id']} — {text}")
            item.setData(_FEATURE_ID, record["id"])
            if result is not None and result.error:
                item.setForeground(_STATUS_COLORS["error"])
                item.setToolTip(result.error)
            self.drawing_list.addItem(item)
            if record["id"] == selected_id:
                self.drawing_list.setCurrentItem(item)

    def _refresh_drawing_sheet(self) -> None:
        paper, scale = (self.session.drawing_sheet() if self.session.document
                        else ("A4", 1))
        scales = [self.drawing_scale.itemData(i) for i in range(self.drawing_scale.count())]
        for combo, index in ((self.drawing_paper, self.drawing_paper.findText(paper)),
                             (self.drawing_scale, scales.index(scale))):
            combo.blockSignals(True)  # zobrazení uloženého stavu není nová změna
            combo.setCurrentIndex(index)
            combo.blockSignals(False)
        shown = self.session.drawing_views() if self.session.document else tuple(
            self.drawing_view_boxes)
        for key, box in self.drawing_view_boxes.items():
            box.blockSignals(True)
            box.setChecked(key in shown)
            box.blockSignals(False)

    def _drawing_sheet_changed(self, _index: int) -> None:
        if self.session.document is None:
            return
        try:
            self._busy(lambda: self.session.set_drawing_sheet(
                self.drawing_paper.currentText(), self.drawing_scale.currentData()))
        except DocumentError as exc:
            self._error("List výkresu nelze nastavit", str(exc))
        self._refresh_all()

    def _drawing_views_changed(self, _checked: bool) -> None:
        if self.session.document is None:
            return
        chosen = [key for key, box in self.drawing_view_boxes.items() if box.isChecked()]
        try:
            self._busy(lambda: self.session.set_drawing_views(chosen))
        except DocumentError as exc:
            self._error("Pohledy výkresu nelze nastavit", str(exc))
        self._refresh_all()

    def _refresh_drawing_section(self) -> None:
        document = self.session.document
        section = (document.drawing or {}).get("section") if document else None
        self.drawing_section_enabled.setChecked(section is not None)
        if section:
            self.drawing_section_axis.setCurrentText(section["axis"])
            self.drawing_section_position.setValue(section["position"])
            self.drawing_section_flipped.setChecked(section.get("flipped", False))

    def set_drawing_section(self) -> None:
        axis = (self.drawing_section_axis.currentText()
                if self.drawing_section_enabled.isChecked() else None)
        try:
            self._busy(lambda: self.session.set_drawing_section(
                axis, self.drawing_section_position.value(),
                self.drawing_section_flipped.isChecked()))
        except DocumentError as exc:
            self._error("Řez nelze nastavit", str(exc))
            return
        self._refresh_all()

    def edit_drawing_title_block(self) -> None:
        if self.session.document is None:
            return
        saved = (self.session.document.drawing or {}).get("title_block", {})
        dialog = QDialog(self)
        dialog.setWindowTitle("Popisové pole výkresu")
        form = QFormLayout(dialog)
        controls = {}
        for key, label, limit in (("number", "Číslo výkresu", 24), ("revision", "Revize", 12),
                                  ("author", "Autor", 24), ("date", "Datum", 16)):
            field = QLineEdit(saved.get(key, ""))
            field.setMaxLength(limit)
            form.addRow(label, field)
            controls[key] = field
        note = QLabel("Název dílu a materiál se přebírají z modelu.")
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if self._exec_dialog(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            self._busy(lambda: self.session.set_drawing_title_block(
                *(controls[key].text().strip() for key in
                  ("number", "revision", "author", "date"))))
        except DocumentError as exc:
            self._error("Popisové pole nelze uložit", str(exc))
            return
        self._refresh_all()

    def show_drawing_preview(self) -> None:
        from skodacad.drawing_annotations import annotations
        from skodacad.drawing_geometry import DrawingGeometryError
        from skodacad.drawing_section_mark import section_mark
        from skodacad.drawing_sheet import layout
        from skodacad.gui.drawing_preview import DrawingPreviewDialog

        try:
            self.session._require_computed("náhled výkresu")
            if self.session.document is None:
                raise DocumentError("Není otevřený žádný model.")
            paper, scale = self.session.drawing_sheet()
            sheet = self._busy(lambda: layout(self.session.document, self.session.result,
                                             paper=paper, scale=scale,
                                             views=self.session.drawing_views()))
            section_mark(sheet)
        except (DocumentError, DrawingGeometryError) as exc:
            self._error("Náhled výkresu nelze vytvořit", str(exc))
            return
        dimensions = self._busy(lambda: annotations(self.session.document, self.session.result,
                                                    sheet))
        try:
            from skodacad.drawing_export import _title_rows

            _title_rows(self.session.document, sheet, dimensions)
        except DocumentError as exc:
            self._error("Náhled výkresu nelze vytvořit", str(exc))
            return
        DrawingPreviewDialog(sheet, dimensions, self, document=self.session.document).exec()

    def export_drawing(self) -> None:
        from skodacad.drawing_annotations import annotations
        from skodacad.drawing_export import collision_notice, export
        from skodacad.drawing_geometry import DrawingGeometryError
        from skodacad.drawing_sheet import layout

        try:
            self.session._require_computed("export výkresu")
            if self.session.document is None:
                raise DocumentError("Není otevřený žádný model.")
            paper, scale = self.session.drawing_sheet()
            sheet = self._busy(lambda: layout(self.session.document, self.session.result,
                                             paper=paper, scale=scale,
                                             views=self.session.drawing_views()))
            dimensions = self._busy(lambda: annotations(self.session.document,
                                                         self.session.result, sheet))
            if dimensions.warnings:
                raise DocumentError(" ".join(dimensions.warnings))
        except (DocumentError, DrawingGeometryError, OSError, ValueError) as exc:
            self._error("Výkres nelze vyvézt", str(exc))
            return
        notice = collision_notice(dimensions)
        title = ("Export – možné překrytí kót, zkontroluj náhled" if notice
                 else "Export pracovního výkresu")
        if notice:
            self.statusBar().showMessage(notice, 30000)
            QApplication.processEvents()
        filename, chosen = QFileDialog.getSaveFileName(
            self, title, "vykres.pdf",
            "PDF – výkres (*.pdf);;DXF – výkres (*.dxf)", options=FILE_OPTIONS)
        if not filename:
            return
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(".dxf" if chosen.startswith("DXF") else ".pdf")
        try:
            self.session._require_computed("export výkresu")
            current = self._busy(lambda: annotations(self.session.document,
                                                      self.session.result, sheet))
            notice = collision_notice(current)
            if notice:
                self.statusBar().showMessage(notice, 30000)
                QApplication.processEvents()
            self._busy(lambda: export(self.session.document, self.session.result, sheet, path))
        except (DocumentError, DrawingGeometryError, OSError, ValueError) as exc:
            self._error("Výkres nelze vyvézt", str(exc))
            return
        self.statusBar().showMessage(
            f"Výkres uložen. {notice}" if notice
            else "Pracovní výkres uložen; zkontroluj jej před výrobou.", 30000 if notice else 10000)

    def _drawing_selection_changed(self, _row: int) -> None:
        item = self.drawing_list.currentItem()
        if item is None or self.session.document is None:
            return
        records = (self.session.document.drawing or {}).get("dimensions", [])
        record = next((d for d in records if d["id"] == item.data(_FEATURE_ID)), None)
        if record is None:
            return
        placement = record.get("placement") or {}
        axis = record.get("axis")
        if record["kind"] == "distance":
            axis = record["a"]["normal"][1]
        default_view = "top" if axis == "y" else "front"
        if record["kind"] in ("diameter", "radius"):
            features = self.session.document.features
            source = next((f for f in features if f.get("id") == record.get("origin")), {})
            sketch = next((f for f in features if f.get("id") == source.get("sketch")), {})
            plane = sketch.get("plane", "XY")
            default_view = ({"XY": "top", "XZ": "front", "YZ": "right"}.get(plane, "top")
                            if isinstance(plane, str) else "top")
        self.dimension_view.setCurrentIndex(self.dimension_view.findData(
            placement.get("view", default_view)))
        self.dimension_side.setCurrentIndex(self.dimension_side.findData(
            placement.get("side", "low")))
        self.dimension_offset.setValue(placement.get("offset", 6))
        tolerance = record.get("tolerance") or {}
        self.dimension_upper.setValue(tolerance.get("upper", 0))
        self.dimension_lower.setValue(tolerance.get("lower", 0))

    def set_drawing_dimension_placement(self) -> None:
        item = self.drawing_list.currentItem()
        if item is None:
            return
        try:
            self._busy(lambda: self.session.set_drawing_dimension_placement(
                item.data(_FEATURE_ID), self.dimension_view.currentData(),
                self.dimension_side.currentData(), self.dimension_offset.value()))
        except DocumentError as exc:
            self._error("Kótu nelze umístit", str(exc))
            return
        self._refresh_all()

    def _apply_drawing_tolerance(self, upper: float | None, lower: float | None) -> None:
        item = self.drawing_list.currentItem()
        if item is None:
            return
        try:
            self._busy(lambda: self.session.set_drawing_dimension_tolerance(
                item.data(_FEATURE_ID), upper, lower))
        except DocumentError as exc:
            self._error("Toleranci nelze nastavit", str(exc))
            return
        self._refresh_all()

    def set_drawing_dimension_tolerance(self) -> None:
        self._apply_drawing_tolerance(self.dimension_upper.value(), self.dimension_lower.value())

    def remove_drawing_dimension_tolerance(self) -> None:
        self._apply_drawing_tolerance(None, None)

    def add_drawing_dimension(self) -> None:
        kind, axis = self.drawing_kind.currentData()
        face = self._picked[0] if len(self._picked) == 1 else None
        try:
            self._busy(lambda: self.session.add_drawing_dimension(
                kind, axis=axis, face=face, faces=list(self._picked)))
        except DocumentError as exc:
            self._error("Kótu nelze přidat", str(exc))
            return
        self._refresh_all()

    def remove_drawing_dimension(self) -> None:
        item = self.drawing_list.currentItem()
        if item is None:
            return
        try:
            self._busy(lambda: self.session.remove_drawing_dimension(item.data(_FEATURE_ID)))
        except DocumentError as exc:
            self._error("Kótu nelze odebrat", str(exc))
            return
        self._refresh_all()

    def _current_saved_id(self) -> str | None:
        item = self.saved_list.currentItem()
        return item.data(_FEATURE_ID) if item is not None else None

    def _current_saved(self) -> SavedResult | None:
        measurement_id = self._current_saved_id()
        return next((m for m in self.session.measurements if m.id == measurement_id), None)

    def _refresh_measure_actions(self) -> None:
        row = self.measure_list.currentRow()
        value = self._measured[row] if 0 <= row < len(self._measured) else None
        self.save_measurement_action.setEnabled(value is not None and not self.session.computing)
        self.save_measurement_action.setText(
            f"Uložit měření do modelu: {value.text}" if value is not None
            else "Uložit měření do modelu")
        has_saved = self._current_saved_id() is not None
        self.rename_measurement_action.setEnabled(has_saved)
        self.delete_measurement_action.setEnabled(has_saved)

    def save_measurement(self) -> None:
        """Uloží vybranou hodnotu z panelu Měření do modelu."""
        row = self.measure_list.currentRow()
        if not 0 <= row < len(self._measured):
            return
        value = self._measured[row]
        picked, point = list(self._picked), self.viewer.picked_point
        try:
            measurement_id = self._busy(
                lambda: self.session.add_measurement(picked, value.kind, point))
        except DocumentError as exc:
            self._error("Měření nejde uložit", str(exc))
            return
        self._refresh_all()
        for i in range(self.saved_list.count()):
            if self.saved_list.item(i).data(_FEATURE_ID) == measurement_id:
                self.saved_list.setCurrentRow(i)
        self.statusBar().showMessage(f"Měření uloženo do modelu: {value.text}", 8000)

    def rename_measurement(self) -> None:
        measurement_id = self._current_saved_id()
        if measurement_id is None:
            return
        record = next(m for m in self.session.document.measurements
                      if m["id"] == measurement_id)
        name, ok = QInputDialog.getText(self, "Přejmenovat měření", "Název měření:",
                                        text=record.get("name", ""))
        if not ok:
            return
        try:
            self._busy(lambda: self.session.rename_measurement(measurement_id, name))
        except DocumentError as exc:
            self._error("Měření nejde přejmenovat", str(exc))
            return
        self._refresh_all()

    def delete_measurement(self) -> None:
        measurement_id = self._current_saved_id()
        if measurement_id is None:
            return
        self._busy(lambda: self.session.remove_measurement(measurement_id))
        self._show_measure_line(None)
        self._refresh_all()

    # --- mapa tloušťky stěny -------------------------------------------------------------

    def toggle_thickness_map(self) -> None:
        """Zapne/vypne barevnou mapu tloušťky stěny (počítá se na pozadí)."""
        visible = self.thickness_map_action.isChecked()
        if self.session.document is None:
            self.thickness_map_action.setChecked(False)
            return
        if visible:
            self.map_dock.raise_()
        self._busy(lambda: self.session.show_thickness_map(visible))
        self._refresh_all()

    def _map_field_edited(self, key: str) -> None:
        field = self.map_fields[key]
        document = self.session.document
        if document is None:
            return
        saved = (document.thickness_map or {}).get(key)
        if field.text().strip() == ("" if saved is None else format_parameter_value(saved)):
            field.setStyleSheet("")
            return  # beze změny
        try:
            self._busy(lambda: self.session.set_map_setting(key, field.text()))
        except DocumentError as exc:
            field.setStyleSheet(_INVALID_STYLE)
            field.setToolTip(str(exc))
            self.statusBar().showMessage(f"Mapa tloušťky: {exc}", 10000)
            return
        field.setStyleSheet("")
        field.setToolTip("")
        self._refresh_all()

    def _refresh_thickness_map(self) -> None:
        """Mapa ve 3D a panel: nastavení z modelu, legenda, souhrn."""
        session = self.session
        found = (session.thickness_map if session.map_visible and session.ndt_coverage is None
                 else None)
        if found is not self._shown_map:
            if found is None:
                self.viewer.hide_thickness_map()
            else:
                x, y, z = found.thinnest or (0.0, 0.0, 0.0)
                marker = ((x, y, z), f"min {number(found.minimum)} mm") \
                    if found.thinnest is not None else None
                nodes, triangles, colors = session.visible_map()
                section = session.section
                self.viewer.show_thickness_map(nodes, triangles, colors, marker,
                                               fill=section.faces if section else None)
            self._shown_map = found
        settings = session.map_settings if session.document is not None else None
        for key, field in self.map_fields.items():
            field.setEnabled(session.document is not None)
            if field.hasFocus() or settings is None:
                continue
            value = getattr(settings, key)
            text = "" if value is None else format_parameter_value(
                int(value) if float(value).is_integer() else value)
            if field.text() != text:
                field.setText(text)
        self.thickness_map_action.setChecked(session.map_visible)
        self.export_map_action.setEnabled(
            found is not None and not session.model_problem and not self.ai_busy)
        if found is not None:
            low, high = found.scale
            self.map_scale_label.setText(f"{number(low)} mm  ←  tenčí   ·   tlustší  →  "
                                         f"{number(high)} mm a víc")
            self.map_summary.setText("\n".join(found.summary()))
        elif session.map_visible and session.computing:
            self.map_scale_label.setText("")
            self.map_summary.setText("⏳ Počítám mapu tloušťky stěny…")
        elif session.map_visible and session.result is not None and session.result.map_error:
            self.map_scale_label.setText("")
            self.map_summary.setText(f"✕ {session.result.map_error}")
        else:
            self.map_scale_label.setText("")
            self.map_summary.setText("Zapni mapu tlačítkem nahoře (nebo klávesou M): díl se "
                                     "obarví podle tloušťky stěny. Kliknutím na místo ve 3D "
                                     "změříš přesnou tloušťku (panel Měření).")

    # --- řez modelem -----------------------------------------------------------------------

    def toggle_section(self) -> None:
        """Zapne/vypne řez (výchozí kolmo na osu Y uprostřed dílu)."""
        if not self.section_action.isChecked():
            self.session.clear_section()
        else:
            self.section_dock.raise_()
            axis = self.section_combo.currentData()
            try:
                self._busy(lambda: self.session.set_section_axis(
                    axis if axis in ("X", "Y", "Z") else "Y"))
            except DocumentError as exc:
                self.statusBar().showMessage(str(exc), 10000)
                self.section_action.setChecked(False)
                return
        self._refresh_all()

    def section_from_face(self) -> None:
        """Řez rovnoběžně s plochou vybranou ve 3D."""
        try:
            self._busy(lambda: self.session.set_section_face(self._picked,
                                                             self.viewer.picked_point))
        except DocumentError as exc:
            self._error("Řez nejde vést", str(exc))
            self._refresh_section_panel()
            return
        self.section_dock.raise_()
        self._refresh_all()

    def flip_section(self) -> None:
        if self.session.section_settings is None:
            return
        self._busy(self.session.flip_section)
        self._refresh_all()

    def export_section(self) -> None:
        """Obrys řezu jako 2D výkres (DXF pro CAD a laser, SVG jako obrázek)."""
        if problem := self.session.model_problem:
            self._error("Export řezu není dostupný", problem)
            return
        name = self.session.document.name if self.session.document else "rez"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export řezu", str(self.user_dir / f"{name}-rez.dxf"),
            "DXF – 2D výkres pro CAD (*.dxf);;SVG – obrázek do protokolu (*.svg)",
            options=FILE_OPTIONS)
        if not path:
            return
        try:
            written = self.session.export_section(path)
        except (DocumentError, OSError) as exc:
            self._error("Export řezu se nepovedl", str(exc))
            return
        self.statusBar().showMessage(f"Řez uložen: {written}", 8000)

    def _section_kind_chosen(self) -> None:
        kind = self.section_combo.currentData()
        if kind == "face":
            self.section_from_face()
            return
        if kind == "target":
            self.ndt_panel.cross_section()
            self._refresh_section_panel()
            return
        if self.session.section_settings is None and not self.section_action.isChecked():
            self.section_action.setChecked(True)
        try:
            self._busy(lambda: self.session.set_section_axis(kind))
        except DocumentError as exc:
            self.statusBar().showMessage(str(exc), 10000)
        self._refresh_all()

    def _section_slider_moved(self) -> None:
        """Táhnutí jen ukazuje číslo; řez se spočítá po puštění (u klávesnice hned)."""
        if self.session.section_settings is None:
            return
        low, high = self.session.section_range()
        value = low + (high - low) * self.section_slider.value() / _SLIDER_STEPS
        self.section_field.setText(format_parameter_value(round(value, 2)))
        if not self.section_slider.isSliderDown():
            self._apply_section_position(value)

    def _section_slider_released(self) -> None:
        if self.session.section_settings is None:
            return
        low, high = self.session.section_range()
        self._apply_section_position(
            low + (high - low) * self.section_slider.value() / _SLIDER_STEPS)

    def _section_field_edited(self) -> None:
        if self.session.section_settings is None:
            return
        text = self.section_field.text().strip().replace(",", ".")
        try:
            value = float(text)
        except ValueError:
            self.section_field.setStyleSheet(_INVALID_STYLE)
            self.statusBar().showMessage(f"„{text}“ není číslo – napiš polohu řezu v mm.",
                                         10000)
            return
        self.section_field.setStyleSheet("")
        if abs(value - self.session.section_settings.position) > 1e-9:
            self._apply_section_position(value)

    def _apply_section_position(self, value: float) -> None:
        if abs(value - self.session.section_settings.position) < 1e-9:
            return
        self._busy(lambda: self.session.set_section_position(value))
        self._refresh_all()

    def _refresh_section_panel(self) -> None:
        session = self.session
        settings = session.section_settings
        has_part = session.result is not None and session.result.part is not None
        self.section_action.setEnabled(has_part or settings is not None)
        self.section_action.setChecked(settings is not None)
        self.flip_section_action.setEnabled(settings is not None)
        self.export_section_action.setEnabled(
            session.section is not None and not session.model_problem and not self.ai_busy)
        self.section_face_action.setEnabled(
            has_part and session.selection_info(self._picked).faces == 1)
        for widget in (self.section_slider, self.section_field):
            widget.setEnabled(settings is not None)
        if settings is None:
            self.section_position_label.setText("Poloha [mm]")
            self.section_range_label.setText("")
            self.section_info.setText("Zapni řez tlačítkem nahoře (nebo klávesou R): díl se "
                                      "rozřízne a uvidíš ho uvnitř. Model se nemění. Na "
                                      "plochy řezu jde klikat a měřit.")
            return
        kind = "target" if settings.target is not None else settings.axis or "face"
        index = self.section_combo.findData(kind)
        if index >= 0 and self.section_combo.currentIndex() != index:
            self.section_combo.setCurrentIndex(index)
        try:
            low, high = session.section_range()
        except DocumentError:
            low, high = settings.position, settings.position
        word = ("Od začátku cíle" if settings.target is not None else "Hloubka"
                if settings.axis is None else f"Poloha {settings.axis}")
        self.section_position_label.setText(f"{word} [mm]")
        self.section_range_label.setText(f"od {number(low)} do {number(high)} mm")
        if not self.section_field.hasFocus():
            self.section_field.setText(format_parameter_value(round(settings.position, 2)))
        if not self.section_slider.isSliderDown() and high > low:
            self.section_slider.blockSignals(True)
            self.section_slider.setValue(round((settings.position - low) / (high - low)
                                               * _SLIDER_STEPS))
            self.section_slider.blockSignals(False)
        section = session.section
        if section is None:
            self.section_info.setText(f"✕ {session.section_error}")
            return
        where = describe_section(section.plane)
        if settings.target is not None:
            where = f"kolmo na osu cíle, {number(settings.position)} mm od jeho začátku"
        elif settings.axis is None:
            where = f"rovnoběžně s plochou, {number(settings.position)} mm pod ní"
        color = ("šedě pod mapou pokrytí" if isinstance(session.ndt_coverage, VolumeCoverageMap)
                 else "cihlově")
        self.section_info.setText(f"Řez {where}\nPlocha řezu: {number(section.area)} mm² "
                                  f"({color})\nKlikni na plochu řezu a změříš ji v panelu "
                                  "Měření.")

    def export_map(self) -> None:
        """Body mapy tloušťky do CSV (x, y, z, tloušťka) – pro Excel a protokol."""
        default = self.user_dir / f"{self.session.document.name or 'mapa'}-tloustka.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export bodů mapy tloušťky", str(default),
                                              "CSV pro Excel (*.csv)", options=FILE_OPTIONS)
        if not path:
            return
        try:
            written = self.session.export_thickness_map(path)
        except (DocumentError, OSError) as exc:
            self._error("Export mapy se nepovedl", str(exc))
            return
        self.statusBar().showMessage(f"Body mapy uložené: {written}", 8000)

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
            "<b>ŠkodaCAD</b> – osobní parametrický 3D CAD.<br>"
            f"{build_text()}<br>{libraries_text()}<br><br>"
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
        # Otevřené sestavy se zavřou s dílem (každá se zeptá na své neuložené změny).
        if any(window.isVisible() and not window.close() for window in self.assembly_windows):
            event.ignore()
            return
        if self._confirm_discard():
            self.assistant_panel.shutdown()  # rozpracovaná odpověď AI se zastaví
            self._poll_timer.stop()
            if self._runner is not None:
                self._runner.close()  # pomocné procesy přepočtu
            if self._assembly_runner is not None:
                self._assembly_runner.close()
            event.accept()
        else:
            event.ignore()
