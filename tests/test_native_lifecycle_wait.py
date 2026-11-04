"""Native self-test waits for deferred startup and always destroys its test viewers."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QApplication

from skodacad.gui import app as application
from skodacad.gui import viewer as viewer_module


@pytest.mark.parametrize('failure', [None, 'initialization', 'render'])
def test_lifecycle_waits_for_deferred_startup_and_cleans_up_on_failure(
        monkeypatch, tmp_path, failure):
    app = QApplication.instance() or QApplication([])
    created = []

    class DeferredViewer:
        def __init__(self):
            self.ready = False
            self.error = None
            self.resize = Mock()
            self.show_part = Mock()
            self.fit_all = Mock()
            self.dump = Mock(return_value=True)
            self.close = Mock()
            self.deleteLater = Mock()
            created.append(self)

        def show(self):
            if failure == 'initialization':
                self.error = 'initialization failed'
            else:
                QTimer.singleShot(30, lambda: setattr(self, 'ready', True))

    monkeypatch.setattr(viewer_module, 'OccViewer', DeferredViewer)
    render = Mock(side_effect=RuntimeError('render failed') if failure == 'render' else None)
    monkeypatch.setattr(application, '_check_render_size', render)
    monkeypatch.setattr(application, 'user_dir', lambda: tmp_path)
    part = object()
    window = SimpleNamespace(viewer=SimpleNamespace(ready=True),
                             session=SimpleNamespace(result=SimpleNamespace(part=part)))
    lines = []
    assert application._self_test_viewer_lifecycle(window, lines) is (failure is None)
    assert len(created) == (4 if failure is None else 1)
    for viewer in created:
        viewer.close.assert_called_once_with()
        viewer.deleteLater.assert_called_once_with()
        if failure is None:
            assert viewer.ready
            viewer.show_part.assert_called_once_with(part, fit=True)
            viewer.fit_all.assert_called_once_with()
            viewer.dump.assert_called_once_with(str(tmp_path / 'self-test-zivotnost-3d.png'))
    if failure is None:
        assert render.call_count == 8
        assert lines[0].startswith('✓ Životnost 3D ploch: 4×')
    else:
        assert lines[0].startswith('✕ Životnost 3D ploch:')
    app.processEvents()


@pytest.mark.parametrize('event_type', [QEvent.Type.FocusOut,
                                      QEvent.Type.WindowDeactivate,
                                      QEvent.Type.UngrabMouse])
def test_native_surface_event_without_python_owner_still_delegates_to_qt(event_type):
    app = QApplication.instance() or QApplication([])
    owner = viewer_module.OccViewer()
    surface = owner._surface
    del surface._owner
    try:
        assert isinstance(surface.event(QEvent(event_type)), bool)
    finally:
        surface._owner = owner
        owner.close()
        owner.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
