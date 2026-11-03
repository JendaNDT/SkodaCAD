"""Odkaz z pracovního editoru vybírá skutečné id a nikdy nepřijímá změnu modelu."""

import copy
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox

from skodacad.assembly_parameter_usage import UsageTarget, parameter_usage
from skodacad.gui.assembly_parameters import AssemblyParametersDialog
from test_assembly_gui import app, dialogs, main_window, opened, project  # noqa: F401
from test_assembly_parameter_usage import sample
from test_assembly_parameters import edit_cell
from test_line_rotation_axis import choose_line


def click_usage(dialog, kind, id_, column=0):
    row = dialog._usage_targets.index(UsageTarget(kind, id_))
    item = dialog.usage_table.item(row, column)
    dialog.usage_table.scrollToItem(item)
    QTest.mouseClick(dialog.usage_table.viewport(), Qt.MouseButton.LeftButton,
                     pos=dialog.usage_table.visualItemRect(item).center())
    return row


def test_targets_identify_records_with_duplicate_names_and_transitive_references(examples_dir):
    assembly = sample({"d": 10, "half": "d/2"}, position=("half", 0, 0))
    assembly.components[0].position[0] = "d"
    report = parameter_usage(assembly, assembly.parameters, "d")
    assert [use.target for use in report.uses] == [UsageTarget("parameter", "half"),
                                                UsageTarget("component", "a"),
                                                UsageTarget("component", "b")]
    from skodacad.assembly import Assembly

    assembly = Assembly.load(examples_dir / "sestavy/krabicka_s_vazbami.json")
    assert parameter_usage(assembly, assembly.parameters, "mezera").uses[0].target == (
        UsageTarget("constraint", "v1"))


def test_real_clicks_preserve_draft_rename_model_result_history_and_files(request):
    w = request.getfixturevalue("opened")
    assert w.open_assembly(w.session.path.parent / "krabicka_s_vazbami.json")
    w.session.set_placement("nozicka_1", position=["mezera-32", -17, -3])
    w._refresh()
    source, result = w.session.assembly, w.session.result
    before = source.to_dict()
    history = (len(w.session._undo), len(w.session._redo), w.session.dirty)
    files = {s.file: s.file.read_bytes() for s in result.statuses}
    w.show()
    seen = []

    def interact(dialog):
        dialog.show()
        QTest.qWait(30)
        edit_cell(dialog, 0, 0, "vule")
        edit_cell(dialog, 0, 1, "12,5")
        assert dialog._renames == [("mezera", "vule")]
        for column in range(4):
            click_usage(dialog, "component", "nozicka_1", column)
            assert w._selection == (("nozicka_1",),) and w._constraint is None
            assert w.viewer.highlighted
        w.tree.collapseAll()
        w.tree_dock.hide()
        click_usage(dialog, "constraint", "v1")
        assert w._constraint == "v1" and not w._selection and len(w.viewer.highlighted) == 2
        item = w.tree.currentItem()
        assert json.loads(item.data(0, Qt.ItemDataRole.UserRole)) == {"constraint": "v1"}
        assert item.parent().isExpanded() and w.tree_dock.isVisible()
        assert dialog.isVisible() and dialog.parameters() == {"vule": 12.5}
        assert "Vybráno:" in dialog.usage_navigation.text()
        assert w.session.assembly is source and w.session.result is result
        assert source.to_dict() == before
        assert (len(w.session._undo), len(w.session._redo), w.session.dirty) == history
        dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        seen.append(True)

    w._exec_dialog = interact
    QTest.mouseClick(w.parameters_button, Qt.MouseButton.LeftButton)
    assert seen == [True] and w._constraint == "v1"
    assert source.to_dict() == before and w.session.result is result
    assert all(path.read_bytes() == value for path, value in files.items())


