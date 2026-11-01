"""Nativní plocha se může ustálit později než logické rozměry Qt."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtWidgets import QApplication

from skodacad.gui import viewer as module


@pytest.fixture
def viewer(monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = module.OccViewer()
    window = Mock()
    window.Size.return_value = (640, 480)
    widget._window = window
    widget._surface.resize(640, 480)
    widget._view = Mock()
    widget._view.SetImmediateUpdate.return_value = True
    widget._view.Window.return_value = window
    yield widget
    widget._view = None
    widget.close()
    app.processEvents()


def test_mac_rechecks_native_backing_size_when_qt_size_stays_the_same(viewer, monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "darwin")
    native = SimpleNamespace(size=(100, 30), pending=(100, 30))
    viewer._view.MustBeResized.side_effect = lambda: setattr(native, "size", native.pending)
    viewer._redraw()
    assert native.size == (100, 30)  # showEvent: nativní plocha ještě není usazená
    native.pending = (1280, 960)
    viewer._redraw()  # paintEvent: stejné Qt 640×480, NSView už odpovídá Retina displeji
    assert native.size == (1280, 960)
    assert viewer._known_size == (640, 480)
    assert viewer._view.MustBeResized.call_count == 2
    assert viewer._view.SetImmediateUpdate.call_args.args == (True,)
    viewer._window.SetSize.assert_called_with(640, 480)
    # OCCT nad NeutralWindow stále převádí a vybírá v logických bodech.
    assert viewer._pixels(QPointF(320, 240)) == (320, 240)


@pytest.mark.parametrize("platform, ratio", [("win32", 1.5), ("linux", 1.0)])
def test_other_platforms_resize_only_when_native_dimensions_change(viewer, monkeypatch,
                                                                 platform, ratio):
    monkeypatch.setattr(module.sys, "platform", platform)
    monkeypatch.setattr(viewer._surface, "devicePixelRatioF", lambda: ratio)
    viewer._redraw()
    viewer._redraw()
    assert viewer._view.MustBeResized.call_count == 1
    viewer._window.Size.return_value = (900, 700)
    viewer._redraw()
    assert viewer._view.MustBeResized.call_count == 2
    assert viewer._known_size == (900, 700)
    assert viewer._pixels(QPointF(100, 80)) == (int(100 * ratio), int(80 * ratio))
    viewer._window.SetSize.assert_not_called()


def test_screen_scale_change_requests_resize_and_paint(viewer, monkeypatch):
    resized, update = Mock(), Mock()
    monkeypatch.setattr(viewer, "_resized", resized)
    monkeypatch.setattr(viewer._surface, "update", update)
    QApplication.sendEvent(viewer._surface, QEvent(QEvent.Type.DevicePixelRatioChange))
    resized.assert_called_once_with()
    update.assert_called_once_with()


def test_part_transparency_changes_material_without_replacing_geometry_or_selection(viewer):
    from build123d import Box, Compound, Location

    viewer._context = Mock()
    a = Box(30, 20, 10)
    b = a.moved(Location((100, 0, 0)))
    compound = Compound([a, b])
    face = max(a.faces(), key=lambda f: f.center().Z)
    viewer.show_part(compound, accent=[face], transparent=[(a, .7)])
    ais = viewer._ais
    aspects = ais.CustomAspectsMap()
    assert aspects.Find(a.wrapped).HasOwnTransparency()
    assert aspects.Find(a.wrapped).ShadingAspect().Aspect().FrontMaterial().Transparency() \
        == pytest.approx(0.7)
    assert not aspects.IsBound(b.wrapped)
    before = Compound(ais.Shape())
    assert len(before.solids()) == 2 and before.volume == pytest.approx(12000)
    assert before.bounding_box().max.X == pytest.approx(115)
    emitted = []
    viewer.selection_changed.connect(emitted.append)
    viewer.set_transparent_parts([(b, .7)])
    aspects = ais.CustomAspectsMap()  # OCP vrací kopii mapy; nové položky načíst znovu
    assert viewer._ais is ais and not emitted
    assert aspects.Find(a.wrapped).ShadingAspect().Aspect().FrontMaterial().Transparency() == 0
    assert aspects.Find(b.wrapped).ShadingAspect().Aspect().FrontMaterial().Transparency() \
        == pytest.approx(0.7)
    assert aspects.Find(face.wrapped).HasOwnColor()  # barvy řezu se nesmějí smazat resetem vzhledu
    viewer._context.RecomputePrsOnly.assert_called_with(ais, False)
    viewer._context.Redisplay.assert_not_called()
    viewer._context.ClearSelected.assert_not_called()
    viewer.set_transparent_parts([])
    assert aspects.Find(b.wrapped).ShadingAspect().Aspect().FrontMaterial().Transparency() == 0
    assert not emitted and Compound(ais.Shape()).volume == pytest.approx(12000)
    viewer.show_part(b)  # nový díl nemá vzhled předchozího
    assert not viewer._transparent_parts and viewer._ais.CustomAspectsMap().IsEmpty()


def test_transparency_before_surface_ready_updates_pending_presentation(viewer):
    from build123d import Box

    viewer._view = None
    part = Box(30, 20, 10)
    viewer.show_part(part, fit=True)
    viewer.set_transparent_parts([(part, .4)])
    pending_part, fit, accent, transparent = viewer._pending
    assert pending_part is part and fit and accent is None
    assert len(transparent) == 1 and transparent[0][0].IsSame(part.wrapped)
    assert transparent[0][1] == .4
    viewer.set_transparent_parts([])
    assert viewer._pending[3] == []


def test_presentation_reset_is_distinct_from_explicit_clear_and_empty_click(viewer, monkeypatch):
    from build123d import Box

    changed, cleared = [], []
    viewer.selection_changed.connect(changed.append)
    viewer.selection_cleared.connect(lambda: cleared.append(True))
    view = viewer._view
    viewer._view = None
    viewer.show_part(Box(30, 20, 10))
    assert not changed and not cleared
    pending, viewer._pending = viewer._pending, None
    viewer._view, viewer._context = view, Mock()
    part, fit, accent, transparent = pending
    viewer.show_part(part, fit, accent, transparent)  # jako přehrání po inicializaci
    assert changed == [[]] and not cleared
    viewer.clear_selection()
    assert changed == [[], []] and cleared == [True]
    monkeypatch.setattr(viewer, "_remember_point", lambda: None)
    monkeypatch.setattr(viewer, "selected_shapes", lambda: [])
    viewer._select_at(5, 5)
    assert changed == [[], [], []] and cleared == [True, True]


def test_independent_material_amounts_zero_and_one_keep_same_shape(viewer):
    from build123d import Box, Compound, Location

    viewer._context = Mock()
    a = Box(30, 20, 10)
    b = a.moved(Location((100, 0, 0)))
    viewer.show_part(Compound([a, b]), transparent=[(a, .25), (b, .85)])
    ais = viewer._ais

    def alpha(part):
        aspects = ais.CustomAspectsMap()
        return aspects.Find(part.wrapped).ShadingAspect().Aspect().FrontMaterial().Transparency()

    assert alpha(a) == pytest.approx(.25) and alpha(b) == pytest.approx(.85)
    viewer.set_transparent_parts([(a, 0), (b, 1)])
    assert viewer._ais is ais and alpha(a) == 0 and alpha(b) == 1
    assert len(viewer._transparent_parts) == 1
    assert Compound(ais.Shape()).volume == pytest.approx(12000)
    assert Compound(ais.Shape()).bounding_box().max.X == pytest.approx(115)
    viewer.set_transparent_parts([(a, 0), (b, 0)])
    assert not viewer._transparent_parts and alpha(b) == 0
    assert viewer._context.HighlightStyle.return_value.SetDisplayMode.call_args.args == (1,)


@pytest.mark.parametrize("amount", [-.1, 1.1, float("nan")])
def test_invalid_transparency_does_not_replace_valid_presentation(viewer, amount):
    from build123d import Box

    viewer._context = Mock()
    part = Box(30, 20, 10)
    viewer.show_part(part, transparent=[(part, .4)])
    ais = viewer._ais
    with pytest.raises(ValueError, match="průhlednosti"):
        viewer.set_transparent_parts([(part, amount)])
    with pytest.raises(ValueError, match="průhlednosti"):
        viewer.show_part(part, transparent=[(part, amount)])
    assert viewer._ais is ais and viewer._transparent_parts[0][1] == .4
