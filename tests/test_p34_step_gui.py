"""GUI tok STEP s testovacím prohlížečem, bez skutečného kreslení OpenGL."""
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from skodacad.gui.main_window import MainWindow  # noqa: E402
from test_gui import FakeViewer  # noqa: E402

STEP = Path(__file__).parent / "fixtures" / "step" / "01-jedno-teleso.step"


@pytest.fixture
def window(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow(viewer_factory=FakeViewer, user_dir=tmp_path)
    w.session.new_document()
    w._reload_all()
    yield w
    w.session.dirty = False
    w.close()
    app.processEvents()


@pytest.mark.parametrize("accept", [True, False])
def test_import_preview_accept_or_cancel(window, monkeypatch, accept):
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", lambda *a: (str(STEP), ""))
    answer = QtWidgets.QMessageBox.StandardButton.Yes if accept else (
        QtWidgets.QMessageBox.StandardButton.No
    )
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a: answer)
    before = window.session.document.to_dict()
    window.import_step_dialog()
    assert any(part is not None and part.volume == pytest.approx(24000)
               for part, _ in window.viewer.parts)
    if accept:
        assert window.session.result.ok
        assert window.session.result.part.volume == pytest.approx(24000)
        assert window.session.document.features[0]["type"] == "step_import"
    else:
        assert window.session.document.to_dict() == before
        assert window.session.result.part is None


def test_corrupt_step_does_not_modify_document(window, monkeypatch):
    damaged = STEP.with_name("06-poskozeny.step")
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", lambda *a: (str(damaged), ""))
    errors = []
    monkeypatch.setattr(window, "_error", lambda title, message: errors.append((title, message)))
    before = window.session.document.to_dict()
    window.import_step_dialog()
    assert errors and "poškozen" in errors[0][1]
    assert window.session.document.to_dict() == before
    assert window.session.result.part is None


def test_metre_import_preview_and_confirmation(window, monkeypatch):
    metre_step = STEP.with_name("07-metry.step")
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", lambda *a: (str(metre_step), ""))
    prompts = []

    def confirm(*args):
        prompts.append(args[2])
        return QtWidgets.QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QtWidgets.QMessageBox, "question", confirm)
    window.import_step_dialog()
    assert prompts and "jednotka zdroje: metry" in prompts[0]
    assert "10 × 13 × 17 mm" in prompts[0]
    assert window.session.result.ok
    assert window.session.result.part.volume == pytest.approx(2210, abs=1e-5)


def test_cancel_running_import_preserves_document(window, monkeypatch):
    from PySide6.QtCore import QTimer

    import skodacad.step_task as step_task

    tasks = []

    class WaitingTask:
        def __init__(self, _data):
            self.canceled = False
            tasks.append(self)

        def poll(self):
            return None

        def cancel(self):
            self.canceled = True

    monkeypatch.setattr(step_task, "StepTask", WaitingTask)
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", lambda *a: (str(STEP), ""))
    before = window.session.document.to_dict()

    def cancel_dialog():
        dialogs = window.findChildren(QtWidgets.QProgressDialog)
        assert dialogs
        dialogs[-1].cancel()
        # Programmatic cancel() does not emit canceled on all Qt platforms.
        dialogs[-1].canceled.emit()

    QTimer.singleShot(150, cancel_dialog)
    window.import_step_dialog()
    assert tasks[0].canceled
    assert window.session.document.to_dict() == before
