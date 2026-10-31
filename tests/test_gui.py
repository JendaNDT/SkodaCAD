"""Testy okna bez skutečného 3D prohlížeče (ten potřebuje OpenGL a obrazovku)."""

import math
import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QPoint, Qt, Signal  # noqa: E402

from body_count_cases import COUNT_CASE_NAMES, body_count_case  # noqa: E402
from conftest import edge_at, face_at  # noqa: E402
from skodacad.gui.main_window import HELP_HINT, MainWindow  # noqa: E402
from skodacad.inspection import number  # noqa: E402


class FakeViewer(QtWidgets.QWidget):
    selection_changed = Signal(list)
    context_menu_requested = Signal(QPoint)
    probe_dragged = Signal(list, object)
    probe_rotated = Signal(int)

    def __init__(self):
        super().__init__()
        self.parts = []
        self.views = []
        self.highlighted = []
        self.measurement = []  # čáry měření (od, do, popisek)
        self.thickness_map = None  # (uzlů, trojúhelníků, barvy, značka) zobrazené mapy
        self.coverage_map = None
        self.probe = None  # (stav, výstupní bod, konec čáry paprsku, popisek, objem těla)
        self.beam = []  # body lomené dráhy osy UT paprsku v dílu
        self.picked_point = None
        self.probe_drag_enabled = False
        self.target = None  # (objem náhledu cíle, objem zadaného tvaru nebo None)
        self.points = None  # (body, barvy) mapy kontaktních ploch návrhu poloh
        self.plan = None  # ({barva: [(od, do)]}, začátek, zóny) plánu dráhy sondy

    def show_part(self, part, fit=False, accent=None):
        self.parts.append((part, fit))
        self.accent = list(accent or [])  # plochy jinou barvou (plochy řezu)
        self.picked_point = None
        self.measurement = []
        self.thickness_map = None
        self.coverage_map = None
        self.probe = None
        self.beam = []
        self.target = None
        self.points = None
        self.plan = None
        self.selection_changed.emit([])  # jako skutečný prohlížeč: nový díl = nic vybráno

    def highlight(self, shapes):
        self.highlighted = list(shapes)

    def show_design_ghost(self, original):
        self.design_ghost = original

    def show_measurement(self, lines):
        self.measurement = list(lines)

    def show_thickness_map(self, nodes, triangles, colors, marker=None, fill=None):
        self.thickness_map = (len(nodes), len(triangles), list(colors), marker)
        self.map_fill = list(fill or [])

    def hide_thickness_map(self):
        self.thickness_map = None

    def show_coverage_map(self, nodes, triangles, colors, fill=None, topmost=False):
        self.coverage_map = (list(nodes), list(triangles), list(colors))
        self.coverage_fill = list(fill or [])  # plochy řezu dílu šedě (objem v řezu)
        self.coverage_topmost = topmost

    def hide_coverage_map(self):
        self.coverage_map = None

    def show_probe(self, body, state, start, end, text, beam=()):
        self.probe = (state, tuple(start), tuple(end), text, body.volume)
        self.beam = [tuple(p) for p in beam]

    def hide_probe(self):
        self.probe = None
        self.beam = []

    def show_target(self, body, outline=None):
        self.target = (body.volume, outline.volume if outline is not None else None)

    def hide_target(self):
        self.target = None

    def show_points(self, points, colors):
        self.points = (list(points), list(colors))

    def hide_points(self):
        self.points = None

    def show_plan(self, lines, start=None, zones=()):
        self.plan = ({tuple(c): list(v) for c, v in lines.items()}, start, list(zones))

    def hide_plan(self):
        self.plan = None

    def clear_selection(self):
        self.picked_point = None
        self.selection_changed.emit([])

    def click(self, shapes, point=None):
        """Jako by uživatel klikl (s Ctrl) na tyto plochy/hrany."""
        self.picked_point = point
        self.selection_changed.emit([shape.wrapped for shape in shapes])

    def drag_probe(self, shapes, point):
        """Jako by uživatel táhl sondou (režim Jezdit sondou myší / Alt+tah) po ploše."""
        self.picked_point = point
        self.probe_dragged.emit([shape.wrapped for shape in shapes], point)

    def rotate_probe(self, delta_deg):
        self.probe_rotated.emit(delta_deg)

    def fit_all(self):
        self.views.append("fit")

    def set_standard_view(self, name):
        self.views.append(name)

    def dump(self, path):
        """Snímek 3D pohledu (AI asistent si díl „prohlíží“)."""
        with open(path, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\nnahled")
        return True


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(app, examples_dir, tmp_path):
    model = tmp_path / "priruba.json"
    shutil.copy(examples_dir / "priruba.json", model)
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert w.open_model(model)
    yield w
    w.session.dirty = False  # ať se při zavírání neptá na uložení
    w.close()


def tree_texts(w):
    return [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]


def edit(w, name, text):
    field = w._param_fields[name]
    field.setText(text)
    field.editingFinished.emit()
    return field


def test_open_shows_parameters_tree_and_properties(window):
    assert list(window._param_fields) == ["D", "d", "t", "k", "n", "dh", "s"]
    assert window._param_fields["D"].text() == "165"
    assert all(text.startswith("✓") for text in tree_texts(window))
    assert "Objem:  311 093 mm³" in window.props_label.text()
    assert window.windowTitle() == "Plochá příruba (priruba.json) – ŠkodaCAD"
    part, fit = window.viewer.parts[-1]
    assert part is not None and fit


@pytest.mark.parametrize("name", COUNT_CASE_NAMES)
def test_successful_body_counts_are_visible_in_tree_and_properties(window, tmp_path, name):
    document, volume, count, transitions = body_count_case(name)
    path = tmp_path / (name + ".json")
    document.save(path)
    assert window.open_model(path)
    assert window.session.result.ok and window.error_label.isHidden()
    assert f"Počet těles: {count}" in window.props_label.text()
    assert window.session.properties.volume_mm3 == pytest.approx(volume, rel=1e-9)
    for index, status in enumerate(window.session.result.statuses):
        item = window.tree.topLevelItem(index)
        assert item.text(0).startswith("✓")
        if status.id in transitions:
            before, after = transitions[status.id]
            message = f"Počet těles: {before} → {after}."
            assert item.text(0).startswith(f"✓  {message} — ")
            assert message in item.toolTip(0)
        else:
            assert "Počet těles:" not in item.text(0)


def test_long_feature_name_keeps_body_count_visible_in_a_narrow_tree(window, tmp_path):
    document, _volume, _count, _transitions = body_count_case("two_regions")
    long_name = "Velmi dlouhý název vysunutí dvou samostatných kružnic " * 4
    document.features[-1]["name"] = long_name
    path = tmp_path / "long-name.json"
    document.save(path)
    window.tree.setFixedWidth(300)
    assert window.open_model(path)
    QtWidgets.QApplication.processEvents()
    item = window.tree.topLevelItem(1)
    rendered = window.tree.fontMetrics().elidedText(
        item.text(0), Qt.TextElideMode.ElideRight, window.tree.viewport().width() - 40)
    assert "Počet těles: 0 → 2." in rendered
    assert long_name not in rendered  # název se nevejde, počet zůstane čitelný
    assert "Počet těles: 0 → 2." in item.toolTip(0)


def test_coverage_panel_compute_hide_export_and_invalidation(ndt_window, tmp_path, monkeypatch,
                                                             slot_errors):
    from skodacad.ndt import UT_DISCLAIMER
    from skodacad.ndt.devices import Probe

    w = ndt_window
    panel = w.ndt_panel
    session = w.session
    panel.select("s1")
    session.set_ndt_target("s1", [face_at(session.result.part, 0, 0, 0).wrapped], (0, 0, 0))
    session.set_ndt_device("s1", Probe.straight(10))
    session.place_ndt_probe("s1", [face_at(session.result.part, 0, 0, 20).wrapped], (0, 0, 20))
    w._refresh_all()
    assert panel.coverage_action.isEnabled()
    panel.coverage_step.setValue(10)
    panel.coverage_mode.setCurrentIndex(panel.coverage_mode.findData("line"))
    # plochy: citlivost na krok je v panelu taky (zapnutá), krok cíle a tolerance ne
    assert panel.coverage_form.isRowVisible(panel.coverage_convergence)
    assert panel.coverage_convergence.isChecked()
    assert not panel.coverage_form.isRowVisible(panel.tolerance_box)
    panel.coverage_action.trigger()
    assert session.ndt_coverage is not None and w.viewer.coverage_map is not None
    text = panel.coverage_label.text()
    assert UT_DISCLAIMER in text
    assert text.startswith("<b>Geometricky pokryto ")
    assert session.ndt_coverage.assumptions["convergence"]["coarse_steps_mm"] == (20, 20)
    assert "citlivost na krok (" in text or "citlivý na krok" in text
    assert session.ndt_coverage.assumptions["convergence_text"] in text
    assert "Průřez svarem" not in text and not panel.volume_legend.isVisibleTo(panel)
    assert w.viewer.probe is not None
    panel.coverage_convergence.setChecked(False)
    panel.coverage_action.trigger()
    assert "convergence" not in session.ndt_coverage.assumptions
    assert "Citlivost na krok neověřena." in panel.coverage_label.text()
    path = tmp_path / "pokryti.csv"
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a: (str(path), "CSV"))
    panel.export_coverage_action.trigger()
    assert path.exists()
    panel.clear_coverage_action.trigger()
    assert session.ndt_coverage is None and w.viewer.coverage_map is None
    panel.coverage_action.trigger()
    panel.shift_probe(1)
    assert session.ndt_coverage is None and w.viewer.coverage_map is None


def test_scan_slider_clears_coverage_summary_and_export(ndt_window, slot_errors):
    from skodacad.ndt.devices import Probe

    w = ndt_window
    session, panel = w.session, w.ndt_panel
    session.set_ndt_target("s1", [face_at(session.result.part, 0, 0, 0).wrapped], (0, 0, 0))
    session.set_ndt_device("s1", Probe.straight(10))
    session.place_ndt_probe("s1", [face_at(session.result.part, 0, 0, 20).wrapped], (0, 0, 20))
    session.scan_ndt_line(20, 5)
    session.compute_ndt_coverage(mode="line", step_mm=10, length_mm=10)
    panel.select("s1")
    w._refresh_all()
    assert "Geometricky pokryto:" in panel.coverage_label.text()
    assert panel.export_coverage_action.isEnabled()
    assert panel.clear_coverage_action.isEnabled()
    panel.scan_slider.setValue(1)
    assert session.ndt_coverage is None and w.viewer.coverage_map is None
    assert "Geometricky pokryto:" not in panel.coverage_label.text()
    assert not panel.export_coverage_action.isEnabled()
    assert not panel.clear_coverage_action.isEnabled()
    assert slot_errors == []


def test_volume_target_panel_loads_and_needs_placed_probe_for_coverage(ndt_window):
    from test_ndt_volume_session import target

    session = ndt_window.session
    session.set_ndt_volume_target("s1", target())
    ndt_window.ndt_panel.select("s1")
    ndt_window._refresh_all()
    assert "objem 2000 mm³" in ndt_window.ndt_panel.details.text()
    assert not ndt_window.ndt_panel.coverage_action.isEnabled()  # sonda není přiložená
    assert "po přiložení sondy" in ndt_window.ndt_panel.coverage_estimate.text()


def test_panel_volume_coverage_options_estimate_and_summary(ndt_window, slot_errors):
    from skodacad.ndt import UT_DISCLAIMER
    from skodacad.ndt.devices import Probe
    from test_ndt_volume_session import target

    w = ndt_window
    session, panel = w.session, w.ndt_panel
    form = panel.coverage_form
    panel.select("s1")
    assert not form.isRowVisible(panel.coverage_target_step)  # plochy: jen krok výpočtu
    assert form.labelForField(panel.coverage_step).text() == "Krok výpočtu [mm]:"
    session.set_ndt_volume_target("s1", target())
    session.set_ndt_device("s1", Probe.straight(10))
    session.place_ndt_probe("s1", [face_at(session.result.part, 0, 0, 20).wrapped], (0, 0, 20))
    w._refresh_all()
    assert form.isRowVisible(panel.coverage_target_step)
    assert form.labelForField(panel.coverage_step).text() == "Krok pojezdu [mm]:"
    # krok cíle = šestina menšího rozměru průřezu 10 × 10 mm, dolů na 0,5 mm (rozbor 15)
    assert (panel.coverage_step.value(), panel.coverage_target_step.value()) == (5, 1.5)
    assert panel.coverage_convergence.isChecked() and panel.coverage_tolerance_auto.isChecked()
    assert not panel.coverage_tolerance.isEnabled()
    assert panel.coverage_estimate.text().startswith("Odhad: 686 buněk cíle, ")
    assert "Doporučený krok cíle" not in panel.coverage_estimate.text()
    assert "hrubší běh" in panel.coverage_estimate.text()
    assert panel.coverage_action.isEnabled()
    panel.coverage_mode.setCurrentIndex(panel.coverage_mode.findData("line"))
    assert not panel.coverage_action.isEnabled()  # čára bez rozevření nevymezuje objem
    assert "nevymezuje pokrytý objem" in panel.coverage_estimate.text()
    panel.coverage_spread.setValue(5)
    assert panel.coverage_action.isEnabled()
    panel.coverage_spread.setValue(0)
    panel.coverage_mode.setCurrentIndex(panel.coverage_mode.findData("face"))
    panel.coverage_step.setValue(25)
    panel.coverage_target_step.setValue(5)
    assert panel.coverage_estimate.text().startswith("Odhad: 16 buněk cíle, 45 poloh sondy")
    assert panel.coverage_estimate.text().endswith("Doporučený krok cíle 1.5 mm.")
    w._refresh_all()  # stejný cíl – vlastní krok cíle zůstane
    assert panel.coverage_target_step.value() == 5
    panel.coverage_tolerance_auto.setChecked(False)
    assert panel.coverage_tolerance.isEnabled()
    panel.coverage_tolerance.setValue(10)
    panel.coverage_action.trigger()
    result = session.ndt_coverage
    assert result.assumptions["tolerance_mm"] == 10
    assert result.assumptions["convergence"]["coarse_steps_mm"] == (50.0, 10.0)
    text = panel.coverage_label.text()
    assert text.startswith("<b>Geometricky pokryto ")
    assert UT_DISCLAIMER in text
    # tolerance 10 mm < pojezd 25 mm × 0,71: hledání neúplné – panel to řekne a porovnání
    # (hrubý běh hledá podle své mřížky) to ukáže jako citlivost
    assert "hledání nemusí najít všechny paprsky" in text
    assert "Výsledek je citlivý na krok" in text
    assert "Stav vnitřního bodu zastupuje objem jeho kusu buňky" in text
    assert "Dovnitř se podívej tlačítkem <b>Průřez svarem</b>" in text
    nodes, triangles, _colors = w.viewer.coverage_map  # 07C.3: povrch cíle navrch
    assert triangles and w.viewer.coverage_topmost and w.viewer.coverage_fill == []
    assert w.viewer.target is None  # mapa nahradí průhledný náhled cíle
    assert panel.volume_legend.isVisibleTo(panel)
    percent = result.percent("covered")
    assert panel.cross_section_action.isEnabled()
    panel.cross_section_action.trigger()
    assert session.section_settings.target is not None and session.section_range() == (0, 20)
    assert w.section_combo.currentData() == "target"
    assert "kolmo na osu cíle, 10.00 mm od jeho začátku" in w.section_info.text()
    assert "(šedě pod mapou pokrytí)" in w.section_info.text()
    assert w.viewer.coverage_fill  # plochy řezu dílu šedě, průřez cíle barevně
    assert session.ndt_coverage is result and result.percent("covered") == percent
    assert "Průřez svarem</b>" not in panel.coverage_label.text()
    action(w, "Řez modelem").trigger()  # vypnout řez
    assert session.section_settings is None
    w.section_combo.setCurrentIndex(w.section_combo.findData("target"))
    w._section_kind_chosen()  # totéž z panelu Řez
    assert session.section_settings.target is not None
    panel.coverage_target_step.setValue(0.5)  # 20 × 20 × 40 buněk – pořád v mezích
    assert panel.coverage_action.isEnabled()
    panel.coverage_step.setValue(0.5)  # pojezd 0,5 mm na desce 200 × 100 = příliš poloh
    assert not panel.coverage_action.isEnabled()
    assert "příliš mnoho poloh" in panel.coverage_estimate.text()
    assert slot_errors == []


