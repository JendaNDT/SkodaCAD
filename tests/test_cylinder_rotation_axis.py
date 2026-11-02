"""P7.24: přesná umístěná osa válce, tuhý pohyb a izolovaný životní cyklus výběru."""

import math

import numpy as np
import pytest
from build123d import Box, Cone, Cylinder, Pos, Rot
from OCP.AIS import AIS_TextLabel
from OCP.gp import gp_Pnt
from PySide6.QtCore import QEvent
from scipy.spatial.transform import Rotation

from skodacad.assembly import AssemblyError
from skodacad.assembly_build import axis_direction, axis_matrix
from skodacad.expressions import evaluate
from skodacad.gui.rotation_drag import angle_on_plane, plane_frame, ring_points
from skodacad.gui.viewer import _rotation_pick_cylinder
from test_assembly import part_data, write
from test_assembly_batch_move import assert_unchanged, linked, snapshot  # noqa: F401
from test_assembly_batch_rotation import group, vertices  # noqa: F401
from test_assembly_gui import app, dialogs, main_window, opened, project  # noqa: F401
from test_rotation_center_pick import pick_viewer  # noqa: F401
from test_selection_drag import mouse, viewer  # noqa: F401


def independent_rotation(direction, angle):
    d = np.array(direction, dtype=float)
    d /= max(abs(d))
    return Rotation.from_rotvec(d/np.linalg.norm(d)*math.radians(angle)).as_matrix()


@pytest.mark.parametrize("direction", [(1, 2, 3), (-2, 0, 1), (0, 0, -1),
                                       (1e308, 1e308, 0), (1e-300, 0, 1e-300)])
@pytest.mark.parametrize("angle", [90, -37.5])
def test_arbitrary_axis_matches_independent_vertices_poses_and_one_undo(request, direction, angle):
    s, source = request.getfixturevalue("group")
    before, raw = s.assembly.to_dict(), source.read_bytes()
    old = {i.ids: vertices(i.part) for i in s.result.instances}
    pivot = np.array((12.5, -31, 18))
    q = independent_rotation(direction, angle)
    assert np.array(axis_matrix(direction, angle)) == pytest.approx(q, abs=1e-14)
    s.turn_many_around(["a", "b", "a"], direction, angle, center=tuple(pivot))
    assert s.result.complete and s.result.volume_mm3 == pytest.approx(13000)
    for i in s.result.instances:
        expected = ((q @ (old[i.ids]-pivot).T).T+pivot if i.ids[0] != "pevny" else old[i.ids])
        assert i.part.is_valid
        assert all(min(np.linalg.norm(expected-p, axis=1)) < 1e-6 for p in vertices(i.part))
    changed = s.assembly.to_dict()
    assert len(s._undo) == 1 and source.read_bytes() == raw
    s.undo()
    assert s.assembly.to_dict() == before
    s.redo()
    assert s.assembly.to_dict() == changed and len(s._undo) == 1


@pytest.mark.parametrize("direction", [None, [], [1, 2], [1, 2, 3, 4], [0, 0, 0],
                                       [float("nan"), 0, 1], [0, float("inf"), 1],
                                       [True, 0, 1], ["k", 0, 1], [object(), 0, 1]])
def test_bad_axis_is_atomic_even_for_full_turn_and_preserves_redo(request, direction):
    s, _ = request.getfixturevalue("group")
    s.turn_many_around(["a", "b"], "z", 30)
    s.undo()
    state = snapshot(s)
    with pytest.raises(AssemblyError, match="Směr osy"):
        s.turn_many_around(["a", "b"], direction, 360, center=[0, 0, 0])
    assert_unchanged(s, state)


