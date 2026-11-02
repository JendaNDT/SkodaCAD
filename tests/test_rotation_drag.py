"""Prstence: pravotočivá projekce, plynulé úhly, AIS náhled a jedno potvrzení."""

import math

import pytest
from OCP.AIS import AIS_Shape, AIS_TextLabel
from OCP.gp import gp_Pnt
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from skodacad.gui.rotation_drag import (
    advance_angle,
    angle_on_plane,
    nearest_ring,
    plane_axes,
    snapped_angle,
)
from test_selection_drag import mouse, viewer  # noqa: F401


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("angle", [-175, -30, 0, 40, 175])
def test_angle_is_right_handed_in_every_world_plane(axis, angle):
    center = (3., -7., 11.)
    point = list(center)
    u, v = plane_axes(axis)
    point[u] += 20*math.cos(math.radians(angle))
    point[v] += 20*math.sin(math.radians(angle))
    origin = list(point)
    origin[axis] -= 50
    d = [0., 0., 0.]
    d[axis] = 3.
    assert angle_on_plane((*origin, *d), center, axis) == pytest.approx(angle)
    d[axis] = -3
    origin[axis] += 100
    assert angle_on_plane((*origin, *d), center, axis) == pytest.approx(angle)


def test_degenerate_plane_and_center_are_refused():
    assert angle_on_plane((1, 2, 3, 1, 0, .001), (0, 0, 0), 2) is None
    assert angle_on_plane((0, 0, 3, 0, 0, -1), (0, 0, 0), 2, .1) is None
    assert angle_on_plane((1, 2, 3, 0, 0, 0), (0, 0, 0), 2) is None
    assert angle_on_plane((1, 2, 3, 0, 0, float("nan")), (0, 0, 0), 2) is None
    assert nearest_ring([[(-10, 0), (10, 0)], [(0, -10), (0, 10)]], (0, 0)) == -1
    assert nearest_ring([[(-10, 0), (10, 0)]], (20, 20)) is None
    assert nearest_ring([[(-10, 0), (10, 0)]], (2, 4)) == 0


@pytest.mark.parametrize("angle,step,expected", [(7.5, 15, 15), (-7.5, 15, -15),
                                                 (17.2, 15, 15), (359.99999999999, 0, 360),
                                                 (.15, .1, .2)])
def test_step_and_crossing_half_turn(angle, step, expected):
    assert snapped_angle(angle, step) == expected
    assert advance_angle(170, -170, 5) == 25
    assert advance_angle(-170, 170, 5) == -15


@pytest.mark.parametrize("step", [-1, 180.001, float("inf"), float("nan")])
def test_invalid_step_is_a_czech_degree_error(step):
    with pytest.raises(ValueError, match="Krok otáčení"):
        snapped_angle(30, step)


def prepare(request, monkeypatch, ratio=1.):
    v = request.getfixturevalue("viewer")
    monkeypatch.setattr(v, "_pixel_scale", lambda: ratio)
    data = dict(v._move_data, mode="rotate", axes=[0, 1, 2], step=15.)
    v.set_move_selection(data)
    v._highlight = AIS_Shape(v._ais.Shape())
    return v


