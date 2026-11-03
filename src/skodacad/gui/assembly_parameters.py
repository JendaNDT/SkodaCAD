"""Pracovní tabulka parametrů sestavy; potvrzení všech změn je jeden krok Zpět."""

from __future__ import annotations

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

from skodacad.assembly import AssemblyError
from skodacad.expressions import ExpressionError, resolve_parameters


class AssemblyParametersDialog(QDialog):
    def __init__(self, parameters: dict[str, Any], apply: Callable[[dict], None], parent=None):
        super().__init__(parent)
        self._apply = apply
        self.setWindowTitle("Parametry sestavy")
        self.resize(680, 440)
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
        layout.addWidget(self.table)
        row = QHBoxLayout()
        self.add_button = QPushButton("Přidat parametr")
        self.delete_button = QPushButton("Smazat vybraný")
        for button in (self.add_button, self.delete_button):
            button.setAutoDefault(False)
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
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
        self.add_button.clicked.connect(self.add_parameter)
        self.delete_button.clicked.connect(self.delete_parameter)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
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
            if not name or keyword.iskeyword(name):
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

    def _selection_changed(self):
        self.delete_button.setEnabled(self.table.currentRow() >= 0)

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
