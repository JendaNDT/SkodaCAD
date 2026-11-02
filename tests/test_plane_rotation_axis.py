"""P7.27: orientovaná kolmice k přesné rovině v místě kliknutí, bez změny výběru."""

import math
from types import SimpleNamespace

import numpy as np
import pytest
from build123d import Box, Cone, Cylinder, GeomType, Pos, Rot, Sphere
from OCP.AIS import AIS_TextLabel
from OCP.gp import gp_Pnt
from PySide6.QtCore import QEvent

from skodacad.gui.rotation_drag import plane_frame
from skodacad.gui.viewer import _rotation_pick_plane
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
from test_rotation_center_pick import pick_viewer  # noqa: F401
from test_selection_drag import mouse, viewer  # noqa: F401


@pytest.mark.parametrize("rotation", [(0, 0, 0), (30, 40, 50)])
@pytest.mark.parametrize("axis,sign", [(0, -1), (0, 1), (1, -1), (1, 1), (2, -1), (2, 1)])
def test_plane_uses_world_ray_intersection_and_oriented_normal(rotation, axis, sign):
    part = Box(10, 12, 14)
    face = next(f for f in part.faces() if tuple(f.normal_at())[axis] == sign)
    face = Pos(12, 23, 34)*Rot(*rotation)*face
    center, normal = np.array(tuple(face.center())), np.array(tuple(face.normal_at()))
    _n, u, v = map(np.array, plane_frame(tuple(normal)))
    target = center+1.25*u-2.5*v  # záměrně mimo těžiště plochy
    ray = (*map(float, target+10*normal+u), *map(float, -10*normal-u))
    point, direction = _rotation_pick_plane(face.wrapped, tuple(target+.1*normal), ray)
    assert point == pytest.approx(target, abs=1e-12)
    assert direction == pytest.approx(normal, abs=1e-12)
    reversed_axis = _rotation_pick_plane(face.wrapped.Reversed(), tuple(target), ray)
    assert reversed_axis[0] == point
    assert reversed_axis[1] == pytest.approx(-normal, abs=1e-12)


def test_plane_trim_and_holes_are_respected_and_bad_rays_do_not_invent_anchor():
    part = Box(20, 20, 4)-Cylinder(3, 10)
    face = next(f for f in part.faces() if f.geom_type == GeomType.PLANE
                and f.normal_at().Z > .99)
    for x in (0, 99):  # díra a místo mimo skutečnou plochu
        assert _rotation_pick_plane(face.wrapped, (x, 0, 2), (x, 0, 12, 0, 0, -1)) is None
    for ray in (None, (0, 0, 0, 0, 0, 0), (0, 0, 12, 1, 0, 0),
                (0, 0, float("nan"), 0, 0, -1)):
        assert _rotation_pick_plane(face.wrapped, (5, 0, 2), ray) is None
    assert _rotation_pick_plane(face.wrapped, None, (5, 0, 12, 0, 0, -1)) is None
    assert _rotation_pick_plane(face.wrapped, (5, 0, 2), (5, 0, 12, 0, 0, -1))[0] == (5, 0, 2)


@pytest.mark.parametrize("part", [Cylinder(5, 10), Cone(5, 2, 10), Sphere(5)])
def test_curved_faces_are_refused_without_tangent_plane_approximation(part):
    for face in part.faces():
        if face.geom_type != GeomType.PLANE:
            assert _rotation_pick_plane(face.wrapped, (1, 2, 3), (1, 2, 30, 0, 0, -1)) is None
    assert _rotation_pick_plane(next(iter(part.edges())).wrapped) is None


@pytest.mark.parametrize("ratio", [1., 1.25, 2.])
def test_viewer_plane_pick_preserves_selection_and_uses_pixel_ray(request, monkeypatch, ratio):
    v, state = request.getfixturevalue("pick_viewer")
    face = next(f for f in Box(10, 10, 4).faces() if f.normal_at().Z > .99)
    state.shape = face.wrapped
    v._context.MainSelector = lambda: SimpleNamespace(
        NbPicked=lambda: 1, PickedPoint=lambda _: gp_Pnt(1, 2, 2.1))
    rays = []
    v._view.ConvertWithProj = lambda x, y: rays.append((x, y)) or (1, 2, 12, 0, 0, -1)
    monkeypatch.setattr(v, "_pixel_scale", lambda: ratio)
    received, selected = [], []
    v.rotation_center_picked.connect(received.append)
    v.selection_changed.connect(selected.append)
    v.selection_cleared.connect(lambda: selected.append("clear"))
    assert v.start_rotation_center_pick("plane", "request")
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (10, 12)))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (10, 12)))
    assert received == [{"token": "request", "kind": "plane", "shape": face.wrapped,
                         "point": (1., 2., 2.), "direction": (0., 0., 1.)}]
    assert rays == [(int(10*ratio), int(12*ratio))]
    assert not selected and v.picked_point == (99, 88, 77)
    assert v._center_pick is None and state.modes[-2:] == [2, 4] and v._move_objects


