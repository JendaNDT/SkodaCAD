"""P5.2B: okno sestavy offscreen – strom, poloha, Zpět, chybějící díl, výpočet na pozadí."""

import json
import math
import shutil

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from skodacad.gui.assembly_window import AssemblyWindow, parse_value  # noqa: E402
from skodacad.gui.main_window import MainWindow  # noqa: E402
from test_gui import FakeViewer  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialogs(monkeypatch):
    """Dialogy by v testu čekaly – odpovědi se nastaví předem (výchozí = zrušit)."""
    answers = {"open": "", "save": "", "directory": None,
               "question": QMessageBox.StandardButton.Cancel}
    shown = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (answers["open"], ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (answers["save"], ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda parent, title, start, **kw:
                        start if answers["directory"] is None else answers["directory"])
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[1:3]))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: shown.append(a[1]) or answers["question"])
    answers["shown"] = shown
    return answers


@pytest.fixture
def project(tmp_path, examples_dir):
    """Kopie ukázky: projekt/krabicka.json a projekt/sestavy/… (cesta ../krabicka.json)."""
    root = tmp_path / "projekt"
    shutil.copytree(examples_dir / "sestavy", root / "sestavy")
    shutil.copy(examples_dir / "krabicka.json", root / "krabicka.json")
    return root


@pytest.fixture
def main_window(app, examples_dir, tmp_path, dialogs):
    window = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    yield window
    for assembly in window.assembly_windows:
        assembly.session.dirty = False
        assembly.close()
    window.session.dirty = False
    window.close()


@pytest.fixture
def opened(main_window, project):
    window = main_window.open_assembly(project / "sestavy" / "krabicka_s_vickem.json")
    assert window is not None
    return window


def items(window):
    result = []

    def walk(item, depth):
        result.append(("  " * depth + item.text(0), item.text(2)))
        for index in range(item.childCount()):
            walk(item.child(index), depth + 1)

    for index in range(window.tree.topLevelItemCount()):
        walk(window.tree.topLevelItem(index), 0)
    return result


def pick(window, component):
    for index in range(window.tree.topLevelItemCount()):
        item = window.tree.topLevelItem(index)
        if item.data(0, 256) == json.dumps([component]):
            window.tree.setCurrentItem(item)
            return
    raise AssertionError(component)


def press(window, text):
    matches = [a for a in window.findChildren(QAction) if a.text() == text]
    assert matches, f"akce „{text}“ v okně není"
    matches[0].trigger()


def test_open_from_main_window_shows_tree_3d_and_summary(main_window, opened, project):
    assert main_window.session.document is None  # díl v hlavním okně se neotevřel
    assert items(opened)[:2] == [("Krabička (pevná)", "✓"), ("Víčko", "✓")]
    assert len(items(opened)) == 6
    part, fit = opened.viewer.parts[-1]
    assert fit and part.volume == pytest.approx(opened.session.result.volume_mm3)
    assert "Objem: 31309,29 mm³" in opened.summary.text()
    assert "Krabička s víčkem – krabicka_s_vickem.json" in opened.windowTitle()
    # I Otevřít v hlavním okně pozná sestavu podle „kind“, ne přípony.
    again = main_window.open_model(project / "sestavy" / "krabicka_s_vickem.json")
    assert again and len(main_window.assembly_windows) == 2


@pytest.mark.parametrize("from_assembly", [False, True])
@pytest.mark.parametrize("cancel", [False, True])
def test_native_project_selection_precedes_open_and_cancel_preserves_window(
        main_window, project, dialogs, monkeypatch, from_assembly, cancel):
    from skodacad.gui import assembly_access

    monkeypatch.setattr(assembly_access, "IS_MACOS", True)
    monkeypatch.setattr(assembly_access, "_granted_projects", set())
    source = project / "sestavy" / "krabicka_s_vickem.json"
    original = source.read_bytes()
    window = main_window.open_assembly(source) if from_assembly else main_window
    old_session = window.session
    old_path = old_session.path
    old_result = old_session.result
    count = len(main_window.assembly_windows)
    dialogs["open"] = str(source)
    dialogs["directory"] = "" if cancel else str(project)
    window.open_dialog()
    assert source.read_bytes() == original
    assert not dialogs["shown"]
    if cancel:
        assert len(main_window.assembly_windows) == count
        assert window.session is old_session and window.session.path == old_path
        assert window.session.result is old_result
    else:
        result_window = window if from_assembly else main_window.assembly_windows[-1]
        result = result_window.session.result
        assert result.complete and len(result.instances) == 6
        assert all(i.part.is_valid for i in result.instances)
        assert result.volume_mm3 == pytest.approx(31309.29, abs=0.01)
        lo, hi = result.bounds()
        assert tuple(lo) == pytest.approx((-40, -25, -3), abs=1e-6)
        assert tuple(hi) == pytest.approx((40, 25, 32), abs=1e-6)


@pytest.mark.parametrize("from_assembly", [False, True])
@pytest.mark.parametrize("cancel", [False, True])
def test_nested_sources_outside_first_folder_round_trip_or_cancel_preserves_model(
        main_window, project, tmp_path, dialogs, monkeypatch, from_assembly, cancel):
    from skodacad.gui import assembly_access
    from test_assembly import assembly_data, component, part_data, write

    monkeypatch.setattr(assembly_access, "IS_MACOS", True)
    monkeypatch.setattr(assembly_access, "_granted_projects", set())
    root = tmp_path / "Vnořený projekt"
    part = write(root / "dily/deska.json", part_data())
    cylinder = part_data()
    cylinder["features"][0]["elements"] = [
        {"shape": "circle", "diameter": 10, "center": [45, 10]}]
    write(root / "dily/valecek.json", cylinder)
    write(root / "sestavy/moduly/pod.json", assembly_data([
        component("deska", "../../dily/deska.json"),
        component("valecek", "../../dily/valecek.json")]))
    source = write(root / "sestavy/hlavni.json", assembly_data([
        component("a", "moduly/pod.json", position=(100, 0, 0), rotation=(0, 0, 90)),
        component("b", "moduly/pod.json", position=(0, 80, 20))]))
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    window = (main_window.open_assembly(project / "sestavy/krabicka_s_vickem.json")
              if from_assembly else main_window)
    original_path, original_result = window.session.path, window.session.result
    count = len(main_window.assembly_windows)
    choices = [str(source.parent), "" if cancel else str(root)]
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: choices.pop(0))
    dialogs["open"] = str(source)
    window.open_dialog()
    assert not choices and not dialogs["shown"]
    if cancel:
        assert window.session.path == original_path and window.session.result is original_result
        assert len(main_window.assembly_windows) == count
    else:
        opened = window if from_assembly else main_window.assembly_windows[-1]
        result = opened.session.result
        assert result.complete and len(result.statuses) == 6 and len(result.instances) == 4
        assert all(i.part.is_valid for i in result.instances)
        assert result.volume_mm3 == pytest.approx(12000 + 500 * math.pi)
        lo, hi = result.bounds()
        assert tuple(lo) == pytest.approx((0, 0, 0), abs=1e-6)
        assert tuple(hi) == pytest.approx((100, 100, 30), abs=1e-6)
        files = [s.file for s in result.statuses]
        target = root / "kopie/kopie.json"
        target.parent.mkdir()
        dialogs["save"] = str(target)
        assert opened.save_as()
        dialogs["open"] = str(target)
        opened.open_dialog()  # projekt je už schválen; další panel nesmí vzniknout
        assert opened.session.path == target.resolve()
        assert opened.session.result.complete
        assert [s.file for s in opened.session.result.statuses] == files
        assert opened.session.result.volume_mm3 == pytest.approx(12000 + 500 * math.pi)
        assert part in files
    assert all(p.read_bytes() == data for p, data in before.items())


