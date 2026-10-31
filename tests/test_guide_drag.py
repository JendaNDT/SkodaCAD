"""Tažení: geometrický význam, jedna transakce, odmítnutí a stav ovladače myši."""

import copy
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from conftest import EXAMPLES
from skodacad.document import DocumentError
from skodacad.gui.guide_drag import nearest_handle, on_xy_plane
from skodacad.gui.viewer import OccViewer
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder

EXAMPLE = EXAMPLES / 'rizeny_prechod.json'


def request(session, delta=(3, 2), corner=(1, 1), handle=0):
    return dict(feature_id='rizeny', corner=list(corner), handle=handle, delta=list(delta),
                signature=session.result.model_signature)


def test_atomic_move_preserves_expression_height_geometry_and_one_undo(tmp_path):
    s = ModelSession()
    s.open(EXAMPLE)
    before = copy.deepcopy(s.document)
    s.move_guided_handle(**request(s))
    assert s.result.ok and s.result.part.is_valid and s.document.to_dict()['version'] == 34
    rail = s.guided_loft_display('rizeny')['guides'][0]
    # Jedna rukojeť má v t=1/2 váhu 3/8; konce ani výška se nemění.
    assert rail['curve'][20] == pytest.approx((23+3*3/8, 17+2*3/8, 30))
    assert rail['poles'][1][2] == 20 and rail['poles'][2][2] == 40
    assert len(s._undo) == 1
    path = s.save(tmp_path/'tah.json')
    s.open(path)
    assert s.result.part.volume > 77760
    s.set_parameter('Bx', '4')
    assert s.guided_loft_display('rizeny')['guides'][0]['curve'][20][0] == pytest.approx(21.125)
    s.undo()
    s.undo()  # otevření resetovalo historii; druhé Zpět už není
    other = ModelSession()
    other.open(EXAMPLE)
    other.move_guided_handle(**request(other))
    other.undo()
    assert other.document == before and not other.can_undo
    other.redo()
    assert other.result.part.volume > 77760


def test_refusal_stale_invalid_or_failed_kernel_preserves_model_history(monkeypatch):
    s = ModelSession()
    s.open(EXAMPLE)
    s.set_parameter('Bx', '4')
    s.undo()
    original, result, dirty, redo = copy.deepcopy(s.document), s.result, s.dirty, list(s._redo)
    for change in ({'delta': [-180, 0]}, {'signature': 'stale'}, {'handle': True},
                   {'delta': [float('nan'), 1]}, {'delta': [10**1000, 0]}, {'corner': [0, 1]}):
        with pytest.raises(DocumentError):
            s.move_guided_handle(**(request(s) | change))
        assert s.document == original and s.result is result and s.dirty == dirty
        assert s._redo == redo and not s.can_undo
    import skodacad.session as module
    monkeypatch.setattr(module, 'rebuild', lambda *_a, **_k: None)
    with pytest.raises(DocumentError, match='Původní model se nezměnil'):
        s.move_guided_handle(**request(s))
    assert s.document == original and s.result is result and s._redo == redo


def test_async_move_accepts_only_completed_result_cancel_and_superseding_edit():
    runner = BackgroundRebuilder()
    try:
        s = ModelSession(runner)
        s.open(EXAMPLE)
        assert s.wait(40)
        original, result = copy.deepcopy(s.document), s.result
        s.move_guided_handle(**request(s))
        assert s.computing and s.document == original and s.result is result
        assert not s.dirty and not s.can_undo
        assert s.wait(40) and s.result.ok and s.dirty and len(s._undo) == 1
        assert s.guided_loft_display('rizeny')['guides'][0]['curve'][20][0] == pytest.approx(24.125)
        s.undo()
        assert s.wait(40)
        redo = list(s._redo)
        s.move_guided_handle(**request(s))
        assert s.cancel() and s.document == original and s._redo == redo
        s.move_guided_handle(**request(s))
        s.set_parameter('By', '4')
        assert s.wait(40) and s.result.ok
        # Starý návrh nesmí doběhnout přes novou úpravu.
        assert s.document.features == original.features
        assert s.document.parameters['By'] == 4
    finally:
        runner.close()


