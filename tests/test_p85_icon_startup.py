"""System icons load between Qt turns, keeping actions and palette updates current."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from skodacad.gui.main_window import MainWindow
from test_gui import FakeViewer


@pytest.fixture
def icons(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    state = SimpleNamespace(calls=[], color="red", hook=None)
    native = app.style()

    class Style:
        def __getattr__(self, name):
            return getattr(native, name)

        def standardIcon(self, code):  # noqa: N802 -- Qt API
            pixmap = QPixmap(8, 8)
            pixmap.fill(QColor(state.color))
            icon = QIcon(pixmap)
            state.calls.append((code, icon.cacheKey()))
            if state.hook:
                hook, state.hook = state.hook, None
                hook()
            return icon

    monkeypatch.setattr(MainWindow, "style", lambda _self: Style())
    window = MainWindow(viewer_factory=FakeViewer, user_dir=tmp_path)
    yield app, window, state
    if isValid(window):
        window.session.dirty = False
        window.close()


def drain(window):
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: loop.quit() if not window._standard_icon_queue else None)
    timer.start(2)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(2000)
    loop.exec()
    timer.stop()
    timeout.stop()
    assert not window._standard_icon_queue


def test_constructor_and_show_return_before_native_icons_and_keep_the_actions(icons):
    app, window, state = icons
    actions = [a for a, _ in window._standard_icons]
    assert state.calls == [] and not window._icon_timer.isActive()
    window.show()
    assert state.calls == []
    drain(window)
    assert [a for a, _ in window._standard_icons] == actions
    assert len(state.calls) == len(actions)
    assert all(not a.icon().isNull() for a in actions)
    assert window.new_action in actions and window.undo_action in actions
    assert window.open_action.shortcut().toString()
    app.processEvents()
    assert len(state.calls) == len(actions)


def test_waits_for_native_view_then_returns_to_qt_before_loading_one_icon(icons):
    _app, window, state = icons
    window.viewer.ready = False
    window.viewer.error = ""
    window.show()
    window._icon_timer.stop()
    window._refresh_next_standard_icon()
    assert not state.calls and window._icon_timer.isActive()
    window._icon_timer.stop()
    window.viewer.ready = True
    window._refresh_next_standard_icon()
    assert not state.calls and window._icons_after_view
    window._icon_timer.stop()
    window._refresh_next_standard_icon()
    assert len(state.calls) == 1  # one action, even with the rest still queued
    assert len(window._standard_icon_queue) == len(window._standard_icons)-1


def test_failed_3d_view_still_gets_all_system_icons(icons):
    _app, window, state = icons
    window.viewer.ready, window.viewer.error = False, "unavailable graphics"
    window.show()
    drain(window)
    assert len(state.calls) == len(window._standard_icons)


def test_palette_refresh_during_native_load_does_not_apply_an_old_icon(icons):
    _app, window, state = icons
    action = window.new_action
    window.show()
    window._icon_timer.stop()
    window._refresh_next_standard_icon()  # finished-view boundary
    window._icon_timer.stop()
    original = action.icon().cacheKey()

    def changed_palette():
        state.color = "blue"
        window._refresh_ui_icons()

    state.hook = changed_palette
    window._refresh_next_standard_icon()
    assert action.icon().cacheKey() == original
    old_key = state.calls[0][1]
    drain(window)
    assert action.icon().cacheKey() != old_key
    assert len(state.calls) == len(window._standard_icons)+1


def test_cancelled_close_keeps_loading_but_accepted_close_stops_it(icons, monkeypatch):
    app, window, state = icons
    window.show()
    monkeypatch.setattr(window, "_confirm_discard", lambda: False)
    assert not window.close()
    assert window._standard_icon_queue and not window._icon_loader_closed
    monkeypatch.setattr(window, "_confirm_discard", lambda: True)
    assert window.close()
    count = len(state.calls)
    assert not window._icon_timer.isActive() and not window._standard_icon_queue
    app.processEvents()
    assert len(state.calls) == count


def test_destroyed_owner_cancels_queued_callbacks(icons):
    app, window, state = icons
    window.show()
    timer = window._icon_timer
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(window) and not isValid(timer)
    count = len(state.calls)
    app.processEvents()
    assert len(state.calls) == count