# --- 07C: editor a náhled cílového objemu ------------------------------------------------


@pytest.fixture
def weld_window(app, examples_dir, tmp_path, no_dialogs, slot_errors):
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert w.open_model(examples_dir / "ndt" / "cilove_objemy" / "tupy_svar_objem.json",
                        template=True)
    yield w
    w.session.dirty = False
    w.close()


def test_volume_examples_menu_and_target_preview(window, slot_errors):
    from PySide6.QtWidgets import QMenu

    menu = next(m for m in window.findChildren(QMenu) if m.title() == "NDT – cílové objemy")
    labels = [a.text() for a in menu.actions()]
    assert labels == ["NDT 07A – Objem tupého svaru V", "NDT 07A – Objemy koutových svarů"]
    window.session.dirty = False
    action(window, labels[0]).trigger()
    assert "svaru V" in window.windowTitle()
    assert window.viewer.target is None  # studie zatím není vybraná
    window.ndt_panel.select("s1")
    volume, outline = window.viewer.target
    assert volume == pytest.approx(14_613.843876, abs=1e-5) and outline is None
    assert "tupý svar V, objem 14613.8 mm³" in window.ndt_panel.details.text()
    window.ndt_panel.select(None)
    assert window.viewer.target is None
    assert slot_errors == []


def test_target_dialog_loads_example_and_unchanged_ok_keeps_target(weld_window, monkeypatch,
                                                                   slot_errors):
    import copy

    from PySide6.QtWidgets import QDialogButtonBox

    w = weld_window
    w.ndt_panel.select("s1")
    before = copy.deepcopy(w.session.ndt_study("s1")["target"])
    seen = {}

    def run(self, dialog):
        seen.update(kind=dialog.kind.currentText(), axis=dialog.axis.currentText(),
                    across=dialog.across.currentText(), height=dialog.height_label.text(),
                    thickness=dialog.dimensions["thickness_mm"].text(),
                    fillet=dialog.dimensions["leg_across_mm"].isVisibleTo(dialog),
                    volume=dialog.volume_label.text(), edge=dialog.edge_button.isEnabled(),
                    ok=dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled(),
                    profiles=len(dialog.preview.profiles))
        dialog.accept()
        seen["check"] = dialog.check_label.text()
        return dialog.result()

    monkeypatch.setattr(MainWindow, "_exec_dialog", run)
    action(w, "Cílový objem…").trigger()
    assert seen.pop("check").startswith("V dílu v pořádku: účinný objem v materiálu "
                                        "14 613.844 mm³")
    assert seen == {"kind": "Tupý svar V", "axis": "+Y", "across": "+X", "height": "+Z",
                    "thickness": "12", "fillet": False,
                    "volume": "Zadaný objem (průřez × délka): <b>14 613.844 mm³</b>",
                    "edge": False, "ok": True, "profiles": 3}
    assert w.session.ndt_study("s1")["target"] == before
    assert not w.session.dirty  # stejné zadání = žádná změna, žádný krok Zpět
    assert slot_errors == []


def test_target_dialog_keeps_invalid_weld_open_and_rejects_bad_numbers(weld_window,
                                                                       monkeypatch):
    from PySide6.QtWidgets import QDialogButtonBox

    w = weld_window
    w.ndt_panel.select("s1")
    before = w.session.ndt_study("s1")["target"]
    seen = {}

    def run(self, dialog):
        dialog.dimensions["thickness_mm"].setText("20")
        seen["volume"] = dialog.volume_label.text()  # ze vzorce jde spočítat …
        dialog.accept()  # … ale v dílu se svar nevejde → dialog zůstane otevřený
        seen.update(result=dialog.result(), check=dialog.check_label.text())
        dialog.dimensions["thickness_mm"].setText("dvanáct")
        seen.update(error=dialog.error_label.text(), profiles=dialog.preview.profiles,
                    ok=dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        dialog.dimensions["thickness_mm"].setText("12,0")  # desetinná čárka platí
        seen["fixed"] = dialog.error_label.text()
        return 0

    monkeypatch.setattr(MainWindow, "_exec_dialog", run)
    w.ndt_panel.volume_action.trigger()
    assert "mm³" in seen["volume"] and seen["result"] == 0
    assert "Zadaný svar není celý v materiálu dílu – chybí" in seen["check"]
    assert "„Tloušťka plechu [mm]“ musí být číslo" in seen["error"]
    assert seen["profiles"] == [] and not seen["ok"] and seen["fixed"] == ""
    assert w.session.ndt_study("s1")["target"] == before


def test_target_dialog_replaces_faces_with_prism_and_undo(ndt_window, monkeypatch, slot_errors):
    w = ndt_window
    panel = w.ndt_panel
    panel.select("s1")
    faces = w.session.ndt_study("s1")["target"]
    assert w.viewer.target is None

    def run(self, dialog):
        assert dialog.kind.currentText() == "Tupý svar V"  # výchozí – nutno přepsat
        dialog.kind.setCurrentIndex(dialog.kind.findData("volume"))
        assert dialog.table.isVisibleTo(dialog)
        assert not dialog.dimensions["thickness_mm"].isVisibleTo(dialog)
        for field, value in zip(dialog.origin, ("-5", "-5", "5"), strict=True):
            field.setText(value)
        dialog.length.setText("10")
        assert "1 000.000 mm³" in dialog.volume_label.text()  # 10 × 10 × 10 mm
        dialog.add_vertex.click()
        assert dialog.table.rowCount() == 5 and dialog.error_label.text() != ""
        dialog.table.selectRow(4)
        dialog.remove_vertex.click()
        assert dialog.table.rowCount() == 4 and dialog.error_label.text() == ""
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(MainWindow, "_exec_dialog", run)
    panel.volume_action.trigger()
    target = w.session.ndt_study("s1")["target"]
    assert target["kind"] == "volume" and target["frame"]["origin"] == [-5.0, -5.0, 5.0]
    assert "obecný hranol, objem 1000 mm³" in panel.details.text()
    assert "nahradil" in w.statusBar().currentMessage()
    assert w.viewer.target == (pytest.approx(1000), None)
    action(w, "Zpět").trigger()
    assert w.session.ndt_study("s1")["target"] == faces
    assert w.viewer.target is None
    assert slot_errors == []


def test_target_dialog_edge_helper_and_custom_direction(ndt_window, monkeypatch, slot_errors):
    w = ndt_window
    session = w.session
    custom = {"kind": "volume", "frame": {"origin": [0, 0, 5], "axis": [0.6, 0.8, 0],
                                          "across": [0.8, -0.6, 0]},
              "length_mm": 10, "profile_mm": [[0, 0], [10, 0], [10, 10], [0, 10]]}
    session.set_ndt_volume_target("s1", custom)
    w._refresh_all()  # okno převezme nový přepočet (jinak by překreslení smazalo výběr)
    before = session.ndt_study("s1")["target"]
    w.ndt_panel.select("s1")
    w.viewer.click([edge_at(session.result.part, 0, -50, 20)])  # horní hrana desky podél X
    seen = {}

    def run(self, dialog):
        seen.update(axis=dialog.axis.currentText(), across=dialog.across.currentText(),
                    height=dialog.height_label.text(), edge=dialog.edge_button.isEnabled())
        if seen.get("second"):
            dialog.edge_button.click()
            seen.update(origin=[f.text() for f in dialog.origin], length=dialog.length.text(),
                        edge_axis=dialog.axis.currentText(),
                        edge_across=dialog.across.currentText())
            return 0
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(MainWindow, "_exec_dialog", run)
    w.ndt_panel.volume_action.trigger()
    assert seen == {"axis": "vlastní (0.6; 0.8; 0)", "across": "vlastní (0.8; -0.6; 0)",
                    "height": "+Z", "edge": True}
    assert session.ndt_study("s1")["target"] == before  # šikmý směr zůstal beze změny
    seen["second"] = True
    w.ndt_panel.volume_action.trigger()
    assert seen["origin"] == ["-100", "-50", "20"] and seen["length"] == "200"
    assert seen["edge_axis"] == "+X" and seen["edge_across"] in ("+Y", "−Y", "+Z", "−Z")
    assert slot_errors == []


def test_parameter_change_rebuilds(window):
    volume_before = window.session.properties.volume_mm3
    edit(window, "n", "8")
    assert window.session.document.parameters["n"] == 8
    assert window.windowTitle().startswith("*")
    expected = volume_before - 4 * math.pi / 4 * 18**2 * 18  # 4 díry Ø18 navíc, tloušťka 18
    assert f"Objem:  {number(expected, 0)} mm³" in window.props_label.text()
    assert window.viewer.parts[-1][1] is False  # po změně parametru se kamera nehýbe


def test_invalid_parameter_is_marked_red(window):
    field = edit(window, "n", "neexistuje + 1")
    assert "c0392b" in field.styleSheet()
    assert "neznámý parametr" in field.toolTip()
    assert window.session.document.parameters["n"] == 4
    edit(window, "n", "6")
    assert field.styleSheet() == ""


def test_failing_feature_shows_error(window):
    edit(window, "s", "50")
    assert window.error_label.isVisibleTo(window)
    assert "Sražení obvodu" in window.error_label.text()
    texts = tree_texts(window)
    assert texts[4].startswith("✕") and texts[5].startswith("·")


def test_save_clears_dirty(window):
    edit(window, "D", "200")
    assert window.save()
    assert not window.session.dirty
    assert not window.windowTitle().startswith("*")


def test_examples_menu_opens_template(window, examples_dir):
    window.session.dirty = False
    assert window.open_model(examples_dir / "krabicka.json", template=True)
    assert window.session.path is None
    assert "Krabička" in window.windowTitle()
    assert list(window._param_fields) == ["L", "W", "H", "r", "stena", "dira"]


def test_selection_shows_in_status_bar(window):
    part = window.session.result.part
    window.viewer.click([face_at(part, 60, 0, 18)])
    assert window.statusBar().currentMessage().startswith("Plocha – rovinná")
    assert "skica nebo díra na ploše" in window.statusBar().currentMessage()
    window.viewer.click([edge_at(part, 82.5, 0, 0), edge_at(part, 0, 32, 0)])
    assert window.statusBar().currentMessage().startswith("Vybráno: 2 hrany")
    window.viewer.click([])
    assert window.statusBar().currentMessage() == HELP_HINT


# --- tlačítka a položky menu -----------------------------------------------------------
# Každá akce se opravdu „stiskne“. Chyba uvnitř akce by v Qt jen tiše skončila v
# sys.excepthook, proto ji fixture slot_errors zachytí a test pak selže.


@pytest.fixture
def slot_errors(monkeypatch):
    import sys

    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, value, tb: errors.append(value))
    return errors


@pytest.fixture
def no_dialogs(monkeypatch):
    """Dialogy by v testu čekaly na kliknutí – nahradíme je zrušením / zavřením."""
    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

    shown = []
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("", False))
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a, **k: ("", False))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    for name in ("information", "about", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, n=name, **k: shown.append(n))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Discard)
    # Skicář (a další vlastní dialogy) jde přes MainWindow._exec_dialog → „Zrušit“.
    monkeypatch.setattr(MainWindow, "_exec_dialog",
                        lambda self, dialog: shown.append(type(dialog).__name__) or 0)
    return shown


def action(window, text):
    from PySide6.QtGui import QAction

    matches = [a for a in window.findChildren(QAction) if a.text() == text]
    assert matches, f"akce „{text}“ v okně není"
    return matches[0]


def test_view_buttons_switch_view(window, slot_errors):
    from skodacad.gui.viewer_views import VIEW_LABELS

    for key, (label, _shortcut) in VIEW_LABELS.items():
        action(window, label).trigger()
        assert window.viewer.views[-1] == key
    action(window, "Celý díl").trigger()
    assert window.viewer.views[-1] == "fit"
    assert slot_errors == []


def test_examples_menu_items_open_examples(window, slot_errors):
    for stem, title in (("krabicka", "Krabička"), ("hridel", "hřídel"), ("priruba", "příruba")):
        window.session.dirty = False
        action(window, stem).trigger()
        assert title in window.windowTitle()
        assert window.session.path is None
    assert slot_errors == []


def test_ndt_reference_parts_are_in_examples_menu_in_order(window, slot_errors):
    from PySide6.QtWidgets import QMenu

    menu = next(m for m in window.findChildren(QMenu) if m.title() == "NDT – referenční díly")
    labels = [a.text() for a in menu.actions()]
    assert len(labels) == 10
    assert labels[0] == "NDT 1 – Deska"
    assert "NDT 9 – Blok se štěrbinou a slepým otvorem" in labels
    assert "NDT 10 – Konstrukční návrh kapsy pro jho" in labels
    window.session.dirty = False
    action(window, "NDT 3 – Deska se žebrem").trigger()
    assert "žebrem" in window.windowTitle()
    assert window.session.result.part.volume == pytest.approx(460_000)
    assert slot_errors == []


@pytest.mark.parametrize("fmt", ["step", "stl", "3mf"])
def test_export_menu_writes_file(window, slot_errors, monkeypatch, tmp_path, fmt):
    from PySide6.QtWidgets import QFileDialog

    target = tmp_path / f"export.{fmt}"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    label = next(text for f, text in __import__(
        "skodacad.gui.main_window", fromlist=["EXPORT_FORMATS"]).EXPORT_FORMATS if f == fmt)
    action(window, label + "…").trigger()
    assert target.stat().st_size > 0
    assert slot_errors == []


def test_open_and_save_as_buttons(window, slot_errors, monkeypatch, examples_dir, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **k: (str(examples_dir / "hridel.json"), ""))
    action(window, "Otevřít…").trigger()
    assert "hřídel" in window.windowTitle()

    target = tmp_path / "kopie.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    action(window, "Uložit jako…").trigger()
    assert target.exists()
    assert window.session.path == target
    assert slot_errors == []


def test_every_action_runs_without_error(window, slot_errors, no_dialogs):
    from PySide6.QtGui import QAction

    actions = [a for a in window.findChildren(QAction) if a.text() and a.text() != "Konec"]
    assert len(actions) >= 15
    # Zapnutá mapa tloušťky by se počítala znovu s každou další změnou – stisknout až nakonec.
    actions.sort(key=lambda a: a is window.thickness_map_action)
    for item in actions:
        item.trigger()
    assert slot_errors == []
    assert {"information", "about"} <= set(no_dialogs)  # Ovládání a O aplikaci se ukázaly


# --- tvorba a úpravy dílu v okně ---------------------------------------------------------


@pytest.fixture
def empty_window(app, examples_dir, tmp_path, no_dialogs, slot_errors):
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    action(w, "Nový").trigger()
    yield w
    assert slot_errors == [], slot_errors
    w.session.dirty = False
    w.close()


def selected_text(w):
    item = w.tree.currentItem()
    return item.text(0) if item else None


def form_field(w, key):
    return w.feature_editor.form.widget(key)


def test_variable_fillet_selection_form_end_labels_reverse_and_undo(empty_window):
    from PySide6.QtCore import QPersistentModelIndex

    from skodacad.selectors import select_edges

    w = empty_window
    build_box(w)
    edge, = select_edges(w.session.result.part, {"parallel": "Z", "near": [20, 15, 5]}, float)
    w._selection_changed([edge.wrapped])
    assert w.selection_actions["variable_fillet"].isEnabled()
    w.selection_actions["variable_fillet"].trigger()
    fid = w._selected_id
    persistent = QPersistentModelIndex(w.tree.currentIndex())
    assert w.session.feature(fid)["type"] == "variable_fillet"
    set_text(form_field(w, "radius_start"), "2")
    set_text(form_field(w, "radius_end"), "6")
    assert w.session.result.ok
    assert persistent.isValid() and "Proměnné zaoblení" in persistent.data()
    expected = 12000 - (1 - math.pi / 4) * 10 / 3 * (4 + 12 + 36)
    assert w.session.result.part.volume == pytest.approx(expected, abs=2e-6)
    assert [line[2] for line in w.viewer.measurement] == ["R1 = 2 mm", "R2 = 6 mm"]
    assert w.viewer.measurement[0][0].Z == pytest.approx(0)
    form_field(w, "reverse").setChecked(True)
    assert w.session.feature(fid)["reverse"] is True
    assert w.viewer.measurement[0][0].Z == pytest.approx(10)
    w.undo_action.trigger()
    assert w.viewer.measurement[0][0].Z == pytest.approx(0)
    assert persistent.isValid() and w.tree.currentIndex() == persistent


