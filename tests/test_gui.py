"""Testy okna bez skutečného 3D prohlížeče (ten potřebuje OpenGL a obrazovku)."""

import math
import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QPoint, Signal  # noqa: E402

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
        self.selection_changed.emit([])  # jako skutečný prohlížeč: nový díl = nic vybráno

    def highlight(self, shapes):
        self.highlighted = list(shapes)

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
    panel.coverage_action.trigger()
    assert session.ndt_coverage is not None and w.viewer.coverage_map is not None
    assert UT_DISCLAIMER in panel.coverage_label.text()
    assert "Geometricky pokryto" in panel.coverage_label.text()
    assert w.viewer.probe is not None
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
    assert len(labels) == 8
    assert labels[0] == "NDT 1 – Deska" and labels[-1] == "NDT 8 – Obtížný přístup"
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
    assert tree_texts(w) == ["✓  Skica „Skica 1“", "✓  Vysunutí „Vysunutí 1“"]
    assert selected_text(w) == "✓  Vysunutí „Vysunutí 1“"  # nový prvek je hned vybraný
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
    assert selected_text(w) == "✓  Zaoblení „Zaoblení 1“"
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
    assert selected_text(w) == "✓  Díra „Díra 1“ – M6 závit"
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
    assert selected_text(w).endswith("M12 závit (vymodelovaný)")
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
    assert selected_text(w) == "✓  Pole „Pole 1“ – v řadě, 3 ks"
    form = w.feature_editor.form
    assert form.widget("features").findChild(QtWidgets.QCheckBox, "feature_hole1").isChecked()
    assert form.is_shown("spacing") and not form.is_shown("axis")
    assert w.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10 - 3 * one)

    kind = form_field(w, "kind")
    kind.setCurrentIndex(kind.findData("circular"))  # 3× dokola kolem osy Z
    assert form.is_shown("axis") and form.is_shown("center") and not form.is_shown("spacing")
    assert w.session.feature("pattern1")["kind"] == "circular"
    assert selected_text(w) == "✓  Pole „Pole 1“ – dokola, 3 ks"
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
    assert selected_text(w) == "✓  Zrcadlení „Zrcadlení 1“ – celý díl"
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
    assert selected_text(w) == "✓  Tažení „Tažení 1“ – jekl 40 × 20 × 2, trasa z 3 bodů"
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
    assert selected_text(w) == ("✓  Normalizovaný díl „Normalizovaný díl 1“ – ložisko 608 "
                                "(8 × 22 × 7)")


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
    assert selected_text(w) == "✓  Normalizovaný díl „Normalizovaný díl 1“ – ISO 4032 M6 (kapsa)"


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
    assert selected_text(w) == "✓  Přechod „Přechod 1“ – mezi 2 skicami, dutý 2 mm"
    first.setChecked(False)
    assert "zaškrtni aspoň 2 skici" in w.statusBar().currentMessage()
    assert w.session.feature("loft1")["sketches"] == ["sketch1", "sketch2"]


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
    assert ndt_texts(w) == ["✓ UT desky shora (UT) – platná"]
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
    assert ndt_texts(w) == ["⚠ UT desky shora (UT) – zastaralá"]
    assert "posunula o 10.00 mm" in w.ndt_panel.details.text()
    assert not w.ndt_panel.verify_action.isEnabled()
    w.ndt_panel.confirm_action.trigger()
    assert ndt_texts(w) == ["✓ UT desky shora (UT) – platná"]
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
    assert ndt_texts(w)[1] == "✓ MT studie 2 (MT) – platná"
    assert w.ndt_panel.current_id() == "s2"
    w.ndt_panel.rename_action.trigger()  # dialog zrušen (no_dialogs) – nic se nezmění
    assert ndt_texts(w)[1].startswith("✓ MT studie 2")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("MT zespodu", True))
    w.ndt_panel.rename_action.trigger()
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("PT – kapilární", True))
    w.ndt_panel.method_action.trigger()
    assert ndt_texts(w)[1] == "✓ MT zespodu (PT) – platná"
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
    assert ndt_texts(w)[2] == "✓ MT zespodu (kopie) (PT) – platná"
    w.ndt_panel.delete_action.trigger()
    assert len(ndt_texts(w)) == 2
    action(w, "Zpět").trigger()
    assert len(ndt_texts(w)) == 3
    assert slot_errors == []


def test_ndt_new_study_without_selection_is_incomplete(ndt_window, slot_errors):
    w = ndt_window
    action(w, "Nová NDT studie z výběru").trigger()
    assert ndt_texts(w)[1] == "⚠ UT studie 2 (UT) – neúplná"
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


def test_probe_tools_only_for_ut_and_bad_placement_message(rib_window, slot_errors):
    from skodacad.ndt import DISCLAIMER, UT_DISCLAIMER

    w = rib_window
    panel = w.ndt_panel
    w.viewer.click([edge_at(w.session.result.part, 0, -50, 80)])
    assert not panel.place_action.isEnabled()  # hrana, ne plocha
    w.session.set_ndt_method("s1", "PT")
    w._refresh_all()
    assert panel.probe_label.text() == "Sonda je zatím jen pro UT studie."
    assert panel.warning.text() == DISCLAIMER  # PT: obecné upozornění, ne UT
    panel.studies.setCurrentRow(-1)  # bez výběru podle metody nové studie (UT)
    assert panel.warning.text() == UT_DISCLAIMER
    panel.method_combo.setCurrentIndex(panel.method_combo.findData("RT"))
    assert panel.warning.text() == DISCLAIMER
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
