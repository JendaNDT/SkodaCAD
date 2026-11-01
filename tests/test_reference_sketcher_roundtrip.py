"""P1.3: returning from the sketcher must preserve edited projection references."""

import copy

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QDialog, QFileDialog, QPushButton  # noqa: E402

import test_reference_interfaces as interfaces  # noqa: E402
from reference_documents import projection_document  # noqa: E402

runner = interfaces.runner
window = interfaces.window
check = interfaces.check
settle = interfaces.settle


@pytest.mark.parametrize("operation", ["replace", "delete", "add"])
def test_existing_profile_transfers_projected_references_through_editor_and_history(
        window, tmp_path, monkeypatch, operation):
    doc = projection_document()
    if operation == "add":
        doc.features[2]["elements"][0].pop("references")
    source, destination = tmp_path / "source.json", tmp_path / "copy.json"
    doc.save(source)
    original = source.read_bytes()
    assert window.open_model(source, template=True)
    settle(window)
    initial = window.session.document.to_dict()
    check(window.session.result, "projection", operation == "add")
    item = next(window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())
                if window.tree.topLevelItem(i).data(0, Qt.UserRole) == "bad")
    window.tree.setCurrentItem(item)
    returned = []

    def edit(self, dialog):
        circle = copy.deepcopy(dialog.profile["segments"]["k1"])
        if operation != "add":
            assert dialog.projection_warning
            dialog.set_tool("select")
            dialog.select(["r1"])
            dialog.delete_action.trigger()
            assert not dialog.profile["references"]
        if operation != "delete":
            dialog.set_tool("project")
            dialog.click(0, -15)
            assert len(dialog.profile["references"]) == 1
        assert dialog.profile["segments"]["k1"] == circle
        returned.append(dialog.result_profile())
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(type(window), "_exec_dialog", edit)
    window.edit_feature_action.trigger()
    panel = window.feature_preview
    shapes = panel.editor.form.widget("elements")
    button = shapes._form.findChild(QPushButton, "open_sketcher")
    button.click()
    settle(window, panel.preview.session)
    assert len(returned) == 1
    assert window.session.document.to_dict() == initial
    check(panel.preview.session.result, "projection", True)
    panel.accept_button.click()
    assert window.feature_preview is None
    actual = window.session.feature("bad")["elements"][0]
    assert actual == returned[0]
    check(window.session.result, "projection", True)
    repaired = window.session.document.to_dict()
    assert repaired != initial  # reference-only changes must create a history step
    window.undo_action.trigger()
    settle(window)
    assert window.session.document.to_dict() == initial
    check(window.session.result, "projection", operation == "add")
    window.redo_action.trigger()
    settle(window)
    assert window.session.document.to_dict() == repaired
    check(window.session.result, "projection", True)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: (str(destination), ""))
    window.save_as_action.trigger()
    assert destination.is_file() and window.open_model(destination)
    settle(window)
    assert window.session.document.to_dict() == repaired
    check(window.session.result, "projection", True)
    assert source.read_bytes() == original