def set_text(widget, text):
    widget.setText(text)
    widget.editingFinished.emit()


def build_box(w):
    action(w, "Skica").trigger()
    action(w, "Vysunutí").trigger()


def test_new_part_from_scratch(empty_window):
    w = empty_window
    assert w.tree.topLevelItemCount() == 0
    assert "Vyber prvek" in w.feature_editor.title.text()
    build_box(w)
    assert tree_texts(w) == ["✓  Skica „Skica 1“",
                             "✓  Počet těles: 0 → 1. — Vysunutí „Vysunutí 1“"]
    # Nový prvek je hned vybraný; jeho nové hlášení nesmí zmizet.
    assert selected_text(w) == "✓  Počet těles: 0 → 1. — Vysunutí „Vysunutí 1“"
    assert "Vysunutí" in w.feature_editor.title.text()
    assert "Objem:  12 000 mm³" in w.props_label.text()
    assert w.viewer.parts[-1][0] is not None


def test_edit_feature_value_in_form(empty_window):
    w = empty_window
    build_box(w)
    set_text(form_field(w, "distance"), "2 * 12,5".replace(",", "."))
    assert "Rozměry:  40.00 × 30.00 × 25.00 mm" in w.props_label.text()
    set_text(form_field(w, "distance"), "7,5")  # desetinná čárka
    assert "× 7.50 mm" in w.props_label.text()


def test_invalid_form_value_is_red_and_model_unchanged(empty_window):
    w = empty_window
    build_box(w)
    action(w, "Zaoblení").trigger()
    radius = form_field(w, "radius")
    set_text(radius, "")
    assert "c0392b" in radius.styleSheet()
    assert "povinná" in w.statusBar().currentMessage()
    assert w.session.feature("fillet1")["radius"] == 2
    set_text(radius, "1")
    assert radius.styleSheet() == ""
    assert w.session.feature("fillet1")["radius"] == 1


def test_cut_with_choice_field(empty_window):
    w = empty_window
    build_box(w)
    action(w, "Skica").trigger()  # druhá skica – automaticky na horní ploše
    sketch = w.session.feature("sketch2")
    assert sketch["plane"] == "top"
    action(w, "Vysunutí").trigger()
    operation = form_field(w, "operation")
    operation.setCurrentIndex(operation.findData("cut"))
    assert w.session.feature("extrude2")["operation"] == "cut"
    assert w.session.result.ok
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - math.pi * 25 * 10)


def test_shapes_editor_adds_hole(empty_window):
    w = empty_window
    build_box(w)
    w.tree.setCurrentItem(w.tree.topLevelItem(0))  # vybrat skicu
    shapes = form_field(w, "elements")
    shapes.add_shape("circle")
    assert [e["shape"] for e in w.session.feature("sketch1")["elements"]] == ["rectangle",
                                                                             "circle"]
    mode = shapes._form.widget("mode")
    mode.setCurrentIndex(mode.findData("subtract"))
    assert w.session.feature("sketch1")["elements"][1]["mode"] == "subtract"
    assert w.session.properties.volume_mm3 == pytest.approx(
        (40 * 30 - math.pi * 10**2) * 10, rel=1e-6)
    assert shapes.list.item(1).text() == "Kružnice (odečíst)"


def test_delete_move_and_undo(empty_window, no_dialogs):
    w = empty_window
    build_box(w)
    w.tree.setCurrentItem(w.tree.topLevelItem(0))
    action(w, "Smazat prvek").trigger()  # skicu používá vysunutí → jen varování
    assert "warning" in no_dialogs
    assert w.tree.topLevelItemCount() == 2

    w.tree.setCurrentItem(w.tree.topLevelItem(1))
    action(w, "Posunout nahoru").trigger()
    assert tree_texts(w)[0].startswith("✕  Vysunutí")  # vysunutí před skicou nejde
    assert w.error_label.isVisibleTo(w)

    action(w, "Zpět").trigger()
    assert all(text.startswith("✓") for text in tree_texts(w))
    action(w, "Znovu").trigger()
    assert tree_texts(w)[0].startswith("✕")
    action(w, "Zpět").trigger()

    w.tree.setCurrentItem(w.tree.topLevelItem(1))
    action(w, "Smazat prvek").trigger()
    assert tree_texts(w) == ["✓  Skica „Skica 1“"]
    assert selected_text(w) == "✓  Skica „Skica 1“"


def test_undo_redo_enabled_states(empty_window):
    w = empty_window
    assert not action(w, "Zpět").isEnabled()
    action(w, "Skica").trigger()
    assert action(w, "Zpět").isEnabled() and not action(w, "Znovu").isEnabled()
    action(w, "Zpět").trigger()
    assert w.tree.topLevelItemCount() == 0
    assert action(w, "Znovu").isEnabled()


def test_add_and_delete_parameter(empty_window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    w = empty_window
    answers = iter([("sirka", True), ("55", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers))
    action(w, "Přidat parametr…").trigger()
    assert w._param_fields["sirka"].text() == "55"

    build_box(w)
    w.tree.setCurrentItem(w.tree.topLevelItem(0))
    shapes = form_field(w, "elements")
    set_text(shapes._form.widget("width"), "sirka")
    assert "Rozměry:  55.00 × 30.00" in w.props_label.text()

    set_text(w._param_fields["sirka"], "60")
    assert "Rozměry:  60.00 × 30.00" in w.props_label.text()

    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("sirka", True))
    action(w, "Smazat parametr…").trigger()  # používá ho skica → jen varování
    assert "sirka" in w._param_fields


def test_part_name_and_material(empty_window):
    w = empty_window
    build_box(w)
    set_text(w.name_edit, "Držák senzoru")
    assert w.windowTitle().startswith("*Držák senzoru")
    combo = w.material_combo
    combo.setCurrentIndex(combo.findData("hliník"))
    assert w.session.document.material == "hliník"
    assert "(hliník)" in w.props_label.text()
    action(w, "Zpět").trigger()
    assert w.material_combo.currentData() == "ocel"


def test_example_material_is_shown(window):
    assert window.material_combo.currentData() == "ocel"
    window.session.dirty = False
    action(window, "krabicka").trigger()
    assert window.material_combo.currentData() == "PETG"


# --- výběr ve 3D → prvky ---------------------------------------------------------------


def shown_part(w):
    return w.session.result.part


def test_fillet_from_clicked_edge(empty_window):
    w = empty_window
    build_box(w)
    fillet = action(w, "Zaoblit vybrané hrany")
    assert not fillet.isEnabled()  # nic nevybráno
    w.viewer.click([edge_at(shown_part(w), 20, -15, 5)])
    assert fillet.isEnabled()
    fillet.trigger()
    assert selected_text(w) == "✓  Počet těles: 1 → 1. — Zaoblení „Zaoblení 1“"
    assert "hrana mezi přední a pravou plochou" in form_field(w, "edges").text()
    loss = (2 ** 2 - math.pi * 2 ** 2 / 4) * 10
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - loss)
    assert len(w.viewer.highlighted) == 1  # zvýrazněná zaoblená hrana
    assert not fillet.isEnabled()  # díl se překreslil, výběr zmizel
    set_text(form_field(w, "radius"), "4")  # poloměr dál jde měnit ve formuláři
    loss = (4 ** 2 - math.pi * 4 ** 2 / 4) * 10
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - loss)


def test_add_clicked_edges_to_selected_fillet(empty_window):
    w = empty_window
    build_box(w)
    w.viewer.click([edge_at(shown_part(w), 20, -15, 5)])
    action(w, "Srazit vybrané hrany").trigger()
    w.viewer.click([edge_at(shown_part(w), -20, 15, 5), edge_at(shown_part(w), -20, -15, 5)])
    add = action(w, "Přidat vybrané hrany do: Sražení „Sražení 1“")
    assert add.isEnabled()
    add.trigger()
    edges = w.session.feature("chamfer1")["edges"]
    assert edges == [{"between": ["front", "right"]}, {"face": "left", "parallel": "Z"}]
    assert "hrany na levé ploše, rovnoběžné s osou Z" in form_field(w, "edges").text()
    assert len(w.viewer.highlighted) == 3
    w.viewer.click([edge_at(shown_part(w), 0, 15, 0)])
    action(w, "Nahradit hrany vybraného prvku výběrem").trigger()
    assert w.session.feature("chamfer1")["edges"] == {"between": ["bottom", "back"]}


def test_sketch_on_clicked_face(empty_window):
    w = empty_window
    build_box(w)
    sketch = action(w, "Skica na vybrané ploše")
    w.viewer.click([face_at(shown_part(w), 0, -15, 5)], point=(8, -15, 4))
    sketch.trigger()
    feature = w.session.feature("sketch2")
    assert feature["plane"] == "front"
    assert feature["elements"][0]["center"] == [8, 4]  # na přední ploše: x a výška z
    assert form_field(w, "plane").currentData() == "front"


def test_direct_edit_preview_cancel_and_apply(empty_window, monkeypatch):
    w = empty_window
    build_box(w)
    before = w.session.document.to_dict()
    part = shown_part(w)
    face = face_at(part, 0, 0, 10)
    w.viewer.click([face], point=(0, 0, 10))

    def cancel(dialog):
        dialog.value.setText("2")
        dialog.calculate()
        assert dialog.apply_button.isEnabled()
        assert w.session.document.to_dict() == before
        assert w.viewer.parts[-1][0].volume == pytest.approx(40 * 30 * 12)
        dialog.value.setText("3")
        assert not dialog.apply_button.isEnabled()
        assert w.viewer.parts[-1][0].volume == pytest.approx(40 * 30 * 10)
        return QtWidgets.QDialog.DialogCode.Rejected

    monkeypatch.setattr(w, "_exec_dialog", cancel)
    action(w, "Posunout vybranou plochu…").trigger()
    assert w.session.document.to_dict() == before
    assert w.viewer.parts[-1][0].volume == pytest.approx(40 * 30 * 10)
    w.viewer.click([face_at(shown_part(w), 0, 0, 10)], point=(0, 0, 10))

    def accept(dialog):
        dialog.value.setText("2")
        dialog.calculate()
        assert dialog.apply_button.isEnabled()
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(w, "_exec_dialog", accept)
    action(w, "Posunout vybranou plochu…").trigger()
    assert w.session.result.part.volume == pytest.approx(40 * 30 * 12)
    w.session.undo()
    assert w.session.document.to_dict() == before


def test_ai_direct_edit_needs_user_confirmation(empty_window, monkeypatch):
    w = empty_window
    build_box(w)
    before = w.session.document.to_dict()
    w.viewer.click([face_at(shown_part(w), 0, 0, 10)], point=(0, 0, 10))

    def confirm(dialog):
        dialog.calculate()
        assert w.session.document.to_dict() == before
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(w, "_exec_dialog", confirm)
    output = w.assistant_panel.tools.run("propose_direct_edit", {"kind": "move_face", "value": 2})
    assert output.changed
    assert w.session.result.part.volume == pytest.approx(40 * 30 * 12)


def test_direct_edit_accepts_parameter_expression(empty_window, monkeypatch):
    w = empty_window
    build_box(w)
    w.session.add_parameter("zmena", "2")
    w._reload_all()
    w.viewer.click([face_at(shown_part(w), 0, 0, 10)], point=(0, 0, 10))

    def confirm(dialog):
        dialog.value.setText("neznamy + 1")
        dialog.calculate()
        assert not dialog.apply_button.isEnabled()
        dialog.value.setText("zmena * 2")
        dialog.calculate()
        assert dialog.apply_button.isEnabled()
        assert dialog.preview.result.part.volume == pytest.approx(40 * 30 * 14)
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(w, "_exec_dialog", confirm)
    action(w, "Posunout vybranou plochu…").trigger()
    assert w.session.document.features[-1]["distance"] == "zmena * 2"
    w.session.set_parameter("zmena", "3")
    assert w.session.result.part.volume == pytest.approx(40 * 30 * 16)


def test_diameter_dialog_warns_about_hole_annotations(empty_window):
    from skodacad.gui.direct_edit_dialog import DirectEditDialog

    dialog = DirectEditDialog(empty_window, "face_diameter", [], None)
    assert any("označení závitu" in label.text() for label in dialog.findChildren(QtWidgets.QLabel))


def test_curved_face_offers_sketch_but_not_shell(window, no_dialogs, slot_errors):
    part = shown_part(window)
    bore = next(face for face in part.faces() if face.geom_type.name == "CYLINDER")
    window.viewer.click([bore])
    assert action(window, "Skica na vybrané ploše").isEnabled()  # na tečné rovině
    assert action(window, "Díra na vybrané ploše").isEnabled()
    assert not action(window, "Skořepina – otevřít vybrané plochy").isEnabled()
    assert "díra na ploše" in window.statusBar().currentMessage()
    # Skořepina zakřivenou plochu otevřít neumí: česká hláška, model beze změny.
    before = len(window.session.document.features)
    window.add_from_selection("shell")
    assert no_dialogs == ["warning"]
    assert len(window.session.document.features) == before
    assert slot_errors == []


def test_selecting_feature_in_tree_highlights_its_edges(window):
    chamfer = next(i for i in range(window.tree.topLevelItemCount())
                   if "Sražení" in window.tree.topLevelItem(i).text(0))
    window.tree.setCurrentItem(window.tree.topLevelItem(chamfer))
    assert window.viewer.highlighted
    window.tree.setCurrentItem(None)
    assert window.viewer.highlighted == []


def test_context_menu_offers_selection_actions(window, monkeypatch):
    shown = []  # nabídka by v testu čekala na kliknutí – jen si zapamatujeme její položky
    monkeypatch.setattr(window, "_exec_menu", lambda menu, position: shown.append(
        [(item.text(), item.isEnabled()) for item in menu.actions() if item.text()]))
    window.viewer.context_menu_requested.emit(QPoint(10, 10))
    assert shown[-1][0] == ("Nic není vybrané – klikni na hranu nebo plochu", False)
    window.viewer.click([edge_at(shown_part(window), 82.5, 0, 0)])
    window.viewer.context_menu_requested.emit(QPoint(10, 10))
    items = dict(shown[-1])
    assert items["Zaoblit vybrané hrany"] and items["Srazit vybrané hrany"]
    assert not items["Skica na vybrané ploše"]
    action(window, "Zrušit výběr ve 3D").trigger()
    assert not action(window, "Zaoblit vybrané hrany").isEnabled()


def test_hole_from_clicked_face_and_size_change(empty_window):
    w = empty_window
    build_box(w)
    w.viewer.click([face_at(shown_part(w), 5, 5, 10)], point=(5, 5, 10))
    action(w, "Díra na vybrané ploše").trigger()
    assert selected_text(w) == "✓  Počet těles: 1 → 1. — Díra „Díra 1“ – M6 závit"
    size = form_field(w, "size")
    assert size.currentData() == "M6"
    size.setCurrentIndex(size.findData("M3"))  # menší závit → menší vrták Ø2,5
    hole = w.session.feature("hole1")
    assert hole["size"] == "M3" and hole["positions"] == [[5, 5]]
    drill = math.pi * 1.25 ** 2 * 6 + math.pi * 1.25 ** 2 * (1.25 / math.tan(math.radians(59))) / 3
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - drill)
    kind = form_field(w, "kind")
    kind.setCurrentIndex(kind.findData("countersink"))  # M3 zápustná, skrz? hloubka 6
    assert "zápustné" in selected_text(w)


