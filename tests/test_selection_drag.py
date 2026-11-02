"""P7.19: projekce a skutečné AIS prezentace; model se mění až v okně sestavy."""

from types import SimpleNamespace

import numpy as np
import pytest
from build123d import Box, Compound, Pos
from OCP.AIS import AIS_ColoredShape
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from skodacad.gui.guide_drag import axis_parameter
from skodacad.gui.viewer import OccViewer


@pytest.mark.parametrize("direction", "XYZ")
@pytest.mark.parametrize("d", [(2., -1., -2.), (1., 2., 3.), (0., 1., 0.)])
def test_xyz_axis_matches_independent_line_solve(direction, d):
    anchor, origin = np.array((20., -7., 40.)), np.array((13., 5., 2.))
    axis = np.eye(3)["XYZ".index(direction)]
    if np.linalg.norm(np.cross(axis, d)) == 0:
        assert axis_parameter((*origin, *d), anchor, direction) is None
    else:
        expected = np.linalg.lstsq(np.column_stack((axis, -np.array(d))), origin-anchor,
                                   rcond=None)[0][0]
        assert axis_parameter((*origin, *d), anchor, direction) == pytest.approx(expected)


def mouse(kind, xy, modifiers=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(kind, QPointF(*xy), QPointF(*xy), Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton, modifiers)


@pytest.fixture
def viewer(monkeypatch):
    app = QApplication.instance() or QApplication([])
    v = OccViewer()
    v._view = SimpleNamespace(
        Convert=lambda *a: a[0]/10 if len(a) == 1 else ((a[0]-a[2])*10, (a[1]-.5*a[2])*10),
        ConvertWithProj=lambda x, y: (x/10, y/10, 0., 1., .5, 1.),
        StartRotation=lambda *_: None, Redraw=lambda: None)
    v._context = SimpleNamespace(**{name: lambda *a: None for name in (
        "Display", "Deactivate", "SetZLayer", "Remove", "UnhilightSelected", "ClearDetected",
        "RecomputePrsOnly", "HilightSelected")})
    shapes = [Box(4, 4, 4), Pos(10, 0, 0)*Box(4, 4, 4)]
    v._ais = AIS_ColoredShape(Compound(children=shapes).wrapped)
    v._transparent_parts = [(shapes[0].wrapped, .35), (shapes[1].wrapped, .85)]
    monkeypatch.setattr(v, "_pixel_scale", lambda: 1.)
    v.set_move_selection({"shapes": [s.wrapped for s in shapes], "anchor": (5., 0., 0.),
                          "step": .5, "token": "current"})
    yield v
    v.cancel_selection_drag()
    v._view = None
    v.close()
    app.processEvents()


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("ratio", [1., 1.25, 2.])
def test_mouse_xyz_preview_and_single_release_use_same_delta(viewer, monkeypatch, axis, ratio):
    v = viewer
    monkeypatch.setattr(v, "_pixel_scale", lambda: ratio)
    v._draw_move_handles()
    tip = next(tip for a, tip in v._move_tips if a == axis)
    start = tuple(p/ratio for p in v._view.Convert(*tip))
    target = list(tip)
    target[axis] += 2.7
    end = tuple(p/ratio for p in v._view.Convert(*target))
    received = []
    v.selection_moved.connect(received.append)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, start))
    assert v._selection_drag is not None
    for shape in v._move_data["shapes"]:
        assert v._ais.CustomAspects(shape).IsHidden()
    v._mouse_move(mouse(QEvent.Type.MouseMove, end))
    drag = v._selection_drag
    delta = [0., 0., 0.]
    delta[axis] = 2.5
    assert drag["delta"] == delta and not received
    translation = drag["preview"].LocalTransformation().TranslationPart()
    assert (translation.X(), translation.Y(), translation.Z()) == tuple(delta)
    assert [drag["preview"].CustomAspects(s).ShadingAspect().Aspect().FrontMaterial().Transparency()
            for s in v._move_data["shapes"]] == pytest.approx([.35, .85])
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, end))
    assert received == [{"token": "current", "delta": delta}]
    assert v._selection_drag is None
    assert all(not v._ais.CustomAspects(s).IsHidden() for s in v._move_data["shapes"])


@pytest.mark.parametrize("cause", ["click", "escape", "focus", "replace", "hide", "resize"])
def test_cancel_never_emits_model_change(viewer, monkeypatch, cause):
    v = viewer
    start = v._view.Convert(*v._move_tips[0][1])
    end = (start[0]+30, start[1])
    received = []
    v.selection_moved.connect(received.append)
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
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, start if cause == "click" else end))
    assert not received and v._selection_drag is None


def test_substep_move_is_noop_and_alt_shift_keep_existing_controls(viewer):
    v = viewer
    v._move_data["step"] = 1000.
    start = v._view.Convert(*v._move_tips[0][1])
    events = []
    v.selection_moved.connect(events.append)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, start))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (start[0]+30, start[1])))
    assert not events
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, start, Qt.KeyboardModifier.ShiftModifier))
    assert v._selection_drag is None