def test_ray_plane_and_ambiguous_screen_pick():
    assert on_xy_plane((1, 2, 5, 2, -1, -2), 1) == pytest.approx((5, 0))
    assert on_xy_plane((0, 0, 0, 1, 0, 1e-5), 20) is None
    assert on_xy_plane((0, 0, 0, 0, 0, 0), 20) is None
    assert on_xy_plane((0, 0, 0, 0, 0, float('inf')), 20) is None
    assert nearest_handle([(10, 10), (10, 10)], (11, 10)) == -1
    assert nearest_handle([(10, 10), (50, 10)], (100, 10)) is None
    assert nearest_handle([(10, 10), (50, 10)], (50, 15)) == 1


def mouse(kind, xy, button=Qt.MouseButton.LeftButton, modifiers=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(kind, QPointF(*xy), QPointF(*xy), button,
                       Qt.MouseButton.LeftButton, modifiers)


@pytest.fixture
def viewer(monkeypatch):
    app = QApplication.instance() or QApplication([])
    v = OccViewer()
    v._view = SimpleNamespace(Convert=lambda x, y, z: (round(x*10), round(y*10)),
                              ConvertWithProj=lambda x, y: (x/10, y/10, 0., 0., 0., 1.),
                              StartRotation=lambda *_: None, Redraw=lambda: None)
    v._drawn = []
    monkeypatch.setattr(v, '_draw_guides', lambda d: v._drawn.append(copy.deepcopy(d)))
    monkeypatch.setattr(v, '_pick_face_at', lambda *_: None)
    data = {'feature_id': 'rizeny', 'signature': 'current', 'selected': 0, 'guides': [
        {'corner': [1, 1], 'poles': [(0, 0, 0), (10, 10, 20), (20, 20, 40), (30, 30, 60)]}]}
    v.show_guides(data)
    yield v
    v._view = None
    v.close()
    app.processEvents()


@pytest.mark.parametrize('ratio', [1., 1.25, 2.])
def test_mouse_drag_anchor_retina_preview_and_single_release_signal(viewer, monkeypatch, ratio):
    v = viewer
    monkeypatch.setattr(v, '_pixel_scale', lambda: ratio)
    events = []
    v.guide_handle_moved.connect(events.append)
    start = (100/ratio+2, 100/ratio)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, start))
    assert v._guide_drag is not None
    for step in (5, 10, 20):
        end = (start[0]+step, start[1])
        v._mouse_move(mouse(QEvent.Type.MouseMove, end))
        assert not events
    assert v._drawn[-1]['guides'][0]['poles'][1] == pytest.approx((10+2*ratio, 10, 20))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, end))
    assert len(events) == 1 and events[0]['delta'] == pytest.approx((2*ratio, 0))
    assert events[0]['corner'] == [1, 1] and events[0]['handle'] == 0
    assert v._guide_drag is None and v._drawn[-1] == v._guides_data


def test_click_cancel_focus_loss_and_replaced_overlay_never_commit(viewer, monkeypatch):
    v = viewer
    monkeypatch.setattr(v, '_pixel_scale', lambda: 1.)
    events = []
    v.guide_handle_moved.connect(events.append)
    for cause in ('click', 'escape', 'focus', 'overlay'):
        v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (100, 100)))
        if cause != 'click':
            v._mouse_move(mouse(QEvent.Type.MouseMove, (130, 100)))
        if cause == 'escape':
            v.clear_selection()  # globální Esc
        elif cause == 'focus':
            QApplication.sendEvent(v._surface, QEvent(QEvent.Type.FocusOut))
        elif cause == 'overlay':
            v.show_guides(copy.deepcopy(v._guides_data))
        v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (100, 100)))
        assert v._guide_drag is None and not events


