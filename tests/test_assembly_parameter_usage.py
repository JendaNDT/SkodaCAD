"""Skutečné odkazy ve výrazech sestavy a jejich přehled, bez úprav modelu."""

import copy

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox

from skodacad.assembly import Assembly
from skodacad.assembly_parameter_usage import parameter_usage
from skodacad.gui.assembly_parameters import AssemblyParametersDialog
from test_assembly import assembly_data, component
from test_assembly_gui import app, dialogs, main_window, opened, project  # noqa: F401
from test_assembly_parameters import edit_cell


def sample(parameters, position=(0, 0, 0), rotation=(0, 0, 0)):
    # Soubory záměrně neexistují: přehled čte recept, nikoli soubory nebo OCCT tvary.
    data = assembly_data([
        component("a", "chybi.json", name="Stejné jméno"),
        component("b", "chybi.json", position=position, rotation=rotation, name="Stejné jméno")
    ], parameters)
    return Assembly.from_dict(data)


@pytest.mark.parametrize("kind,label", [("position", "Posun"), ("rotation", "Otočení")])
@pytest.mark.parametrize("index,axis", enumerate("XYZ"))
def test_position_and_rotation_axes_have_exact_place_field_and_expression(kind, label, index, axis):
    values = [0, 0, 0]
    values[index] = "roztec / 2"
    assembly = sample({"roztec": 40}, **{kind: values})
    before = copy.deepcopy(assembly.to_dict())
    report = parameter_usage(assembly, assembly.parameters, "roztec")
    assert not report.warnings and len(report.uses) == 1
    use = report.uses[0]
    assert use.place == "Komponenta „Stejné jméno“ (b)"
    assert use.field == f"{label} {axis} [{'mm' if kind == 'position' else '°'}]"
    assert use.expression == "roztec / 2" and not use.via
    assert assembly.to_dict() == before


def test_forward_references_transitive_paths_and_diamond_report_each_site_once():
    raw = {"treti": "polovina+offset", "polovina": "roztec/2",
           "offset": "roztec+1", "roztec": 40, "nepouzity": 9}
    assembly = sample(raw, position=("treti", "polovina+roztec", "polovina+offset"))
    report = parameter_usage(assembly, raw, "roztec")
    places = {(u.place, u.field): u for u in report.uses}
    assert len(places) == len(report.uses) == 6
    assert places[("Parametr „polovina“", "Hodnota")].via == ()
    assert places[("Parametr „treti“", "Hodnota")].via == ("offset",)
    location = "Komponenta „Stejné jméno“ (b)"
    assert places[(location, "Posun X [mm]")].via == ("polovina", "treti")
    assert places[(location, "Posun Y [mm]")].via == ()  # přímý odkaz má přednost
    assert places[(location, "Posun Z [mm]")].via == ("offset",)
    assert not parameter_usage(assembly, raw, "nepouzity").uses


def test_names_are_identifiers_not_substrings_and_function_names_are_not_references():
    raw = {"d": 4, "delsi": 8, "šířka": "d * 2"}
    assembly = sample(raw, position=("delsi + sin(30)", "šířka", "max(d, delsi)"))
    report = parameter_usage(assembly, raw, "d")
    assert len(report.uses) == 3
    assert not any(use.field == "Posun X [mm]" for use in report.uses)
    assert next(use for use in report.uses if use.field == "Posun Y [mm]").via == ("šířka",)
    assert not parameter_usage(assembly, raw, "sin").uses


def test_cycle_is_finite_and_bad_syntax_is_explicitly_incomplete():
    raw = {"a": "b", "b": "a", "chyba": "a +"}
    assembly = sample(raw, position=("b", 0, 0))
    report = parameter_usage(assembly, raw, "a")
    assert len(report.uses) == 3 and len(report.warnings) == 1
    assert "chyba" in report.warnings[0]
    assert next(use for use in report.uses if use.field == "Posun X [mm]").via == ("b",)


