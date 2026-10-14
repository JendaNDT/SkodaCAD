"""Hlavní okno: 3D prohlížeč uprostřed, vlevo parametry, strom prvků a vlastnosti.

Okno nikdy nemodeluje samo – všechno jde přes ``ModelSession`` (jádro).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.gui.viewer_views import VIEW_LABELS
from skodacad.inspection import number
from skodacad.session import ModelSession, format_parameter_value

log = logging.getLogger(__name__)

HELP_HINT = ("Levé tlačítko: otáčení  ·  Prostřední/pravé: posun  ·  Kolečko: zoom  ·  "
             "Klik: výběr plochy/hrany  ·  Dvojklik: celý díl")

_STATUS_ICONS = {"ok": "✓", "error": "✕", "skipped": "·"}
_STATUS_COLORS = {"ok": QColor("#1b7f3b"), "error": QColor("#c0392b"), "skipped": QColor("#888")}
_INVALID_STYLE = "QLineEdit { border: 2px solid #c0392b; background: #fdecea; }"

EXPORT_FORMATS = [
    ("step", "STEP – pro jiné CAD programy"),
    ("stl", "STL – 3D tisk"),
    ("3mf", "3MF – 3D tisk (modernější)"),
]


class MainWindow(QMainWindow):
    def __init__(self, viewer_factory: Callable[[], QWidget] | None = None,
                 examples_dir: Path | None = None, user_dir: Path | None = None) -> None:
        super().__init__()
        self.session = ModelSession()
        self.examples_dir = examples_dir
        self.user_dir = user_dir or Path.home()
        self._param_fields: dict[str, QLineEdit] = {}

        if viewer_factory is None:
            from skodacad.gui.viewer import OccViewer

            viewer_factory = OccViewer
        self.viewer = viewer_factory()
        self.viewer.selection_changed.connect(self._show_selection)
        self.setCentralWidget(self.viewer)

        self._build_side_panel()
        self._build_menus()
        self.resize(1280, 800)
        self._refresh_all()
        self.statusBar().showMessage(HELP_HINT)

    # --- stavba okna ---------------------------------------------------------------

    def _build_side_panel(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: #555;")
        layout.addWidget(self.description_label)

        params_box = QGroupBox("Parametry (Enter = přepočítat)")
        self.params_form = QFormLayout(params_box)
        layout.addWidget(params_box)

        tree_box = QGroupBox("Strom prvků")
        tree_layout = QVBoxLayout(tree_box)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        tree_layout.addWidget(self.tree)
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

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        dock = QDockWidget("Model", self)
        dock.setObjectName("model_dock")
        dock.setWidget(scroll)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        dock.setMinimumWidth(330)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _action(self, text: str, slot: Callable[[], object],
                shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        return action

    def _build_menus(self) -> None:
        bar = self.menuBar()
        toolbar = self.addToolBar("Hlavní")
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)

        file_menu = bar.addMenu("&Soubor")
        open_action = self._action("Otevřít…", self.open_dialog, "Ctrl+O")
        file_menu.addAction(open_action)
        toolbar.addAction(open_action)
        examples_menu = file_menu.addMenu("Otevřít ukázku")
        for path in sorted(self.examples_dir.glob("*.json")) if self.examples_dir else []:
            examples_menu.addAction(
                self._action(path.stem, lambda p=path: self.open_model(p, template=True))
            )
        examples_menu.setEnabled(not examples_menu.isEmpty())
        file_menu.addSeparator()
        self.save_action = self._action("Uložit", self.save, "Ctrl+S")
        file_menu.addAction(self.save_action)
        toolbar.addAction(self.save_action)
        file_menu.addAction(self._action("Uložit jako…", self.save_as, "Ctrl+Shift+S"))
        export_menu = file_menu.addMenu("Exportovat")
        for fmt, label in EXPORT_FORMATS:
            export_menu.addAction(self._action(label + "…", lambda f=fmt: self.export_dialog(f)))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Konec", self.close, "Ctrl+Q"))

        model_menu = bar.addMenu("&Model")
        rebuild_action = self._action("Přepočítat", self.rebuild, "F5")
        model_menu.addAction(rebuild_action)
        toolbar.addAction(rebuild_action)
        toolbar.addSeparator()

        view_menu = bar.addMenu("&Zobrazení")
        fit_action = self._action("Celý díl", self.viewer.fit_all, "F")
        view_menu.addAction(fit_action)
        toolbar.addAction(fit_action)
        for key, (label, shortcut) in VIEW_LABELS.items():
            action = self._action(label, lambda k=key: self.viewer.set_standard_view(k), shortcut)
            view_menu.addAction(action)
            if key in ("iso", "top", "front", "right"):
                toolbar.addAction(action)

        help_menu = bar.addMenu("&Nápověda")
        help_menu.addAction(self._action("Ovládání", self.show_controls))
        help_menu.addAction(self._action("O aplikaci", self.show_about))

    # --- práce se souborem -------------------------------------------------------

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
        self._rebuild_param_fields()
        self._refresh_all(fit=True)
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

    def _refresh_all(self, fit: bool = False) -> None:
        self._refresh_title()
        document = self.session.document
        self.description_label.setText(document.description if document else
                                       "Otevři model přes Soubor → Otevřít, nebo ukázku.")
        self._refresh_tree()
        self._refresh_properties()
        part = self.session.result.part if self.session.result else None
        self.viewer.show_part(part, fit=fit)

    def _refresh_title(self) -> None:
        self.setWindowTitle(self.session.title)

    def _refresh_tree(self) -> None:
        self.tree.clear()
        result = self.session.result
        if result is None:
            self.error_label.hide()
            return
        for status in result.statuses:
            item = QTreeWidgetItem([f"{_STATUS_ICONS[status.status]}  {status.label}"])
            item.setForeground(0, _STATUS_COLORS[status.status])
            item.setToolTip(0, status.message or status.id)
            self.tree.addTopLevelItem(item)
        error = result.first_error
        if error is None:
            self.error_label.hide()
        else:
            self.error_label.setText(f"✕ {error.label}: {error.message}")
            self.error_label.show()

    def _refresh_properties(self) -> None:
        props = self.session.properties
        if props is None:
            self.props_label.setText("—")
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
        self.props_label.setText("\n".join(lines))

    def _show_selection(self, description: str) -> None:
        if description:
            self.statusBar().showMessage(description)
        else:
            self.statusBar().showMessage(HELP_HINT)

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
            event.accept()
        else:
            event.ignore()
