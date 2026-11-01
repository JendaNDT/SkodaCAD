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