def test_form_changes_position_name_as_one_undo_step(opened):
    pick(opened, "nozicka_1")
    assert [e.text() for e in opened.position_edits] == ["-x0", "-y0", "-h"]
    assert opened.viewer.highlighted  # hrany vybrané kopie
    opened.name_edit.setText("Přední levá")
    opened.position_edits[2].setText("-h - 1.5")
    opened.position_edits[0].setText("-30,5")
    opened.apply_form()
    component = opened.session.assembly.component("nozicka_1")
    assert component.position == [-30.5, "-y0", "-h - 1.5"]
    box = opened.session.result.instances[2].part.bounding_box()
    assert (box.min.X, box.min.Z) == pytest.approx((-35.5, -4.5))
    assert component.name == "Přední levá" and opened.session.dirty
    assert "*" in opened.windowTitle()
    press(opened, "Zpět")
    component = opened.session.assembly.component("nozicka_1")
    assert component.position == ["-x0", "-y0", "-h"] and component.name == "Nožička 1"
    assert not opened.session.can_undo
    press(opened, "Znovu")
    assert opened.session.assembly.component("nozicka_1").name == "Přední levá"


@pytest.mark.parametrize("width, view_width", [(1200, 620), (1024, 450), (960, 390)])
def test_compact_panels_leave_space_for_model_and_readable_coordinates(opened, app,
                                                                     width, view_width):
    opened.resize(width, 720)
    opened.reset_layout_action.trigger()
    pick(opened, "nozicka_1")
    app.processEvents()
    assert opened.viewer.width() >= view_width
    assert opened.tree.visualRect(opened.tree.indexFromItem(
        opened.tree.topLevelItem(0), 0)).width() >= 130
    assert opened.viewer.height() >= 600
    assert all(edit.width() >= 90 for edit in
               [*opened.position_edits, *opened.rotation_edits])
    assert not opened.component_scroll.horizontalScrollBar().isVisible()
    assert opened.checks_dock.isHidden()
    assert "krabicka" in opened.tree.topLevelItem(0).toolTip(0).lower()


def test_view_controls_preserve_unapplied_values_history_selection_and_view(opened, app):
    pick(opened, "nozicka_1")
    document = opened.session.assembly.to_dict()
    current = opened.tree.currentItem()
    parts, views = list(opened.viewer.parts), list(opened.viewer.views)
    opened.position_edits[0].setText("x0 + rozepsano")
    for dock in (opened.tree_dock, opened.component_dock, opened.checks_dock):
        dock.toggleViewAction().trigger()
    opened.files_action.setChecked(True)
    assert not opened.tree.isColumnHidden(1)
    opened.tree.setColumnWidth(0, 30)
    opened.reset_layout_action.trigger()
    app.processEvents()
    assert opened.tree_dock.isVisible() and opened.component_dock.isVisible()
    assert opened.checks_dock.isHidden() and opened.tree.isColumnHidden(1)
    assert opened.tree.columnWidth(0) >= 140
    assert opened.position_edits[0].text() == "x0 + rozepsano"
    assert opened.session.assembly.to_dict() == document and not opened.session.can_undo
    assert opened._selected == ("nozicka_1",) and opened.tree.currentItem() is current
    assert opened.viewer.parts == parts and opened.viewer.views == views


def test_check_command_reopens_panel_and_layout_reset_preserves_results(opened, app):
    before = opened.session.assembly.to_dict()
    opened.checks_dock.close()
    opened.check_action.trigger()
    app.processEvents()
    assert opened.checks_dock.isVisible() and opened.check_tabs.currentIndex() == 0
    result = opened.session.last_check()
    assert result is not None
    opened.reset_layout_action.trigger()
    assert opened.checks_dock.isHidden() and opened.session.last_check() == result
    assert opened.session.assembly.to_dict() == before and not opened.session.can_undo


def test_packaged_panel_check_uses_actual_window_size_when_desktop_caps_width(opened,
                                                                            monkeypatch):
    from skodacad.gui.app import _self_test_assembly_layout

    opened.setMaximumWidth(1028)  # stejné omezení jako na Windows runneru
    monkeypatch.setattr(opened.viewer, "ready", False, raising=False)
    lines = []
    assert _self_test_assembly_layout(opened, lines), "\n".join(lines)
    assert "skutečném okně 1028/1024" in lines[-1]
    assert "panely a mezery ≤580" in lines[-1]


def test_standard_views_share_toolbar_and_menu_actions_without_model_changes(opened, app):
    from skodacad.gui.viewer_views import VIEW_LABELS

    pick(opened, "vicko")
    before = opened.session.assembly.to_dict()
    result, selected = opened.session.result, opened._selected
    parts, highlight = list(opened.viewer.parts), list(opened.viewer.highlighted)
    opened.position_edits[0].setText("rozepsaný výraz")
    for action, label in ((opened.open_action, "Otevřít"),
                          (opened.constraint_action, "Vazba"),
                          (opened.check_action, "Kontrola")):
        assert opened.toolbar.widgetForAction(action).text() == label
        assert action.toolTip() == action.text()
    for key, (label, shortcut) in VIEW_LABELS.items():
        view = opened.view_actions[key]
        assert view.text() == label and view.shortcut().toString() == shortcut
        view.trigger()
        assert opened.viewer.views[-1] == key
    # Windows offscreen používá náhradní stejně široké znaky (lišta 1313 bodů).
    # Skutečné šířky 1024/960 ověřuje nativní self-test, zde funkci stejných akcí.
    opened.resize(max(1200, opened.toolbar.sizeHint().width()), 720)
    app.processEvents()
    for key in ("top", "front", "iso"):
        button = opened.toolbar.widgetForAction(opened.view_actions[key])
        assert button.isVisible(), (key, opened.width(), opened.toolbar.sizeHint().width())
        assert button.defaultAction() is opened.view_actions[key]
        assert opened.toolbar.rect().contains(button.geometry())
        button.click()
        assert opened.viewer.views[-1] == key
    fit = opened.toolbar.widgetForAction(opened.fit_action)
    assert fit.isVisible() and opened.fit_action.shortcut().toString() == "F"
    assert opened.toolbar.rect().contains(fit.geometry())
    fit.click()
    assert opened.viewer.views[-1] == "fit"
    assert opened.session.assembly.to_dict() == before and not opened.session.can_undo
    assert opened.session.result.volume_mm3 == pytest.approx(result.volume_mm3)
    assert opened._selected == selected
    assert opened.viewer.parts == parts and opened.viewer.highlighted == highlight
    assert opened.position_edits[0].text() == "rozepsaný výraz"