def test_worker_failure_or_foreign_result_never_changes_history():
    s = ModelSession()
    s.open(EXAMPLE)
    original, result = copy.deepcopy(s.document), s.result
    queue = []
    s._runner = SimpleNamespace(submit=lambda *_a, **_k: 1,
                                poll=lambda: queue.pop(0) if queue else None)
    for payload, error in ((None, 'Chyba pomocného procesu'), (result, '')):
        s.move_guided_handle(**request(s))
        queue.append(SimpleNamespace(job=1, update=None, result=payload, error=error))
        assert s.poll() and not s.computing and s.failure
        assert s.document == original and s.result is result and not s.can_undo and not s.dirty


def test_edge_on_overlap_and_alt_do_not_start_guide_drag(viewer, monkeypatch):
    v = viewer
    monkeypatch.setattr(v, '_pixel_scale', lambda: 1.)
    v._view.ConvertWithProj = lambda *_: (0, 0, 0, 1, 0, 0)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (100, 100)))
    assert v._guide_drag is None and v._press is None
    v._guides_data['guides'][0]['poles'][2] = (10, 10, 40)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (100, 100)))
    assert v._guide_drag is None
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (100, 100),
                         modifiers=Qt.KeyboardModifier.AltModifier))
    assert v._guide_drag is None and v._probe_dragging


def test_valid_guides_but_broken_later_hole_are_rejected_atomically():
    s = ModelSession()
    s.open(EXAMPLE)
    s.add_feature('hole', values={'kind': 'clearance', 'size': 'M3', 'diameter': .5,
                                 'plane': 'top', 'positions': [[22, 10]], 'through_all': True})
    assert s.result.ok and s.result.part.volume < 77760
    original, result, undo = copy.deepcopy(s.document), s.result, list(s._undo)
    with pytest.raises(DocumentError, match='řez neodebral'):
        s.move_guided_handle(**request(s, delta=(-20, 0)))
    assert s.document == original and s.result is result and s._undo == undo


@pytest.mark.parametrize('delta,step,expected', [
    ((1.49, -1.51), 1., (1., -2.)),
    ((.25, -.25), .5, (.5, -.5)),
    ((.15, -.15), .1, (.2, -.2)),
    ((.0005, -.0005), .001, (.001, -.001)),
    ((.26, -.34), .1, (.3, -.3)),
    ((499., -501.), 1000., (0., -1000.)),
    ((1.23456789, -2.3456789), 0., (1.23456789, -2.3456789)),
])
def test_step_is_symmetric_and_decimal_clean(delta, step, expected):
    from skodacad.gui.guide_drag import snapped_delta

    assert snapped_delta(delta, step) == expected


@pytest.mark.parametrize('step', [-1., float('nan'), float('inf'), 1000.001])
def test_bad_drag_step_is_refused(step):
    from skodacad.gui.guide_drag import snapped_delta

    with pytest.raises(ValueError, match='Krok tažení'):
        snapped_delta((1., 2.), step)


@pytest.mark.parametrize('ratio', [1., 1.25, 2.])
def test_snapped_preview_and_release_use_total_xy_displacement(viewer, monkeypatch, ratio):
    v = viewer
    monkeypatch.setattr(v, '_pixel_scale', lambda: ratio)
    v.set_guide_drag_step(.5)
    events = []
    v.guide_handle_moved.connect(events.append)
    start = (100/ratio+2, 100/ratio)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, start))
    # Více událostí nesmí sčítat zaokrouhlení; každý náhled patří témuž počátku tahu.
    for amount in (7, 13, 7):
        v._mouse_move(mouse(QEvent.Type.MouseMove,
                            (start[0]+amount/ratio, start[1]-7/ratio)))
    assert v._drawn[-1]['guides'][0]['poles'][1] == pytest.approx((10.5, 9.5, 20))
    assert not events
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease,
                           (start[0]+7/ratio, start[1]-7/ratio)))
    assert len(events) == 1 and events[0]['delta'] == [.5, -.5]
    assert v._drawn[-1] == v._guides_data


