"""Dialogy RT (etapa 13): *Nastavení RT…* (zdroj, detektor, třída, kroky) a *Upravit
projekci…* (zaměřený bod, sklon a natočení směru ke zdroji, vzdálenost, detektor).

Dialogy jen upravují čísla; uloží je okno přes ``ModelSession`` (jeden krok Zpět, stejné
nastavení = žádná změna). Čísla jsou text (ne číselník), aby se nezaokrouhlila – nezměněné *OK*
vrátí totéž nastavení i projekci. Kontrolu dělá jádro (``RtSettings``, ``Projection``).
"""

from __future__ import annotations

from dataclasses import replace

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

from skodacad.ndt.rt import (
    ANGLE_NOTE,
    CHOSEN,
    DETECTOR_MODES,
    FILM_SOURCE,
    FMIN_SOURCE,
    RATIO_SOURCE,
    Projection,
    RtError,
    RtSettings,
    tilted,
)

CLASSES = {"B": "B – zlepšená (poměr tloušťky 1,1)", "A": "A – základní (poměr tloušťky 1,2)"}
FIELDS = (  # klíč, popis, poznámka (původ hodnoty)
    ("focal_mm", "Rozměr ohniska d [mm]", CHOSEN + " – podle štítku zdroje"),
    ("cone_deg", "Kužel svazku – vrcholový úhel [°]", CHOSEN + "; 360 = panoramatický zdroj"),
    ("housing_diameter_mm", "Tělo zdroje – průměr [mm]", CHOSEN + "; 0 = jen bod"),
    ("housing_length_mm", "Tělo zdroje – délka za ohniskem [mm]", CHOSEN),
    ("detector_width_mm", "Detektor – šířka [mm]", FILM_SOURCE),
    ("detector_length_mm", "Detektor – délka [mm]", FILM_SOURCE),
    ("detector_thickness_mm", "Detektor – tloušťka kazety nebo panelu [mm]", CHOSEN),
    ("step_mm", "Krok sítě míst [mm]", "prázdné = automaticky (plochy asi 1000 míst, svar "
                                        "podle průřezu)"),
    ("image_step_mm", "Krok náhledu na detektoru [mm]",
     "menší = jemnější náhled, déle (10 × 24 cm po 2 mm = 6 000 paprsků)"),
)
OPTIONAL = ("step_mm",)


def _text(value: float | None) -> str:
    """Číslo jako text s desetinnou čárkou, bez zaokrouhlení (nezměněné OK = totéž číslo)."""
    if value is None:
        return ""
    text = repr(float(value))
    return (text[:-2] if text.endswith(".0") else text).replace(".", ",")


def _number(text: str, label: str, optional: bool = False) -> float | None:
    text = text.strip().replace(",", ".")
    if not text and optional:
        return None
    try:
        return float(text)
    except ValueError:
        raise RtError(f"{label}: zadej číslo.") from None


def _note(text: str) -> QLabel:
    note = QLabel(text)
    note.setStyleSheet("color: #666; font-size: small;")
    note.setWordWrap(True)
    return note


