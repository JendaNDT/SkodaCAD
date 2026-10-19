"""Panel NDT: studie nedestruktivní kontroly v modelu a virtuální sonda (etapy 01 a 03).

Seznam studií se stavem (✓ platná, ⚠ zastaralá / neúplná, ✕ neplatná vazba), nová studie
z ploch vybraných ve 3D, úpravy a ověření. Všechno jde přes ``ModelSession`` (jeden krok Zpět
na úpravu); panel sám nic nepočítá. Klik na studii zvýrazní ve 3D kontrolovanou oblast.
U UT studie jde nastavit sondu (uloží se do studie) a přiložit ji kliknutím na plochu – sonda
se ve 3D nakreslí v barvě výsledku (jen pohled, do modelu se neukládá). U UT (vybraná studie,
bez výběru metoda nové studie) je nahoře povinné upozornění ``UT_DISCLAIMER``
(``docs/ndt/04-zavazne-vymezeni-ut.md``), u PT ``PT_DISCLAIMER`` (``20-vymezeni-pt.md``),
jinak obecné ``DISCLAIMER``. U PT studie je místo skupin sondy skupina *Přístupnost povrchu pro
PT* (etapa 11): nastavení, mapa ve 3D po kontrolách, souhrn a důvod místa po kliknutí.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skodacad.document import DocumentError
from skodacad.gui.probe_dialog import ProbeDialog
from skodacad.gui.pt_dialog import PtDialog
from skodacad.gui.target_dialog import TargetDialog
from skodacad.gui.zone_dialog import ZoneDialog
from skodacad.materials import material_key
from skodacad.ndt import (
    DISCLAIMER,
    PT_ACCESS,
    PT_DISCLAIMER,
    PT_MAP,
    UT_ACCESS,
    UT_COVERAGE,
    UT_DISCLAIMER,
)
from skodacad.ndt.access import (
    ALTERNATIVE_ANGLES,
    CONTACT_COLORS,
    CONTACT_STATES,
    KINDS,
    NOT_FOUND_NOTE,
    ORDER_NOTE,
    AccessEstimate,
)
from skodacad.ndt.coverage import PERCENT_NOTE, STATES, CoverageMap
from skodacad.ndt.library import (
    MATERIALS,
    UserLibrary,
    describe,
    load_user_library,
    save_user_probe,
    user_library_path,
)
from skodacad.ndt.plan import (
    EDGE_MM,
    PATTERN_CHOICES,
    PLAN_NOTE,
    STEP_COLORS,
    ZONE_COLOR,
    PlanError,
    PlanEstimate,
)
from skodacad.ndt.pt import CHECKS as PT_CHECKS
from skodacad.ndt.pt import COLORS as PT_COLORS
from skodacad.ndt.pt import GRADE_COLORS as PT_GRADE_COLORS
from skodacad.ndt.pt import GRADES as PT_GRADES
from skodacad.ndt.pt import STATES as PT_STATES
from skodacad.ndt.pt import PtError, PtMap
from skodacad.ndt.study import METHODS, StudyResult
from skodacad.ndt.volume_coverage import VolumeCoverageMap
from skodacad.ndt.volume_drawing import UNRESOLVED_LABEL
from skodacad.ndt.welds import WELD_TYPES
from skodacad.session import CoverageEstimate

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
PT_PICK_HINT = "Klikni ve 3D do mapy – napíšu, proč je místo omezené nebo nepřístupné."


def _swatches(colors: dict, labels: dict) -> str:
    """Legenda barev mapy (čtverečky v barvě a popis)."""
    def hex_color(rgb: tuple) -> str:
        return "#" + "".join(f"{round(255 * v):02x}" for v in rgb)

    return " · ".join(f'<span style="color: {hex_color(colors[key])};">■</span> {escape(label)}'
                      for key, label in labels.items() if key in colors)


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
        self.cross_section_action = action("Průřez svarem", self.cross_section)
        self.cross_section_action.setToolTip(
            "Řez kolmo na osu cílového objemu uprostřed jeho délky; posuvníkem v panelu Řez "
            "jedeš podél svaru (jen pohled)")
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
        self.transfer_action = action("Přepočítat úhel", self.transfer_angle)
        self.transfer_action.setToolTip(
            "Úhel sondy platí v jiném materiálu – přepočti ho Snellovým zákonem do materiálu "
            "pro UT (jeden krok Zpět)")
        self.part_material_action = action("Použít materiál dílu", self.use_part_material)
        self.part_material_action.setToolTip(
            "Materiál pro UT = materiál dílu z vestavěné knihovny (orientační rychlosti)")
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
        self.access_action = action("Navrhnout polohy", self.start_access)
        self.access_action.setToolTip(
            "Program sám vyzkouší rovinné plochy, směry, úhly a odrazy a seřadí varianty podle "
            "geometrického pokrytí (jen pohled, model se nemění)")
        self.access_stop_action = action("Zastavit", self.stop_access)
        self.access_stop_action.setToolTip("Zastaví návrh poloh; hotové varianty zůstanou")
        self.access_show_action = action("Ukázat variantu", self.show_variant)
        self.access_show_action.setToolTip(
            "Přiloží sondu do nejlepší polohy vybrané varianty – jen pohled, model se nemění")
        self.access_apply_action = action("Použít variantu", self.apply_variant)
        self.access_apply_action.setToolTip(
            "Uloží úhel a odrazy varianty do studie (jeden krok Zpět) a přiloží sondu; pak "
            "Spočítat pokrytí stejným krokem dá totéž číslo")
        self.access_export_action = action("Export CSV…", self.export_access)
        # plán dráhy sondy (etapa 10)
        self.plan_action = action("Naplánovat dráhu", self.start_plan)
        self.plan_action.setToolTip(
            "Sestaví souvislou dráhu sondy (řádky tam a zpět) z přiložené sondy nebo z varianty "
            "návrhu poloh, zkontroluje ji po 1 mm, spočítá pokrytí a uloží do studie (jeden "
            "krok Zpět)")
        self.plan_check_action = action("Ověřit a spočítat", self.check_plan)
        self.plan_check_action.setToolTip(
            "Ověří uložený plán na současném dílu a spočítá geometrické pokrytí. Zastaralý "
            "plán, který celou kontrolou projde, převezme současný díl (jeden krok Zpět).")
        self.plan_stop_action = action("Zastavit", self.stop_plan)
        self.plan_stop_action.setToolTip("Zastaví výpočet plánu; uložený plán zůstane beze změny")
        self.plan_export_action = action("Export CSV…", self.export_plan)
        self.plan_remove_action = action("Smazat úsek", self.remove_plan_segment)
        self.plan_reverse_action = action("Obrátit", self.reverse_plan_segment)
        self.plan_reverse_action.setToolTip("Sonda pojede úsekem opačně")
        self.plan_up_action = action("Nahoru", lambda: self.move_plan_segment(-1))
        self.plan_up_action.setToolTip("Úsek dřív v pořadí jízdy")
        self.plan_down_action = action("Dolů", lambda: self.move_plan_segment(1))
        self.plan_down_action.setToolTip("Úsek později v pořadí jízdy")
        self.plan_edit_action = action("Upravit…", self.edit_plan_segment)
        self.plan_edit_action.setToolTip(
            "Začátek a konec úseku v mm (zkrátit, prodloužit, posunout)")
        self.plan_add_action = action("Přidat z přiložené sondy", self.add_plan_segment)
        self.plan_add_action.setToolTip(
            "Nový úsek od výstupního bodu přiložené sondy ve směru paprsku, délka jako Délka čáry")
        self.plan_zones_action = action("Zakázané zóny…", self.edit_zones)
        self.plan_zones_action.setToolTip("Kvádry, kam sonda nesmí (štítek, upínka …)")
        self.plan_delete_action = action("Smazat plán", self.delete_plan)
        self.plan_prune_action = action("Smazat úseky bez přínosu", self.prune_plan)
        self.plan_prune_action.setToolTip(
            "Smaže úseky, ze kterých paprsek žádný vzorek cíle nezasáhne jako první (sloupec "
            "Přínos = 0); pokrytí se tím nezmenší – ověří ho Ověřit a spočítat")
        self.plan_play_action = action("Přehrát", self.toggle_play)
        self.plan_play_action.setCheckable(True)
        self.plan_play_action.setToolTip("Sonda s paprskem jede po dráze, mapa pokrytí narůstá")
        self.plan_prev_action = action("◀", lambda: self.step_plan(-1))
        self.plan_prev_action.setToolTip("Předchozí poloha plánu")
        self.plan_next_action = action("▶", lambda: self.step_plan(1))
        self.plan_next_action.setToolTip("Další poloha plánu")
        # PT – přístupnost povrchu (etapa 11)
        self.pt_settings_action = action("Nastavení PT…", self.edit_pt_settings)
        self.pt_settings_action.setToolTip(
            "Nástroje, úhly nástřiku a prohlídky, oko a postup čištění (uloží se do studie, "
            "jeden krok Zpět)")
        self.pt_action = action("Spočítat mapu PT", self.start_pt)
        self.pt_action.setToolTip(
            "Pro plochy studie zjistí nástřik, otření nástrojem a prohlídku (jen geometrie, "
            "model se nemění)")
        self.pt_stop_action = action("Zastavit", self.stop_pt)
        self.pt_clear_action = action("Skrýt mapu", self.clear_pt)
        self.pt_export_action = action("Export CSV…", self.export_pt)

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
        for row in ((self.target_action, self.volume_action, self.cross_section_action),
                    (self.rename_action, self.method_action, self.note_action),
                    (self.confirm_action, self.verify_action, self.unverify_action),
                    (self.duplicate_action, self.delete_action)):
            buttons = QHBoxLayout()
            for item in row:
                buttons.addWidget(window._tool_button(item))
            buttons.addStretch()
            layout.addLayout(buttons)
        self._build_pt(layout)
        probe_box = QGroupBox(UT_ACCESS)
        probe_box.setObjectName("ndt_ut")
        self.probe_box = probe_box
        probe_layout = QVBoxLayout(probe_box)
        self.probe_label = QLabel()
        self.probe_label.setObjectName("ndt_probe")
        self.probe_label.setWordWrap(True)
        probe_layout.addWidget(self.probe_label)
        material_row = QHBoxLayout()  # materiál pro UT (etapa 08)
        material_row.addWidget(QLabel("Materiál pro UT:"))
        self.ut_material = QComboBox()
        self.ut_material.setObjectName("ndt_ut_material")
        self.ut_material.setToolTip(
            "Rychlosti zvuku pro přepočet úhlu sondy. Vestavěné hodnoty jsou orientační "
            "(dva zdroje); vlastní materiál si ulož do Mých sond.")
        self.ut_material.currentIndexChanged.connect(lambda _index: self._ut_material_chosen())
        material_row.addWidget(self.ut_material, stretch=1)
        probe_layout.addLayout(material_row)
        self.material_label = QLabel()
        self.material_label.setObjectName("ndt_ut_material_info")
        self.material_label.setWordWrap(True)
        self.material_label.setStyleSheet("color: #555;")
        probe_layout.addWidget(self.material_label)
        self.angle_check_label = QLabel()
        self.angle_check_label.setObjectName("ndt_angle_check")
        self.angle_check_label.setWordWrap(True)
        self.angle_check_label.setStyleSheet("color: #b9770e;")
        probe_layout.addWidget(self.angle_check_label)
        buttons = QHBoxLayout()
        for item in (self.transfer_action, self.part_material_action):
            buttons.addWidget(window._tool_button(item))
        buttons.addStretch()
        probe_layout.addLayout(buttons)
        self._library_cache: tuple[tuple, UserLibrary] | None = None
        for pair in ((self.probe_action, self.place_action),  # po dvou – vejde se do doku
                     (self.drag_probe_action, self.remove_probe_action)):
            buttons = QHBoxLayout()
            for item in pair:
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
        angle_row.addStretch()
        probe_layout.addLayout(angle_row)
        angle_row = QHBoxLayout()  # krokování na vlastním řádku – vejde se do doku
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
        # Objemový cíl (07C): krok cíle a tolerance; u ploch jsou řádky skryté.
        self.coverage_target_step = QDoubleSpinBox()
        self.coverage_target_step.setObjectName("ndt_coverage_target_step")
        self.coverage_target_step.setRange(0.5, 100)
        self.coverage_target_step.setDecimals(1)
        self.coverage_target_step.setValue(4.0)  # při výběru studie se nastaví doporučený
        self.coverage_target_step.setToolTip(
            "Hrana objemové buňky cíle. Doporučeno: šestina menšího rozměru průřezu cíle "
            "(jemnější = přesnější, ale delší výpočet)")
        self._target_step_key: tuple | None = None  # pro který cíl je nastaven doporučený
        form.addRow("Krok cíle [mm]:", self.coverage_target_step)
        self.coverage_spread = QDoubleSpinBox()
        self.coverage_spread.setRange(0, 45)
        self.coverage_spread.setValue(0)
        form.addRow("Rozevření (poloviční úhel) [°]:", self.coverage_spread)
        self.tolerance_box = QWidget()
        tolerance_row = QHBoxLayout(self.tolerance_box)
        tolerance_row.setContentsMargins(0, 0, 0, 0)
        self.coverage_tolerance_auto = QCheckBox("automaticky")
        self.coverage_tolerance_auto.setObjectName("ndt_coverage_tolerance_auto")
        self.coverage_tolerance_auto.setChecked(True)
        self.coverage_tolerance = QDoubleSpinBox()
        self.coverage_tolerance.setObjectName("ndt_coverage_tolerance")
        self.coverage_tolerance.setRange(0.1, 1000)
        self.coverage_tolerance.setDecimals(2)
        self.coverage_tolerance.setValue(3.54)
        self.coverage_tolerance.setEnabled(False)
        tolerance_row.addWidget(self.coverage_tolerance_auto)
        tolerance_row.addWidget(self.coverage_tolerance)
        self.tolerance_box.setToolTip(
            "Vyhledávací pomůcka, ne šířka svazku. Automaticky = krok pojezdu × 0,71 (po ploše) "
            "nebo × 0,6 (po čáře). Každý zásah se dál ověří skutečným přiložením sondy.")
        form.addRow("Tolerance zachycení [mm]:", self.tolerance_box)
        self.coverage_convergence = QCheckBox("Ověřit citlivost na krok")
        self.coverage_convergence.setObjectName("ndt_coverage_convergence")
        self.coverage_convergence.setChecked(True)
        self.coverage_convergence.setToolTip(
            "Navíc hrubší výpočet: porovná výsledek s dvojnásobnými kroky (hrubší výpočet "
            "hledá paprsky podle svých kroků). Trvá zhruba o polovinu déle. Bez porovnání "
            "panel napíše „Citlivost na krok neověřena“.")
        form.addRow(self.coverage_convergence)
        # Dlouhý popisek nad pole, když je dok úzký (jinak by se panel posouval do strany).
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.coverage_form = form
        coverage_layout.addLayout(form)
        self.coverage_estimate = QLabel()
        self.coverage_estimate.setObjectName("ndt_coverage_estimate")
        self.coverage_estimate.setWordWrap(True)
        coverage_layout.addWidget(self.coverage_estimate)
        self._estimate_cache: tuple[tuple, CoverageEstimate] | None = None
        for signal in (self.coverage_mode.currentIndexChanged, self.coverage_step.valueChanged,
                       self.coverage_target_step.valueChanged,
                       self.coverage_spread.valueChanged, self.coverage_convergence.toggled,
                       self.scan_length.valueChanged):
            signal.connect(lambda *_args: self.refresh_actions())
        self.coverage_tolerance_auto.toggled.connect(
            lambda checked: self.coverage_tolerance.setEnabled(not checked))
        row = QHBoxLayout()
        for item in (self.coverage_action, self.clear_coverage_action, self.export_coverage_action):
            row.addWidget(window._tool_button(item))
        coverage_layout.addLayout(row)
        legend = QLabel('<span style="color:#26b340">■ Pokryto</span> · '
                        '<span style="color:#d93326">■ Nepokryto</span> · '
                        '<span style="color:#e6bf26">■ Nelze spolehlivě vyhodnotit</span>')
        legend.setWordWrap(True)
        coverage_layout.addWidget(legend)
        self.volume_legend = QLabel(  # jen u objemového cíle (07C)
            f'<span style="color:#9e9e9e">■ {UNRESOLVED_LABEL}</span> (jen kresba – buňka s více '
            "kusy, které nejde rozlišit; čísla to nemění)")
        self.volume_legend.setObjectName("ndt_volume_legend")
        self.volume_legend.setWordWrap(True)
        coverage_layout.addWidget(self.volume_legend)
        self.coverage_label = QLabel(PERCENT_NOTE)
        self.coverage_label.setObjectName("ndt_coverage_summary")
        self.coverage_label.setWordWrap(True)
        self.coverage_label.setTextFormat(Qt.TextFormat.RichText)
        self.coverage_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        coverage_layout.addWidget(self.coverage_label)
        layout.addWidget(self.coverage_box)
        self._build_access(layout)
        self._build_plan(layout)
        self.details = QLabel()
        self.details.setObjectName("ndt_details")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)
        layout.addStretch()
        self.refresh()

    def _build_pt(self, layout: QVBoxLayout) -> None:
        """Skupina Přístupnost povrchu pro PT (etapa 11): nastavení, výpočet, mapa, důvody."""
        window = self.window
        self.pt_box = QGroupBox(PT_ACCESS)
        self.pt_box.setObjectName("ndt_pt")
        box = QVBoxLayout(self.pt_box)
        self.pt_settings_label = QLabel()
        self.pt_settings_label.setObjectName("ndt_pt_settings")
        self.pt_settings_label.setWordWrap(True)
        box.addWidget(self.pt_settings_label)
        for row_items in ((self.pt_settings_action, self.pt_action, self.pt_stop_action),
                          (self.pt_clear_action, self.pt_export_action)):
            row = QHBoxLayout()
            for item in row_items:
                row.addWidget(window._tool_button(item))
            row.addStretch()
            box.addLayout(row)
        self.pt_estimate = QLabel()
        self.pt_estimate.setObjectName("ndt_pt_estimate")
        self.pt_estimate.setWordWrap(True)
        box.addWidget(self.pt_estimate)
        self._pt_estimate_cache: tuple[tuple, str] | None = None
        show_row = QHBoxLayout()
        show_row.addWidget(QLabel("Ukázat ve 3D:"))
        self.pt_check = QComboBox()
        self.pt_check.setObjectName("ndt_pt_check")
        self.pt_check.addItem("celkem", "")
        for key, label in PT_CHECKS.items():
            self.pt_check.addItem(label.lower(), key)
        self.pt_check.currentIndexChanged.connect(lambda _index: self._pt_check_changed())
        show_row.addWidget(self.pt_check)
        show_row.addStretch()
        box.addLayout(show_row)
        self.pt_legend = QLabel()
        self.pt_legend.setObjectName("ndt_pt_legend")
        self.pt_legend.setWordWrap(True)
        self.pt_legend.setTextFormat(Qt.TextFormat.RichText)
        box.addWidget(self.pt_legend)
        self.pt_summary = QLabel()
        self.pt_summary.setObjectName("ndt_pt_summary")
        self.pt_summary.setWordWrap(True)
        self.pt_summary.setTextFormat(Qt.TextFormat.RichText)
        self.pt_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.pt_summary)
        self.pt_pick = QLabel(PT_PICK_HINT)
        self.pt_pick.setObjectName("ndt_pt_pick")
        self.pt_pick.setWordWrap(True)
        self.pt_pick.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.pt_pick)
        layout.addWidget(self.pt_box)

    def _build_access(self, layout: QVBoxLayout) -> None:
        """Skupina Návrh poloh sondy (etapa 09): volby, odhad, průběh, tabulka, kombinace."""
        window = self.window
        self.access_box = QGroupBox("Návrh poloh sondy")
        self.access_box.setObjectName("ndt_access")
        box = QVBoxLayout(self.access_box)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.access_faces = QComboBox()
        self.access_faces.setObjectName("ndt_access_faces")
        self.access_faces.addItem("všechny rovinné plochy", "all")
        self.access_faces.addItem("plochy vybrané ve 3D", "picked")
        form.addRow("Kontaktní plochy:", self.access_faces)
        self.access_directions = QComboBox()
        self.access_directions.setObjectName("ndt_access_directions")
        for step in (45.0, 30.0, 90.0):
            self.access_directions.addItem(f"po {step:g}° + k cíli a kolmo na svar", step)
        form.addRow("Směry paprsku:", self.access_directions)
        self.access_angles = QCheckBox("zkusit i 45°, 60°, 70° (stejné rozměry sondy)")
        self.access_angles.setObjectName("ndt_access_angles")
        form.addRow(self.access_angles)
        self.access_bounces = QComboBox()
        self.access_bounces.setObjectName("ndt_access_bounces")
        for label, data in (("0 a 1 (půlkrok i celý krok)", "0,1"), ("jen 0", "0"),
                            ("0 až 2", "0,1,2")):
            self.access_bounces.addItem(label, data)
        form.addRow("Odrazy:", self.access_bounces)
        self.access_step = QDoubleSpinBox()
        self.access_step.setObjectName("ndt_access_step")
        self.access_step.setRange(2, 100)
        self.access_step.setDecimals(1)
        self.access_step.setValue(10.0)
        self.access_step.setToolTip("Krok mřížky poloh sondy i pojezdu pro hrubé pokrytí "
                                    "(u ploch i krok cíle). Jemnější = pomalejší.")
        form.addRow("Krok analýzy [mm]:", self.access_step)
        box.addLayout(form)
        self.access_estimate = QLabel()
        self.access_estimate.setObjectName("ndt_access_estimate")
        self.access_estimate.setWordWrap(True)
        box.addWidget(self.access_estimate)
        self._access_estimate_cache: tuple[tuple, AccessEstimate] | None = None
        row = QHBoxLayout()
        for item in (self.access_action, self.access_stop_action, self.access_export_action):
            row.addWidget(window._tool_button(item))
        row.addStretch()
        box.addLayout(row)
        self.access_progress = QLabel()
        self.access_progress.setObjectName("ndt_access_progress")
        self.access_progress.setWordWrap(True)
        box.addWidget(self.access_progress)
        self.access_table = QTableWidget(0, 8)
        self.access_table.setObjectName("ndt_access_table")
        self.access_table.setHorizontalHeaderLabels(
            ["#", "Plocha", "Směr", "β", "Odrazy", "Pokryto", "Platné polohy", "Poznámka"])
        self.access_table.verticalHeader().setVisible(False)
        self.access_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.access_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.access_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.access_table.setMinimumHeight(120)
        self.access_table.setMaximumHeight(240)
        self.access_table.itemSelectionChanged.connect(self.refresh_actions)
        self.access_table.itemDoubleClicked.connect(lambda _item: self.show_variant())
        box.addWidget(self.access_table)
        self.access_combination = QLabel()
        self.access_combination.setObjectName("ndt_access_combination")
        self.access_combination.setWordWrap(True)
        self.access_combination.setTextFormat(Qt.TextFormat.RichText)
        self.access_combination.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.access_combination)
        row = QHBoxLayout()
        for item in (self.access_show_action, self.access_apply_action):
            row.addWidget(window._tool_button(item))
        row.addStretch()
        box.addLayout(row)
        map_row = QHBoxLayout()
        map_row.addWidget(QLabel("Mapa ve 3D:"))
        self.access_map = QComboBox()
        self.access_map.setObjectName("ndt_access_map")
        self.access_map.addItem("cíl – co pokryje kombinace", "target")
        self.access_map.addItem("kontaktní plochy – kde se sonda vejde", "contact")
        self.access_map.addItem("nic", "none")
        self.access_map.currentIndexChanged.connect(lambda _index: self._access_map_changed())
        map_row.addWidget(self.access_map)
        map_row.addStretch()
        box.addLayout(map_row)
        self.access_legend = QLabel()
        self.access_legend.setObjectName("ndt_access_legend")
        self.access_legend.setWordWrap(True)
        box.addWidget(self.access_legend)
        self.access_rejected = QLabel()
        self.access_rejected.setObjectName("ndt_access_rejected")
        self.access_rejected.setWordWrap(True)
        self.access_rejected.setStyleSheet("color: #555;")
        self.access_rejected.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.access_rejected)
        note = QLabel(f"{ORDER_NOTE} {NOT_FOUND_NOTE}")
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a5a00; font-style: italic;")
        box.addWidget(note)
        for signal in (self.access_faces.currentIndexChanged,
                       self.access_directions.currentIndexChanged, self.access_angles.toggled,
                       self.access_bounces.currentIndexChanged, self.access_step.valueChanged):
            signal.connect(lambda *_args: self.refresh_actions())
        layout.addWidget(self.access_box)

    def _build_plan(self, layout: QVBoxLayout) -> None:
        """Skupina Plán dráhy sondy (etapa 10): volby, sestavení, stav, úseky, přehrávání."""
        window = self.window
        self.plan_box = QGroupBox("Plán dráhy sondy")
        self.plan_box.setObjectName("ndt_plan")
        box = QVBoxLayout(self.plan_box)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.plan_source = QComboBox()
        self.plan_source.setObjectName("ndt_plan_source")
        for label, data in (("přiložená sonda", "placement"),
                            ("vybraná varianta návrhu poloh", "variant"),
                            ("kombinace návrhu poloh", "combination")):
            self.plan_source.addItem(label, data)
        form.addRow("Z čeho:", self.plan_source)
        self.plan_pattern = QComboBox()
        self.plan_pattern.setObjectName("ndt_plan_pattern")
        for key, label in PATTERN_CHOICES.items():
            self.plan_pattern.addItem(label, key)
        self.plan_pattern.setToolTip("Automaticky: méně přestavení, pak kratší dráha, pak méně "
                                     "řádků")
        form.addRow("Vzor řádků:", self.plan_pattern)
        self.plan_step = QDoubleSpinBox()
        self.plan_step.setObjectName("ndt_plan_step")
        self.plan_step.setRange(0.5, 100)
        self.plan_step.setDecimals(1)
        self.plan_step.setValue(5.0)
        self.plan_step.setToolTip("Vzdálenost sousedních řádků; řádek se počítá jako spojitě "
                                  "projetý pás této šířky (jako pojezd po ploše)")
        form.addRow("Rozteč řádků [mm]:", self.plan_step)
        self.plan_approach = QDoubleSpinBox()
        self.plan_approach.setObjectName("ndt_plan_approach")
        self.plan_approach.setRange(0, 500)
        self.plan_approach.setDecimals(0)
        self.plan_approach.setValue(20)
        self.plan_approach.setToolTip("O kolik se sonda zvedá a spouští kolmo k ploše; tělo "
                                      "prodloužené o tuto výšku nesmí narazit. 0 = nekontrolovat.")
        form.addRow("Výška nájezdu [mm]:", self.plan_approach)
        self.plan_compare = QCheckBox("porovnat s pojezdem po celé ploše")
        self.plan_compare.setObjectName("ndt_plan_compare")
        self.plan_compare.setToolTip("Další výpočet pokrytí – trvá déle")
        form.addRow(self.plan_compare)
        self.plan_robust = QCheckBox("ověřit odolnost (posun řádků o ± půl rozteče)")
        self.plan_robust.setObjectName("ndt_plan_robust")
        self.plan_robust.setToolTip("Dva další výpočty pokrytí – trvá déle")
        form.addRow(self.plan_robust)
        box.addLayout(form)
        self.plan_estimate = QLabel()
        self.plan_estimate.setObjectName("ndt_plan_estimate")
        self.plan_estimate.setWordWrap(True)
        box.addWidget(self.plan_estimate)
        self._plan_estimate_cache: tuple[tuple, PlanEstimate] | None = None
        for row_items in ((self.plan_action, self.plan_check_action),
                          (self.plan_stop_action, self.plan_export_action)):
            row = QHBoxLayout()
            for item in row_items:
                row.addWidget(window._tool_button(item))
            row.addStretch()
            box.addLayout(row)
        self.plan_progress = QLabel()
        self.plan_progress.setObjectName("ndt_plan_progress")
        self.plan_progress.setWordWrap(True)
        box.addWidget(self.plan_progress)
        self.plan_state = QLabel()
        self.plan_state.setObjectName("ndt_plan_state")
        self.plan_state.setWordWrap(True)
        self.plan_state.setTextFormat(Qt.TextFormat.RichText)
        box.addWidget(self.plan_state)
        self.plan_summary = QLabel()
        self.plan_summary.setObjectName("ndt_plan_summary")
        self.plan_summary.setWordWrap(True)
        self.plan_summary.setTextFormat(Qt.TextFormat.RichText)
        self.plan_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.plan_summary)
        self.plan_segments = QTableWidget(0, 7)
        self.plan_segments.setObjectName("ndt_plan_segments")
        self.plan_segments.setHorizontalHeaderLabels(
            ["Průchod", "Úsek", "Od [mm]", "Do [mm]", "Délka", "Návaznost", "Přínos"])
        self.plan_segments.verticalHeader().setVisible(False)
        self.plan_segments.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.plan_segments.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.plan_segments.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.plan_segments.setMinimumHeight(100)
        self.plan_segments.setMaximumHeight(200)
        self.plan_segments.itemSelectionChanged.connect(self.refresh_actions)
        self._plan_rows: list[tuple[int, int]] = []
        box.addWidget(self.plan_segments)
        for row_items in ((self.plan_remove_action, self.plan_reverse_action,
                           self.plan_up_action, self.plan_down_action),
                          (self.plan_edit_action, self.plan_add_action),
                          (self.plan_zones_action, self.plan_prune_action),
                          (self.plan_delete_action,)):
            row = QHBoxLayout()
            for item in row_items:
                row.addWidget(window._tool_button(item))
            row.addStretch()
            box.addLayout(row)
        play = QHBoxLayout()
        play.addWidget(QLabel("Poloha:"))
        for item in (self.plan_prev_action, self.plan_play_action, self.plan_next_action):
            play.addWidget(window._tool_button(item))
        self.plan_slider = QSlider(Qt.Orientation.Horizontal)
        self.plan_slider.setObjectName("ndt_plan_slider")
        self.plan_slider.setRange(0, 0)
        self.plan_slider.valueChanged.connect(self._plan_slider_changed)
        play.addWidget(self.plan_slider, stretch=1)
        box.addLayout(play)
        self.plan_position = QLabel()
        self.plan_position.setObjectName("ndt_plan_position")
        self.plan_position.setWordWrap(True)
        box.addWidget(self.plan_position)
        self.plan_map = QCheckBox("ukázat pokrytí plánu ve 3D (při přehrávání narůstá)")
        self.plan_map.setObjectName("ndt_plan_map")
        self.plan_map.setChecked(True)
        self.plan_map.toggled.connect(lambda _checked: self.window._refresh_probe())
        box.addWidget(self.plan_map)
        legend = QLabel(" · ".join(f'<span style="color:{_hex(color)}">■</span> {label}'
                                   for label, color in PLAN_LEGEND))
        legend.setObjectName("ndt_plan_legend")
        legend.setWordWrap(True)
        box.addWidget(legend)
        note = QLabel(PLAN_NOTE)
        note.setWordWrap(True)
        note.setStyleSheet("color: #8a5a00; font-style: italic;")
        box.addWidget(note)
        self._plan_index: int | None = None  # poloha přehrávání (None = celý plán)
        self._plan_recheck: str | None = None  # po úpravě ověřit, až doběhne přepočet dílu
        self._plan_timer = QTimer(self)
        self._plan_timer.setInterval(150)
        self._plan_timer.timeout.connect(self._play_tick)
        for signal in (self.plan_source.currentIndexChanged,
                       self.plan_pattern.currentIndexChanged, self.plan_step.valueChanged,
                       self.plan_approach.valueChanged, self.plan_compare.toggled,
                       self.plan_robust.toggled):
            signal.connect(lambda *_args: self.refresh_actions())
        layout.addWidget(self.plan_box)

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
        self._show_access()
        self._show_plan()
        self._show_pt()
        self.refresh_actions()
        self._start_recheck()

    def _row_changed(self) -> None:
        self._show_warning()
        self._show_details()
        self._show_probe()
        self._show_coverage()
        self._show_access()
        self._plan_index = None
        self._show_plan()
        self._show_pt()
        self.refresh_actions()
        self.window._update_highlight()  # kontrolovaná oblast vybrané studie ve 3D

    def _show_warning(self) -> None:
        """UT studie (nebo nová UT bez výběru) = povinné upozornění UT, PT studie = povinné
        upozornění PT, jinak obecné."""
        session = self.window.session
        record = self._record(self.current_id())
        method = record.get("method") if record else self.method_combo.currentData()
        if method == "PT":
            text = PT_DISCLAIMER
        elif method == "UT" or session.ndt_coverage is not None:
            text = UT_DISCLAIMER
        else:
            text = PT_DISCLAIMER if session.ndt_pt_map is not None else DISCLAIMER
        self.warning.setText(text)

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
        self.cross_section_action.setEnabled(selected and has_part and self._volume_target())
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
        possible = bool(ut and placed and matching and result is not None
                        and result.state == "ok" and not self.window.ai_busy)
        volume = self._volume_target()
        if volume:
            self._recommend_target_step()
        estimate = self._estimate() if possible and volume else None
        self.coverage_action.setEnabled(possible and (not volume or (estimate is not None
                                                                      and estimate.ok)))
        self._show_volume_options(volume, estimate)
        has_coverage = session.ndt_coverage is not None
        self.clear_coverage_action.setEnabled(has_coverage and not self.window.ai_busy)
        self.export_coverage_action.setEnabled(has_coverage and not self.window.ai_busy)
        self.coverage_box.setVisible(bool(ut or has_coverage or session.coverage_pending))
        self._refresh_access_actions(ut and has_part and result is not None
                                     and result.state == "ok")
        self._refresh_plan_actions(bool(ut and has_part and result is not None
                                        and result.state == "ok"))
        pt = selected and (record or {}).get("method") == "PT"
        has_pt = session.ndt_pt_map is not None
        self.pt_settings_action.setEnabled(pt)
        self.pt_action.setEnabled(bool(pt and has_part and result is not None
                                       and result.state == "ok" and not session.pt_pending))
        self.pt_stop_action.setEnabled(session.pt_pending)
        self.pt_clear_action.setEnabled(has_pt)
        self.pt_export_action.setEnabled(has_pt)
        self.pt_box.setVisible(bool(pt or has_pt or session.pt_pending))
        self.probe_box.setVisible(not pt)
        if self.window.ai_busy:  # AI pracuje – ruční úpravy počkají
            for action in (self.new_action, self.target_action, self.volume_action,
                           self.cross_section_action, self.rename_action,
                           self.method_action, self.note_action, self.duplicate_action,
                           self.delete_action, self.confirm_action, self.verify_action,
                           self.unverify_action, self.probe_action, self.place_action,
                           self.drag_probe_action, self.remove_probe_action,
                           self.step_back_action, self.step_forward_action, self.scan_action,
                           self.transfer_action, self.part_material_action,
                           self.access_action, self.access_show_action,
                           self.access_apply_action, self.access_export_action,
                           *self._plan_actions(), *self._pt_actions()):
                action.setEnabled(False)
            self.scan_slider.setEnabled(False)
            self.ut_material.setEnabled(False)

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
        session = self.window.session
        result = session.ndt_coverage
        if result is not None:
            lines = [escape(line) for line in result.summary()]
            lines[:0] = ["<b>" + " · ".join(f"{label} {result.percent(state):.2f} %"
                                            for state, label in STATES.items()) + "</b>",
                         _sensitivity_html(result)]
            if isinstance(result, VolumeCoverageMap) and session.section_settings is None:
                lines.insert(2, "Barevný je jen povrch cíle. Dovnitř se podívej tlačítkem "
                                "<b>Průřez svarem</b>.")
            self.coverage_label.setText("<br>".join(lines))
        elif session.coverage_pending:
            self.coverage_label.setText(
                f"Počítám mapu… {session.computing_seconds:.0f} s. Výpočet můžeš zastavit "
                "tlačítkem Zastavit dole v okně.")
        else:
            self.coverage_label.setText("Zelená: pokryto · červená: nepokryto · žlutá: "
                                        f"nejisté.<br>{escape(PERCENT_NOTE)}")

    def cross_section(self) -> None:
        """Průřez svarem: řez kolmo na osu cílového objemu vybrané studie (jen pohled)."""
        target = (self._record(self.current_id()) or {}).get("target") or {}
        if target.get("kind") not in ("volume", "weld"):
            self.window.statusBar().showMessage("Průřez svarem jde jen u studie s cílovým "
                                                "objemem (Cílový objem…).", 8000)
            return
        try:
            self.window._busy(lambda: self.window.session.set_section_target(target))
        except DocumentError as exc:
            self.window._error("Průřez svarem nejde ukázat", str(exc))
            return
        self.window._refresh_all()
        self.window.statusBar().showMessage("Průřez svarem: posuvníkem v panelu Řez jedeš "
                                            "podél cíle; model se nemění.", 10000)

    def _volume_target(self) -> bool:
        target = (self._record(self.current_id()) or {}).get("target") or {}
        return target.get("kind") in ("volume", "weld")

    def _coverage_options(self) -> dict:
        options = {"mode": self.coverage_mode.currentData(), "step_mm": self.coverage_step.value(),
                   "spread_deg": self.coverage_spread.value(),
                   "length_mm": self.scan_length.value(),
                   "convergence": self.coverage_convergence.isChecked()}
        if self._volume_target():
            options.update(target_step_mm=self.coverage_target_step.value())
        return options

    def _estimate(self) -> CoverageEstimate:
        """Odhad objemového výpočtu (bez průniků); pamatuje se pro stejné zadání."""
        session = self.window.session
        options = self._coverage_options()
        key = (id(session.result), repr(session.ndt_placement_request),
               repr(self._record(self.current_id())), repr(sorted(options.items())))
        if self._estimate_cache is None or self._estimate_cache[0] != key:
            try:
                found = session.ndt_coverage_estimate(**options)
            except DocumentError as exc:
                found = CoverageEstimate(0, 0, 0, False, str(exc))
            self._estimate_cache = (key, found)
        return self._estimate_cache[1]

    def _recommend_target_step(self) -> None:
        """Nový objemový cíl → doporučený krok cíle (šestina menšího rozměru průřezu);
        uživatel ho pak smí změnit, dokud se cíl nezmění."""
        key = (self.current_id(), repr((self._record(self.current_id()) or {}).get("target")))
        if key == self._target_step_key:
            return
        recommended = self.window.session.ndt_recommended_target_step(self.current_id())
        if recommended is None:
            return
        self._target_step_key = key
        self.coverage_target_step.blockSignals(True)
        self.coverage_target_step.setValue(recommended)
        self.coverage_target_step.blockSignals(False)

    def _show_volume_options(self, volume: bool, estimate: CoverageEstimate | None) -> None:
        """Krok cíle a tolerance jen u objemového cíle (citlivost i u ploch); odhad pod nimi."""
        form = self.coverage_form
        for widget in (self.coverage_target_step, self.tolerance_box):
            form.setRowVisible(widget, volume)
        recommended = (self.window.session.ndt_recommended_target_step(self.current_id())
                       if volume else None)
        form.labelForField(self.coverage_step).setText(
            "Krok pojezdu [mm]:" if volume else "Krok výpočtu [mm]:")
        self.coverage_estimate.setVisible(volume)
        self.volume_legend.setVisible(volume)
        if estimate is None:
            self.coverage_estimate.setStyleSheet("color: #555;")
            self.coverage_estimate.setText("Odhad velikosti výpočtu se ukáže po přiložení "
                                           "sondy této studie na pojezdovou plochu.")
        else:
            self.coverage_estimate.setStyleSheet("color: #555;" if estimate.ok
                                                 else "color: #b9770e;")
            text = estimate.text
            if recommended is not None and \
                    abs(self.coverage_target_step.value() - recommended) > 1e-9:
                text += f" Doporučený krok cíle {recommended:g} mm."
            self.coverage_estimate.setText(text)

    def compute_coverage(self) -> None:
        options = self._coverage_options()
        if self._volume_target() and not self.coverage_tolerance_auto.isChecked():
            options["tolerance_mm"] = self.coverage_tolerance.value()
        self._apply("Pokrytí nejde spočítat",
                    lambda: self.window.session.start_ndt_coverage(**options))

    def clear_coverage(self) -> None:
        self.window.session.clear_ndt_coverage()
        self.window._refresh_all()

    def export_coverage(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export geometrického pokrytí UT",
                                             "pokryti-ut.csv", "CSV (*.csv)")
        if path:
            self._apply("CSV nejde uložit", lambda: self.window.session.export_ndt_coverage(path))

    # --- PT – přístupnost povrchu (etapa 11) -------------------------------------------

    def _pt_actions(self) -> tuple:
        return (self.pt_settings_action, self.pt_action, self.pt_stop_action,
                self.pt_clear_action, self.pt_export_action)

    def _pt_study(self) -> str | None:
        """Vybraná PT studie, nebo None."""
        study_id = self.current_id()
        record = self._record(study_id)
        return study_id if record is not None and record.get("method") == "PT" else None

    def pt_view(self) -> tuple[PtMap, str | None] | None:
        """Mapa PT ve 3D: (mapa, kontrola – None = celkem), nebo None."""
        found = self.window.session.ndt_pt_map
        if found is None:
            return None
        return found, (self.pt_check.currentData() or None)

    def _pt_check_changed(self) -> None:
        self._show_pt_legend()
        self.window._refresh_coverage()

    def _show_pt_legend(self) -> None:
        check = self.pt_check.currentData() or None
        if check is None:
            self.pt_legend.setText(_swatches(PT_COLORS, PT_STATES))
        else:
            self.pt_legend.setText(f"{escape(PT_CHECKS[check])}: " + _swatches(
                PT_GRADE_COLORS, {key: PT_GRADES[key] for key in PT_GRADE_COLORS}))

    def _pt_estimate_text(self, study_id: str) -> str:
        """Odhad počtu vzorků a doby (síť ploch); pamatuje se pro stejné zadání."""
        session = self.window.session
        key = (id(session.result), study_id, repr(self._record(study_id)))
        if self._pt_estimate_cache is None or self._pt_estimate_cache[0] != key:
            try:
                count, step, seconds = session.ndt_pt_estimate(study_id)
                text = (f"Odhad: {count} vzorků při kroku {f'{step:g}'.replace('.', ',')} mm, "
                        f"asi {seconds:.0f} s (počítá se na pozadí, jde zastavit).")
            except DocumentError as exc:
                text = str(exc)
            self._pt_estimate_cache = (key, text)
        return self._pt_estimate_cache[1]

    def _show_pt(self) -> None:
        session = self.window.session
        study_id = self._pt_study()
        self._show_pt_legend()
        if study_id is not None:
            try:
                self.pt_settings_label.setText(
                    "\n".join(session.ndt_pt_settings(study_id).lines()))
            except DocumentError as exc:
                self.pt_settings_label.setText(str(exc))
        else:
            self.pt_settings_label.setText("")
        found = session.ndt_pt_map
        if session.pt_pending:
            progress = session.ndt_pt_progress
            done = f" – vzorky {progress[0]} z {progress[1]}" if progress else ""
            self.pt_estimate.setText(f"Počítám mapu PT… {session.computing_seconds:.0f} s"
                                     f"{done}. Výpočet zastavíš tlačítkem Zastavit.")
        elif study_id is not None and found is None and not session.computing:
            self.pt_estimate.setText(self._pt_estimate_text(study_id))
        else:
            self.pt_estimate.setText("")
        if found is not None:
            name = (self._record(session.ndt_pt_study()) or {}).get("name", "")
            lines = [escape(line) for line in found.summary()]
            lines[0] = f"<b>{escape(PT_MAP)}</b> – {escape(name)}"
            lines.insert(1, "<b>" + " · ".join(f"{label} {found.percent(state):.1f} %"
                                               for state, label in PT_STATES.items())
                         .replace(".", ",") + "</b>")
            self.pt_summary.setText("<br>".join(lines))
        else:
            self.pt_summary.setText("")
        self.pt_pick.setVisible(found is not None)
        self.show_pt_pick()

    def show_pt_pick(self) -> None:
        """Stav a důvody místa mapy, na které uživatel klikl ve 3D."""
        session = self.window.session
        point = self.window.viewer.picked_point if self.window._picked else None
        lines = session.ndt_pt_describe(point) if point is not None else []
        self.pt_pick.setText("\n".join(lines) if lines else PT_PICK_HINT)

    def edit_pt_settings(self) -> None:
        study_id = self._pt_study()
        if study_id is None:
            return
        session = self.window.session
        try:
            current = session.ndt_pt_settings(study_id)
        except DocumentError as exc:
            self.window._error("Nastavení PT nejde načíst", str(exc))
            return
        dialog = PtDialog(self, current)
        if self.window._exec_dialog(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            settings = dialog.settings()
        except PtError as exc:
            self.window._error("Nastavení PT nejde uložit", str(exc))
            return
        self._apply("Nastavení PT nejde uložit",
                    lambda: session.set_ndt_pt_settings(study_id, settings))

    def start_pt(self) -> None:
        study_id = self._pt_study()
        if study_id is not None:
            self._apply("Mapu PT nejde spočítat",
                        lambda: self.window.session.start_ndt_pt(study_id))

    def stop_pt(self) -> None:
        self.window.stop_rebuild()

    def clear_pt(self) -> None:
        self.window.session.clear_ndt_pt()
        self.window._refresh_all()

    def export_pt(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export mapy přístupnosti PT",
                                             "pristupnost-pt.csv", "CSV (*.csv)")
        if path:
            self._apply("CSV nejde uložit", lambda: self.window.session.export_ndt_pt(path))

    # --- návrh poloh sondy (etapa 09) -------------------------------------------------

    def _access_options(self) -> dict:
        return {"step_mm": self.access_step.value(),
                "direction_step_deg": self.access_directions.currentData(),
                "angles": ALTERNATIVE_ANGLES if self.access_angles.isChecked() else (),
                "bounces": tuple(int(v) for v in self.access_bounces.currentData().split(","))}

    def _access_contact(self) -> list | None:
        if self.access_faces.currentData() != "picked":
            return None
        return self.window.session.ndt_access_contact(self.window._picked)

    def _access_estimate(self) -> AccessEstimate:
        """Odhad analýzy (bez přiložení a paprsků); pamatuje se pro stejné zadání."""
        session = self.window.session
        options = self._access_options()
        picked = (tuple(id(s) for s in self.window._picked)
                  if self.access_faces.currentData() == "picked" else ())
        key = (id(session.result), self.current_id(), repr(self._record(self.current_id())),
               repr(sorted(options.items())), picked)
        if self._access_estimate_cache is None or self._access_estimate_cache[0] != key:
            try:
                found = session.ndt_access_estimate(self.current_id(), options,
                                                    self._access_contact())
            except DocumentError as exc:
                found = AccessEstimate(0, 0, 0, (0.0, 0.0), False, str(exc))
            self._access_estimate_cache = (key, found)
        return self._access_estimate_cache[1]

    def _selected_rank(self) -> int | None:
        rows = self.access_table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _refresh_access_actions(self, possible: bool) -> None:
        session = self.window.session
        ai = self.window.ai_busy
        pending = session.access_pending
        estimate = (self._access_estimate() if possible and not pending
                    and not session.computing else None)
        self.access_action.setEnabled(bool(estimate is not None and estimate.ok and not ai))
        self.access_stop_action.setEnabled(pending)
        access = session.ndt_access
        rank = self._selected_rank()
        chosen = (access is not None and rank is not None and rank < len(access.variants)
                  and access.variants[rank].best_reference is not None)
        ready = session.document is not None and not session.computing
        self.access_show_action.setEnabled(ready and chosen and not ai)
        self.access_apply_action.setEnabled(ready and chosen and not ai)
        self.access_export_action.setEnabled(access is not None and not ai)
        for widget in (self.access_faces, self.access_directions, self.access_angles,
                       self.access_bounces, self.access_step):
            widget.setEnabled(not pending and not ai)
        ut = (self._record(self.current_id()) or {}).get("method") == "UT"
        self.access_box.setVisible(bool(ut or access is not None or pending))
        if estimate is not None:
            self.access_estimate.setStyleSheet("color: #555;" if estimate.ok
                                               else "color: #b9770e;")
            self.access_estimate.setText(estimate.text)
        elif not pending:
            self.access_estimate.setStyleSheet("color: #555;")
            self.access_estimate.setText("Návrh poloh potřebuje platnou UT studii s "
                                         "kontrolovanou oblastí (plochy nebo cílový objem).")

    def _show_access(self) -> None:
        """Průběh, tabulka nejlepších variant, kombinace a vyřazené varianty."""
        session = self.window.session
        result = session.ndt_access
        if session.access_pending:
            self.access_progress.setText(
                f"⏳ {escape(session.ndt_access_progress)} · {session.computing_seconds:.0f} s "
                "– Zastavit nechá hotové varianty.")
        else:
            self.access_progress.setText("")
        selected = self._selected_rank()
        self.access_table.blockSignals(True)
        self.access_table.setRowCount(0)
        variants = result.variants[:10] if result is not None else []
        for rank, found in enumerate(variants):
            v = found.variant
            covered = f"{found.covered:.2f} %".replace(".", ",")
            if found.uncertain > 0.005:
                covered += f" (+{found.uncertain:.2f} % nejisté)".replace(".", ",")
            cells = [f"#{rank + 1}", v.short_face, v.direction,
                     "přímá" if v.beta == 0 else f"{v.beta:g}°", str(v.bounces), covered,
                     f"{found.coverage.valid_positions}/{found.coverage.positions}", found.note]
            self.access_table.insertRow(rank)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(v.label if column == 1 else text)
                self.access_table.setItem(rank, column, item)
        self.access_table.resizeColumnsToContents()
        if selected is not None and selected < len(variants):
            self.access_table.selectRow(selected)
        self.access_table.blockSignals(False)
        self.access_table.setVisible(bool(variants))
        if result is None:
            self.access_combination.setText("")
            self.access_rejected.setText("")
        else:
            lines = []
            if not result.complete:
                lines.append(f"<b>Neúplná analýza</b> – zastavena po {len(result.variants)} "
                             f"z {result.expected} variant.")
            if result.combination:
                lines.append(f"<b>{escape(result.combination_text())}</b>")
            elif result.variants:
                lines.append("<b>Žádná vyzkoušená varianta z cíle nic geometricky "
                             "nepokryje.</b>")
            else:
                lines.append("<b>Žádnou variantu, ze které by sonda šla přiložit a paprsek "
                             "mířil k cíli, jsem nenašel.</b>")
            if len(result.variants) > 10:
                lines.append(f"V tabulce je 10 nejlepších z {len(result.variants)} – "
                             "všechny v CSV.")
            study = result.preparation.assumptions.get("study_id")
            if study != self.current_id():
                lines.append(f"Návrh patří ke studii {escape(str(study))}.")
            self.access_combination.setText("<br>".join(lines))
            counts: dict[str, int] = {}
            for rejected in result.rejected:
                counts[rejected.kind] = counts.get(rejected.kind, 0) + 1
            self.access_rejected.setText(
                ("Vyřazeno: " + ", ".join(f"{KINDS[k]} {n}" for k, n in counts.items())
                 + ". Důvody u každé plochy jsou v CSV.") if counts else "")
        mode = self.access_map.currentData()
        if mode == "contact":
            self.access_legend.setText(" · ".join(
                f'<span style="color:{_hex(CONTACT_COLORS[state])}">■</span> {label}'
                for state, label in CONTACT_STATES.items()))
        elif mode == "target":
            self.access_legend.setText("Zelená: pokryto kombinací · červená: nepokryto žádnou "
                                       "vyzkoušenou variantou · žlutá: nejisté. (Mapa "
                                       "pokrytí ze Spočítat pokrytí má přednost.)")
        else:
            self.access_legend.setText("")

    def access_map_mode(self) -> str:
        return self.access_map.currentData()

    def _access_map_changed(self) -> None:
        self._show_access()
        self.window._refresh_probe()  # mapa ve 3D

    def start_access(self) -> None:
        study_id = self.current_id()
        options = self._access_options()

        def work() -> object:
            return self.window.session.start_ndt_access(study_id, options,
                                                        self._access_contact())

        self._apply("Návrh poloh nejde spustit", work)

    def stop_access(self) -> None:
        self.window.stop_rebuild()

    def show_variant(self) -> None:
        rank = self._selected_rank()
        if rank is not None:
            self._apply("Variantu nejde ukázat",
                        lambda: self.window.session.show_ndt_access_variant(rank))

    def apply_variant(self) -> None:
        rank = self._selected_rank()
        if rank is not None:
            self._apply("Variantu nejde použít",
                        lambda: self.window.session.apply_ndt_access_variant(rank))

    def export_access(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export návrhu poloh UT sondy",
                                             "navrh-poloh-ut.csv", "CSV (*.csv)")
        if path:
            self._apply("CSV nejde uložit", lambda: self.window.session.export_ndt_access(path))

    # --- plán dráhy sondy (etapa 10) -------------------------------------------------------

    def _plan_actions(self) -> tuple:
        return (self.plan_action, self.plan_check_action, self.plan_export_action,
                self.plan_remove_action, self.plan_reverse_action, self.plan_up_action,
                self.plan_down_action, self.plan_edit_action, self.plan_add_action,
                self.plan_zones_action, self.plan_delete_action, self.plan_prune_action,
                self.plan_play_action,
                self.plan_prev_action, self.plan_next_action)

    def _plan_options(self) -> dict:
        return {"pattern": self.plan_pattern.currentData(),
                "row_step_mm": self.plan_step.value(),
                "approach_mm": self.plan_approach.value(),
                "compare": self.plan_compare.isChecked(),
                "robustness": self.plan_robust.isChecked()}

    def _plan_passes(self) -> list:
        source = self.plan_source.currentData()
        rank = self._selected_rank() if source == "variant" else None
        return self.window.session.ndt_plan_passes(self.current_id(), source, rank)

    def _plan_estimate(self) -> PlanEstimate:
        """Odhad plánu (jen mřížka); pamatuje se pro stejné zadání."""
        session = self.window.session
        options = self._plan_options()
        key = (id(session.result), self.current_id(), repr(self._record(self.current_id())),
               repr(sorted(options.items())), self.plan_source.currentData(),
               self._selected_rank(), repr(session.ndt_placement_request),
               id(session.ndt_access))
        if self._plan_estimate_cache is None or self._plan_estimate_cache[0] != key:
            try:
                found = session.ndt_plan_estimate(self.current_id(), self._plan_passes(),
                                                  options)
            except DocumentError as exc:
                found = PlanEstimate(0, 0, (0.0, 0.0), False, str(exc))
            self._plan_estimate_cache = (key, found)
        return self._plan_estimate_cache[1]

    def _plan_result(self):
        """Ověřený plán vybrané studie (jen když patří k ní)."""
        session = self.window.session
        if session.ndt_plan_study() != self.current_id():
            return None
        return session.ndt_plan_result

    def _selected_segment(self) -> tuple[int, int] | None:
        rows = self.plan_segments.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self._plan_rows):
            return None
        return self._plan_rows[rows[0].row()]

    def _refresh_plan_actions(self, possible: bool) -> None:
        session = self.window.session
        ai = self.window.ai_busy
        pending = session.plan_pending
        ready = session.document is not None and not session.computing
        record = self._record(self.current_id()) or {}
        ut = record.get("method") == "UT"
        has_plan = "plan" in record
        estimate = self._plan_estimate() if possible and not pending and ready else None
        self.plan_action.setEnabled(bool(estimate is not None and estimate.ok and not ai))
        self.plan_check_action.setEnabled(possible and has_plan and ready and not ai)
        self.plan_stop_action.setEnabled(pending)
        result = self._plan_result()
        self.plan_export_action.setEnabled(result is not None and not ai)
        segment = self._selected_segment()
        editable = ready and has_plan and not ai
        for item in (self.plan_remove_action, self.plan_reverse_action, self.plan_edit_action):
            item.setEnabled(editable and segment is not None)
        count = len(record.get("plan", {}).get("passes", [{}])[segment[0]]["segments"]) \
            if editable and segment is not None else 0
        self.plan_up_action.setEnabled(editable and segment is not None and segment[1] > 0)
        self.plan_down_action.setEnabled(editable and segment is not None
                                         and segment[1] < count - 1)
        matching = (session.ndt_placement_request is not None
                    and session.ndt_placement_request[0] == self.current_id())
        self.plan_add_action.setEnabled(ready and ut and matching and not ai
                                        and session.ndt_placement is not None)
        self.plan_zones_action.setEnabled(ready and ut and not ai)
        self.plan_delete_action.setEnabled(editable)
        self.plan_prune_action.setEnabled(editable and result is not None
                                          and bool(result.useless_segments()))
        moving = result is not None and bool(result.check.positions) and not ai
        for item in (self.plan_play_action, self.plan_prev_action, self.plan_next_action):
            item.setEnabled(moving and not pending)
        self.plan_slider.setEnabled(moving and not pending)
        for widget in (self.plan_source, self.plan_pattern, self.plan_step,
                       self.plan_approach, self.plan_compare, self.plan_robust):
            widget.setEnabled(not pending and not ai)
        self.plan_box.setVisible(bool(ut or has_plan or pending))
        if estimate is not None:
            self.plan_estimate.setStyleSheet("color: #555;" if estimate.ok
                                             else "color: #b9770e;")
            self.plan_estimate.setText(estimate.text)
        elif not pending:
            self.plan_estimate.setStyleSheet("color: #555;")
            self.plan_estimate.setText("Plán dráhy potřebuje platnou UT studii a přiloženou "
                                       "sondu na rovinné ploše (nebo návrh poloh).")

    def _show_plan(self) -> None:
        """Stav plánu, souhrn hodnocení, úseky a přehrávání."""
        session = self.window.session
        study_id = self.current_id()
        record = self._record(study_id) or {}
        if session.plan_pending:
            self.plan_progress.setText(
                f"⏳ {escape(session.ndt_plan_progress)} · {session.computing_seconds:.0f} s")
        else:
            self.plan_progress.setText("")
        if "plan" in record:
            try:
                state, text = session.ndt_plan_state(study_id)
            except DocumentError as exc:
                state, text = "invalid", str(exc)
        else:
            state, text = "none", "Studie zatím nemá plán dráhy."
        color = {"ok": "#1b7f3b", "invalid": "#c0392b", "none": "#555"}.get(state, "#b9770e")
        self.plan_state.setText(f'<span style="color: {color};"><b>{escape(text)}</b></span>')
        result = self._plan_result()
        lines = []
        if result is not None:
            lines += [escape(line) for line in result.check.lines()]
            if result.coverage is not None:
                cov = result.coverage
                lines.append(f"<b>Geometricky pokryto {cov.covered:.2f} %</b>, nelze spolehlivě "
                             f"vyhodnotit {cov.coverage.percent('uncertain'):.2f} %"
                             .replace(".", ","))
                if cov.face_coverage is not None:
                    lines.append(f"Srovnání: pojezd po celé ploše "
                                 f"{cov.face_coverage.percent('covered'):.2f} %"
                                 .replace(".", ","))
                if cov.robustness is not None:
                    lines.append(f"Odolnost: po posunu řádků pokryto {cov.robustness[0]:.2f}–"
                                 f"{cov.robustness[1]:.2f} %".replace(".", ","))
            else:
                lines.append("Pokrytí zatím není spočítané – dej Ověřit a spočítat.")
            lines += [escape(d.text) + (" <b>(zvolen)</b>" if d.chosen else "")
                      for d in result.drafts]
            lines += [escape(note) for note in result.dropped]
        self.plan_summary.setText("<br>".join(lines))
        self._show_plan_segments(record, result)
        positions = result.check.positions if result is not None else ()
        self.plan_slider.blockSignals(True)
        self.plan_slider.setRange(0, max(0, len(positions) - 1))
        if self._plan_index is not None and self._plan_index < len(positions):
            self.plan_slider.setValue(self._plan_index)
        else:
            self.plan_slider.setValue(max(0, len(positions) - 1))
        self.plan_slider.blockSignals(False)
        self._show_plan_position(result)

    def _show_plan_segments(self, record: dict, result) -> None:
        links, hits = {}, {}
        if result is not None and result.plan.to_dict()["passes"] == \
                record.get("plan", {}).get("passes"):
            if result.coverage is not None:
                hits = result.coverage.segment_hits(result.check)
            previous = None
            for step in result.check.steps:
                if step.kind == "scan":
                    links[(step.pass_index, step.segment)] = (
                        "začátek" if previous is None else
                        "přestavení" if previous == "air" else "po povrchu")
                previous = step.kind
        selected = self._selected_segment()
        self.plan_segments.blockSignals(True)
        self.plan_segments.setRowCount(0)
        self._plan_rows = []
        for p_index, plan_pass in enumerate(record.get("plan", {}).get("passes", [])):
            for s_index, segment in enumerate(plan_pass["segments"]):
                row = len(self._plan_rows)
                self._plan_rows.append((p_index, s_index))
                length = sum((a - b) ** 2 for a, b in zip(segment["end"], segment["start"],
                                                          strict=True)) ** 0.5
                cells = [str(p_index + 1), str(s_index + 1), _point_text(segment["start"]),
                         _point_text(segment["end"]), f"{length:.1f} mm".replace(".", ","),
                         links.get((p_index, s_index), ""),
                         ("bez přínosu" if hits.get((p_index, s_index)) == 0 else
                          str(hits[(p_index, s_index)]) if (p_index, s_index) in hits
                          else "")]
                self.plan_segments.insertRow(row)
                for column, text in enumerate(cells):
                    self.plan_segments.setItem(row, column, QTableWidgetItem(text))
        self.plan_segments.resizeColumnsToContents()
        if selected in self._plan_rows:
            self.plan_segments.selectRow(self._plan_rows.index(selected))
        self.plan_segments.blockSignals(False)
        self.plan_segments.setVisible(bool(self._plan_rows))

    def _show_plan_position(self, result=None) -> None:
        result = result if result is not None else self._plan_result()
        if result is None or not result.check.positions:
            self.plan_position.setText("")
            return
        index = self.plan_slider.value()
        position = result.check.positions[min(index, len(result.check.positions) - 1)]
        margin = ""
        if position.margin is not None:
            margin = (f", boční rezerva {'aspoň ' if position.margin_capped else ''}"
                      f"{position.margin:.1f} mm".replace(".", ","))
            if position.margin < EDGE_MM:
                margin += " – na hraně"
        self.plan_position.setText(
            f"Poloha {index + 1} z {len(result.check.positions)}: průchod "
            f"{position.pass_index + 1}, úsek {position.segment + 1}, "
            f"({_point_text(position.point)}){margin}"
            + (f" – {position.note}" if position.note else ""))

    def plan_view(self):
        """Mapa pokrytí plánu do 3D (po poloze přehrávání), None = žádná."""
        result = self._plan_result()
        if not self.plan_map.isChecked() or result is None or result.coverage is None:
            return None
        return self.window.session.ndt_plan_view_map(self._plan_index)

    def _start_recheck(self) -> None:
        """Po úpravě plánu ověřit (bez pokrytí), až doběhne přepočet dílu."""
        session = self.window.session
        study_id = self._plan_recheck
        if study_id is None or session.computing or session.document is None:
            return
        self._plan_recheck = None
        if self._record(study_id) is None or "plan" not in self._record(study_id):
            return
        try:
            session.start_ndt_plan_check(study_id, coverage=False)
        except DocumentError as exc:
            self.window.statusBar().showMessage(f"Plán nejde ověřit: {exc}", 8000)
            return
        if not session.computing:  # bez pomocného procesu je hotovo hned
            self.window._refresh_probe()
            self._show_plan()
            self.refresh_actions()

    def start_plan(self) -> None:
        study_id = self.current_id()
        options = self._plan_options()
        passes = self._plan_passes()
        self._plan_index = None
        found = self._apply("Plán dráhy nejde spustit",
                            lambda: self.window.session.start_ndt_plan(study_id, passes, options))
        if found is not None and not found.plan.passes:
            self.window._error("Plán dráhy nenašel žádný úsek", " ".join(found.dropped))

    def check_plan(self) -> None:
        study_id = self.current_id()
        session = self.window.session
        confirm = session.ndt_plan_state(study_id)[0] == "stale"
        self._plan_index = None
        self._apply("Plán dráhy nejde ověřit", lambda: session.start_ndt_plan_check(
            study_id, self._plan_options(), coverage=True, confirm=confirm))

    def stop_plan(self) -> None:
        self.window.stop_rebuild()

    def export_plan(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export plánu dráhy UT sondy",
                                             "plan-drahy-ut.csv", "CSV (*.csv)")
        if path:
            self._apply("CSV nejde uložit", lambda: self.window.session.export_ndt_plan(path))

    def _edit_plan(self, title: str, work) -> None:
        study_id = self.current_id()
        self._plan_index = None
        if self._apply(title, work) is not None:
            self._plan_recheck = study_id
            self._start_recheck()

    def remove_plan_segment(self) -> None:
        found = self._selected_segment()
        if found is not None:
            self._edit_plan("Úsek nejde smazat", lambda: self.window.session
                            .remove_ndt_plan_segment(self.current_id(), *found))

    def reverse_plan_segment(self) -> None:
        found = self._selected_segment()
        if found is not None:
            self._edit_plan("Úsek nejde obrátit", lambda: self.window.session
                            .reverse_ndt_plan_segment(self.current_id(), *found))

    def move_plan_segment(self, offset: int) -> None:
        found = self._selected_segment()
        if found is None:
            return
        self._edit_plan("Úsek nejde přeřadit", lambda: self.window.session
                        .move_ndt_plan_segment(self.current_id(), *found, offset))
        target = (found[0], found[1] + offset)
        if target in self._plan_rows:
            self.plan_segments.selectRow(self._plan_rows.index(target))

    def edit_plan_segment(self) -> None:
        found = self._selected_segment()
        record = self._record(self.current_id()) or {}
        if found is None or "plan" not in record:
            return
        segment = record["plan"]["passes"][found[0]]["segments"][found[1]]
        text, ok = QInputDialog.getText(
            self, "Upravit úsek", "Začátek → konec úseku [mm] (x; y; z → x; y; z):",
            text=f"{_point_text(segment['start'])} → {_point_text(segment['end'])}")
        if not ok:
            return
        try:
            start, end = (_parse_point(part) for part in text.replace("->", "→").split("→"))
        except ValueError:
            self.window._error("Úsek nejde upravit", "Zadej začátek a konec jako "
                               "„x; y; z → x; y; z“ (mm).")
            return
        self._edit_plan("Úsek nejde upravit", lambda: self.window.session
                        .set_ndt_plan_segment(self.current_id(), *found, start, end))

    def add_plan_segment(self) -> None:
        length = self.scan_length.value()
        self._edit_plan("Úsek nejde přidat", lambda: self.window.session
                        .add_ndt_plan_segment(self.current_id(), length))

    def prune_plan(self) -> None:
        self._edit_plan("Úseky nejde smazat", lambda: self.window.session
                        .remove_ndt_useless_segments(self.current_id()))

    def delete_plan(self) -> None:
        self._plan_index = None
        self._apply("Plán nejde smazat",
                    lambda: self.window.session.remove_ndt_plan(self.current_id()))

    def edit_zones(self) -> None:
        study_id = self.current_id()
        session = self.window.session
        try:
            current = [zone.to_dict() for zone in session.ndt_zones(study_id)]
        except DocumentError as exc:
            self.window._error("Zóny nejde načíst", str(exc))
            return
        picked = list(self.window._picked)

        def from_selection() -> dict:
            if not picked:
                raise DocumentError("Nejdřív ve 3D vyber plochu nebo hranu, kolem které má "
                                    "zóna být.")
            return session.ndt_zone_from_selection(picked)

        dialog = ZoneDialog(self, current, from_selection)
        if self.window._exec_dialog(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            zones = dialog.zones()
        except PlanError as exc:
            self.window._error("Zóny nejde uložit", str(exc))
            return
        if zones == current:
            return
        self._edit_plan("Zóny nejde uložit",
                        lambda: session.set_ndt_zones(study_id, zones))

    def toggle_play(self) -> None:
        if not self.plan_play_action.isChecked():
            self._plan_timer.stop()
            return
        if self.plan_slider.value() >= self.plan_slider.maximum():
            self.plan_slider.setValue(0)
        self._plan_timer.start()

    def _play_tick(self) -> None:
        if self.plan_slider.value() >= self.plan_slider.maximum() or \
                not self.plan_slider.isEnabled():
            self._plan_timer.stop()
            self.plan_play_action.setChecked(False)
            return
        self.plan_slider.setValue(self.plan_slider.value() + 1)

    def step_plan(self, delta: int) -> None:
        value = min(max(self.plan_slider.value() + delta, 0), self.plan_slider.maximum())
        if value == self.plan_slider.value():
            self._plan_slider_changed(value)
        else:
            self.plan_slider.setValue(value)

    def _plan_slider_changed(self, index: int) -> None:
        if self._plan_result() is None:
            return
        try:
            self.window.session.show_ndt_plan_position(index)
        except DocumentError as exc:
            self.window.statusBar().showMessage(str(exc), 8000)
            return
        self._plan_index = index
        self.window._refresh_probe()  # sonda, paprsek a narůstající mapa
        self._show_probe()
        self._show_plan_position()
        if self._plan_rows:
            result = self._plan_result()
            position = result.check.positions[index]
            key = (position.pass_index, position.segment)
            if key in self._plan_rows:
                self.plan_segments.blockSignals(True)
                self.plan_segments.selectRow(self._plan_rows.index(key))
                self.plan_segments.blockSignals(False)

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
            beam_info = f", paprsek {probe.beam_angle:g}°" if probe.kind == "angle" else ""
            details = "".join(f"<br><span style='color: #555;'>{escape(line)}</span>"
                              for line in describe(probe))
            self.probe_label.setText(f"{escape(probe.label)}{beam_info}{stored}; mezera nejvýš "
                                     f"{probe.max_gap:.2f} mm, rezerva {probe.reserve:.2f} mm, "
                                     f"odrazy {probe.bounces}.{details}")
        self._show_material(record)
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
            zone = session.ndt_placement_zone
            zone_html = (f'<br><span style="color: #b9770e;"><b>{escape(zone)}</b></span>'
                         if zone else "")
            self.placement_label.setText(f'<span style="color: {color};"><b>'
                                         f"{placement.text}</b></span>{zone_html}{beam_html}")
        elif session.ndt_placement_request is not None and session.ndt_placement_error:
            self.placement_label.setText(f'<span style="color: #c0392b;">'
                                         f"{session.ndt_placement_error}</span>")
        else:
            self.placement_label.setText("Klikni ve 3D na plochu a dej Přiložit sondu sem "
                                         "(nebo zapni Jezdit sondou myší / drž Alt).")

    def _user_library(self) -> UserLibrary:
        """Moje sondy (``~/SkodaCAD/ndt-knihovna.json``); znovu se čtou jen po změně souboru."""
        path = user_library_path(self.window.user_dir)
        try:
            stamp = (str(path), path.stat().st_mtime_ns)
        except OSError:
            stamp = (str(path), None)
        if self._library_cache is None or self._library_cache[0] != stamp:
            self._library_cache = (stamp, load_user_library(path))
        return self._library_cache[1]

    def _show_material(self, record: dict | None) -> None:
        """Materiál pro UT vybrané UT studie, kontrola úhlu sondy a tlačítka přepočtu."""
        session = self.window.session
        ut = record is not None and record.get("method") == "UT"
        material = session.ndt_ut_material(record["id"]) if ut else None
        library = self._user_library()
        self.ut_material.blockSignals(True)
        self.ut_material.clear()
        self.ut_material.addItem("nezvolen", "")
        for key, item in MATERIALS.items():
            self.ut_material.addItem(f"{item.name} (orientační)", f"builtin:{key}")
        for name in library.materials:
            self.ut_material.addItem(f"{name} (Moje sondy)", f"user:{name}")
        current = ""
        if material is not None:
            current = (f"builtin:{material.profile}" if material.profile in MATERIALS
                       else f"user:{material.name}")
            if self.ut_material.findData(current) < 0:
                self.ut_material.addItem(f"{material.name} (ve studii)", current)
        self.ut_material.setCurrentIndex(self.ut_material.findData(current))
        self.ut_material.setEnabled(ut and not self.window.ai_busy)
        self.ut_material.blockSignals(False)
        self.material_label.setText(
            "" if material is None else f"{material.text}; zdroj: {material.source}.")
        check = session.ndt_angle_check(record["id"]) if ut else None
        warn = check is not None and check.state in ("differs", "unknown", "error")
        self.angle_check_label.setText(check.text if warn else "")
        self.angle_check_label.setVisible(warn)
        part = session.document.material if session.document is not None else ""
        self.transfer_action.setEnabled(bool(check and check.state == "differs")
                                        and not self.window.ai_busy)
        self.part_material_action.setText(f"Použít materiál dílu ({part})")
        self.part_material_action.setEnabled(
            ut and material is None and material_key(part) in MATERIALS
            and not self.window.ai_busy)

    def _ut_material_chosen(self) -> None:
        study_id = self.current_id()
        data = self.ut_material.currentData()
        if study_id is None or data is None or data.startswith("study"):
            return
        if data.startswith("builtin:"):
            chosen = MATERIALS[data.removeprefix("builtin:")]
        elif data.startswith("user:"):
            chosen = self._user_library().materials.get(data.removeprefix("user:"))
            if chosen is None:
                return
        else:
            chosen = None
        if chosen == self.window.session.ndt_ut_material(study_id):
            return
        self._apply("Materiál pro UT nejde nastavit",
                    lambda: self.window.session.set_ndt_ut_material(study_id, chosen))

    def use_part_material(self) -> None:
        study_id = self.current_id()
        if study_id is not None:
            part = self.window.session.document.material
            self._apply("Materiál pro UT nejde nastavit",
                        lambda: self.window.session.set_ndt_ut_material(study_id, part))

    def transfer_angle(self) -> None:
        study_id = self.current_id()
        if study_id is not None:
            self._apply("Úhel nejde přepočítat",
                        lambda: self.window.session.apply_ndt_angle_transfer(study_id))

    def edit_probe(self) -> None:
        study_id = self.current_id()
        if study_id is None:
            return
        path = user_library_path(self.window.user_dir)
        dialog = ProbeDialog(self.window.session.ndt_probe(study_id), self,
                             library=self._user_library(),
                             save=lambda name, probe: save_user_probe(path, name, probe))
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


PLAN_LEGEND = (("úsek", STEP_COLORS["scan"]), ("přesun po povrchu", STEP_COLORS["slide"]),
               ("přestavení (nad dílem)", STEP_COLORS["air"]), ("zakázaná zóna", ZONE_COLOR))


def _point_text(point: tuple) -> str:
    return "; ".join(f"{round(v, 3) + 0.0:g}".replace(".", ",") for v in point)


def _parse_point(text: str) -> list[float]:
    parts = [part.strip().replace(",", ".") for part in text.split(";")]
    if len(parts) != 3:
        raise ValueError(text)
    return [float(part) for part in parts]


def _sensitivity_html(result: CoverageMap | VolumeCoverageMap) -> str:
    """Citlivost na krok nahlas: oranžově citlivý nebo neověřený výsledek."""
    found = result.assumptions.get("convergence")
    if found is None:
        return '<span style="color: #b9770e;">Citlivost na krok neověřena.</span>'
    if found["delta_pp"] > 1:
        return (f'<span style="color: #b9770e;"><b>Výsledek je citlivý na krok</b> (rozdíl '
                f'{found["delta_pp"]:.2f} p. b.) – zjemni krok.</span>')
    return (f'<span style="color: #1b7f3b;">Nízká pozorovaná citlivost na krok '
            f'({found["delta_pp"]:.2f} p. b.) – není zárukou přesnosti.</span>')


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


def _hex(color: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in color)
