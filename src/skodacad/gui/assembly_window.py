"""Okno sestavy (P5.2B, P5.3B, P5.4B): strom komponent a vazeb, poloha, kopie dílů ve 3D,
kontrola kolizí a vůlí, kusovník a export STEP.

Okno nemodeluje – všechno jde přes ``AssemblySession`` (pravidlo 8 a 10), takže funguje
Zpět/Znovu a soubory dílů se nikdy nemění. S ``runner`` (pomocný proces jako u dílu) se
díly sestavy počítají na pozadí a okno nestojí; bez něj (testy) hned.

Vazba (M12): klik na plochu první komponenty, Ctrl+klik na plochu druhé, *Přidat vazbu…*
nabídne jen vhodné druhy. Vazby jsou ve stromu pod komponentami se stavem; vybraná vazba
jde přejmenovat, u vzdálenosti změnit hodnota, a smazat.

Kontrola (K1–K12): *Zkontrolovat kolize a vůle* počítá na pozadí (s ``runner``), výsledek je
jen pohled a po změně sestavy neplatí. Klik na nález zvýrazní obě kopie a místo průniku,
*Přijmout kolizi…* ji zapíše s poznámkou (jeden krok Zpět). Kusovník je rozbalený po
souborech dílů; uložit CSV a exportovat STEP jde jen z úplné sestavy.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.assembly import CONSTRAINT_TYPES, AssemblyError
from skodacad.assembly_build import (
    CONSTRAINT_LABELS,
    LABELS,
    AssemblyResult,
    Built,
    Cache,
    build_part,
)
from skodacad.assembly_check import NDT_NOTE, labels, total_mass
from skodacad.assembly_session import AssemblySession
from skodacad.document import DocumentError
from skodacad.gui.assembly_access import request_project_access
from skodacad.gui.file_dialogs import FILE_OPTIONS
from skodacad.gui.viewer_views import VIEW_LABELS

log = logging.getLogger(__name__)

AXES = ("x", "y", "z")
FILTER = "Sestava ŠkodaCAD (*.json)"
PART_FILTER = "Díl nebo sestava ŠkodaCAD (*.json)"
MARK = (0.85, 0.10, 0.10)  # kulička v těžišti průniku vybrané kolize
GONE = "přijatá kolize – už není"


def is_assembly_file(path: str | Path) -> bool:
    """Je soubor sestava (podle „kind“, ne přípony)? Nečitelný soubor = ne."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("kind") == "assembly"


def parse_value(text: str) -> float | int | str:
    """Číslo (i s desetinnou čárkou), jinak výraz s parametry sestavy."""
    text = text.strip()
    if not text:
        raise AssemblyError("Pole polohy je prázdné – zadej číslo nebo výraz.")
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def show_value(value: Any) -> str:
    return str(value).replace(".", ",") if isinstance(value, float) else str(value)


