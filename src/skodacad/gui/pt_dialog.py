"""Dialog *Nastavení PT…* (etapa 11): nástroje, úhly nástřiku a prohlídky, oko, postup čištění.

Dialog jen upravuje čísla; uloží je okno přes ``ModelSession.set_ndt_pt_settings`` (jeden
krok Zpět, stejné nastavení = žádná změna). Čísla jsou text (ne číselník), aby se
nezaokrouhlila – nezměněné *OK* vrátí totéž nastavení. Kontrolu dělá jádro (``PtSettings``).
"""

from __future__ import annotations

from dataclasses import fields

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from skodacad.ndt.pt import CHOSEN, CLEANING, VIEW_SOURCE, PtError, PtSettings

FIELDS = (  # klíč, popis, poznámka (původ hodnoty)
    ("step_mm", "Krok sítě [mm]", "prázdné = automaticky (asi 1500 vzorků)"),
    ("tool_mm", "Hlavní nástroj – průměr [mm]", CHOSEN + " (hadřík na prstu, štětec)"),
    ("fine_tool_mm", "Jemný nástroj – průměr [mm]", CHOSEN + " (vatová tyčinka); 0 = bez něj"),
    ("tool_length_mm", "Délka dříku nástroje [mm]", CHOSEN),
    ("spray_deg", "Nástřik – nejvýš od kolmice [°]", CHOSEN),
    ("spray_limit_deg", "Nástřik šikmo – nejvýš od kolmice [°]", CHOSEN),
    ("view_deg", "Prohlídka – aspoň k povrchu [°]", VIEW_SOURCE),
    ("view_limit_deg", "Prohlídka šikmo – aspoň k povrchu [°]", CHOSEN + " (zrcátko, šikmo)"),
    ("view_distance_mm", "Vzdálenost oka – nejvýš [mm]", VIEW_SOURCE),
    ("eye_mm", "Volný prostor pro oko – průměr [mm]", CHOSEN + "; 0 = oko jako bod"),
    ("open_warning", "Upozornit pod otevřeností [%]", CHOSEN),
)


def _text(value: float | None) -> str:
    return "" if value is None else f"{value:g}".replace(".", ",")


class PtDialog(QDialog):
    def __init__(self, parent: QWidget | None, settings: PtSettings) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastavení PT – přístupnost povrchu")
        self._original = settings
        layout = QVBoxLayout(self)
        hint = QLabel("Jen geometrie: kam vede volná přímka zvenku, kam se vejde nástroj a kam je "
                      "vidět. Hodnoty označené „zvoleno pro výpočet“ nejsou z normy – nastav je "
                      "podle skutečných nástrojů a postupu.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.cleaning = QComboBox()
        self.cleaning.setObjectName("pt_cleaning")
        for key, label in CLEANING.items():
            self.cleaning.addItem(label, key)
        self.cleaning.setCurrentIndex(list(CLEANING).index(settings.cleaning))
        form.addRow("Čištění a odstranění přebytku:", self.cleaning)
        self.edits: dict[str, QLineEdit] = {}
        for key, label, note in FIELDS:
            edit = QLineEdit(_text(getattr(settings, key)))
            edit.setObjectName(f"pt_{key}")
            edit.setToolTip(note)
            self.edits[key] = edit
            form.addRow(label + ":", edit)
            source = QLabel(note)
            source.setStyleSheet("color: #666; font-size: small;")
            source.setWordWrap(True)
            form.addRow("", source)
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("pt_error")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c0392b;")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def settings(self) -> PtSettings:
        """Nastavení z polí (zkontrolované jádrem); chyba = ``PtError`` česky."""
        values: dict[str, object] = {"cleaning": self.cleaning.currentData()}
        labels = {key: label for key, label, _ in FIELDS}
        for key, edit in self.edits.items():
            text = edit.text().strip().replace(",", ".")
            if not text and key == "step_mm":
                values[key] = None
                continue
            try:
                values[key] = float(text)
            except ValueError:
                raise PtError(f"{labels[key]}: zadej číslo.") from None
        known = {f.name for f in fields(PtSettings)}
        return PtSettings(**{key: value for key, value in values.items() if key in known})

    def accept(self) -> None:
        try:
            self.settings()
        except PtError as exc:
            self.error.setText(str(exc))  # dialog zůstane otevřený s chybou
            return
        super().accept()
