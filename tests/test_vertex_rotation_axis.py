"""P7.28: dva přesné vrcholy, rozpracovaný výběr a společná fyzická rotace."""

import math

import numpy as np
import pytest
from build123d import Box, Pos, Rot
from OCP.AIS import AIS_TextLabel
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.gp import gp_Pnt
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

from skodacad.gui.rotation_drag import plane_frame
from skodacad.gui.viewer import _rotation_pick_vertices
from test_assembly_batch_move import assert_unchanged, snapshot
from test_assembly_batch_rotation import vertices
from test_assembly_gui import (  # noqa: F401
    app,
    dialogs,
    main_window,
    nested_isolation,
    opened,
    project,
)
from test_cylinder_rotation_axis import choose_cylinder, independent_rotation
from test_line_rotation_axis import choose_line, prepare_window
from test_plane_rotation_axis import choose_plane
from test_rotation_center_pick import mouse, pick_viewer  # noqa: F401
from test_selection_drag import viewer  # noqa: F401


def vertex(point):
    return BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()


@pytest.mark.parametrize("rotation", [(0, 0, 0), (30, 40, 50)])
@pytest.mark.parametrize("cross_part", [False, True])
def test_axis_uses_exact_placed_vertices_in_click_order(rotation, cross_part):
    part = Pos(12, 23, 34)*Rot(*rotation)*Box(8, 10, 12)
    first = min(part.vertices(), key=lambda v: v.X)
    other = Pos(-15, 27, -4)*Box(2, 4, 6) if cross_part else part
    second = max(other.vertices(), key=lambda v: v.X)
    p, q = np.array(tuple(first.center())), np.array(tuple(second.center()))
    point, direction = _rotation_pick_vertices(first.wrapped, second.wrapped)
    assert point == pytest.approx(p, abs=1e-12)
    assert direction == pytest.approx((q-p)/np.linalg.norm(q-p), abs=1e-12)
    reverse = _rotation_pick_vertices(second.wrapped, first.wrapped)
    assert reverse[0] == pytest.approx(q) and reverse[1] == pytest.approx(-np.array(direction))


@pytest.mark.parametrize("distance", [0., 1e-10, 1e-7])
def test_coincident_distinct_topology_and_too_close_points_are_refused(distance):
    a, b = vertex((0, 0, 0)), vertex((distance, 0, 0))
    assert not a.IsSame(b)
    assert _rotation_pick_vertices(a, b) is None
    assert _rotation_pick_vertices(a, a) is None
    assert _rotation_pick_vertices(a, next(iter(Box(2, 2, 2).edges())).wrapped) is None
    assert _rotation_pick_vertices(a, vertex((2e-7, 0, 0))) == ((0., 0., 0.), (1., 0., 0.))


@pytest.mark.parametrize("ratio", [1., 1.25, 2.])
def test_two_clicks_retry_marker_cleanup_and_selection_preserved(request, monkeypatch, ratio):
    v, state = request.getfixturevalue("pick_viewer")
    monkeypatch.setattr(v, "_pixel_scale", lambda: ratio)
    removed, received, selected = [], [], []
    v._context.Remove = lambda obj, *_: removed.append(obj)
    v.rotation_center_picked.connect(received.append)
    v.selection_changed.connect(selected.append)
    v.selection_cleared.connect(lambda: selected.append("clear"))
    first, second = vertex((2, -3, 4)), vertex((5, 1, 4))
    assert v.start_rotation_center_pick("vertices", "request")

    def click(shape, detected=True):
        state.shape, state.detected = shape, detected
        v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (10, 12)))
        v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (10, 12)))

    click(first)
    marker = v._center_pick["marker"]
    assert v._center_pick["first"].IsSame(first) and not received
    for shape, detected in ((first, True), (vertex((2, -3, 4)), True),
                            (first, False), (next(iter(Box(2, 2, 2).edges())).wrapped, True)):
        click(shape, detected)
        assert v._center_pick["marker"] is marker and not received
    click(second)
    assert len(received) == 1
    assert received[0] == {"token": "request", "kind": "vertices", "shape": second,
                            "shapes": (first, second), "point": (2., -3., 4.),
                            "direction": (.6, .8, 0.)}
    assert marker in removed and v._center_pick is None
    assert not selected and v.picked_point == (99, 88, 77) and state.modes[-2:] == [2, 4]
    assert state.moves[-1] == (int(10*ratio), int(12*ratio))
    assert v._surface.cursor().shape() == Qt.CursorShape.ArrowCursor


