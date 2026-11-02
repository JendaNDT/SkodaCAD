"""Přesná geometrie bodu a jednorázový výběr bez změny komponent nebo historie."""

from types import SimpleNamespace

import numpy as np
import pytest
from build123d import Box, Cylinder, Pos, Rot
from OCP.AIS import AIS_Shape
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt
from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from skodacad.gui.viewer import _rotation_pick_point
from test_assembly_gui import (  # noqa: F401
    app,
    dialogs,
    main_window,
    nested_isolation,
    opened,
    project,
)
from test_selection_drag import viewer  # noqa: F401


def circle(center=(12, 23, 34), arc=False):
    curve = gp_Circ(gp_Ax2(gp_Pnt(*center), gp_Dir(0, 0, 1)), 5)
    return (BRepBuilderAPI_MakeEdge(curve, 0., 1.).Edge() if arc
            else BRepBuilderAPI_MakeEdge(curve).Edge())


@pytest.mark.parametrize("rotation,axis", [((0, 90, 0), (1, 0, 0)),
                                          ((90, 0, 0), (0, -1, 0)),
                                          ((0, 0, 35), (0, 0, 1))])
def test_circle_centers_follow_world_instance_placement(rotation, axis):
    part = Pos(12, 23, 34)*Rot(*rotation)*Cylinder(5, 10)
    centers = [_rotation_pick_point(e.wrapped, "circle") for e in part.edges()]
    centers = [p for p in centers if p is not None]
    expected = [np.array([12, 23, 34])+sign*5*np.array(axis) for sign in (-1, 1)]
    assert len(centers) == 2
    assert all(any(np.allclose(p, q, atol=1e-10, rtol=0) for q in centers) for p in expected)


def test_arc_center_and_exact_vertex_are_not_clicked_mesh_positions():
    assert _rotation_pick_point(circle(arc=True), "circle", (99, 88, 77)) == (12, 23, 34)
    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(2, -3, 4)).Vertex()
    assert _rotation_pick_point(vertex, "vertex", (99, 88, 77)) == (2, -3, 4)
    line = BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0), gp_Pnt(1, 2, 3)).Edge()
    assert _rotation_pick_point(line, "circle") is None
    assert _rotation_pick_point(vertex, "circle") is None


def test_face_hit_is_refined_to_actual_curved_surface_along_camera_ray():
    part = Pos(12, 23, 34)*Cylinder(5, 10)
    # x=15: přesný průsečík válce má y=23+sqrt(25-9)=27, nikoli 26.9 ze sítě.
    points = [_rotation_pick_point(f.wrapped, "face", (15, 26.9, 34),
                                   (15, 40, 34, 0, -1, 0)) for f in part.faces()]
    assert [p for p in points if p is not None] == [(15, 27, 34)]
    face = next(iter(Box(4, 4, 4).faces())).wrapped
    assert _rotation_pick_point(face, "face", (0, 0, 0), (100, 100, 100, 1, 0, 0)) is None
    assert _rotation_pick_point(face, "face", (0, 0, 0), (0, 0, 0, 0, 0, 0)) is None
    assert _rotation_pick_point(face, "face", None, (0, 0, 0, 0, 0, 1)) is None


