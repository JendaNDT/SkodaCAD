"""Panel NDT: studie nedestruktivní kontroly v modelu a virtuální sonda (etapy 01 a 03).

Seznam studií se stavem (✓ platná, ⚠ zastaralá / neúplná, ✕ neplatná vazba), nová studie
z ploch vybraných ve 3D, úpravy a ověření. Všechno jde přes ``ModelSession`` (jeden krok Zpět
na úpravu); panel sám nic nepočítá. Klik na studii zvýrazní ve 3D kontrolovanou oblast.
U UT studie jde nastavit sondu (uloží se do studie) a přiložit ji kliknutím na plochu – sonda
se ve 3D nakreslí v barvě výsledku (jen pohled, do modelu se neukládá). U UT (vybraná studie,
bez výběru metoda nové studie) je nahoře povinné upozornění ``UT_DISCLAIMER``
(``docs/ndt/04-zavazne-vymezeni-ut.md``), jinak obecné ``DISCLAIMER``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.gui.target_dialog import TargetDialog
from skodacad.ndt import DISCLAIMER, UT_ACCESS, UT_COVERAGE, UT_DISCLAIMER
from skodacad.ndt.coverage import PERCENT_NOTE
from skodacad.ndt.devices import KINDS, Probe
from skodacad.ndt.study import METHODS, StudyResult
from skodacad.ndt.welds import WELD_TYPES

if TYPE_CHECKING:
    from skodacad.gui.main_window import MainWindow

_STUDY_ID = Qt.ItemDataRole.UserRole
_STATE_COLORS = {"ok": QColor("#1b7f3b"), "stale": QColor("#b9770e"),
                 "incomplete": QColor("#b9770e"), "broken": QColor("#c0392b")}
_PLACEMENT_COLORS = {"ok": "#1b7f3b", "collision": "#c0392b"}  # ostatní stavy oranžově
ANGLE_HINT = ("Směr paprsku ve stupních: 0° = osa +X sklopená do plochy (u plochy kolmé na X "
              "osa +Y), kladně proti směru hodin při pohledu na plochu zvenku.")
METHOD_LABELS = {key: f"{key} – {name}" for key, name in METHODS.items()}
HINT = ("Vyber ve 3D plochy kontrolované oblasti (Ctrl+klik přidá další) a dej Nová studie. "
        "Studie nemění díl; po změně dílu se označí jako zastaralá.")


class NdtPanel(QWidget):
    def __init__(self, window: MainWindow) -> None:
        super().__init__()
        self.window = window
        action = window._action
        self.new_action = action("Nová NDT studie z výběru", self.new_study)
        self.new_action.setToolTip("Nová studie; vybrané plochy budou kontrolovaná oblast")
        self.rename_action = action("Přejmenovat…", self.rename)
        self.target_action = action("Oblast z výběru", self.set_target)
        self.target_action.setToolTip("Kontrolovaná oblast = plochy vybrané ve 3D")
        self.volume_action = action("Cílový objem…", self.edit_volume_target)
        self.volume_action.setToolTip("Svar nebo kontrolovaný objem uvnitř dílu (místo ploch); "
                                      "díl se nemění")
        self.method_action = action("Metoda…", self.change_method)
        self.note_action = action("Poznámka…", self.edit_note)
        self.confirm_action = action("Potvrdit pro aktuální díl", self.confirm)
        self.confirm_action.setToolTip("Díl se změnil – zkontroloval(a) jsem studii a platí")
        self.verify_action = action("Ověřit…", self.verify)
        self.verify_action.setToolTip("Zapsat odborné ověření (kdo, dnes) pro aktuální díl")
        self.unverify_action = action("Zrušit ověření", self.unverify)
        self.duplicate_action = action("Kopie", self.duplicate)
        self.delete_action = action("Smazat studii", self.delete)
        self.probe_action = action("Sonda…", self.edit_probe)
        self.probe_action.setToolTip("Druh a rozměry virtuální sondy, dovolená mezera, rezerva")
        self.place_action = action("Přiložit sondu sem", self.place_probe)
        self.place_action.setToolTip("Přiloží sondu studie na plochu, na kterou jsi klikl(a)")
        self.drag_probe_action = action("Jezdit sondou myší", self._toggle_drag_mode)
        self.drag_probe_action.setCheckable(True)
        self.drag_probe_action.setToolTip(
            "Levé tlačítko myší ve 3D jezdí sondou po povrchu dílu (nebo kdykoli drž Alt)")
        self.remove_probe_action = action("Odebrat sondu", self.remove_probe)
        self.step_back_action = action("◀", lambda: self.shift_probe(-self.step_mm.value()))
        self.step_back_action.setToolTip("Posunout sondu dozadu proti směru paprsku")
        self.step_forward_action = action("▶", lambda: self.shift_probe(self.step_mm.value()))
        self.step_forward_action.setToolTip("Posunout sondu dopředu ve směru paprsku")
        self.scan_action = action("Projet čáru", self.scan_line)
        self.scan_action.setToolTip(
            "Projede sondou přímku ve směru paprsku po 1 mm a najde volný rozsah i první překážku")
        self.coverage_action = action("Spočítat pokrytí", self.compute_coverage)
        self.clear_coverage_action = action("Skrýt mapu", self.clear_coverage)
        self.export_coverage_action = action("Export CSV…", self.export_coverage)

        layout = QVBoxLayout(self)
        self.warning = QLabel(UT_DISCLAIMER)  # povinné upozornění UT, jinak obecné (_show_warning)
        self.warning.setObjectName("ndt_warning")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #8a5a00; font-style: italic;")
        layout.addWidget(self.warning)
        top = QHBoxLayout()  # metoda a tlačítko pod sebou – vedle sebe se do panelu nevejdou
        top.addWidget(QLabel("Metoda nové studie:"))
        self.method_combo = QComboBox()
        self.method_combo.setObjectName("ndt_method")
        for key, label in METHOD_LABELS.items():
            self.method_combo.addItem(label, key)
        self.method_combo.currentIndexChanged.connect(lambda _index: self._show_warning())
        top.addWidget(self.method_combo)
        top.addStretch()
        layout.addLayout(top)
        new_row = QHBoxLayout()
        new_row.addWidget(window._tool_button(self.new_action))
        new_row.addStretch()
        layout.addLayout(new_row)
        self.hint = QLabel(HINT)
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #555;")
        layout.addWidget(self.hint)
        self.studies = QListWidget()
        self.studies.setObjectName("ndt_studies")
        self.studies.setMinimumHeight(70)
        self.studies.setMaximumHeight(140)  # pod seznamem musí být vidět podrobnosti
        self.studies.currentRowChanged.connect(lambda _row: self._row_changed())
        self.studies.itemDoubleClicked.connect(lambda _item: self.rename())
        layout.addWidget(self.studies)
        for row in ((self.target_action, self.volume_action),
                    (self.rename_action, self.method_action, self.note_action),
                    (self.confirm_action, self.verify_action, self.unverify_action),
                    (self.duplicate_action, self.delete_action)):
            buttons = QHBoxLayout()
            for item in row:
                buttons.addWidget(window._tool_button(item))
            buttons.addStretch()
            layout.addLayout(buttons)
        probe_box = QGroupBox(UT_ACCESS)
        probe_box.setObjectName("ndt_ut")
        probe_layout = QVBoxLayout(probe_box)
        self.probe_label = QLabel()
        self.probe_label.setObjectName("ndt_probe")
        self.probe_label.setWordWrap(True)
        probe_layout.addWidget(self.probe_label)
        buttons = QHBoxLayout()
        for item in (self.probe_action, self.place_action, self.drag_probe_action,
                     self.remove_probe_action):
            buttons.addWidget(window._tool_button(item))
        buttons.addStretch()
        probe_layout.addLayout(buttons)
        angle_row = QHBoxLayout()
        angle_row.addWidget(QLabel("Směr paprsku [°]:"))
        self.angle = QSpinBox()
        self.angle.setObjectName("ndt_angle")
        self.angle.setRange(-180, 180)
        self.angle.setSingleStep(15)
        self.angle.setWrapping(True)
        self.angle.setToolTip(ANGLE_HINT)
        self.angle.valueChanged.connect(lambda _value: self._angle_changed())
        angle_row.addWidget(self.angle)
        angle_row.addWidget(QLabel("Krok [mm]:"))
        self.step_mm = QDoubleSpinBox()
        self.step_mm.setObjectName("ndt_step")
        self.step_mm.setDecimals(1)
        self.step_mm.setRange(0.5, 100.0)
        self.step_mm.setSingleStep(1.0)
        self.step_mm.setValue(2.0)
        angle_row.addWidget(self.step_mm)
        for item in (self.step_back_action, self.step_forward_action):
            angle_row.addWidget(window._tool_button(item))
        angle_row.addStretch()
        probe_layout.addLayout(angle_row)
        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Délka čáry [mm]:"))
        self.scan_length = QDoubleSpinBox()
        self.scan_length.setObjectName("ndt_scan_length")
        self.scan_length.setDecimals(0)
        self.scan_length.setRange(1.0, 500.0)
        self.scan_length.setSingleStep(10.0)
        self.scan_length.setValue(50.0)
        scan_row.addWidget(self.scan_length)
        scan_row.addWidget(window._tool_button(self.scan_action))
        self.scan_slider = QSlider(Qt.Orientation.Horizontal)
        self.scan_slider.setObjectName("ndt_scan_slider")
        self.scan_slider.setRange(0, 0)
        self.scan_slider.valueChanged.connect(self._scan_slider_changed)
        scan_row.addWidget(self.scan_slider, stretch=1)
        probe_layout.addLayout(scan_row)
        self.scan_label = QLabel()
        self.scan_label.setObjectName("ndt_scan_summary")
        self.scan_label.setWordWrap(True)
        self.scan_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.scan_label.hide()
        probe_layout.addWidget(self.scan_label)
        self.placement_label = QLabel()
        self.placement_label.setObjectName("ndt_placement")
        self.placement_label.setWordWrap(True)
        self.placement_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        probe_layout.addWidget(self.placement_label)
        layout.addWidget(probe_box)
        self.coverage_box = QGroupBox(UT_COVERAGE)
        self.coverage_box.setObjectName("ndt_coverage")
        coverage_layout = QVBoxLayout(self.coverage_box)
        form = QFormLayout()
        self.coverage_mode = QComboBox()
        self.coverage_mode.addItem("Po ploše přiložení", "face")
        self.coverage_mode.addItem("Z přímé dráhy", "line")
        form.addRow("Zdroj poloh sondy:", self.coverage_mode)
        self.coverage_step = QDoubleSpinBox()
        self.coverage_step.setObjectName("ndt_coverage_step")
        self.coverage_step.setRange(0.5, 100)
        self.coverage_step.setDecimals(1)
        self.coverage_step.setValue(5.0)
        form.addRow("Krok výpočtu [mm]:", self.coverage_step)
        self.coverage_spread = QDoubleSpinBox()
        self.coverage_spread.setRange(0, 45)
        self.coverage_spread.setValue(0)
        form.addRow("Rozevření (poloviční úhel) [°]:", self.coverage_spread)
        coverage_layout.addLayout(form)
        row = QHBoxLayout()
        for item in (self.coverage_action, self.clear_coverage_action, self.export_coverage_action):
            row.addWidget(window._tool_button(item))
        coverage_layout.addLayout(row)
        legend = QLabel('<span style="color:#26b340">■ Pokryto</span> · '
                        '<span style="color:#d93326">■ Nepokryto</span> · '
                        '<span style="color:#e6bf26">■ Nelze spolehlivě vyhodnotit</span>')
        legend.setWordWrap(True)
        coverage_layout.addWidget(legend)
        self.coverage_label = QLabel(PERCENT_NOTE)
        self.coverage_label.setObjectName("ndt_coverage_summary")
        self.coverage_label.setWordWrap(True)
        self.coverage_label.setTextFormat(Qt.TextFormat.PlainText)
        self.coverage_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        coverage_layout.addWidget(self.coverage_label)
        layout.addWidget(self.coverage_box)
        self.details = QLabel()
        self.details.setObjectName("ndt_details")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)
        layout.addStretch()
        self.refresh()

    # --- zobrazení ---------------------------------------------------------------------

    def current_id(self) -> str | None:
        item = self.studies.currentItem()
        return item.data(_STUDY_ID) if item is not None else None

    def current(self) -> StudyResult | None:
        study_id = self.current_id()
        return next((r for r in self.window.session.ndt_studies if r.id == study_id), None)

    def _record(self, study_id: str | None) -> dict | None:
        """Záznam studie, nebo None (seznam se může na chvíli lišit od modelu – po smazání se
        obnoví až po překreslení dílu)."""
        document = self.window.session.document
        studies = (document.ndt or {}).get("studies", []) if document is not None else []
        return next((study for study in studies if study.get("id") == study_id), None)

    def select(self, study_id: str | None) -> None:
        for row in range(self.studies.count()):
            if self.studies.item(row).data(_STUDY_ID) == study_id:
                self.studies.setCurrentRow(row)
                return
        self.studies.setCurrentRow(-1)

    def refresh(self) -> None:
        """Seznam studií se stavem z posledního přepočtu (během přepočtu ⏳)."""
        session = self.window.session
        document = session.document
        records = (document.ndt or {}).get("studies", []) if document is not None else []
        results = {r.id: r for r in session.ndt_studies}
        selected = self.current_id()
        self.studies.blockSignals(True)
        self.studies.clear()
        for record in records:
            result = results.get(record["id"])
            if session.computing or result is None:
                item = QListWidgetItem(f"⏳ {record.get('name') or record['id']}")
            else:
                item = QListWidgetItem(f"{result.mark} {result.name} ({result.method}) – "
                                       f"{result.label}")
                item.setForeground(_STATE_COLORS[result.state])
                item.setToolTip("\n".join([*result.messages, result.verified]))
            item.setData(_STUDY_ID, record["id"])
            self.studies.addItem(item)
            if record["id"] == selected:
                self.studies.setCurrentItem(item)
        self.studies.blockSignals(False)
        self._show_warning()
        self._show_details()
        self._show_probe()
        self._show_coverage()
        self.refresh_actions()

    def _row_changed(self) -> None:
        self._show_warning()
        self._show_details()
        self._show_probe()
        self._show_coverage()
        self.refresh_actions()
        self.window._update_highlight()  # kontrolovaná oblast vybrané studie ve 3D

    def _show_warning(self) -> None:
        """UT studie (nebo nová UT bez výběru) = povinné upozornění UT, jinak obecné."""
        record = self._record(self.current_id())
        method = record.get("method") if record else self.method_combo.currentData()
        self.warning.setText(UT_DISCLAIMER if method == "UT"
                             or self.window.session.ndt_coverage is not None else DISCLAIMER)

    def _show_details(self) -> None:
        result = self.current()
        study_id = self.current_id()
        if result is None or study_id is None:
            self.details.setText("" if self.studies.count() else "Model zatím nemá NDT studii.")
            return
        record = self._record(study_id) or {}
        faces = (_count(result.faces, "plocha", "plochy", "ploch")
                 if result.target_kind == "faces" else _volume_text(record, result))
        lines = [f"<b>{result.name}</b> – {METHOD_LABELS.get(result.method, result.method)}",
                 f"Stav: <b>{result.mark} {result.label}</b> · kontrolovaná oblast: {faces}",
                 *result.messages, result.verified]
        if record.get("note"):
            lines.append(f"Poznámka: {record['note']}")
        if record.get("created"):
            lines.append(f"Založena: {record['created']} · otisk dílu {result.part}")
        self.details.setText("<br>".join(lines))

    def refresh_actions(self) -> None:
        session = self.window.session
        ready = session.document is not None and not session.computing
        result = self.current()
        selected = ready and self.current_id() is not None
        info = session.selection_info(self.window._picked)
        has_part = ready and session.result is not None and session.result.part is not None
        self.new_action.setEnabled(ready)
        self.target_action.setEnabled(selected and has_part and info.faces > 0
                                      and info.edges == 0)
        self.volume_action.setEnabled(selected and has_part)
        for action in (self.rename_action, self.method_action, self.note_action,
                       self.duplicate_action, self.delete_action):
            action.setEnabled(selected)
        self.confirm_action.setEnabled(selected and result is not None
                                       and result.state == "stale")
        self.verify_action.setEnabled(selected and result is not None and result.state == "ok")
        record = self._record(self.current_id())
        self.unverify_action.setEnabled(selected and record is not None and "verified" in record)
        ut = selected and (self._record(self.current_id()) or {}).get("method") == "UT"
        placed = ready and session.ndt_placement is not None
        self.probe_action.setEnabled(ut)
        self.place_action.setEnabled(ut and has_part and info.faces == 1 and info.edges == 0)
        can_drag = has_part and (ut or placed)
        self.drag_probe_action.setEnabled(can_drag)
        if not can_drag and self.drag_probe_action.isChecked():
            self.drag_probe_action.setChecked(False)
            self.window.viewer.probe_drag_enabled = False
        self.remove_probe_action.setEnabled(session.ndt_placement_request is not None)
        for action in (self.step_back_action, self.step_forward_action, self.scan_action):
            action.setEnabled(placed)
        self.scan_slider.setEnabled(placed and session.ndt_line_scan is not None)
        matching = (session.ndt_placement_request is not None
                    and session.ndt_placement_request[0] == self.current_id())
        self.coverage_action.setEnabled(bool(ut and placed and matching
                                             and result is not None and result.state == "ok"
                                             and result.target_kind == "faces"
                                             and not self.window.ai_busy))
        has_coverage = session.ndt_coverage is not None
        self.clear_coverage_action.setEnabled(has_coverage and not self.window.ai_busy)
        self.export_coverage_action.setEnabled(has_coverage and not self.window.ai_busy)
        self.coverage_box.setVisible(bool(ut or has_coverage or session._coverage_pending))
        if self.window.ai_busy:  # AI pracuje – ruční úpravy počkají
            for action in (self.new_action, self.target_action, self.volume_action,
                           self.rename_action,
                           self.method_action, self.note_action, self.duplicate_action,
                           self.delete_action, self.confirm_action, self.verify_action,
                           self.unverify_action, self.probe_action, self.place_action,
                           self.drag_probe_action, self.remove_probe_action,
                           self.step_back_action, self.step_forward_action, self.scan_action):
                action.setEnabled(False)
            self.scan_slider.setEnabled(False)

    # --- úpravy (každá přes ModelSession = jeden krok Zpět) -------------------------------

    def _apply(self, title: str, work) -> object | None:
        try:
            value = self.window._busy(work)
        except DocumentError as exc:
            self.window._error(title, str(exc))
            return None
        self.window._refresh_all()
        return value

    def new_study(self) -> None:
        method = self.method_combo.currentData()
        picked, point = list(self.window._picked), self.window.viewer.picked_point
        study_id = self._apply("NDT studii nejde založit",
                               lambda: self.window.session.add_ndt_study(method, picked, point))
        if study_id is not None:
            self.window.show_ndt()
            self.select(study_id)
            self.window.statusBar().showMessage(
                f"NDT studie založena: {self.window.session.ndt_study(study_id)['name']}", 8000)

    def rename(self) -> None:
        study_id = self.current_id()
        if study_id is None:
            return
        name, ok = QInputDialog.getText(self, "Přejmenovat NDT studii", "Název studie:",
                                        text=self.window.session.ndt_study(study_id)["name"])
        if ok:
            self._apply("Studii nejde přejmenovat",
                        lambda: self.window.session.rename_ndt_study(study_id, name))

    def set_target(self) -> None:
        study_id = self.current_id()
        if study_id is None:
            return
        picked, point = list(self.window._picked), self.window.viewer.picked_point
        self._apply("Kontrolovanou oblast nejde nastavit",
                    lambda: self.window.session.set_ndt_target(study_id, picked, point))

    def edit_volume_target(self) -> None:
        """Dialog cílového objemu (svar / hranol); OK = jeden krok Zpět, díl se nemění."""
        study_id = self.current_id()
        if study_id is None:
            return
        session = self.window.session
        target = session.ndt_study(study_id).get("target") or {}
        replaces_faces = bool(target.get("faces"))
        try:
            edge = session.ndt_frame_from_edge(list(self.window._picked))
        except DocumentError:
            edge = None  # pomůcka „Podle vybrané hrany“ zůstane vypnutá
        dialog = TargetDialog(session, target if target.get("kind") in ("volume", "weld")
                              else None, edge, self)
        if self.window._exec_dialog(dialog) != QDialog.DialogCode.Accepted:
            return
        values = dialog.target()
        if self._apply("Cílový objem nejde nastavit",
                       lambda: session.set_ndt_volume_target(study_id, values)) is not None:
            self.window.statusBar().showMessage(
                "Cílový objem nastaven" + (" – plochy oblasti nahradil (Zpět je vrátí)."
                                           if replaces_faces else "."), 8000)

    def change_method(self) -> None:
        study_id = self.current_id()
        if study_id is None:
            return
        labels = list(METHOD_LABELS.values())
        current = METHOD_LABELS[self.window.session.ndt_study(study_id)["method"]]
        label, ok = QInputDialog.getItem(self, "Metoda NDT studie", "Metoda:", labels,
                                         labels.index(current), False)
        if ok and label in labels:
            method = list(METHOD_LABELS)[labels.index(label)]
            self._apply("Metodu nejde změnit",
                        lambda: self.window.session.set_ndt_method(study_id, method))

    def edit_note(self) -> None:
        study_id = self.current_id()
        if study_id is None:
            return
        note, ok = QInputDialog.getMultiLineText(
            self, "Poznámka ke studii", "Zadání, předpoklady, omezení:",
            self.window.session.ndt_study(study_id).get("note", ""))
        if ok:
            self._apply("Poznámku nejde uložit",
                        lambda: self.window.session.set_ndt_note(study_id, note))

    def confirm(self) -> None:
        study_id = self.current_id()
        if study_id is not None:
            self._apply("Studii nejde potvrdit",
                        lambda: self.window.session.confirm_ndt_study(study_id))

    def verify(self) -> None:
        study_id = self.current_id()
        if study_id is None:
            return
        by, ok = QInputDialog.getText(self, "Ověřit NDT studii",
                                      "Kdo studii odborně ověřil (jméno):")
        if ok:
            self._apply("Studii nejde ověřit",
                        lambda: self.window.session.verify_ndt_study(study_id, by))

    def unverify(self) -> None:
        study_id = self.current_id()
        if study_id is not None:
            self._apply("Ověření nejde zrušit",
                        lambda: self.window.session.unverify_ndt_study(study_id))

    def duplicate(self) -> None:
        study_id = self.current_id()
        if study_id is None:
            return
        copy_id = self._apply("Studii nejde zkopírovat",
                              lambda: self.window.session.duplicate_ndt_study(study_id))
        if copy_id is not None:
            self.select(copy_id)

    def delete(self) -> None:
        study_id = self.current_id()
        if study_id is not None:
            self._apply("Studii nejde smazat",
                        lambda: self.window.session.remove_ndt_study(study_id))

    # --- sonda a paprsek (etapy 03 až 05) ----------------------------------------------------

    def _show_coverage(self) -> None:
        result = self.window.session.ndt_coverage
        if result is not None:
            self.coverage_label.setText("\n".join(result.summary()))
        elif self.window.session._coverage_pending is not None:
            self.coverage_label.setText("Počítám mapu… Výpočet můžeš zastavit dole v okně.")
        else:
            self.coverage_label.setText("Zelená: pokryto · červená: nepokryto · žlutá: nejisté.\n"
                                        + PERCENT_NOTE)

    def compute_coverage(self) -> None:
        self._apply("Pokrytí nejde spočítat", lambda: self.window.session.start_ndt_coverage(
            mode=self.coverage_mode.currentData(), step_mm=self.coverage_step.value(),
            spread_deg=self.coverage_spread.value(), length_mm=self.scan_length.value()))

    def clear_coverage(self) -> None:
        self.window.session.clear_ndt_coverage()
        self.window._refresh_all()

    def export_coverage(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export geometrického pokrytí UT",
                                             "pokryti-ut.csv", "CSV (*.csv)")
        if path:
            self._apply("CSV nejde uložit", lambda: self.window.session.export_ndt_coverage(path))

    def _show_probe(self) -> None:
        """Sonda vybrané studie, výsledek přiložení, čára posuvu a geometrická dráha paprsku."""
        session = self.window.session
        record = self._record(self.current_id())
        if record is None:
            self.probe_label.setText("Vyber UT studii – sonda patří ke studii.")
        elif record.get("method") != "UT":
            self.probe_label.setText("Sonda je zatím jen pro UT studie.")
        else:
            stored = "" if "device" in record else " (výchozí)"
            probe = session.ndt_probe(record["id"])
            beam_info = f", paprsek {probe.beam_angle:.0f}°" if probe.kind == "angle" else ""
            self.probe_label.setText(f"{probe.label}{beam_info}{stored}; mezera nejvýš "
                                     f"{probe.max_gap:.2f} mm, rezerva {probe.reserve:.2f} mm, "
                                     f"odrazy {probe.bounces}.")
        if session.ndt_placement_request is not None:
            self.angle.blockSignals(True)
            self.angle.setValue(round(session.ndt_placement_request[2]))
            self.angle.blockSignals(False)
        scan = session.ndt_line_scan
        self.scan_slider.blockSignals(True)
        if scan is not None:
            self.scan_slider.setRange(0, max(0, len(scan.positions) - 1))
            self.scan_slider.setValue(session.ndt_scan_index)
            dist = scan.positions[session.ndt_scan_index][0]
            self.scan_label.setText(f"Čára ({dist:.0f} mm): {scan.summary}")
            self.scan_label.show()
        else:
            self.scan_slider.setRange(0, 0)
            self.scan_slider.setValue(0)
            self.scan_label.setText("")
            self.scan_label.hide()
        self.scan_slider.blockSignals(False)
        placement = session.ndt_placement
        if placement is not None:
            color = _PLACEMENT_COLORS.get(placement.state, "#b9770e")
            beam = session.ndt_beam
            beam_html = f"<br>{beam.text.replace(chr(10), '<br>')}" if beam is not None else ""
            self.placement_label.setText(f'<span style="color: {color};"><b>'
                                         f"{placement.text}</b></span>{beam_html}")
        elif session.ndt_placement_request is not None and session.ndt_placement_error:
            self.placement_label.setText(f'<span style="color: #c0392b;">'
                                         f"{session.ndt_placement_error}</span>")
        else:
            self.placement_label.setText("Klikni ve 3D na plochu a dej Přiložit sondu sem "
                                         "(nebo zapni Jezdit sondou myší / drž Alt).")

    def edit_probe(self) -> None:
        study_id = self.current_id()
        if study_id is None:
            return
        dialog = ProbeDialog(self.window.session.ndt_probe(study_id), self)
        if self.window._exec_dialog(dialog) != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self._apply("Sondu nejde nastavit",
                    lambda: self.window.session.set_ndt_device(study_id, values))

    def place_probe(self) -> None:
        study_id = self.current_id()
        if study_id is None:
            return
        picked, point = list(self.window._picked), self.window.viewer.picked_point
        angle = self.angle.value()
        self._apply("Sondu nejde přiložit", lambda: self.window.session.place_ndt_probe(
            study_id, picked, point, angle))

    def remove_probe(self) -> None:
        self.window.session.clear_ndt_placement()
        self.window._refresh_all()

    def _toggle_drag_mode(self) -> None:
        self.window.viewer.probe_drag_enabled = self.drag_probe_action.isChecked()

    def shift_probe(self, delta_mm: float) -> None:
        self._apply("Sondu nejde posunout",
                    lambda: self.window.session.shift_ndt_probe(delta_mm))

    def scan_line(self) -> None:
        self._apply("Čáru nejde projet",
                    lambda: self.window.session.scan_ndt_line(self.scan_length.value(), 1.0))

    def _scan_slider_changed(self, index: int) -> None:
        if self.window.session.ndt_line_scan is None:
            return
        try:
            self.window.session.select_ndt_scan_index(index)
        except DocumentError as exc:
            self.window.statusBar().showMessage(str(exc), 8000)
            return
        self.window._refresh_probe()
        self._show_probe()
        self._show_coverage()
        self.refresh_actions()

    def on_probe_dragged(self, shapes: list, point: object) -> None:
        """Jízda sondou myší ve 3D: přesune (nebo poprvé přiloží) sondu bez vyskakovacích oken."""
        if self.window.ai_busy or self.window.session.computing:
            return
        session = self.window.session
        if session.ndt_placement_request is not None:
            study_id = session.ndt_placement_request[0]
        else:
            record = self._record(self.current_id())
            if record is None or record.get("method") != "UT":
                return
            study_id = record["id"]
        try:
            session.move_ndt_probe(study_id, shapes, point, angle=self.angle.value())
        except DocumentError as exc:
            self.window.statusBar().showMessage(str(exc), 5000)
            return
        self.window._refresh_probe()
        self.window._update_highlight()
        self._show_probe()
        self._show_coverage()
        self.refresh_actions()

    def on_probe_rotated(self, delta_deg: int) -> None:
        if self.window.ai_busy or self.window.session.ndt_placement_request is None:
            return
        angle = ((self.angle.value() + int(delta_deg) + 180) % 360) - 180
        self.angle.setValue(angle)

    def _angle_changed(self) -> None:
        if self.window.session.ndt_placement_request is None:
            return
        self.window._busy(lambda: self.window.session.turn_ndt_probe(self.angle.value()))
        self.window._refresh_all()


class ProbeDialog(QDialog):
    """Nastavení virtuální sondy studie: druh, rozměry, výstupní bod, úhel paprsku, odrazy,
    mezera a rezerva."""

    FIELDS = (("diameter", "Průměr [mm]", ("straight",)), ("length", "Délka [mm]", ("angle",)),
              ("width", "Šířka [mm]", ("angle",)), ("height", "Výška [mm]", None),
              ("front", "Výstupní bod od čela [mm]", ("angle",)),
              ("beam_angle", "Úhel paprsku v materiálu β [°]", ("angle",)),
              ("max_gap", "Dovolená mezera pod sondou [mm]", None),
              ("reserve", "Manipulační rezerva [mm]", None))

    def __init__(self, probe: Probe, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sonda NDT studie")
        form = QFormLayout(self)
        note = QLabel("Obecná virtuální sonda – ne katalogový výrobek. Mezera 0,5 mm odpovídá "
                      "EN ISO 17640 (nejde o tvrzení o shodě).")
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        form.addRow(note)
        self.kind = QComboBox()
        self.kind.setObjectName("probe_kind")
        for key, label in KINDS.items():
            self.kind.addItem(label.capitalize(), key)
        self.kind.setCurrentIndex(self.kind.findData(probe.kind))
        form.addRow("Druh", self.kind)
        self.fields: dict[str, QDoubleSpinBox] = {}
        self.labels: dict[str, QLabel] = {}
        for key, label, _kinds in self.FIELDS:
            field = QDoubleSpinBox()
            field.setObjectName(f"probe_{key}")
            field.setDecimals(2)
            field.setRange(1.0 if key == "beam_angle" else 0.0,
                           85.0 if key == "beam_angle" else 1000.0)
            field.setValue(float(getattr(probe, key)))
            self.fields[key] = field
            self.labels[key] = QLabel(label)
            form.addRow(self.labels[key], field)
        self.bounces = QSpinBox()
        self.bounces.setObjectName("probe_bounces")
        self.bounces.setRange(0, 10)
        self.bounces.setValue(int(probe.bounces))
        form.addRow("Počet odrazů v dílu", self.bounces)
        self.kind.currentIndexChanged.connect(
            lambda _index: self._kind_changed(switched=True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self._kind_changed()

    def _kind_changed(self, switched: bool = False) -> None:
        kind = self.kind.currentData()
        for key, _label, kinds in self.FIELDS:
            shown = kinds is None or kind in kinds
            self.fields[key].setVisible(shown)
            self.labels[key].setVisible(shown)
        if switched:
            if kind == "straight" and self.bounces.value() == 1:
                self.bounces.setValue(0)
            elif kind == "angle" and self.bounces.value() == 0:
                self.bounces.setValue(1)

    def values(self) -> dict:
        kind = self.kind.currentData()
        return {"kind": kind,
                **{key: self.fields[key].value() for key, _label, kinds in self.FIELDS
                   if kinds is None or kind in kinds},
                "bounces": self.bounces.value()}


def _volume_text(record: dict, result: StudyResult) -> str:
    """Popis objemového cíle: druh a objem v materiálu (zadaný, když se liší)."""
    target = record.get("target") or {}
    kind = WELD_TYPES.get(target.get("weld_type"), "svar") if target.get("kind") == "weld" \
        else "obecný hranol"
    text = f"{kind}, objem {result.volume_mm3:.6g} mm³"
    if abs(result.requested_volume_mm3 - result.volume_mm3) > 1e-6 * max(1.0, result.volume_mm3):
        text += f" (zadaný {result.requested_volume_mm3:.6g} mm³)"
    return text


def _count(n: int, one: str, few: str, many: str) -> str:
    return f"{n} {one if n == 1 else few if 2 <= n <= 4 else many}"
