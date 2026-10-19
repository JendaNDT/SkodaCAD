"""Dialog *Nastavení MT…* (etapa 12): jho, rozteče, meze, materiál, nanesení a prohlídka.

Dialog jen upravuje čísla; uloží je okno přes ``ModelSession.set_ndt_mt_settings`` (jeden
krok Zpět, stejné nastavení = žádná změna). Čísla jsou text (ne číselník), aby se
nezaokrouhlila – nezměněné *OK* vrátí totéž nastavení. Kontrolu dělá jádro (``MtSettings``).
"""

from __future__ import annotations

from dataclasses import fields

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from skodacad.ndt.mt import CHOSEN, DETECT_SOURCE, ZONE_SOURCE, MtError, MtSettings

VIEW_SOURCE = "kontrola prohlídky PT (ASME BPVC V čl. 9 a BINDT CP25)"
FIELDS = (  # klíč, popis, poznámka (původ hodnoty)
    ("spacing_mm", "Rozteč pólů [mm]", CHOSEN),
    ("min_spacing_mm", "Nejmenší rozteč, když hlavní nejde [mm]",
     "ISO 17638: aspoň 75 mm; = rozteč pólů → bez zálohy"),
    ("pole_mm", "Pól – průměr [mm]", CHOSEN),
    ("leg_mm", "Výška nohy od plochy k tělu [mm]", CHOSEN + " (botka pólu 15 mm)"),
    ("body_mm", "Tělo jha – průřez [mm]", CHOSEN),
    ("body_overhang_mm", "Přesah těla za nohy [mm]", CHOSEN),
    ("max_gap_mm", "Mezera pod pólem – nejvýš [mm]", CHOSEN + " (norma číslo neuvádí)"),
    ("leg_angle_deg", "Úhel mezi nohami – nejvýš [°]", CHOSEN + " (kloubové jho)"),
    ("step_over_mm", "Spojnice místa a pólu nad povrchem [mm]", CHOSEN),
    ("pole_zone_mm", "Oblast u pólu, která se nepočítá [mm]", ZONE_SOURCE),
    ("detect_deg", "Nejmenší úhel vady k poli [°]", DETECT_SOURCE),
    ("step_mm", "Krok sítě míst [mm]", "prázdné = automaticky (asi 1000 míst)"),
    ("center_step_mm", "Krok středů jha [mm]",
     "prázdné = automaticky (asi 1500 poloh jha); menší krok = přesnější okraj, déle"),
    ("spray_deg", "Nanesení – nejvýš od kolmice [°]", CHOSEN),
    ("spray_limit_deg", "Nanesení šikmo – nejvýš od kolmice [°]", CHOSEN),
    ("view_deg", "Prohlídka – aspoň k povrchu [°]", VIEW_SOURCE),
    ("view_limit_deg", "Prohlídka šikmo – aspoň k povrchu [°]", CHOSEN + " (zrcátko, šikmo)"),
    ("view_distance_mm", "Vzdálenost oka – nejvýš [mm]", VIEW_SOURCE),
    ("eye_mm", "Volný prostor pro oko – průměr [mm]", CHOSEN + "; 0 = oko jako bod"),
)
OPTIONAL = ("step_mm", "center_step_mm")
CHECKS = (  # klíč, popis
    ("apply", "Počítat nanesení detekčního prostředku (nástřik)"),
    ("inspect", "Počítat prohlídku"),
    ("ferromagnetic", "Materiál je feromagnetický (potvrzeno uživatelem – nerez, neuvedený)"),
)


def _text(value: float | None) -> str:
    return "" if value is None else f"{value:g}".replace(".", ",")


class MtDialog(QDialog):
    def __init__(self, parent: QWidget | None, settings: MtSettings, material: str = ""
                 ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastavení MT – přiložení jha a směry magnetizace")
        self._original = settings
        layout = QVBoxLayout(self)
        hint = QLabel("Jen geometrie zkoušky jhem: kam se jho vejde a kterým orientačním směrem "
                      "povede pole mezi póly. Hodnoty označené „zvoleno pro výpočet“ nejsou "
                      "z normy – nastav je podle svého jha.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        if material:
            note = QLabel(material)
            note.setObjectName("mt_material_note")
            note.setWordWrap(True)
            layout.addWidget(note)
        form = QFormLayout()
        self.edits: dict[str, QLineEdit] = {}
        for key, label, source in FIELDS:
            edit = QLineEdit(_text(getattr(settings, key)))
            edit.setObjectName(f"mt_{key}")
            edit.setToolTip(source)
            self.edits[key] = edit
            form.addRow(label + ":", edit)
            note = QLabel(source)
            note.setStyleSheet("color: #666; font-size: small;")
            note.setWordWrap(True)
            form.addRow("", note)
        layout.addLayout(form)
        self.checks: dict[str, QCheckBox] = {}
        for key, label in CHECKS:
            box = QCheckBox(label)
            box.setObjectName(f"mt_{key}")
            box.setChecked(bool(getattr(settings, key)))
            self.checks[key] = box
            layout.addWidget(box)
        self.error = QLabel()
        self.error.setObjectName("mt_error")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c0392b;")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def settings(self) -> MtSettings:
        """Nastavení z polí (zkontrolované jádrem); chyba = ``MtError`` česky."""
        values: dict[str, object] = {}
        labels = {key: label for key, label, _ in FIELDS}
        for key, edit in self.edits.items():
            text = edit.text().strip().replace(",", ".")
            if not text and key in OPTIONAL:
                values[key] = None
                continue
            try:
                values[key] = float(text)
            except ValueError:
                raise MtError(f"{labels[key]}: zadej číslo.") from None
        for key, box in self.checks.items():
            values[key] = box.isChecked()
        if not values["ferromagnetic"] and self._original.ferromagnetic is None:
            values["ferromagnetic"] = None  # nezaškrtnuté = bez potvrzení (totožný záznam)
        known = {f.name for f in fields(MtSettings)}
        return MtSettings(**{key: value for key, value in values.items() if key in known})

    def accept(self) -> None:
        try:
            self.settings()
        except MtError as exc:
            self.error.setText(str(exc))  # dialog zůstane otevřený s chybou
            return
        super().accept()