def mouse(kind, xy, button=Qt.MouseButton.LeftButton, modifiers=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(kind, QPointF(*xy), QPointF(*xy), button, button, modifiers)


@pytest.fixture
def pick_viewer(request, monkeypatch):
    v = request.getfixturevalue("viewer")
    state = SimpleNamespace(shape=circle(), detected=True, moves=[], modes=[], pan=[])
    context = v._context
    context.ActivatedModes = lambda ais, saved: [saved.Append(i) for i in (2, 4)]
    context.Activate = lambda ais, mode: state.modes.append(mode)
    context.MoveTo = lambda x, y, *_: state.moves.append((x, y))
    context.HasDetected = lambda: state.detected
    context.HasDetectedShape = lambda: state.detected
    context.DetectedShape = lambda: state.shape
    context.HighlightStyle = lambda _: SimpleNamespace(SetDisplayMode=lambda _: None)
    context.MainSelector = lambda: SimpleNamespace(NbPicked=lambda: 1,
                                                   PickedPoint=lambda _: gp_Pnt(17, 23, 34))
    v._view.Pan = lambda *args: state.pan.append(args)
    v._view.Rotation = lambda *_: None
    v.picked_point = (99, 88, 77)
    yield v, state
    v.cancel_rotation_center_pick()


@pytest.mark.parametrize("kind,typ", [("circle", TopAbs_EDGE), ("vertex", TopAbs_VERTEX)])
@pytest.mark.parametrize("ratio", [1., 1.25, 2.])
def test_one_click_preserves_normal_selection_and_restores_modes(pick_viewer, monkeypatch,
                                                                 kind, typ, ratio):
    v, state = pick_viewer
    monkeypatch.setattr(v, "_pixel_scale", lambda: ratio)
    if kind == "vertex":
        state.shape = BRepBuilderAPI_MakeVertex(gp_Pnt(2, -3, 4)).Vertex()
    expected = (12, 23, 34) if kind == "circle" else (2, -3, 4)
    received, selection, order = [], [], []
    v.rotation_center_picked.connect(lambda r: (received.append(r), order.append("point")))
    v.rotation_center_pick_finished.connect(lambda _token: order.append("finished"))
    v.selection_changed.connect(selection.append)
    v.selection_cleared.connect(lambda: selection.append("cleared"))
    assert v.start_rotation_center_pick(kind, "token")
    assert not v._move_objects and state.modes == [AIS_Shape.SelectionMode_s(typ)]
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (10, 12)))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (10, 12)))
    assert v._center_pick is None and not selection and v.picked_point == (99, 88, 77)
    assert received == [{"token": "token", "kind": kind, "point": expected,
                         "shape": state.shape}]
    assert order == ["point", "finished"] and state.moves[-1] == (int(10*ratio), int(12*ratio))
    assert state.modes[-2:] == [2, 4] and v._move_objects
    assert v._surface.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_miss_or_wrong_edge_keeps_pick_armed_then_drag_pans_without_selecting(pick_viewer):
    v, state = pick_viewer
    received = []
    v.rotation_center_picked.connect(received.append)
    v.start_rotation_center_pick("circle", "token")
    for detected in (False, True):
        state.detected = detected
        state.shape = BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0), gp_Pnt(1, 2, 3)).Edge()
        v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (10, 12)))
        v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (10, 12)))
        assert v._center_pick is not None and not received
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (10, 12),
                         modifiers=Qt.KeyboardModifier.ShiftModifier))
    v._mouse_move(mouse(QEvent.Type.MouseMove, (30, 40),
                        modifiers=Qt.KeyboardModifier.ShiftModifier))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (30, 40)))
    assert state.pan and v._center_pick is not None and not received


@pytest.mark.parametrize("cause", ["escape", "right", "resize", "hide", "deactivate",
                                  "data", "alpha", "stop"])
def test_pick_cancel_restores_everything_without_a_point(pick_viewer, monkeypatch, cause):
    v, state = pick_viewer
    received, selection = [], []
    v.rotation_center_picked.connect(received.append)
    v.selection_cleared.connect(lambda: selection.append("clear"))
    v.start_rotation_center_pick("vertex", "token")
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
    else:
        v.cancel_rotation_center_pick()
    assert v._center_pick is None and not received and not selection
    assert v.picked_point == (99, 88, 77) and state.modes[-2:] == [2, 4]


@pytest.mark.parametrize("kind", ["circle", "vertex", "face"])
def test_controller_accepts_visible_reference_without_changing_selected_parts(request, kind):
    w = request.getfixturevalue("opened")
    ids = (("nozicka_1",), ("nozicka_2",))
    w.select_many(ids)
    w.batch_rotation_button.click()
    w.undo_action.trigger()  # také nevymazat Znovu
    before, result, redo = w.session.assembly.to_dict(), w.session.result, list(w.session._redo)
    w.rotation_handles.click()
    reference = next(i for i in w.visible_instances() if i.ids == ("krabicka",))
    pieces = {"circle": "edges", "vertex": "vertices", "face": "faces"}
    shape = next(iter(getattr(reference.part, pieces[kind])())).wrapped
    w._picks = [(shape, (1, 2, 3))]
    w.rotation_pick_kind.setCurrentIndex(w.rotation_pick_kind.findData(kind))
    w.rotation_pick_button.click()
    token = w.viewer.center_pick["token"]
    w.viewer.rotation_center_picked.emit({"token": token, "kind": kind,
                                         "shape": shape, "point": (12.5, -31, 18)})
    assert w._selection == ids and w.session.assembly.to_dict() == before
    assert w.session.result is result and w.session._redo == redo and not w.session.can_undo
    assert w.rotation_center_mode.currentText() == "Vlastní bod"
    assert [float(f.text()) for f in w.rotation_center_edits] == [12.5, -31, 18]
    assert w.viewer.move_selection["anchor"] == (12.5, -31, 18)
    assert not w.rotation_pick_button.isChecked() and w.viewer.center_pick is None
    assert w._picks == [(shape, (1, 2, 3))]
    old = {i.ids: tuple(i.part.center()) for i in result.instances}
    w.batch_rotation_angle.setText("90")
    w.batch_rotation_button.click()
    for i in w.session.result.instances:
        x, y, z = old[i.ids]
        expected = (12.5-(y+31), -31+(x-12.5), z) if i.ids in ids else (x, y, z)
        assert tuple(i.part.center()) == pytest.approx(expected, abs=1e-6)
    assert len(w.session._undo) == 1
    w.undo_action.trigger()
    assert w.session.assembly.to_dict() == before and not w.session.can_undo