class AssemblyWindow(QMainWindow):
    def __init__(self, viewer_factory: Callable[[], QWidget] | None = None,
                 runner: Any = None, user_dir: Path | None = None,
                 open_part: Callable[[Path], object] | None = None) -> None:
        super().__init__()
        self.runner = runner
        self.session = AssemblySession(Cache(builder=None if runner is not None else build_part))
        self.user_dir = user_dir or Path.home()
        self.open_part = open_part  # hlavní okno otevře soubor dílu
        self._selected: tuple[str, ...] | None = None
        self._constraint: str | None = None  # vybraná vazba (místo komponenty)
        self._picks: list[tuple[Any, Any]] = []  # vybrané tvary ve 3D a místo kliknutí
        self._job_source: Any = None
        self._check_job: tuple | None = None  # klíč sestavy při spuštění kontroly na pozadí
        self._check_progress = (0, 0)
        self._finding: dict[str, Any] | None = None  # vybraný nález kontroly
        self._finding_rows: list[dict[str, Any]] = []  # řádky tabulky nálezů
        self._bill_of: Any = None  # výsledek sestavy, ze kterého je tabulka kusovníku
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)

        if viewer_factory is None:
            from skodacad.gui.viewer import OccViewer

            viewer_factory = OccViewer
        self.viewer = viewer_factory()
        self.viewer.selection_changed.connect(self._picked)
        self.setCentralWidget(self.viewer)
        self._build_tree()
        self._build_form()
        self._build_checks()
        self._create_actions()
        self._build_menus()
        self.setMinimumSize(960, 600)
        self.resize(1200, 760)
        self.reset_layout()
        self._refresh()

    # --- stavba okna -----------------------------------------------------------------

    def _action(self, text: str, slot: Callable[[], object],
                shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False: slot())  # bez hodnoty „checked“
        return action

    def _build_tree(self) -> None:
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Komponenta", "Soubor", "Stav"])
        self.tree.setMinimumWidth(220)
        self.tree.setColumnWidth(0, 180)
        self.tree.setColumnWidth(1, 180)
        self.tree.setColumnWidth(2, 65)
        self.tree.setColumnHidden(1, True)  # zdroj je v detailu a bublině, lze jej zapnout
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        dock = self.tree_dock = QDockWidget("Komponenty", self)
        dock.setObjectName("assembly_components")
        dock.setWidget(self.tree)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_form(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.form_note = self._wrapped_label()
        layout.addWidget(self.form_note)
        layout.addWidget(QLabel("Název"))
        self.name_edit = QLineEdit()
        self.name_edit.setAccessibleName("Název komponenty")
        layout.addWidget(self.name_edit)
        self.position_edits = [QLineEdit() for _ in AXES]
        self.rotation_edits = [QLineEdit() for _ in AXES]
        coordinates = QGridLayout()
        coordinates.addWidget(QLabel("Osa"), 0, 0)
        coordinates.addWidget(QLabel("Posun [mm]"), 0, 1)
        coordinates.addWidget(QLabel("Otočení [°]"), 0, 2)
        for row, axis in enumerate(AXES, 1):
            coordinates.addWidget(QLabel(axis.upper()), row, 0)
            for column, edits in ((1, self.position_edits), (2, self.rotation_edits)):
                edit = edits[row - 1]
                edit.setMinimumWidth(90)
                edit.setAccessibleName(f"{'Posun' if column == 1 else 'Otočení'} {axis.upper()}")
                edit.returnPressed.connect(self.apply_form)
                coordinates.addWidget(edit, row, column)
        coordinates.setColumnStretch(1, 1)
        coordinates.setColumnStretch(2, 1)
        layout.addLayout(coordinates)
        self.fixed_box = QCheckBox("Pevná komponenta")
        self.fixed_box.setToolTip("Pevnou komponentu nepřesune tažení ani vazby.")
        self.fixed_box.toggled.connect(self._fixed_toggled)
        layout.addWidget(self.fixed_box)
        turns = QGridLayout()
        self.turn_buttons: list[QPushButton] = []
        for column, axis in enumerate(AXES):
            for row, degrees in enumerate((-90, 90)):
                button = QPushButton(f"{axis.upper()} {degrees:+d}°")
                button.clicked.connect(lambda _c=False, a=axis, d=degrees: self.turn(a, d))
                turns.addWidget(button, row, column)
                self.turn_buttons.append(button)
        layout.addWidget(self._wrapped_label("Otočit kolem osy sestavy vedené počátkem dílu:"))
        layout.addLayout(turns)
        self.apply_button = QPushButton("Použít polohu a název")
        self.apply_button.clicked.connect(self.apply_form)
        layout.addWidget(self.apply_button)
        buttons = QHBoxLayout()
        self.relink_button = QPushButton("Najít soubor…")
        self.relink_button.clicked.connect(self.relink_dialog)
        self.open_part_button = QPushButton("Otevřít díl")
        self.open_part_button.clicked.connect(self.open_selected_part)
        buttons.addWidget(self.relink_button)
        buttons.addWidget(self.open_part_button)
        layout.addLayout(buttons)
        self.pick_note = self._wrapped_label()
        layout.addWidget(self.pick_note)
        layout.addWidget(self._build_constraint_box())
        self.summary = self._wrapped_label()
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        layout.addStretch(1)
        panel.setMinimumWidth(280)
        scroll = self.component_scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(panel)
        dock = self.component_dock = QDockWidget("Komponenta", self)
        dock.setObjectName("assembly_component")
        dock.setWidget(scroll)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    @staticmethod
    def _wrapped_label(text: str = "") -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        return label

    def _build_constraint_box(self) -> QGroupBox:
        self.constraint_box = QGroupBox("Vazba")
        layout = QVBoxLayout(self.constraint_box)
        self.constraint_note = QLabel()
        self.constraint_note.setWordWrap(True)
        layout.addWidget(self.constraint_note)
        form = QFormLayout()
        self.constraint_name = QLineEdit()
        form.addRow("Název", self.constraint_name)
        self.constraint_value = QLineEdit()
        self.constraint_value.returnPressed.connect(self.apply_constraint)
        form.addRow("Vzdálenost [mm]", self.constraint_value)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        self.constraint_apply = QPushButton("Použít vazbu")
        self.constraint_apply.clicked.connect(self.apply_constraint)
        self.constraint_remove = QPushButton("Smazat vazbu")
        self.constraint_remove.clicked.connect(self.remove_selected)
        buttons.addWidget(self.constraint_apply)
        buttons.addWidget(self.constraint_remove)
        layout.addLayout(buttons)
        self.constraint_box.setVisible(False)
        return self.constraint_box

    def _build_checks(self) -> None:
        """Panel *Kontrola sestavy*: kolize a vůle, kusovník (K1–K7, K9)."""
        self.check_tabs = QTabWidget()
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(QLabel("Mez vůle [mm]"))
        self.clearance_edit = QLineEdit()
        self.clearance_edit.setMaximumWidth(70)
        self.clearance_edit.returnPressed.connect(self.apply_clearance)
        row.addWidget(self.clearance_edit)
        self.check_button = QPushButton("Zkontrolovat kolize a vůle")
        self.check_button.clicked.connect(self.run_check)
        self.stop_check_button = QPushButton("Zastavit")
        self.stop_check_button.clicked.connect(self.stop_check)
        self.accept_button = QPushButton("Přijmout kolizi…")
        self.accept_button.clicked.connect(self.accept_dialog)
        self.unaccept_button = QPushButton("Zrušit přijetí")
        self.unaccept_button.clicked.connect(self.unaccept_selected)
        for button in (self.check_button, self.stop_check_button, self.accept_button,
                       self.unaccept_button):
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        self.check_note = QLabel()
        self.check_note.setWordWrap(True)
        layout.addWidget(self.check_note)
        self.findings = self._table(["Nález", "Komponenty", "Hodnota", "Poznámka / důvod"])
        self.findings.itemSelectionChanged.connect(self._finding_selected)
        layout.addWidget(self.findings)
        self.check_tabs.addTab(page, "Kolize a vůle")
        page = QWidget()
        layout = QVBoxLayout(page)
        self.bill_note = QLabel()
        self.bill_note.setWordWrap(True)
        layout.addWidget(self.bill_note)
        self.bill_table = self._table(["Poz.", "Název", "Soubor", "Kusů", "Materiál",
                                       "Hmotnost celkem [g]", "Komponenty", "NDT v dílu"])
        layout.addWidget(self.bill_table)
        self.bill_button = QPushButton("Uložit kusovník CSV…")
        self.bill_button.clicked.connect(self.save_bill_dialog)
        layout.addWidget(self.bill_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.check_tabs.addTab(page, "Kusovník")
        dock = self.checks_dock = QDockWidget("Kontrola sestavy", self)
        dock.setObjectName("assembly_checks")
        dock.setWidget(self.check_tabs)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [230], Qt.Orientation.Vertical)  # 3D pohled zůstane velký

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(80)
        return table

    def _create_actions(self) -> None:
        self.new_action = self._action("Nová sestava…", self.new_dialog)
        self.open_action = self._action("Otevřít sestavu…", self.open_dialog)
        self.save_action = self._action("Uložit", self.save, "Ctrl+S")
        self.save_as_action = self._action("Uložit jako…", self.save_as, "Ctrl+Shift+S")
        self.undo_action = self._action("Zpět", self.undo, "Ctrl+Z")
        self.redo_action = self._action("Znovu", self.redo, "Ctrl+Y")
        self.insert_action = self._action("Vložit díl…", self.insert_dialog, "Ctrl+I")
        self.remove_action = self._action("Smazat komponentu", self.remove_selected, "Delete")
        self.constraint_action = self._action("Přidat vazbu…", self.add_constraint_dialog,
                                              "Ctrl+L")
        self.reload_action = self._action("Načíst díly znovu", self.reload, "F5")
        self.check_action = self._action("Zkontrolovat kolize a vůle", self.run_check, "F7")
        self.bill_action = self._action("Uložit kusovník CSV…", self.save_bill_dialog)
        self.export_action = self._action("Exportovat STEP…", self.export_dialog)
        self.fit_action = self._action("Celá sestava", self.viewer.fit_all, "F")
        self.view_actions = {
            key: self._action(label, lambda k=key: self.viewer.set_standard_view(k), shortcut)
            for key, (label, shortcut) in VIEW_LABELS.items()
        }
        for action in (*self.view_actions.values(), self.fit_action):
            action.setToolTip(f"{action.text()} ({action.shortcut().toString()})")

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&Soubor")
        for action in (self.new_action, self.open_action, self.save_action,
                       self.save_as_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addAction(self.bill_action)
        file_menu.addSeparator()
        file_menu.addAction(self._action("Zavřít sestavu", self.close, "Ctrl+W"))
        edit_menu = bar.addMenu("Ú&pravy")
        for action in (self.undo_action, self.redo_action, self.insert_action,
                       self.remove_action, self.constraint_action, self.reload_action):
            edit_menu.addAction(action)
        check_menu = bar.addMenu("&Kontrola")
        check_menu.addAction(self.check_action)
        check_menu.addAction(self.bill_action)
        view_menu = bar.addMenu("&Zobrazení")
        view_menu.addAction(self.fit_action)
        for action in self.view_actions.values():
            view_menu.addAction(action)
        view_menu.addSeparator()
        for dock, shortcut in ((self.tree_dock, "F9"), (self.component_dock, "F4"),
                               (self.checks_dock, "F8")):
            action = dock.toggleViewAction()
            action.setShortcut(QKeySequence(shortcut))
            view_menu.addAction(action)
        self.files_action = view_menu.addAction("Soubory ve stromu")
        self.files_action.setCheckable(True)
        self.files_action.toggled.connect(lambda checked: self.tree.setColumnHidden(1, not checked))
        self.reset_layout_action = self._action("Obnovit rozložení", self.reset_layout)
        view_menu.addAction(self.reset_layout_action)
        toolbar = self.toolbar = self.addToolBar("Sestava")
        toolbar.setObjectName("assembly_toolbar")
        toolbar.setMovable(False)
        for action in (self.open_action, self.save_action, self.insert_action,
                       self.constraint_action, self.check_action, self.undo_action,
                       self.redo_action):
            toolbar.addAction(action)
        toolbar.addSeparator()
        for key in ("top", "front", "iso"):
            toolbar.addAction(self.view_actions[key])
        toolbar.addAction(self.fit_action)

    def reset_layout(self) -> None:
        """Kompaktní panely; pouze rozložení, bez změny sestavy, výběru či kamery."""
        self.tree_dock.show()
        self.component_dock.show()
        self.checks_dock.hide()
        self.files_action.setChecked(False)
        self.tree.setColumnWidth(0, 180)
        self.tree.setColumnWidth(1, 180)
        self.tree.setColumnWidth(2, 65)
        self.resizeDocks([self.tree_dock, self.component_dock], [250, 300],
                         Qt.Orientation.Horizontal)

    # --- soubor -------------------------------------------------------------------------

    def open_assembly(self, path: str | Path, template: bool = False) -> bool:
        """Otevře sestavu; ``template`` (ukázka) = *Uložit* se zeptá kam, ukázka zůstane."""
        if not self._confirm_discard():
            return False
        if not self._run("Sestavu nejde otevřít", lambda: self.session.open(path), fit=True):
            return False
        self.template = template
        return True

    def new_assembly(self, path: str | Path, name: str = "Nová sestava") -> bool:
        if not self._confirm_discard():
            return False
        if not self._run("Sestavu nejde založit", lambda: self.session.new(path, name),
                         fit=True):
            return False
        self.template = False
        return True

    def new_dialog(self) -> None:
        start = self.session.path.parent if self.session.path else self.user_dir
        path, _ = QFileDialog.getSaveFileName(
            self, "Nová sestava – kam ji uložit (cesty k dílům se počítají od její složky)",
            str(start / "sestava.json"), FILTER, options=FILE_OPTIONS)
        if path:
            self.new_assembly(path if path.lower().endswith(".json") else path + ".json",
                              Path(path).stem)

    def open_dialog(self) -> None:
        start = self.session.path.parent if self.session.path else self.user_dir
        path, _ = QFileDialog.getOpenFileName(self, "Otevřít sestavu", str(start), FILTER,
                                              options=FILE_OPTIONS)
        if path and request_project_access(self, path):
            self.open_assembly(path)

    template = False  # otevřená ukázka – ukládá se jen jinam

    def save(self) -> bool:
        if self.session.assembly is None:
            return False
        if self.template:
            return self.save_as()
        return self._run("Uložení se nepodařilo", self.session.save)

    def save_as(self) -> bool:
        if self.session.assembly is None:
            return False
        start = (self.user_dir / self.session.path.name if self.template
                 else self.session.path or self.user_dir)  # ukázku ukládat mimo ukázky
        path, _ = QFileDialog.getSaveFileName(self, "Uložit sestavu jako", str(start), FILTER,
                                              options=FILE_OPTIONS)
        if not path:
            return False
        path = path if path.lower().endswith(".json") else path + ".json"
        copy_parts = self.template  # ukázka: díly se zkopírují k sestavě (samostatný projekt)
        if not self._run("Uložení se nepodařilo",
                         lambda: self.session.save(path, copy_parts=copy_parts)):
            return False
        self.template = False
        return True

    def reload(self) -> None:
        """Načte soubory dílů znovu (po úpravě dílu v hlavním okně)."""
        if self.session.assembly is not None:
            self._run("Sestavu nejde sestavit", self.session.rebuild)

    # --- úpravy -------------------------------------------------------------------------

    def insert_dialog(self) -> None:
        if self.session.assembly is None:
            self._error("Vložit díl", "Nejdřív založ nebo otevři sestavu.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Vložit díl nebo podsestavu",
                                              str(self.session.path.parent), PART_FILTER,
                                              options=FILE_OPTIONS)
        if path:
            self.insert(path)

    def insert(self, path: str | Path) -> str | None:
        created: list[str] = []
        if self._run("Díl nejde vložit", lambda: created.append(self.session.insert(path))):
            self.select((created[0],))
            return created[0]
        return None

    def remove_selected(self) -> None:
        """Smaže vybranou vazbu, jinak vybranou komponentu (i s jejími vazbami)."""
        if self._constraint is not None:
            constraint, self._constraint = self._constraint, None
            self._run("Vazbu nejde smazat",
                      lambda: self.session.remove_constraint(constraint))
            return
        component = self._editable()
        if component is not None:
            self._selected = None
            self._run("Komponentu nejde smazat", lambda: self.session.remove(component))

    # --- vazby (P5.3B) ------------------------------------------------------------------

    def add_constraint_dialog(self) -> None:
        """Vazba mezi dvěma naposledy vybranými plochami (klik, Ctrl+klik)."""
        if self.session.assembly is None:
            return
        if len(self._picks) < 2:
            self._error("Přidat vazbu", "Klikni na plochu první komponenty a s Ctrl na plochu "
                        "druhé komponenty, potom Přidat vazbu….")
            return
        (first, first_at), (second, second_at) = self._picks[-2:]
        try:
            a = self.session.reference_at(first, first_at)
            b = self.session.reference_at(second, second_at)
            if a["component"] == b["component"]:
                raise AssemblyError("Obě plochy patří ke stejné komponentě – druhou plochu "
                                    "vyber na jiné komponentě.")
            kinds = self.session.constraint_kinds(a, b)
            if not kinds:
                raise AssemblyError("Vazba potřebuje dvě rovinné plochy (dotyk, zarovnání, "
                                    "vzdálenost), nebo dvě válcové plochy (souosost).")
            default = self.session.gap(a, b) if "distance" in kinds else 0
        except (AssemblyError, DocumentError) as exc:
            self._error("Vazbu nejde přidat", str(exc))
            return
        kind = kinds[0]
        if len(kinds) > 1:
            labels = [CONSTRAINT_TYPES[k] for k in kinds]
            label, ok = QInputDialog.getItem(self, "Přidat vazbu", "Druh vazby:", labels, 0,
                                             False)
            if not ok:
                return
            kind = kinds[labels.index(label)]
        value = None
        if kind == "distance":
            text, ok = QInputDialog.getText(
                self, "Vzdálenost", "Vzdálenost v mm (číslo nebo výraz s parametry sestavy):",
                QLineEdit.EchoMode.Normal, show_value(default))
            if not ok:
                return
            try:
                value = parse_value(text)
            except AssemblyError as exc:
                self._error("Vazbu nejde přidat", str(exc))
                return
        self.add_constraint(kind, a, b, value)

    def add_constraint(self, kind: str, a: dict, b: dict, value: Any = None,
                       name: str = "") -> str | None:
        created: list[str] = []
        if self._run("Vazbu nejde přidat",
                     lambda: created.append(self.session.add_constraint(kind, a, b, value, name))):
            self._picks = []
            self.select_constraint(created[0])
            return created[0]
        return None

    def apply_constraint(self) -> None:
        constraint_id = self._constraint
        if constraint_id is None or self.session.assembly is None:
            return
        constraint = self.session.assembly.constraint(constraint_id)

        def work() -> None:
            value = (parse_value(self.constraint_value.text())
                     if constraint.type == "distance" else None)
            self.session.set_constraint(constraint_id, value=value,
                                        name=self.constraint_name.text())

        self._run("Vazbu nejde změnit", work)

    def select_constraint(self, constraint_id: str | None) -> None:
        self._constraint = constraint_id
        if constraint_id is not None:
            self._selected = None
        self._fill_tree(self.session.result)
        self._refresh_selection()

    def apply_form(self) -> None:
        component = self._editable()
        if component is None:
            return

        def work() -> None:
            position = [parse_value(edit.text()) for edit in self.position_edits]
            rotation = [parse_value(edit.text()) for edit in self.rotation_edits]
            self.session.begin_group()
            try:
                self.session.set_placement(component, position=position, rotation=rotation)
                self.session.rename(component, self.name_edit.text())
            finally:
                self.session.end_group()

        self._run("Polohu nejde použít", work)

    def turn(self, axis: str, degrees: float) -> None:
        component = self._editable()
        if component is not None:
            self._run("Komponentu nejde otočit",
                      lambda: self.session.turn(component, axis, degrees))

    def _fixed_toggled(self, checked: bool) -> None:
        component = self._editable()
        if component is not None and self.session.assembly.component(component).fixed != checked:
            self._run("Volbu Pevná nejde změnit",
                      lambda: self.session.set_fixed(component, checked))

    def relink_dialog(self) -> None:
        component = self._editable()
        if component is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Najít soubor komponenty",
                                              str(self.session.path.parent), PART_FILTER,
                                              options=FILE_OPTIONS)
        if path:
            self.relink(component, path)

    def relink(self, component: str, path: str | Path) -> bool:
        try:
            warning = self.session.relink_warning(component, path)
        except (AssemblyError, DocumentError) as exc:
            self._error("Soubor nejde použít", str(exc))
            return False
        if warning:
            answer = QMessageBox.question(
                self, "Jiný díl?", warning + "\n\nPoužít ho přesto?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                return False
        return self._run("Soubor nejde použít", lambda: self.session.relink(component, path))

    def open_selected_part(self) -> None:
        if self._selected is None or self.session.assembly is None:
            return
        try:
            file = self.session.find(self._selected[0])
        except AssemblyError as exc:
            self._error("Díl nejde otevřít", str(exc))
            return
        if file is None:
            self._error("Díl nejde otevřít", "Soubor komponenty se nenašel – použij "
                        "Najít soubor….")
            return
        if self.open_part is not None:
            self.open_part(file)

    def undo(self) -> None:
        if self.session.can_undo:
            self._run("Zpět se nepodařilo", self.session.undo)

    def redo(self) -> None:
        if self.session.can_redo:
            self._run("Znovu se nepodařilo", self.session.redo)

    # --- kontrola, kusovník, export (P5.4B) ------------------------------------------------

    def apply_clearance(self) -> None:
        if self.session.assembly is None:
            return
        try:
            value = float(self.clearance_edit.text().strip().replace(",", "."))
        except ValueError:
            self._error("Mez vůle", "Mez vůle musí být kladné číslo v mm.")
            self._refresh()
            return
        if value != self.session.assembly.checks.clearance:
            self._run("Mez vůle nejde změnit", lambda: self.session.set_clearance(value))

    def run_check(self) -> None:
        """Kolize a vůle všech dvojic kopií – s ``runner`` na pozadí, jinak hned."""
        if self.session.assembly is None or self.checking:
            return
        result = self.session.result
        if self.computing or result is None:
            self._error("Kontrola sestavy", "Díly se ještě počítají – zkontroluj sestavu, až "
                        "budou hotové.")
            return
        if not result.complete:
            self._error("Kontrola sestavy", "Kontrolu kolizí jde spustit jen u úplné sestavy – "
                        "nejdřív oprav chybějící komponenty, chyby dílů a vazby ve sporu.")
            return
        self.check_tabs.setCurrentIndex(0)
        self.checks_dock.show()
        self.resizeDocks([self.checks_dock], [230], Qt.Orientation.Vertical)
        if self.runner is None:
            self._run("Kontrola se nepodařila", self.session.check)
            return
        self._check_job = self.session.check_key()
        self._check_progress = (0, 0)
        self.runner.submit_assembly_check(self.session.assembly.to_dict(),
                                          str(self.session.path))
        self._timer.start()
        self._refresh_checks()

    def stop_check(self) -> None:
        if self._check_job is not None:
            self.runner.cancel()
            self._check_job = None
            self.statusBar().showMessage("Kontrola zastavena.", 10000)
            self._refresh_checks()

    @property
    def checking(self) -> bool:
        return self._check_job is not None

    def _check_finished(self, finished: Any) -> None:
        key, self._check_job = self._check_job, None
        if finished.error:
            self._error("Kontrola se nepodařila", finished.error)
        elif not self.session.store_check(finished.assembly_check, key):
            self.statusBar().showMessage("Sestava se během kontroly změnila – spusť kontrolu "
                                         "znovu.", 20000)
        self._refresh_checks()
        self._refresh_selection()

    def accept_dialog(self) -> None:
        finding = self._finding
        if finding is None or finding["kind"] not in ("collision", "changed"):
            return
        note, ok = QInputDialog.getText(
            self, "Přijmout kolizi",
            f"{finding['pair']}: průnik {finding['value']}\n"
            "Proč je kolize v pořádku (poznámka, např. „závit M3 – díra je jen vrták“):",
            QLineEdit.EchoMode.Normal, finding["note"])
        if ok:
            self.accept_collision(finding["a"], finding["b"], finding["volume"], note)

    def accept_collision(self, a: list[str], b: list[str], volume: float,
                         note: str = "") -> bool:
        return self._run("Kolizi nejde přijmout",
                         lambda: self.session.accept_collision(a, b, volume, note))

    def unaccept_selected(self) -> None:
        finding = self._finding
        if finding is not None and finding["kind"] in ("accepted", "changed", "gone"):
            self._run("Přijetí nejde zrušit",
                      lambda: self.session.unaccept_collision(finding["a"], finding["b"]))

    def save_bill_dialog(self) -> None:
        result = self.session.result
        if self.session.assembly is None or result is None:
            return
        if not result.complete:
            self._error("Kusovník", "Kusovník jde uložit jen z úplné sestavy – nejdřív oprav "
                        "chybějící komponenty, chyby dílů a vazby ve sporu.")
            return
        start = self.session.path.with_name(f"{self.session.path.stem}-kusovnik.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Uložit kusovník", str(start),
                                              "CSV (*.csv)", options=FILE_OPTIONS)
        if path:
            path = path if path.lower().endswith(".csv") else path + ".csv"
            if self._run("Kusovník se nepodařilo uložit",
                         lambda: self.session.write_bill(path)):
                self.statusBar().showMessage(f"Kusovník uložen: {path}", 20000)

    def export_dialog(self) -> None:
        result = self.session.result
        if self.session.assembly is None or result is None:
            return
        if not result.complete:
            self._error("Export STEP", "Export STEP jde jen z úplné sestavy – nejdřív oprav "
                        "chybějící komponenty, chyby dílů a vazby ve sporu.")
            return
        start = self.session.path.with_suffix(".step")
        if self.template:
            start = self.user_dir / start.name
        path, _ = QFileDialog.getSaveFileName(self, "Exportovat sestavu do STEP", str(start),
                                              "STEP (*.step *.stp)", options=FILE_OPTIONS)
        if path:
            path = path if path.lower().endswith((".step", ".stp")) else path + ".step"
            if self._run("Export STEP se nepodařil", lambda: self.session.export_step(path)):
                self.statusBar().showMessage(f"Sestava uložena do STEP: {path}", 20000)

    def _finding_selected(self) -> None:
        rows = self.findings.selectionModel().selectedRows()
        finding = self._finding_rows[rows[0].row()] if rows else None
        if finding is self._finding:
            return
        self._finding = finding
        if finding is not None:
            self._selected, self._constraint = None, None
            self.tree.blockSignals(True)
            self.tree.clearSelection()
            self.tree.blockSignals(False)
        self._refresh_finding_buttons()
        self._refresh_selection()

    def _refresh_finding_buttons(self) -> None:
        kind = self._finding["kind"] if self._finding else None
        self.accept_button.setEnabled(kind in ("collision", "changed") and not self.checking)
        self.unaccept_button.setEnabled(kind in ("accepted", "changed", "gone")
                                        and not self.checking)

    def _refresh_checks(self) -> None:
        assembly, result = self.session.assembly, self.session.result
        if not self.clearance_edit.hasFocus():
            self.clearance_edit.setText(show_value(assembly.checks.clearance)
                                        if assembly is not None else "")
        view = self.session.last_check() if not self.checking else None
        rows: list[dict[str, Any]] = []
        if view is not None:
            for finding in view.findings:
                value = (f"{finding.distance:.3f} mm" if finding.kind == "clearance"
                         else f"{finding.volume:.3f} mm³" if finding.volume is not None
                         else "?").replace(".", ",")
                rows.append({"kind": finding.kind, "label": finding.label,
                             "a": list(finding.a), "b": list(finding.b), "pair": finding.pair,
                             "value": value, "volume": finding.volume,
                             "center": list(finding.center) if finding.center else None,
                             "note": finding.note, "reason": finding.reason})
            for item in view.gone:
                rows.append({"kind": "gone", "label": GONE, "a": item.a, "b": item.b,
                             "pair": f"{labels(result, item.a)} × {labels(result, item.b)}",
                             "value": f"{item.volume:.3f} mm³".replace(".", ","),
                             "volume": item.volume, "center": None, "note": item.note,
                             "reason": "záznam můžeš zrušit"})
        if self.checking:
            done, total = self._check_progress
            note = (f"Kontroluji kolize a vůle na pozadí… {done} / {total} dvojic"
                    if total else "Kontroluji kolize a vůle na pozadí…")
        elif assembly is None:
            note = "Nejdřív založ nebo otevři sestavu."
        elif view is None:
            note = ("Kontrola zatím neproběhla nebo po změně sestavy neplatí – dej "
                    "Zkontrolovat kolize a vůle (F7).")
        else:
            lines = view.summary()
            note = lines[0] + (" Žádná nepřijatá kolize." if view.clean else
                               f" K řešení: {len(view.problems)}.")
        self.check_note.setText(f"{note}\n{NDT_NOTE}")
        self._finding_rows = rows
        self.findings.blockSignals(True)
        self.findings.setRowCount(len(rows))
        chosen = None
        for index, row in enumerate(rows):
            texts = [row["label"].capitalize(), row["pair"], row["value"],
                     " – ".join(part for part in (row["note"], row["reason"]) if part)]
            for column, text in enumerate(texts):
                self._set_cell(self.findings, index, column, text)
            if self._finding is not None and (row["a"], row["b"]) == (self._finding["a"],
                                                                      self._finding["b"]):
                chosen = index
        self.findings.clearSelection()
        if chosen is not None:
            self.findings.selectRow(chosen)
            self._finding = rows[chosen]
        else:
            self._finding = None
        self.findings.resizeColumnsToContents()
        self.findings.blockSignals(False)
        ready = (assembly is not None and result is not None and result.complete
                 and not self.computing)
        self.check_button.setEnabled(ready and not self.checking)
        self.check_action.setEnabled(ready and not self.checking)
        self.stop_check_button.setVisible(self.checking)
        self.clearance_edit.setEnabled(assembly is not None and not self.checking)
        self._refresh_finding_buttons()
        self.export_action.setEnabled(ready)
        self._refresh_bill(result, ready)

    def _refresh_bill(self, result: AssemblyResult | None, ready: bool) -> None:
        self.bill_button.setEnabled(ready)
        self.bill_action.setEnabled(ready)
        if result is self._bill_of and result is not None:
            return  # soubory dílů se čtou jen po novém sestavení
        self._bill_of = result
        rows = self.session.bill() if result is not None else []
        self.bill_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            grams = "?" if row.total_kg is None else f"{row.total_kg * 1000:.2f}"
            texts = [str(row.position), row.name, row.path, str(row.count), row.material,
                     grams.replace(".", ","), ", ".join(row.components),
                     f"{row.ndt} (jen pro díl)" if row.ndt else ""]
            for column, text in enumerate(texts):
                self._set_cell(self.bill_table, index, column, text)
        self.bill_table.resizeColumnsToContents()
        mass = total_mass(rows)
        text = (f"Řádků {len(rows)}, kusů {sum(row.count for row in rows)}, hmotnost celkem "
                + ("neznámá (materiál bez hustoty)" if mass is None
                   else f"{mass * 1000:.2f} g".replace(".", ",")))
        if result is not None and not result.complete:
            text += (" – NEÚPLNÁ sestava: chybějící díly v kusovníku nejsou, uložit jde jen "
                     "kusovník úplné sestavy.")
        self.bill_note.setText(f"{text}\n{NDT_NOTE}" if result is not None
                               else "Nejdřív založ nebo otevři sestavu.")

    @staticmethod
    def _set_cell(table: QTableWidget, row: int, column: int, text: str) -> None:
        """Update cells in place, preserving native accessibility references."""
        cell = table.item(row, column)
        if cell is None:
            cell = QTableWidgetItem()
            table.setItem(row, column, cell)
        if cell.text() != text:
            cell.setText(text)
        cell.setToolTip(text)

    # --- výběr ---------------------------------------------------------------------------

    def select(self, ids: tuple[str, ...] | None) -> None:
        self._selected = ids
        if ids is not None:
            self._constraint = None
            self._clear_finding()
        self._refresh_selection()

    def _clear_finding(self) -> None:
        self._finding = None
        self.findings.blockSignals(True)
        self.findings.clearSelection()
        self.findings.blockSignals(False)
        self._refresh_finding_buttons()

    def _tree_selected(self) -> None:
        items = self.tree.selectedItems()
        # Id jako JSON text: Qt by n-tici v datech položky převedl na seznam.
        data = json.loads(items[0].data(0, Qt.ItemDataRole.UserRole)) if items else None
        constraint = data.get("constraint") if isinstance(data, dict) else None
        ids = tuple(data) if isinstance(data, list) else None
        if ids != self._selected or constraint != self._constraint:
            self._selected, self._constraint = ids, constraint
            if ids is not None or constraint is not None:
                self._clear_finding()
            self._refresh_selection()

    def _picked(self, shapes: list) -> None:
        """Klik ve 3D vybere komponentu, které kliknutá plocha nebo hrana patří; vybrané
        plochy (s místem kliknutí) si okno pamatuje pro *Přidat vazbu…*."""
        known = self._picks
        self._picks = []
        for shape in shapes:
            previous = next((at for old, at in known if old.IsSame(shape)), None)
            self._picks.append((shape, previous if previous is not None
                                else getattr(self.viewer, "picked_point", None)))
        self._refresh_pick_note()
        result = self.session.result
        if not shapes or result is None:
            return
        for instance in result.instances:
            pieces = [*instance.part.faces(), *instance.part.edges()]
            if any(piece.wrapped.IsSame(shapes[0]) for piece in pieces):
                self.select(instance.ids)
                return

    def _refresh_pick_note(self) -> None:
        count = len(self._picks)
        self.constraint_action.setEnabled(self.session.assembly is not None and count >= 2)
        self.pick_note.setText(
            "Vazba: klikni na plochu první komponenty, s Ctrl na plochu druhé a dej "
            "Přidat vazbu… (Ctrl+L)." if count < 2
            else f"Vybrané plochy: {count} – Přidat vazbu… (Ctrl+L) spojí poslední dvě.")

    def _editable(self) -> str | None:
        """Vybraná komponenta, kterou jde upravit (nejvyšší úroveň); jinak None."""
        if self._selected is None or self.session.assembly is None:
            return None
        if len(self._selected) != 1:
            return None
        return self._selected[0]

    # --- výpočet na pozadí -------------------------------------------------------------

    def _start_next(self) -> None:
        if self.runner is None or self._job_source is not None:
            return
        waiting = list(self.session.cache.waiting.values())
        if not waiting:
            return
        if self._check_job is not None:  # díl se změnil – kontrola by už neplatila
            self.runner.cancel()
            self._check_job = None
            self.statusBar().showMessage("Kontrola se přerušila – díly sestavy se počítají "
                                         "znovu.", 20000)
        self._job_source = waiting[0]
        self.runner.submit(self._job_source.document.to_dict())
        self._timer.start()

    def _poll(self) -> None:
        if self.runner is None or (self._job_source is None and self._check_job is None):
            self._timer.stop()
            return
        finished = self.runner.poll()
        if finished is None:
            return
        if self._check_job is not None:
            if finished.update is not None:
                self._check_progress = finished.update[1]
                self._refresh_checks()
                return
            self._timer.stop()
            self._check_finished(finished)
            return
        source, self._job_source = self._job_source, None
        built = (Built(problem=finished.error) if finished.error
                 else Built.from_result(source.document, finished.result))
        self.session.cache.store(source, built)
        self.session.rebuild()
        if not self.session.cache.waiting:
            self._timer.stop()
        self._refresh(fit=self._fit_after)

    @property
    def computing(self) -> bool:
        return self._job_source is not None or bool(self.session.cache.waiting)

    # --- překreslení -------------------------------------------------------------------

    _fit_after = False

    def _run(self, title: str, work: Callable[[], object], fit: bool = False) -> bool:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.session.notice = ""  # hláška o přepočtu poloh platí jen do další úpravy
        try:
            work()
        except (AssemblyError, DocumentError, OSError) as exc:
            self._error(title, str(exc))
            self._refresh()
            return False
        finally:
            QApplication.restoreOverrideCursor()
        self._fit_after = fit
        self._refresh(fit=fit)
        return True

    def _refresh(self, fit: bool = False) -> None:
        result = self.session.result
        self._start_next()
        self._fill_tree(result)
        if result is not None and result.instances:
            self.viewer.show_part(result.compound(), fit=fit)
        else:
            self.viewer.show_part(None, fit=fit)
        self._refresh_selection()
        self._refresh_summary(result)
        has = self.session.assembly is not None
        for action in (self.save_action, self.save_as_action, self.insert_action,
                       self.reload_action):
            action.setEnabled(has)
        self._refresh_pick_note()
        self._refresh_checks()
        if self.session.notice:
            self.statusBar().showMessage(self.session.notice, 20000)
        self.undo_action.setEnabled(self.session.can_undo)
        self.redo_action.setEnabled(self.session.can_redo)
        title = "Sestava – ŠkodaCAD"
        if has:
            title = (f"{self.session.assembly.name}{' *' if self.session.dirty else ''} – "
                     f"{self.session.path.name} – sestava ŠkodaCAD")
        self.setWindowTitle(title)

    def _fill_tree(self, result: AssemblyResult | None) -> None:
        self.tree.blockSignals(True)
        # Cocoa accessibility keeps references to the selected table cells. Clearing
        # the whole model on every edit leaves those references dangling (macOS
        # 27.2 / Qt 6.11.2: SIGSEGV in libqcocoa while reading the AX hierarchy).
        # Keep existing rows and notify Qt of individual insertions/removals instead.
        previous: dict[str, QTreeWidgetItem] = {}

        def remember(item: QTreeWidgetItem) -> None:
            previous[item.data(0, Qt.ItemDataRole.UserRole)] = item
            for index in range(item.childCount()):
                remember(item.child(index))

        for index in range(self.tree.topLevelItemCount()):
            remember(self.tree.topLevelItem(index))

        def row(key: Any, texts: list[str], parent: QTreeWidgetItem | None,
                index: int) -> QTreeWidgetItem:
            encoded = json.dumps(key)
            item = previous.pop(encoded, None)
            created = item is None
            if item is None:
                item = QTreeWidgetItem()
                item.setData(0, Qt.ItemDataRole.UserRole, encoded)
            old_parent = item.parent()
            old_index = (old_parent.indexOfChild(item) if old_parent is not None
                         else self.tree.indexOfTopLevelItem(item))
            if item.treeWidget() is None or old_parent is not parent or old_index != index:
                if old_parent is not None:
                    old_parent.takeChild(old_index)
                elif old_index >= 0:
                    self.tree.takeTopLevelItem(old_index)
                if parent is None:
                    self.tree.insertTopLevelItem(index, item)
                else:
                    parent.insertChild(index, item)
            if created:
                item.setExpanded(True)
            for column, text in enumerate(texts):
                if item.text(column) != text:
                    item.setText(column, text)
            return item

        items: dict[tuple[str, ...], QTreeWidgetItem] = {}
        positions: dict[tuple[str, ...], int] = {}
        for status in result.statuses if result is not None else []:
            parent = items.get(status.ids[:-1])
            state = "✓" if status.state == "ok" else f"✕ {LABELS[status.state]}"
            if status.state == "pending":
                state = "… počítá se"
            if status.warnings:
                state += " ⚠"
            if status.freedom_text and status.freedom_text != "pevná":
                state += f" {status.freedom_text}"
            name = status.label + (" (pevná)" if status.fixed else "")
            parent_ids = status.ids[:-1]
            index = positions.get(parent_ids, 0)
            positions[parent_ids] = index + 1
            item = row(list(status.ids), [name, status.source, state], parent, index)
            tip = "\n".join([status.label, f"Soubor: {status.source}", state,
                             status.reason, *status.warnings]).strip()
            for column in range(3):
                item.setToolTip(column, tip)
            items[status.ids] = item
        constraints = [c for c in result.constraints if c.depth == 0] if result else []
        chosen = None
        if constraints:
            group = row(None, [f"Vazby ({len(constraints)})", "", ""], None,
                        positions.get((), 0))
            for index, constraint in enumerate(constraints):
                state = ("✓" if constraint.state == "ok"
                         else f"✕ {CONSTRAINT_LABELS[constraint.state]}")
                key = constraint.ids[-1]
                item = row({"constraint": key}, [constraint.label,
                           f"{constraint.type_label}: " + " ↔ ".join(constraint.components),
                           state], group, index)
                for column in range(3):
                    item.setToolTip(column, constraint.reason)
                if key == self._constraint:
                    chosen = item
        # Remove children before their parents, without resetting unrelated rows.
        for item in reversed(list(previous.values())):
            parent = item.parent()
            if parent is None:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
            else:
                parent.takeChild(parent.indexOfChild(item))
        selected = items.get(self._selected) if self._selected else None
        if selected is None:
            self._selected = None
        if chosen is None:
            self._constraint = None
        target = chosen if chosen is not None else selected
        for item in self.tree.selectedItems():
            if item is not target:
                item.setSelected(False)
        if self.tree.currentItem() is not target:
            self.tree.setCurrentItem(target)
        if target is not None:
            target.setSelected(True)
        self.tree.blockSignals(False)

    def _refresh_selection(self) -> None:
        result = self.session.result
        component = self._editable()
        record = (self.session.assembly.component(component)
                  if component is not None else None)
        widgets = [self.name_edit, *self.position_edits, *self.rotation_edits,
                   self.fixed_box, self.apply_button, *self.turn_buttons,
                   self.relink_button]
        for widget in widgets:
            widget.setEnabled(record is not None)
        self.remove_action.setEnabled(record is not None or self._constraint is not None)
        self.remove_action.setText("Smazat vazbu" if self._constraint is not None
                                   else "Smazat komponentu")
        self.open_part_button.setEnabled(self._selected is not None)
        self._refresh_constraint_box()
        self.fixed_box.blockSignals(True)
        if record is not None:
            self.name_edit.setText(record.name)
            for edit, value in zip(self.position_edits, record.position, strict=True):
                edit.setText(show_value(value))
            for edit, value in zip(self.rotation_edits, record.rotation, strict=True):
                edit.setText(show_value(value))
            self.fixed_box.setChecked(record.fixed)
            note = f"Komponenta „{record.label}“ – soubor {record.path}"
            try:
                freedom = result.status(component).freedom_text if result else ""
            except AssemblyError:
                freedom = ""
            if freedom:
                note += f"\nVazby: {freedom}"
            self.form_note.setText(note)
        else:
            for edit in (self.name_edit, *self.position_edits, *self.rotation_edits):
                edit.clear()
            self.fixed_box.setChecked(False)
            self.form_note.setText(
                "Komponenta podsestavy – uprav ji v souboru podsestavy." if self._selected
                else "Vybraná vazba – uprav ji níž." if self._constraint
                else "Vyber komponentu ve stromu nebo ve 3D.")
        self.fixed_box.blockSignals(False)
        shapes = []
        if self._constraint is not None and self.session.assembly is not None:
            shapes = self.session.constraint_faces(self._constraint)
        elif result is not None and self._selected is not None:
            for instance in result.instances:
                if instance.ids[:len(self._selected)] == self._selected:
                    shapes.extend(edge.wrapped for edge in instance.part.edges())
        elif result is not None and self._finding is not None:
            pair = (tuple(self._finding["a"]), tuple(self._finding["b"]))
            for instance in result.instances:
                if instance.ids in pair:
                    shapes.extend(edge.wrapped for edge in instance.part.edges())
        self.viewer.highlight(shapes)
        center = self._finding.get("center") if self._finding is not None else None
        if center and self._selected is None and self._constraint is None:
            self.viewer.show_points([tuple(center)], [MARK])
        else:
            self.viewer.hide_points()

    def _refresh_constraint_box(self) -> None:
        constraint_id = self._constraint
        if constraint_id is None or self.session.assembly is None:
            self.constraint_box.setVisible(False)
            return
        constraint = self.session.assembly.constraint(constraint_id)
        self.constraint_box.setVisible(True)
        self.constraint_name.setText(constraint.name)
        distance = constraint.type == "distance"
        self.constraint_value.setEnabled(distance)
        self.constraint_value.setText(show_value(constraint.value) if distance else "")
        try:
            status = self.session.result.constraint(constraint_id)
            state = (CONSTRAINT_LABELS[status.state]
                     + (f" – {status.reason}" if status.reason else ""))
        except (AssemblyError, AttributeError):
            state = ""
        labels = [self.session.assembly.component(c).label
                  if any(x.id == c for x in self.session.assembly.components) else c
                  for c in constraint.components]
        self.constraint_note.setText(f"{CONSTRAINT_TYPES[constraint.type].capitalize()}: "
                                     f"{labels[0]} ↔ {labels[1]}\nStav: {state}")

    def _refresh_summary(self, result: AssemblyResult | None) -> None:
        if result is None:
            self.summary.setText("Založ novou sestavu (Soubor → Nová sestava…) nebo otevři "
                                 "existující; pak Vložit díl….")
            return
        lines = [f"Komponent: {len(result.statuses)}, dílů ve 3D: {len(result.instances)}"]
        mass = result.mass_kg
        mass_text = "neznámá (materiál bez hustoty)" if mass is None else f"{mass * 1000:.2f} g"
        lines.append(f"Objem: {result.volume_mm3:.2f} mm³, hmotnost: {mass_text}"
                     .replace(".", ","))
        if result.constraints:
            done = sum(1 for c in result.constraints if c.state == "ok")
            lines.append(f"Vazby: {len(result.constraints)}, splněné {done}")
        if self.session.notice:
            lines.append(f"ℹ {self.session.notice}")
        if self.computing:
            lines.append("Počítám díly sestavy na pozadí…")
        elif not result.complete:
            lines.append("NEÚPLNÁ sestava – součty platí jen pro nalezené díly a splněné "
                         "vazby.")
        lines.extend(f"✕ {problem}" for problem in result.problems
                     if "díl se počítá" not in problem)
        lines.extend(f"⚠ {warning}" for warning in result.warnings)
        self.summary.setText("\n".join(lines))

    # --- pomocné -----------------------------------------------------------------------

    def _error(self, title: str, message: str) -> None:
        log.warning("%s: %s", title, message)
        QMessageBox.warning(self, title, message)

    def _confirm_discard(self) -> bool:
        if not self.session.dirty:
            return True
        answer = QMessageBox.question(
            self, "Neuložené změny", "Sestava má neuložené změny. Uložit je?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._confirm_discard():
            self._timer.stop()
            if self._check_job is not None:
                self.runner.cancel()
                self._check_job = None
            event.accept()
        else:
            event.ignore()

    def changeEvent(self, event) -> None:  # noqa: N802
        """Po návratu do okna (díl upravený v hlavním okně) načte díly znovu."""
        super().changeEvent(event)
        from PySide6.QtCore import QEvent

        if (event.type() == QEvent.Type.ActivationChange and self.isActiveWindow()
                and self.session.assembly is not None and not self.computing
                and not self.checking):
            before = _signature(self.session.result)
            self.session.rebuild()
            if _signature(self.session.result) != before:
                self._refresh()


def _signature(result: AssemblyResult | None) -> tuple:
    """Co je ze sestavy vidět (stavy a otisky zdrojů) – bez porovnávání tvarů."""
    if result is None:
        return ()
    return (tuple((s.ids, s.state, s.reason, s.fingerprint, tuple(s.warnings))
                  for s in result.statuses)
            + tuple((c.ids, c.state, c.reason) for c in result.constraints)
            + tuple(sorted(result.solved)))