def test_curved_face_and_miss_keep_plane_picker_armed(request):
    v, state = request.getfixturevalue("pick_viewer")
    state.shape = next(f.wrapped for f in Cylinder(5, 10).faces()
                       if f.geom_type == GeomType.CYLINDER)
    received = []
    v.rotation_center_picked.connect(received.append)
    v.start_rotation_center_pick("plane", "request")
    for detected in (True, False):
        state.detected = detected
        v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (10, 12)))
        v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (10, 12)))
        assert v._center_pick is not None and not received


@pytest.mark.parametrize("ratio", [1., 1.25, 2.])
def test_plane_ring_preview_and_release_share_negative_oblique_axis(request, monkeypatch, ratio):
    v = request.getfixturevalue("viewer")
    monkeypatch.setattr(v, "_pixel_scale", lambda: ratio)
    direction = (-2., 1., -4.)
    v.set_move_selection(dict(v._move_data, mode="rotate", axes=[3], axis_kind="plane",
                              axis_direction=direction, step=15))
    assert [o.Text().ToExtString() for o in v._move_objects
            if isinstance(o, AIS_TextLabel)] == ["Kolmice k ploše"]
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
    assert received == [{"token": "current", "axis": "plane", "angle": 30}]


def choose_plane(w):
    w.batch_rotation_axis.setCurrentIndex(5)
    w.rotation_axis_pick_button.click()
    ref = next(i for i in w.visible_instances() if i.ids == ("nozicka_3",))
    matrix, _origin = w.session._pose("nozicka_3")
    normal = matrix @ np.array([0., 0., 1.])
    face = next(f for f in ref.part.faces() if f.geom_type == GeomType.PLANE
                and np.dot(tuple(f.normal_at()), normal) > .99)
    point = np.array(tuple(face.center()))+matrix @ np.array([1., .5, 0.])
    return {"token": w.viewer.center_pick["token"], "kind": "plane", "shape": face.wrapped,
            "point": tuple(point), "direction": tuple(normal)}


@pytest.mark.parametrize("mode,angle", [("number", 90), ("mouse", 30)])
def test_plane_snapshot_reverse_physical_motion_and_one_undo_redo(request, mode, angle):
    w = prepare_window(request)
    w.batch_rotation_button.click()
    w.undo_action.trigger()
    w.rotation_handles.click()
    payload = choose_plane(w)
    w._picks = [(payload["shape"], (1, 2, 3))]
    w.move_edits[0].setText("2,5")
    state, selected = snapshot(w.session), w._selection
    w.viewer.rotation_center_picked.emit(payload)
    assert_unchanged(w.session, state)
    assert w._selection == selected and w._picks == [(payload["shape"], (1, 2, 3))]
    assert w.move_edits[0].text() == "2,5" and w.rotation_axis_reverse_button.isEnabled()
    pivot, direction = w._rotation_plane
    w.rotation_axis_reverse_button.click()
    assert_unchanged(w.session, state)
    old = {i.ids: vertices(i.part) for i in w.session.result.instances}
    q = independent_rotation(direction, -angle)
    if mode == "number":
        w.batch_rotation_angle.setText(str(angle))
        w.batch_rotation_button.click()
    else:
        w.viewer.selection_rotated.emit({"token": w.viewer.move_selection["token"],
                                         "axis": "plane", "angle": angle})
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


@pytest.mark.parametrize("cause", ["escape", "stop", "reverse", "away_back", "hide",
                                  "selection", "result", "restart", "bad_shape", "bad_direction"])