@pytest.mark.parametrize("key", [None, Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_parameter_link_selects_working_row_without_dispatching_again(request, key):
    request.getfixturevalue("app")
    calls = []
    assembly = sample({"a": 10, "b": "a/2"}, position=("b", 0, 0))
    dialog = AssemblyParametersDialog(assembly.parameters, calls.append, assembly=assembly,
                                      select_usage=lambda target: calls.append(target))
    try:
        dialog.show()
        QTest.qWait(20)
        if key is None:
            click_usage(dialog, "parameter", "b")
        else:
            dialog.usage_table.setCurrentCell(0, 0)
            dialog.usage_table.setFocus()
            QTest.keyClick(dialog.usage_table, key)
        assert dialog.table.currentRow() == 1 and dialog.table.currentColumn() == 1
        assert "Parametr „b“" in dialog.usage_navigation.text()
        assert dialog.isVisible() and not calls
    finally:
        dialog.close()


def test_same_part_navigation_cancels_picker_and_rejects_old_motion(request):
    w = request.getfixturevalue("opened")
    w.select(("nozicka_1",))
    source = w.session.assembly
    move = {"token": w._move_token(), "delta": [5, 0, 0]}
    old = choose_line(w)
    assert w.viewer.center_pick is not None
    assert w.select_parameter_usage(UsageTarget("component", "nozicka_1"), source)
    assert w.viewer.center_pick is None and not w.rotation_axis_pick_button.isChecked()
    w.movement_tabs.setCurrentIndex(0)
    w.viewer.selection_moved.emit(move)
    w.viewer.rotation_center_picked.emit(old)
    assert not w.session.can_undo and w.session.assembly is source


@pytest.mark.parametrize("kind,id_", [("component", "nozicka_1"), ("constraint", "v1")])
def test_navigation_preserves_visibility_and_isolation(request, kind, id_):
    w = request.getfixturevalue("opened")
    assert w.open_assembly(w.session.path.parent / "krabicka_s_vazbami.json")
    w.select(("nozicka_1",))
    w.toggle_selected_visibility()
    w.select(("vicko",))
    w.isolate_selected()
    state = (copy.deepcopy(w._visibility), w._isolated, len(w.viewer.parts))
    assert w.select_parameter_usage(UsageTarget(kind, id_), w.session.assembly)
    assert (w._visibility, w._isolated, len(w.viewer.parts)) == state
    assert not w.viewer.highlighted and not w.session.can_undo


@pytest.mark.parametrize("target", [UsageTarget("component", "missing"),
                                  UsageTarget("constraint", "missing"),
                                  UsageTarget("parameter", "mezera")])
def test_unknown_and_stale_model_targets_do_not_touch_selection_or_picker(request, target):
    w = request.getfixturevalue("opened")
    w.select(("nozicka_1",))
    choose_line(w)
    source = w.session.assembly
    state = (w._selection, w._constraint, w._movement_panel_revision, w.viewer.center_pick)
    assert not w.select_parameter_usage(target, source)
    assert not w.select_parameter_usage(UsageTarget("component", "nozicka_1"),
                                         copy.deepcopy(source))
    assert (w._selection, w._constraint, w._movement_panel_revision, w.viewer.center_pick) == state


def test_missing_component_still_selects_tree_record(request):
    w = request.getfixturevalue("opened")
    w.session.assembly.component("nozicka_1").path = "missing.json"
    w.session.rebuild()
    w._refresh()
    assert w.select_parameter_usage(UsageTarget("component", "nozicka_1"), w.session.assembly)
    assert w._selection == (("nozicka_1",),) and w.tree.currentItem().isSelected()


def test_unavailable_usage_keeps_draft_and_explains_failure(request):
    request.getfixturevalue("app")
    assembly = sample({"a": 10}, position=("a", 0, 0))
    dialog = AssemblyParametersDialog(assembly.parameters, lambda _: None, assembly=assembly,
                                      select_usage=lambda _: False)
    try:
        dialog.show()
        QTest.qWait(20)
        click_usage(dialog, "component", "b")
        assert "není dostupné" in dialog.usage_navigation.text()
        assert dialog.parameters() == {"a": 10} and dialog.isVisible()
    finally:
        dialog.close()
