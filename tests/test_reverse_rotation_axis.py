"""P7.26: obrácení převzaté osy je preference; oba příkazy sdílejí nový směr."""

import numpy as np
import pytest

from skodacad.expressions import evaluate
from skodacad.gui.viewer import _rotation_pick_cylinder
from test_assembly_batch_move import assert_unchanged, snapshot
from test_assembly_batch_rotation import vertices
from test_assembly_gui import app, dialogs, main_window, opened, project  # noqa: F401
from test_cylinder_rotation_axis import choose_cylinder, independent_rotation
from test_line_rotation_axis import choose_line, prepare_window


def pick_axis(w, kind):
    payload = choose_line(w) if kind == "line" else choose_cylinder(w)
    if kind == "cylinder":
        payload["point"], payload["direction"] = _rotation_pick_cylinder(payload["shape"])
    w.viewer.rotation_center_picked.emit(payload)
    return payload


@pytest.mark.parametrize("kind", ["line", "cylinder"])
def test_two_clicks_preserve_anchor_selection_fields_result_and_redo(request, kind):
    w = prepare_window(request)
    w.batch_rotation_button.click()
    w.undo_action.trigger()
    w.rotation_handles.click()
    payload = pick_axis(w, kind)
    w.set_component_transparency(("nozicka_1",), 35)
    w.set_component_transparency(("nozicka_2",), 85)
    w.set_component_visible(("vicko",), False)
    w._picks = [(payload["shape"], (1, 2, 3))]
    w.viewer.picked_point = (1, 2, 3)
    fields = [*w.move_edits, *w.rotation_center_edits, w.batch_rotation_angle]
    for field, text in zip(fields, ["2,5", "h/2", "", "x0", "-7,25", "", "37,5"], strict=True):
        field.setText(text)
    w.rotation_step.setValue(7.5)
    before, selected, picks = snapshot(w.session), w._selection, list(w._picks)
    texts = [f.text() for f in fields]
    point, direction = w._picked_rotation_axis()
    visible = tuple(i.ids for i in w.visible_instances())
    alpha = list(w.viewer.transparencies)
    tokens = [w._rotation_token()]
    assert w.rotation_axis_reverse_button.isEnabled()
    for sign in (-1, 1):
        w.rotation_axis_reverse_button.click()
        tokens.append(w._rotation_token())
        assert w._picked_rotation_axis() == (point, tuple(sign*v for v in direction))
        assert w.viewer.move_selection["anchor"] == point
        assert w.viewer.move_selection["axis_direction"] == tuple(sign*v for v in direction)
        assert w.viewer.move_selection["axis_kind"] == kind
        assert_unchanged(w.session, before)
        assert w._selection == selected and w._picks == picks
        assert w.viewer.picked_point == (1, 2, 3)
        assert [f.text() for f in fields] == texts and w.rotation_step.value() == 7.5
        assert tuple(i.ids for i in w.visible_instances()) == visible
        assert w.viewer.transparencies == alpha
    assert len(set(tokens)) == 3  # i návrat ke stejnému směru zneplatní starý tah


@pytest.mark.parametrize("kind", ["line", "cylinder"])
@pytest.mark.parametrize("mode,angle", [("number", 90), ("mouse", 30)])
def test_reversed_axis_rotates_real_parts_opposite_with_one_undo_redo(request, kind, mode, angle):
    w = prepare_window(request)
    w.rotation_handles.click()
    pick_axis(w, kind)
    point, direction = w._picked_rotation_axis()
    w.rotation_axis_reverse_button.click()
    before = snapshot(w.session)
    old = {i.ids: vertices(i.part) for i in w.session.result.instances}
    pivot = np.array(point)
    # Stejný kladný úhel kolem obrácené osy = záporný kolem původní.
    q = independent_rotation(direction, -angle)
    if mode == "number":
        w.batch_rotation_angle.setText(str(angle))
        w.batch_rotation_button.click()
    else:
        w.viewer.selection_rotated.emit({"token": w.viewer.move_selection["token"],
                                         "axis": kind, "angle": angle})
    for i in w.session.result.instances:
        expected = ((q @ (old[i.ids]-pivot).T).T+pivot if i.ids in w._selection else old[i.ids])
        assert all(min(np.linalg.norm(expected-p, axis=1)) < 1e-6 for p in vertices(i.part))
        assert i.part.is_valid
    assert w.session.result.complete and len(w.session._undo) == len(before[2])+1
    moved = w.session.assembly.to_dict()
    axis = w._picked_rotation_axis()
    w.undo_action.trigger()
    assert w.session.assembly.to_dict() == before[0] and w._picked_rotation_axis() == axis
    w.redo_action.trigger()
    assert w.session.assembly.to_dict() == moved and w._picked_rotation_axis() == axis


