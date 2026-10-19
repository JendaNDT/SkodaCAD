"""Skupina *Geometrie projekce RT* v panelu NDT (etapa 13, ``RT_DISCLAIMER``).

Nastavení zdroje a detektoru, seznam projekcí (Zdroj nad vybrané místo, Upravit, Kopírovat
posunutou, Smazat – každá změna jeden krok Zpět), výpočet na pozadí, mapa ve 3D celkem i po
projekcích, důvody místa po kliknutí, náhled prozařované tloušťky na detektoru (PNG) a CSV.
Všechno jde přes ``ModelSession``; skupina sama nic nepočítá. Zdroj a detektor vybrané projekce
kreslí okno jako sondu (průhledné těleso v barvě stavu, čára ke zaměřenému bodu, paprsky do
rohů detektoru) – žádný nový druh kreslení.
"""

from __future__ import annotations

import math
from html import escape
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from skodacad.document import DocumentError
from skodacad.gui.rt_dialog import ProjectionDialog, RtDialog
from skodacad.ndt import RT_ACCESS, RT_MAP, RT_PREVIEW
from skodacad.ndt.rt import COLORS, PREVIEW_LEGEND, STATES, RtError, RtMap

if TYPE_CHECKING:
    from skodacad.gui.ndt_panel import NdtPanel

PICK_HINT = "Klikni ve 3D do mapy – napíšu stav místa v každé projekci s čísly a důvody."
ADD_HINT = ("Zdroj nad vybrané místo: klikni ve 3D na plochu (u svaru na temeno) – zdroj bude "
            "500 mm nad ní po kolmici, detektor na protější ploše.")
PREVIEW_WIDTH = 420  # náhled v panelu: delší strana detektoru na tuto šířku


def _swatches() -> str:
    def hex_color(rgb: tuple) -> str:
        return "#" + "".join(f"{round(255 * v):02x}" for v in rgb)

    return " · ".join(f'<span style="color: {hex_color(COLORS[key])};">■</span> {escape(label)}'
                      for key, label in STATES.items())


def _mm(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def describe(projection) -> str:
    """Jeden řádek seznamu projekcí."""
    detector = ("detektor na ploše" if projection.detector == "contact"
                else f"detektor volně {_mm(projection.detector_distance_mm)} mm od zdroje")
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, max(abs(v) for v in
                                                        projection.direction)))))
    text = f"{projection.name} – f {_mm(projection.distance_mm)} mm, {detector}"
    if tilt > 0.05:
        text += f", šikmo {_mm(round(tilt, 1))}° od osy"
    if projection.reference_mm is not None:
        text += f", jmenovitá tloušťka {_mm(projection.reference_mm)} mm"
    return text


