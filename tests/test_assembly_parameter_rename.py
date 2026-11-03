"""Bezpečné přejmenování: přesné tokeny, skutečná tělesa, vazby a jedna transakce."""

import copy

import pytest
from PySide6.QtCore import QPersistentModelIndex, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox, QLineEdit

from skodacad.assembly import AssemblyError
from skodacad.assembly_parameter_rename import rename_expression, rename_parameters
from skodacad.assembly_session import AssemblySession
from test_assembly import assembly_data, component, part_data, write
from test_assembly_gui import app, dialogs, main_window, opened, project  # noqa: F401
from test_assembly_parameter_usage import usage_rows
from test_assembly_parameters import edit_cell, lid_bounds


def geometry(result):
    return [(i.ids, i.part.is_valid, round(i.part.volume, 7),
             sorted(tuple(round(v, 7) for v in point) for point in i.part.vertices()))
            for i in result.instances]


@pytest.mark.parametrize("value,expected", [
    ("d + delsi + d/2", "roztec + delsi + roztec/2"),
    ("  d * 1.00  # d zůstane v komentáři\n", "  roztec * 1.00  # d zůstane v komentáři\n"),
    (" \n(šířka + d\n + d)  ", " \n(šířka + roztec\n + roztec)  "),
    ("(šířka +\r\n d)", "(šířka +\r\n roztec)"),
    ("(d + # d \v poznámka\n d)", "(roztec + # d \v poznámka\n roztec)"),
    ("max(d, delsi) + sin(30)", "max(roztec, delsi) + sin(30)"),
    ("'d'", "'d'"),
    (12.5, 12.5),
])
def test_rename_changes_only_reference_tokens_and_preserves_other_spelling(value, expected):
    assert rename_expression(value, "d", "roztec", "Zkouška") == expected


def test_unicode_offsets_normalized_reference_and_callee_are_unambiguous():
    assert rename_expression("šířka + šířka/2", "šířka", "mezera", "X") == "mezera + mezera/2"
    assert rename_expression("𝑑 + d", "d", "šířka", "X") == "šířka + šířka"
    assert rename_expression("f + f(2)", "f", "delka", "X") == "delka + f(2)"


@pytest.mark.parametrize("new", ["", "má mezeru", "1x", "for", "pi", "sin", "𝑑", "obsazeny"])
def test_bad_target_is_atomic_and_never_merges_two_parameters(new):
    raw = {"d": 10, "obsazeny": "d/2"}
    before = copy.deepcopy(raw)
    with pytest.raises(AssemblyError):
        rename_parameters(raw, "d", new)
    assert raw == before


def test_unreadable_expression_refuses_rename_instead_of_guessing_references():
    raw = {"d": 10, "jiny": "d +"}
    with pytest.raises(AssemblyError, match="Nejprve jej oprav"):
        rename_parameters(raw, "d", "roztec")
    assert raw == {"d": 10, "jiny": "d +"}
    with pytest.raises(AssemblyError, match="nenašel"):
        rename_parameters(raw, "chybi", "novy")


def test_session_rename_preserves_physical_vertices_metadata_and_source_files(tmp_path):
    part = write(tmp_path / "d.json", part_data())
    source = part.read_bytes()
    path = write(tmp_path / "assembly.json", assembly_data([
        component("d", "d.json", fixed=True, name="d v popisu"),
        component("d2", "d.json", position=("d", "pulka", "d/4"),
                  rotation=("d/10", "d/20", "d/2"))],
        {"d": 40, "pulka": " d/2 ", "delsi": 50}, description="d v popisu"))
    session = AssemblySession()
    session.open(path)
    before, shape = copy.deepcopy(session.assembly.to_dict()), geometry(session.result)
    session.rename_parameter("d", "rozteč")
    after = session.assembly.to_dict()
    assert list(after["parameters"]) == ["rozteč", "pulka", "delsi"]
    assert after["parameters"]["pulka"] == " rozteč/2 "
    assert session.assembly.component("d2").position == ["rozteč", "pulka", "rozteč/4"]
    assert session.assembly.component("d2").rotation == ["rozteč/10", "rozteč/20", "rozteč/2"]
    assert after["description"] == before["description"]
    assert after["components"][0] == before["components"][0]  # id/název/cesta se nepřepisují
    assert geometry(session.result) == shape and all(entry[1] for entry in shape)
    assert len(session._undo) == 1
    session.undo()
    assert session.assembly.to_dict() == before and not session.can_undo
    session.redo()
    assert session.assembly.to_dict() == after and geometry(session.result) == shape
    session.save()
    session.open(path)
    assert session.assembly.parameters == after["parameters"] and geometry(session.result) == shape
    assert part.read_bytes() == source


def test_renamed_distance_remains_live_and_one_undo_restores_original_references(request):
    w = request.getfixturevalue("opened")
    assert w.open_assembly(w.session.path.parent / "krabicka_s_vazbami.json")
    before, physical = w.session.assembly.to_dict(), geometry(w.session.result)
    w.session.rename_parameter("mezera", "vule")
    assert w.session.assembly.constraints[0].value == "vule"
    assert geometry(w.session.result) == physical and w.session.result.complete
    assert len(w.session._undo) == 1
    original = lid_bounds(w)
    w.session.set_parameters({"vule": 12.5})
    assert lid_bounds(w)[1][2] == pytest.approx(original[1][2] + 12.5)
    assert all(c.state == "ok" for c in w.session.result.constraints)
    w.session.undo()
    w.session.undo()
    assert w.session.assembly.to_dict() == before and not w.session.can_undo


