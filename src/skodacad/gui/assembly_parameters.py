"""Pracovní tabulka parametrů sestavy; potvrzení všech změn je jeden krok Zpět."""

from __future__ import annotations

import copy
import keyword
import math
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
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
from skodacad.assembly_parameter_usage import parameter_usage
from skodacad.expressions import CONSTANTS, FUNCTIONS, ExpressionError, resolve_parameters


class AssemblyParametersDialog(QDialog):
    def __init__(self, parameters: dict[str, Any], apply: Callable[[dict], None], parent=None,
                 *, assembly: Assembly | None = None):
        super().__init__(parent)
        self._apply = apply
        self._assembly = copy.deepcopy(assembly)
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
        layout.addWidget(self.table, 2)
        row = QHBoxLayout()
        self.add_button = QPushButton("Přidat parametr")
        self.delete_button = QPushButton("Smazat vybraný")
        for button in (self.add_button, self.delete_button):
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
        self.usage_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.usage_table.setMinimumHeight(120)
        layout.addWidget(self.usage_table, 1)
        scope = QLabel("Odkazy v této sestavě, včetně návazností přes jiné parametry. "
                       "Vazby mohou přemístit i další spojené díly.")
        scope.setWordWrap(True)
        layout.addWidget(scope)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setAccessibleName("Stav parametrů")
        layout.addWidget(self.message)
        footnote = QLabel("Změny se projeví až po potvrzení, všechny najednou. "
                          "Zpět vrátí celou úpravu. Rozměry zdrojových dílů se zde nemění.")
        footnote.setWordWrap(True)
        layout.addWidget(footnote)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.apply_button.setText("Použít změny")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        # Enter patří editoru buňky; celou dávku potvrzuje až tlačítko Použít změny.
        for button in self.buttons.buttons():
            button.setAutoDefault(False)
            button.setDefault(False)
        layout.addWidget(self.buttons)
        for name, value in parameters.items():
            self._append(name, self._format(value))
        self.table.itemChanged.connect(self._update)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.currentCellChanged.connect(self._selection_changed)
        self.add_button.clicked.connect(self.add_parameter)
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
            if column == 2:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column, item)
        return row

    def parameters(self):
        parameters = {}
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text().strip()
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
        self._refresh_usage()

    def _refresh_usage(self):
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
            self._apply(self.parameters())
        except AssemblyError as exc:
            self._error(str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        super().accept()