@pytest.mark.parametrize("cause", ["escape", "stop", "center", "kind", "selection", "result",
                                  "recipe", "hide", "alpha", "restart", "hidden_shape"])
def test_stale_pick_does_not_overwrite_previous_center_or_selection(request, cause):
    w = request.getfixturevalue("opened")
    w.select_many((("nozicka_1",), ("nozicka_2",)))
    w.rotation_center_mode.setCurrentIndex(2)
    w.rotation_center_edits[0].setText("9")
    reference = next(i for i in w.visible_instances() if i.ids == ("krabicka",))
    shape = next(iter(reference.part.edges())).wrapped
    w.rotation_pick_button.click()
    token = w.viewer.center_pick["token"]
    if cause == "escape":
        w.clear_component_selection()
    elif cause == "stop":
        w.rotation_pick_button.click()
    elif cause == "center":
        w.rotation_center_edits[0].setText("10")
    elif cause == "kind":
        w.rotation_pick_kind.setCurrentIndex(1)
    elif cause == "selection":
        w.select_many((("nozicka_3",), ("nozicka_4",)))
    elif cause == "result":
        w.session.rebuild()
    elif cause == "recipe":
        w.session.assembly.name += " změna"
    elif cause == "hide":
        w.set_component_visible(("nozicka_1",), False)
    elif cause == "hidden_shape":
        w.set_component_visible(("krabicka",), False)
    elif cause == "alpha":
        w.set_component_transparency(("nozicka_1",), 35)
    else:
        w.rotation_pick_button.click()
        w.rotation_pick_button.click()
        assert w.viewer.center_pick["token"] != token
    before, selected = w.session.assembly.to_dict(), w._selection
    previous = [f.text() for f in w.rotation_center_edits]
    w.viewer.rotation_center_picked.emit({"token": token, "kind": "circle", "shape": shape,
                                         "point": (12.5, -31, 18)})
    assert w.session.assembly.to_dict() == before and w._selection == selected
    assert [f.text() for f in w.rotation_center_edits] == previous and not w.session.can_undo
    if cause == "restart":
        current = w.viewer.center_pick["token"]
        assert current != token and w.rotation_pick_button.isChecked()
        w.viewer.rotation_center_pick_finished.emit(token)
        assert w.viewer.center_pick["token"] == current and w._rotation_pick_pending == current


@pytest.mark.parametrize("bad", ["nan", "missing", "kind"])
def test_bad_pick_payload_cannot_change_the_center(request, bad):
    w = request.getfixturevalue("opened")
    w.select_many((("nozicka_1",), ("nozicka_2",)))
    w.rotation_pick_button.click()
    point = (float("nan"), 0, 0) if bad == "nan" else (1, 2, 3)
    shape = next(iter(w.visible_instances()[0].part.edges())).wrapped
    payload = {"token": w.viewer.center_pick["token"], "kind": "circle",
               "shape": shape, "point": point}
    if bad == "missing":
        payload["shape"] = None
    elif bad == "kind":
        payload["kind"] = "face"
    before = [f.text() for f in w.rotation_center_edits]
    w.viewer.rotation_center_picked.emit(payload)
    assert [f.text() for f in w.rotation_center_edits] == before
    assert w.rotation_center_mode.currentIndex() == 0 and not w.session.can_undo


def test_nested_reference_is_allowed_without_changing_parent_selection(request):
    w = request.getfixturevalue("nested_isolation")
    ids = (("a",), ("b",))
    w.select_many(ids)
    child = next(i for i in w.visible_instances() if i.ids[:1] == ("b",))
    w.rotation_pick_kind.setCurrentIndex(2)
    w.rotation_pick_button.click()
    w.viewer.rotation_center_picked.emit({"token": w.viewer.center_pick["token"],
                                         "kind": "face", "point": (12, 23, 34),
                                         "shape": next(iter(child.part.faces())).wrapped})
    assert w._selection == ids and [f.text() for f in w.rotation_center_edits] == [
        "12.0", "23.0", "34.0"]
    assert not w.session.can_undo


def test_fixed_incomplete_and_all_hidden_views_cannot_start_picking(request):
    w = request.getfixturevalue("opened")
    w.select_many((("krabicka",), ("vicko",)))
    assert not w.rotation_pick_button.isEnabled()
    w.select_many((("nozicka_1",), ("nozicka_2",)))
    w.select_all_components()
    w.toggle_selected_visibility()
    w.select_many((("nozicka_1",), ("nozicka_2",)))
    assert not w.rotation_pick_button.isEnabled()
    w.show_all()
    assert w.rotation_pick_button.isEnabled()
    w.session.result = None
    w._refresh_batch_rotation_box()
    assert not w.rotation_pick_button.isEnabled()
