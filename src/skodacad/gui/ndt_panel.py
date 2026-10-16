"""Panel NDT: studie nedestruktivní kontroly v modelu (etapa 01 – zatím bez výpočtů).

Seznam studií se stavem (✓ platná, ⚠ zastaralá / neúplná, ✕ neplatná vazba), nová studie
z ploch vybraných ve 3D, úpravy a ověření. Všechno jde přes ``ModelSession`` (jeden krok Zpět
na úpravu); panel sám nic nepočítá. Klik na studii zvýrazní ve 3D kontrolovanou oblast.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.ndt import DISCLAIMER
from skodacad.ndt.study import METHODS, StudyResult

if TYPE_CHECKING:
    from skodacad.gui.main_window import MainWindow

_STUDY_ID = Qt.ItemDataRole.UserRole
_STATE_COLORS = {"ok": QColor("#1b7f3b"), "stale": QColor("#b9770e"),
                 "incomplete": QColor("#b9770e"), "broken": QColor("#c0392b")}
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
        self.method_action = action("Metoda…", self.change_method)
        self.note_action = action("Poznámka…", self.edit_note)
        self.confirm_action = action("Potvrdit pro aktuální díl", self.confirm)
        self.confirm_action.setToolTip("Díl se změnil – zkontroloval(a) jsem studii a platí")
        self.verify_action = action("Ověřit…", self.verify)
        self.verify_action.setToolTip("Zapsat odborné ověření (kdo, dnes) pro aktuální díl")
        self.unverify_action = action("Zrušit ověření", self.unverify)
        self.duplicate_action = action("Kopie", self.duplicate)
        self.delete_action = action("Smazat studii", self.delete)

        layout = QVBoxLayout(self)
        warning = QLabel(DISCLAIMER)
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #8a5a00; font-style: italic;")
        layout.addWidget(warning)
        top = QHBoxLayout()  # metoda a tlačítko pod sebou – vedle sebe se do panelu nevejdou
        top.addWidget(QLabel("Metoda nové studie:"))
        self.method_combo = QComboBox()
        self.method_combo.setObjectName("ndt_method")
        for key, label in METHOD_LABELS.items():
            self.method_combo.addItem(label, key)
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
        for row in ((self.rename_action, self.target_action, self.method_action),
                    (self.confirm_action, self.verify_action, self.unverify_action),
                    (self.note_action, self.duplicate_action, self.delete_action)):
            buttons = QHBoxLayout()
            for item in row:
                buttons.addWidget(window._tool_button(item))
            buttons.addStretch()
            layout.addLayout(buttons)
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
        self._show_details()
        self.refresh_actions()

    def _row_changed(self) -> None:
        self._show_details()
        self.refresh_actions()
        self.window._update_highlight()  # kontrolovaná oblast vybrané studie ve 3D

    def _show_details(self) -> None:
        result = self.current()
        study_id = self.current_id()
        if result is None or study_id is None:
            self.details.setText("" if self.studies.count() else "Model zatím nemá NDT studii.")
            return
        record = self._record(study_id) or {}
        faces = _count(result.faces, "plocha", "plochy", "ploch")
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
        for action in (self.rename_action, self.method_action, self.note_action,
                       self.duplicate_action, self.delete_action):
            action.setEnabled(selected)
        self.confirm_action.setEnabled(selected and result is not None
                                       and result.state == "stale")
        self.verify_action.setEnabled(selected and result is not None and result.state == "ok")
        record = self._record(self.current_id())
        self.unverify_action.setEnabled(selected and record is not None and "verified" in record)
        if self.window.ai_busy:  # AI pracuje – ruční úpravy počkají
            for action in (self.new_action, self.target_action, self.rename_action,
                           self.method_action, self.note_action, self.duplicate_action,
                           self.delete_action, self.confirm_action, self.verify_action,
                           self.unverify_action):
                action.setEnabled(False)

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


def _count(n: int, one: str, few: str, many: str) -> str:
    return f"{n} {one if n == 1 else few if 2 <= n <= 4 else many}"