def test_substep_drag_is_no_change_and_step_switch_cancels_active_drag(viewer, monkeypatch):
    v = viewer
    monkeypatch.setattr(v, '_pixel_scale', lambda: 1.)
    events = []
    v.guide_handle_moved.connect(events.append)
    v.set_guide_drag_step(1.)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (100, 100)))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (104, 100)))
    assert not events  # čtyři pixely už jsou tah, ale 0,4 mm je stále nulový krok
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (100, 100)))
    v._mouse_move(mouse(QEvent.Type.MouseMove, (116, 100)))
    assert v._drawn[-1]['guides'][0]['poles'][1] == (12., 10., 20.)
    v.set_guide_drag_step(.1)
    assert v._guide_drag is None
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (116, 100)))
    assert not events and v._drawn[-1] == v._guides_data


def test_snapped_move_reaches_exact_geometry_volume_and_one_undo():
    from skodacad.gui.guide_drag import snapped_delta

    s = ModelSession()
    s.open(EXAMPLE)
    s.move_guided_handle(**request(s, delta=snapped_delta((2.7, 1.8), 1.)))
    # Posun jedné první rukojeti o (3,2): nezávislý integrál změny plochy
    # dV = H * integral[3t(1-t)^2 * (b(t)*dx + a(t)*dy)] = 249dx + 336dy.
    assert s.result.ok and s.result.part.is_valid
    assert s.result.part.volume == pytest.approx(77760+249*3+336*2, abs=2e-5)
    assert len(s._undo) == 1
    s.undo()
    assert s.result.part.volume == pytest.approx(77760, abs=2e-5)


@pytest.mark.parametrize('direction', ['XY', 'X', 'Y'])
@pytest.mark.parametrize('step,expected', [(0., (2.7, -1.8)), (.1, (2.7, -1.8)),
                                          (.5, (2.5, -2.)), (1., (3., -2.))])
def test_axis_constraint_combines_with_free_or_stepped_drag(direction, step, expected):
    from skodacad.gui.guide_drag import constrained_delta

    actual = constrained_delta((2.7, -1.8), step, direction)
    assert actual == (0. if direction == 'Y' else expected[0],
                      0. if direction == 'X' else expected[1])


@pytest.mark.parametrize('direction', ['X', 'Y'])
@pytest.mark.parametrize('d', [(2., -1., -2.), (1., 2., 3.), (0., 0., 1.)])
def test_axis_parameter_matches_independent_closest_lines_solve(direction, d):
    import numpy as np

    from skodacad.gui.guide_drag import axis_parameter

    anchor, origin = np.array((20., -7., 40.)), np.array((13., 5., 2.))
    e = np.array((1., 0., 0.) if direction == 'X' else (0., 1., 0.))
    expected = np.linalg.lstsq(np.column_stack((e, -np.array(d))), origin-anchor, rcond=None)[0][0]
    assert axis_parameter((*origin, *d), anchor, direction) == pytest.approx(expected, abs=1e-10)
    translation = np.array((1000., -700., 500.))
    assert axis_parameter((*(origin+translation), *(v*1e6 for v in d)),
                          anchor+translation, direction) == pytest.approx(expected, abs=1e-10)


def test_hidden_axis_is_refused_and_front_side_views_have_visible_axis():
    from skodacad.gui.guide_drag import axis_parameter, constrained_delta

    assert axis_parameter((3, 4, 5, 0, 1, 0), (1, 2, 20), 'X') == 2
    assert axis_parameter((3, 4, 5, 1, 0, 0), (1, 2, 20), 'Y') == 2
    assert axis_parameter((3, 4, 5, 1, 0, 0), (1, 2, 20), 'X') is None
    assert axis_parameter((3, 4, 5, 0, 1, 0), (1, 2, 20), 'Y') is None
    assert axis_parameter((3, 4, 5, 1, 1e-5, 0), (1, 2, 20), 'X') is None
    assert axis_parameter((3, 4, 5, 0, 0, 0), (1, 2, 20), 'X') is None
    assert axis_parameter((3, 4, 5, 0, 0, float('inf')), (1, 2, 20), 'X') is None
    with pytest.raises(ValueError, match='Směr tažení'):
        constrained_delta((1, 2), 1, 'Z')


