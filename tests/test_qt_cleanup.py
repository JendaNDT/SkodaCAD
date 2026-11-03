import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtGui import QAction  # noqa: E402
from shiboken6 import isValid  # noqa: E402

from qt_cleanup import dispose_new_widgets, top_levels  # noqa: E402


def test_closed_window_and_action_cycle_are_destroyed_with_python_refs_alive():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    previous = top_levels()
    closed = []

    class Window(QtWidgets.QWidget):
        def closeEvent(self, event):  # noqa: N802
            closed.append(True)
            super().closeEvent(event)

    window = Window()
    action = QAction("test", window)
    window.action = action
    action.triggered.connect(lambda: window.setWindowTitle("callback"))
    window.close()
    assert isValid(window) and isValid(action)  # původní samotné close nestačí
    dispose_new_widgets(previous)
    assert closed and not isValid(window) and not isValid(action)
    assert app is QtWidgets.QApplication.instance()


def test_preexisting_window_is_preserved_while_new_child_tree_is_disposed():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    existing = QtWidgets.QWidget()
    previous = top_levels()
    created = QtWidgets.QWidget()
    child = QtWidgets.QLabel("child", created)
    dispose_new_widgets(previous)
    assert isValid(existing) and not isValid(created) and not isValid(child)
    assert app is QtWidgets.QApplication.instance()
    dispose_new_widgets(tuple(w for w in previous if w is not existing))
    assert not isValid(existing)
