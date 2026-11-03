"""Náhled fyzicky řeší vazby na kopii; pouze potvrzení vytvoří jeden krok Zpět."""

import copy

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit

import skodacad.assembly_session as session_module
from skodacad.assembly import AssemblyError
from skodacad.gui.assembly_parameter_preview import (
    AssemblyParameterPreviewDialog,
    placement_changes,
)
from test_assembly import write
from test_assembly_gui import app, dialogs, main_window, opened, project  # noqa: F401
from test_assembly_parameter_rename import geometry
from test_assembly_parameters import edit_cell


def constrained(request):
    w = request.getfixturevalue("opened")
    assert w.open_assembly(w.session.path.parent / "krabicka_s_vazbami.json")
    return w


def history(s):
    return (list(s._undo), list(s._redo), s.dirty, s.notice, s._checked, s._group)


def lid(result):
    return next(i.part for i in result.instances if i.ids == ("vicko",))


def test_preview_solves_actual_lid_on_copy_preserving_redo_group_cache_and_source_files(request):
    s = constrained(request).session
    s.set_parameters({"mezera": 5})
    s.undo()
    s.begin_group()
    s.notice = "původní zpráva"
    s._checked = ("key", "report")
    s.cache.waiting[("test", "pending")] = object()
    original, result = s.assembly, s.result
    before, shape, state = original.to_dict(), geometry(result), history(s)
    cache = (s.cache._parts.copy(), s.cache.waiting.copy())
    files = {status.file: status.file.read_bytes() for status in result.statuses}
    preview = s.preview_parameters({"vule": 12.5, "polovina": "vule/2"},
                                    renames=[("mezera", "vule")])
    assert preview.result.complete and len(preview.result.constraints) == 7
    assert preview.assembly.constraints[0].value == "vule"
    assert lid(preview.result).bounding_box().max.Z == pytest.approx(
        lid(result).bounding_box().max.Z + 12.5)
    assert preview.result.parameters["polovina"] == 6.25
    assert [r[0] for r in placement_changes(preview)] == ["vicko"]
    assert s.assembly is original and s.result is result and original.to_dict() == before
    assert history(s) == state and geometry(result) == shape
    assert (s.cache._parts, s.cache.waiting) == cache
    assert all(path.read_bytes() == data for path, data in files.items())


def test_repeated_previews_then_accept_are_one_undo_and_redo_with_renames(request):
    s = constrained(request).session
    before, shape = s.assembly.to_dict(), geometry(s.result)
    s.preview_parameters({"mezera": 5})
    preview = s.preview_parameters({"vule": 12.5}, renames=[("mezera", "vule")])
    assert not s.can_undo
    s.apply_parameter_preview(preview)
    assert geometry(s.result) == geometry(preview.result)
    assert s.assembly.parameters == {"vule": 12.5} and len(s._undo) == 1
    after = s.assembly.to_dict()
    s.undo()
    assert s.assembly.to_dict() == before and geometry(s.result) == shape
    s.redo()
    assert s.assembly.to_dict() == after and geometry(s.result) == geometry(preview.result)
    with pytest.raises(AssemblyError, match="od náhledu změnil"):
        s.apply_parameter_preview(preview)  # stejné hodnoty po Zpět/Znovu nejsou původní session


def test_unchanged_preview_accept_is_not_history(request):
    s = constrained(request).session
    before, result = s.assembly, s.result
    preview = s.preview_parameters(dict(before.parameters))
    assert not placement_changes(preview)
    s.apply_parameter_preview(preview)
    assert s.assembly is before and s.result is result and not s.can_undo and not s.dirty


@pytest.mark.parametrize("parameters", [{}, {"mezera": "missing+1"}, {"mezera": "1/0"}])
def test_invalid_preview_preserves_last_model_result_and_history(request, parameters):
    s = constrained(request).session
    original, result, state = s.assembly, s.result, history(s)
    with pytest.raises(AssemblyError):
        s.preview_parameters(parameters)
    assert s.assembly is original and s.result is result and history(s) == state


