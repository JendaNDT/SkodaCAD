"""P7.55: NDT průvodce UT (rámy 2c a 3d) a skupina „NDT studie“ v levé kartě."""

import os
import re
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402

from conftest import face_at  # noqa: E402
from skodacad.gui.main_window import MainWindow  # noqa: E402
from skodacad.gui.ndt_wizard import (  # noqa: E402
    COVERAGE_NOTE,
    SCOPE_FILES,
    ScopeDialog,
    StepState,
    Wizard,
    scope_text,
)
from skodacad.ndt import MT_DISCLAIMER, PT_DISCLAIMER, RT_DISCLAIMER, UT_DISCLAIMER  # noqa: E402
from test_gui import FakeViewer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def plate(app, examples_dir, tmp_path):
    """Referenční deska: UT studie s1 (horní plocha) a MT studie s2."""
    model = tmp_path / "deska.json"
    shutil.copy(examples_dir / "ndt" / "deska.json", model)
    window = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert window.open_model(model)
    window.resize(1440, 900)
    window.show()
    app.processEvents()
    yield window
    window.session.dirty = False
    window.close()


def wizard(states):
    w = Wizard("Přístupnost UT sondy")
    for title in ("Kontrolovaná oblast", "Sonda", "Přiložení sondy", "Geometrické pokrytí"):
        w.add_step(title, QtWidgets.QWidget(), short="pokrytí" if "pokrytí" in title else None)
    w.update(states, key="s1")
    return w


def kinds(w):
    return [step.kind for step in w.steps]


def test_wizard_derives_step_then_stays_until_next(app):
    w = wizard([StepState(True, "1 plocha"), StepState(True, "Úhlová"),
                StepState(False, "Nepřiloženo", skippable=True), StepState(False)])
    assert w.active == 2 and kinds(w) == ["done", "done", "active", "future"]
    assert w.position.text() == "Krok 3 ze 4" and w.next.text() == "Další: pokrytí"
    assert w.next.isEnabled()  # přiložení jde přeskočit (návrh poloh v kroku 4)
    assert not w.steps[3].change.isVisible() and w.steps[0].summary_label.text() == "1 plocha"
    # přiložená sonda: krok 3 hotový, ale zůstává otevřený (rám 2c)
    w.update([StepState(True), StepState(True), StepState(True, "Přiloženo"), StepState(False)],
             key="s1")
    assert w.active == 2 and w.steps[2].kind == "active"
    w.go_next()
    assert w.active == 3 and w.next.text() == "Hotovo" and not w.next.isEnabled()
    w.update([StepState(True)] * 4, key="s1")
    assert w.next.isEnabled()
    w.go_next()  # Hotovo: všechny kroky jako hotové řádky
    assert w.active is None and kinds(w) == ["done"] * 4
    assert w.position.text() == "Všechny kroky hotové"
    w.steps[0].change.click()  # Změnit otevře hotový krok
    assert w.active == 0 and w.back.isEnabled() is False
    w.go_next()
    assert w.active == 1
    w.go_back()
    assert w.active == 0


def test_wizard_resets_for_another_study_and_when_step_disappears(app):
    w = wizard([StepState(True), StepState(True), StepState(True), StepState(True)])
    assert w.active == 3
    w.open_step(0)
    w.update([StepState(False, "není zadaná"), StepState(False), StepState(False),
              StepState(False)], key="s1")
    assert w.active == 0 and kinds(w) == ["active", "future", "future", "future"]
    w.open_step(2)  # nedostupný krok nejde otevřít
    assert w.active == 0 and not w.next.isEnabled()
    w.update([StepState(True), StepState(True), StepState(False), StepState(False)], key="s2")
    assert w.active == 2  # jiná studie: krok podle jejího stavu


def test_scope_documents_are_bundled_and_quote_the_disclaimer():
    spec = (ROOT / "packaging" / "skodacad.spec").read_text(encoding="utf-8")
    for method, disclaimer in (("UT", UT_DISCLAIMER), ("PT", PT_DISCLAIMER),
                               ("MT", MT_DISCLAIMER), ("RT", RT_DISCLAIMER)):
        assert f'"{SCOPE_FILES[method]}"' in spec  # aplikace je přibalí (Celé upozornění)
        assert disclaimer in scope_text(method)


def test_ut_study_shows_wizard_header_badge_and_full_disclaimer(plate, monkeypatch):
    w = plate
    panel = w.ndt_panel
    w.workspace.show_panel("ndt")
    assert panel.new_box.isVisibleTo(panel) and not panel.ut_wizard.isVisibleTo(panel)
    panel.select("s1")
    assert panel.ut_wizard.isVisibleTo(panel) and not panel.new_box.isVisibleTo(panel)
    assert panel.ut_wizard.title() == "Přístupnost UT sondy"  # doporučený název (vymezení)
    assert panel.warning.text() == UT_DISCLAIMER and panel.warning.isVisibleTo(panel)  # R7
    assert w.workspace.heading("ndt") == "UT desky shora"
    assert w.workspace.menu_buttons["ndt"].text() == "NDT studie"
    badge = w.workspace.badges["ndt"]
    assert badge.text() == "✓ platná" and badge.property("cardBadge") == "ok"
    assert not panel.studies_section.expanded  # seznam studií je sbalený
    wiz = panel.ut_wizard
    assert kinds(wiz) == ["done", "done", "active", "future"]
    assert wiz.steps[0].summary_label.text() == "1 plocha"
    assert wiz.steps[1].summary_label.text().startswith("Úhlová · β 45°")
    shown = []
    monkeypatch.setattr(w, "_exec_dialog", lambda dialog: shown.append(dialog) or 0)
    panel.scope_link.linkActivated.emit("scope")
    assert isinstance(shown[0], ScopeDialog)
    assert UT_DISCLAIMER in shown[0].browser.toPlainText()