def test_snapshot_axis_keeps_position_expressions_and_negative_z_orientation_expressions(request):
    s, _ = request.getfixturevalue("group")
    s.set_placement("a", position=["20*k", "k+2", "k-3"], rotation=["k", "2*k", "k+1"])
    state = snapshot(s)
    with pytest.raises(AssemblyError, match="výrazem"):
        s.turn_many_around(["a", "b"], (1, 2, 3), 45)
    assert_unchanged(s, state)
    s.turn_many_around(["a", "b"], (0, 0, -2), 90, center=[12, -5, 8])
    s.set_parameters({"k": 9, "uhel": 37.5})
    assert s.assembly.component("a").rotation[:2] == ["k", "2*k"]
    p = np.array([180, 11, 6])
    q = independent_rotation((0, 0, -1), 90)
    assert s._pose("a")[1] == pytest.approx([12, -5, 8]+q @ (p-[12, -5, 8]), abs=1e-6)
    assert evaluate(s.assembly.component("a").rotation[2], s.result.parameters) == -80


def test_arbitrary_axis_keeps_internal_constraints_and_refuses_external_motion(request):
    s = request.getfixturevalue("linked")
    pivot = np.array(s.rotation_center(["a", "b"]))
    before = {cid: s._pose(cid) for cid in ("a", "b", "c")}
    q = independent_rotation((1, 2, 3), 37.5)
    s.turn_many_around(["a", "b"], (1, 2, 3), 37.5)
    for cid in before:
        assert s._pose(cid)[1] == pytest.approx(
            pivot+q @ (before[cid][1]-pivot) if cid != "c" else before[cid][1], abs=1e-6)
    s.undo()
    state = snapshot(s)
    with pytest.raises(AssemblyError, match="Vazb"):
        s.turn_many_around(["a", "c"], (1, 2, 3), 90)
    assert_unchanged(s, state)


def test_fixed_source_change_and_full_turn_keep_entire_state_with_vector_axis(request):
    s, source = request.getfixturevalue("group")
    s.turn_many_around(["a", "b"], (1, 2, 3), 30)
    s.undo()
    state = snapshot(s)
    assert s.turn_many_around(["a", "b"], (1, 2, 3), 720) is state[1]
    assert_unchanged(s, state)
    with pytest.raises(AssemblyError, match="pevné"):
        s.turn_many_around(["a", "pevny"], (1, 2, 3), 30)
    assert_unchanged(s, state)
    write(source, part_data(height=20))
    with pytest.raises(AssemblyError, match="změnil zdroj"):
        s.turn_many_around(["a", "b"], (1, 2, 3), 30)
    assert_unchanged(s, state)


@pytest.mark.parametrize("angles", [(0, 0, 0), (30, 40, 50), (0, 90, 0), (180, 0, 0)])
def test_exact_cylinder_axis_includes_world_location_and_ignores_caps(angles):
    part = Pos(12, 23, 34)*Rot(*angles)*Cylinder(5, 10)
    axes = [_rotation_pick_cylinder(f.wrapped) for f in part.faces()]
    axes = [a for a in axes if a is not None]
    assert len(axes) == 1 and axes[0][0] == pytest.approx((12, 23, 34), abs=1e-12)
    # Nezávisle z krajních středů kružnic; znaménko i světové umístění jsou zachované.
    from skodacad.gui.viewer import _rotation_pick_point
    centers = [_rotation_pick_point(e.wrapped, "circle") for e in part.edges()]
    centers = np.array([p for p in centers if p is not None])
    d = np.array(axes[0][1])
    assert np.linalg.norm(d) == pytest.approx(1)
    assert sorted((centers-np.array(axes[0][0])) @ d) == pytest.approx([-5, 5])


def test_plane_cone_and_edge_are_not_approximated_as_cylinders():
    assert all(_rotation_pick_cylinder(f.wrapped) is None for f in Box(4, 4, 4).faces())
    assert all(_rotation_pick_cylinder(f.wrapped) is None for f in Cone(5, 2, 10).faces())
    assert _rotation_pick_cylinder(next(iter(Cylinder(5, 10).edges())).wrapped) is None


def cylinder_shape(part):
    return next(f.wrapped for f in part.faces() if _rotation_pick_cylinder(f.wrapped) is not None)


