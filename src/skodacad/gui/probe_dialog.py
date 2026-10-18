"""Dialog sondy NDT studie (etapy 03, 04 a 08).

Druh, rozměry, výstupní bod, úhel paprsku, odrazy a meze přiložení jako dosud. Etapa 08 přidává
**profil** z knihovny (obecné profily, Moje sondy), **původ hodnot** (z profilu, změřeno,
zadáno ručně), materiál, ve kterém platí úhel, jen informativní frekvenci a průměr měniče,
zdroj údajů, pomůcku *Úhel ze Snellova zákona* a **Uložit do Mých sond**. Dialog nic
nepočítá s dílem – vrátí záznam ``device`` pro ``ModelSession.set_ndt_device``. Nezměněné
*OK* vrátí totožný záznam (bez kroku Zpět).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from skodacad.ndt.devices import KINDS, ORIGINS, DeviceError, Probe
from skodacad.ndt.library import (
    BUILTIN,
    MATERIALS,
    PROBES,
    USER_LIBRARY,
    LibraryError,
    UserLibrary,
)
from skodacad.ndt.ut import WAVES, BeamError, refract

MEASURABLE = ("front", "beam_angle")  # ověřují se na kalibračním bloku (č. 1 / č. 2)
CUSTOM = ""  # položka „Vlastní (bez profilu)“
IN_STUDY = "study"  # profil uložený ve studii, který už v knihovně není


class ProbeDialog(QDialog):
    """Nastavení virtuální sondy studie: profil, druh, rozměry, výstupní bod, úhel paprsku,
    odrazy, mezera, rezerva a původ hodnot."""

    FIELDS = (("diameter", "Průměr [mm]", ("straight",)), ("length", "Délka [mm]", ("angle",)),
              ("width", "Šířka [mm]", ("angle",)), ("height", "Výška [mm]", None),
              ("front", "Výstupní bod od čela [mm]", ("angle",)),
              ("beam_angle", "Úhel paprsku v materiálu β [°]", ("angle",)),
              ("max_gap", "Dovolená mezera pod sondou [mm]", None),
              ("reserve", "Manipulační rezerva [mm]", None))
    LIMITS = ("max_gap", "reserve")  # meze přiložení – nejsou vlastnost sondy, původ nemají

    def __init__(self, probe: Probe, parent: QWidget | None = None, *,
                 library: UserLibrary | None = None,
                 save: Callable[[str, Probe], Probe] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sonda NDT studie")
        self._original = probe
        self._reference: Probe | None = probe  # podle ní se určuje původ hodnot
        self._note = probe.angle_note  # platí jen pro úhel a materiál, ke kterým vznikla
        self._note_for = (float(probe.beam_angle), probe.angle_material)
        self._library = library or UserLibrary(Path())
        self._save = save
        form = QFormLayout(self)
        note = QLabel("Obecná virtuální sonda – ne katalogový výrobek. Mezera 0,5 mm odpovídá "
                      "EN ISO 17640 (nejde o tvrzení o shodě). Úhel a výstupní bod skutečné "
                      "sondy se ověřují na kalibračním bloku – pak zaškrtni „změřeno“.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        form.addRow(note)
        self.profile = QComboBox()
        self.profile.setObjectName("probe_profile")
        self._profiles: dict[str, Probe] = {}
        self._fill_profiles(probe)
        self.profile.currentIndexChanged.connect(lambda _index: self._profile_chosen())
        form.addRow("Profil", self.profile)
        self.kind = QComboBox()
        self.kind.setObjectName("probe_kind")
        for key, label in KINDS.items():
            self.kind.addItem(label.capitalize(), key)
        self.kind.setCurrentIndex(self.kind.findData(probe.kind))
        form.addRow("Druh", self.kind)
        self.fields: dict[str, QDoubleSpinBox] = {}
        self.labels: dict[str, QLabel] = {}
        self.rows: dict[str, QWidget] = {}
        self.origins: dict[str, QLabel] = {}
        self.measured: dict[str, QCheckBox] = {}
        for key, label, _kinds in self.FIELDS:
            field = QDoubleSpinBox()
            field.setObjectName(f"probe_{key}")
            field.setDecimals(2)
            field.setRange(1.0 if key == "beam_angle" else 0.0,
                           85.0 if key == "beam_angle" else 1000.0)
            field.setValue(float(getattr(probe, key)))
            field.valueChanged.connect(lambda _value: self._show_origins())
            self.fields[key] = field
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.addWidget(field)
            if key not in self.LIMITS:
                origin = QLabel()
                origin.setObjectName(f"probe_origin_{key}")
                origin.setStyleSheet("color: #555;")
                self.origins[key] = origin
                line.addWidget(origin)
            if key in MEASURABLE:
                box = QCheckBox("změřeno")
                box.setObjectName(f"probe_measured_{key}")
                box.setChecked(probe.origin(key) == "measured")
                box.toggled.connect(lambda _checked: self._show_origins())
                self.measured[key] = box
                line.addWidget(box)
            line.addStretch()
            self.rows[key] = row
            self.labels[key] = QLabel(label)
            form.addRow(self.labels[key], row)
        self.angle_material = QComboBox()
        self.angle_material.setObjectName("probe_angle_material")
        self.angle_material.addItem("přímo v materiálu dílu", "")
        for material in [*MATERIALS.values(), *self._library.materials.values()]:
            self.angle_material.addItem(material.name, material.name)
        self._select(self.angle_material, probe.angle_material, f"{probe.angle_material}")
        self.angle_material.currentIndexChanged.connect(lambda _index: self._show_origins())
        self.angle_material_label = QLabel("Úhel platí v materiálu")
        form.addRow(self.angle_material_label, self.angle_material)
        self.bounces = QSpinBox()
        self.bounces.setObjectName("probe_bounces")
        self.bounces.setRange(0, 10)
        self.bounces.setValue(int(probe.bounces))
        form.addRow("Počet odrazů v dílu", self.bounces)
        self.frequency = self._info_field("probe_frequency", probe.frequency_mhz, 50, " MHz")
        form.addRow("Frekvence (jen informativně)", self.frequency)
        self.crystal = self._info_field("probe_crystal", probe.crystal_mm, 100, " mm")
        form.addRow("Průměr měniče (jen informativně)", self.crystal)
        self.source = QLineEdit(probe.source)
        self.source.setObjectName("probe_source")
        self.source.setPlaceholderText("např. katalogový list, protokol měření na bloku č. 1")
        form.addRow("Zdroj údajů", self.source)
        form.addRow(self._snell_box())
        self.save_button = QPushButton("Uložit do Mých sond…")
        self.save_button.setObjectName("probe_save")
        self.save_button.setEnabled(save is not None)
        self.save_button.clicked.connect(self.save_to_library)
        form.addRow(self.save_button)
        self.error = QLabel("\n".join(self._library.problems))
        self.error.setObjectName("probe_error")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c0392b;")
        form.addRow(self.error)
        self.kind.currentIndexChanged.connect(
            lambda _index: self._kind_changed(switched=True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self._kind_changed()

    # --- stavba ---------------------------------------------------------------------------

    def _fill_profiles(self, probe: Probe) -> None:
        self.profile.addItem("Vlastní (bez profilu)", CUSTOM)
        for key, profile in PROBES.items():
            self.profile.addItem(profile.name, f"builtin:{key}")
            self._profiles[f"builtin:{key}"] = profile.probe
        for name, stored in self._library.probes.items():
            self.profile.addItem(f"{name} ({USER_LIBRARY})", f"user:{name}")
            self._profiles[f"user:{name}"] = stored
        current = CUSTOM
        if probe.profile:
            current = next((data for data, stored in self._profiles.items()
                            if stored.profile == probe.profile
                            and stored.library == probe.library), IN_STUDY)
            if current == IN_STUDY:
                self.profile.addItem(f"{probe.profile} (ve studii)", IN_STUDY)
                self._profiles[IN_STUDY] = probe
        self.profile.setCurrentIndex(self.profile.findData(current))

    def _info_field(self, name: str, value: float, high: float, suffix: str) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setObjectName(name)
        field.setDecimals(1)
        field.setRange(0, high)
        field.setSuffix(suffix)
        field.setSpecialValueText("neuvedeno")
        field.setValue(value)
        return field

    def _snell_box(self) -> QGroupBox:
        box = QGroupBox("Úhel ze Snellova zákona (rychlosti zadej sám)")
        layout = QFormLayout(box)
        self.snell_alpha = QLineEdit()
        self.snell_alpha.setObjectName("probe_snell_alpha")
        self.snell_alpha.setPlaceholderText("úhel v předsádce, např. 36,4")
        layout.addRow("α v předsádce [°]", self.snell_alpha)
        self.snell_c1 = QLineEdit()
        self.snell_c1.setObjectName("probe_snell_c1")
        self.snell_c1.setPlaceholderText("rychlost v předsádce, např. 2730")
        layout.addRow("c₁ předsádka [m/s]", self.snell_c1)
        self.snell_c2 = QLineEdit()
        self.snell_c2.setObjectName("probe_snell_c2")
        self.snell_c2.setPlaceholderText("rychlost v materiálu dílu, např. 3240")
        layout.addRow("c₂ materiál [m/s]", self.snell_c2)
        self.snell_wave = QComboBox()
        self.snell_wave.setObjectName("probe_snell_wave")
        for key, label in WAVES.items():
            self.snell_wave.addItem(f"{label} vlna", key)
        layout.addRow("Druh vlny", self.snell_wave)
        compute = QPushButton("Spočítat úhel β")
        compute.setObjectName("probe_snell_compute")
        compute.clicked.connect(self.compute_snell)
        self.snell_result = QLabel()
        self.snell_result.setObjectName("probe_snell_result")
        self.snell_result.setWordWrap(True)
        layout.addRow(compute, self.snell_result)
        self.snell_box = box
        return box

    @staticmethod
    def _select(combo: QComboBox, value: str, label: str) -> None:
        index = combo.findData(value)
        if index < 0:  # materiál ze souboru, který v knihovně není – nesmí se ztratit
            combo.addItem(label, value)
            index = combo.count() - 1
        combo.setCurrentIndex(index)

    # --- chování -------------------------------------------------------------------------

    def _kind_changed(self, switched: bool = False) -> None:
        kind = self.kind.currentData()
        for key, _label, kinds in self.FIELDS:
            shown = kinds is None or kind in kinds
            self.rows[key].setVisible(shown)
            self.labels[key].setVisible(shown)
        for widget in (self.angle_material, self.angle_material_label, self.snell_box):
            widget.setVisible(kind == "angle")
        if switched:
            if kind == "straight" and self.bounces.value() == 1:
                self.bounces.setValue(0)
            elif kind == "angle" and self.bounces.value() == 0:
                self.bounces.setValue(1)
        self._show_origins()

    def _profile_chosen(self) -> None:
        """Profil z knihovny vyplní rozměry, úhel a materiál úhlu (meze přiložení zůstanou)."""
        data = self.profile.currentData()
        chosen = self._profiles.get(data)
        if chosen is None:  # Vlastní (bez profilu): hodnoty zůstanou, původ se nesleduje
            self._reference = None
            self._show_origins()
            return
        self._reference = chosen
        self.kind.setCurrentIndex(self.kind.findData(chosen.kind))
        for key, _label, kinds in self.FIELDS:
            if key not in self.LIMITS and (kinds is None or chosen.kind in kinds):
                self.fields[key].setValue(float(getattr(chosen, key)))
        for key, box in self.measured.items():
            box.setChecked(chosen.origin(key) == "measured")
        self._select(self.angle_material, chosen.angle_material, chosen.angle_material)
        self.frequency.setValue(chosen.frequency_mhz)
        self.crystal.setValue(chosen.crystal_mm)
        self.source.setText(chosen.source)
        self._remember_note(chosen.angle_note)
        self._show_origins()

    def _remember_note(self, note: str) -> None:
        self._note = note
        self._note_for = (self.fields["beam_angle"].value(), self.angle_material.currentData())

    def _origin(self, key: str) -> str:
        """Původ hodnoty: změřeno (zaškrtnuto), jinak podle profilu, jinak zadáno ručně."""
        if key in self.measured and self.measured[key].isChecked():
            return "measured"
        reference = self._reference
        if reference is None or reference.kind != self.kind.currentData():
            return ""
        same = abs(self.fields[key].value() - float(getattr(reference, key))) < 1e-9
        tracked = bool(reference.origins or reference.profile)
        if same:
            found = reference.origin(key)
            return "entered" if found == "measured" else found
        return "entered" if tracked else ""

    def _show_origins(self) -> None:
        for key, label in self.origins.items():
            origin = self._origin(key)  # „změřeno“ ukazuje zaškrtávátko vedle
            label.setText(ORIGINS[origin] if origin and origin != "measured" else "")

    def compute_snell(self) -> None:
        """β ze Snellova zákona se zadanými rychlostmi; úhel pak platí v materiálu dílu."""
        try:
            values = [float(edit.text().replace(",", ".").strip())
                      for edit in (self.snell_alpha, self.snell_c1, self.snell_c2)]
            refraction = refract(*values, self.snell_wave.currentData())
        except ValueError as exc:  # i BeamError
            message = (str(exc) if isinstance(exc, BeamError)
                       else "Vyplň úhel α a obě rychlosti čísly.")
            self.snell_result.setStyleSheet("color: #c0392b;")
            self.snell_result.setText(message)
            return
        self.snell_result.setStyleSheet("")
        self.snell_result.setText(refraction.label)
        self.measured["beam_angle"].setChecked(False)
        self.fields["beam_angle"].setValue(round(refraction.beta, 2))
        self._select(self.angle_material, "", "")
        self._remember_note(refraction.label)
        self._show_origins()

    def save_to_library(self) -> None:
        """Uloží sondu z dialogu do Mých sond a zvolí ji jako profil."""
        if self._save is None:
            return
        suggested = self._original.profile if self._original.library == USER_LIBRARY else ""
        name, ok = QInputDialog.getText(self, "Uložit do Mých sond", "Název sondy:",
                                        text=suggested)
        if not ok or not name.strip():
            return
        try:
            stored = self._save(name.strip(), Probe.from_dict(self.values()))
        except (DeviceError, LibraryError) as exc:
            self.error.setText(f"Sondu nejde uložit: {exc}")
            return
        data = f"user:{stored.profile}"
        self._profiles[data] = stored
        index = self.profile.findData(data)
        self.profile.blockSignals(True)
        if index < 0:
            self.profile.addItem(f"{stored.profile} ({USER_LIBRARY})", data)
            index = self.profile.count() - 1
        self.profile.setCurrentIndex(index)
        self.profile.blockSignals(False)
        self._reference = stored
        self.error.setText(f"Uloženo do Mých sond jako „{stored.profile}“.")
        self._show_origins()

    def values(self) -> dict[str, Any]:
        kind = self.kind.currentData()
        data: dict[str, Any] = {
            "kind": kind,
            **{key: self.fields[key].value() for key, _label, kinds in self.FIELDS
               if kinds is None or kind in kinds},
            "bounces": self.bounces.value()}
        origins = {key: origin for key, _label, kinds in self.FIELDS
                   if key not in self.LIMITS and (kinds is None or kind in kinds)
                   and (origin := self._origin(key))}
        profile, library = self._profile_name()
        angle = kind == "angle"
        material = self.angle_material.currentData() if angle else ""
        beta, noted_material = self._note_for
        # Poznámka (např. „přepočteno z 70° v oceli“) jen k úhlu a materiálu, ke kterým vznikla.
        note = self._note if (angle and abs(self.fields["beam_angle"].value() - beta) < 1e-9
                              and material == noted_material) else ""
        wave = self._original.wave if self._original.kind == kind else ""
        meta = {"profile": profile, "library": library, "origins": origins,
                "angle_material": material, "angle_note": note, "wave": wave,
                "frequency_mhz": self.frequency.value(), "crystal_mm": self.crystal.value(),
                "source": self.source.text().strip()}
        data.update({key: value for key, value in meta.items() if value})
        return data

    def _profile_name(self) -> tuple[str, str]:
        data = self.profile.currentData()
        if data == CUSTOM:
            return "", ""
        if data == IN_STUDY:
            return self._original.profile, self._original.library
        if data.startswith("builtin:"):
            return PROBES[data.removeprefix("builtin:")].name, BUILTIN
        return data.removeprefix("user:"), USER_LIBRARY
