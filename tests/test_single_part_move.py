"""Přírůstkový posun a posouvací rukojeti pro jednu komponentu sestavy."""

import numpy as np
import pytest

from test_assembly_batch_rotation import vertices
from test_assembly_gui import (  # noqa: F401
    app,
    constrained,
    dialogs,
    main_window,
    nested_isolation,
    opened,
    project,
)


@pytest.mark.parametrize("delta", [(3.5, 0, 0), (0, -4, 0), (0, 0, 2.25)])
@pytest.mark.parametrize("mode", ["number", "mouse"])
def test_single_increment_moves_only_selected_geometry_and_undoes_once(request, delta, mode):
    w = request.getfixturevalue("opened")
    w.select(("nozicka_1",))
    assert w.move_box.isVisibleTo(w) and w.move_box.title() == "Posun [mm]"
    assert w.move_button.isEnabled() and w.move_handles.isEnabled()
    assert len(w.viewer.move_selection["shapes"]) == 1
    before = w.session.assembly.to_dict()
    old = {i.ids: vertices(i.part) for i in w.session.result.instances}
    volume = w.session.result.volume_mm3
    if mode == "number":
        for field, value in zip(w.move_edits, delta, strict=True):
            field.setText(str(value).replace(".", ","))
        w.move_button.click()
        assert [field.text() for field in w.move_edits] == ["0", "0", "0"]
    else:
        w.move_edits[0].setText("2,5")
        w.viewer.selection_moved.emit({"token": w.viewer.move_selection["token"],
                                      "delta": delta})
        assert w.move_edits[0].text() == "2,5"
    assert len(w.session._undo) == 1 and w._selection == (("nozicka_1",),)
    for i in w.session.result.instances:
        expected = old[i.ids] + (np.array(delta) if i.ids == ("nozicka_1",) else 0)
        assert all(min(np.linalg.norm(expected-p, axis=1)) < 1e-6 for p in vertices(i.part))
        assert i.part.is_valid
    assert w.session.result.volume_mm3 == pytest.approx(volume)
    assert all(c.rotation == next(c0["placement"]["rotation"] for c0 in before["components"]
                                 if c0["id"] == c.id) for c in w.session.assembly.components)
    moved = w.session.assembly.to_dict()
    w.undo_action.trigger()
    assert w.session.assembly.to_dict() == before and not w.session.can_undo
    w.redo_action.trigger()
    assert w.session.assembly.to_dict() == moved


def test_single_move_and_rotation_switch_without_model_changes_or_old_drag(request):
    w = request.getfixturevalue("opened")
    w.select(("nozicka_1",))
    old = {"token": w.viewer.move_selection["token"], "delta": [5, 0, 0]}
    before = w.session.assembly.to_dict()
    w.rotation_handles.click()
    assert not w.move_handles.isChecked() and w.viewer.move_selection["mode"] == "rotate"
    w.viewer.selection_moved.emit(old)
    assert w.session.assembly.to_dict() == before and not w.session.can_undo
    w.move_handles.click()
    assert not w.rotation_handles.isChecked()
    assert w.viewer.move_selection.get("mode") != "rotate"
    assert w.session.assembly.to_dict() == before and not w.session.can_undo
    w.select(("nozicka_2",))
    w.viewer.selection_moved.emit(old)
    assert w.session.assembly.to_dict() == before and not w.session.can_undo


def test_single_move_blocks_fixed_nested_and_empty_selection_and_hides_handles(request):
    w = request.getfixturevalue("opened")
    w.select(("nozicka_1",))
    old = {"token": w.viewer.move_selection["token"], "delta": [5, 0, 0]}
    for selection in (("krabicka",), None):
        w.select(selection)
        before = w.session.assembly.to_dict()
        assert not w.move_button.isEnabled() and not w.move_handles.isEnabled()
        assert w.viewer.move_selection is None
        w.viewer.selection_moved.emit(old)
        assert w.session.assembly.to_dict() == before and not w.session.can_undo
    assert not w.move_box.isVisibleTo(w)
    nested = request.getfixturevalue("nested_isolation")
    nested.select(("a", "deska"))
    assert not nested.move_button.isEnabled() and nested.viewer.move_selection is None


def test_hidden_single_part_can_move_numerically_without_handles(request):
    w = request.getfixturevalue("opened")
    w.select(("nozicka_1",))
    old = np.array(tuple(next(i for i in w.session.result.instances
                              if i.ids == ("nozicka_1",)).part.center()))
    w.toggle_selected_visibility()
    assert w.viewer.move_selection is None and w.move_button.isEnabled()
    w.move_edits[2].setText("h")
    w.move_button.click()
    moved = next(i for i in w.session.result.instances if i.ids == ("nozicka_1",))
    assert tuple(moved.part.center()) == pytest.approx(old + (0, 0, 3))
    assert w.viewer.move_selection is None and len(w.session._undo) == 1


def test_single_part_constraint_failure_preserves_pose_and_input(request):
    w = request.getfixturevalue("constrained")
    answers = request.getfixturevalue("dialogs")
    w.select(("nozicka_1",))
    before, result = w.session.assembly.to_dict(), w.session.result
    w.move_edits[2].setText("5")
    w.move_button.click()
    assert answers["shown"][-1][0] == "Výběr nejde posunout"
    assert w.session.assembly.to_dict() == before and w.session.result is result
    assert not w.session.can_undo and w.move_edits[2].text() == "5"


def test_single_parent_moves_its_hidden_child_and_keeps_other_branch(request):
    w = request.getfixturevalue("nested_isolation")
    w.select(("a",))
    w.set_component_visible(("a", "druha"), False)
    before = {i.ids: vertices(i.part) for i in w.session.result.instances}
    assert len(w.viewer.move_selection["shapes"]) == 1
    w.viewer.selection_moved.emit({"token": w.viewer.move_selection["token"],
                                  "delta": (5, 0, 0)})
    assert len(w.session._undo) == 1
    for i in w.session.result.instances:
        expected = before[i.ids] + (np.array((5, 0, 0)) if i.ids[0] == "a" else 0)
        assert all(min(np.linalg.norm(expected-p, axis=1)) < 1e-6 for p in vertices(i.part))
        assert i.part.is_valid