def test_viewer_pick_emits_axis_without_normal_selection_and_restores_detection(request):
    v, state = request.getfixturevalue("pick_viewer")
    state.shape = cylinder_shape(Pos(12, 23, 34)*Rot(30, 40, 50)*Cylinder(5, 10))
    received = []
    v.rotation_center_picked.connect(received.append)
    assert v.start_rotation_center_pick("cylinder", "request")
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (10, 12)))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (10, 12)))
    assert len(received) == 1 and received[0]["kind"] == "cylinder"
    assert received[0]["point"] == pytest.approx((12, 23, 34))
    assert np.linalg.norm(received[0]["direction"]) == pytest.approx(1)
    assert state.modes[-2:] == [2, 4] and v._center_pick is None
    assert v.picked_point == (99, 88, 77)


@pytest.mark.parametrize("direction", [(1, 2, 3), (0, 0, -1), (1, 0, 0)])
def test_oblique_ring_is_right_handed_and_edge_on_views_are_refused(direction):
    n, u, v = map(np.array, plane_frame(direction))
    assert np.cross(u, v) == pytest.approx(n)
    center = np.array([12, -5, 8])
    points = np.array(ring_points(center, direction, 10))
    assert (points-center) @ n == pytest.approx(np.zeros(len(points)), abs=1e-12)
    assert np.linalg.norm(points-center, axis=1) == pytest.approx(np.full(len(points), 10))
    p = center+10*(u*math.cos(.7)+v*math.sin(.7))
    assert angle_on_plane((*(p-20*n), *n), center, direction) == pytest.approx(math.degrees(.7))
    assert angle_on_plane((*(p-20*n), *u), center, direction) is None


def test_oblique_mouse_preview_and_committed_axis_use_same_world_line(request):
    v = request.getfixturevalue("viewer")
    direction = axis_direction((1, 2, 3))
    v.set_move_selection(dict(v._move_data, mode="rotate", axes=[3],
                              axis_direction=direction, step=15))
    assert [o.Text().ToExtString() for o in v._move_objects
            if isinstance(o, AIS_TextLabel)] == ["Osa válce"]
    received = []
    v.selection_rotated.connect(received.append)
    center = np.array(v._move_data["anchor"])
    radius = v._view.Convert(90)
    n, u, w = map(np.array, plane_frame(direction))

    def position(angle):
        p = center+radius*(u*math.cos(math.radians(angle))+w*math.sin(math.radians(angle)))
        return v._view.Convert(*p)

    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, position(45)))
    v._mouse_move(mouse(QEvent.Type.MouseMove, position(77)))
    assert v._selection_drag is not None and v._selection_drag["angle"] == 30
    transform = v._selection_drag["preview"].LocalTransformation()
    point = center+7*n+3*u
    moved = gp_Pnt(*point).Transformed(transform)
    expected = center+independent_rotation(direction, 30) @ (point-center)
    assert moved.Coord() == pytest.approx(expected, abs=1e-10)
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, position(77)))
    assert received == [{"token": "current", "axis": "cylinder", "angle": 30}]


def choose_cylinder(w):
    w.batch_rotation_axis.setCurrentIndex(3)
    w.rotation_axis_pick_button.click()
    ref = next(i for i in w.visible_instances() if i.ids == ("nozicka_3",))
    shape = cylinder_shape(ref.part)
    return {"token": w.viewer.center_pick["token"], "kind": "cylinder", "shape": shape,
            "point": (32, 17, -1.5), "direction": (1, 2, 3)}


