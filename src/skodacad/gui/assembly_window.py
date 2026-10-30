"""Okno sestavy (P5.2B): strom komponent, poloha, kopie dílů ve 3D.

Okno nemodeluje – všechno jde přes ``AssemblySession`` (pravidlo 8 a 10), takže funguje
Zpět/Znovu a soubory dílů se nikdy nemění. S ``runner`` (pomocný proces jako u dílu) se
díly sestavy počítají na pozadí a okno nestojí; bez něj (testy) hned.
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
    QApplication,
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.assembly import AssemblyError
from skodacad.assembly_build import LABELS, AssemblyResult, Built, Cache, build_part
from skodacad.assembly_session import AssemblySession
from skodacad.document import DocumentError

log = logging.getLogger(__name__)

AXES = ("x", "y", "z")
FILTER = "Sestava ŠkodaCAD (*.json)"
PART_FILTER = "Díl nebo sestava ŠkodaCAD (*.json)"


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
        self._job_source: Any = None
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
        self._create_actions()
        self._build_menus()
        self.resize(1200, 760)
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
        self.tree.setColumnWidth(0, 150)
        self.tree.setColumnWidth(1, 130)
        self.tree.setMinimumWidth(360)
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        dock = QDockWidget("Komponenty", self)
        dock.setObjectName("assembly_components")
        dock.setWidget(self.tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_form(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.form_note = QLabel()
        self.form_note.setWordWrap(True)
        layout.addWidget(self.form_note)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow("Název", self.name_edit)
        self.position_edits = [QLineEdit() for _ in AXES]
        self.rotation_edits = [QLineEdit() for _ in AXES]
        for label, edits in (("Posun X / Y / Z [mm]", self.position_edits),
                             ("Otočení X / Y / Z [°]", self.rotation_edits)):
            row = QHBoxLayout()
            for edit in edits:
                edit.returnPressed.connect(self.apply_form)
                row.addWidget(edit)
            form.addRow(label, row)
        self.fixed_box = QCheckBox("Pevná (nehne ji tažení ani vazby)")
        self.fixed_box.toggled.connect(self._fixed_toggled)
        form.addRow("", self.fixed_box)
        layout.addLayout(form)
        turns = QGridLayout()
        self.turn_buttons: list[QPushButton] = []
        for column, axis in enumerate(AXES):
            for row, degrees in enumerate((-90, 90)):
                button = QPushButton(f"{axis.upper()} {degrees:+d}°")
                button.clicked.connect(lambda _c=False, a=axis, d=degrees: self.turn(a, d))
                turns.addWidget(button, row, column)
                self.turn_buttons.append(button)
        layout.addWidget(QLabel("Otočit kolem osy sestavy vedené počátkem dílu:"))
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
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)
        layout.addStretch(1)
        panel.setMaximumWidth(430)
        dock = QDockWidget("Komponenta", self)
        dock.setObjectName("assembly_component")
        dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _create_actions(self) -> None:
        self.new_action = self._action("Nová sestava…", self.new_dialog)
        self.open_action = self._action("Otevřít sestavu…", self.open_dialog)
        self.save_action = self._action("Uložit", self.save, "Ctrl+S")
        self.save_as_action = self._action("Uložit jako…", self.save_as, "Ctrl+Shift+S")
        self.undo_action = self._action("Zpět", self.undo, "Ctrl+Z")
        self.redo_action = self._action("Znovu", self.redo, "Ctrl+Y")
        self.insert_action = self._action("Vložit díl…", self.insert_dialog, "Ctrl+I")
        self.remove_action = self._action("Smazat komponentu", self.remove_selected, "Delete")
        self.reload_action = self._action("Načíst díly znovu", self.reload, "F5")

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&Soubor")
        for action in (self.new_action, self.open_action, self.save_action,
                       self.save_as_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self._action("Zavřít sestavu", self.close, "Ctrl+W"))
        edit_menu = bar.addMenu("Ú&pravy")
        for action in (self.undo_action, self.redo_action, self.insert_action,
                       self.remove_action, self.reload_action):
            edit_menu.addAction(action)
        toolbar = self.addToolBar("Sestava")
        toolbar.setObjectName("assembly_toolbar")
        toolbar.setMovable(False)
        for action in (self.open_action, self.save_action, self.insert_action,
                       self.undo_action, self.redo_action):
            toolbar.addAction(action)

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
            str(start / "sestava.json"), FILTER)
        if path:
            self.new_assembly(path if path.lower().endswith(".json") else path + ".json",
                              Path(path).stem)

    def open_dialog(self) -> None:
        start = self.session.path.parent if self.session.path else self.user_dir
        path, _ = QFileDialog.getOpenFileName(self, "Otevřít sestavu", str(start), FILTER)
        if path:
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
        path, _ = QFileDialog.getSaveFileName(self, "Uložit sestavu jako", str(start), FILTER)
        if not path:
            return False
        path = path if path.lower().endswith(".json") else path + ".json"
        if not self._run("Uložení se nepodařilo", lambda: self.session.save(path)):
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
                                              str(self.session.path.parent), PART_FILTER)
        if path:
            self.insert(path)

    def insert(self, path: str | Path) -> str | None:
        created: list[str] = []
        if self._run("Díl nejde vložit", lambda: created.append(self.session.insert(path))):
            self.select((created[0],))
            return created[0]
        return None

    def remove_selected(self) -> None:
        component = self._editable()
        if component is not None:
            self._selected = None
            self._run("Komponentu nejde smazat", lambda: self.session.remove(component))

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
                                              str(self.session.path.parent), PART_FILTER)
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

    # --- výběr ---------------------------------------------------------------------------

    def select(self, ids: tuple[str, ...] | None) -> None:
        self._selected = ids
        self._refresh_selection()

    def _tree_selected(self) -> None:
        items = self.tree.selectedItems()
        # Id jako JSON text: Qt by n-tici v datech položky převedl na seznam.
        ids = tuple(json.loads(items[0].data(0, Qt.ItemDataRole.UserRole))) if items else None
        if ids != self._selected:
            self._selected = ids
            self._refresh_selection()

    def _picked(self, shapes: list) -> None:
        """Klik ve 3D vybere komponentu, které kliknutá plocha nebo hrana patří."""
        result = self.session.result
        if not shapes or result is None:
            return
        for instance in result.instances:
            pieces = [*instance.part.faces(), *instance.part.edges()]
            if any(piece.wrapped.IsSame(shapes[0]) for piece in pieces):
                self.select(instance.ids)
                return

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
        self._job_source = waiting[0]
        self.runner.submit(self._job_source.document.to_dict())
        self._timer.start()

    def _poll(self) -> None:
        if self.runner is None or self._job_source is None:
            self._timer.stop()
            return
        finished = self.runner.poll()
        if finished is None:
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
        self.undo_action.setEnabled(self.session.can_undo)
        self.redo_action.setEnabled(self.session.can_redo)
        title = "Sestava – ŠkodaCAD"
        if has:
            title = (f"{self.session.assembly.name}{' *' if self.session.dirty else ''} – "
                     f"{self.session.path.name} – sestava ŠkodaCAD")
        self.setWindowTitle(title)

    def _fill_tree(self, result: AssemblyResult | None) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        items: dict[tuple[str, ...], QTreeWidgetItem] = {}
        for status in result.statuses if result is not None else []:
            parent = items.get(status.ids[:-1])
            state = "✓" if status.state == "ok" else f"✕ {LABELS[status.state]}"
            if status.state == "pending":
                state = "… počítá se"
            if status.warnings:
                state += " ⚠"
            name = status.label + (" (pevná)" if status.fixed else "")
            item = QTreeWidgetItem([name, status.source, state])
            tip = "\n".join([status.reason, *status.warnings]).strip()
            for column in range(3):
                item.setToolTip(column, tip)
            item.setData(0, Qt.ItemDataRole.UserRole, json.dumps(list(status.ids)))
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            items[status.ids] = item
        self.tree.expandAll()
        selected = items.get(self._selected) if self._selected else None
        if selected is not None:
            selected.setSelected(True)
        else:
            self._selected = None
        self.tree.blockSignals(False)

    def _refresh_selection(self) -> None:
        result = self.session.result
        component = self._editable()
        record = (self.session.assembly.component(component)
                  if component is not None else None)
        widgets = [self.name_edit, *self.position_edits, *self.rotation_edits,
                   self.fixed_box, self.apply_button, *self.turn_buttons,
                   self.relink_button, self.remove_action]
        for widget in widgets:
            widget.setEnabled(record is not None)
        self.open_part_button.setEnabled(self._selected is not None)
        self.fixed_box.blockSignals(True)
        if record is not None:
            self.name_edit.setText(record.name)
            for edit, value in zip(self.position_edits, record.position, strict=True):
                edit.setText(show_value(value))
            for edit, value in zip(self.rotation_edits, record.rotation, strict=True):
                edit.setText(show_value(value))
            self.fixed_box.setChecked(record.fixed)
            self.form_note.setText(f"Komponenta „{record.label}“ – soubor {record.path}")
        else:
            for edit in (self.name_edit, *self.position_edits, *self.rotation_edits):
                edit.clear()
            self.fixed_box.setChecked(False)
            self.form_note.setText(
                "Komponenta podsestavy – uprav ji v souboru podsestavy." if self._selected
                else "Vyber komponentu ve stromu nebo ve 3D.")
        self.fixed_box.blockSignals(False)
        shapes = []
        if result is not None and self._selected is not None:
            for instance in result.instances:
                if instance.ids[:len(self._selected)] == self._selected:
                    shapes.extend(edge.wrapped for edge in instance.part.edges())
        self.viewer.highlight(shapes)

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
        if self.computing:
            lines.append("Počítám díly sestavy na pozadí…")
        elif not result.complete:
            lines.append("NEÚPLNÁ sestava – součty platí jen pro nalezené díly.")
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
            event.accept()
        else:
            event.ignore()

    def changeEvent(self, event) -> None:  # noqa: N802
        """Po návratu do okna (díl upravený v hlavním okně) načte díly znovu."""
        super().changeEvent(event)
        from PySide6.QtCore import QEvent

        if (event.type() == QEvent.Type.ActivationChange and self.isActiveWindow()
                and self.session.assembly is not None and not self.computing):
            before = _signature(self.session.result)
            self.session.rebuild()
            if _signature(self.session.result) != before:
                self._refresh()


def _signature(result: AssemblyResult | None) -> tuple:
    """Co je ze sestavy vidět (stavy a otisky zdrojů) – bez porovnávání tvarů."""
    if result is None:
        return ()
    return tuple((s.ids, s.state, s.reason, s.fingerprint, tuple(s.warnings))
                 for s in result.statuses)