def test_stale_plane_pick_cannot_replace_previous_snapshot(request, cause):
    w = prepare_window(request)
    w.viewer.rotation_center_picked.emit(choose_plane(w))
    payload = choose_plane(w)
    if cause == "escape":
        w.clear_component_selection()
    elif cause == "stop":
        w.rotation_axis_pick_button.click()
    elif cause == "reverse":
        w.rotation_axis_reverse_button.click()
    elif cause == "away_back":
        w.batch_rotation_axis.setCurrentIndex(3)
        w.batch_rotation_axis.setCurrentIndex(5)
    elif cause == "hide":
        w.set_component_visible(("nozicka_3",), False)
    elif cause == "selection":
        w.select_many((("nozicka_3",), ("nozicka_4",)))
    elif cause == "result":
        w.session.rebuild()
    elif cause == "restart":
        w.rotation_axis_pick_button.click()
        w.rotation_axis_pick_button.click()
    elif cause == "bad_shape":
        payload["shape"] = next(iter(Box(2, 2, 2).faces())).wrapped
    else:
        payload["direction"] = (float("nan"), 0, 1)
    axis, selected, before = w._rotation_plane, w._selection, snapshot(w.session)
    w.viewer.rotation_center_picked.emit(payload)
    assert w._rotation_plane == axis and w._selection == selected
    assert_unchanged(w.session, before)
    if cause == "restart":
        token = w.viewer.center_pick["token"]
        w.viewer.rotation_center_pick_finished.emit(payload["token"])
        assert w.viewer.center_pick["token"] == token and w.rotation_axis_pick_button.isChecked()


def test_three_independent_axis_snapshots_and_wrong_kind_drag(request):
    w = prepare_window(request)
    w.rotation_handles.click()
    w.viewer.rotation_center_picked.emit(choose_plane(w))
    plane = w._rotation_plane
    for pick in (choose_line, choose_cylinder):
        w.viewer.rotation_center_picked.emit(pick(w))
    for index, kind in ((5, "plane"), (4, "line"), (3, "cylinder")):
        w.batch_rotation_axis.setCurrentIndex(index)
        assert w._picked_rotation_axis() == getattr(w, f"_rotation_{kind}")
        assert w.viewer.move_selection["axis_kind"] == kind
    w.batch_rotation_axis.setCurrentIndex(5)
    assert w._picked_rotation_axis() == plane
    before = snapshot(w.session)
    w.viewer.selection_rotated.emit({"token": w.viewer.move_selection["token"],
                                     "axis": "cylinder", "angle": 90})
    assert_unchanged(w.session, before)


@pytest.mark.parametrize("tilted", [False, True])
def test_plane_respects_orientation_expressions_and_keeps_reverse_available(request, tilted):
    w = prepare_window(request, tilted)
    w.session.set_placement("nozicka_1", rotation=["h", 0, 0])
    w._refresh()
    w.viewer.rotation_center_picked.emit(choose_plane(w))
    w.rotation_axis_reverse_button.click()
    assert w.rotation_axis_reverse_button.isEnabled() and w.rotation_axis_pick_button.isEnabled()
    assert w.batch_rotation_button.isEnabled() == (not tilted)
    assert w.rotation_handles.isEnabled() == (not tilted)
    if tilted:
        assert "výrazem" in w.batch_rotation_note.text()


def test_plane_on_nested_visible_part_keeps_parent_selection_and_world_axis(request):
    w = request.getfixturevalue("nested_isolation")
    selected = (("a",), ("b",))
    w.select_many(selected)
    w.batch_rotation_axis.setCurrentIndex(5)
    w.rotation_axis_pick_button.click()
    child = next(i for i in w.visible_instances() if i.ids[:1] == ("b",))
    face = next(f for f in child.part.faces() if f.geom_type == GeomType.PLANE)
    p, n = np.array(tuple(face.center())), np.array(tuple(face.normal_at()))
    point, direction = _rotation_pick_plane(face.wrapped, tuple(p), (*map(float, p+10*n),
                                                                  *map(float, -n)))
    before = snapshot(w.session)
    w.viewer.rotation_center_picked.emit({"token": w.viewer.center_pick["token"], "kind": "plane",
                                         "shape": face.wrapped, "point": point,
                                         "direction": direction})
    assert w._rotation_plane == (point, direction) and w._selection == selected
    assert point == pytest.approx(p) and direction == pytest.approx(n)
    assert_unchanged(w.session, before)
