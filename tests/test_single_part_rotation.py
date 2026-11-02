"""Jediný díl používá stejnou osu, střed a potvrzení otočení jako celý výběr."""

import numpy as np
import pytest

from test_assembly_batch_rotation import rodrigues, vertices
from test_assembly_gui import (  # noqa: F401
    app,
    dialogs,
    main_window,
    nested_isolation,
    opened,
    project,
)
from test_cylinder_rotation_axis import choose_cylinder
from test_line_rotation_axis import choose_line
from test_plane_rotation_axis import choose_plane
from test_vertex_rotation_axis import choose_vertices


@pytest.mark.parametrize("axis", ["x", "y", "z", "cylinder", "line", "plane", "vertices"])
@pytest.mark.parametrize("mode", ["number", "mouse"])
def test_single_part_axis_rotates_geometry_with_one_undo_redo(request, axis, mode):
    w = request.getfixturevalue("opened")
    selected = ("nozicka_1",)
    w.select(selected)
    before = w.session.assembly.to_dict()
    old = {i.ids: vertices(i.part) for i in w.session.result.instances}
    w.component_scroll.ensureWidgetVisible(w.batch_rotation_axis)
    assert w.batch_rotation_box.isVisibleTo(w)
    assert w.batch_rotation_box.title() == "Otočení [°]"
    assert w.rotation_handles.isEnabled() and w.rotation_pick_button.isEnabled()
    w.rotation_handles.click()
    pickers = {"cylinder": choose_cylinder, "line": choose_line,
               "plane": choose_plane, "vertices": choose_vertices}
    if axis in pickers:
        payload = pickers[axis](w)
        w.viewer.rotation_center_picked.emit(payload)
        assert w.rotation_axis_reverse_button.isEnabled()
        w.rotation_axis_reverse_button.click()
    else:
        w.batch_rotation_axis.setCurrentText(axis.upper())
        w.rotation_center_mode.setCurrentIndex(2)
        for field, value in zip(w.rotation_center_edits, (12, -7, 3), strict=True):
            field.setText(str(value))
    center = np.array(w._chosen_rotation_center())
    q = rodrigues(w._chosen_rotation_axis(), 30)
    data = w.viewer.move_selection
    assert data["mode"] == "rotate" and len(data["shapes"]) == 1
    assert data["anchor"] == pytest.approx(center)
    assert w.session.assembly.to_dict() == before and not w.session.can_undo
    if mode == "number":
        w.batch_rotation_angle.setText("30")
        w.batch_rotation_button.click()
    else:
        w.viewer.selection_rotated.emit({"token": data["token"], "axis": axis, "angle": 30})
    assert len(w.session._undo) == 1 and w._selection == (selected,)
    for i in w.session.result.instances:
        expected = ((q @ (old[i.ids]-center).T).T+center if i.ids == selected else old[i.ids])
        assert all(min(np.linalg.norm(expected-p, axis=1)) < 1e-6 for p in vertices(i.part))
        assert i.part.is_valid
    moved = w.session.assembly.to_dict()
    w.undo_action.trigger()
    assert w.session.assembly.to_dict() == before and not w.session.can_undo
    w.redo_action.trigger()
    assert w.session.assembly.to_dict() == moved


def test_single_part_selection_changes_reject_old_drag_and_keep_restrictions(request):
    w = request.getfixturevalue("opened")
    nested = request.getfixturevalue("nested_isolation")
    w.select(("nozicka_1",))
    w.rotation_handles.click()
    old = {"token": w.viewer.move_selection["token"], "axis": "z", "angle": 30}
    for selection in (("nozicka_2",), ("krabicka",), None):
        if selection is None:
            w.clear_component_selection()
        else:
            w.select(selection)
        before = w.session.assembly.to_dict()
        w.viewer.selection_rotated.emit(old)
        assert w.session.assembly.to_dict() == before and not w.session.can_undo
        if selection != ("nozicka_2",):
            assert not w.rotation_handles.isEnabled()
            assert not w.batch_rotation_button.isEnabled()
            assert not w.rotation_axis_pick_button.isEnabled()
            assert not w.rotation_pick_button.isEnabled()
            assert w.viewer.move_selection is None
    assert not w.batch_rotation_box.isVisibleTo(w)
    nested.select(("a", "deska"))
    assert not nested.rotation_handles.isEnabled()
    assert not nested.batch_rotation_button.isEnabled()
