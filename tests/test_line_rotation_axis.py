"""P7.25: skutečná přímá hrana ve světě sestavy a společný náhled/potvrzení osy."""

import math

import numpy as np
import pytest
from build123d import Box, Edge, Pos, Rot
from OCP.AIS import AIS_TextLabel
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.Geom import Geom_Line
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
from OCP.TopoDS import TopoDS_Edge
from PySide6.QtCore import QEvent, Qt

from skodacad.gui.rotation_drag import plane_frame
from skodacad.gui.viewer import _rotation_pick_line
from test_assembly_batch_move import assert_unchanged, snapshot
from test_assembly_gui import (  # noqa: F401
    app,
    dialogs,
    main_window,
    nested_isolation,
    opened,
    project,
)
from test_cylinder_rotation_axis import choose_cylinder, independent_rotation
from test_rotation_center_pick import circle, pick_viewer  # noqa: F401
from test_selection_drag import mouse, viewer  # noqa: F401


@pytest.mark.parametrize("end", [(6, 0, 0), (0, -8, 0), (0, 0, 12), (6, 8, 12)])
@pytest.mark.parametrize("rotation", [(0, 0, 0), (30, 40, 50)])
def test_line_midpoint_and_direction_follow_world_placement(end, rotation):
    edge = Pos(12, 23, 34)*Rot(*rotation)*Edge.make_line((0, 0, 0), end)
    point, direction = _rotation_pick_line(edge.wrapped)
    endpoints = np.array([tuple(v) for v in edge.vertices()])
    assert point == pytest.approx(endpoints.mean(axis=0), abs=1e-12)
    assert np.linalg.norm(direction) == pytest.approx(1)
    for p in endpoints:
        assert np.cross(p-point, direction) == pytest.approx(np.zeros(3), abs=1e-12)
    assert np.linalg.norm(endpoints[1]-endpoints[0]) == pytest.approx(math.hypot(*end))


def test_trimmed_line_uses_segment_midpoint_not_carrier_origin_and_reversal_keeps_axis():
    line = gp_Lin(gp_Pnt(100, -20, 30), gp_Dir(1, 2, 3))
    edge = BRepBuilderAPI_MakeEdge(line, 10., 30.).Edge()
    point, direction = _rotation_pick_line(edge)
    assert point == pytest.approx(np.array([100, -20, 30])+20*np.array(direction))
    assert _rotation_pick_line(edge.Reversed()) == (point, direction)


@pytest.mark.parametrize("kind", ["circle", "arc", "bezier", "collinear_bezier", "face"])
def test_curves_and_faces_are_not_approximated_as_straight_edges(kind):
    shape = {"circle": lambda: circle(), "arc": lambda: circle(arc=True),
             "bezier": lambda: Edge.make_bezier((0, 0, 0), (2, 1, 0), (4, 0, 0)).wrapped,
             "collinear_bezier": lambda: Edge.make_bezier((0, 0, 0), (2, 0, 0),
                                                         (4, 0, 0)).wrapped,
             "face": lambda: next(iter(Box(4, 4, 4).faces())).wrapped}[kind]()
    assert _rotation_pick_line(shape) is None


def test_degenerate_zero_and_unbounded_edges_cannot_supply_an_axis():
    builder = BRep_Builder()
    degenerate = TopoDS_Edge()
    builder.MakeEdge(degenerate)
    builder.Degenerated(degenerate, True)
    assert _rotation_pick_line(degenerate) is None
    zero = TopoDS_Edge()
    builder.MakeEdge(zero)
    line = gp_Lin(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0))
    builder.UpdateEdge(zero, Geom_Line(line), 1e-7)
    builder.Range(zero, 2., 2.)
    assert _rotation_pick_line(zero) is None
    assert _rotation_pick_line(BRepBuilderAPI_MakeEdge(line).Edge()) is None


@pytest.mark.parametrize("ratio", [1., 1.25, 2.])
def test_viewer_line_pick_preserves_selection_point_and_restores_modes(request, monkeypatch, ratio):
    v, state = request.getfixturevalue("pick_viewer")
    monkeypatch.setattr(v, "_pixel_scale", lambda: ratio)
    state.shape = Edge.make_line((2, -3, 4), (8, 5, 16)).wrapped
    received, selected = [], []
    v.rotation_center_picked.connect(received.append)
    v.selection_changed.connect(selected.append)
    v.selection_cleared.connect(lambda: selected.append("clear"))
    assert v.start_rotation_center_pick("line", "request")
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (10, 12)))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (10, 12)))
    assert len(received) == 1 and received[0]["kind"] == "line"
    assert received[0]["point"] == pytest.approx((5, 1, 10))
    assert not selected and v.picked_point == (99, 88, 77) and v._center_pick is None
    assert state.modes[-2:] == [2, 4] and v._move_objects
    assert state.moves[-1] == (int(10*ratio), int(12*ratio))