@pytest.mark.parametrize("cause", ["escape", "right", "resize", "hide", "deactivate",
                                  "data", "alpha", "stop", "restart"])
def test_cancel_after_first_vertex_removes_marker_and_restores_modes(request, monkeypatch, cause):
    v, state = request.getfixturevalue("pick_viewer")
    received, removed = [], []
    v.rotation_center_picked.connect(received.append)
    v._context.Remove = lambda obj, *_: removed.append(obj)
    v.start_rotation_center_pick("vertices", "old")
    state.shape = vertex((2, 3, 4))
    v._pick_rotation_center_at(10, 12)
    marker = v._center_pick["marker"]
    if cause == "escape":
        v.clear_selection()
    elif cause == "right":
        v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (10, 12), Qt.MouseButton.RightButton))
        v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (10, 12),
                               Qt.MouseButton.RightButton))
    elif cause == "resize":
        monkeypatch.setattr(v, "_sync_size", lambda: None)
        v._resized()
    elif cause in ("hide", "deactivate"):
        QApplication.sendEvent(v._surface, QEvent(QEvent.Type.Hide if cause == "hide"
                                                 else QEvent.Type.WindowDeactivate))
    elif cause == "data":
        v.set_move_selection(v._move_data)
    elif cause == "alpha":
        v.set_transparent_parts([])
    elif cause == "restart":
        v.start_rotation_center_pick("vertices", "new")
        assert "first" not in v._center_pick and v._center_pick["token"] == "new"
    else:
        v.cancel_rotation_center_pick()
    assert marker in removed and not received and v.picked_point == (99, 88, 77)
    if cause != "restart":
        assert v._center_pick is None and state.modes[-2:] == [2, 4]


def choose_vertices(w, instances=None):
    w.batch_rotation_axis.setCurrentIndex(6)
    w.rotation_axis_pick_button.click()
    if instances is None:
        instances = [next(i for i in w.visible_instances() if i.ids == (name,))
                     for name in ("nozicka_3", "nozicka_4")]
    a = max(instances[0].part.vertices(), key=lambda v: v.Z).wrapped
    b = min(instances[1].part.vertices(), key=lambda v: v.Z).wrapped
    point, direction = _rotation_pick_vertices(a, b)
    return {"token": w.viewer.center_pick["token"], "kind": "vertices", "shape": b,
            "shapes": (a, b), "point": point, "direction": direction}