def test_modeled_thread_checkbox(empty_window):
    w = empty_window
    build_box(w)
    w.viewer.click([face_at(shown_part(w), 5, 5, 10)], point=(5, 5, 10))
    action(w, "Díra na vybrané ploše").trigger()
    size = form_field(w, "size")
    size.setCurrentIndex(size.findData("M12"))  # velké stoupání = málo závitů = rychlý test
    before = w.session.properties.volume_mm3
    form_field(w, "modeled_thread").setChecked(True)
    hole = w.session.feature("hole1")
    assert hole["modeled_thread"] is True
    assert selected_text(w) == "✓  Počet těles: 1 → 1. — Díra „Díra 1“ – M12 závit (vymodelovaný)"
    assert w.session.result.ok
    assert w.session.properties.volume_mm3 < before  # drážka závitu ubrala materiál


def test_pattern_and_mirror_from_tree(empty_window):
    w = empty_window
    build_box(w)  # kvádr 40 × 30 × 10
    action(w, "Díra").trigger()
    positions = form_field(w, "positions")
    positions.setPlainText("-10; 5")
    positions.editingFinished.emit()
    one = 40 * 30 * 10 - w.session.properties.volume_mm3
    action(w, "Pole").trigger()  # vybraná je díra → pole ji rovnou opakuje
    assert selected_text(w) == "✓  Počet těles: 1 → 1. — Pole „Pole 1“ – v řadě, 3 ks"
    form = w.feature_editor.form
    assert form.widget("features").findChild(QtWidgets.QCheckBox, "feature_hole1").isChecked()
    assert form.is_shown("spacing") and not form.is_shown("axis")
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - 3 * one)

    kind = form_field(w, "kind")
    kind.setCurrentIndex(kind.findData("circular"))  # 3× dokola kolem osy Z
    assert form.is_shown("axis") and form.is_shown("center") and not form.is_shown("spacing")
    assert w.session.feature("pattern1")["kind"] == "circular"
    assert selected_text(w) == "✓  Počet těles: 1 → 1. — Pole „Pole 1“ – dokola, 3 ks"
    set_text(form_field(w, "center").findChild(QtWidgets.QLineEdit, "point_z"), "4")
    assert w.session.feature("pattern1")["center"] == [0, 0, 4]
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - 3 * one)

    action(w, "Zrcadlení").trigger()  # zrcadlí pole podle YZ
    assert w.session.feature("mirror1")["features"] == ["pattern1"]
    box = form_field(w, "features").findChild(QtWidgets.QCheckBox, "feature_pattern1")
    box.setChecked(False)  # nic nezaškrtnuto → zrcadlí se celý díl
    assert "features" not in w.session.feature("mirror1")
    plane = form_field(w, "plane")
    plane.setCurrentIndex(plane.findData("right"))
    assert selected_text(w) == "✓  Počet těles: 1 → 1. — Zrcadlení „Zrcadlení 1“ – celý díl"
    assert w.session.properties.volume_mm3 == pytest.approx(2 * (40 * 30 * 10 - 3 * one))


def test_pattern_needs_a_checked_feature(empty_window):
    w = empty_window
    build_box(w)
    action(w, "Pole").trigger()  # před ním je jen základní těleso → nic zaškrtnuté
    assert w.session.result.first_error.id == "pattern1"
    assert "vyber prvky" in w.session.result.first_error.message
    form = form_field(w, "features")
    form.findChild(QtWidgets.QCheckBox, "feature_extrude1").setChecked(True)
    form.findChild(QtWidgets.QCheckBox, "feature_extrude1").setChecked(False)
    assert "zaškrtni aspoň jeden prvek" in w.statusBar().currentMessage()


def test_sweep_form_path_and_profile(empty_window):
    w = empty_window
    action(w, "Tažení").trigger()  # nové tažení = trubkové koleno Ø30 × 2, R40
    form = w.feature_editor.form
    length = 2 * 60 + math.pi / 2 * 40
    assert w.session.properties.volume_mm3 == pytest.approx(math.pi * 56 * length)
    assert form.is_shown("diameter") and not form.is_shown("width")
    assert not form.is_shown("sketch")
    path = form_field(w, "path")
    assert path.toPlainText() == "0; 0; 0\n0; 0; 100\n100; 0; 100"
    path.setPlainText("0; 0; 0\n100; 0; 0\n100; 100; 0")
    path.editingFinished.emit()
    set_text(form_field(w, "bend_radius"), "")  # ostrý roh = pokos
    profile = form_field(w, "profile")
    profile.setCurrentIndex(profile.findData("rectangle"))  # jekl 40 × 20 × 2
    assert form.is_shown("width") and not form.is_shown("diameter")
    feature = w.session.feature("sweep1")
    assert feature["path"] == [[0, 0, 0], [100, 0, 0], [100, 100, 0]]
    assert "bend_radius" not in feature and feature["diameter"] == 30  # skryté zůstane
    assert w.session.properties.volume_mm3 == pytest.approx((40 * 20 - 36 * 16) * 200)
    assert selected_text(w) == ("✓  Počet těles: 0 → 1. — Tažení „Tažení 1“"
                                 " – jekl 40 × 20 × 2, trasa z 3 bodů")
    path.setPlainText("0; 0\n1; 1")  # bod bez z
    path.editingFinished.emit()
    assert "x; y; z" in w.statusBar().currentMessage()
    assert w.session.feature("sweep1")["path"][1] == [100, 0, 0]
    path.setPlainText("0; 0; 0\n100; 0; 0")
    path.editingFinished.emit()
    assert w.session.properties.volume_mm3 == pytest.approx((40 * 20 - 36 * 16) * 100)
    profile.setCurrentIndex(profile.findData("sketch"))  # skica tu žádná není
    assert "není žádná skica" in w.statusBar().currentMessage()
    assert w.session.feature("sweep1")["profile"] == "rectangle"


def test_standard_part_form_switches_sizes_by_kind(empty_window):
    from skodacad.standards import BEARING, SOCKET_HEAD

    w = empty_window
    action(w, "Normalizovaný díl").trigger()  # bez dílu: samotný imbus M6 × 20
    form = w.feature_editor.form
    dk, k, s, t = SOCKET_HEAD["M6"]
    hexagon = math.sqrt(3) / 2
    assert w.session.properties.volume_mm3 == pytest.approx(
        math.pi * dk**2 / 4 * k - hexagon * s**2 * t + math.pi * 9 * 20)
    assert form.is_shown("length") and not form.is_shown("clearance")
    kind = form_field(w, "kind")
    kind.setCurrentIndex(kind.findData("bearing"))  # jiný druh → jiný seznam velikostí
    assert not form.is_shown("length")
    assert w.session.feature("standard1")["size"] == "623"
    size = form_field(w, "size")
    size.setCurrentIndex(size.findData("608"))
    d, big, width = BEARING["608"]
    assert w.session.properties.volume_mm3 == pytest.approx(
        math.pi / 4 * (big**2 - d**2) * width)
    assert selected_text(w) == ("✓  Počet těles: 0 → 1. — Normalizovaný díl „Normalizovaný díl 1“"
                                " – ložisko 608 (8 × 22 × 7)")


def test_nut_pocket_from_form(empty_window):
    from skodacad.standards import NUT

    w = empty_window
    build_box(w)  # kvádr 40 × 30 × 10
    action(w, "Normalizovaný díl").trigger()  # na horní ploše dílu
    assert w.session.feature("standard1")["plane"] == "top"
    form = w.feature_editor.form
    kind = form_field(w, "kind")
    kind.setCurrentIndex(kind.findData("nut"))
    operation = form_field(w, "operation")
    operation.setCurrentIndex(operation.findData("cut"))
    assert "otoč do materiálu" in w.session.result.first_error.message
    direction = form_field(w, "direction")
    direction.setCurrentIndex(direction.findData("reverse"))
    assert form.is_shown("clearance")
    set_text(form_field(w, "clearance"), "0,2")
    s, m = NUT["M6"]
    assert w.session.properties.volume_mm3 == pytest.approx(
        40 * 30 * 10 - math.sqrt(3) / 2 * (s + 0.4)**2 * (m + 0.2))
    assert selected_text(w) == ("✓  Počet těles: 1 → 1. — Normalizovaný díl „Normalizovaný díl 1“"
                                 " – ISO 4032 M6 (kapsa)")


def test_loft_form_picks_sketches_in_order(empty_window):
    w = empty_window
    action(w, "Skica").trigger()  # obdélník 40 × 30 v XY
    action(w, "Skica").trigger()
    set_text(form_field(w, "offset"), "30")
    action(w, "Přechod").trigger()  # spojí dvě poslední skici
    form = form_field(w, "sketches")
    first = form.findChild(QtWidgets.QCheckBox, "sketch_sketch1")
    assert first.isChecked() and form.findChild(QtWidgets.QCheckBox, "sketch_sketch2").isChecked()
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 30)
    set_text(form_field(w, "wall"), "2")
    assert w.session.properties.volume_mm3 == pytest.approx((40 * 30 - 36 * 26) * 30, rel=1e-6)
    assert selected_text(w) == ("✓  Počet těles: 0 → 1. — Přechod „Přechod 1“"
                                 " – mezi 2 skicami, dutý 2 mm, kolmo ke stěně")
    first.setChecked(False)
    assert "zaškrtni aspoň 2 skici" in w.statusBar().currentMessage()
    assert w.session.feature("loft1")["sketches"] == ["sketch1", "sketch2"]


def test_loft_wall_mode_form_history_save_and_reopen(empty_window, examples_dir, tmp_path):
    w = empty_window
    assert w.open_model(examples_dir / "loft_stena.json", template=True)
    w.tree.setCurrentItem(w.tree.topLevelItem(2))
    combo = form_field(w, "wall_mode")
    assert combo.count() == 2 and combo.currentData() == "normal"
    normal_volume = w.session.result.part.volume
    combo.setCurrentIndex(combo.findData("sections"))
    assert w.session.result.part.volume == pytest.approx(32232.740625831255, abs=2e-5)
    assert "v rovinách skic" in selected_text(w)
    w.undo_action.trigger()
    assert form_field(w, "wall_mode").currentData() == "normal"
    assert w.session.result.part.volume == pytest.approx(normal_volume, abs=2e-5)
    w.redo_action.trigger()
    assert form_field(w, "wall_mode").currentData() == "sections"
    path = tmp_path / "loft.json"
    w.session.save(path)
    assert w.open_model(path)
    assert w.session.document.to_dict()["version"] == 33
    assert w.session.feature("prechod")["wall_mode"] == "sections"


def test_legacy_loft_form_preserves_missing_mode_and_recovers_from_normal_error(
        empty_window, examples_dir):
    w = empty_window
    assert w.open_model(examples_dir / "vysypka.json", template=True)
    w.tree.setCurrentItem(w.tree.topLevelItem(2))
    combo = form_field(w, "wall_mode")
    assert combo.count() == 3 and combo.currentData() is None
    assert "starší model" in combo.currentText()
    volume = w.session.result.part.volume
    set_text(form_field(w, "name"), "Přejmenovaná výsypka")
    assert "wall_mode" not in w.session.feature("vysypka")
    assert w.session.document.to_dict()["version"] == 24
    combo.setCurrentIndex(combo.findData("normal"))
    assert not w.session.result.ok and "V rovinách skic" in w.error_label.text()
    combo.setCurrentIndex(combo.findData("sections"))
    assert w.session.result.ok
    assert w.session.result.part.volume == pytest.approx(volume, abs=2e-5)
    w.undo_action.trigger()
    assert not w.session.result.ok
    w.undo_action.trigger()
    assert w.session.result.ok and "wall_mode" not in w.session.feature("vysypka")
    assert w.session.result.part.volume == pytest.approx(volume, abs=2e-5)


def test_sketch_on_inclined_face_from_click(empty_window):
    w = empty_window
    build_box(w)  # kvádr 40 × 30 × 10
    w.session.add_feature("chamfer", values={"edges": {"between": ["top", "front"]},
                                             "distance": 5})
    w._reload_all()
    slope = face_at(shown_part(w), 0, -12.5, 7.5)  # šikmá plocha sražení
    w.viewer.click([slope], point=(4, -12.5, 7.5))
    assert action(w, "Skica na vybrané ploše").isEnabled()
    action(w, "Skica na vybrané ploše").trigger()
    sketch = w.session.feature("sketch2")
    assert sketch["plane"]["at"] == pytest.approx([4, -12.5, 7.5])
    assert sketch["elements"][0]["center"] == [0.0, 0.0]  # počátek skici = místo kliknutí
    plane = form_field(w, "plane")
    assert plane.currentText() == "plocha vybraná ve 3D (u bodu 4; -12.5; 7.5)"
    shapes = form_field(w, "elements")
    set_text(shapes._form.widget("diameter"), "4")  # jiné pole – rovina musí zůstat
    assert w.session.feature("sketch2")["plane"]["at"] == pytest.approx([4, -12.5, 7.5])
    w.session.add_feature("extrude", values={"operation": "cut", "distance": 2})
    chamfered = 40 * 30 * 10 - 0.5 * 5 * 5 * 40
    assert w.session.properties.volume_mm3 == pytest.approx(chamfered - math.pi * 4 * 2)


def test_hole_on_shaft_surface_from_click(empty_window):
    w = empty_window
    session = w.session
    session.add_feature("sketch", values={"plane": "YZ", "elements": [
        {"shape": "circle", "diameter": 20}]})
    session.add_feature("extrude", values={"distance": 80, "direction": "both"})
    w._reload_all()
    shaft = face_at(shown_part(w), 5, 0, 10)
    assert shaft.geom_type.name == "CYLINDER"
    w.viewer.click([shaft], point=(5, 0, 10))
    action(w, "Díra na vybrané ploše").trigger()
    hole = session.feature("hole1")
    assert hole["plane"] == {"at": [5.0, 0.0, 10.0], "normal": [0.0, 0.0, 1.0]}
    assert hole["positions"] == [[0.0, 0.0]] and session.result.ok
    assert session.properties.volume_mm3 < math.pi * 100 * 80  # díra do hřídele z boku
    w.viewer.click([face_at(shown_part(w), -20, 0, 10)], point=(-20, 0, 10))
    assert w.add_to_feature_action.text().startswith("Přidat díru v místě kliknutí do:")
    w.add_to_feature_action.trigger()  # na horní přímce hřídele = stejná tečná rovina → další díra
    assert session.feature("hole1")["positions"] == [[0.0, 0.0], [-25.0, 0.0]]
    w.viewer.click([face_at(shown_part(w), 0, -10, 0)], point=(0, -10, 0))
    w.add_to_feature_action.trigger()  # na boku hřídele je jiná tečná rovina → jen hláška
    assert len(session.feature("hole1")["positions"]) == 2


# --- měření -----------------------------------------------------------------------------


def measure_rows(w):
    return [w.measure_list.item(i).text() for i in range(w.measure_list.count())]


def saved_rows(w):
    return [w.saved_list.item(i).text() for i in range(w.saved_list.count())]


