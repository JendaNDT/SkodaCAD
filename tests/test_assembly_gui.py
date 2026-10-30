"""P5.2B: okno sestavy offscreen – strom, poloha, Zpět, chybějící díl, výpočet na pozadí."""

import json
import shutil

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from skodacad.gui.assembly_window import AssemblyWindow, parse_value  # noqa: E402
from skodacad.gui.main_window import MainWindow  # noqa: E402
from test_gui import FakeViewer  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialogs(monkeypatch):
    """Dialogy by v testu čekaly – odpovědi se nastaví předem (výchozí = zrušit)."""
    answers = {"open": "", "save": "", "question": QMessageBox.StandardButton.Cancel}
    shown = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (answers["open"], ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (answers["save"], ""))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[1:3]))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: shown.append(a[1]) or answers["question"])
    answers["shown"] = shown
    return answers


@pytest.fixture
def project(tmp_path, examples_dir):
    """Kopie ukázky: projekt/krabicka.json a projekt/sestavy/… (cesta ../krabicka.json)."""
    root = tmp_path / "projekt"
    shutil.copytree(examples_dir / "sestavy", root / "sestavy")
    shutil.copy(examples_dir / "krabicka.json", root / "krabicka.json")
    return root


@pytest.fixture
def main_window(app, examples_dir, tmp_path, dialogs):
    window = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    yield window
    for assembly in window.assembly_windows:
        assembly.session.dirty = False
        assembly.close()
    window.session.dirty = False
    window.close()


@pytest.fixture
def opened(main_window, project):
    window = main_window.open_assembly(project / "sestavy" / "krabicka_s_vickem.json")
    assert window is not None
    return window


def items(window):
    result = []

    def walk(item, depth):
        result.append(("  " * depth + item.text(0), item.text(2)))
        for index in range(item.childCount()):
            walk(item.child(index), depth + 1)

    for index in range(window.tree.topLevelItemCount()):
        walk(window.tree.topLevelItem(index), 0)
    return result


def pick(window, component):
    for index in range(window.tree.topLevelItemCount()):
        item = window.tree.topLevelItem(index)
        if item.data(0, 256) == json.dumps([component]):
            window.tree.setCurrentItem(item)
            return
    raise AssertionError(component)


def press(window, text):
    matches = [a for a in window.findChildren(QAction) if a.text() == text]
    assert matches, f"akce „{text}“ v okně není"
    matches[0].trigger()


def test_open_from_main_window_shows_tree_3d_and_summary(main_window, opened, project):
    assert main_window.session.document is None  # díl v hlavním okně se neotevřel
    assert items(opened)[:2] == [("Krabička (pevná)", "✓"), ("Víčko", "✓")]
    assert len(items(opened)) == 6
    part, fit = opened.viewer.parts[-1]
    assert fit and part.volume == pytest.approx(opened.session.result.volume_mm3)
    assert "Objem: 31309,29 mm³" in opened.summary.text()
    assert "Krabička s víčkem – krabicka_s_vickem.json" in opened.windowTitle()
    # I Otevřít v hlavním okně pozná sestavu podle „kind“, ne přípony.
    again = main_window.open_model(project / "sestavy" / "krabicka_s_vickem.json")
    assert again and len(main_window.assembly_windows) == 2


def test_form_changes_position_name_as_one_undo_step(opened):
    pick(opened, "nozicka_1")
    assert [e.text() for e in opened.position_edits] == ["-x0", "-y0", "-h"]
    assert opened.viewer.highlighted  # hrany vybrané kopie
    opened.name_edit.setText("Přední levá")
    opened.position_edits[2].setText("-h - 1.5")
    opened.position_edits[0].setText("-30,5")
    opened.apply_form()
    component = opened.session.assembly.component("nozicka_1")
    assert component.position == [-30.5, "-y0", "-h - 1.5"]
    box = opened.session.result.instances[2].part.bounding_box()
    assert (box.min.X, box.min.Z) == pytest.approx((-35.5, -4.5))
    assert component.name == "Přední levá" and opened.session.dirty
    assert "*" in opened.windowTitle()
    press(opened, "Zpět")
    component = opened.session.assembly.component("nozicka_1")
    assert component.position == ["-x0", "-y0", "-h"] and component.name == "Nožička 1"
    assert not opened.session.can_undo
    press(opened, "Znovu")
    assert opened.session.assembly.component("nozicka_1").name == "Přední levá"