class RtBox(QGroupBox):
    def __init__(self, panel: NdtPanel) -> None:
        super().__init__(RT_ACCESS)
        self.panel = panel
        window = panel.window
        action = window._action
        self.settings_action = action("Nastavení RT…", self.edit_settings)
        self.settings_action.setToolTip("Třída zkoušky, ohnisko, kužel a tělo zdroje, detektor, "
                                        "kroky – uloží se do studie (jeden krok Zpět)")
        self.compute_action = action("Spočítat projekce", self.start)
        self.compute_action.setToolTip(
            "Pro místa oblasti a každou projekci zjistí, zda se promítnou na detektor, "
            "prozařovanou tloušťku, poměr a nejmenší vzdálenost zdroje (jen geometrie, model "
            "se nemění)")
        self.stop_action = action("Zastavit", self.stop)
        self.clear_action = action("Skrýt mapu", self.clear)
        self.export_action = action("Export CSV…", self.export)
        self.png_action = action("Uložit náhled PNG…", self.save_png)
        self.add_action = action("Zdroj nad vybrané místo", self.add_projection)
        self.add_action.setToolTip(ADD_HINT)
        self.edit_action = action("Upravit projekci…", self.edit_projection)
        self.edit_action.setToolTip("Zaměřený bod, sklon a natočení, vzdálenost zdroje, detektor, "
                                    "jmenovitá tloušťka (jeden krok Zpět)")
        self.copy_action = action("Kopírovat posunutou…", self.copy_projection)
        self.copy_action.setToolTip("Kopie vybrané projekce posunutá o zadaný vektor – třeba "
                                    "další snímek podél svaru (jeden krok Zpět)")
        self.remove_action = action("Smazat projekci", self.remove_projection)
        self._estimate_cache: tuple[tuple, str] | None = None

        self.setObjectName("ndt_rt")
        box = QVBoxLayout(self)
        self.settings_label = QLabel()
        self.settings_label.setObjectName("ndt_rt_settings")
        self.settings_label.setWordWrap(True)
        box.addWidget(self.settings_label)
        self._row(box, (self.settings_action, self.compute_action, self.stop_action))
        box.addWidget(QLabel("Projekce (zdroj a detektor):"))
        self.projections = QListWidget()
        self.projections.setObjectName("ndt_rt_projections")
        self.projections.setMinimumHeight(50)
        self.projections.setMaximumHeight(100)
        self.projections.currentRowChanged.connect(lambda _row: self._projection_changed())
        self.projections.itemDoubleClicked.connect(lambda _item: self.edit_projection())
        box.addWidget(self.projections)
        self._row(box, (self.add_action, self.edit_action))
        self._row(box, (self.copy_action, self.remove_action))
        self.setup_label = QLabel(ADD_HINT)
        self.setup_label.setObjectName("ndt_rt_setup")
        self.setup_label.setWordWrap(True)
        box.addWidget(self.setup_label)
        self.estimate = QLabel()
        self.estimate.setObjectName("ndt_rt_estimate")
        self.estimate.setWordWrap(True)
        box.addWidget(self.estimate)
        show_row = QHBoxLayout()
        show_row.addWidget(QLabel("Ukázat ve 3D:"))
        self.view = QComboBox()
        self.view.setObjectName("ndt_rt_view")
        self.view.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.view.addItem("celkem", "")
        self.view.currentIndexChanged.connect(lambda _index: self.window._refresh_coverage())
        show_row.addWidget(self.view)
        show_row.addStretch(1)
        box.addLayout(show_row)
        self.legend = QLabel(_swatches())
        self.legend.setObjectName("ndt_rt_legend")
        self.legend.setWordWrap(True)
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        box.addWidget(self.legend)
        self.summary = QLabel()
        self.summary.setObjectName("ndt_rt_summary")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.summary)
        self.pick = QLabel(PICK_HINT)
        self.pick.setObjectName("ndt_rt_pick")
        self.pick.setWordWrap(True)
        self.pick.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.pick)
        self.preview_title = QLabel(f"<b>{escape(RT_PREVIEW)}</b>")
        self.preview_title.setObjectName("ndt_rt_preview_title")
        self.preview_title.setWordWrap(True)
        box.addWidget(self.preview_title)
        self.preview = QLabel()
        self.preview.setObjectName("ndt_rt_preview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignLeft)
        box.addWidget(self.preview)
        self.preview_legend = QLabel(PREVIEW_LEGEND)
        self.preview_legend.setObjectName("ndt_rt_preview_legend")
        self.preview_legend.setWordWrap(True)
        self.preview_legend.setStyleSheet("color: #555;")
        box.addWidget(self.preview_legend)
        self._row(box, (self.png_action, self.clear_action, self.export_action))

    @property
    def window(self):
        return self.panel.window

    def _row(self, layout: QVBoxLayout, actions: tuple) -> None:
        row = QHBoxLayout()
        for item in actions:
            row.addWidget(self.window._tool_button(item))
        row.addStretch()
        layout.addLayout(row)

    def actions(self) -> tuple:
        return (self.settings_action, self.compute_action, self.stop_action, self.clear_action,
                self.export_action, self.png_action, self.add_action, self.edit_action,
                self.copy_action, self.remove_action)

    # --- stav ----------------------------------------------------------------------------

    def study(self) -> str | None:
        """Vybraná RT studie, nebo None."""
        study_id = self.panel.current_id()
        record = self.panel._record(study_id)
        return study_id if record is not None and record.get("method") == "RT" else None

    def projection_name(self) -> str | None:
        item = self.projections.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _settings(self, study_id: str | None):
        if study_id is None:
            return None
        try:
            return self.window.session.ndt_rt_settings(study_id)
        except DocumentError:
            return None

    def drawing(self):
        """Zdroj a detektor vybrané projekce pro prohlížeč (jen u vybrané RT studie)."""
        study_id = self.study()
        if study_id is None:
            return None
        return self.window.session.ndt_rt_drawing(study_id, self.projection_name())

    def map_view(self) -> tuple[RtMap, str | None] | None:
        """Mapa RT ve 3D: (mapa, pohled – None = celkem, „p0“ … = projekce)."""
        found = self.window.session.ndt_rt_map
        if found is None:
            return None
        view = self.view.currentData() or None
        return found, (view if view in found.views() else None)

    def refresh(self) -> None:
        session = self.window.session
        study_id = self.study()
        settings = self._settings(study_id)
        self._fill_projections(settings)
        found = session.ndt_rt_map
        self._fill_views(found)
        self.settings_label.setText("\n".join(settings.lines()) if settings is not None else "")
        self.settings_label.setVisible(found is None)  # se spočítanou mapou je v souhrnu
        if session.rt_pending:
            progress = session.ndt_rt_progress
            done = f" – {progress[0]} z {progress[1]}" if progress else ""
            self.estimate.setText(f"Počítám projekce RT… {session.computing_seconds:.0f} s"
                                  f"{done}. Výpočet zastavíš tlačítkem Zastavit.")
        elif study_id is not None and found is None and not session.computing:
            self.estimate.setText(self._estimate_text(study_id))
        else:
            self.estimate.setText("")
        if found is not None:
            name = (self.panel._record(session.ndt_rt_study()) or {}).get("name", "")
            lines = [escape(line) for line in found.summary()]
            lines[0] = f"<b>{escape(RT_MAP)}</b> – {escape(name)}"
            lines.insert(1, "<b>" + " · ".join(f"{label} {found.percent(state):.1f} %"
                                               for state, label in STATES.items())
                         .replace(".", ",") + "</b>")
            self.summary.setText("<br>".join(lines))
        else:
            self.summary.setText("")
        self.pick.setVisible(found is not None)
        self.show_pick()
        self._show_setup()
        self._show_preview()

    def _fill_projections(self, settings) -> None:
        selected = self.projection_name()
        names = [p.name for p in settings.projections] if settings is not None else []
        self.projections.blockSignals(True)
        self.projections.clear()
        for projection in (settings.projections if settings is not None else ()):
            item = QListWidgetItem(describe(projection))
            item.setData(Qt.ItemDataRole.UserRole, projection.name)
            self.projections.addItem(item)
        if names:
            self.projections.setCurrentRow(names.index(selected) if selected in names else 0)
        self.projections.blockSignals(False)

    def _fill_views(self, found: RtMap | None) -> None:
        views = found.views() if found is not None else {None: "Celkem"}
        current = self.view.currentData() or ""
        self.view.blockSignals(True)
        self.view.clear()
        for key, label in views.items():
            self.view.addItem(label.lower() if key is None else label, key or "")
        index = self.view.findData(current)
        self.view.setCurrentIndex(index if index >= 0 else 0)
        self.view.blockSignals(False)

    def _estimate_text(self, study_id: str) -> str:
        """Odhad počtu míst a doby; pamatuje se pro stejné zadání."""
        session = self.window.session
        key = (id(session.result), study_id, repr(self.panel._record(study_id)))
        if self._estimate_cache is None or self._estimate_cache[0] != key:
            try:
                samples, step, projections, seconds = session.ndt_rt_estimate(study_id)
                text = (f"Odhad: asi {samples} míst při kroku {_mm(round(step, 2))} mm, "
                        f"{projections} projekcí, asi {math.ceil(seconds)} s (počítá se na "
                        "pozadí, jde zastavit).")
                if projections == 0:
                    text = "Studie zatím nemá projekci – " + ADD_HINT[0].lower() + ADD_HINT[1:]
            except DocumentError as exc:
                text = str(exc)
            self._estimate_cache = (key, text)
        return self._estimate_cache[1]

    def _show_setup(self) -> None:
        study_id, name = self.study(), self.projection_name()
        text = self.window.session.ndt_rt_setup_text(study_id, name) if name else ""
        self.setup_label.setText(text or ADD_HINT)

    def _show_preview(self) -> None:
        session = self.window.session
        name = self.projection_name()
        image = session.ndt_rt_image(name) if name else None
        scale = math.ceil(PREVIEW_WIDTH / image.columns) if image is not None else 1
        shown = session.ndt_rt_preview(name, scale) if image is not None else None
        visible = shown is not None
        for widget in (self.preview_title, self.preview, self.preview_legend):
            widget.setVisible(visible)
        if not visible:
            self.preview.clear()
            return
        width, height, data = shown
        picture = QImage(data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(picture).scaledToWidth(
            PREVIEW_WIDTH, Qt.TransformationMode.FastTransformation)  # buňky zůstanou ostré
        self.preview.setPixmap(pixmap)
        self.preview.setToolTip(f"Projekce {name}: největší prozařovaná tloušťka "
                                f"{_mm(round(image.max_mm, 2))} mm")

    def show_pick(self) -> None:
        """Stav místa mapy RT, na které uživatel klikl ve 3D, v každé projekci."""
        point = self.window.viewer.picked_point if self.window._picked else None
        lines = self.window.session.ndt_rt_describe(point) if point is not None else []
        self.pick.setText("\n".join(lines) if lines else PICK_HINT)

    def refresh_actions(self, ready: bool, has_part: bool, valid: bool) -> None:
        session = self.window.session
        study_id = self.study()
        rt = ready and study_id is not None
        settings = self._settings(study_id)
        has_projection = bool(settings is not None and settings.projections)
        selected = rt and self.projection_name() is not None
        info = session.selection_info(self.window._picked)
        picked = self.window.viewer.picked_point if self.window._picked else None
        has_map = session.ndt_rt_map is not None
        self.settings_action.setEnabled(rt)
        self.compute_action.setEnabled(bool(rt and has_part and valid and has_projection
                                            and not session.rt_pending))
        self.stop_action.setEnabled(session.rt_pending)
        self.clear_action.setEnabled(has_map)
        self.export_action.setEnabled(has_map)
        self.png_action.setEnabled(bool(has_map and self.projection_name() is not None
                                        and session.ndt_rt_image(self.projection_name())))
        self.add_action.setEnabled(bool(rt and has_part and picked is not None
                                        and info.faces == 1 and info.edges == 0))
        for item in (self.edit_action, self.copy_action, self.remove_action):
            item.setEnabled(selected)
        self.setVisible(bool(rt or has_map or session.rt_pending))
        if self.window.ai_busy:  # AI pracuje – ruční úpravy počkají
            for item in self.actions():
                item.setEnabled(False)

    # --- akce ----------------------------------------------------------------------------

    def _projection_changed(self) -> None:
        self._show_setup()
        self._show_preview()
        self.panel.refresh_actions()
        self.window._refresh_probe()  # zdroj a detektor vybrané projekce ve 3D

    def select(self, name: str) -> None:
        for row in range(self.projections.count()):
            if self.projections.item(row).data(Qt.ItemDataRole.UserRole) == name:
                self.projections.setCurrentRow(row)
                return

    def edit_settings(self) -> None:
        study_id = self.study()
        current = self._settings(study_id)
        if current is None:
            return
        dialog = RtDialog(self, current)
        if self.window._exec_dialog(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            settings = dialog.settings()
        except RtError as exc:
            self.window._error("Nastavení RT nejde uložit", str(exc))
            return
        self.panel._apply("Nastavení RT nejde uložit",
                          lambda: self.window.session.set_ndt_rt_settings(study_id, settings))

    def add_projection(self) -> None:
        study_id = self.study()
        point = self.window.viewer.picked_point if self.window._picked else None
        if study_id is None or point is None:
            return
        session = self.window.session
        try:
            projection = self.window._busy(lambda: session.ndt_rt_projection_at(study_id, point))
        except DocumentError as exc:
            self.window._error("Projekci nejde přidat", str(exc))
            return
        self.panel._apply("Projekci nejde přidat",
                          lambda: session.add_ndt_rt_projection(study_id, projection))
        if projection.name in self._names():
            self.select(projection.name)

    def _names(self) -> list[str]:
        settings = self._settings(self.study())
        return [p.name for p in settings.projections] if settings is not None else []

    def _hint(self, name: str) -> str:
        """Nejmenší vzdálenost zdroje ze spočítané mapy (pro dialog projekce)."""
        found = self.window.session.ndt_rt_map
        if found is None:
            return "Nejmenší vzdálenost zdroje f_min ukáže výpočet projekcí."
        for result in found.projections:
            if result.setup.name == name and result.f_min_a is not None:
                return (f"Ze spočítané mapy: f_min pro třídu A {_mm(round(result.f_min_a, 1))} mm"
                        f", pro B {_mm(round(result.f_min_b, 1))} mm (b = "
                        f"{_mm(round(result.b or 0, 1))} mm).")
        return "Nejmenší vzdálenost zdroje f_min ukáže výpočet projekcí."

    def edit_projection(self) -> None:
        study_id, name = self.study(), self.projection_name()
        settings = self._settings(study_id)
        if settings is None or name is None:
            return
        session = self.window.session
        projection = settings.projection(name)
        normal, tilt, turn, reference = session.ndt_rt_angles(projection.aim,
                                                              projection.direction)
        dialog = ProjectionDialog(self, projection, normal, tilt, turn, reference,
                                  self._hint(name))
        if self.window._exec_dialog(dialog) != QDialog.DialogCode.Accepted:
            return
        try:
            changed = dialog.projection()
        except RtError as exc:
            self.window._error("Projekci nejde uložit", str(exc))
            return
        self.panel._apply("Projekci nejde uložit",
                          lambda: session.set_ndt_rt_projection(study_id, name, changed))
        self.select(changed.name)

    def copy_projection(self) -> None:
        study_id, name = self.study(), self.projection_name()
        if study_id is None or name is None:
            return
        text, ok = QInputDialog.getText(
            self, "Kopírovat posunutou",
            f"Posun kopie projekce {name} x; y; z [mm] (třeba podél svaru):", text="0; 0; 0")
        if not ok:
            return
        parts = [p for p in text.replace(",", ".").split(";") if p.strip()]
        try:
            shift = tuple(float(p) for p in parts)
        except ValueError:
            shift = ()
        if len(shift) != 3:
            self.window._error("Projekci nejde zkopírovat",
                               "Posun zadej jako tři čísla oddělená středníkem, např. 0; 150; 0.")
            return
        before = set(self._names())
        self.panel._apply("Projekci nejde zkopírovat",
                          lambda: self.window.session.copy_ndt_rt_projection(study_id, name,
                                                                             shift))
        added = [n for n in self._names() if n not in before]
        if added:
            self.select(added[0])

    def remove_projection(self) -> None:
        study_id, name = self.study(), self.projection_name()
        if study_id is not None and name is not None:
            self.panel._apply("Projekci nejde smazat",
                              lambda: self.window.session.remove_ndt_rt_projection(study_id,
                                                                                   name))

    def start(self) -> None:
        study_id = self.study()
        if study_id is not None:
            self.panel._apply("Projekce RT nejde spočítat",
                              lambda: self.window.session.start_ndt_rt(study_id))

    def stop(self) -> None:
        self.window.stop_rebuild()

    def clear(self) -> None:
        self.window.session.clear_ndt_rt()
        self.window._refresh_all()

    def export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export mapy RT", "projekce-rt.csv",
                                              "CSV (*.csv)")
        if path:
            self.panel._apply("CSV nejde uložit",
                              lambda: self.window.session.export_ndt_rt(path))

    def save_png(self) -> None:
        name = self.projection_name()
        if name is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Náhled prozařované tloušťky",
                                              f"nahled-{name}.png", "PNG (*.png)")
        if path:
            self.panel._apply("PNG nejde uložit",
                              lambda: self.window.session.export_ndt_rt_png(name, path))