def test_noop_and_failed_rename_preserve_result_dirty_and_existing_redo(request):
    w = request.getfixturevalue("opened")
    w.session.set_parameters({**w.session.assembly.parameters, "a": 10, "b": "a/2"})
    w.session.set_info(description="Poznámka")
    w.session.undo()
    before, result = w.session.assembly.to_dict(), w.session.result
    history = (len(w.session._undo), len(w.session._redo), w.session.dirty)
    w.session.rename_parameter("a", "a")
    with pytest.raises(AssemblyError, match="už existuje"):
        w.session.rename_parameter("a", "b")
    assert w.session.assembly.to_dict() == before and w.session.result is result
    assert (len(w.session._undo), len(w.session._redo), w.session.dirty) == history


def test_bad_placement_refuses_all_changes_even_after_other_axes_were_rewritten(tmp_path):
    write(tmp_path / "d.json", part_data())
    path = write(tmp_path / "assembly.json", assembly_data([
        component("a", "d.json", position=("d", "d +", 0))], {"d": 10}))
    session = AssemblySession()
    session.open(path)
    before, result = session.assembly.to_dict(), session.result
    with pytest.raises(AssemblyError, match="Poloha komponenty"):
        session.rename_parameter("d", "roztec")
    assert session.assembly.to_dict() == before and session.result is result
    assert not session.can_undo and not session.dirty


def test_editor_rename_button_updates_working_usage_and_cancel_preserves_model(request):
    w = request.getfixturevalue("opened")
    assert w.open_assembly(w.session.path.parent / "krabicka_s_vazbami.json")
    before, result = w.session.assembly.to_dict(), w.session.result
    seen = []

    def interact(dialog):
        dialog.show()
        QTest.qWait(20)
        stable = QPersistentModelIndex(dialog.table.model().index(0, 0))
        dialog.rename_button.click()
        editor = next(e for e in dialog.table.findChildren(QLineEdit) if e.isVisible())
        editor.selectAll()
        QTest.keyClicks(editor, "vule")
        QTest.keyClick(editor, Qt.Key.Key_Return)
        QTest.qWait(10)
        assert stable.isValid() and stable.data() == "vule"
        assert usage_rows(dialog) == [(
            "Vazba „Víčko na okraji“ (v1)", "Vzdálenost [mm]", "vule", "Přímo")]
        assert w.session.assembly.to_dict() == before and w.session.result is result
        dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        seen.append(True)

    w._exec_dialog = interact
    w.edit_parameters()
    assert seen == [True] and not w.session.can_undo
    assert w.session.assembly.to_dict() == before and w.session.result is result


def test_multiple_renames_and_swap_apply_once_with_identical_geometry(request, tmp_path):
    w = request.getfixturevalue("opened")
    # Dvě hodnoty řídí různé osy; prohození názvů musí zachovat jejich význam.
    base_parameters = w.session.assembly.parameters
    w.session.set_parameters({"a": 40, "b": 20, "odvozena": "a/2", **base_parameters})
    w.session.set_placement("nozicka_1", position=("a", "b", "odvozena"))
    w.session.save()
    w.session.open(w.session.path)
    w._refresh()
    before, physical = w.session.assembly.to_dict(), geometry(w.session.result)
    seen = []

    def interact(dialog):
        dialog.show()
        QTest.qWait(20)
        edit_cell(dialog, 0, 0, "docasny")
        edit_cell(dialog, 1, 0, "a")
        edit_cell(dialog, 0, 0, "b")
        assert dialog.parameters() == {"b": 40, "a": 20, "odvozena": "b/2", **base_parameters}
        assert w.session.assembly.to_dict() == before
        dialog.apply_button.click()
        seen.append(True)

    w._exec_dialog = interact
    w.edit_parameters()
    assert seen == [True]
    assert geometry(w.session.result) == physical and len(w.session._undo) == 1
    assert w.session.assembly.component("nozicka_1").position == ["b", "a", "odvozena"]
    w.undo()
    assert w.session.assembly.to_dict() == before and not w.session.can_undo
    w.redo()
    assert geometry(w.session.result) == physical


def test_root_rename_keeps_nested_parameters_and_all_source_bytes(tmp_path):
    part = write(tmp_path / "d.json", part_data())
    nested = write(tmp_path / "nested.json", assembly_data([
        component("inner", "d.json", position=("d", 0, 0))], {"d": 10}))
    root = write(tmp_path / "root.json", assembly_data([
        component("nested", "nested.json", position=("d", 0, 0))], {"d": 40}))
    sources = {p: p.read_bytes() for p in (part, nested)}
    session = AssemblySession()
    session.open(root)
    before = geometry(session.result)
    session.rename_parameter("d", "roztec")
    assert session.assembly.component("nested").position == ["roztec", 0, 0]
    assert geometry(session.result) == before and session.result.complete
    assert all(p.read_bytes() == content for p, content in sources.items())