@pytest.mark.parametrize("mode,angle", [("number", 90), ("mouse", 30)])
def test_vertex_axis_reverse_physical_motion_and_one_undo_redo(request, mode, angle):
    w = prepare_window(request)
    w.rotation_handles.click()
    w.move_edits[0].setText("2,5")
    w.rotation_center_edits[0].setText("12,5")
    payload = choose_vertices(w)
    w._picks = [(payload["shape"], (1, 2, 3))]
    state, selected = snapshot(w.session), w._selection
    w.viewer.rotation_center_picked.emit(payload)
    assert_unchanged(w.session, state)
    assert w._selection == selected and w._picks == [(payload["shape"], (1, 2, 3))]
    pivot, direction = w._rotation_vertices
    assert pivot == payload["point"] and direction == pytest.approx(payload["direction"])
    w.rotation_axis_reverse_button.click()
    assert_unchanged(w.session, state)
    old = {i.ids: vertices(i.part) for i in w.session.result.instances}
    q = independent_rotation(direction, -angle)
    if mode == "number":
        w.batch_rotation_angle.setText(str(angle))
        w.batch_rotation_button.click()
    else:
        w.viewer.selection_rotated.emit({"token": w.viewer.move_selection["token"],
                                         "axis": "vertices", "angle": angle})
    for i in w.session.result.instances:
        expected = ((q @ (old[i.ids]-pivot).T).T+pivot if i.ids in selected else old[i.ids])
        assert all(min(np.linalg.norm(expected-p, axis=1)) < 1e-6 for p in vertices(i.part))
        assert i.part.is_valid
    moved = w.session.assembly.to_dict()
    assert len(w.session._undo) == len(state[2])+1
    w.undo_action.trigger()
    assert w.session.assembly.to_dict() == state[0]
    w.redo_action.trigger()
    assert w.session.assembly.to_dict() == moved
    assert w.move_edits[0].text() == "2,5" and w.rotation_center_edits[0].text() == "12,5"


@pytest.mark.parametrize("cause", ["stop", "reverse", "away_back", "hide_first", "hide_second",
                                  "selection", "result", "restart", "bad_first", "bad_second",
                                  "missing_shapes", "bad_direction"])
def test_stale_vertex_pair_cannot_replace_previous_axis(request, cause):
    w = prepare_window(request)
    w.viewer.rotation_center_picked.emit(choose_vertices(w))
    payload = choose_vertices(w)
    if cause == "stop":
        w.rotation_axis_pick_button.click()
    elif cause == "reverse":
        w.rotation_axis_reverse_button.click()
    elif cause == "away_back":
        w.batch_rotation_axis.setCurrentIndex(3)
        w.batch_rotation_axis.setCurrentIndex(6)
    elif cause.startswith("hide_"):
        w.set_component_visible(("nozicka_3" if cause == "hide_first" else "nozicka_4",), False)
    elif cause == "selection":
        w.select_many((("nozicka_3",), ("nozicka_4",)))
    elif cause == "result":
        w.session.rebuild()
    elif cause == "restart":
        w.rotation_axis_pick_button.click()
        w.rotation_axis_pick_button.click()
    elif cause in ("bad_first", "bad_second"):
        a, b = payload["shapes"]
        foreign = vertex((100, 200, 300))
        payload["shapes"] = (foreign, b) if cause == "bad_first" else (a, foreign)
    elif cause == "missing_shapes":
        del payload["shapes"]
    else:
        payload["direction"] = (float("nan"), 0, 1)
    axis, selected, before = w._rotation_vertices, w._selection, snapshot(w.session)
    w.viewer.rotation_center_picked.emit(payload)
    assert w._rotation_vertices == axis and w._selection == selected
    assert_unchanged(w.session, before)
    if cause == "restart":
        token = w.viewer.center_pick["token"]
        w.viewer.rotation_center_pick_finished.emit(payload["token"])
        assert w.viewer.center_pick["token"] == token and w.rotation_axis_pick_button.isChecked()


def test_four_independent_snapshots_and_nested_vertices(request):
    w = request.getfixturevalue("nested_isolation")
    selected = (("a",), ("b",))
    w.select_many(selected)
    children = [next(i for i in w.visible_instances() if i.ids[:1] == (name,))
                for name in ("a", "b")]
    payload = choose_vertices(w, children)
    before = snapshot(w.session)
    w.viewer.rotation_center_picked.emit(payload)
    assert w._rotation_vertices[0] == payload["point"]
    assert w._rotation_vertices[1] == pytest.approx(payload["direction"])
    assert w._selection == selected
    assert_unchanged(w.session, before)
    w = prepare_window(request)
    for pick in (choose_vertices, choose_plane, choose_line, choose_cylinder):
        w.viewer.rotation_center_picked.emit(pick(w))
    for index, kind in ((6, "vertices"), (5, "plane"), (4, "line"), (3, "cylinder")):
        w.batch_rotation_axis.setCurrentIndex(index)
        assert w._picked_rotation_axis() == getattr(w, f"_rotation_{kind}")


