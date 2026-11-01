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
    viewer.show_part(compound, accent=[face], transparent=[a])
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
    viewer.set_transparent_parts([b])
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
    viewer.set_transparent_parts([part])
    pending_part, fit, accent, transparent = viewer._pending
    assert pending_part is part and fit and accent is None
    assert len(transparent) == 1 and transparent[0].IsSame(part.wrapped)
    viewer.set_transparent_parts([])
    assert viewer._pending[3] == []
