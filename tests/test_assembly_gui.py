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
    reopened = main_window.open_assembly(tmp_path / "moje_krabicka.json")
    assert reopened.session.result.complete  # cesty vedou na díly ukázky


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