@pytest.mark.parametrize("kind", ["line", "cylinder"])
def test_reverse_cancels_pick_and_rejects_old_response_without_stopping_new_pick(request, kind):
    w = prepare_window(request)
    w.rotation_handles.click()
    pick_axis(w, kind)
    previous = w._picked_rotation_axis()
    old = choose_line(w) if kind == "line" else choose_cylinder(w)
    assert w.viewer.center_pick is not None and w.rotation_axis_reverse_button.isEnabled()
    before = snapshot(w.session)
    w.rotation_axis_reverse_button.click()
    expected = (previous[0], tuple(-v for v in previous[1]))
    assert w.viewer.center_pick is None and not w.rotation_axis_pick_button.isChecked()
    w.viewer.rotation_center_picked.emit(old)
    assert w._picked_rotation_axis() == expected
    new = choose_line(w) if kind == "line" else choose_cylinder(w)
    w.viewer.rotation_center_pick_finished.emit(old["token"])
    assert w.viewer.center_pick["token"] == new["token"]
    assert w.rotation_axis_pick_button.isChecked()
    assert_unchanged(w.session, before)


@pytest.mark.parametrize("kind", ["line", "cylinder"])
def test_old_rotation_cannot_commit_after_reverse_even_when_direction_is_restored(request, kind):
    w = prepare_window(request)
    w.rotation_handles.click()
    pick_axis(w, kind)
    old = {"token": w.viewer.move_selection["token"], "axis": kind, "angle": 90}
    before = snapshot(w.session)
    for _ in range(2):
        w.rotation_axis_reverse_button.click()
        w.viewer.selection_rotated.emit(old)
        assert_unchanged(w.session, before)
    assert w.viewer.move_selection["token"] != old["token"]


def test_kinds_remember_own_direction_xyz_stays_positive_and_new_pick_resets_direction(request):
    w = prepare_window(request)
    pick_axis(w, "line")
    original_line = w._picked_rotation_axis()
    w.rotation_axis_reverse_button.click()
    line = w._picked_rotation_axis()
    pick_axis(w, "cylinder")
    original_cylinder = w._picked_rotation_axis()
    assert original_cylinder != line
    w.rotation_axis_reverse_button.click()
    cylinder = w._picked_rotation_axis()
    w.batch_rotation_axis.setCurrentIndex(4)
    assert w._picked_rotation_axis() == line
    w.batch_rotation_axis.setCurrentText("Z")
    assert w.rotation_axis_box.isHidden() and not w.rotation_axis_reverse_button.isEnabled()
    assert w._chosen_rotation_axis() == "z"
    w.batch_rotation_axis.setCurrentIndex(3)
    assert w._picked_rotation_axis() == cylinder
    pick_axis(w, "line")
    assert w._picked_rotation_axis() == original_line
    assert w._rotation_cylinder == cylinder and cylinder[0] == original_cylinder[0]


@pytest.mark.parametrize("kind", ["line", "cylinder"])
def test_axis_is_required_and_disabled_handler_cannot_change_preferences(request, kind):
    w = prepare_window(request)
    w.batch_rotation_axis.setCurrentIndex(4 if kind == "line" else 3)
    before = snapshot(w.session)
    assert not w.rotation_axis_reverse_button.isEnabled()
    w._reverse_rotation_axis()
    assert w._picked_rotation_axis() is None
    pick_axis(w, kind)
    axis = w._picked_rotation_axis()
    w.select_many((("nozicka_1",),))
    assert w.rotation_axis_reverse_button.isEnabled()
    w.select(("krabicka",))
    assert not w.rotation_axis_reverse_button.isEnabled()
    w._reverse_rotation_axis()
    assert w._picked_rotation_axis() == axis
    assert_unchanged(w.session, before)


@pytest.mark.parametrize("kind", ["line", "cylinder"])
@pytest.mark.parametrize("tilted", [False, True])
def test_reversal_preserves_expression_limits_and_negative_z_expressions(request, kind, tilted):
    w = prepare_window(request, tilted)
    w.session.set_placement("nozicka_1", rotation=["h", 0, 0])
    w._refresh()
    pick_axis(w, kind)
    assert w.rotation_axis_reverse_button.isEnabled()
    w.rotation_axis_reverse_button.click()
    assert w.batch_rotation_button.isEnabled() == (not tilted)
    assert w.rotation_handles.isEnabled() == (not tilted)
    if not tilted:
        w.batch_rotation_angle.setText("90")
        direction = w._chosen_rotation_axis()
        w.batch_rotation_button.click()
        rotation = w.session.assembly.component("nozicka_1").rotation
        assert rotation[:2] == ["h", 0]
        assert evaluate(rotation[2], w.session.result.parameters) == pytest.approx(90*direction[2])
    else:
        assert "výrazem" in w.batch_rotation_note.text()