def test_curved_edge_and_miss_keep_line_picker_armed(request):
    v, state = request.getfixturevalue("pick_viewer")
    received = []
    v.rotation_center_picked.connect(received.append)
    v.start_rotation_center_pick("line", "request")
    for detected in (True, False):
        state.detected = detected
        v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (10, 12)))
        v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (10, 12)))
        assert v._center_pick is not None and not received


@pytest.mark.parametrize("cause", ["escape", "right", "data"])
def test_line_cancel_restores_detection_without_a_point(request, cause):
    v, state = request.getfixturevalue("pick_viewer")
    received = []
    v.rotation_center_picked.connect(received.append)
    v.start_rotation_center_pick("line", "request")
    if cause == "escape":
        v.clear_selection()
    elif cause == "data":
        v.set_move_selection(v._move_data)
    else:
        from test_rotation_center_pick import mouse as pick_mouse
        v._mouse_press(pick_mouse(QEvent.Type.MouseButtonPress, (10, 12),
                                  Qt.MouseButton.RightButton))
        v._mouse_release(pick_mouse(QEvent.Type.MouseButtonRelease, (10, 12),
                                    Qt.MouseButton.RightButton))
    assert v._center_pick is None and not received and state.modes[-2:] == [2, 4]


@pytest.mark.parametrize("ratio", [1., 1.25, 2.])
def test_line_ring_preview_and_release_use_same_world_axis(request, monkeypatch, ratio):
    v = request.getfixturevalue("viewer")
    monkeypatch.setattr(v, "_pixel_scale", lambda: ratio)
    direction = (2., -1., 4.)
    v.set_move_selection(dict(v._move_data, mode="rotate", axes=[3], axis_kind="line",
                              axis_direction=direction, step=15))
    assert [o.Text().ToExtString() for o in v._move_objects
            if isinstance(o, AIS_TextLabel)] == ["Osa hrany"]
    center = np.array(v._move_data["anchor"])
    n, u, w = map(np.array, plane_frame(direction))
    radius = v._view.Convert(round(90*ratio))

    def position(angle):
        point = center+radius*(u*math.cos(math.radians(angle))+w*math.sin(math.radians(angle)))
        return tuple(p/ratio for p in v._view.Convert(*point))

    received = []
    v.selection_rotated.connect(received.append)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, position(45)))
    v._mouse_move(mouse(QEvent.Type.MouseMove, position(77)))
    assert v._selection_drag["angle"] == 30 and not received
    transform = v._selection_drag["preview"].LocalTransformation()
    assert gp_Pnt(*(center+7*n)).Transformed(transform).Coord() == pytest.approx(center+7*n)
    moved = gp_Pnt(*(center+3*u)).Transformed(transform)
    assert moved.Coord() == pytest.approx(center+independent_rotation(direction, 30) @ (3*u))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, position(77)))
    assert received == [{"token": "current", "axis": "line", "angle": 30}]


def choose_line(w):
    w.batch_rotation_axis.setCurrentIndex(4)
    w.rotation_axis_pick_button.click()
    ref = next(i for i in w.visible_instances() if i.ids == ("nozicka_3",))
    shape = next(e.wrapped for e in ref.part.edges() if _rotation_pick_line(e.wrapped) is not None)
    point, direction = _rotation_pick_line(shape)
    return {"token": w.viewer.center_pick["token"], "kind": "line", "shape": shape,
            "point": point, "direction": direction}


def prepare_window(request, tilted=True):
    w = request.getfixturevalue("opened")
    if tilted:
        w.session.set_placement("nozicka_3", rotation=[30, 40, 50])
        w._refresh()
    w.select_many((("nozicka_1",), ("nozicka_2",)))
    return w


def test_picked_edge_keeps_selection_redo_and_drives_numeric_and_mouse_rotation(request):
    w = prepare_window(request)
    w.batch_rotation_button.click()
    w.undo_action.trigger()
    state = snapshot(w.session)
    w.rotation_handles.click()
    w.move_edits[0].setText("2,5")
    payload = choose_line(w)
    w._picks = [(payload["shape"], (1, 2, 3))]
    w.viewer.rotation_center_picked.emit(payload)
    assert_unchanged(w.session, state)
    assert w._selection == (("nozicka_1",), ("nozicka_2",))
    assert w._picks == [(payload["shape"], (1, 2, 3))] and w.move_edits[0].text() == "2,5"
    assert w._rotation_line is not None and w._rotation_cylinder is None
    assert not w.rotation_axis_pick_button.isChecked() and w.viewer.center_pick is None
    assert w.viewer.move_selection["axis_kind"] == "line"
    old = {i.ids: np.array(tuple(i.part.center())) for i in w.session.result.instances}
    pivot, direction = map(np.array, w._rotation_line)
    for mode, angle in (("number", 90), ("mouse", 30)):
        if mode == "number":
            w.batch_rotation_angle.setText(str(angle))
            w.batch_rotation_button.click()
        else:
            w.viewer.selection_rotated.emit({"token": w.viewer.move_selection["token"],
                                             "axis": "line", "angle": angle})
        q = independent_rotation(direction, angle)
        for i in w.session.result.instances:
            assert tuple(i.part.center()) == pytest.approx(
                pivot+q @ (old[i.ids]-pivot) if i.ids in w._selection else old[i.ids], abs=1e-6)
            assert i.part.is_valid
        assert len(w.session._undo) == len(state[2])+1
        w.undo_action.trigger()
        assert w.session.assembly.to_dict() == state[0]


