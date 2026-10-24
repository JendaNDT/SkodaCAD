"""Panel Konstrukční návrh pro NDT (etapa 15B).

Pouze srovnává varianty na kopiích modelu. Vybraná varianta se nikdy neuplatní bez
potvrzení uživatele. Protokol a upozornění odpovídají docs/ndt/26-navrh-etapa-15.md.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.gui.audit_panel import write_pdf
from skodacad.ndt import DISCLAIMER
from skodacad.ndt.design import (
    BANNER,
    BEFORE,
    DESIGN_NOTE,
    TITLE,
    Design,
    DesignError,
)
from skodacad.rebuild import rebuild

if TYPE_CHECKING:
    from skodacad.gui.main_window import MainWindow

DATA = Qt.ItemDataRole.UserRole
COLUMNS = ("Varianta", "Parametry", "Stav", "Pokrytí / přístup", "Rozsah",
           "Proti původnímu", "Objem", "Hmotnost", "Důvod")
STATUS_COLORS = {"passed": "#226a33", "rejected": "#9b6500", "failed": "#a52a2a"}


def _label(text: str, name: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if name:
        widget.setObjectName(name)
    return widget


def _values(text: str) -> list[float]:
    """'40,60,80' nebo '40:100:20' v mm; desetinná tečka, nikoli čárka."""
    text = text.strip()
    if ":" in text:
        try:
            start, end, step = [float(piece.strip()) for piece in text.split(":")]
        except ValueError:
            raise DesignError("Rozsah hodnot zadej jako 40:100:20.") from None
        if step <= 0 or end < start:
            raise DesignError("Krok musí být kladný a konec nesmí být před začátkem.")
        count = round((end - start) / step)
        if count > 24 or abs(start + count * step - end) > 1e-7:
            raise DesignError("Konec rozsahu musí odpovídat kroku, nejvýš 24 intervalů.")
        return [round(start + i * step, 9) for i in range(count + 1)]
    try:
        return [float(number.strip()) for number in text.split(",")]
    except ValueError:
        raise DesignError("Hodnoty zadej například 40,60,80 nebo 40:100:20.") from None


class DesignDialog(QDialog):
    """Zadání studie, hodnot, zámků, podmínek a voleb ve formuláři bez přímé editace JSON."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Zadání konstrukčního návrhu pro NDT")
        self.setMinimumWidth(690)
        session = window.session
        document = session.document
        saved = session.ndt_design_settings()
        settings = saved.to_dict() if saved else {}
        layout = QVBoxLayout(self)
        layout.addWidget(_label(DESIGN_NOTE, "design_dialog_warning"))

        self.study = QComboBox()
        self.study.setObjectName("design_study")
        for item in (document.ndt or {}).get("studies", []):
            self.study.addItem(f"{item.get('name') or item['id']} ({item['method']})",
                               item["id"])
        index = self.study.findData(settings.get("study"))
        self.study.setCurrentIndex(max(index, 0))
        form = QFormLayout()
        form.addRow("Cílová NDT studie:", self.study)
        layout.addLayout(form)
        layout.addWidget(QLabel("Parametry a hodnoty (výčet 40,60,80 nebo rozsah 40:100:20):"))
        grid = QGridLayout()
        self.parameters: list[tuple[QComboBox, QLineEdit]] = []
        numeric = [name for name, value in document.parameters.items()
                   if isinstance(value, (int, float)) and not isinstance(value, bool)]
        for row in range(3):
            selector = QComboBox()
            selector.addItem("Nevybráno", "")
            for name in numeric:
                selector.addItem(name, name)
            values = QLineEdit()
            values.setPlaceholderText("40,60,80")
            values.setObjectName(f"design_values_{row}")
            old = settings.get("parameters", [])
            if row < len(old):
                item = old[row]
                index = selector.findData(item["name"])
                selector.setCurrentIndex(max(index, 0))
                if "values" in item:
                    values.setText(",".join(f"{v:g}" for v in item["values"]))
                else:
                    values.setText(f"{item['from']:g}:{item['to']:g}:{item['step']:g}")
            grid.addWidget(selector, row, 0)
            grid.addWidget(values, row, 1)
            self.parameters.append((selector, values))
        layout.addLayout(grid)

        locked = settings.get("locked", {})
        self.locked_measures = QListWidget()
        self.locked_measures.setObjectName("design_locked_measures")
        self.locked_measures.setMaximumHeight(90)
        for measure in document.measurements:
            item = QListWidgetItem(measure.get("name") or measure["id"])
            item.setData(DATA, measure["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if measure["id"] in
                               locked.get("measurements", []) else Qt.CheckState.Unchecked)
            self.locked_measures.addItem(item)
        layout.addWidget(QLabel("Zamčené uložené rozměry (žádná změna):"))
        layout.addWidget(self.locked_measures)

        self.locked_params = QListWidget()
        self.locked_params.setMaximumHeight(80)
        for name in document.parameters:
            item = QListWidgetItem(name)
            item.setData(DATA, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in
                               locked.get("parameters", []) else Qt.CheckState.Unchecked)
            self.locked_params.addItem(item)
        layout.addWidget(QLabel("Zamčené parametry včetně výrazů:"))
        layout.addWidget(self.locked_params)

        layout.addWidget(QLabel("Podmínky uložených měření (prázdná mez = bez podmínky):"))
        self.conditions = QTableWidget(len(document.measurements), 4)
        self.conditions.setObjectName("design_conditions")
        self.conditions.setHorizontalHeaderLabels(("Měření", "Min. ≥", "Max. ≤", "Důvod"))
        self.conditions.setMinimumHeight(95)
        self.conditions.setMaximumHeight(145)
        lookup = {c["measurement"]: c for c in settings.get("conditions", [])}
        for row, measurement in enumerate(document.measurements):
            mid = measurement["id"]
            fixed = QTableWidgetItem(measurement.get("name") or mid)
            fixed.setData(DATA, mid)
            fixed.setFlags(fixed.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.conditions.setItem(row, 0, fixed)
            c = lookup.get(mid, {})
            for col, key in ((1, "min"), (2, "max"), (3, "reason")):
                value = c.get(key)
                self.conditions.setItem(row, col, QTableWidgetItem(
                    "" if value is None else str(value)))
        layout.addWidget(self.conditions)

        options = settings.get("options", {})
        option_row = QGridLayout()
        self.mass_enabled = QCheckBox("Změna hmotnosti max. ± %")
        self.mass_enabled.setChecked(settings.get("mass_change_pct") is not None)
        self.mass = QDoubleSpinBox()
        self.mass.setRange(0.01, 10000)
        self.mass.setDecimals(2)
        self.mass.setValue(settings.get("mass_change_pct") or 10)
        self.mass.setEnabled(self.mass_enabled.isChecked())
        self.mass_enabled.toggled.connect(self.mass.setEnabled)
        option_row.addWidget(self.mass_enabled, 0, 0)
        option_row.addWidget(self.mass, 0, 1)
        self.others = QCheckBox("Spočítat i ostatní NDT studie")
        self.others.setChecked(options.get("others", False))
        self.rejected = QCheckBox("Spočítat i neprošlé varianty")
        self.rejected.setChecked(options.get("rejected", True))
        self.verify = QCheckBox("Ověřit pořadí jemnějším krokem")
        self.verify.setChecked(options.get("verify", True))
        self.thickness = QCheckBox("Hlídání meze mapy tloušťky")
        self.thickness.setChecked(options.get("thickness", False))
        option_row.addWidget(self.others, 1, 0)
        option_row.addWidget(self.rejected, 1, 1)
        option_row.addWidget(self.verify, 2, 0)
        option_row.addWidget(self.thickness, 2, 1)
        self.ut = QComboBox()
        self.ut.addItem("UT – sestavit plán znovu", "rebuild")
        self.ut.addItem("UT – jen ověřit uložený plán", "check")
        self.ut.setCurrentIndex(1 if options.get("ut") == "check" else 0)
        option_row.addWidget(self.ut, 3, 0, 1, 2)
        layout.addLayout(option_row)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    @staticmethod
    def _checked(widget: QListWidget) -> list[str]:
        return [widget.item(i).data(DATA) for i in range(widget.count())
                if widget.item(i).checkState() == Qt.CheckState.Checked]

    def design(self) -> Design:
        changes = []
        for selector, field in self.parameters:
            name = selector.currentData()
            if name:
                changes.append({"name": name, "values": _values(field.text())})
        conditions = []
        for row in range(self.conditions.rowCount()):
            record = {"measurement": self.conditions.item(row, 0).data(DATA)}
            for col, key in ((1, "min"), (2, "max")):
                value = self.conditions.item(row, col).text().strip()
                if value:
                    try:
                        record[key] = float(value)
                    except ValueError:
                        raise DesignError(f"Mez měření {record['measurement']} musí být číslo."
                                          ) from None
            if "min" in record or "max" in record:
                record["reason"] = self.conditions.item(row, 3).text().strip()
                conditions.append(record)
        data = {"study": self.study.currentData(), "parameters": changes,
                "locked": {"measurements": self._checked(self.locked_measures),
                           "parameters": self._checked(self.locked_params)},
                "conditions": conditions,
                "options": {"others": self.others.isChecked(),
                            "rejected": self.rejected.isChecked(),
                            "verify": self.verify.isChecked(),
                            "thickness": self.thickness.isChecked(),
                            "ut": self.ut.currentData()}}
        if self.mass_enabled.isChecked():
            data["mass_change_pct"] = self.mass.value()
        result = Design.from_dict(data)
        result.check(self.window.session.document)
        return result

    def accept(self) -> None:
        try:
            self.design()
        except (DesignError, DocumentError) as exc:
            QMessageBox.warning(self, "Neplatné zadání", str(exc))
            return
        super().accept()


class DesignPanel(QWidget):
    """Vlastní výsledky jsou jen pohled; změna modelu výsledek zneplatní."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__()
        self.window = window
        self._shown_result = None
        self._preview_model = None
        self._preview = None
        self._preview_base = None
        self._estimate_cache = None
        action = window._action
        self.edit_action = action("Zadat návrh…", self.edit_settings)
        self.estimate_action = action("Odhad doby", self.estimate_time)
        self.run_action = action("Spustit návrh", self.start)
        self.stop_action = action("Zastavit návrh", self.stop)
        self.apply_action = action("Použít variantu…", self.apply)
        self.save_action = action("Uložit variantu jako…", self.save_variant)
        self.export_action = action("Exportovat zprávu…", self.export)
        self.hide_action = action("Ukončit náhled", self.hide_preview)
        self.reject_action = action("Odmítnout výsledky", self.reject_results)

        layout = QVBoxLayout(self)
        layout.addWidget(_label(BEFORE))
        self.warning = _label(DISCLAIMER + "\n" + DESIGN_NOTE, "design_warning")
        self.warning.setStyleSheet("color: #8a4b00; font-size: 8pt;")
        layout.addWidget(self.warning)
        self.settings = _label("", "design_settings")
        layout.addWidget(self.settings)
        self.estimate = _label("", "design_estimate")
        layout.addWidget(self.estimate)
        self._actions(layout, self.edit_action, self.estimate_action)
        self._actions(layout, self.run_action, self.stop_action)
        self.progress = _label("", "design_progress")
        layout.addWidget(self.progress)
        layout.addWidget(QLabel(BANNER))
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("design_variants")
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(160)
        self.table.itemSelectionChanged.connect(self.preview)
        layout.addWidget(self.table)
        self.details = _label("", "design_details")
        layout.addWidget(self.details)
        self.preview_banner = _label("", "design_preview_banner")
        layout.addWidget(self.preview_banner)
        self._actions(layout, self.apply_action, self.save_action, self.hide_action)
        self._actions(layout, self.export_action, self.reject_action)
        layout.addStretch(1)
        self.refresh()

    def _actions(self, layout: QVBoxLayout, *actions) -> None:
        row = QHBoxLayout()
        for action in actions:
            row.addWidget(self.window._tool_button(action))
        row.addStretch()
        layout.addLayout(row)

    def refresh(self) -> None:
        session = self.window.session
        valid = session.document is not None and session.result is not None
        if self._preview is not None and (session.result is not self._preview_base
                                          or session.ndt_design is None):
            self._discard_preview()
        if not valid:
            self.settings.setText("Otevři nejprve model s NDT studií.")
        else:
            design = session.ndt_design_settings()
            self.settings.setText("Zadání: " + ("; ".join(design.text()) if design else
                                               "zatím neuloženo, otevři Zadat návrh…"))
        outcome = session.ndt_design if valid else None
        if outcome is not self._shown_result:
            self._fill(outcome)
            self._shown_result = outcome
        self.progress.setText(session.ndt_design_progress if session.design_pending else
                              outcome.conclusion() if outcome else "")
        ready = valid and not session.computing and not self.window.ai_busy
        has_settings = ready and not session.model_problem \
            and session.ndt_design_settings() is not None
        self.edit_action.setEnabled(ready)
        self.estimate_action.setEnabled(has_settings)
        self.run_action.setEnabled(has_settings)
        self.stop_action.setEnabled(session.design_pending)
        self.export_action.setEnabled(ready and outcome is not None)
        self.reject_action.setEnabled(ready and outcome is not None)
        self._selection_actions(ready)
        if session.design_pending:
            self.estimate.setText("Počítám konstrukční varianty…")
        elif has_settings:
            key = (id(session.result), repr(session.ndt_design_settings()))
            self.estimate.setText(self._estimate_cache[1] if self._estimate_cache is not None
                                  and self._estimate_cache[0] == key else
                                  "Zadání připravené – klikni na Odhad doby.")
        else:
            self.estimate.setText("")

    def _fill(self, result) -> None:
        selected = self.selected_index()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        if result is not None:
            for variant in result.ranked():
                row = result.row(variant)
                index = self.table.rowCount()
                self.table.insertRow(index)
                values = (row["variant"], row["values"], row["status"], row["good"],
                          row["region"], row["better"], row["volume"], row["mass"],
                          "; ".join(variant.reasons + list(variant.notes)))
                for col, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    cell.setData(DATA, variant.index)
                    cell.setToolTip(value)
                    if variant.status in STATUS_COLORS:
                        cell.setForeground(QColor(STATUS_COLORS[variant.status]))
                    self.table.setItem(index, col, cell)
                if variant.index == selected:
                    self.table.selectRow(index)
        self.table.blockSignals(False)
        self.details.setText(result.region_warning() if result else "")

    def selected_index(self) -> int | None:
        row = self.table.currentRow()
        cell = self.table.item(row, 0) if row >= 0 else None
        return int(cell.data(DATA)) if cell is not None else None

    def selected_variant(self):
        result = self.window.session.ndt_design
        index = self.selected_index()
        return (next((v for v in result.variants if v.index == index), None)
                if result is not None else None)

    def _selection_actions(self, ready: bool) -> None:
        variant = self.selected_variant()
        passed = variant is not None and variant.index != 0 and \
            variant.status == "passed" and variant.target is not None and \
            variant.target.status == "done"
        self.apply_action.setEnabled(ready and passed)
        self.save_action.setEnabled(ready and passed)
        self.hide_action.setEnabled(self._preview is not None)

    def edit_settings(self) -> None:
        if self.window.session.computing or self.window.ai_busy:
            return
        dialog = DesignDialog(self.window)
        if self.window._exec_dialog(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            self.hide_preview()
            self.window.session.set_ndt_design(dialog.design())
            self.window._refresh_all()
        except (DocumentError, DesignError) as exc:
            self.window._error("Zadání návrhu", str(exc))

    def estimate_time(self) -> None:
        session = self.window.session
        if session.computing or session.ndt_design_settings() is None:
            return
        try:
            key = (id(session.result), repr(session.ndt_design_settings()))
            count, seconds = self.window._busy(session.ndt_design_estimate)
            message = f"{count} variant, odhad přibližně {seconds / 60:.1f} minut."
            self._estimate_cache = (key, message)
            self.estimate.setText(message)
        except (DesignError, DocumentError) as exc:
            self.window._error("Odhad konstrukčního návrhu", str(exc))

    def start(self) -> None:
        session = self.window.session
        if session.computing or self.window.ai_busy:
            return
        try:
            design = session.ndt_design_settings()
            count, seconds = session.ndt_design_estimate(design)
            text = f"{count} variant, přibližně {seconds / 60:.1f} minut."
            if QMessageBox.question(self, "Spustit konstrukční návrh?",
                                    DESIGN_NOTE + "\n\n" + text) != \
                    QMessageBox.StandardButton.Yes:
                return
            self.hide_preview()
            session.start_ndt_design(design)
            self.refresh()
        except (DocumentError, DesignError) as exc:
            self.window._error("Konstrukční návrh", str(exc))

    def stop(self) -> None:
        if self.window.session.design_pending:
            self.window.stop_rebuild()

    def _discard_preview(self) -> None:
        self._preview = None
        self._preview_base = None
        self._preview_model = None
        self.preview_banner.setText("")

    def hide_preview(self) -> None:
        if self._preview is None:
            return
        self._discard_preview()
        self.window._shown_key = None
        self.window._refresh_all()

    def preview(self) -> None:
        variant = self.selected_variant()
        if variant is None or variant.index == 0 or self.window.session.computing:
            self.hide_preview()
            self._selection_actions(not self.window.session.computing)
            return
        session = self.window.session
        key = (id(session.result), variant.index)
        if key == self._preview:
            return
        self._discard_preview()
        try:
            copy_model = session.document.with_parameters(variant.values)
            view = rebuild(copy_model, with_map=False)
            if view.part is None or not view.ok:
                raise DocumentError("Variantu nejde zobrazit – nemá platné 3D těleso.")
            viewer = self.window.viewer
            viewer.show_part(view.part, fit=False)
            if hasattr(viewer, "show_design_ghost"):
                viewer.show_design_ghost(session.result.part)
            # Přebíráme přímo výsledek cílové studie z výpočtu varianty.
            self._show_target_map(copy_model, view, variant)
            self._preview = key
            self._preview_base = session.result
            self._preview_model = view
            self.preview_banner.setText(f"Náhled varianty {variant.label} – model se nezměnil.")
            result = session.ndt_design
            self.details.setText("; ".join(
                [result.row(variant)["status"], *variant.reasons, *variant.notes]))
        except Exception as exc:  # noqa: BLE001 – chybný náhled nesmí shodit GUI
            # Prohlížeč musí ukázat původní díl, i když náhled selhal.
            self.window._shown_key = None
            self.window._refresh_all()
            self.details.setText(f"Náhled nelze sestavit: {exc}")
        self._selection_actions(not session.computing and not self.window.ai_busy)

    def _show_target_map(self, document, model, variant) -> None:
        target = variant.target
        if target is None or target.result is None:
            return
        try:
            from skodacad.ndt.coverage import CoverageMap
            from skodacad.ndt.plan import PlanResult
            from skodacad.ndt.volume_coverage import VolumeCoverageMap
            from skodacad.session import ModelSession

            temporary = ModelSession()
            temporary.document, temporary.result = document, model
            mapped = target.result
            if isinstance(mapped, PlanResult):
                mapped = mapped.coverage.coverage if mapped.coverage is not None else None
            if mapped is None:
                return
            if isinstance(mapped, (CoverageMap, VolumeCoverageMap)):
                nodes, faces, colors = temporary.coverage_mesh(mapped)
            elif getattr(mapped, "kind", None) == "volume" and hasattr(
                    temporary, "_rt_volume_drawing"):
                nodes, faces, colors = temporary._rt_volume_drawing(mapped, None)
            else:
                nodes, faces, colors = mapped.mesh(None)
            if nodes and hasattr(self.window.viewer, "show_coverage_map"):
                self.window.viewer.show_coverage_map(nodes, faces, colors,
                                                      topmost=isinstance(mapped,
                                                                         VolumeCoverageMap))
        except (DocumentError, ValueError, TypeError, AttributeError):
            # Mapa se nesmí prezentovat, pokud ji nelze spolehlivě zobrazit.
            self.details.setText("Geometrickou mapu náhledu nelze spolehlivě zobrazit.")

    def apply(self) -> None:
        variant = self.selected_variant()
        result = self.window.session.ndt_design
        if variant is None or result is None:
            return
        description = variant.values_text(result.original)
        text = DESIGN_NOTE + "\n\nPoužít změny v otevřeném modelu?\n" + description + \
            "\n\nSoubor nebude uložen automaticky; Zpět vrátí původní parametry."
        if QMessageBox.question(self, "Potvrzení konstrukční změny", text) != \
                QMessageBox.StandardButton.Yes:
            return
        self.hide_preview()
        try:
            self.window._apply(lambda: self.window.session.apply_ndt_design_variant(
                variant.index))
            self.window._reload_all()
        except (DocumentError, DesignError) as exc:
            self.window._error("Použití varianty", str(exc))

    def save_variant(self) -> None:
        variant = self.selected_variant()
        if variant is None:
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Uložit variantu jako nový model",
            str(self.window.user_dir / f"SkodaCAD-{variant.label}.json"),
            "Model ŠkodaCAD (*.json)")
        if not target:
            return
        try:
            path = self.window.session.save_ndt_design_variant(variant.index, target)
            self.window.statusBar().showMessage(f"Varianta uložena: {path}", 10000)
        except (DocumentError, OSError) as exc:
            self.window._error("Uložení varianty", str(exc))

    def export(self) -> None:
        result = self.window.session.ndt_design
        if result is None:
            return
        target = QFileDialog.getExistingDirectory(self, "Složka pro zprávu konstrukčního návrhu")
        if not target:
            return
        images: dict[str, list[tuple[str, bytes]]] = {}
        selected = self.selected_index()
        try:
            with tempfile.TemporaryDirectory() as folder:
                for variant in result.ranked():
                    if variant.index == 0 or variant.volume is None:
                        continue
                    row = next((r for r in range(self.table.rowCount())
                                if self.table.item(r, 0).data(DATA) == variant.index), None)
                    if row is None:
                        continue
                    self.table.selectRow(row)
                    if self._preview is None:
                        continue
                    image = Path(folder) / f"varianta-{variant.index}.png"
                    if self.window.viewer.dump(str(image)) and image.exists():
                        images[variant.label] = [("Geometrický náhled", image.read_bytes())]
            files = self.window.session.export_ndt_design(target, images)
            files.append(write_pdf(result.html(images), Path(target) / "navrh.pdf",
                                   title=TITLE))
            self.window.statusBar().showMessage(
                f"Zpráva návrhu uložena: {len(files)} souborů", 10000)
        except (DocumentError, OSError) as exc:
            self.window._error("Export konstrukčního návrhu", str(exc))
        finally:
            self.hide_preview()
            if selected is not None:
                for row in range(self.table.rowCount()):
                    if self.table.item(row, 0).data(DATA) == selected:
                        self.table.selectRow(row)
                        break

    def reject_results(self) -> None:
        """Odmítnutí = odstranit jen vypočítaný náhled a tabulku, model zůstane."""
        self.hide_preview()
        self.window.session.clear_ndt_design()
        self.refresh()