def test_bad_expression_in_form_is_czech_error_and_nothing_changes(opened, dialogs):
    pick(opened, "vicko")
    opened.position_edits[2].setText("H + neznamy")
    opened.apply_form()
    assert opened.session.result.status("vicko").state == "error"
    assert "neznamy" in opened.session.result.status("vicko").reason
    opened.position_edits[2].setText("")
    opened.apply_form()
    assert dialogs["shown"][-1][0] == "Polohu nejde použít"


def test_turn_buttons_and_fixed_box(opened, dialogs):
    pick(opened, "nozicka_2")
    [button for button in opened.turn_buttons if button.text() == "X +90°"][0].click()
    assert opened.session.assembly.component("nozicka_2").rotation == [90, 0, 0]
    opened.fixed_box.setChecked(True)
    assert opened.session.assembly.component("nozicka_2").fixed
    assert "Nožička 2 (pevná)" in [name for name, _ in items(opened)]
    pick(opened, "vicko")
    opened.position_edits[0].setText("x0")
    opened.apply_form()
    assert opened.session.assembly.component("vicko").position[0] == "x0"
    pick(opened, "krabicka")
    opened.session.rebuild()
    assert opened.fixed_box.isChecked()


def test_missing_part_is_marked_and_relink_asks_before_other_recipe(opened, project, dialogs):
    assert opened.save()  # zapíše otisky dílů – podle nich se pozná jiný recept
    (project / "sestavy" / "dily" / "vicko.json").rename(project / "jinde.json")
    press(opened, "Načíst díly znovu")
    assert ("Víčko", "✕ chybí") in items(opened)
    assert "NEÚPLNÁ" in opened.summary.text()
    other = project / "sestavy" / "dily" / "nozicka.json"
    opened.relink("vicko", other)  # jiný recept → otázka → Zrušit
    assert opened.session.assembly.component("vicko").path == "dily/vicko.json"
    assert "Jiný díl?" in dialogs["shown"]
    assert opened.relink("vicko", project / "jinde.json")
    assert opened.session.assembly.component("vicko").path == "../jinde.json"
    assert opened.session.result.complete


def test_insert_remove_and_pick_in_3d(opened, project, dialogs):
    new = opened.insert(project / "sestavy" / "dily" / "nozicka.json")
    assert new == "nozicka_5" and opened._selected == ("nozicka_5",)
    assert len(items(opened)) == 7
    instance = opened.session.result.instances[1]
    opened.viewer.selection_changed.emit([instance.part.faces()[0].wrapped])
    assert opened._selected == ("vicko",)
    pick(opened, "nozicka_5")
    press(opened, "Smazat komponentu")
    assert len(items(opened)) == 6 and opened._selected is None
    dialogs["open"] = str(project / "sestavy" / "dily" / "nozicka.json")
    press(opened, "Vložit díl…")
    assert len(items(opened)) == 7
    dialogs["open"] = str(project / "sestavy" / "krabicka_s_vickem.json")
    press(opened, "Vložit díl…")
    assert dialogs["shown"][-1][0] == "Díl nejde vložit"


def test_open_part_switches_main_window_to_the_part_file(main_window, opened, project):
    pick(opened, "vicko")
    opened.open_part_button.click()
    assert main_window.session.path == (project / "sestavy" / "dily" / "vicko.json").resolve() \
        or main_window.session.path == project / "sestavy" / "dily" / "vicko.json"
    assert main_window.session.document.name == "Víčko krabičky"


def test_new_assembly_and_file_actions(main_window, tmp_path, project, dialogs):
    dialogs["save"] = ""
    assert main_window.new_assembly_dialog() is None  # zrušeno → žádné okno
    dialogs["save"] = str(tmp_path / "moje")
    window = main_window.new_assembly_dialog()
    assert window is not None and (tmp_path / "moje.json").is_file()
    assert window.session.assembly.name == "moje" and items(window) == []
    window.insert(project / "sestavy" / "dily" / "nozicka.json")
    assert window.session.assembly.components[0].fixed
    press(window, "Uložit")
    saved = json.loads((tmp_path / "moje.json").read_text(encoding="utf-8"))
    assert saved["components"][0]["source"]["path"] == "projekt/sestavy/dily/nozicka.json"
    dialogs["save"] = str(tmp_path / "kopie.json")
    press(window, "Uložit jako…")
    assert (tmp_path / "kopie.json").is_file() and window.session.path.name == "kopie.json"
    dialogs["open"] = str(project / "sestavy" / "krabicka_s_vickem.json")
    press(window, "Otevřít sestavu…")
    assert len(items(window)) == 6
    dialogs["save"] = ""
    press(window, "Nová sestava…")
    assert len(items(window)) == 6  # zrušeno – sestava zůstala