def test_edge_and_cylinder_snapshots_do_not_mix_and_wrong_kind_rotation_is_rejected(request):
    w = prepare_window(request)
    w.rotation_handles.click()
    w.viewer.rotation_center_picked.emit(choose_line(w))
    line = w._rotation_line
    payload = choose_cylinder(w)
    assert w._picked_rotation_axis() is None and not w.batch_rotation_button.isEnabled()
    w.viewer.rotation_center_picked.emit(payload)
    cylinder = w._rotation_cylinder
    assert cylinder[0] != line[0]
    w.batch_rotation_axis.setCurrentIndex(4)
    assert w._picked_rotation_axis() == line and w.viewer.move_selection["axis_kind"] == "line"
    state = snapshot(w.session)
    w.viewer.selection_rotated.emit({"token": w.viewer.move_selection["token"],
                                     "axis": "cylinder", "angle": 90})
    assert_unchanged(w.session, state)
    w.batch_rotation_axis.setCurrentIndex(3)
    assert w._picked_rotation_axis() == cylinder
    assert w.viewer.move_selection["axis_kind"] == "cylinder"


@pytest.mark.parametrize("cause", ["escape", "stop", "kind", "selection", "hide", "alpha",
                                  "recipe", "result", "restart", "away_back", "bad_shape",
                                  "bad_direction", "bad_point"])
def test_stale_or_bad_line_request_preserves_previous_axis_and_state(request, cause):
    w = prepare_window(request)
    w.viewer.rotation_center_picked.emit(choose_line(w))
    previous = w._rotation_line
    payload = choose_line(w)
    if cause == "escape":
        w.clear_component_selection()
    elif cause == "stop":
        w.rotation_axis_pick_button.click()
    elif cause in ("kind", "away_back"):
        w.batch_rotation_axis.setCurrentIndex(3)
        if cause == "away_back":
            w.batch_rotation_axis.setCurrentIndex(4)
    elif cause == "selection":
        w.select_many((("nozicka_3",), ("nozicka_4",)))
    elif cause == "hide":
        w.set_component_visible(("nozicka_3",), False)
    elif cause == "alpha":
        w.set_component_transparency(("nozicka_1",), 35)
    elif cause == "recipe":
        w.session.assembly.name += " změna"
    elif cause == "result":
        w.session.rebuild()
    elif cause == "restart":
        w.rotation_axis_pick_button.click()
        w.rotation_axis_pick_button.click()
    elif cause == "bad_shape":
        payload["shape"] = Edge.make_line((100, 200, 300), (110, 200, 300)).wrapped
    elif cause == "bad_direction":
        payload["direction"] = (0, 0, 0)
    else:
        payload["point"] = (float("nan"), 0, 0)
    before, selected = snapshot(w.session), w._selection
    w.viewer.rotation_center_picked.emit(payload)
    assert w._rotation_line == previous and w._selection == selected
    assert_unchanged(w.session, before)
    if cause == "restart":
        token = w.viewer.center_pick["token"]
        w.viewer.rotation_center_pick_finished.emit(payload["token"])
        assert w.viewer.center_pick["token"] == token and w.rotation_axis_pick_button.isChecked()


@pytest.mark.parametrize("tilted", [False, True])
def test_line_axis_respects_orientation_expressions_and_allows_another_pick(request, tilted):
    w = prepare_window(request, tilted)
    w.session.set_placement("nozicka_1", rotation=["h", 0, 0])
    w._refresh()
    w.rotation_handles.click()
    w.viewer.rotation_center_picked.emit(choose_line(w))
    assert w.rotation_axis_pick_button.isEnabled()
    assert w.batch_rotation_button.isEnabled() == (not tilted)
    assert w.rotation_handles.isEnabled() == (not tilted)
    assert w.viewer.move_selection["axes"] == ([] if tilted else [3])
    if tilted:
        assert "výrazem" in w.batch_rotation_note.text()


def test_nested_visible_edge_keeps_parent_selection_and_uses_world_axis(request):
    w = request.getfixturevalue("nested_isolation")
    ids = (("a",), ("b",))
    w.select_many(ids)
    w.batch_rotation_axis.setCurrentIndex(4)
    w.rotation_axis_pick_button.click()
    child = next(i for i in w.visible_instances() if i.ids[:1] == ("b",))
    shape = next(e.wrapped for e in child.part.edges()
                 if _rotation_pick_line(e.wrapped) is not None)
    point, direction = _rotation_pick_line(shape)
    state = snapshot(w.session)
    w.viewer.rotation_center_picked.emit({"token": w.viewer.center_pick["token"], "kind": "line",
                                         "shape": shape, "point": point, "direction": direction})
    assert w._rotation_line == (point, direction) and w._selection == ids
    assert_unchanged(w.session, state)
