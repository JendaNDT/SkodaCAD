"""Etapa 15B: offscreen testy editoru, tabulky, náhledu, potvrzení, exportu a AI zámku."""

import copy
import shutil

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from skodacad.gui.design_panel import DesignDialog  # noqa: E402
from skodacad.gui.main_window import MainWindow  # noqa: E402
from test_gui import FakeViewer  # noqa: E402

MODEL = "navrh_kapsa.json"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def design_window(app, examples_dir, tmp_path):
    original = examples_dir / "ndt" / MODEL
    model = tmp_path / MODEL
    shutil.copy(original, model)
    window = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert window.open_model(model)
    yield window, model
    window.session.dirty = False
    window.close()


def quick_settings():
    return {"study": "s3", "parameters": [{"name": "a", "values": [40, 90]}],
            "conditions": [{"measurement": "m1", "min": 15, "reason": "stěna"}],
            "options": {"verify": False, "rejected": False}}


def test_dialog_prefills_and_validates_everything(design_window):
    window, _source = design_window
    dialog = DesignDialog(window)
    saved = window.session.ndt_design_settings()
    assert dialog.study.currentData() == "s3"
    assert dialog.design().to_dict() == saved.to_dict()
    dialog.parameters[0][1].setText("40:90:50")
    assert dialog.design().parameters[0].values == (40.0, 90.0)
    dialog.parameters[0][1].setText("40:90:0")
    with pytest.raises(ValueError, match="Krok"):
        dialog.design()
    dialog.close()


def test_panel_flow_preserves_original_until_explicit_approval(design_window, monkeypatch,
                                                               tmp_path):
    window, source = design_window
    before = source.read_bytes()
    panel = window.design_panel
    window.show_design()
    assert "pevnost" in panel.warning.text().lower()
    assert window.design_dock.isVisible() or window.design_dock.widget() is not None
    window.session.set_ndt_design(quick_settings())
    window._refresh_all()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    panel.start()
    result = window.session.ndt_design
    assert result is not None and result.complete
    assert len(result.variants) == 2 and panel.table.rowCount() == 2
    assert source.read_bytes() == before
    assert window.session.document.parameters["a"] == 40
    assert panel.table.item(0, 0).text() == "Původní"
    assert any("90" in panel.table.item(i, 1).text() for i in range(2))
    panel.table.selectRow(1)
    assert panel.selected_variant().values == {"a": 90}
    assert panel.preview_banner.text().startswith("Náhled varianty V1")
    assert window.viewer.parts[-1][0] is not window.session.result.part
    assert window.session.document.parameters["a"] == 40
    target = tmp_path / "v1.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *args, **kwargs: (str(target), ""))
    panel.save_variant()
    assert target.is_file() and window.session.document.parameters["a"] == 40

    output = tmp_path / "report"
    output.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *args, **kwargs: str(output))
    panel.export()
    assert (output / "navrh.html").is_file()
    assert (output / "varianty.csv").is_file()
    assert (output / "navrh.pdf").read_bytes().startswith(b"%PDF")
    assert source.read_bytes() == before

    panel.table.selectRow(1)
    panel.apply()
    assert window.session.document.parameters["a"] == 90
    assert source.read_bytes() == before  # změna v paměti, nikoli na disku
    window.session.undo()
    assert window.session.document.parameters["a"] == 40


def test_cannot_apply_rejected_variant_and_ai_locks_panel(design_window, monkeypatch):
    window, _source = design_window
    window.session.set_ndt_design({
        "study": "s3", "parameters": [{"name": "a", "values": [40, 100]}],
        "conditions": [{"measurement": "m1", "min": 15}],
        "options": {"verify": False, "rejected": False}})
    window._refresh_all()
    panel = window.design_panel
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    panel.start()
    panel.table.selectRow(1)
    assert panel.selected_variant().status == "rejected"
    assert not panel.apply_action.isEnabled()
    assert not panel.save_action.isEnabled()
    before = copy.deepcopy(window.session.document.to_dict())
    panel.reject_results()
    assert panel.table.rowCount() == 0
    assert window.session.document.to_dict() == before
    window.set_assistant_busy(True)
    assert not panel.edit_action.isEnabled() and not panel.run_action.isEnabled()
    window.set_assistant_busy(False)
    assert panel.edit_action.isEnabled()