def test_view_shortcuts_do_not_steal_characters_from_position_input(opened, app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    pick(opened, "vicko")
    opened.raise_()
    opened.activateWindow()
    field = opened.position_edits[0]
    field.setFocus()
    field.selectAll()
    app.processEvents()
    QTest.keyClicks(field, "107FIHT")
    assert field.text() == "107FIHT" and opened.viewer.views == []
    assert opened._isolated is None
    assert not opened._visibility
    assert not opened._transparency
    assert not opened.session.can_undo
    opened.viewer.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    opened.viewer.setFocus()
    app.processEvents()
    for key, view in ((Qt.Key.Key_7, "top"), (Qt.Key.Key_1, "front"),
                      (Qt.Key.Key_0, "iso"), (Qt.Key.Key_F, "fit")):
        QTest.keyClick(opened.viewer, key)
        assert opened.viewer.views[-1] == view
    QTest.keyClick(opened.viewer, Qt.Key.Key_I)
    assert opened._isolated == ("vicko",)
    QTest.keyClick(opened.viewer, Qt.Key.Key_I,
                   Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert opened._isolated is None
    QTest.keyClick(opened.viewer, Qt.Key.Key_H)
    assert len(opened.visible_instances()) == 5
    QTest.keyClick(opened.viewer, Qt.Key.Key_H)
    assert len(opened.visible_instances()) == 6
    QTest.keyClick(opened.viewer, Qt.Key.Key_T)
    assert opened._is_transparent(("vicko",))
    QTest.keyClick(opened.viewer, Qt.Key.Key_T)
    assert not opened._transparency
    assert field.text() == "107FIHT" and not opened.session.can_undo


def test_isolation_preserves_pending_fields_model_history_and_restores_all(opened):
    assert not opened.isolate_action.isEnabled()
    assert not opened.restore_visibility_action.isEnabled()
    pick(opened, "vicko")
    result = opened.session.result
    lid = next(i for i in result.instances if i.ids == ("vicko",))
    before = opened.session.assembly.to_dict()
    history = (opened.session.can_undo, opened.session.can_redo, opened.session.dirty)
    opened.position_edits[0].setText("rozepsaný výraz")
    opened.isolate_action.trigger()
    assert opened._isolated == lid.ids and opened._selected == lid.ids
    shown, fit = opened.viewer.parts[-1]
    assert fit and len(shown.solids()) == 1
    assert shown.volume == pytest.approx(lid.volume_mm3)
    assert opened.position_edits[0].text() == "rozepsaný výraz"
    assert "izolace (1/6)" in opened.windowTitle()
    assert "Součty níže platí pro celou sestavu" in opened.summary.text()
    opened.fit_action.trigger()
    assert opened.viewer.views[-1] == "fit"
    opened.restore_visibility_action.trigger()
    shown, fit = opened.viewer.parts[-1]
    assert opened._isolated is None and fit and len(shown.solids()) == 6
    assert shown.volume == pytest.approx(result.volume_mm3)
    assert opened._selected == lid.ids
    assert opened.position_edits[0].text() == "rozepsaný výraz"
    assert opened.session.assembly.to_dict() == before
    assert history == (opened.session.can_undo, opened.session.can_redo, opened.session.dirty)


@pytest.fixture
def nested_isolation(main_window, tmp_path):
    from test_assembly import assembly_data, component, part_data, write

    root = tmp_path / "nested"
    write(root / "dily/deska.json", part_data())
    write(root / "modul.json", assembly_data([
        component("deska", "dily/deska.json"),
        component("druha", "dily/deska.json", position=(40, 0, 0))]))
    source = write(root / "sestava.json", assembly_data([
        component("a", "modul.json", position=(100, 0, 0), rotation=(0, 0, 90)),
        component("b", "modul.json", position=(0, 80, 20))]))
    return main_window.open_assembly(source)


def test_nested_isolation_uses_instance_path_and_hidden_picks_do_not_select(nested_isolation):
    w = nested_isolation
    w.select(("a", "deska"))
    w.isolate_selected()
    assert [i.ids for i in w.visible_instances()] == [("a", "deska")]
    assert w.viewer.parts[-1][0].volume == pytest.approx(6000)
    assert tuple(w.viewer.parts[-1][0].bounding_box().min) == pytest.approx((80, 0, 0))
    hidden = next(i for i in w.session.result.instances if i.ids == ("b", "deska"))
    face = max(hidden.part.faces(), key=lambda f: f.center().Z)
    w.viewer.selection_changed.emit([face.wrapped])
    assert w._selected == ("a", "deska")
    assert not w._picks
    w.select(("b",))  # strom zůstává celý; samotný výběr neodkryje skryté těleso
    assert w._isolated == ("a", "deska") and not w.viewer.highlighted
    assert len(w.viewer.parts[-1][0].solids()) == 1
    w.isolate_selected()
    assert [i.ids for i in w.visible_instances()] == [("b", "deska"), ("b", "druha")]
    assert w.viewer.parts[-1][0].volume == pytest.approx(12000)
    assert len(w.viewer.parts[-1][0].solids()) == 2
    assert not w._picks and not w.constraint_action.isEnabled()
    w.show_all()
    assert len(w.visible_instances()) == 4 and w.session.result.volume_mm3 == pytest.approx(24000)


def test_isolation_save_and_step_export_keep_full_assembly(opened, tmp_path, dialogs):
    from build123d import import_step

    pick(opened, "vicko")
    opened.isolate_selected()
    total = opened.session.result.volume_mm3
    target = tmp_path / "kopie.json"
    dialogs["save"] = str(target)
    assert opened.save_as() and opened._isolated == ("vicko",)
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert len(saved["components"]) == 6 and "isolation" not in saved
    step = tmp_path / "cela.step"
    opened.session.export_step(step)
    exported = import_step(step)
    assert len(exported.solids()) == 6 and exported.volume == pytest.approx(total)
    assert opened.open_assembly(target)
    assert opened._isolated is None and len(opened.viewer.parts[-1][0].solids()) == 6


def test_isolation_survives_edit_undo_and_missing_source_then_removal_restores_all(opened, project):
    pick(opened, "vicko")
    opened.isolate_selected()
    opened.position_edits[0].setText("10")
    opened.apply_form()
    assert opened._isolated == ("vicko",) and len(opened.visible_instances()) == 1
    opened.undo()
    assert opened._isolated == ("vicko",)
    (project / "sestavy/dily/vicko.json").unlink()
    opened.reload()
    assert opened._isolated == ("vicko",) and not opened.visible_instances()
    assert opened.viewer.parts[-1][0] is None
    assert opened.restore_visibility_action.isEnabled()
    opened.remove_selected()
    assert opened._isolated is None and len(opened.visible_instances()) == 5


def test_isolation_keeps_constraint_and_collision_overlays_from_revealing_hidden_parts(opened):
    pick(opened, "vicko")
    opened.isolate_selected()
    opened._finding = {"kind": "collision", "a": ["vicko"], "b": ["krabicka"],
                       "center": [0, 0, 20]}
    opened._selected = None
    opened._refresh_highlight()
    assert opened.viewer.highlighted and opened.viewer.points is None
    opened._finding = None
    opened._constraint = "v1"
    opened._refresh_highlight()  # v izolaci se plochy vazby vůbec nevytvářejí
    assert not opened.viewer.highlighted


def test_restore_from_constraint_keeps_unfinished_distance_and_restores_faces(
        main_window, project):
    w = main_window.open_assembly(project / "sestavy/krabicka_s_vazbami.json")
    before = w.session.assembly.to_dict()
    pick(w, "vicko")
    w.isolate_selected()
    w.select_constraint("v1")
    w.constraint_value.setText("rozepsaná vzdálenost")
    assert not w.viewer.highlighted and w.constraint_isolation_note.isVisible()
    w.show_all()
    assert len(w.viewer.highlighted) == 2 and not w.constraint_isolation_note.isVisible()
    assert w.constraint_value.text() == "rozepsaná vzdálenost"
    assert w.session.assembly.to_dict() == before and not w.session.can_undo


def visibility_row(window, ids):
    def walk(item):
        if item.data(0, 256) == json.dumps(list(ids)):
            return item
        for n in range(item.childCount()):
            found = walk(item.child(n))
            if found is not None:
                return found
        return None

    for n in range(window.tree.topLevelItemCount()):
        found = walk(window.tree.topLevelItem(n))
        if found is not None:
            return found
    raise AssertionError(ids)


def test_hide_show_preserve_pending_fields_selection_history_and_clear_hidden_picks(opened):
    from PySide6.QtCore import Qt

    w = opened
    pick(w, "vicko")
    before = w.session.assembly.to_dict()
    history = (len(w.session._undo), len(w.session._redo), w.session.dirty)
    lid = next(i for i in w.session.result.instances if i.ids == ("vicko",))
    w.position_edits[0].setText("rozepsaná poloha")
    w.visibility_action.trigger()
    shown, fit = w.viewer.parts[-1]
    assert not fit and len(shown.solids()) == 5
    assert shown.volume == pytest.approx(w.session.result.volume_mm3 - lid.volume_mm3)
    assert visibility_row(w, lid.ids).checkState(0) == Qt.CheckState.Unchecked
    assert w.visibility_action.iconText() == "Zobrazit"
    assert w.restore_visibility_action.isEnabled()
    assert "viditelné díly (5/6)" in w.windowTitle()
    assert w.position_edits[0].text() == "rozepsaná poloha" and w._selected == lid.ids
    face = max(lid.part.faces(), key=lambda f: f.center().Z)
    w.viewer.selection_changed.emit([face.wrapped, face.wrapped])
    assert not w._picks and not w.constraint_action.isEnabled()
    assert not w.viewer.highlighted
    w.visibility_action.trigger()
    assert not w._visibility and len(w.viewer.parts[-1][0].solids()) == 6
    assert w.position_edits[0].text() == "rozepsaná poloha"
    assert w.session.assembly.to_dict() == before
    assert history == (len(w.session._undo), len(w.session._redo), w.session.dirty)


def test_nested_checkboxes_show_child_of_hidden_parent_without_other_copies(nested_isolation, app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    w = nested_isolation
    parent = visibility_row(w, ("a",))
    child = visibility_row(w, ("a", "deska"))
    parent.setCheckState(0, Qt.CheckState.Unchecked)
    assert {i.ids for i in w.visible_instances()} == {("b", "deska"), ("b", "druha")}
    assert child.checkState(0) == Qt.CheckState.Unchecked
    assert visibility_row(w, ("b",)).checkState(0) == Qt.CheckState.Checked
    w.tree.setCurrentItem(child)
    w.tree.setFocus()
    app.processEvents()
    QTest.keyClick(w.tree, Qt.Key.Key_Space)
    assert child.checkState(0) == Qt.CheckState.Checked
    assert parent.checkState(0) == Qt.CheckState.PartiallyChecked
    shown = w.viewer.parts[-1][0]
    assert len(shown.solids()) == 3 and shown.volume == pytest.approx(18000)
    assert "V pohledu: 1/2 dílů" in parent.toolTip(0)
    parent.setCheckState(0, Qt.CheckState.Checked)
    assert len(w.visible_instances()) == 4 and parent.checkState(0) == Qt.CheckState.Checked
    assert not w._visibility


def test_isolation_intersects_manual_visibility_and_exit_preserves_hidden_parts(opened):
    w = opened
    w.set_component_visible(("nozicka_1",), False)
    pick(w, "vicko")
    w.isolate_selected()
    assert len(w.visible_instances()) == 1 and w.end_isolation_action.isEnabled()
    w.end_isolation_action.trigger()
    assert w._isolated is None and len(w.visible_instances()) == 5
    assert w._visibility == {("nozicka_1",): False}
    w.isolate_selected()
    w.toggle_selected_visibility()
    assert w._isolated == ("vicko",) and not w.visible_instances()
    assert w.viewer.parts[-1][0] is None and not w.isolate_action.isEnabled()
    assert w.end_isolation_action.isEnabled() and w.restore_visibility_action.isEnabled()
    w.show_all()
    assert not w._visibility and w._isolated is None and len(w.visible_instances()) == 6


def test_hidden_child_stays_hidden_when_isolating_parent(nested_isolation):
    w = nested_isolation
    w.set_component_visible(("a", "deska"), False)
    w.select(("a",))
    w.isolate_selected()
    assert [i.ids for i in w.visible_instances()] == [("a", "druha")]
    assert w.viewer.parts[-1][0].volume == pytest.approx(6000)
    w.end_isolation()
    assert len(w.visible_instances()) == 3
    w.select(("a", "deska"))
    assert not w.isolate_action.isEnabled() and w.visibility_action.isEnabled()
    w.toggle_selected_visibility()
    assert w.isolate_action.isEnabled() and len(w.visible_instances()) == 4


def test_manual_visibility_survives_rebuild_new_children_and_save_but_not_removal_or_open(
        nested_isolation, dialogs, tmp_path):
    from test_assembly import component, write

    w = nested_isolation
    w.set_component_visible(("a",), False)
    source = w.session.path.parent / "modul.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    data["components"].append(component("treti", "dily/deska.json", position=(80, 0, 0)))
    write(source, data)
    w.reload()
    assert {i.ids for i in w.visible_instances()} == {
        ("b", "deska"), ("b", "druha"), ("b", "treti")}
    target = tmp_path / "kopie.json"
    dialogs["save"] = str(target)
    assert w.save_as() and w._visibility == {("a",): False}
    w.select(("a",))
    w.remove_selected()
    assert not w._visibility and len(w.visible_instances()) == 3
    w.undo()
    assert len(w.visible_instances()) == 6
    w.set_component_visible(("a",), False)
    assert w.save()
    assert w.open_assembly(target)
    assert not w._visibility and len(w.visible_instances()) == 6


def test_hidden_parts_remain_in_saved_recipe_step_and_constraint_values(opened, project, tmp_path):
    from build123d import import_step

    w = opened
    w.set_component_visible(("krabicka",), False)
    w.set_component_transparent(("vicko",), True)
    total = w.session.result.volume_mm3
    saved = tmp_path / "cele.json"
    w.session.save(saved)
    assert len(json.loads(saved.read_text(encoding="utf-8"))["components"]) == 6
    assert json.loads(saved.read_text(encoding="utf-8")) == w.session.assembly.to_dict()
    step = tmp_path / "cele.step"
    w.session.export_step(step)
    shape = import_step(step)
    assert len(shape.solids()) == 6 and shape.volume == pytest.approx(total)
    assert len(w.visible_instances()) == 5
    assert w.open_assembly(project / "sestavy/krabicka_s_vazbami.json")
    w.set_component_visible(("krabicka",), False)
    w.select_constraint("v1")
    w.constraint_value.setText("rozepsaná vazba")
    w.set_component_transparent(("vicko",), True)
    w.reset_transparency_action.trigger()
    assert not w.viewer.highlighted and w.constraint_isolation_note.isVisible()
    w.show_all()
    assert len(w.viewer.highlighted) == 2 and not w.constraint_isolation_note.isVisible()
    assert w.constraint_value.text() == "rozepsaná vazba"


def transparent_ids(window):
    return {i.ids for i in window.visible_instances() if any(
        p.wrapped.IsSame(i.part.wrapped) for p in window.viewer.transparent_parts)}


def test_transparency_controls_preserve_picks_pending_fields_geometry_and_history(opened):
    from PySide6.QtCore import Qt

    w = opened
    assert not w.transparency_action.isEnabled() and not w.transparency_box.isEnabled()
    pick(w, "vicko")
    lid = next(i for i in w.session.result.instances if i.ids == ("vicko",))
    face = max(lid.part.faces(), key=lambda f: f.center().Z)
    w.viewer.selection_changed.emit([face.wrapped])
    w.position_edits[0].setText("rozepsaná poloha")
    before = w.session.assembly.to_dict()
    history = (len(w.session._undo), len(w.session._redo), w.session.dirty)
    geometry = list(w.viewer.parts)
    picks = list(w._picks)
    w.transparency_action.trigger()
    assert transparent_ids(w) == {("vicko",)}
    assert w.transparency_action.isChecked() and w.transparency_box.isChecked()
    assert w.transparency_box.checkState() == Qt.CheckState.Checked
    assert visibility_row(w, lid.ids).font(0).italic()
    assert "Průhlednost: 70 %" in visibility_row(w, lid.ids).toolTip(0)
    assert "Průhledné díly: 1/6" in w.summary.text()
    assert w.reset_transparency_action.isEnabled()
    assert w.viewer.parts == geometry and w._picks == picks
    assert w._selected == lid.ids and w.position_edits[0].text() == "rozepsaná poloha"
    w.transparency_box.click()
    assert not w._transparency and not w.viewer.transparent_parts
    assert not w.transparency_action.isChecked() and not w.reset_transparency_action.isEnabled()
    assert not visibility_row(w, lid.ids).font(0).italic()
    assert w.viewer.parts[-1][0].volume == pytest.approx(w.session.result.volume_mm3)
    assert w.session.assembly.to_dict() == before
    assert history == (len(w.session._undo), len(w.session._redo), w.session.dirty)
    assert w._picks == picks and w.position_edits[0].text() == "rozepsaná poloha"


def test_nested_transparency_is_independent_and_mixed_parent_toggle_sets_whole_branch(
        nested_isolation):
    from PySide6.QtCore import Qt

    w = nested_isolation
    w.set_component_transparent(("a",), True)
    assert transparent_ids(w) == {("a", "deska"), ("a", "druha")}
    assert sum(p.volume for p in w.viewer.transparent_parts) == pytest.approx(12000)
    w.set_component_transparent(("a", "deska"), False)
    w.select(("a",))
    assert w.transparency_box.checkState() == Qt.CheckState.PartiallyChecked
    assert not w.transparency_action.isChecked()
    assert "jen některé díly" in visibility_row(w, ("a",)).toolTip(0)
    assert not visibility_row(w, ("b",)).font(0).italic()
    w.transparency_box.click()
    assert w.transparency_box.checkState() == Qt.CheckState.Checked
    assert w._transparency == {("a",): True}
    assert transparent_ids(w) == {("a", "deska"), ("a", "druha")}
    w.transparency_action.trigger()
    assert not w._transparency and not w.viewer.transparent_parts
    assert len(w.viewer.parts[-1][0].solids()) == 4
    assert w.viewer.parts[-1][0].volume == pytest.approx(24000)


def test_transparency_survives_hiding_and_isolation_and_reset_does_not_change_filters(
        nested_isolation):
    w = nested_isolation
    w.set_component_transparent(("a",), True)
    w.set_component_visible(("a", "deska"), False)
    assert transparent_ids(w) == {("a", "druha")}
    w.select(("b",))
    w.isolate_selected()
    assert not w.viewer.transparent_parts and w._transparency == {("a",): True}
    w.show_all()
    assert transparent_ids(w) == {("a", "deska"), ("a", "druha")}
    w.set_component_visible(("b",), False)
    w.select(("a",))
    w.isolate_selected()
    shown = list(w.viewer.parts)
    w.reset_transparency_action.trigger()
    assert not w._transparency and not w.viewer.transparent_parts
    assert w._isolated == ("a",) and w._visibility == {("b",): False}
    assert w.viewer.parts == shown and len(w.visible_instances()) == 2
    w.set_component_visible(("a",), False)
    w.set_component_transparent(("a",), True)  # i zcela skrytá větev může mít připravený vzhled
    assert w.viewer.parts[-1][0] is None and not w.viewer.transparent_parts
    w.show_all()
    assert transparent_ids(w) == {("a", "deska"), ("a", "druha")}


def test_transparency_lifetime_rebuild_save_remove_undo_cancel_failed_and_successful_open(
        nested_isolation, dialogs, tmp_path):
    from test_assembly import component, write

    w = nested_isolation
    w.set_component_transparent(("a",), True)
    source = w.session.path.parent / "modul.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    data["components"].append(component("treti", "dily/deska.json", position=(80, 0, 0)))
    write(source, data)
    w.reload()
    assert transparent_ids(w) == {("a", "deska"), ("a", "druha"), ("a", "treti")}
    target = tmp_path / "pruhledna-kopie.json"
    dialogs["save"] = str(target)
    assert w.save_as() and w._transparency == {("a",): True}
    assert json.loads(target.read_text(encoding="utf-8")) == w.session.assembly.to_dict()
    w.select(("a",))
    w.remove_selected()
    assert not w._transparency
    w.undo()
    assert not w.viewer.transparent_parts and len(w.visible_instances()) == 6
    w.set_component_transparent(("a",), True)
    assert not w.open_assembly(target)  # rozpracovaná změna, zrušené potvrzení
    assert w._transparency == {("a",): True}
    w.session.dirty = False
    assert not w.open_assembly(tmp_path / "chybi.json")
    assert w._transparency == {("a",): True}
    assert w.open_assembly(target) and not w._transparency and not w.viewer.transparent_parts
    w.set_component_transparent(("a",), True)
    assert w.new_assembly(tmp_path / "nova.json") and not w._transparency


def test_bad_expression_in_form_is_czech_error_and_nothing_changes(opened, dialogs):
    pick(opened, "vicko")
    opened.position_edits[2].setText("H + neznamy")
    opened.apply_form()
    assert opened.session.result.status("vicko").state == "error"
    assert "neznamy" in opened.session.result.status("vicko").reason
    opened.position_edits[2].setText("")
    opened.apply_form()
    assert dialogs["shown"][-1][0] == "Polohu nejde použít"


def test_turn_buttons_and_fixed_box(opened, dialogs):
    pick(opened, "nozicka_2")
    [button for button in opened.turn_buttons if button.text() == "X +90°"][0].click()
    assert opened.session.assembly.component("nozicka_2").rotation == [90, 0, 0]
    opened.fixed_box.setChecked(True)
    assert opened.session.assembly.component("nozicka_2").fixed
    assert "Nožička 2 (pevná)" in [name for name, _ in items(opened)]
    pick(opened, "vicko")
    opened.position_edits[0].setText("x0")
    opened.apply_form()
    assert opened.session.assembly.component("vicko").position[0] == "x0"
    pick(opened, "krabicka")
    opened.session.rebuild()
    assert opened.fixed_box.isChecked()


def test_missing_part_is_marked_and_relink_asks_before_other_recipe(opened, project, dialogs):
    assert opened.save()  # zapíše otisky dílů – podle nich se pozná jiný recept
    (project / "sestavy" / "dily" / "vicko.json").rename(project / "jinde.json")
    press(opened, "Načíst díly znovu")
    assert ("Víčko", "✕ chybí") in items(opened)
    assert "NEÚPLNÁ" in opened.summary.text()
    other = project / "sestavy" / "dily" / "nozicka.json"
    opened.relink("vicko", other)  # jiný recept → otázka → Zrušit
    assert opened.session.assembly.component("vicko").path == "dily/vicko.json"
    assert "Jiný díl?" in dialogs["shown"]
    assert opened.relink("vicko", project / "jinde.json")
    assert opened.session.assembly.component("vicko").path == "../jinde.json"
    assert opened.session.result.complete


def test_insert_remove_and_pick_in_3d(opened, project, dialogs):
    new = opened.insert(project / "sestavy" / "dily" / "nozicka.json")
    assert new == "nozicka_5" and opened._selected == ("nozicka_5",)
    assert len(items(opened)) == 7
    instance = opened.session.result.instances[1]
    opened.viewer.selection_changed.emit([instance.part.faces()[0].wrapped])
    assert opened._selected == ("vicko",)
    pick(opened, "nozicka_5")
    press(opened, "Smazat komponentu")
    assert len(items(opened)) == 6 and opened._selected is None
    dialogs["open"] = str(project / "sestavy" / "dily" / "nozicka.json")
    press(opened, "Vložit díl…")
    assert len(items(opened)) == 7
    dialogs["open"] = str(project / "sestavy" / "krabicka_s_vickem.json")
    press(opened, "Vložit díl…")
    assert dialogs["shown"][-1][0] == "Díl nejde vložit"


def test_open_part_switches_main_window_to_the_part_file(main_window, opened, project):
    pick(opened, "vicko")
    opened.open_part_button.click()
    assert main_window.session.path == (project / "sestavy" / "dily" / "vicko.json").resolve() \
        or main_window.session.path == project / "sestavy" / "dily" / "vicko.json"
    assert main_window.session.document.name == "Víčko krabičky"


def test_new_assembly_and_file_actions(main_window, tmp_path, project, dialogs):
    dialogs["save"] = ""
    assert main_window.new_assembly_dialog() is None  # zrušeno → žádné okno
    dialogs["save"] = str(tmp_path / "moje")
    window = main_window.new_assembly_dialog()
    assert window is not None and (tmp_path / "moje.json").is_file()
    assert window.session.assembly.name == "moje" and items(window) == []
    window.insert(project / "sestavy" / "dily" / "nozicka.json")
    assert window.session.assembly.components[0].fixed
    press(window, "Uložit")
    saved = json.loads((tmp_path / "moje.json").read_text(encoding="utf-8"))
    assert saved["components"][0]["source"]["path"] == "projekt/sestavy/dily/nozicka.json"
    dialogs["save"] = str(tmp_path / "kopie.json")
    press(window, "Uložit jako…")
    assert (tmp_path / "kopie.json").is_file() and window.session.path.name == "kopie.json"
    dialogs["open"] = str(project / "sestavy" / "krabicka_s_vickem.json")
    press(window, "Otevřít sestavu…")
    assert len(items(window)) == 6
    dialogs["save"] = ""
    press(window, "Nová sestava…")
    assert len(items(window)) == 6  # zrušeno – sestava zůstala


def test_example_assembly_is_a_template_and_example_stays_untouched(main_window, examples_dir,
                                                                     tmp_path, dialogs):
    sample = examples_dir / "sestavy" / "krabicka_s_vickem.json"
    original = sample.read_bytes()
    press(main_window, "krabicka_s_vickem")
    window = main_window.assembly_windows[-1]
    pick(window, "vicko")
    window.position_edits[2].setText("40")
    window.apply_form()
    dialogs["save"] = str(tmp_path / "moje_krabicka.json")
    press(window, "Uložit")  # ukázka = Uložit se zeptá kam
    assert sample.read_bytes() == original
    saved = json.loads((tmp_path / "moje_krabicka.json").read_text(encoding="utf-8"))
    assert saved["components"][1]["placement"]["position"][2] == 40
    # Díly ukázky se zkopírovaly k sestavě – projekt nezávisí na složce ukázek ani disku
    # (na Windows jsou ukázky na jiném disku než uživatelská složka).
    assert [c["source"]["path"] for c in saved["components"]] == [
        "dily/krabicka.json", "dily/vicko.json", *["dily/nozicka.json"] * 4]
    assert (tmp_path / "dily" / "vicko.json").read_bytes() == \
        (examples_dir / "sestavy" / "dily" / "vicko.json").read_bytes()
    reopened = main_window.open_assembly(tmp_path / "moje_krabicka.json")
    assert reopened.session.result.complete and not reopened.session.result.warnings


def test_closing_with_unsaved_changes_asks(opened, dialogs):
    pick(opened, "vicko")
    opened.turn("z", 90)
    dialogs["question"] = QMessageBox.StandardButton.Cancel
    assert not opened.close()
    dialogs["question"] = QMessageBox.StandardButton.Discard
    press(opened, "Zavřít sestavu")
    assert not opened.isVisible()


def test_parse_value():
    assert parse_value("12") == 12 and parse_value("2,5") == 2.5 and parse_value("H/2") == "H/2"
    with pytest.raises(ValueError):
        parse_value("  ")


def test_background_runner_computes_parts_without_blocking(app, project, dialogs):
    from PySide6.QtTest import QTest

    from skodacad.worker import BackgroundRebuilder

    runner = BackgroundRebuilder()
    window = AssemblyWindow(FakeViewer, runner=runner)
    try:
        assert window.open_assembly(project / "sestavy" / "krabicka_s_vickem.json")
        assert {state for _name, state in items(window)} == {"… počítá se"}
        assert "Počítám díly sestavy na pozadí" in window.summary.text()
        for _ in range(1200):
            if not window.computing:
                break
            QTest.qWait(100)
        assert not window.computing
        assert window.session.result.complete and len(window.session.result.instances) == 6
        assert window.session.result.volume_mm3 == pytest.approx(31309.287, abs=0.01)
    finally:
        window.session.dirty = False
        window.close()
        runner.close()


# --- P5.3B: vazby v okně (B20) ---------------------------------------------------------


@pytest.fixture
def constrained(main_window, project):
    window = main_window.open_assembly(project / "sestavy" / "krabicka_s_vazbami.json")
    assert window is not None and window.session.result.complete
    return window


def pick_constraint(window, constraint_id):
    for index in range(window.tree.topLevelItemCount()):
        group = window.tree.topLevelItem(index)
        for child in range(group.childCount()):
            item = group.child(child)
            if item.data(0, 256) == json.dumps({"constraint": constraint_id}):
                window.tree.setCurrentItem(item)
                return
    raise AssertionError(constraint_id)


def plane_face(window, component, normal_z, z):
    instance = next(i for i in window.session.result.instances if i.ids == (component,))
    return next(f for f in instance.part.faces() if f.geom_type.name == "PLANE"
                and abs(f.normal_at().Z - normal_z) < 1e-9 and abs(f.center().Z - z) < 1e-9)


def click(window, face, point, add=False):
    """Klik (s Ctrl ``add``) ve 3D jako skutečný prohlížeč: místo kliknutí + výběr."""
    window.viewer.picked_point = point
    shapes = [shape for shape, _at in window._picks] if add else []
    window.viewer.selection_changed.emit([*shapes, face.wrapped])


def test_b20_constraints_in_tree_add_by_two_clicks_edit_and_delete(constrained, dialogs,
                                                                   monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window = constrained
    rows = items(window)
    assert ("Víčko", "✓ plně určená") in rows
    assert ("Nožička 1", "✓ volná: 2 posuny, 1 otočení") in rows
    assert ("Vazby (7)", "") in rows and ("  Víčko na okraji", "✓") in rows
    assert "Vazby: 7, splněné 7" in window.summary.text()
    # Smazat vazbu: výběr ve stromu, Delete = jeden krok Zpět.
    pick_constraint(window, "v4")
    assert window.constraint_box.isVisibleTo(window) and window.viewer.highlighted
    assert "Dotyk: Krabička ↔ Nožička 1" in window.constraint_note.text()
    press(window, "Smazat vazbu")
    assert "v4" not in [c.id for c in window.session.assembly.constraints]
    assert ("Nožička 1", "✓") in items(window) and len(window.session._undo) == 1
    # Přidat vazbu: klik na dno krabičky, Ctrl+klik na horní plochu nožičky.
    asked = {}
    monkeypatch.setattr(QInputDialog, "getItem",
                        lambda *a, **k: asked.setdefault("item", a[3]) and ("vzdálenost", True))
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *a, **k: asked.setdefault("text", a[4]) and ("2", True))
    assert not window.constraint_action.isEnabled()
    click(window, plane_face(window, "krabicka", -1, 0), (-32, -17, 0))
    click(window, plane_face(window, "nozicka_1", 1, 0), (-32, -17, 0), add=True)
    assert window.constraint_action.isEnabled() and "Vybrané plochy: 2" in window.pick_note.text()
    press(window, "Přidat vazbu…")
    assert asked == {"item": ["dotyk", "zarovnání", "vzdálenost"], "text": "0"}
    new = window.session.assembly.constraints[-1]
    assert new.type == "distance" and new.value == 2 and window._constraint == new.id
    assert new.a == {"component": "krabicka", "face": {
        "at": [-32, -17, 0], "normal": [0, 0, -1], "type": "plane"}}
    assert new.b == {"component": "nozicka_1", "face": {
        "at": [0, 0, 3], "normal": [0, 0, 1], "type": "plane"}}
    assert window.session.assembly.component("nozicka_1").position == [-32, -17, -5]
    assert ("Nožička 1", "✓ volná: 2 posuny, 1 otočení") in items(window)
    assert len(window.session._undo) == 2
    # Upravit vzdálenost ve formuláři vazby = jeden krok Zpět.
    window.constraint_value.setText("1,5")
    window.constraint_name.setText("Nožička pod dnem")
    window.constraint_apply.click()
    assert window.session.assembly.component("nozicka_1").position == [-32, -17, -4.5]
    assert ("  Nožička pod dnem", "✓") in items(window) and len(window.session._undo) == 3
    for _ in range(3):
        press(window, "Zpět")
    assert len(window.session.assembly.constraints) == 7 and not window.session.can_undo


def test_constraint_edit_keeps_accessibility_model_indexes_alive(constrained):
    """macOS AX clients retain cell indexes while an edit refreshes the tree."""
    from PySide6.QtCore import QPersistentModelIndex

    window = constrained
    pick_constraint(window, "v1")
    index = QPersistentModelIndex(window.tree.currentIndex().siblingAtColumn(0))
    bill_cell = window.bill_table.item(0, 1)
    bill_name = bill_cell.text()
    group = window.tree.currentItem().parent()
    group.setExpanded(False)
    assert index.data() == "Víčko na okraji"
    window.constraint_value.setText("15")
    window.constraint_name.setText("Víčko nad krabičkou")
    window.constraint_apply.click()
    assert window.session.assembly.component("vicko").position == [0, 0, 47]
    assert index.isValid() and index.data() == "Víčko nad krabičkou"
    assert bill_cell.text() == bill_name
    assert not group.isExpanded()
    assert window.tree.currentIndex().siblingAtColumn(0) == index
    press(window, "Zpět")
    assert index.isValid() and index.data() == "Víčko na okraji"
    assert window.session.assembly.component("vicko").position == [0, 0, 32]
    # Removing a different constraint must not destroy this accessible cell either.
    pick_constraint(window, "v4")
    press(window, "Smazat vazbu")
    assert index.isValid() and index.data() == "Víčko na okraji"
    press(window, "Zpět")
    assert items(window).count(("  Nožička 1 na dně", "✓")) == 1
    assert index.isValid()


def test_constraint_errors_in_window_are_czech_dialogs(constrained, dialogs):
    window = constrained
    press(window, "Přidat vazbu…")  # bez výběru: tlačítko je vypnuté, akce nic neudělá
    window.add_constraint_dialog()
    assert dialogs["shown"][-1][0] == "Přidat vazbu"
    box = plane_face(window, "krabicka", -1, 0)
    click(window, box, (0, 0, 0))
    click(window, plane_face(window, "krabicka", 1, 2), (0, 0, 2), add=True)  # dno uvnitř
    window.add_constraint_dialog()
    assert dialogs["shown"][-1] == ("Vazbu nejde přidat", "Obě plochy patří ke stejné "
                                    "komponentě – druhou plochu vyber na jiné komponentě.")
    foot = next(i for i in window.session.result.instances if i.ids == ("nozicka_2",))
    side = next(f for f in foot.part.faces() if f.geom_type.name == "CYLINDER")
    click(window, box, (0, 0, 0))
    click(window, side, (37, -17, -1.5), add=True)
    window.add_constraint_dialog()
    assert "dvě rovinné plochy" in dialogs["shown"][-1][1]
    rim = {"component": "krabicka",
           "face": {"at": [0, 24, 30], "normal": [0, 0, 1], "type": "plane"}}
    ring = {"component": "vicko", "face": {"at": [0, 24, 2], "normal": [0, 0, 1],
                                           "type": "plane"}}
    assert window.add_constraint("distance", rim, ring, 5) is None
    assert dialogs["shown"][-1][0] == "Vazbu nejde přidat"
    assert "si odporují" in dialogs["shown"][-1][1] and not window.session.can_undo


def test_changed_part_moves_constrained_lid_and_window_says_so(constrained, project):
    box = json.loads((project / "krabicka.json").read_text(encoding="utf-8"))
    box["parameters"]["H"] = 40
    (project / "krabicka.json").write_text(json.dumps(box), encoding="utf-8")
    press(constrained, "Načíst díly znovu")
    assert constrained.session.assembly.component("vicko").position == [0, 0, 42]
    assert "po změně dílu přepočítaly" in constrained.summary.text()
    assert "*" in constrained.windowTitle()


# --- P5.4B: kontrola sestavy v okně (C20) ----------------------------------------------


@pytest.fixture
def screwed(main_window, project):
    window = main_window.open_assembly(project / "sestavy" / "deska_se_sroubem.json")
    assert window is not None and window.session.result.complete
    return window


def found(window):
    return [tuple(window.findings.item(row, column).text() for column in range(3))
            for row in range(window.findings.rowCount())]


def test_c20_check_accept_bill_and_step_in_window(screwed, dialogs, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QInputDialog

    from skodacad.assembly_check import NDT_NOTE
    from skodacad.gui.assembly_window import MARK

    window = screwed
    assert "neproběhla" in window.check_note.text() and NDT_NOTE in window.check_note.text()
    assert window.clearance_edit.text() == "0,3" and window.findings.rowCount() == 0
    press(window, "Zkontrolovat kolize a vůle")
    assert found(window) == [("Přijatá kolize", "Deska × Šroub M3 × 10", "12,959 mm³")]
    assert "Žádná nepřijatá kolize" in window.check_note.text()
    # Klik na nález: obě kopie zvýrazněné, kulička v těžišti průniku (osa šroubu).
    window.findings.selectRow(0)
    assert window._finding["kind"] == "accepted" and window.viewer.highlighted
    [center], [color] = window.viewer.points
    assert center == pytest.approx((0, 0, 3), abs=1e-6) and color == MARK
    assert window.unaccept_button.isEnabled() and not window.accept_button.isEnabled()
    window.unaccept_button.click()  # přijetí zrušené = kolize, jeden krok Zpět
    assert found(window)[0][0] == "Kolize" and len(window.session._undo) == 1
    assert "K řešení: 1" in window.check_note.text() and window.accept_button.isEnabled()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("závit M3", True))
    window.accept_button.click()
    assert found(window)[0][0] == "Přijatá kolize" and len(window.session._undo) == 2
    assert window.session.assembly.checks.accepted[0].note == "závit M3"
    # Mez vůle = krok Zpět; s jinou mezí výsledek neplatí, po Zpět zase ano (bez výpočtu).
    window.clearance_edit.setText("0,5")
    window.apply_clearance()
    assert window.session.assembly.checks.clearance == 0.5
    assert "po změně sestavy neplatí" in window.check_note.text() and not found(window)
    press(window, "Zpět")
    assert found(window)[0][0] == "Přijatá kolize"
    # Výběr komponenty ve stromu zruší výběr nálezu i kuličku.
    pick(window, "deska")
    assert window._finding is None and window.viewer.points is None
    # Kusovník a export STEP.
    window.check_tabs.setCurrentIndex(1)
    bill = [[window.bill_table.item(r, c).text() for c in (1, 3, 4)] for r in range(2)]
    assert bill == [["Deska se závitem M3", "1", "hliník"], ["Šroub M3 × 10 ISO 4762", "1", "ocel"]]
    assert "Řádků 2, kusů 2, hmotnost celkem 20,42 g" in window.bill_note.text()
    dialogs["save"] = str(tmp_path / "kusovnik")
    press(window, "Uložit kusovník CSV…")
    assert "Deska se závitem M3" in (tmp_path / "kusovnik.csv").read_text(encoding="utf-8-sig")
    dialogs["save"] = str(tmp_path / "sestava")
    press(window, "Exportovat STEP…")
    assert (tmp_path / "sestava.step").read_text(errors="replace").startswith("ISO-10303-21")


def test_c20_incomplete_assembly_refuses_check_bill_and_export(opened, project, dialogs):
    (project / "sestavy" / "dily" / "vicko.json").rename(project / "jinde.json")
    press(opened, "Načíst díly znovu")
    assert not opened.check_button.isEnabled() and not opened.export_action.isEnabled()
    assert not opened.bill_button.isEnabled() and "NEÚPLNÁ" in opened.bill_note.text()
    assert opened.bill_table.rowCount() == 2  # krabička a nožičky; víčko chybí
    for action in (opened.run_check, opened.save_bill_dialog, opened.export_dialog):
        action()
        assert "jen u úplné sestavy" in dialogs["shown"][-1][1] \
            or "jen z úplné sestavy" in dialogs["shown"][-1][1]


def test_c20_check_runs_in_background_and_change_meanwhile_discards_it(app, project, dialogs):
    from PySide6.QtTest import QTest

    from skodacad.worker import BackgroundRebuilder

    def wait(condition):
        for _ in range(1200):
            if condition():
                return
            QTest.qWait(100)
        raise AssertionError("výpočet na pozadí nedoběhl")

    runner = BackgroundRebuilder()
    window = AssemblyWindow(FakeViewer, runner=runner)
    try:
        assert window.open_assembly(project / "sestavy" / "deska_se_sroubem.json")
        wait(lambda: not window.computing)
        window.run_check()
        assert window.checking and window.stop_check_button.isVisibleTo(window)
        assert "na pozadí" in window.check_note.text() and not window.check_button.isEnabled()
        pick(window, "sroub_1")
        window.turn("z", 90)  # změna během kontroly – výsledek nesmí platit
        wait(lambda: not window.checking)
        assert "během kontroly změnila" in window.statusBar().currentMessage()
        assert window.findings.rowCount() == 0
        window.run_check()
        wait(lambda: not window.checking)
        assert found(window) == [("Přijatá kolize", "Deska × Šroub M3 × 10", "12,959 mm³")]
        window.run_check()
        window.stop_check()  # Zastavit: nic se nepřevezme, okno jde dál
        assert not window.checking and "Zastavena" not in window.check_note.text()
    finally:
        window.session.dirty = False
        window.close()
        runner.close()