@pytest.mark.parametrize('direction,delta', [('X', [.5, 0.]), ('Y', [0., -.5])])
@pytest.mark.parametrize('ratio', [1., 1.25, 2.])
def test_locked_mouse_preview_and_release_preserve_other_coordinate(
        viewer, monkeypatch, direction, delta, ratio):
    v = viewer
    monkeypatch.setattr(v, '_pixel_scale', lambda: ratio)
    v.set_guide_drag_step(.5)
    v.set_guide_drag_direction(direction)
    events = []
    v.guide_handle_moved.connect(events.append)
    start, end = (102/ratio, 100/ratio), (109/ratio, 93/ratio)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, start))
    v._mouse_move(mouse(QEvent.Type.MouseMove, end))
    assert v._drawn[-1]['guides'][0]['poles'][1] == pytest.approx((10+delta[0], 10+delta[1], 20))
    assert not events
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, end))
    assert len(events) == 1 and events[0]['delta'] == delta


@pytest.mark.parametrize('direction,end', [('X', (100, 116)), ('Y', (116, 100))])
def test_movement_across_locked_axis_never_creates_change(viewer, monkeypatch, direction, end):
    v = viewer
    monkeypatch.setattr(v, '_pixel_scale', lambda: 1.)
    v.set_guide_drag_direction(direction)
    events = []
    v.guide_handle_moved.connect(events.append)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (100, 100)))
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, end))
    assert not events


def test_direction_switch_cancels_preview_and_front_drag_works(viewer, monkeypatch):
    v = viewer
    monkeypatch.setattr(v, '_pixel_scale', lambda: 1.)
    events = []
    v.guide_handle_moved.connect(events.append)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (100, 100)))
    v._mouse_move(mouse(QEvent.Type.MouseMove, (116, 100)))
    v.set_guide_drag_direction('X')
    assert v._guide_drag is None and v._drawn[-1] == v._guides_data
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (116, 100)))
    assert not events
    # Paprsek rovnoběžný s XY: volné tažení by odmítl, viditelná osa X zůstává použitelná.
    v._view.ConvertWithProj = lambda x, y: (x/10, 0., y/10, 0., 1., 0.)
    v.set_guide_drag_step(1.)
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (100, 100)))
    assert v._guide_drag is not None
    v._mouse_release(mouse(QEvent.Type.MouseButtonRelease, (118, 100)))
    assert events[0]['delta'] == [2., 0.]
    v.set_guide_drag_direction('Y')
    v._mouse_press(mouse(QEvent.Type.MouseButtonPress, (100, 100)))
    assert v._guide_drag is None and v._press is None


@pytest.mark.parametrize('direction,delta,volume', [('X', (3., 0.), 78507.),
                                                   ('Y', (0., -2.), 77088.)])
def test_single_axis_move_has_independent_volume_and_unchanged_other_expression(
        direction, delta, volume):
    from skodacad.gui.guide_drag import constrained_delta

    s = ModelSession()
    s.open(EXAMPLE)
    original = copy.deepcopy(s.document)
    s.move_guided_handle(**request(s, delta=constrained_delta((2.7, -1.8), 1., direction)))
    assert s.result.ok and s.result.part.is_valid
    assert s.result.part.volume == pytest.approx(volume, abs=2e-5)  # 77760 + 249dx + 336dy
    rail = s.guided_loft_display('rizeny')['guides'][0]
    assert rail['curve'][20] == pytest.approx((23+3*delta[0]/8, 17+3*delta[1]/8, 30))
    inactive = 1 if direction == 'X' else 0
    assert s.document.features[-1]['guides'][0]['controls'][0][inactive] == \
        original.features[-1]['guides'][0]['controls'][0][inactive]
    assert len(s._undo) == 1
    s.undo()
    assert s.document == original and s.result.part.volume == pytest.approx(77760, abs=2e-5)