def test_conflicting_distance_reports_reason_without_accepting_or_losing_geometry(request):
    w = constrained(request)
    data = w.session.assembly.to_dict()
    other = copy.deepcopy(data["constraints"][0])
    other.update(id="locked", name="Pevná mezera", value=0)
    data["constraints"].append(other)
    assert w.open_assembly(write(w.session.path.parent / "locked.json", data))
    s = w.session
    assert s.result.complete
    before, result = s.assembly.to_dict(), s.result
    with pytest.raises(AssemblyError, match="odporují"):
        s.preview_parameters({"mezera": 10})
    assert s.assembly.to_dict() == before and s.result is result and not s.can_undo


@pytest.mark.parametrize("change", ["model", "in_place", "rebuild", "file", "missing", "path"])
def test_stale_preview_is_rejected_atomically_even_when_ids_are_reused(request, change):
    s = constrained(request).session
    preview = s.preview_parameters({"mezera": 12.5})
    file = next(status.file for status in s.result.statuses)
    if change == "model":
        s.set_parameters({"mezera": 2})
    elif change == "in_place":
        s.assembly.name = "Novější práce"
    elif change == "rebuild":
        s.rebuild()
    elif change == "file":
        file.write_bytes(file.read_bytes() + b"\n")
    elif change == "missing":
        file.unlink()
    else:
        s.path = s.path.with_name("new.json")
    before, result, state = s.assembly.to_dict(), s.result, history(s)
    with pytest.raises(AssemblyError):
        s.apply_parameter_preview(preview)
    assert s.assembly.to_dict() == before and s.result is result and history(s) == state