def test_example_assembly_is_a_template_and_example_stays_untouched(main_window, examples_dir,
                                                                     tmp_path, dialogs):
    sample = examples_dir / "sestavy" / "krabicka_s_vickem.json"
    original = sample.read_bytes()
    press(main_window, "krabicka_s_vickem")
    window = main_window.assembly_windows[-1]
    pick(window, "vicko")
    window.position_edits[2].setText("40")
    window.apply_form()
    dialogs["save"] = str(tmp_path / "moje_krabicka.json")
    press(window, "Uložit")  # ukázka = Uložit se zeptá kam
    assert sample.read_bytes() == original
    saved = json.loads((tmp_path / "moje_krabicka.json").read_text(encoding="utf-8"))
    assert saved["components"][1]["placement"]["position"][2] == 40
    # Díly ukázky se zkopírovaly k sestavě – projekt nezávisí na složce ukázek ani disku
    # (na Windows jsou ukázky na jiném disku než uživatelská složka).
    assert [c["source"]["path"] for c in saved["components"]] == [
        "dily/krabicka.json", "dily/vicko.json", *["dily/nozicka.json"] * 4]
    assert (tmp_path / "dily" / "vicko.json").read_bytes() == \
        (examples_dir / "sestavy" / "dily" / "vicko.json").read_bytes()
    reopened = main_window.open_assembly(tmp_path / "moje_krabicka.json")
    assert reopened.session.result.complete and not reopened.session.result.warnings


def test_closing_with_unsaved_changes_asks(opened, dialogs):
    pick(opened, "vicko")
    opened.turn("z", 90)
    dialogs["question"] = QMessageBox.StandardButton.Cancel
    assert not opened.close()
    dialogs["question"] = QMessageBox.StandardButton.Discard
    press(opened, "Zavřít sestavu")
    assert not opened.isVisible()


def test_parse_value():
    assert parse_value("12") == 12 and parse_value("2,5") == 2.5 and parse_value("H/2") == "H/2"
    with pytest.raises(ValueError):
        parse_value("  ")


def test_background_runner_computes_parts_without_blocking(app, project, dialogs):
    from PySide6.QtTest import QTest

    from skodacad.worker import BackgroundRebuilder

    runner = BackgroundRebuilder()
    window = AssemblyWindow(FakeViewer, runner=runner)
    try:
        assert window.open_assembly(project / "sestavy" / "krabicka_s_vickem.json")
        assert {state for _name, state in items(window)} == {"… počítá se"}
        assert "Počítám díly sestavy na pozadí" in window.summary.text()
        for _ in range(1200):
            if not window.computing:
                break
            QTest.qWait(100)
        assert not window.computing
        assert window.session.result.complete and len(window.session.result.instances) == 6
        assert window.session.result.volume_mm3 == pytest.approx(31309.287, abs=0.01)
    finally:
        window.session.dirty = False
        window.close()
        runner.close()


# --- P5.3B: vazby v okně (B20) ---------------------------------------------------------


@pytest.fixture
def constrained(main_window, project):
    window = main_window.open_assembly(project / "sestavy" / "krabicka_s_vazbami.json")
    assert window is not None and window.session.result.complete
    return window


def pick_constraint(window, constraint_id):
    for index in range(window.tree.topLevelItemCount()):
        group = window.tree.topLevelItem(index)
        for child in range(group.childCount()):
            item = group.child(child)
            if item.data(0, 256) == json.dumps({"constraint": constraint_id}):
                window.tree.setCurrentItem(item)
                return
    raise AssertionError(constraint_id)


def plane_face(window, component, normal_z, z):
    instance = next(i for i in window.session.result.instances if i.ids == (component,))
    return next(f for f in instance.part.faces() if f.geom_type.name == "PLANE"
                and abs(f.normal_at().Z - normal_z) < 1e-9 and abs(f.center().Z - z) < 1e-9)


def click(window, face, point, add=False):
    """Klik (s Ctrl ``add``) ve 3D jako skutečný prohlížeč: místo kliknutí + výběr."""
    window.viewer.picked_point = point
    shapes = [shape for shape, _at in window._picks] if add else []
    window.viewer.selection_changed.emit([*shapes, face.wrapped])