def position(v, axis, degrees):
    center = v._move_data["anchor"]
    radius = v._view.Convert(round(90*v._pixel_scale()))
    u, w = plane_axes(axis)
    p = list(center)
    p[u] += radius*math.cos(math.radians(degrees))
    p[w] += radius*math.sin(math.radians(degrees))
    return tuple(x/v._pixel_scale() for x in v._view.Convert(*p))


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("ratio", [1., 1.25, 2.])
def test_mouse_preview_rotates_about_center_and_emits_once(request, monkeypatch, axis, ratio):
    v = prepare(request, monkeypatch, ratio)
    received, moved = [], []
    v.selection_rotated.connect(received.append)
    v.selection_moved.connect(moved.append)
    start, end = position(v, axis, 45), position(v, axis, 77)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, start))
    assert v._selection_drag is not None and v._selection_drag["axis"] == axis
    v._mouse_move(mouse(QEvent.Type.MouseMove, end))
    drag = v._selection_drag
    assert drag is not None and drag["angle"] == 30 and not received and not moved
    center = v._move_data["anchor"]
    transform = drag["preview"].LocalTransformation()
    c = gp_Pnt(*center).Transformed(transform)
    assert (c.X(), c.Y(), c.Z()) == pytest.approx(center, abs=1e-10)
    u, w = plane_axes(axis)
    original, expected = list(center), list(center)
    original[u] += 10
    expected[u] += 10*math.cos(math.radians(30))
    expected[w] += 10*math.sin(math.radians(30))
    p = gp_Pnt(*original).Transformed(transform)
    assert (p.X(), p.Y(), p.Z()) == pytest.approx(expected, abs=1e-10)
    hp = gp_Pnt(*original).Transformed(v._highlight.LocalTransformation())
    assert (hp.X(), hp.Y(), hp.Z()) == pytest.approx(expected, abs=1e-10)
    assert all(v._ais.CustomAspects(s).IsHidden() for s in v._move_data["shapes"])
    assert [drag["preview"].CustomAspects(s).ShadingAspect().Aspect().FrontMaterial().Transparency()
            for s in v._move_data["shapes"]] == pytest.approx([.35, .85])
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, end))
    assert received == [{"token": "current", "axis": "xyz"[axis], "angle": 30}]
    assert not moved and v._selection_drag is None
    assert all(not v._ais.CustomAspects(s).IsHidden() for s in v._move_data["shapes"])
    assert v._highlight.LocalTransformation().Form().name == "gp_Identity"


@pytest.mark.parametrize("turns", [-2, -1, 1, 2])
def test_continuous_full_turns_do_not_emit_a_model_change(request, monkeypatch, turns):
    v = prepare(request, monkeypatch)
    received = []
    v.selection_rotated.connect(received.append)
    start = position(v, 2, 45)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, start))
    for k in range(1, abs(turns)*12):
        v._mouse_move(mouse(QEvent.Type.MouseMove, position(v, 2, 45+math.copysign(30*k, turns))))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, start))
    assert not received and v._selection_drag is None


@pytest.mark.parametrize("cause", ["click", "escape", "focus", "hide", "replace", "resize",
                                    "center", "step"])
def test_cancel_restores_presentations_without_commit(request, monkeypatch, cause):
    v = prepare(request, monkeypatch)
    received = []
    v.selection_rotated.connect(received.append)
    start, end = position(v, 2, 45), position(v, 2, 77)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, start))
    if cause != "click":
        v._mouse_move(mouse(QEvent.Type.MouseMove, end))
    if cause == "escape":
        v.clear_selection()
    elif cause in ("focus", "hide"):
        QApplication.sendEvent(v._surface, QEvent(QEvent.Type.FocusOut if cause == "focus"
                                                 else QEvent.Type.Hide))
    elif cause == "replace":
        v.set_move_selection(None)
    elif cause == "resize":
        monkeypatch.setattr(v, "_sync_size", lambda: None)
        v._resized()
    elif cause == "center":
        v._mouse_move(mouse(QEvent.Type.MouseMove, v._view.Convert(*v._move_data["anchor"])))
    elif cause == "step":
        v.set_move_selection(dict(v._move_data, step=5.))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, start if cause == "click" else end))
    assert not received and v._selection_drag is None
    assert v._highlight.LocalTransformation().Form().name == "gp_Identity"


def test_crossing_and_edge_on_axes_do_not_start_an_ambiguous_drag(request, monkeypatch):
    v = prepare(request, monkeypatch)
    # Kladná osa Y leží současně na prstenci X a Z, ale mimo kuličky.
    p = list(v._move_data["anchor"])
    p[1] += v._view.Convert(90)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, v._view.Convert(*p)))
    assert v._selection_drag is None and v._press is None
    v._view.ConvertWithProj = lambda *_: (0, 0, 0, 1., 0., 0.)
    v._draw_move_handles()
    assert [axis for axis, _tip in v._move_tips] == [0]


def test_ring_labels_are_outside_all_arcs_and_ball_handles(request, monkeypatch):
    v = prepare(request, monkeypatch)
    center = v._view.Convert(*v._move_data["anchor"])
    labels = [o for o in v._move_objects if isinstance(o, AIS_TextLabel)]
    assert [label.Text().ToExtString() for label in labels] == list("XYZ")
    for label in labels:
        p = label.Position()
        screen = v._view.Convert(p.X(), p.Y(), p.Z())
        assert math.dist(screen, center)/v._pixel_scale() == pytest.approx(110., abs=1.)