class RtDialog(QDialog):
    """Nastavení RT studie (bez projekcí – ty zůstanou, jak jsou)."""

    def __init__(self, parent: QWidget | None, settings: RtSettings) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nastavení RT – zdroj a detektor")
        self._original = settings
        layout = QVBoxLayout(self)
        hint = QLabel("Jen geometrie projekce: kam se vejde zdroj a detektor, kudy vedou přímé "
                      "paprsky a jakou tloušťku prozařují. Hodnoty označené „zvoleno pro výpočet“ "
                      "nejsou z normy – nastav je podle svého zdroje a detektoru.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.test_class = QComboBox()
        self.test_class.setObjectName("rt_class")
        for key, label in CLASSES.items():
            self.test_class.addItem(label, key)
        self.test_class.setCurrentIndex(self.test_class.findData(settings.test_class))
        form.addRow("Třída zkoušky:", self.test_class)
        form.addRow("", _note(f"{RATIO_SOURCE}; nejmenší vzdálenost zdroje: {FMIN_SOURCE}"))
        self.edits: dict[str, QLineEdit] = {}
        for key, label, source in FIELDS:
            edit = QLineEdit(_text(getattr(settings, key)))
            edit.setObjectName(f"rt_{key}")
            edit.setToolTip(source)
            self.edits[key] = edit
            form.addRow(label + ":", edit)
            form.addRow("", _note(source))
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("rt_error")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c0392b;")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def settings(self) -> RtSettings:
        """Nastavení z polí (zkontrolované jádrem); chyba = ``RtError`` česky."""
        labels = {key: label for key, label, _ in FIELDS}
        values = {key: _number(edit.text(), labels[key], key in OPTIONAL)
                  for key, edit in self.edits.items()}
        return replace(self._original, test_class=self.test_class.currentData(), **values)

    def accept(self) -> None:
        try:
            self.settings()
        except RtError as exc:
            self.error.setText(str(exc))  # dialog zůstane otevřený s chybou
            return
        super().accept()


class ProjectionDialog(QDialog):
    """Jedna projekce: zaměřený bod, směr ke zdroji jako sklon a natočení vůči vztažné kolmici
    (``normal`` – kolmice k ploše v zaměřeném bodě, nebo nejbližší osa), vzdálenost, detektor."""

    def __init__(self, parent: QWidget | None, projection: Projection,
                 normal: tuple[float, ...], tilt: float, turn: float, reference: str,
                 hint: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Projekce RT {projection.name}")
        self._original = projection
        self._normal = normal
        self._angles = (_angle(tilt), _angle(turn))
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(projection.name)
        self.name.setObjectName("rt_name")
        form.addRow("Název:", self.name)
        self.aim = QLineEdit("; ".join(_text(v) for v in projection.aim))
        self.aim.setObjectName("rt_aim")
        form.addRow("Zaměřený bod x; y; z [mm]:", self.aim)
        form.addRow("", _note("Bod oblasti, na který míří střední paprsek (obvykle střed svaru "
                              "na straně zdroje)."))
        self.tilt = QLineEdit(self._angles[0])
        self.tilt.setObjectName("rt_tilt")
        form.addRow(f"Sklon od {reference} [°]:", self.tilt)
        self.turn = QLineEdit(self._angles[1])
        self.turn.setObjectName("rt_turn")
        form.addRow("Natočení sklonu [°]:", self.turn)
        form.addRow("", _note(ANGLE_NOTE))
        self.distance = QLineEdit(_text(projection.distance_mm))
        self.distance.setObjectName("rt_distance")
        form.addRow("Vzdálenost zdroje od zaměřeného bodu [mm]:", self.distance)
        if hint:
            form.addRow("", _note(hint))
        self.detector = QComboBox()
        self.detector.setObjectName("rt_detector")
        for key, label in DETECTOR_MODES.items():
            self.detector.addItem(label, key)
        self.detector.setCurrentIndex(self.detector.findData(projection.detector))
        self.detector.currentIndexChanged.connect(lambda _index: self._detector_changed())
        form.addRow("Detektor:", self.detector)
        self.detector_distance = QLineEdit(_text(projection.detector_distance_mm))
        self.detector_distance.setObjectName("rt_detector_distance")
        form.addRow("Detektor volně – vzdálenost od zdroje [mm]:", self.detector_distance)
        self.detector_angle = QLineEdit(_text(projection.detector_angle_deg))
        self.detector_angle.setObjectName("rt_detector_angle")
        form.addRow("Natočení delší strany detektoru [°]:", self.detector_angle)
        self.reference = QLineEdit(_text(projection.reference_mm))
        self.reference.setObjectName("rt_reference")
        form.addRow("Jmenovitá prozařovaná tloušťka [mm]:", self.reference)
        form.addRow("", _note("Prázdné = tloušťka na středním paprsku. Zadej, když střední paprsek "
                              "míří do otvoru nebo přes hranu (u šikmé projekce šikmou "
                              "tloušťku, např. 20 / cos 30° = 23,09)."))
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("rt_error")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c0392b;")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._detector_changed()

    def _detector_changed(self) -> None:
        self.detector_distance.setEnabled(self.detector.currentData() == "free")

    def projection(self) -> Projection:
        """Projekce z polí (zkontrolovaná jádrem); chyba = ``RtError`` česky."""
        parts = [p for p in self.aim.text().replace(",", ".").split(";") if p.strip()]
        try:
            aim = tuple(float(p) for p in parts)
        except ValueError:
            aim = ()
        if len(aim) != 3:
            raise RtError("Zaměřený bod: zadej tři čísla oddělená středníkem, např. 0; 0; 20.")
        if (self.tilt.text().strip(), self.turn.text().strip()) == self._angles:
            direction = self._original.direction  # beze změny – žádné zaokrouhlení
        else:
            tilt = _number(self.tilt.text(), "Sklon")
            turn = _number(self.turn.text(), "Natočení sklonu")
            if not 0 <= tilt < 90:
                raise RtError("Sklon musí být od 0° do méně než 90°.")
            direction = tilted(self._normal, tilt, turn)
        free = self.detector.currentData() == "free"
        return Projection(
            self.name.text(), aim, direction,
            _number(self.distance.text(), "Vzdálenost zdroje"), self.detector.currentData(),
            _number(self.detector_angle.text(), "Natočení detektoru"),
            _number(self.detector_distance.text(), "Vzdálenost detektoru", optional=not free)
            if free else None,
            _number(self.reference.text(), "Jmenovitá tloušťka", optional=True))

    def accept(self) -> None:
        try:
            self.projection()
        except RtError as exc:
            self.error.setText(str(exc))
            return
        super().accept()


def _angle(value: float) -> str:
    """Úhel pro pole dialogu: na 4 desetinná místa (29,999999 → 30)."""
    return f"{round(value, 4) + 0.0:g}".replace(".", ",")
