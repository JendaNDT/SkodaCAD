"""Přehledné záložky: rozepsané hodnoty a model se při navigaci nemění."""

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from test_assembly_gui import app, dialogs, main_window, opened, project  # noqa: F401
from test_line_rotation_axis import choose_line


def test_tabs_preserve_pending_values_geometry_history_and_preferences(request):
    w = request.getfixturevalue("opened")
    w.select(("nozicka_1",))
    fields = [w.name_edit, *w.position_edits, *w.move_edits,
              w.batch_rotation_angle, *w.rotation_center_edits]
    for index, field in enumerate(fields):
        field.setText(f"{index}+h")
    before, result = w.session.assembly.to_dict(), w.session.result
    token = w._move_token()
    texts = [f.text() for f in fields]
    handles = (w.move_handles.isChecked(), w.rotation_handles.isChecked())
    for index in (1, 0, 1, 0):
        w.movement_tabs.setCurrentIndex(index)
        w.placement_section.set_expanded(not w.placement_section.expanded)
        w.appearance_section.set_expanded(not w.appearance_section.expanded)
    assert [f.text() for f in fields] == texts
    assert w.session.assembly.to_dict() == before and w.session.result is result
    assert not w.session.can_undo and not w.session.dirty
    assert (w.move_handles.isChecked(), w.rotation_handles.isChecked()) == handles
    assert w._move_token() != token


def test_real_tab_clicks_show_one_page_and_use_its_height(request):
    w = request.getfixturevalue("opened")
    qt = request.getfixturevalue("app")
    w.select(("nozicka_1",))
    w.resize(1200, 800)
    w.show()
    qt.processEvents()
    assert w.movement_tabs.currentWidget() is w.move_box
    assert w.move_box.isVisibleTo(w) and not w.batch_rotation_box.isVisibleTo(w)
    assert not w.placement_section.expanded and not w.appearance_section.expanded
    move_height = w.movement_tabs.height()
    bar = w.movement_tabs.tabBar()
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(1).center())
    qt.processEvents()
    assert w.batch_rotation_box.isVisibleTo(w) and not w.move_box.isVisibleTo(w)
    assert w.movement_tabs.height() > move_height
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(0).center())
    qt.processEvents()
    assert w.movement_tabs.height() == move_height
    viewport = w.component_scroll.viewport()
    button_rect = w.move_button.rect().translated(
        w.move_button.mapTo(viewport, w.move_button.rect().topLeft()))
    assert viewport.rect().contains(button_rect)


def test_revealing_a_control_opens_its_tab_or_collapsed_section(request):
    w = request.getfixturevalue("opened")
    w.select(("nozicka_1",))
    w.component_scroll.ensureWidgetVisible(w.batch_rotation_axis)
    assert w.movement_tabs.currentWidget() is w.batch_rotation_box
    w.component_scroll.ensureWidgetVisible(w.position_edits[0])
    assert w.placement_section.expanded
    w.component_scroll.ensureWidgetVisible(w.transparency_percent)
    assert w.appearance_section.expanded
    assert not w.session.can_undo


def test_tab_change_rejects_old_move_and_rotation_even_after_returning(request):
    w = request.getfixturevalue("opened")
    w.select(("nozicka_1",))
    before = w.session.assembly.to_dict()
    move = {"token": w._move_token(), "delta": [5, 0, 0]}
    w.movement_tabs.setCurrentIndex(1)
    w.movement_tabs.setCurrentIndex(0)
    w.viewer.selection_moved.emit(move)
    w.rotation_handles.click()
    turn = {"token": w._rotation_token(), "axis": "z", "angle": 30}
    w.movement_tabs.setCurrentIndex(0)
    w.movement_tabs.setCurrentIndex(1)
    w.viewer.selection_rotated.emit(turn)
    assert w.session.assembly.to_dict() == before and not w.session.can_undo


def test_leaving_rotation_cancels_picker_and_old_reference_cannot_replace_new_pick(request):
    w = request.getfixturevalue("opened")
    w.select(("nozicka_1",))
    old = choose_line(w)
    w.movement_tabs.setCurrentIndex(0)
    assert w.viewer.center_pick is None and not w.rotation_axis_pick_button.isChecked()
    new = choose_line(w)
    w.viewer.rotation_center_picked.emit(old)
    assert w.viewer.center_pick["token"] == new["token"]
    assert w._rotation_line is None and not w.session.can_undo