def test_controller_preserves_parts_constraints_inputs_redo_and_uses_axis_for_both_actions(request):
    w = request.getfixturevalue("opened")
    ids = (("nozicka_1",), ("nozicka_2",))
    w.select_many(ids)
    w.batch_rotation_button.click()
    w.undo_action.trigger()
    state = snapshot(w.session)
    w.rotation_handles.click()
    w.rotation_center_edits[0].setText("x0")
    w.move_edits[0].setText("2,5")
    request = choose_cylinder(w)
    w._picks = [(request["shape"], (1, 2, 3))]
    w.viewer.rotation_center_picked.emit(request)
    assert_unchanged(w.session, state)
    assert w._selection == ids and w._picks == [(request["shape"], (1, 2, 3))]
    assert w.move_edits[0].text() == "2,5" and w.rotation_center_edits[0].text() == "x0"
    assert not w.rotation_center_mode.isEnabled() and not w.rotation_pick_button.isEnabled()
    assert not w.rotation_axis_pick_button.isChecked() and w.viewer.center_pick is None
    data = w.viewer.move_selection
    assert data["axes"] == [3] and data["axis_direction"] == axis_direction((1, 2, 3))
    assert data["anchor"] == (32, 17, -1.5)
    old = {i.ids: np.array(tuple(i.part.center())) for i in w.session.result.instances}
    pivot = np.array(data["anchor"])
    for mode in ("number", "mouse"):
        if mode == "number":
            w.batch_rotation_angle.setText("90")
            w.batch_rotation_button.click()
        else:
            w.viewer.selection_rotated.emit({"token": w.viewer.move_selection["token"],
                                             "axis": "cylinder", "angle": 90})
        q = independent_rotation((1, 2, 3), 90)
        for i in w.session.result.instances:
            assert tuple(i.part.center()) == pytest.approx(
                pivot+q @ (old[i.ids]-pivot) if i.ids in ids else old[i.ids], abs=1e-6)
        assert len(w.session._undo) == 1
        w.undo_action.trigger()
        assert w.session.assembly.to_dict() == state[0]
    w.batch_rotation_axis.setCurrentText("Z")
    assert w.rotation_center_mode.isEnabled() and w.rotation_pick_button.isEnabled()
    assert w.rotation_center_edits[0].text() == "x0"


@pytest.mark.parametrize("cause", ["escape", "stop", "axis", "selection", "hide", "alpha",
                                  "recipe", "result", "restart", "bad_direction", "bad_point"])
def test_cancel_or_stale_axis_never_overwrites_axis_or_selection(request, cause):
    w = request.getfixturevalue("opened")
    w.select_many((("nozicka_1",), ("nozicka_2",)))
    payload = choose_cylinder(w)
    if cause == "escape":
        w.clear_component_selection()
    elif cause == "stop":
        w.rotation_axis_pick_button.click()
    elif cause == "axis":
        w.batch_rotation_axis.setCurrentText("Z")
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
    elif cause == "bad_direction":
        payload["direction"] = (0, 0, 0)
    else:
        payload["point"] = (float("nan"), 0, 0)
    before, selected = snapshot(w.session), w._selection
    w.viewer.rotation_center_picked.emit(payload)
    assert w._rotation_cylinder is None and w._selection == selected
    assert_unchanged(w.session, before)
    if cause == "restart":
        token = w.viewer.center_pick["token"]
        w.viewer.rotation_center_pick_finished.emit(payload["token"])
        assert w.viewer.center_pick["token"] == token
        assert w.rotation_axis_pick_button.isChecked()


def test_axis_mode_needs_pick_and_axis_change_cancels_stale_rotation(request):
    w = request.getfixturevalue("opened")
    w.select_many((("nozicka_1",), ("nozicka_2",)))
    w.rotation_handles.click()
    payload = choose_cylinder(w)
    assert not w.batch_rotation_button.isEnabled() and not w.rotation_handles.isEnabled()
    assert w.rotation_axis_pick_button.isEnabled()
    w.viewer.rotation_center_picked.emit(payload)
    token = w.viewer.move_selection["token"]
    w.batch_rotation_axis.setCurrentText("Z")
    w.batch_rotation_axis.setCurrentIndex(3)
    before = snapshot(w.session)
    w.viewer.selection_rotated.emit({"token": token, "axis": "cylinder", "angle": 90})
    assert_unchanged(w.session, before)
    assert w.viewer.move_selection["axes"] == [3]


def test_oblique_axis_with_orientation_expressions_explains_and_disables_movement(request):
    w = request.getfixturevalue("opened")
    w.session.set_placement("nozicka_1", rotation=["h", 0, 0])
    w._refresh()
    w.select_many((("nozicka_1",), ("nozicka_2",)))
    w.rotation_handles.click()
    w.viewer.rotation_center_picked.emit(choose_cylinder(w))
    assert not w.batch_rotation_button.isEnabled() and not w.rotation_handles.isEnabled()
    assert w.rotation_axis_pick_button.isEnabled() and "výrazem" in w.batch_rotation_note.text()
    assert not w.viewer.move_selection["axes"]