def test_distance_constraint_and_subassembly_placement_use_only_current_context(examples_dir):
    assembly = Assembly.load(examples_dir / "sestavy/krabicka_s_vazbami.json")
    report = parameter_usage(assembly, {"mezera": "zaklad * 2", "zaklad": 5}, "zaklad")
    assert len(report.uses) == 2
    distance = next(use for use in report.uses if use.field == "Vzdálenost [mm]")
    assert distance.place == "Vazba „Víčko na okraji“ (v1)"
    assert distance.expression == "mezera" and distance.via == ("mezera",)
    # Vnitřní parametry souboru se nečtou a polohy nadřazené podsestavy se nezamlčí.
    nested = sample({"mezera": 8}, position=("mezera", 0, 0))
    nested.components[1].path = "podsestava-neexistuje.json"
    nested.components[1].name = "Podsestava"
    report = parameter_usage(nested, nested.parameters, "mezera")
    assert len(report.uses) == 1 and "Podsestava" in report.uses[0].place


def usage_rows(dialog):
    return [tuple(dialog.usage_table.item(row, col).text() for col in range(4))
            for row in range(dialog.usage_table.rowCount())]


def test_editor_browsing_and_draft_dependencies_preserve_model_history_and_sources(request):
    w = request.getfixturevalue("opened")
    assert w.open_assembly(w.session.path.parent / "krabicka_s_vazbami.json")
    before, result = copy.deepcopy(w.session.assembly.to_dict()), w.session.result
    history = (len(w.session._undo), len(w.session._redo), w.session.dirty)
    files = {s.file: s.file.read_bytes() for s in result.statuses}
    captured = []

    def inspect(dialog):
        dialog.show()
        QTest.qWait(20)
        assert usage_rows(dialog) == [(
            "Vazba „Víčko na okraji“ (v1)", "Vzdálenost [mm]", "mezera", "Přímo")]
        # Stejná hodnota, jiná závislost v pracovní tabulce; model se nepřepočítá.
        dialog.add_button.click()
        from PySide6.QtWidgets import QLineEdit

        field = next(e for e in dialog.table.findChildren(QLineEdit) if e.isVisible())
        field.selectAll()
        QTest.keyClicks(field, "zaklad")
        QTest.keyClick(field, Qt.Key.Key_Return)
        QTest.qWait(10)
        edit_cell(dialog, 0, 1, "zaklad * 2")
        dialog.table.setCurrentCell(1, 0)
        rows = usage_rows(dialog)
        assert ("Vazba „Víčko na okraji“ (v1)", "Vzdálenost [mm]",
                "mezera", "Přes mezera") in rows
        assert ("Parametr „mezera“", "Hodnota", "zaklad * 2", "Přímo") in rows
        assert w.session.assembly.to_dict() == before and w.session.result is result
        dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        captured.append(True)

    w._exec_dialog = inspect
    w.edit_parameters()
    assert captured == [True]
    assert w.session.assembly.to_dict() == before and w.session.result is result
    assert (len(w.session._undo), len(w.session._redo), w.session.dirty) == history
    assert all(path.read_bytes() == value for path, value in files.items())


def test_editor_updates_usage_on_invalid_repair_duplicate_delete_and_selection(request):
    request.getfixturevalue("app")
    dialog = AssemblyParametersDialog({"a": 10, "b": "a/2", "volny": 7}, lambda _: None)
    try:
        assert len(usage_rows(dialog)) == 1 and "a" in dialog.usage_title.text()
        dialog.table.item(1, 1).setText("a +")
        assert "není úplný" in dialog.usage_title.text()
        dialog.table.item(1, 1).setText("a/4")
        assert usage_rows(dialog)[0][2] == "a/4" and "není úplný" not in dialog.usage_title.text()
        dialog.table.setCurrentCell(2, 0)
        assert "nepoužívá" in dialog.usage_title.text() and not usage_rows(dialog)
        dialog.table.item(2, 0).setText("a")
        assert "už existuje" in dialog.message.text() and not usage_rows(dialog)
        assert dialog.table.item(2, 0).text() == "volny"
        dialog.table.item(2, 0).setText("volny")
        for _ in range(3):
            dialog.delete_button.click()
        assert "Vyber parametr" in dialog.usage_title.text() and not usage_rows(dialog)
    finally:
        dialog.close()