def test_measuring_on_click_and_saving_into_the_model(window, no_dialogs, slot_errors,
                                                      monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    w = window
    assert measure_rows(w) == [] and "Klikni ve 3D" in w.measure_hint.text()
    assert not w.save_measurement_action.isEnabled()
    top = face_at(shown_part(w), 60, 0, 18)
    w.viewer.click([top], point=(60, 0, 18))
    assert measure_rows(w)[0] == "Tloušťka stěny: 18.00 mm"  # deska příruby t = 18
    [(start, end, label)] = w.viewer.measurement  # čára od kliknutí skrz desku
    assert start == pytest.approx((60, 0, 18)) and end == pytest.approx((60, 0, 0))
    assert label == "18.00 mm"
    assert w.save_measurement_action.text() == \
        "Uložit měření do modelu: Tloušťka stěny: 18.00 mm"
    w.save_measurement_action.trigger()
    assert saved_rows(w) == ["Tloušťka stěny: 18.00 mm"]
    assert w.session.document.measurements[0]["kind"] == "thickness"
    assert w.viewer.measurement  # uložené měření je vybrané a jeho čára vidět
    edit(w, "t", "20")
    assert saved_rows(w) == ["Tloušťka stěny: 20.00 mm"]  # přepočítalo se s dílem

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Stěna příruby", True))
    w.saved_list.setCurrentRow(0)
    action(w, "Přejmenovat měření…").trigger()
    assert saved_rows(w) == ["Stěna příruby: 20.00 mm"]
    w.saved_list.setCurrentRow(0)
    action(w, "Smazat měření").trigger()
    assert saved_rows(w) == [] and w.viewer.measurement == []
    action(w, "Zpět").trigger()
    assert saved_rows(w) == ["Stěna příruby: 20.00 mm"]
    assert slot_errors == []


def test_two_holes_show_pitch_in_panel_and_status_bar(window, monkeypatch):
    w = window
    part = shown_part(w)
    pitch = 125 / 2 * math.sqrt(2)  # sousední díry na roztečné kružnici k = 125, n = 4
    corner = 125 / 2 / math.sqrt(2)  # díry jsou pootočené o 45°
    holes = [face_at(part, sx * corner + sx * 9, corner, 9) for sx in (1, -1)]
    assert all(h.geom_type.name == "CYLINDER" for h in holes)
    w.viewer.click(holes)
    assert measure_rows(w)[0] == f"Rozteč os: {number(pitch)} mm"
    assert f"Rozteč os: {number(pitch)} mm" in w.statusBar().currentMessage()
    shown = []
    monkeypatch.setattr(w, "_exec_menu", lambda menu, position: shown.append(
        [item.text() for item in menu.actions() if item.isEnabled()]))
    w.viewer.context_menu_requested.emit(QPoint(10, 10))
    assert f"Uložit měření do modelu: Rozteč os: {number(pitch)} mm" in shown[-1]
    w.measure_list.setCurrentRow(len(measure_rows(w)) - 1)  # nejkratší vzdálenost
    assert w.viewer.measurement[0][2] == f"{number(pitch - 18)} mm"  # mezi stěnami děr Ø18
    w.viewer.click(list(part.faces())[:3])
    assert measure_rows(w) == [] and "jednu nebo dvě" in w.measure_hint.text()


# --- mapa tloušťky stěny ------------------------------------------------------------------


def test_thickness_map_in_window(window, no_dialogs, slot_errors, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    w = window  # příruba: deska 18 mm s dírami
    assert w.viewer.thickness_map is None and not w.export_map_action.isEnabled()
    assert "Zapni mapu" in w.map_summary.text()
    action(w, "Mapa tloušťky stěny").trigger()
    nodes, triangles, colors, (point, label) = w.viewer.thickness_map
    assert nodes > 1000 and triangles > 1000 and len(colors) == nodes
    found = w.session.thickness_map
    assert label == f"min {number(found.minimum)} mm"
    assert "Nejčastější tloušťka: 18.00 mm" in w.map_summary.text()
    assert w.map_scale_label.text().endswith("18.00 mm a víc")
    # klik na mapu = přesná tloušťka v bodě i ve stavovém řádku
    w.viewer.click([face_at(shown_part(w), 60, 0, 18)], point=(60, 0, 18))
    assert "Tloušťka stěny: 18.00 mm" in w.statusBar().currentMessage()

    set_text(w.map_fields["limit"], "20")  # minimum nad tloušťkou desky → skoro vše pod ním
    assert w.session.document.thickness_map == {"limit": 20}
    assert "Pod minimem 20.00 mm" in w.map_summary.text()
    set_text(w.map_fields["step"], "nic")
    assert "c0392b" in w.map_fields["step"].styleSheet()  # neplatné číslo → červeně
    assert w.session.document.thickness_map == {"limit": 20}
    set_text(w.map_fields["step"], "8")
    assert w.session.thickness_map.step == 8 and w.map_fields["step"].styleSheet() == ""
    action(w, "Zpět").trigger()
    assert w.map_fields["step"].text() == "" and w.session.thickness_map.step != 8

    target = tmp_path / "mapa.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    action(w, "Export bodů mapy do CSV…").trigger()
    assert target.read_text(encoding="utf-8-sig").startswith("x [mm];y [mm];z [mm]")

    action(w, "Mapa tloušťky stěny").trigger()  # vypnout
    assert w.viewer.thickness_map is None and not w.session.map_visible
    edit(w, "t", "20")
    assert w.session.thickness_map is None  # vypnutá mapa se nepočítá
    assert slot_errors == []


# --- řez modelem ---------------------------------------------------------------------------


def test_section_in_window(window, no_dialogs, slot_errors, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    w = window  # příruba Ø165 × 18 s otvorem Ø62 a čtyřmi děrami Ø18
    full = w.session.result.part
    assert not w.flip_section_action.isEnabled() and "Zapni řez" in w.section_info.text()
    action(w, "Řez modelem").trigger()  # výchozí kolmo na Y uprostřed (středem otvoru)
    shown, _fit = w.viewer.parts[-1]
    assert shown is w.session.section.part and shown.volume == pytest.approx(full.volume / 2)
    assert len(w.viewer.accent) == 2  # dvě plochy řezu vedle otvoru
    area = 2 * (165 - 62) / 2 * 18 - 4 * 2  # bez sražení obvodu 2 a otvoru 1 mm (2 × 2 rohy)
    assert w.session.section.area == pytest.approx(area, rel=0.02)
    assert "Plocha řezu" in w.section_info.text()
    assert w.session.document.to_dict() == w.session.document.to_dict() and not \
        w.session.dirty  # řez model nemění

    set_text(w.section_field, "40")  # poloha číslem
    assert w.session.section_settings.position == 40
    w.section_slider.setValue(1000)  # posuvník na konec dílu → řez díl míjí
    assert w.session.section is None and "✕" in w.section_info.text()
    w.section_slider.setValue(500)
    assert w.session.section is not None
    action(w, "Otočit stranu řezu").trigger()
    assert w.session.section_settings.flipped
    w.section_combo.setCurrentIndex(w.section_combo.findData("Z"))
    w.section_combo.activated.emit(w.section_combo.currentIndex())
    assert w.session.section_settings.axis == "Z"
    assert w.session.section.area == pytest.approx(math.pi * (82.5**2 - 31**2)
                                                   - 4 * math.pi * 81, rel=1e-3)

    # řez rovnoběžně s plochou kliknutím (horní plocha → do hloubky)
    top = face_at(shown_part(w), 60, 0, 18)
    w.viewer.click([top], point=(60, 0, 18))
    action(w, "Řez rovnoběžně s vybranou plochou").trigger()
    assert w.session.section_settings.axis is None
    assert w.section_combo.currentData() == "face"

    target = tmp_path / "rez.dxf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    action(w, "Export řezu do DXF/SVG…").trigger()
    assert target.exists() and target.stat().st_size > 0

    # mapa tloušťky v řezu: kreslí se jen trojúhelníky zbylé poloviny
    action(w, "Mapa tloušťky stěny").trigger()
    nodes, triangles, colors, marker = w.viewer.thickness_map
    assert 0 < triangles < len(w.session.thickness_map.triangles)
    assert len(colors) == nodes > len(w.session.thickness_map.nodes)  # uzly na řezu navíc
    assert w.viewer.map_fill == w.session.section.faces  # plochy řezu vyplněné
    action(w, "Mapa tloušťky stěny").trigger()

    action(w, "Řez modelem").trigger()  # vypnout → zase celý díl
    assert w.viewer.parts[-1][0] is w.session.result.part and w.session.section is None
    assert slot_errors == []


# --- AI asistent -----------------------------------------------------------------------


def wait_for_assistant(window, timeout=30.0):
    import time

    from PySide6.QtTest import QTest

    end = time.monotonic() + timeout
    while window.assistant_panel.busy and time.monotonic() < end:
        QTest.qWait(20)
    assert not window.assistant_panel.busy, "asistent nedoběhl"


def test_assistant_panel_edits_model_in_one_undo_step(window, slot_errors):
    from skodacad.assistant import offline_client

    requests = []
    turns = [
        ([{"type": "text", "text": "Zvětším přírubu."},
          {"type": "tool_use", "id": "t1", "name": "set_parameters",
           "input": {"values": {"D": 200}}}], "tool_use"),
        ([{"type": "tool_use", "id": "t2", "name": "view_part", "input": {"view": "iso"}}],
         "tool_use"),
        ([{"type": "text", "text": "Hotovo, D = 200 mm."}], "end_turn"),
    ]
    panel = window.assistant_panel
    panel.client_factory = lambda settings: offline_client(turns, requests)
    action(window, "AI asistent").trigger()
    panel.prompt.setPlainText("zvětši D na 200")
    action(window, "Odeslat").trigger()
    assert panel.busy  # během práce AI jsou ruční úpravy zamčené
    assert not window.model_dock.isEnabled() and not window.undo_action.isEnabled()
    assert not action(window, "Smazat prvek").isEnabled()
    wait_for_assistant(window)

    assert window.session.document.parameters["D"] == 200
    assert window._param_fields["D"].text() == "200"  # okno ukazuje nový stav
    text = panel.history_text()
    assert "Ty: zvětši D na 200" in text
    assert "→ Nastavuji parametry: D = 200" in text and "Hotovo, D = 200 mm." in text
    assert window.viewer.views[-1] == "iso"  # AI se na díl podívala izometricky
    image = requests[2]["body"]["messages"][-1]["content"][0]["content"][0]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/png"
    assert "Kč" in panel.status.text() and panel.prompt.toPlainText() == ""
    assert window.model_dock.isEnabled() and window.undo_action.isEnabled()

    action(window, "Zpět").trigger()  # celá odpověď AI = jeden krok Zpět
    assert window.session.document.parameters["D"] == 165
    assert slot_errors == []


def test_assistant_without_key_explains_and_new_model_resets(window, slot_errors,
                                                               monkeypatch, examples_dir):
    from skodacad.assistant import offline_client

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    panel = window.assistant_panel
    assert "chybí API klíč" in panel.status.text()
    panel.prompt.setPlainText("zvětši D")
    panel.send()
    assert not panel.busy and "Chybí API klíč" in panel.history_text()

    panel.client_factory = lambda settings: offline_client(
        [([{"type": "text", "text": "Příruba má 4 díry."}], "end_turn")])
    panel.prompt.setPlainText("kolik má děr?")
    panel.send()
    wait_for_assistant(window)
    assert panel.assistant.messages
    window.session.dirty = False
    window.open_model(examples_dir / "krabicka.json", template=True)
    assert panel.assistant.messages == []  # jiný model = nová konverzace
    assert "nová konverzace" in panel.history_text()
    action(window, "Nová konverzace").trigger()
    assert panel.history_text() == ""
    assert slot_errors == []


def test_assistant_settings_dialog_saves_key_and_model(window, monkeypatch, tmp_path,
                                                        slot_errors):
    import json

    from PySide6.QtWidgets import QDialog, QLineEdit

    def fill(self, dialog):
        assert dialog.key_edit.echoMode() == QLineEdit.EchoMode.Password  # klíč není vidět
        dialog.key_edit.setText(" sk-ant-test ")
        dialog.model_combo.setCurrentIndex(dialog.model_combo.findData("claude-sonnet-5-5"))
        dialog.effort_combo.setCurrentIndex(dialog.effort_combo.findData("medium"))
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", fill)
    action(window, "Nastavení AI…").trigger()
    saved = json.loads((tmp_path / "nastaveni.json").read_text(encoding="utf-8"))["ai"]
    assert saved == {"api_key": "sk-ant-test", "model": "claude-sonnet-5-5",
                     "effort": "medium"}
    status = window.assistant_panel.status.text()
    assert "Sonnet 5.5" in status and "vyváženě" in status and "chybí" not in status
    assert slot_errors == []


# --- panel NDT ---------------------------------------------------------------------------


@pytest.fixture
def ndt_window(app, examples_dir, tmp_path, no_dialogs, slot_errors):
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert w.open_model(examples_dir / "ndt" / "deska.json", template=True)
    yield w
    w.session.dirty = False
    w.close()


def ndt_texts(w):
    return [w.ndt_panel.studies.item(i).text() for i in range(w.ndt_panel.studies.count())]


def test_ndt_panel_shows_sample_study_and_highlights_its_target(ndt_window, slot_errors):
    w = ndt_window
    assert ndt_texts(w) == ["✓ UT desky shora (UT) – platná", "✓ MT horní plochy (MT) – platná"]
    assert w.ndt_panel.findChildren(QtWidgets.QLabel)[0] is w.ndt_panel.warning  # nahoře
    assert "nenahrazují kvalifikovaný NDT postup" in w.ndt_panel.warning.text()  # UT studie
    w.ndt_panel.studies.setCurrentRow(0)
    assert len(w.viewer.highlighted) == 1  # horní plocha desky
    assert "kontrolovaná oblast: 1 plocha" in w.ndt_panel.details.text()
    assert "Neověřeno." in w.ndt_panel.details.text()
    assert not w.ndt_panel.confirm_action.isEnabled()  # platná – není co potvrzovat
    first = w.tree.topLevelItem(0)
    w.tree.setCurrentItem(first)  # prvek ve stromu → zvýraznit prvek, ne oblast studie
    assert w.ndt_panel.current_id() is None
    action(w, "Panel NDT studií").trigger()
    assert slot_errors == []


def test_ndt_panel_stale_confirm_and_verify(ndt_window, slot_errors, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    w = ndt_window
    w.ndt_panel.studies.setCurrentRow(0)
    edit(w, "t", "30")
    assert ndt_texts(w)[0] == "⚠ UT desky shora (UT) – zastaralá"
    assert "posunula o 10.00 mm" in w.ndt_panel.details.text()
    assert not w.ndt_panel.verify_action.isEnabled()
    w.ndt_panel.confirm_action.trigger()
    assert ndt_texts(w)[0] == "✓ UT desky shora (UT) – platná"
    assert ndt_texts(w)[1] == "⚠ MT horní plochy (MT) – zastaralá"  # potvrzuje se po jedné
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("J. N.", True))
    w.ndt_panel.verify_action.trigger()
    assert "Ověřil(a) J. N." in w.ndt_panel.details.text()
    assert w.ndt_panel.unverify_action.isEnabled()
    w.ndt_panel.unverify_action.trigger()
    assert "Neověřeno." in w.ndt_panel.details.text()
    action(w, "Zpět").trigger()
    assert "Ověřil(a) J. N." in w.ndt_panel.details.text()
    assert slot_errors == []


def test_ndt_panel_new_study_from_click_and_edits(ndt_window, slot_errors, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    w = ndt_window
    part = w.session.result.part
    w.viewer.click([face_at(part, 0, 0, 0)], (0, 0, 0))  # spodní plocha
    w.ndt_panel.method_combo.setCurrentIndex(w.ndt_panel.method_combo.findData("MT"))
    w.ndt_panel.new_action.trigger()
    assert ndt_texts(w)[2] == "✓ MT studie 3 (MT) – platná"  # deska má UT a MT studii
    assert w.ndt_panel.current_id() == "s3"
    w.ndt_panel.rename_action.trigger()  # dialog zrušen (no_dialogs) – nic se nezmění
    assert ndt_texts(w)[2].startswith("✓ MT studie 3")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("MT zespodu", True))
    w.ndt_panel.rename_action.trigger()
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("PT – kapilární", True))
    w.ndt_panel.method_action.trigger()
    assert ndt_texts(w)[2] == "✓ MT zespodu (PT) – platná"
    monkeypatch.setattr(QInputDialog, "getMultiLineText",
                        lambda *a, **k: ("Celá spodní plocha.", True))
    w.ndt_panel.note_action.trigger()
    assert "Poznámka: Celá spodní plocha." in w.ndt_panel.details.text()
    part = w.session.result.part
    w.viewer.click([face_at(part, 0, 0, 20), face_at(part, 0, 0, 0)], (0, 0, 20))
    assert w.ndt_panel.target_action.isEnabled()
    w.ndt_panel.target_action.trigger()
    assert "kontrolovaná oblast: 2 plochy" in w.ndt_panel.details.text()
    w.ndt_panel.duplicate_action.trigger()
    assert ndt_texts(w)[3] == "✓ MT zespodu (kopie) (PT) – platná"
    w.ndt_panel.delete_action.trigger()
    assert len(ndt_texts(w)) == 3
    action(w, "Zpět").trigger()
    assert len(ndt_texts(w)) == 4
    assert slot_errors == []


def test_ndt_new_study_without_selection_is_incomplete(ndt_window, slot_errors):
    w = ndt_window
    action(w, "Nová NDT studie z výběru").trigger()
    assert ndt_texts(w)[2] == "⚠ UT studie 3 (UT) – neúplná"
    assert "Chybí kontrolovaná oblast" in w.ndt_panel.details.text()
    w.viewer.click([edge_at(w.session.result.part, 0, -50, 20)])
    assert not w.ndt_panel.target_action.isEnabled()  # hrana není plocha
    assert slot_errors == []


def test_ndt_panel_is_locked_while_ai_works(ndt_window):
    w = ndt_window
    w.ndt_panel.studies.setCurrentRow(0)
    w.set_assistant_busy(True)
    w.ndt_panel.refresh()
    assert not w.ndt_dock.isEnabled()
    assert not any(a.isEnabled() for a in (w.ndt_panel.new_action, w.ndt_panel.rename_action,
                                           w.ndt_panel.delete_action))
    w.set_assistant_busy(False)
    assert w.ndt_dock.isEnabled() and w.ndt_panel.rename_action.isEnabled()


# --- sonda v panelu NDT (etapa 03) -----------------------------------------------------------


@pytest.fixture
def rib_window(app, examples_dir, tmp_path, no_dialogs, slot_errors):
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert w.open_model(examples_dir / "ndt" / "zebro.json", template=True)
    w.ndt_panel.studies.setCurrentRow(0)
    yield w
    w.session.dirty = False
    w.close()


def test_place_turn_and_remove_probe(rib_window, slot_errors):
    from PySide6.QtWidgets import QGroupBox

    from skodacad.ndt import UT_DISCLAIMER

    w = rib_window
    panel = w.ndt_panel
    assert panel.findChild(QGroupBox, "ndt_ut").title() == "Přístupnost UT sondy"
    assert panel.warning.text() == UT_DISCLAIMER  # povinné upozornění (04-zavazne-…)
    assert panel.warning.isVisibleTo(panel)
    assert "Úhlová sonda 40 × 20 × 25 mm" in panel.probe_label.text()
    assert "(výchozí)" in panel.probe_label.text()
    assert not panel.place_action.isEnabled()  # nic není vybráno
    w.viewer.click([face_at(w.session.result.part, 22, 0, 20)], (22, 0, 20))
    panel.angle.setValue(180)  # paprsek k žebru (−X)
    assert panel.place_action.isEnabled()
    panel.place_action.trigger()
    state, start, end, text, volume = w.viewer.probe
    assert state == "ok" and start == pytest.approx((22, 0, 20))
    assert end == pytest.approx((22 - 30, 0, 20))  # čára směru paprsku
    assert text == "přiloženo · volno 5.0 mm" and volume == pytest.approx(40 * 20 * 25)
    assert len(w.viewer.beam) == 3  # výstup -> odraz u dna (x=2, z=0) -> stěna žebra (x=5)
    assert w.viewer.beam[0] == pytest.approx((22, 0, 20))
    assert w.viewer.beam[1] == pytest.approx((2, 0, 0), abs=1e-4)
    assert "Přiloženo. Mezera pod sondou 0.00 mm, volno k překážkám 5.00 mm." in \
        panel.placement_label.text()
    assert "Dráha paprsku (úhel lomu 45.0°" in panel.placement_label.text()
    assert "půlkrok 20.00 mm, celý krok 40.00 mm" in panel.placement_label.text()
    panel.angle.setValue(0)  # otočit: zadní konec sondy zajede do žebra
    assert w.viewer.probe[0] == "collision"
    assert "Koliduje" in panel.placement_label.text()
    edit(w, "t", "25")  # silnější deska: sonda se přiloží znovu na posunutou plochu
    assert w.viewer.probe[1] == pytest.approx((22, 0, 25))
    panel.remove_probe_action.trigger()
    assert w.viewer.probe is None and w.viewer.beam == []
    assert w.session.ndt_placement_request is None
    assert slot_errors == []


def test_probe_dialog_stores_probe_in_study(rib_window, slot_errors, monkeypatch):
    from PySide6.QtWidgets import QDialog

    w = rib_window
    panel = w.ndt_panel
    panel.probe_action.trigger()  # no_dialogs: zrušeno → beze změny
    assert "device" not in w.session.ndt_study("s1")

    def accept(self, dialog):
        assert dialog.fields["beam_angle"].value() == 45
        assert dialog.bounces.value() == 1
        dialog.kind.setCurrentIndex(dialog.kind.findData("straight"))
        assert not dialog.fields["length"].isVisibleTo(dialog)  # délka jen u úhlové
        assert not dialog.fields["beam_angle"].isVisibleTo(dialog)  # úhel lomu jen u úhlové
        assert dialog.bounces.value() == 0  # u přímé sondy výchozí 0 odrazů
        dialog.fields["diameter"].setValue(12)
        dialog.fields["reserve"].setValue(3)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", accept)
    panel.probe_action.trigger()
    assert w.session.ndt_study("s1")["device"] == {"kind": "straight", "diameter": 12,
                                                   "height": 25, "bounces": 0, "max_gap": 0.5,
                                                   "reserve": 3}
    assert panel.probe_label.text().startswith("Přímá sonda Ø 12 × 25 mm; mezera nejvýš 0.50")
    action(w, "Zpět").trigger()
    assert "device" not in w.session.ndt_study("s1")
    assert slot_errors == []


def test_probe_dialog_profiles_origins_snell_and_my_probes(ndt_window, slot_errors,
                                                         monkeypatch):
    from PySide6.QtWidgets import QDialog, QInputDialog

    from skodacad.ndt.library import BUILTIN, PROBES, load_user_library, user_library_path

    w = ndt_window
    panel = w.ndt_panel
    panel.select("s1")
    seen = {}

    def choose_profile(self, dialog):
        assert dialog.profile.currentData() == ""  # výchozí sonda = vlastní, bez profilu
        assert dialog.values() == w.session.ndt_probe("s1").to_dict()  # OK beze změny
        dialog.profile.setCurrentIndex(dialog.profile.findData("builtin:uhlova-velka-70"))
        assert dialog.fields["length"].value() == 50 and dialog.fields["beam_angle"].value() == 70
        assert dialog.origins["front"].text() == "obecný profil"
        assert dialog.angle_material.currentData() == "ocel"
        dialog.fields["front"].setValue(15)  # ručně přepsaný výstupní bod
        assert dialog.origins["front"].text() == "zadáno ručně"
        dialog.measured["beam_angle"].setChecked(True)  # úhel změřený na bloku
        assert dialog.origins["beam_angle"].text() == ""  # „změřeno“ ukazuje zaškrtávátko
        dialog.frequency.setValue(4)
        dialog.source.setText("blok č. 1, 18. 10. 2026")
        seen["values"] = dialog.values()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", choose_profile)
    panel.probe_action.trigger()
    probe = w.session.ndt_probe("s1")
    assert probe.profile == PROBES["uhlova-velka-70"].name and probe.library == BUILTIN
    assert (probe.front, probe.origin("front"), probe.origin("beam_angle")) == (
        15, "entered", "measured")
    assert probe.frequency_mhz == 4 and probe.angle_material == "ocel"
    text = panel.probe_label.text()
    assert "Původ hodnot sondy: " in text and "obecný profil – " in text
    assert "změřeno – úhel lomu v materiálu" in text and "zadáno ručně – výstupní bod" in text

    def unchanged(self, dialog):
        assert dialog.profile.currentData() == "builtin:uhlova-velka-70"
        assert dialog.values() == probe.to_dict()  # nezměněné OK = totožný záznam
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", unchanged)
    steps = len(w.session._undo)
    panel.probe_action.trigger()
    assert len(w.session._undo) == steps  # bez kroku Zpět

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Moje velká 70°", True))

    def snell_and_save(self, dialog):
        dialog.snell_alpha.setText("abc")
        dialog.compute_snell()
        assert "čísly" in dialog.snell_result.text()
        dialog.snell_alpha.setText("60")
        dialog.snell_c1.setText("2730")
        dialog.snell_c2.setText("3240")
        dialog.compute_snell()
        assert "totální odraz" in dialog.snell_result.text()
        dialog.snell_alpha.setText("36,4")
        dialog.compute_snell()
        assert dialog.fields["beam_angle"].value() == pytest.approx(44.77, abs=0.01)
        assert dialog.angle_material.currentData() == ""  # β platí přímo v materiálu dílu
        assert dialog.origins["beam_angle"].text() == "zadáno ručně"
        dialog.save_button.click()
        assert dialog.profile.currentData() == "user:Moje velká 70°"
        assert "Uloženo do Mých sond" in dialog.error.text()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", snell_and_save)
    panel.probe_action.trigger()
    probe = w.session.ndt_probe("s1")
    assert probe.profile == "Moje velká 70°" and "Snellův zákon: α = 36.4°" in probe.angle_note
    mine = load_user_library(user_library_path(w.user_dir))
    assert mine.probes["Moje velká 70°"].beam_angle == pytest.approx(44.77, abs=0.01)
    assert slot_errors == []


def test_panel_ut_material_angle_warning_and_transfer(ndt_window, slot_errors):
    from skodacad.ndt.library import MATERIALS, PROBES

    w = ndt_window
    session, panel = w.session, w.ndt_panel
    panel.select("s1")
    session.set_ndt_device("s1", PROBES["uhlova-standardni-70"].probe)
    w._refresh_all()
    assert panel.ut_material.currentData() == "" and panel.ut_material.isEnabled()
    assert not panel.angle_check_label.isVisibleTo(panel)  # díl i úhel v oceli
    assert not panel.transfer_action.isEnabled()
    session.set_info(material="hliník")
    w._refresh_all()
    assert "materiál pro UT není zvolený" in panel.angle_check_label.text()
    assert panel.part_material_action.isEnabled()
    assert panel.part_material_action.text() == "Použít materiál dílu (hliník)"
    panel.part_material_action.trigger()
    assert session.ndt_ut_material("s1") == MATERIALS["hlinik"]
    assert panel.ut_material.currentData() == "builtin:hlinik"
    assert "hliník – podélná 6320 m/s, příčná 3130 m/s" in panel.material_label.text()
    assert "v něm je asi 65.2°" in panel.angle_check_label.text()
    assert panel.transfer_action.isEnabled()
    panel.transfer_action.trigger()
    assert session.ndt_probe("s1").beam_angle == 65.2
    assert not panel.angle_check_label.isVisibleTo(panel) and not panel.transfer_action.isEnabled()
    assert "přepočteno z 70°" in panel.probe_label.text()
    action(w, "Zpět").trigger()
    assert session.ndt_probe("s1").beam_angle == 70
    panel.ut_material.setCurrentIndex(panel.ut_material.findData("builtin:med"))
    assert session.ndt_ut_material("s1") == MATERIALS["med"]
    assert "asi 41.0°" in panel.angle_check_label.text()
    panel.ut_material.setCurrentIndex(panel.ut_material.findData(""))
    assert session.ndt_ut_material("s1") is None
    assert slot_errors == []


def test_probe_tools_only_for_ut_and_bad_placement_message(rib_window, slot_errors):
    from skodacad.ndt import PT_DISCLAIMER, RT_DISCLAIMER, UT_DISCLAIMER

    w = rib_window
    panel = w.ndt_panel
    w.viewer.click([edge_at(w.session.result.part, 0, -50, 80)])
    assert not panel.place_action.isEnabled()  # hrana, ne plocha
    w.session.set_ndt_method("s1", "PT")
    w._refresh_all()
    assert panel.probe_label.text() == "Sonda je zatím jen pro UT studie."
    assert not panel.probe_box.isVisibleTo(panel) and panel.pt_box.isVisibleTo(panel)
    assert panel.warning.text() == PT_DISCLAIMER  # PT: povinné upozornění PT (20-vymezeni-pt)
    panel.studies.setCurrentRow(-1)  # bez výběru podle metody nové studie (UT)
    assert panel.warning.text() == UT_DISCLAIMER
    panel.method_combo.setCurrentIndex(panel.method_combo.findData("RT"))
    assert panel.warning.text() == RT_DISCLAIMER  # RT: povinné upozornění RT (24-vymezeni-rt)
    assert not panel.probe_action.isEnabled()
    assert slot_errors == []


def test_ndt_probe_interactive_drag_step_and_scan(rib_window, slot_errors):
    w = rib_window
    panel = w.ndt_panel
    top = face_at(w.session.result.part, 22, 0, 20)

    # režim „Jezdit sondou myší“ přiloží a plynule posouvá sondu po ploše
    assert panel.drag_probe_action.isEnabled()
    assert not panel.step_forward_action.isEnabled()
    assert not panel.scan_action.isEnabled()
    panel.angle.setValue(180)
    panel.drag_probe_action.trigger()
    assert w.viewer.probe_drag_enabled
    w.viewer.drag_probe([top], (22, 0, 20))
    assert w.viewer.probe[0] == "ok" and w.viewer.probe[1] == pytest.approx((22, 0, 20))
    w.viewer.drag_probe([top], (19, 0, 20))
    assert w.viewer.probe[1] == pytest.approx((19, 0, 20))
    assert "volno k překážkám 2.00 mm" in panel.placement_label.text()

    # krokový posun ◀ / ▶ a otáčení kolečkem
    panel.step_mm.setValue(3.0)
    panel.step_forward_action.trigger()  # +3 mm k žebru (−X) → x = 16 → kolize
    assert w.viewer.probe[0] == "collision" and w.viewer.probe[1] == pytest.approx((16, 0, 20))
    panel.step_back_action.trigger()
    panel.step_back_action.trigger()  # −6 mm od žebra (+X) → x = 22
    assert w.viewer.probe[0] == "ok" and w.viewer.probe[1] == pytest.approx((22, 0, 20))
    w.viewer.rotate_probe(-15)
    assert panel.angle.value() == 165
    w.viewer.rotate_probe(15)
    assert panel.angle.value() == -180

    # projetí čáry a posuvník polohy po čáře
    panel.scan_length.setValue(10)
    panel.scan_action.trigger()
    assert panel.scan_slider.isEnabled() and panel.scan_slider.maximum() == 10
    assert panel.scan_label.isVisibleTo(panel)
    assert "Čára (0 mm): Volně: 0–5 mm. První potíž po 6 mm: Koliduje." in panel.scan_label.text()
    panel.scan_slider.setValue(6)
    assert w.viewer.probe[0] == "collision" and w.viewer.probe[1] == pytest.approx((16, 0, 20))
    assert "Čára (6 mm):" in panel.scan_label.text()
    assert slot_errors == []


# --- macOS: souřadnice myši -------------------------------------------------------------------


def test_pixel_ratio_measured_on_mac_only():
    from skodacad.gui.viewer import pixel_ratio

    assert pixel_ratio("win32", 1204, 803, 1.5) == 1.5  # Windows 150 %: jako dřív
    assert pixel_ratio("linux", 600, 600, 1.0) == 1.0
    assert pixel_ratio("darwin", 1600, 800, 2.0) == 2.0  # Retina, OCCT počítá v pixelech
    assert pixel_ratio("darwin", 800, 800, 2.0) == 1.0  # OCCT v bodech – nenásobit
    assert pixel_ratio("darwin", 0, 800, 2.0) == 2.0  # okno OCCT ještě nezná velikost


# --- návrh poloh sondy (etapa 09) ------------------------------------------------------------


def test_access_panel_runs_shows_applies_and_draws_maps(rib_window, slot_errors, tmp_path,
                                                        monkeypatch):
    from skodacad.ndt.access import ORDER_NOTE

    w = rib_window
    panel = w.ndt_panel
    session = w.session
    assert panel.access_box.isVisibleTo(panel) and panel.access_box.title() == \
        "Návrh poloh sondy"
    top = face_at(session.result.part, 50, 0, 20)
    w.viewer.click([top], (50, 0, 20))
    panel.access_faces.setCurrentIndex(panel.access_faces.findData("picked"))
    panel.access_directions.setCurrentIndex(panel.access_directions.findData(90.0))
    panel.access_bounces.setCurrentIndex(panel.access_bounces.findData("0"))
    panel.access_step.setValue(40)
    panel.access_angles.setChecked(True)
    panel.refresh_actions()
    assert "Odhad: 1 plocha" in panel.access_estimate.text()
    assert panel.access_action.isEnabled() and not panel.access_stop_action.isEnabled()
    panel.access_action.trigger()
    result = session.ndt_access
    assert result is not None and not slot_errors
    assert panel.access_table.rowCount() == min(10, len(result.variants)) > 0
    assert panel.access_table.item(0, 0).text() == "#1"
    assert "Kombinace" in panel.access_combination.text()
    assert ORDER_NOTE in " ".join(label.text() for label in panel.access_box.findChildren(
        QtWidgets.QLabel))
    # mapa cíle = sjednocení kombinace, kontaktní plochy = body, nic = nic
    assert w.viewer.coverage_map is not None and w.viewer.points is None
    panel.access_map.setCurrentIndex(panel.access_map.findData("contact"))
    assert w.viewer.points is not None and len(w.viewer.points[0]) > 0
    assert "sonda se nevejde" in panel.access_legend.text()
    panel.access_map.setCurrentIndex(panel.access_map.findData("none"))
    assert w.viewer.points is None and w.viewer.coverage_map is None
    # Ukázat = jen pohled, Použít = jeden krok Zpět
    rank = next(i for i, r in enumerate(result.variants)
                if r.variant.beta == 60 and r.best_reference is not None)
    panel.access_table.selectRow(rank)
    assert panel.access_show_action.isEnabled() and panel.access_apply_action.isEnabled()
    panel.access_show_action.trigger()
    assert w.viewer.probe is not None and not session.dirty
    assert session.ndt_probe_preview.beam_angle == 60
    panel.access_apply_action.trigger()
    assert session.dirty and session.ndt_probe("s1").beam_angle == 60
    assert session.ndt_access is result and panel.access_table.rowCount() > 0
    w.undo_action.trigger()
    assert session.ndt_probe("s1").beam_angle == 45
    path = tmp_path / "polohy.csv"
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a: (str(path), "CSV"))
    panel.access_export_action.trigger()
    assert path.exists() and not slot_errors


def test_access_panel_is_locked_while_ai_works(rib_window):
    w = rib_window
    panel = w.ndt_panel
    w.set_assistant_busy(True)
    panel.refresh()
    assert not any(a.isEnabled() for a in (panel.access_action, panel.access_show_action,
                                           panel.access_apply_action,
                                           panel.access_export_action))
    assert not panel.access_step.isEnabled()
    w.set_assistant_busy(False)
    panel.refresh()
    assert panel.access_action.isEnabled() and panel.access_step.isEnabled()


def test_plan_panel_builds_plays_edits_zones_and_exports(rib_window, no_dialogs, slot_errors,
                                                         tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from skodacad.ndt.plan import PLAN_NOTE, STEP_COLORS

    w = rib_window
    panel = w.ndt_panel
    session = w.session
    assert panel.plan_box.isVisibleTo(panel) and panel.plan_box.title() == "Plán dráhy sondy"
    top = face_at(session.result.part, 50, 0, 20)
    w.viewer.click([top], (50, 0, 20))
    panel.angle.setValue(180)
    panel.place_action.trigger()
    panel.plan_step.setValue(20)
    panel.refresh_actions()
    assert "Odhad: 1 průchod" in panel.plan_estimate.text() and panel.plan_action.isEnabled()
    panel.plan_action.trigger()
    result = session.ndt_plan_result
    assert result is not None and result.coverage is not None and session.dirty
    assert "Plán platí" in panel.plan_state.text() and not slot_errors
    assert panel.plan_segments.rowCount() == result.plan.segment_count
    assert "Geometricky pokryto" in panel.plan_summary.text()
    assert PLAN_NOTE in " ".join(label.text() for label in panel.plan_box.findChildren(
        QtWidgets.QLabel))
    lines, start, zones = w.viewer.plan
    assert lines[STEP_COLORS["scan"]] and start == result.check.steps[0].start and not zones
    full = w.viewer.coverage_map  # pokrytí plánu ve 3D
    assert full is not None
    # přehrávání: sonda na první poloze, mapa jen to, co do té doby paprsek zasáhl
    panel.plan_slider.setValue(0)
    assert w.viewer.probe is not None
    assert w.viewer.probe[1] == pytest.approx(result.check.positions[0].point, abs=1e-6)
    green = (0.15, 0.70, 0.25)
    assert w.viewer.coverage_map[2].count(green) <= full[2].count(green)
    assert "Poloha 1 z" in panel.plan_position.text()
    panel.plan_next_action.trigger()
    assert panel.plan_slider.value() == 1
    panel.plan_play_action.trigger()
    for _ in range(len(result.check.positions) + 2):
        panel._play_tick()
    assert not panel.plan_play_action.isChecked()
    assert panel.plan_slider.value() == panel.plan_slider.maximum()
    # úpravy jsou kroky Zpět; plán se po nich znovu ověří
    panel.plan_segments.selectRow(0)
    panel.plan_reverse_action.trigger()
    assert session.ndt_plan("s1").edited and "ručně upravený" in panel.plan_state.text()
    w.undo_action.trigger()
    assert not session.ndt_plan("s1").edited
    first = session.ndt_plan("s1").passes[0].segments[0]
    monkeypatch.setattr(QtWidgets.QInputDialog, "getText", lambda *a, **k: (
        f"{first.start[0]:g}; {first.start[1]:g}; 20 → 40; {first.start[1]:g}; 20", True))
    panel.plan_segments.selectRow(0)
    panel.plan_edit_action.trigger()
    assert session.ndt_plan("s1").passes[0].segments[0].end == (40.0, first.start[1], 20.0)
    # zakázaná zóna přes úsek: plán neplatí, zóna je ve 3D
    panel.plan_zones_action.trigger()
    assert "ZoneDialog" in no_dialogs  # zrušený dialog nic nemění
    zone = {"name": "štítek", "min": [43, first.start[1] - 1, 20],
            "max": [47, first.start[1] + 1, 23]}

    def accept(self, dialog):
        dialog._add_row(zone)
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", accept)
    panel.plan_zones_action.trigger()
    assert session.ndt_zones("s1")[0].to_dict() == zone
    assert "neplatí" in panel.plan_state.text() and len(w.viewer.plan[2]) == 1
    path = tmp_path / "plan.csv"
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", lambda *a: (str(path), "CSV"))
    panel.plan_export_action.trigger()
    assert path.exists()
    panel.plan_delete_action.trigger()
    assert session.ndt_plan("s1") is None and panel.plan_segments.rowCount() == 0
    assert not slot_errors


def test_plan_panel_is_locked_while_ai_works(rib_window):
    w = rib_window
    panel = w.ndt_panel
    w.set_assistant_busy(True)
    panel.refresh()
    assert not any(a.isEnabled() for a in panel._plan_actions())
    assert not panel.plan_step.isEnabled()
    w.set_assistant_busy(False)
    panel.refresh()
    assert panel.plan_step.isEnabled() and panel.plan_zones_action.isEnabled()


@pytest.fixture
def pt_window(app, examples_dir, tmp_path, no_dialogs, slot_errors):
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert w.open_model(examples_dir / "ndt" / "sterbina.json", template=True)
    w.ndt_panel.studies.setCurrentRow(0)  # s1 – PT horní plochy dílu 9
    yield w
    w.session.dirty = False
    w.close()


def test_pt_panel_settings_map_checks_pick_and_export(pt_window, no_dialogs, slot_errors,
                                                      tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QFileDialog

    from skodacad.ndt import PT_DISCLAIMER
    from skodacad.ndt.pt import COLORS

    w = pt_window
    panel = w.ndt_panel
    session = w.session
    assert panel.pt_box.isVisibleTo(panel) and panel.pt_box.title() == "Přístupnost povrchu pro PT"
    assert not panel.probe_box.isVisibleTo(panel)  # skupiny sondy UT jsou u PT skryté
    assert panel.warning.text() == PT_DISCLAIMER
    assert "zvoleno pro výpočet" in panel.pt_settings_label.text()
    panel.pt_settings_action.trigger()
    assert "PtDialog" in no_dialogs and not session.dirty  # zrušený dialog nic nemění

    def accept(self, dialog):
        dialog.edits["step_mm"].setText("20")
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", accept)
    panel.pt_settings_action.trigger()
    assert session.ndt_study("s1")["pt"]["step_mm"] == 20 and session.dirty
    steps = len(session._undo)

    def unchanged(self, dialog):
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", unchanged)
    panel.pt_settings_action.trigger()
    assert len(session._undo) == steps  # nezměněné OK = žádný krok Zpět
    assert "Odhad:" in panel.pt_estimate.text() and panel.pt_action.isEnabled()
    assert w.viewer.highlighted  # oblast studie zvýrazněná …
    panel.pt_action.trigger()
    assert session.ndt_pt_map is not None and not slot_errors
    assert w.viewer.highlighted == []  # … dokud ji nepřekryje mapa PT (barvy by vybledly)
    shown = w.viewer.coverage_map
    assert shown is not None and set(shown[2]) == {COLORS["ok"]}
    assert "Přístupné 100,0 %" in panel.pt_summary.text()
    panel.pt_check.setCurrentIndex(panel.pt_check.findData("view"))
    assert w.viewer.coverage_map is not shown  # mapa jedné kontroly se nakreslí znovu
    assert "Prohlídka" in panel.pt_legend.text()
    top = face_at(session.result.part, 0, 20, 30)
    w.viewer.click([top], (0, 20, 30))
    assert panel.pt_pick.text().startswith("Přístupné")
    path = tmp_path / "pt.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    panel.pt_export_action.trigger()
    assert path.read_text(encoding="utf-8-sig").splitlines()[1] == PT_DISCLAIMER
    panel.pt_stop_action.trigger()  # nic neběží – nic se nestane
    panel.pt_clear_action.trigger()
    assert session.ndt_pt_map is None and w.viewer.coverage_map is None
    w.undo_action.trigger()
    assert "pt" not in session.ndt_study("s1")
    assert slot_errors == []


def test_pt_panel_is_locked_while_ai_works(pt_window):
    w = pt_window
    panel = w.ndt_panel
    w.set_assistant_busy(True)
    panel.refresh()
    assert not any(a.isEnabled() for a in panel._pt_actions())
    w.set_assistant_busy(False)
    panel.refresh()
    assert panel.pt_settings_action.isEnabled() and panel.pt_action.isEnabled()


@pytest.fixture
def mt_window(app, examples_dir, tmp_path, no_dialogs, slot_errors):
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert w.open_model(examples_dir / "ndt" / "deska.json", template=True)
    w.ndt_panel.studies.setCurrentRow(1)  # s2 – MT horní plochy desky
    yield w
    w.session.dirty = False
    w.close()


def test_mt_panel_settings_map_views_pick_yoke_and_export(mt_window, no_dialogs, slot_errors,
                                                          tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QFileDialog

    from skodacad.ndt import MT_DISCLAIMER

    w = mt_window
    panel = w.ndt_panel
    session = w.session
    assert panel.mt_box.isVisibleTo(panel)
    assert panel.mt_box.title() == "Přiložení jha a směry magnetizace pro MT"
    assert not panel.probe_box.isVisibleTo(panel) and not panel.pt_box.isVisibleTo(panel)
    assert panel.warning.text() == MT_DISCLAIMER
    assert "je feromagnetický" in panel.mt_material.text()
    assert "zvoleno pro výpočet" in panel.mt_settings_label.text()
    panel.mt_settings_action.trigger()
    assert "MtDialog" in no_dialogs and not session.dirty  # zrušený dialog nic nemění

    def accept(self, dialog):
        dialog.edits["step_mm"].setText("25")
        dialog.edits["center_step_mm"].setText("50")
        dialog.checks["apply"].setChecked(False)
        dialog.checks["inspect"].setChecked(False)
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", accept)
    panel.mt_settings_action.trigger()
    assert session.ndt_study("s2")["mt"]["center_step_mm"] == 50 and session.dirty
    steps = len(session._undo)

    def unchanged(self, dialog):
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", unchanged)
    panel.mt_settings_action.trigger()
    assert len(session._undo) == steps  # nezměněné OK = žádný krok Zpět
    assert "Odhad:" in panel.mt_estimate.text() and panel.mt_action.isEnabled()
    panel.mt_action.trigger()
    assert session.ndt_mt_map is not None and not slot_errors
    assert w.viewer.highlighted == []  # mapa MT je hlavní – oblast se nezvýrazňuje
    shown = w.viewer.coverage_map
    assert shown is not None
    assert "Pokryto ve všech orientacích vad" in panel.mt_summary.text()
    panel.mt_view.setCurrentIndex(panel.mt_view.findData("d4"))
    assert w.viewer.coverage_map is not shown  # mapa jednoho směru se nakreslí znovu
    assert "Pole 90°" in panel.mt_legend.text()
    panel.mt_view.setCurrentIndex(panel.mt_view.findData("d0"))
    top = face_at(session.result.part, 0, 0, 20)
    w.viewer.click([top], (0, 30, 20))
    assert "Místo" in panel.mt_pick.text() and panel.mt_show_yoke_action.isEnabled()
    panel.mt_show_yoke_action.trigger()  # jho, které místo pokryje polem 0°
    assert session.ndt_yoke is not None and session.ndt_yoke.ok
    assert w.viewer.probe is not None and w.viewer.probe[0] == "ok"
    panel.mt_angle.setValue(90)
    w.viewer.click([top], (0, 0, 20))
    panel.mt_place_yoke_action.trigger()  # deska je široká jen 100 mm → rozteč 75
    assert session.ndt_yoke.spacing == 75 and "rozteč 75 mm" in panel.mt_yoke.text()
    assert w.viewer.probe[0] == "ok"
    panel.mt_hide_yoke_action.trigger()
    assert session.ndt_yoke is None and w.viewer.probe is None
    path = tmp_path / "mt.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    panel.mt_export_action.trigger()
    assert path.read_text(encoding="utf-8-sig").splitlines()[1] == MT_DISCLAIMER
    panel.mt_stop_action.trigger()  # nic neběží – nic se nestane
    panel.mt_clear_action.trigger()
    assert session.ndt_mt_map is None and w.viewer.coverage_map is None
    w.undo_action.trigger()
    assert "mt" not in session.ndt_study("s2")
    assert slot_errors == []


def test_mt_panel_is_locked_while_ai_works(mt_window):
    w = mt_window
    panel = w.ndt_panel
    w.set_assistant_busy(True)
    panel.refresh()
    assert not any(a.isEnabled() for a in panel._mt_actions())
    w.set_assistant_busy(False)
    panel.refresh()
    assert panel.mt_settings_action.isEnabled() and panel.mt_action.isEnabled()


@pytest.fixture
def rt_window(app, examples_dir, tmp_path, no_dialogs, slot_errors):
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert w.open_model(examples_dir / "ndt" / "otvor.json", template=True)
    w.ndt_panel.studies.setCurrentRow(1)  # s2 – RT desky s otvorem kolmo a pod 30°
    yield w
    w.session.dirty = False
    w.close()


def test_rt_panel_settings_projections_map_preview_and_export(rt_window, no_dialogs,
                                                              slot_errors, tmp_path,
                                                              monkeypatch):
    from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog

    from skodacad.ndt import RT_DISCLAIMER

    w = rt_window
    panel = w.ndt_panel
    box = panel.rt_box
    session = w.session
    assert box.isVisibleTo(panel) and box.title() == "Geometrie projekce RT"
    assert not panel.probe_box.isVisibleTo(panel) and not panel.mt_box.isVisibleTo(panel)
    assert panel.warning.text() == RT_DISCLAIMER
    assert box.projections.count() == 2 and box.projection_name() == "P1"
    assert w.viewer.probe[0] == "ok" and w.viewer.probe[1] == pytest.approx((0, 0, 520))
    assert len(w.viewer.beam) == 8  # paprsky ze zdroje do rohů detektoru
    assert "detektor volně" in box.setup_label.text()
    box.projections.setCurrentRow(1)  # P2 pod 30°
    assert w.viewer.probe[1] == pytest.approx((250, 0, 453.0127), abs=1e-3)
    box.settings_action.trigger()
    assert "RtDialog" in no_dialogs and not session.dirty  # zrušený dialog nic nemění

    def quick(self, dialog):
        dialog.edits["step_mm"].setText("10")
        dialog.edits["image_step_mm"].setText("20")
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", quick)
    box.settings_action.trigger()
    assert session.ndt_study("s2")["rt"]["image_step_mm"] == 20 and session.dirty
    steps = len(session._undo)

    def unchanged(self, dialog):
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", unchanged)
    box.settings_action.trigger()
    box.edit_action.trigger()  # P2: sklon 30° od osy +Z, nic nezměněno
    assert len(session._undo) == steps  # nezměněné OK = žádný krok Zpět
    before = session.ndt_rt_settings("s2").projection("P2")

    def tilt(self, dialog):
        assert dialog.tilt.text() == "30" and dialog.turn.text() == "0"
        dialog.tilt.setText("45")
        dialog.distance.setText("700")
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", tilt)
    box.edit_action.trigger()
    p2 = session.ndt_rt_settings("s2").projection("P2")
    assert p2.distance_mm == 700 and p2.reference_mm == before.reference_mm
    assert p2.direction == pytest.approx((math.sqrt(0.5), 0, math.sqrt(0.5)))
    top = face_at(session.result.part, 60, 0, 20)
    w.viewer.click([top], (60, 0, 20))
    assert box.add_action.isEnabled()
    box.add_action.trigger()  # zdroj nad kliknutým místem
    assert box.projection_name() == "P3" and w.viewer.probe[1] == pytest.approx((60, 0, 520))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("0; 30; 0", True))
    box.copy_action.trigger()
    assert box.projection_name() == "P4"
    assert session.ndt_rt_settings("s2").projection("P4").aim == (60, 30, 20)
    box.remove_action.trigger()
    assert [p.name for p in session.ndt_rt_settings("s2").projections] == ["P1", "P2", "P3"]
    assert "Odhad:" in box.estimate.text() and box.compute_action.isEnabled()
    box.compute_action.trigger()
    found = session.ndt_rt_map
    assert found is not None and len(found.projections) == 3 and not slot_errors
    assert w.viewer.highlighted == []  # mapa RT je hlavní – oblast se nezvýrazňuje
    shown = w.viewer.coverage_map
    assert shown is not None and "Promítne se" in box.summary.text()
    assert box.view.count() == 4  # celkem + 3 projekce
    box.view.setCurrentIndex(box.view.findData("p1"))
    assert w.viewer.coverage_map is not shown  # mapa jedné projekce se nakreslí znovu
    assert box.projection_name() == "P1" and not box.preview.pixmap().isNull()
    assert box.preview.pixmap().width() == 420  # náhled zmenšený na šířku panelu
    w.viewer.click([top], (60, 0, 20))
    assert "P1:" in box.pick.text() and "P3:" in box.pick.text()
    path = tmp_path / "rt.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(path), ""))
    box.export_action.trigger()
    assert path.read_text(encoding="utf-8-sig").splitlines()[1] == RT_DISCLAIMER
    png = tmp_path / "p3.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(png), ""))
    box.png_action.trigger()
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    box.stop_action.trigger()  # nic neběží – nic se nestane
    box.clear_action.trigger()
    assert session.ndt_rt_map is None and w.viewer.coverage_map is None
    w.undo_action.trigger()  # smazání P4
    assert box.projections.count() == 4
    assert slot_errors == []


def test_rt_panel_is_locked_while_ai_works(rt_window):
    w = rt_window
    box = w.ndt_panel.rt_box
    w.set_assistant_busy(True)
    w.ndt_panel.refresh()
    assert not any(a.isEnabled() for a in box.actions())
    w.set_assistant_busy(False)
    w.ndt_panel.refresh()
    assert box.settings_action.isEnabled() and box.compute_action.isEnabled()


def test_audit_panel_list_run_places_click_and_export(rt_window, no_dialogs, slot_errors,
                                                      tmp_path, monkeypatch):
    import dataclasses

    from PySide6.QtCore import Qt as QtCore
    from PySide6.QtWidgets import QFileDialog

    from skodacad.gui.audit_panel import MARK
    from skodacad.ndt import DISCLAIMER, RT_DISCLAIMER, UT_DISCLAIMER
    from skodacad.ndt.audit import TITLE

    w = rt_window
    session = w.session
    settings = session.ndt_rt_settings("s2")
    session.set_ndt_rt_settings("s2", dataclasses.replace(settings, step_mm=10,
                                                          image_step_mm=20))
    w._refresh_all()
    action(w, "Předběžný NDT audit…").trigger()
    panel = w.audit_panel
    assert panel.warning.text() == DISCLAIMER
    rows = [panel.studies.item(i) for i in range(panel.studies.count())]
    assert [r.data(QtCore.ItemDataRole.UserRole) for r in rows] == ["study", "access", "study"]
    assert rows[0].checkState() == QtCore.CheckState.Unchecked  # UT bez plánu – neprovedeno
    assert "nemá plán dráhy" in rows[0].text() and "i návrh poloh" in rows[1].text()
    assert rows[2].checkState() == QtCore.CheckState.Checked and "– asi" in rows[2].text()
    assert panel.estimate.text().startswith("Spočítá se 1 z 2")
    assert not panel.export_action.isEnabled() and panel.run_action.isEnabled()
    steps = len(session._undo)
    panel.operator.setText("J. N.")
    panel.run_action.trigger()
    audit = session.ndt_audit
    assert audit is not None and audit.operator == "J. N." and len(session._undo) == steps
    assert UT_DISCLAIMER in panel.warning.text() and RT_DISCLAIMER in panel.warning.text()
    assert TITLE in panel.overview.text() and "spočítáno" in panel.overview.text()
    assert panel.places.rowCount() == 2 and panel.places.item(0, 0).text() == "S2-01"
    assert "mimo detektor" in panel.places.item(0, 5).text()
    assert w.viewer.points is None
    panel.places.selectRow(0)
    place = audit.places()[0]
    assert w.ndt_panel.current_id() == "s2" and "S2-01" in panel.place_info.text()
    assert w.viewer.points == ([place.center], [MARK]) and w.viewer.coverage_map is not None
    assert session.ndt_rt_map is audit.entry("s2").result  # mapa i ve skupině RT
    panel.hide_action.trigger()
    assert w.viewer.points is None and panel.place() is None
    panel.export_action.trigger()  # zrušený výběr složky – nic
    folder = tmp_path / "zprava"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(folder))
    panel.export_action.trigger()
    assert sorted(p.name for p in folder.iterdir()) == ["mista.csv", "studie-s2-rt.csv",
                                                       "zprava.html", "zprava.pdf"]
    page = (folder / "zprava.html").read_text(encoding="utf-8")
    assert page.count("data:image/png;base64,") == 3  # 2 náhledy RT + mapa z 3D okna
    assert "Mapa ve 3D – RT desky" in page and "Zpracoval(a): J. N." in page
    pdf = (folder / "zprava.pdf").read_bytes()
    assert pdf.startswith(b"%PDF") and b"/Image" in pdf  # náhledy RT i v PDF
    session.set_parameter("t", "25")
    w._refresh_all()
    assert session.ndt_audit is None and panel.places.rowCount() == 0
    assert panel.warning.text() == DISCLAIMER and not panel.export_action.isEnabled()
    assert slot_errors == []


def test_audit_panel_is_locked_while_ai_works(rt_window):
    w = rt_window
    w.show_audit()
    panel = w.audit_panel
    assert panel.run_action.isEnabled()
    w.set_assistant_busy(True)
    panel.refresh()
    assert not any(a.isEnabled() for a in panel.actions()) and not w.audit_dock.isEnabled()
    w.set_assistant_busy(False)
    panel.refresh()
    assert panel.run_action.isEnabled() and w.audit_dock.isEnabled()


def test_direct_edit_feature_shows_its_face_and_edits_only_the_value(window, tmp_path, monkeypatch):
    """Hodnota existující úpravy se mění až po náhledu a potvrzení."""
    from skodacad.document import Document

    document = Document.load(window.session.path)
    face = {"at": [70, 0, 0], "normal": [0, 0, -1], "type": "plane"}
    document.features.append({"id": "tensi", "type": "move_face", "face": face,
                              "origin": "deska", "distance": -3})
    path = tmp_path / "upravy.json"
    document.save(path)
    before = window.session.properties.volume_mm3
    assert window.open_model(path) and window.session.result.ok
    assert all(a.text() not in ("Posunutí plochy", "Průměr plochy")
               for a in window.add_feature_actions.values())
    window.tree.setCurrentItem(window.tree.topLevelItem(len(document.features) - 1))
    assert "u bodu 70; 0; 0" in form_field(window, "face").text()
    assert form_field(window, "origin").text() == "deska"
    thinner = window.session.properties.volume_mm3
    assert thinner < before

    def cancel(dialog):
        dialog.calculate()
        assert dialog.apply_button.isEnabled()
        return QtWidgets.QDialog.DialogCode.Rejected

    monkeypatch.setattr(window, "_exec_dialog", cancel)
    set_text(form_field(window, "distance"), "-5")
    assert window.session.feature("tensi")["distance"] == -3
    assert window.session.properties.volume_mm3 == pytest.approx(thinner)

    def confirm(dialog):
        dialog.calculate()
        assert dialog.apply_button.isEnabled()
        assert window.session.feature("tensi")["distance"] == -3
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(window, "_exec_dialog", confirm)
    set_text(form_field(window, "distance"), "-6")
    feature = window.session.feature("tensi")
    assert feature["face"] == face and feature["origin"] == "deska" and feature["distance"] == -6
    assert before - window.session.properties.volume_mm3 == pytest.approx(2 * (before - thinner))


def test_drawing_dimensions_are_visible_and_removable(window):
    w = window
    w.drawing_kind.setCurrentIndex(0)  # celkový rozměr X
    w.add_drawing_dimension()
    assert w.drawing_list.count() == 1
    assert "Celkový rozměr X" in w.drawing_list.item(0).text()
    assert "✕" not in w.drawing_list.item(0).text()
    w.drawing_list.setCurrentRow(0)
    w.remove_drawing_dimension()
    assert w.drawing_list.count() == 0


def test_drawing_dimension_placement_in_window_is_saved_and_undoable(window):
    w = window
    w.drawing_kind.setCurrentIndex(0)
    w.add_drawing_dimension()
    w.drawing_list.setCurrentRow(0)
    w.dimension_view.setCurrentIndex(w.dimension_view.findData("top"))
    w.dimension_side.setCurrentIndex(w.dimension_side.findData("high"))
    w.dimension_offset.setValue(12)
    w.set_drawing_dimension_placement()
    placement = w.session.document.drawing["dimensions"][0]["placement"]
    assert placement == {"view": "top", "side": "high", "offset": 12}
    w.session.undo()
    assert "placement" not in w.session.document.drawing["dimensions"][0]


def test_drawing_section_can_be_set_and_removed(window):
    w = window
    w.drawing_section_enabled.setChecked(True)
    w.drawing_section_axis.setCurrentText("Y")
    w.drawing_section_position.setValue(5)
    w.set_drawing_section()
    assert w.session.document.drawing["section"] == {"axis": "Y", "position": 5.0,
                                                       "flipped": False}
    w.drawing_section_enabled.setChecked(False)
    w.set_drawing_section()
    assert "section" not in w.session.document.drawing


def test_export_drawing_from_panel(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    path = tmp_path / "vykres.dxf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kw: (str(path), "DXF"))
    monkeypatch.setattr(window, "_error", lambda title, message: pytest.fail(f"{title}: {message}"))
    window.drawing_scale.setCurrentIndex(window.drawing_scale.findData(0.5))
    window.export_drawing()
    assert path.exists() and path.stat().st_size > 100
    assert "zkontroluj" in window.statusBar().currentMessage()


def test_export_warns_before_saving_overlapping_dimensions(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    path = tmp_path / "vykres.dxf"
    window.drawing_scale.setCurrentIndex(window.drawing_scale.findData(0.5))
    first = window.session.add_drawing_dimension("overall", axis="x")
    second = window.session.add_drawing_dimension("overall", axis="x")
    for dimension in (first, second):
        window.session.set_drawing_dimension_placement(dimension, "front", "low", 6)
    seen = []

    def save_dialog(_parent, title, *_args, **kwargs):
        from skodacad.gui.file_dialogs import FILE_OPTIONS

        assert kwargs["options"] == FILE_OPTIONS
        seen.append((title, window.statusBar().currentMessage()))
        return str(path), "DXF"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", save_dialog)
    monkeypatch.setattr(window, "_error", lambda title, message: pytest.fail(f"{title}: {message}"))
    window.export_drawing()
    assert path.exists()
    assert "překrytí" in seen[0][0] and "překrytí" in seen[0][1]
    assert "překrytí" in window.statusBar().currentMessage()
    window._refresh_all()
    visible = [window.drawing_list.item(i).text() for i in range(window.drawing_list.count())]
    assert any(first in text for text in visible) and any(second in text for text in visible)


def test_drawing_paper_and_scale_are_saved_and_shown_after_undo_and_reopen(window, tmp_path,
                                                                           monkeypatch):
    w = window
    monkeypatch.setattr(w, "_error", lambda title, message: pytest.fail(f"{title}: {message}"))
    w.drawing_paper.setCurrentText("A3")
    w.drawing_scale.setCurrentIndex(w.drawing_scale.findData(0.5))
    assert w.session.drawing_sheet() == ("A3", 0.5)
    w.undo()  # jen měřítko zpět, okno ukáže uložený stav
    assert (w.drawing_paper.currentText(), w.drawing_scale.currentData()) == ("A3", 1)
    w.redo()
    path = tmp_path / "s_vykresem.json"
    w.session.save(path)
    w.undo()
    w.undo()
    assert (w.drawing_paper.currentText(), w.drawing_scale.currentData()) == ("A4", 1)
    w.session.dirty = False  # jinak by se otevření ptalo na uložení (dialog by čekal)
    assert w.open_model(path)
    assert (w.drawing_paper.currentText(), w.drawing_scale.currentData()) == ("A3", 0.5)
    assert not w.session.can_undo  # zobrazení uloženého listu není nová změna


def test_drawing_views_can_be_hidden_undone_and_last_one_stays(window, monkeypatch):
    w = window
    boxes = w.drawing_view_boxes
    errors = []
    monkeypatch.setattr(w, "_error", lambda title, message: errors.append(message))
    boxes["right"].setChecked(False)
    assert w.session.drawing_views() == ("front", "top") and not errors
    w.undo()
    assert boxes["right"].isChecked() and w.session.drawing_views() == (
        "front", "top", "right")
    boxes["front"].setChecked(False)
    boxes["top"].setChecked(False)
    boxes["right"].setChecked(False)  # poslední pohled odebrat nejde
    assert errors and "aspoň jeden pohled" in errors[-1]
    assert w.session.drawing_views() == ("right",) and boxes["right"].isChecked()


def test_drawing_title_dialog_saves_and_reopens(window, monkeypatch):
    def fill(_window, dialog):
        fields = dialog.findChildren(QtWidgets.QLineEdit)
        assert len(fields) == 4
        for field, value in zip(fields, ("V-12", "B", "Novák", "28.10.2026"), strict=True):
            field.setText(value)
        return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(MainWindow, "_exec_dialog", fill)
    window.edit_drawing_title_block()
    assert window.session.document.drawing["title_block"]["number"] == "V-12"

    def cancel(_window, dialog):
        fields = dialog.findChildren(QtWidgets.QLineEdit)
        assert [f.text() for f in fields] == ["V-12", "B", "Novák", "28.10.2026"]
        return QtWidgets.QDialog.DialogCode.Rejected

    monkeypatch.setattr(MainWindow, "_exec_dialog", cancel)
    window.edit_drawing_title_block()
    assert window.session.document.drawing["title_block"]["revision"] == "B"
