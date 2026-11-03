"""Pracovní tabulka parametrů sestavy; potvrzení všech změn je jeden krok Zpět."""

from __future__ import annotations

import copy
import keyword
import math
from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from skodacad.assembly import Assembly, AssemblyError
from skodacad.assembly_parameter_rename import rename_parameters, rename_references
from skodacad.assembly_parameter_usage import UsageTarget, parameter_usage
from skodacad.expressions import CONSTANTS, FUNCTIONS, ExpressionError, resolve_parameters


class AssemblyParametersDialog(QDialog):
    def __init__(self, parameters: dict[str, Any], apply: Callable[[dict], None], parent=None,
                 *, assembly: Assembly | None = None,
                 apply_renamed: Callable[[dict, Sequence[tuple[str, str]]], None] | None = None,
                 select_usage: Callable[[UsageTarget], bool] | None = None,
                 preview: Callable[[dict, Sequence[tuple[str, str]]], bool] | None = None):
        super().__init__(parent)
        self._apply = apply
        self._apply_renamed = apply_renamed
        self._renames: list[tuple[str, str]] = []
        self._assembly = copy.deepcopy(assembly)
        self._select_usage = select_usage
        self._preview = preview
        self._usage_targets: list[UsageTarget | None] = []
        self.setWindowTitle("Parametry sestavy")
        self.resize(780, 640)
        layout = QVBoxLayout(self)
        note = QLabel("Pojmenované hodnoty pro polohy a vazby sestavy. "
                      "Například roztec = 120 a polovina = roztec/2. "
                      "Délky jsou v mm, úhly ve stupních podle pole, kde parametr použiješ.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 3)
        self.table.setAccessibleName("Parametry sestavy")
        self.table.setHorizontalHeaderLabels(["Název", "Hodnota nebo výraz", "Výsledek"])
        self.table.horizontalHeaderItem(1).setToolTip(
            "Číslo může mít desetinnou čárku (12,5). Ve výrazech piš desetinnou tečku "
            "(roztec * 1.5); čárka odděluje argumenty funkcí, např. min(a, b).")
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.add_button = QPushButton("Přidat parametr")
        self.rename_button = QPushButton("Přejmenovat")
        self.rename_button.setToolTip("Uprav název vybraného parametru; jeho odkazy se přepíší. "
                                     "Vše potvrdíš tlačítkem Použít změny.")
        self.delete_button = QPushButton("Smazat vybraný")
        for button in (self.add_button, self.rename_button, self.delete_button):
            button.setAutoDefault(False)
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.usage_title = QLabel()
        self.usage_title.setTextFormat(Qt.TextFormat.PlainText)
        self.usage_title.setWordWrap(True)
        layout.addWidget(self.usage_title)
        self.usage_table = QTableWidget(0, 4)
        self.usage_table.setAccessibleName("Použití vybraného parametru")
        self.usage_table.setHorizontalHeaderLabels(["Místo", "Pole", "Výraz", "Závislost"])
        self.usage_table.verticalHeader().hide()
        self.usage_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.usage_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.usage_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.usage_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.usage_table.setMinimumHeight(120)
        layout.addWidget(self.usage_table, 1)
        self.usage_navigation = QLabel()
        self.usage_navigation.setTextFormat(Qt.TextFormat.PlainText)
        self.usage_navigation.setWordWrap(True)
        self.usage_navigation.setAccessibleName("Výběr z přehledu použití")
        layout.addWidget(self.usage_navigation)
        scope = QLabel("Odkazy v této sestavě, včetně návazností přes jiné parametry. "
                       "Vazby mohou přemístit i další spojené díly.")
        scope.setWordWrap(True)
        layout.addWidget(scope)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setAccessibleName("Stav parametrů")
        layout.addWidget(self.message)
        footnote = QLabel("Změna názvu upraví i jeho odkazy. Náhled ukáže dopad před potvrzením; "
                          "Použít změny přijme celou dávku najednou. "
                          "Zpět vrátí celou úpravu. Rozměry zdrojových dílů se zde nemění.")
        footnote.setWordWrap(True)
        layout.addWidget(footnote)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.apply_button.setText("Použít změny")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        self.preview_button = self.buttons.addButton("Náhled změn",
                                                     QDialogButtonBox.ButtonRole.ActionRole)
        self.preview_button.setVisible(preview is not None)
        self.preview_button.clicked.connect(self.show_preview)
        # Enter patří editoru buňky; celou dávku potvrzuje až tlačítko Použít změny.
        for button in self.buttons.buttons():
            button.setAutoDefault(False)
            button.setDefault(False)
        layout.addWidget(self.buttons)
        for name, value in parameters.items():
            self._append(name, self._format(value))
        self.table.itemChanged.connect(self._item_changed)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.currentCellChanged.connect(self._selection_changed)
        self.usage_table.cellClicked.connect(self._usage_clicked)
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self.usage_table)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self._activate_usage_row)
        self.add_button.clicked.connect(self.add_parameter)
        self.rename_button.clicked.connect(self.edit_parameter_name)
        self.delete_button.clicked.connect(self.delete_parameter)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        if self.table.rowCount():
            self.table.setCurrentCell(0, 0)
        self._update()

    @staticmethod
    def _format(value):
        return str(value).replace(".", ",") if isinstance(value, float) else str(value)

    def _append(self, name, value):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, text in enumerate((name, value, "")):
            item = QTableWidgetItem(text)
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, name.strip())
            if column == 2:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column, item)
        return row

    def parameters(self, name_at=None):
        parameters = {}
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text().strip()
            if name_at is not None and row == name_at[0]:
                name = name_at[1]
            text = self.table.item(row, 1).text().strip()
            if (not name.isidentifier() or keyword.iskeyword(name)
                    or name in CONSTANTS or name in FUNCTIONS):
                raise AssemblyError(f"Řádek {row + 1}: zadej platný název, například roztec.")
            if name in parameters:
                raise AssemblyError(f"Název „{name}“ je v tabulce dvakrát. Každý musí být jiný.")
            if not text:
                raise AssemblyError(f"Parametr „{name}“ nemá hodnotu. Zadej číslo nebo výraz.")
            try:
                number = float(text.replace(",", "."))
            except ValueError:
                parameters[name] = text
            else:
                parameters[name] = int(number) if number.is_integer() else number
        return parameters

    def _selection_changed(self, *_args):
        self.delete_button.setEnabled(self.table.currentRow() >= 0)
        self.rename_button.setEnabled(self.table.currentRow() >= 0)
        self._refresh_usage()

    def edit_parameter_name(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.setCurrentCell(row, 0)
            self.table.editItem(self.table.item(row, 0))

    def _item_changed(self, item):
        if item.column() != 0 or item.text().strip() == item.data(Qt.ItemDataRole.UserRole):
            self._update()
            return
        old, new = item.data(Qt.ItemDataRole.UserRole), item.text().strip()
        error = None
        self.table.blockSignals(True)
        try:
            parameters = rename_parameters(self.parameters(name_at=(item.row(), old)), old, new)
            candidate = copy.deepcopy(self._assembly)
            if candidate is not None:
                rename_references(candidate, old, new)
            for row in range(self.table.rowCount()):
                name_item = self.table.item(row, 0)
                name = new if row == item.row() else name_item.text().strip()
                name_item.setText(name)
                name_item.setData(Qt.ItemDataRole.UserRole, name)
                self.table.item(row, 1).setText(self._format(parameters[name]))
            self._assembly = candidate
            self._renames.append((old, new))
        except AssemblyError as exc:
            item.setText(old)
            error = str(exc)
        finally:
            self.table.blockSignals(False)
        self._update()
        if error is not None:
            self._error(error)

    def _refresh_usage(self):
        self._usage_targets = []
        self.usage_navigation.setText("Kliknutím nebo Enterem vybereš místo použití. "
                                      "Editor zůstane otevřený.")
        self.usage_navigation.setStyleSheet("")
        row = self.table.currentRow()
        if row < 0:
            self.usage_title.setText("Vyber parametr pro přehled použití.")
            self.usage_title.setToolTip("")
            self.usage_table.setRowCount(0)
            return
        try:
            parameters = self.parameters()
        except AssemblyError as exc:
            self.usage_title.setText(f"Přehled použití není dostupný: {exc}")
            self.usage_title.setToolTip("")
            self.usage_table.setRowCount(0)
            return
        name = self.table.item(row, 0).text().strip()
        report = parameter_usage(self._assembly, parameters, name)
        self._usage_targets = [use.target for use in report.uses]
        if report.warnings:
            status = "Přehled není úplný: " + report.warnings[0]
            if len(report.warnings) > 1:
                status += f" Další nečitelné výrazy: {len(report.warnings) - 1}."
        else:
            status = (f"Počet míst: {len(report.uses)}." if report.uses
                      else "V této sestavě se nepoužívá.")
        self.usage_title.setText(f"Použití parametru „{name}“ — {status}")
        self.usage_title.setToolTip("\n".join(report.warnings))
        # Při přepínání zachovat existující buňky kvůli nativní přístupnosti.
        self.usage_table.setRowCount(len(report.uses))
        for index, use in enumerate(report.uses):
            values = (use.place, use.field, self._format(use.expression),
                      "Přes " + " → ".join(use.via) if use.via else "Přímo")
            for column, text in enumerate(values):
                item = self.usage_table.item(index, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.usage_table.setItem(index, column, item)
                item.setText(text)
                item.setToolTip(text)

    def _activate_usage_row(self):
        self._usage_clicked(self.usage_table.currentRow())

    def _usage_clicked(self, row, _column=0):
        if not 0 <= row < len(self._usage_targets):
            return
        target = self._usage_targets[row]
        if target is None:
            return
        # Cíl nese skutečné id, nikdy jej neodvozujeme z popisku ani pořadí řádku.
        place = self.usage_table.item(row, 0).text()
        selected = False
        if target.kind == "parameter":
            for index in range(self.table.rowCount()):
                if self.table.item(index, 0).text().strip() == target.id:
                    self.table.setCurrentCell(index, 1)
                    self.table.scrollToItem(self.table.item(index, 1))
                    self.table.setFocus()
                    selected = True
                    break
        elif self._select_usage is not None:
            selected = self._select_usage(target)
        self.usage_navigation.setText(f"Vybráno: {place}." if selected else
                                      "Místo už není dostupné. Otevři přehled parametrů znovu.")
        self.usage_navigation.setStyleSheet("" if selected else "color: #bf3030;")

    def _update(self, *_args):
        # Buňky ponecháváme na místě; přístupnost drží jejich indexy i při opravě chyby.
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                self.table.item(row, 2).setText("—")
            resolved = resolve_parameters(self.parameters())
            for name, value in resolved.items():
                if not math.isfinite(value):
                    raise AssemblyError(f"Parametr „{name}“ musí být konečné číslo.")
            for row in range(self.table.rowCount()):
                name = self.table.item(row, 0).text().strip()
                self.table.item(row, 2).setText(f"{resolved[name]:.12g}".replace(".", ","))
            self.message.setText("Bez chyb. Názvy můžeš použít v polohách i vzdálenostech vazeb.")
            self.message.setStyleSheet("")
            self.apply_button.setEnabled(True)
        except (AssemblyError, ExpressionError, TypeError, ArithmeticError) as exc:
            self._error(str(exc) if not isinstance(exc, TypeError) else
                        "Zkontroluj počet argumentů matematické funkce ve výrazu.")
            self.apply_button.setEnabled(False)
        finally:
            self.table.blockSignals(False)
            self._selection_changed()
            self.preview_button.setEnabled(self.apply_button.isEnabled())

    def _error(self, text):
        self.message.setText(text)
        self.message.setStyleSheet("color: #bf3030;")

    def add_parameter(self):
        names = {self.table.item(row, 0).text().strip() for row in range(self.table.rowCount())}
        name, index = "parametr", 2
        while name in names:
            name, index = f"parametr{index}", index + 1
        self.table.blockSignals(True)
        row = self._append(name, "10")
        self.table.blockSignals(False)
        self.table.setCurrentCell(row, 0)
        self._update()
        self.table.editItem(self.table.item(row, 0))

    def delete_parameter(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self._update()

    def accept(self):
        # Také při Enteru nejprve převezmeme rozepsanou buňku z jejího editoru.
        self.table.setFocus()
        self._update()
        if not self.apply_button.isEnabled():
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if self._renames and self._apply_renamed is not None:
                self._apply_renamed(self.parameters(), tuple(self._renames))
            elif self._renames and self._assembly is not None:
                raise AssemblyError("Přejmenování zde nelze potvrdit. Otevři editor "
                                    "tlačítkem Parametry sestavy v okně sestavy.")
            else:
                self._apply(self.parameters())
        except AssemblyError as exc:
            self._error(str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        super().accept()

    def show_preview(self):
        self.table.setFocus()  # převzít rozepsanou buňku stejně jako při Použít
        self._update()
        if not self.preview_button.isEnabled() or self._preview is None:
            return
        try:
            if self._preview(self.parameters(), tuple(self._renames)):
                super().accept()  # dávku už přijal náhled, nepoužívat ji podruhé
        except AssemblyError as exc:
            self._error(str(exc))
