"""Editor parametrů: skutečná poloha těles, vazby, atomické odmítnutí a historie."""

import math

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit

from skodacad.assembly import AssemblyError
from skodacad.assembly_session import AssemblySession
from skodacad.gui.assembly_parameters import AssemblyParametersDialog
from skodacad.gui.assembly_window import AssemblyWindow
from test_assembly import assembly_data, component, part_data, write
from test_assembly_gui import app, dialogs, main_window, opened, project  # noqa: F401
from test_gui import FakeViewer


def lid_bounds(window):
    part = next(i.part for i in window.session.result.instances if i.ids == ("vicko",))
    assert part.is_valid
    return tuple(part.bounding_box().min), tuple(part.bounding_box().max)


def edit_cell(dialog, row, column, text):
    """Zadání přes skutečný editor buňky, včetně potvrzení Enterem."""
    dialog.table.setFocus()
    dialog.table.setCurrentCell(row, column)
    dialog.table.editItem(dialog.table.item(row, column))
    editor = next((e for e in dialog.table.findChildren(QLineEdit) if e.isVisible()), None)
    assert editor is not None and editor.isVisible()
    editor.selectAll()
    QTest.keyClicks(editor, text)
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.qWait(10)  # Qt odloží uzavření delegátu buňky do fronty událostí


def test_editor_applies_dependent_values_to_real_constraint_and_one_undo(request):
    w = request.getfixturevalue("opened")
    assert w.open_assembly(w.session.path.parent / "krabicka_s_vazbami.json")
    before = w.session.assembly.to_dict()
    bounds = lid_bounds(w)
    sources = {s.file: s.file.read_bytes() for s in w.session.result.statuses}
    w.show()
    captured = []

    def interact(dialog):
        dialog.show()
        QTest.qWait(20)
        assert isinstance(dialog, AssemblyParametersDialog)
        assert not dialog.table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable
        QTest.mouseClick(dialog.add_button, Qt.MouseButton.LeftButton)
        # Přidání zahájí editaci názvu; nejprve ji dokončíme.
        editor = dialog.table.findChild(QLineEdit)
        editor.selectAll()
        QTest.keyClicks(editor, "zdvih")
        QTest.keyClick(editor, Qt.Key.Key_Return)
        QTest.qWait(10)
        edit_cell(dialog, 1, 1, "6,25")
        edit_cell(dialog, 0, 1, "zdvih * 2")
        assert dialog.table.item(0, 2).text() == "12,5"
        assert w.session.assembly.to_dict() == before  # jen pracovní tabulka
        QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
        captured.append(dialog.result())

    w._exec_dialog = interact
    QTest.mouseClick(w.parameters_button, Qt.MouseButton.LeftButton)
    assert captured == [QDialog.DialogCode.Accepted]
    assert w.session.assembly.parameters == {"mezera": "zdvih * 2", "zdvih": 6.25}
    assert lid_bounds(w)[0][2] == pytest.approx(bounds[0][2] + 12.5)
    assert lid_bounds(w)[1][2] == pytest.approx(bounds[1][2] + 12.5)
    assert w.session.result.complete and all(c.state == "ok" for c in w.session.result.constraints)
    assert all(path.read_bytes() == original for path, original in sources.items())
    w.undo()
    assert w.session.assembly.to_dict() == before and not w.session.can_undo
    w.redo()
    assert lid_bounds(w)[1][2] == pytest.approx(bounds[1][2] + 12.5)
    w.session.save()
    path = w.session.path
    w.session.open(path)
    assert w.session.assembly.parameters == {"mezera": "zdvih * 2", "zdvih": 6.25}
    assert lid_bounds(w)[1][2] == pytest.approx(bounds[1][2] + 12.5)


@pytest.mark.parametrize("parameters, message", [
    ({"a": "b", "b": "a"}, "kruhu"),
    ({"a": "chybi/2"}, "neznámý"),
    ({"a": "1/0"}, "nulou"),
    ({"a": "sqrt(-1)"}, "nejde spočítat"),
    ({"a": "sqrt(1, 2)"}, "argumentů"),
    ({"a": "1e309"}, "konečné"),
    ({"pi": 10}, "název"),
    ({"for": 10}, "název"),
    ({"": 10}, "název"),
    ({"a": ""}, "nemá hodnotu"),
])
def test_invalid_table_never_calls_model(request, parameters, message):
    request.getfixturevalue("app")
    calls = []
    dialog = AssemblyParametersDialog(parameters, calls.append)
    try:
        assert not dialog.apply_button.isEnabled()
        assert message in dialog.message.text()
        dialog.accept()
        assert not calls and dialog.result() != QDialog.DialogCode.Accepted
    finally:
        dialog.close()


def test_duplicate_name_repair_delete_and_cancel_are_only_staged(request):
    request.getfixturevalue("app")
    calls = []
    dialog = AssemblyParametersDialog({"a": 10, "b": "a/2"}, calls.append)
    try:
        dialog.table.item(1, 0).setText("a")
        assert "dvakrát" in dialog.message.text() and not dialog.apply_button.isEnabled()
        dialog.table.item(1, 0).setText("b")
        assert dialog.apply_button.isEnabled() and dialog.table.item(1, 2).text() == "5"
        dialog.table.setCurrentCell(1, 0)
        dialog.delete_button.click()
        assert dialog.parameters() == {"a": 10}
        dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        assert not calls and dialog.result() == QDialog.DialogCode.Rejected
    finally:
        dialog.close()