def test_place_probe_then_coverage_step_bar_and_pill(plate):
    w = plate
    panel = w.ndt_panel
    w.workspace.show_panel("ndt")
    panel.select("s1")
    wiz = panel.ut_wizard
    assert panel.placement_label.property("cardState") == "info"
    w.viewer.click([face_at(w.session.result.part, 40, 0, 20)], (40, 0, 20))
    panel.place_action.trigger()
    assert w.session.ndt_placement.state == "ok"
    assert wiz.active == 2 and wiz.steps[2].kind == "active"  # zůstává do „Další“
    assert panel.placement_label.property("cardState") == "ok"
    assert w.status_pill.focus == ("measure", "● Přiloženo")
    assert panel.beam_section.isVisibleTo(panel) and "Dráha paprsku" in panel.beam_label.text()
    wiz.next.click()
    assert wiz.active == 3 and wiz.steps[2].summary_label.text() == "Přiloženo · směr 0°"
    assert panel.coverage_action.isEnabled()
    assert not panel.coverage_bar.bar.isVisibleTo(panel)  # zatím nespočítáno
    panel.coverage_step.setValue(25)
    panel.coverage_convergence.setChecked(False)
    panel.coverage_action.trigger()
    result = w.session.ndt_coverage
    bar = panel.coverage_bar
    assert bar.bar.isVisibleTo(panel)
    assert sum(bar.percents.values()) == pytest.approx(100, abs=0.05)
    covered = result.percent("covered")
    assert f"{covered:.2f} %" in bar.rows["covered"].text()
    assert bar.note.text() == COVERAGE_NOTE and bar.note.isVisibleTo(panel)
    assert w.status_pill.focus == ("measure", f"● Pokryto {covered:.2f} %")
    assert wiz.steps[3].kind == "active" and wiz.next.isEnabled()
    wiz.next.click()
    assert wiz.active is None
    assert wiz.steps[3].summary_label.text() == f"Pokryto {covered:.2f} %"


def test_other_methods_keep_their_groups_and_stale_study_asks_for_confirmation(plate):
    w = plate
    panel = w.ndt_panel
    w.workspace.show_panel("ndt")
    panel.select("s2")  # MT
    assert not panel.ut_wizard.isVisibleTo(panel) and panel.mt_box.isVisibleTo(panel)
    assert panel.warning.text() == MT_DISCLAIMER
    assert not panel.stale_box.isVisibleTo(panel)
    panel.select("s1")
    field = w._param_fields["t"]
    field.setText("25")
    field.editingFinished.emit()
    assert panel.current().state == "stale"
    assert panel.stale_box.isVisibleTo(panel) and w.workspace.badges["ndt"].text() == \
        "⚠ zastaralá"
    assert panel.stale_button.text() == "Potvrdit" and panel.stale_button.isEnabled()
    panel.stale_button.click()
    assert panel.current().state == "ok" and not panel.stale_box.isVisibleTo(panel)


def test_left_card_study_group_follows_ndt_activity_and_selection(plate):
    w = plate
    group, studies = w.ndt_group, w.ndt_study_list
    assert not group.isVisibleTo(w.model_dock)  # činnost 3D model
    w.ribbon.select_page("ndt")
    assert group.isVisibleTo(w.model_dock)
    rows = [(studies.item(i).text(), studies.item(i).data(Qt.ItemDataRole.UserRole + 41))
            for i in range(studies.count())]
    assert rows == [("UT desky shora", "ok"), ("MT horní plochy", "ok")]
    first = studies.item(0)
    studies.setCurrentRow(1)  # klik v levé kartě = studie v panelu NDT
    assert w.ndt_panel.current_id() == "s2" and w.workspace.active == "ndt"
    w.ndt_panel.select("s1")  # výběr v panelu = řádek v levé kartě
    assert studies.currentRow() == 0
    w._reload_all()
    assert studies.item(0) is first  # řádky se znovu používají (Cocoa AX)
    w.ribbon.select_page("model")
    assert not group.isVisibleTo(w.model_dock)


def test_long_checkbox_labels_move_detail_into_tooltip(plate):
    panel = plate.ndt_panel
    for box in panel.findChildren(QtWidgets.QCheckBox):
        assert not re.search(r" \(.*\)$", box.text()), box.text()
    assert panel.plan_robust.text() == "ověřit odolnost"
    assert "Posun řádků o ± půl rozteče." in panel.plan_robust.toolTip()