@pytest.mark.parametrize("ratio", [1., 1.25, 2.])
def test_vertex_ring_preview_and_release_share_negative_oblique_axis(request, monkeypatch, ratio):
    v = request.getfixturevalue("viewer")
    monkeypatch.setattr(v, "_pixel_scale", lambda: ratio)
    direction = (-2., 1., -4.)
    v.set_move_selection(dict(v._move_data, mode="rotate", axes=[3], axis_kind="vertices",
                              axis_direction=direction, step=15))
    assert [o.Text().ToExtString() for o in v._move_objects
            if isinstance(o, AIS_TextLabel)] == ["Osa dvou vrcholů"]
    center = np.array(v._move_data["anchor"])
    n, u, w = map(np.array, plane_frame(direction))
    radius = v._view.Convert(round(90*ratio))

    def position(angle):
        p = center+radius*(u*math.cos(math.radians(angle))+w*math.sin(math.radians(angle)))
        return tuple(p/ratio for p in v._view.Convert(*p))

    received = []
    v.selection_rotated.connect(received.append)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, position(45)))
    v._mouse_move(mouse(QEvent.Type.MouseMove, position(77)))
    assert v._selection_drag["angle"] == 30 and not received
    transform = v._selection_drag["preview"].LocalTransformation()
    assert gp_Pnt(*(center+7*n)).Transformed(transform).Coord() == pytest.approx(center+7*n)
    assert gp_Pnt(*(center+3*u)).Transformed(transform).Coord() == pytest.approx(
        center+independent_rotation(direction, 30) @ (3*u))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, position(77)))
    assert received == [{"token": "current", "axis": "vertices", "angle": 30}]


@pytest.mark.parametrize("tilted", [False, True])
def test_vertex_axis_orientation_expressions_and_fixed_reference(request, tilted):
    w = prepare_window(request, tilted)
    w.session.set_placement("nozicka_1", rotation=["h", 0, 0])
    w._refresh()
    ref = next(i for i in w.visible_instances() if i.ids == ("nozicka_3",))
    w.viewer.rotation_center_picked.emit(choose_vertices(w, [ref, ref]))
    w.rotation_axis_reverse_button.click()
    assert w.rotation_axis_reverse_button.isEnabled() and w.rotation_axis_pick_button.isEnabled()
    assert w.batch_rotation_button.isEnabled() == (not tilted)
    assert w.rotation_handles.isEnabled() == (not tilted)
    if tilted:
        assert "výrazem" in w.batch_rotation_note.text()
    fixed = next(i for i in w.visible_instances() if i.ids == ("krabicka",))
    before = snapshot(w.session)
    payload = choose_vertices(w, [fixed, ref])
    w.viewer.rotation_center_picked.emit(payload)
    assert w._rotation_vertices[0] == payload["point"]
    assert_unchanged(w.session, before)


@pytest.mark.parametrize("cause", ["reverse_twice", "away_back", "wrong_kind"])
def test_old_vertex_drag_never_commits_after_axis_revision(request, cause):
    w = prepare_window(request)
    w.viewer.rotation_center_picked.emit(choose_vertices(w))
    w.rotation_handles.click()
    token = w.viewer.move_selection["token"]
    axis = "vertices"
    if cause == "reverse_twice":
        w.rotation_axis_reverse_button.click()
        w.rotation_axis_reverse_button.click()
    elif cause == "away_back":
        w.batch_rotation_axis.setCurrentIndex(2)
        w.batch_rotation_axis.setCurrentIndex(6)
    else:
        axis = "line"
    before = snapshot(w.session)
    w.viewer.selection_rotated.emit({"token": token, "axis": axis, "angle": 90})
    assert_unchanged(w.session, before)