def test_file_change_during_confirmation_is_rejected_before_commit(request, monkeypatch):
    s = constrained(request).session
    preview = s.preview_parameters({"mezera": 12.5})
    file = next(status.file for status in s.result.statuses)
    original_build = session_module.build

    def changed_build(*args, **kwargs):
        result = original_build(*args, **kwargs)
        file.write_bytes(file.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(session_module, "build", changed_build)
    result, state = s.result, history(s)
    with pytest.raises(AssemblyError, match="od náhledu změnil"):
        s.apply_parameter_preview(preview)
    assert s.result is result and history(s) == state and s.assembly.parameters == {"mezera": 0}


def test_missing_source_cannot_be_disguised_by_unchanged_parameters(request):
    s = constrained(request).session
    next(status.file for status in s.result.statuses).unlink()
    with pytest.raises(AssemblyError):
        s.preview_parameters(dict(s.assembly.parameters))
    assert s.result.complete and not s.can_undo  # poslední dobrý výsledek zůstává


def test_working_preview_inputs_cannot_change_silently_before_confirmation(request):
    s = constrained(request).session
    preview = s.preview_parameters({"mezera": 12.5})
    preview.parameters["mezera"] = 20
    with pytest.raises(AssemblyError, match="neodpovídá náhledu"):
        s.apply_parameter_preview(preview)
    assert not s.can_undo and s.assembly.parameters == {"mezera": 0}


@pytest.mark.parametrize("accept", [False, True])
def test_real_dialog_preview_compare_back_or_apply_keeps_main_view_unchanged(request, accept):
    w = constrained(request)
    s = w.session
    original, result, before, state = s.assembly, s.result, s.assembly.to_dict(), history(s)
    w.show()
    seen = []

    def inspect_preview(dialog):
        assert isinstance(dialog, AssemblyParameterPreviewDialog)
        dialog.show()
        QTest.qWait(20)
        assert dialog.viewer is not w.viewer and dialog.viewer.parts[-1][1]
        assert "7/7" in dialog.summary.text() and "vicko" in dialog.changes.item(0, 0).text()
        assert dialog.viewer.highlighted and s.assembly is original and s.result is result
        assert history(s) == state and len(w.viewer.parts) == main_parts
        preview_part = dialog.viewer.parts[-1][0]
        QTest.mouseClick(dialog.original_box, Qt.MouseButton.LeftButton)
        assert "Původní sestava" in dialog.heading.text()
        assert dialog.viewer.parts[-1][0].bounding_box().max.Z < preview_part.bounding_box().max.Z
        assert not dialog.viewer.parts[-1][1]  # porovnání nepřizpůsobuje kameru znovu
        QTest.mouseClick(dialog.original_box, Qt.MouseButton.LeftButton)
        assert dialog.preview.parameters == {"vule": 12.5}
        QTest.mouseClick(dialog.apply_button if accept else dialog.back_button,
                         Qt.MouseButton.LeftButton)
        seen.append(True)
        return dialog.result()

    def inspect_parameters(dialog):
        dialog.show()
        QTest.qWait(20)
        edit_cell(dialog, 0, 0, "vule")
        edit_cell(dialog, 0, 1, "12,5")
        QTest.mouseClick(dialog.preview_button, Qt.MouseButton.LeftButton)
        if not accept:
            assert dialog.isVisible() and dialog.parameters() == {"vule": 12.5}
            assert s.assembly.to_dict() == before and history(s) == state
            dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        else:
            assert dialog.result() == QDialog.DialogCode.Accepted

    w._exec_parameter_preview = inspect_preview
    w._exec_dialog = inspect_parameters
    main_parts = len(w.viewer.parts)
    w.edit_parameters()
    assert seen == [True]
    if accept:
        assert len(s._undo) == 1 and s.assembly.parameters == {"vule": 12.5}
        s.undo()
        assert s.assembly.to_dict() == before
    else:
        assert s.assembly is original and s.result is result and len(w.viewer.parts) == main_parts


def test_real_click_finishes_active_cell_and_invalid_preview_stays_in_editor(request):
    w = constrained(request)
    seen = []

    def inspect_preview(dialog):
        assert dialog.preview.parameters == {"mezera": 12.5}
        seen.append(True)
        return QDialog.DialogCode.Rejected

    def inspect_parameters(dialog):
        dialog.show()
        QTest.qWait(20)
        dialog.table.setCurrentCell(0, 1)
        dialog.table.editItem(dialog.table.item(0, 1))
        editor = next(e for e in dialog.table.findChildren(QLineEdit) if e.isVisible())
        editor.selectAll()
        QTest.keyClicks(editor, "12,5")
        QTest.mouseClick(dialog.preview_button, Qt.MouseButton.LeftButton)
        assert seen == [True] and dialog.isVisible()
        dialog.delete_button.click()
        dialog.preview_button.click()
        assert "neznámý" in dialog.message.text() and seen == [True]
        dialog.reject()

    w._exec_parameter_preview = inspect_preview
    w._exec_dialog = inspect_parameters
    w.edit_parameters()
    assert not w.session.can_undo and w.session.assembly.parameters == {"mezera": 0}


def test_preview_keeps_visibility_isolation_transparency_and_main_selection(request):
    w = constrained(request)
    w.select(("nozicka_1",))
    w.toggle_selected_visibility()
    w.select(("vicko",))
    w.isolate_selected()
    w.transparency_percent.setValue(60)
    state = (w._visibility.copy(), w._isolated, w._selection, w._transparency.copy(),
             w._transparency_levels.copy(), len(w.viewer.parts))

    def inspect_preview(dialog):
        dialog.show()
        QTest.qWait(20)
        assert dialog._visible_ids == {("vicko",)}
        assert dialog.viewer.transparencies[0][1] == .6
        assert len(dialog.viewer.parts[-1][0].solids()) == 1
        return QDialog.DialogCode.Rejected

    w._exec_parameter_preview = inspect_preview
    assert not w.preview_parameters({"mezera": 12.5}, (), w.session.assembly)
    assert (w._visibility, w._isolated, w._selection, w._transparency,
            w._transparency_levels, len(w.viewer.parts)) == state
    assert not w.session.can_undo


def test_stale_preview_cannot_be_confirmed_through_parent_editor_either(request):
    w = constrained(request)

    def inspect_preview(dialog):
        w.session.set_parameters({"mezera": 3})  # novější práce během prohlížení
        dialog.accept()
        assert "od náhledu změnil" in dialog.message.text()
        assert not dialog.apply_button.isEnabled()
        return QDialog.DialogCode.Rejected

    def inspect_parameters(dialog):
        dialog.show()
        QTest.qWait(20)
        edit_cell(dialog, 0, 1, "12,5")
        dialog.show_preview()
        dialog.accept()
        assert "od otevření editoru změnila" in dialog.message.text()
        assert w.session.assembly.parameters == {"mezera": 3} and len(w.session._undo) == 1
        dialog.reject()

    w._exec_parameter_preview = inspect_preview
    w._exec_dialog = inspect_parameters
    w.edit_parameters()
