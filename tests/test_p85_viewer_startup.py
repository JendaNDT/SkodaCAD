"""Otevření nativní plochy se vrátí do Qt před založením grafického kontextu."""

from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from skodacad.gui.viewer import OccViewer


@pytest.fixture
def startup_viewer(monkeypatch):
    app = QApplication.instance() or QApplication([])
    widget = OccViewer()
    initialize = Mock()
    monkeypatch.setattr(widget, "_initialize", initialize)
    monkeypatch.setattr(widget, "_redraw", Mock())
    monkeypatch.setattr(widget, "_resized", Mock())
    yield app, widget, initialize
    if isValid(widget):
        widget.close()


def test_show_returns_before_native_initialization_and_keeps_pending_model(startup_viewer):
    app, widget, initialize = startup_viewer
    model = object()
    widget.show_part(model, fit=False)
    widget.show()
    initialize.assert_not_called()
    assert widget._pending == (model, False, None, [])
    assert not widget.ready
    assert QSignalSpy(widget._surface._initialize_timer.timeout).wait(1000)
    initialize.assert_called_once_with()
    app.processEvents()
    initialize.assert_called_once_with()


@pytest.mark.parametrize("delivery_delay_ms", [1, 50])
def test_hide_before_first_turn_cancels_initialization_until_shown_again(
        startup_viewer, delivery_delay_ms):
    _app, widget, initialize = startup_viewer
    widget.show()
    widget.hide()
    assert not widget._surface._initialize_timer.isActive()
    QTest.qWait(20)
    initialize.assert_not_called()
    widget.show()
    initialize.assert_not_called()
    assert widget._surface._initialize_timer.isActive()
    # Testujeme i opožděné doručení: 20 ms není smluvní lhůta Qt události.
    widget._surface._initialize_timer.start(delivery_delay_ms)
    assert QSignalSpy(widget._surface._initialize_timer.timeout).wait(1000)
    initialize.assert_called_once_with()


def test_destroy_before_first_turn_does_not_initialize_deleted_surface(startup_viewer):
    _app, widget, initialize = startup_viewer
    widget.show()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTest.qWait(20)
    initialize.assert_not_called()


@pytest.mark.parametrize("state", ["ready", "error"])
def test_already_initialized_or_failed_viewer_does_not_queue_work(startup_viewer, state):
    _app, widget, initialize = startup_viewer
    if state == "ready":
        widget._view, widget._context = Mock(), Mock()
    else:
        widget.error = "Grafika není dostupná"
    widget.show()
    QTest.qWait(20)
    initialize.assert_not_called()