@pytest.mark.parametrize("use", ["position", "rotation", "constraint"])
@pytest.mark.parametrize("parameters", [{}, {"jiny_nazev": 20}, {"v": "1/0"}])
def test_used_parameter_removal_or_bad_value_is_atomic(request, tmp_path, use, parameters):
    request.getfixturevalue("app")
    write(tmp_path / "box.json", part_data())
    parts = [component("a", "box.json", fixed=True), component("b", "box.json")]
    extra = {}
    if use == "constraint":
        extra = {"version": 30, "constraints": [{"id": "gap", "type": "distance", "value": "v",
                 "a": {"component": "a", "face": {"at": [15, 10, 10],
                       "normal": [0, 0, 1], "type": "plane"}},
                 "b": {"component": "b", "face": {"at": [15, 10, 0],
                       "normal": [0, 0, -1], "type": "plane"}}}]}
    else:
        parts[1]["placement"][use][0] = "v"
    path = write(tmp_path / "assembly.json", assembly_data(parts, {"v": 10}, **extra))
    w = AssemblyWindow(viewer_factory=FakeViewer, user_dir=tmp_path)
    try:
        assert w.open_assembly(path)
        w.session.save()  # řešič při prvním otevření umístí dosud nesplněnou vazbu
        saved = path.read_bytes()
        before, result = w.session.assembly.to_dict(), w.session.result
        dialog = AssemblyParametersDialog(parameters, w.apply_parameters, w)
        dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted
        assert w.session.assembly.to_dict() == before and w.session.result is result
        assert not w.session.dirty and not w.session.can_undo
        assert dialog.message.text() and path.read_bytes() == saved
    finally:
        w.session.dirty = False
        w.close()


def test_parameters_move_and_rotate_physical_copy_without_altering_source(tmp_path):
    part = write(tmp_path / "box.json", part_data())
    original = part.read_bytes()
    path = write(tmp_path / "assembly.json", assembly_data([
        component("a", "box.json", fixed=True),
        component("b", "box.json", position=("roztec", "roztec/2", 0),
                  rotation=(0, 0, "uhel"))], {"roztec": 40, "uhel": 0}))
    session = AssemblySession()
    session.open(path)
    before = session.assembly.to_dict()
    session.set_parameters({"roztec": 80, "uhel": 90})
    b = next(i.part for i in session.result.instances if i.ids == ("b",))
    assert b.is_valid and b.volume == pytest.approx(6000)
    assert tuple(b.bounding_box().min) == pytest.approx((60, 40, 0))
    assert tuple(b.bounding_box().max) == pytest.approx((80, 70, 10))
    assert part.read_bytes() == original
    session.undo()
    assert session.assembly.to_dict() == before and not session.can_undo
    session.redo()
    assert tuple(session.result.instances[1].part.bounding_box().min) == pytest.approx((60, 40, 0))
    with pytest.raises(AssemblyError, match="konečné"):
        session.set_parameters({"roztec": math.inf, "uhel": 90})


def test_empty_assembly_can_add_parameters_and_unchanged_accept_is_not_history(request, tmp_path):
    request.getfixturevalue("app")
    w = AssemblyWindow(viewer_factory=FakeViewer, user_dir=tmp_path)
    try:
        assert not w.parameters_action.isEnabled() and not w.parameters_button.isEnabled()
        w.new_assembly(tmp_path / "empty.json")
        assert w.parameters_action.isEnabled() and w.parameters_button.isEnabled()
        dialog = AssemblyParametersDialog({}, w.apply_parameters, w)
        dialog.accept()
        assert not w.session.can_undo and not w.session.dirty
        dialog = AssemblyParametersDialog({"roztec": 120}, w.apply_parameters, w)
        dialog.accept()
        assert w.session.assembly.parameters == {"roztec": 120}
        w.undo()
        assert not w.session.assembly.parameters and not w.session.can_undo
    finally:
        w.session.dirty = False
        w.close()


def test_conflicting_parameter_preserves_result_and_existing_redo(request):
    w = request.getfixturevalue("opened")
    assert w.open_assembly(w.session.path.parent / "krabicka_s_vazbami.json")
    w.session.set_fixed("vicko", True)
    w.session.set_info(description="Dočasná poznámka")
    w.session.undo()  # neúspěšné zadání musí zachovat i existující Znovu
    before, result = w.session.assembly.to_dict(), w.session.result
    history = (len(w.session._undo), len(w.session._redo), w.session.dirty)
    dialog = AssemblyParametersDialog({"mezera": 20}, w.apply_parameters, w)
    dialog.accept()
    assert "odporují" in dialog.message.text()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert w.session.assembly.to_dict() == before and w.session.result is result
    assert (len(w.session._undo), len(w.session._redo), w.session.dirty) == history


def test_cancel_or_escape_during_live_cell_edit_never_mutates_model(request):
    w = request.getfixturevalue("opened")
    before, result = w.session.assembly.to_dict(), w.session.result
    dialog = AssemblyParametersDialog({"roztec": 10}, w.apply_parameters, w)
    dialog.show()
    QTest.qWait(20)
    dialog.table.setCurrentCell(0, 1)
    dialog.table.editItem(dialog.table.item(0, 1))
    field = next(e for e in dialog.table.findChildren(QLineEdit) if e.isVisible())
    field.selectAll()
    QTest.keyClicks(field, "25")
    dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert w.session.assembly.to_dict() == before and w.session.result is result
    assert not w.session.can_undo and not w.session.dirty