def test_b20_constraints_in_tree_add_by_two_clicks_edit_and_delete(constrained, dialogs,
                                                                   monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window = constrained
    rows = items(window)
    assert ("Víčko", "✓ plně určená") in rows
    assert ("Nožička 1", "✓ volná: 2 posuny, 1 otočení") in rows
    assert ("Vazby (7)", "") in rows and ("  Víčko na okraji", "✓") in rows
    assert "Vazby: 7, splněné 7" in window.summary.text()
    # Smazat vazbu: výběr ve stromu, Delete = jeden krok Zpět.
    pick_constraint(window, "v4")
    assert window.constraint_box.isVisibleTo(window) and window.viewer.highlighted
    assert "Dotyk: Krabička ↔ Nožička 1" in window.constraint_note.text()
    press(window, "Smazat vazbu")
    assert "v4" not in [c.id for c in window.session.assembly.constraints]
    assert ("Nožička 1", "✓") in items(window) and len(window.session._undo) == 1
    # Přidat vazbu: klik na dno krabičky, Ctrl+klik na horní plochu nožičky.
    asked = {}
    monkeypatch.setattr(QInputDialog, "getItem",
                        lambda *a, **k: asked.setdefault("item", a[3]) and ("vzdálenost", True))
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *a, **k: asked.setdefault("text", a[4]) and ("2", True))
    assert not window.constraint_action.isEnabled()
    click(window, plane_face(window, "krabicka", -1, 0), (-32, -17, 0))
    click(window, plane_face(window, "nozicka_1", 1, 0), (-32, -17, 0), add=True)
    assert window.constraint_action.isEnabled() and "Vybrané plochy: 2" in window.pick_note.text()
    press(window, "Přidat vazbu…")
    assert asked == {"item": ["dotyk", "zarovnání", "vzdálenost"], "text": "0"}
    new = window.session.assembly.constraints[-1]
    assert new.type == "distance" and new.value == 2 and window._constraint == new.id
    assert new.a == {"component": "krabicka", "face": {
        "at": [-32, -17, 0], "normal": [0, 0, -1], "type": "plane"}}
    assert new.b == {"component": "nozicka_1", "face": {
        "at": [0, 0, 3], "normal": [0, 0, 1], "type": "plane"}}
    assert window.session.assembly.component("nozicka_1").position == [-32, -17, -5]
    assert ("Nožička 1", "✓ volná: 2 posuny, 1 otočení") in items(window)
    assert len(window.session._undo) == 2
    # Upravit vzdálenost ve formuláři vazby = jeden krok Zpět.
    window.constraint_value.setText("1,5")
    window.constraint_name.setText("Nožička pod dnem")
    window.constraint_apply.click()
    assert window.session.assembly.component("nozicka_1").position == [-32, -17, -4.5]
    assert ("  Nožička pod dnem", "✓") in items(window) and len(window.session._undo) == 3
    for _ in range(3):
        press(window, "Zpět")
    assert len(window.session.assembly.constraints) == 7 and not window.session.can_undo


def test_constraint_errors_in_window_are_czech_dialogs(constrained, dialogs):
    window = constrained
    press(window, "Přidat vazbu…")  # bez výběru: tlačítko je vypnuté, akce nic neudělá
    window.add_constraint_dialog()
    assert dialogs["shown"][-1][0] == "Přidat vazbu"
    box = plane_face(window, "krabicka", -1, 0)
    click(window, box, (0, 0, 0))
    click(window, plane_face(window, "krabicka", 1, 2), (0, 0, 2), add=True)  # dno uvnitř
    window.add_constraint_dialog()
    assert dialogs["shown"][-1] == ("Vazbu nejde přidat", "Obě plochy patří ke stejné "
                                    "komponentě – druhou plochu vyber na jiné komponentě.")
    foot = next(i for i in window.session.result.instances if i.ids == ("nozicka_2",))
    side = next(f for f in foot.part.faces() if f.geom_type.name == "CYLINDER")
    click(window, box, (0, 0, 0))
    click(window, side, (37, -17, -1.5), add=True)
    window.add_constraint_dialog()
    assert "dvě rovinné plochy" in dialogs["shown"][-1][1]
    rim = {"component": "krabicka",
           "face": {"at": [0, 24, 30], "normal": [0, 0, 1], "type": "plane"}}
    ring = {"component": "vicko", "face": {"at": [0, 24, 2], "normal": [0, 0, 1],
                                           "type": "plane"}}
    assert window.add_constraint("distance", rim, ring, 5) is None
    assert dialogs["shown"][-1][0] == "Vazbu nejde přidat"
    assert "si odporují" in dialogs["shown"][-1][1] and not window.session.can_undo


def test_changed_part_moves_constrained_lid_and_window_says_so(constrained, project):
    box = json.loads((project / "krabicka.json").read_text(encoding="utf-8"))
    box["parameters"]["H"] = 40
    (project / "krabicka.json").write_text(json.dumps(box), encoding="utf-8")
    press(constrained, "Načíst díly znovu")
    assert constrained.session.assembly.component("vicko").position == [0, 0, 42]
    assert "po změně dílu přepočítaly" in constrained.summary.text()
    assert "*" in constrained.windowTitle()
