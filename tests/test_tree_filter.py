"""P7.40: filtr stromu prvků dílu – jen pohled, model ani historie se nemění."""

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem  # noqa: E402

from skodacad.gui.main_window import MainWindow  # noqa: E402
from skodacad.gui.tree_filter import SEARCH_ROLE, TreeFilter  # noqa: E402
from test_gui import FakeViewer, app  # noqa: E402, F401


@pytest.fixture
def window(app, examples_dir, tmp_path):  # noqa: F811
    model = tmp_path / "priruba.json"
    shutil.copy(examples_dir / "priruba.json", model)
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert w.open_model(model)
    w.resize(1400, 900)  # menší okno by strom modelu schovalo (kompaktní rozložení)
    w.show()
    w.activateWindow()
    assert QTest.qWaitForWindowActive(w)  # fokus jen v aktivním okně
    yield w
    w.session.dirty = False
    w.close()


def visible(w):
    return [w.tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            for i in range(w.tree.topLevelItemCount()) if not w.tree.topLevelItem(i).isHidden()]


def snapshot(w):
    session = w.session
    return (session.document.to_dict(), session.result, list(session._undo),
            list(session._redo), session.dirty)


def test_filter_hides_rows_without_diacritics_and_keeps_model(window):
    w = window
    before = snapshot(w)
    rows = [w.tree.topLevelItem(i) for i in range(w.tree.topLevelItemCount())]
    QTest.keyClicks(w.tree_filter.field, "srazeni")
    assert visible(w) == ["sraz_obvod", "sraz_otvor"]
    assert w.tree_filter.note.isVisibleTo(w) and "2 z 6 prvků" in w.tree_filter.note.text()
    w.tree_filter.field.setText("VRTANI der")  # více slov, velikost písmen nerozhoduje
    assert visible(w) == ["diry"]
    w.tree_filter.field.setText("deska")  # vyhledá i podle id prvku
    assert visible(w) == ["deska"]
    w.tree_filter.field.setText("nic takoveho")
    assert visible(w) == []
    assert "Žádný řádek" in w.tree_filter.note.text()
    QTest.keyClick(w.tree_filter.field, Qt.Key.Key_Escape)
    assert w.tree_filter.field.text() == "" and not w.tree_filter.note.isVisibleTo(w)
    assert len(visible(w)) == 6
    # řádky se jen skrývají, nikdy nemažou (přístupnost Cocoa drží odkazy na buňky)
    assert [w.tree.topLevelItem(i) for i in range(w.tree.topLevelItemCount())] == rows
    assert snapshot(w) == before


def test_enter_selects_first_match_and_selected_row_stays_visible(window):
    w = window
    before = snapshot(w)
    w.tree_filter_action.trigger()  # Ctrl+F: fokus do filtru
    assert w.tree_filter.field.hasFocus()
    QTest.keyClicks(w.tree_filter.field, "skica")
    QTest.keyClick(w.tree_filter.field, Qt.Key.Key_Return)
    assert w._selected_id == "obrys" and w.tree.hasFocus()
    assert w.feature_editor.form is not None  # editor ukazuje vybraný prvek
    w.tree_filter.field.setText("sraz")
    assert visible(w) == ["obrys", "sraz_obvod", "sraz_otvor"]  # vybraný zůstává vidět
    w.tree.setCurrentItem(w.tree_filter.visible_matches()[0])
    assert w._selected_id == "sraz_obvod"
    assert visible(w) == ["sraz_obvod", "sraz_otvor"]  # bývalý výběr už neodpovídá
    assert snapshot(w) == before


def edit_parameter(w, name, text):
    field = w._param_fields[name]
    field.setText(text)
    field.editingFinished.emit()  # přepočet obnoví řádky stromu


def test_filter_survives_rebuild_and_finds_failed_features(window):
    w = window
    w.tree_filter.field.setText("sraz")
    edit_parameter(w, "D", "170")
    assert w.session.document.parameters["D"] == 170
    assert visible(w) == ["sraz_obvod", "sraz_otvor"]
    w.tree_filter.field.setText("chyba")
    assert visible(w) == []
    edit_parameter(w, "t", "0")  # nulová tloušťka desky = chyba přepočtu
    failed = [s.id for s in w.session.result.statuses if s.status == "error"]
    assert failed and visible(w) == failed
    assert "z 6 prvků" in w.tree_filter.note.text()


def test_open_and_new_model_clear_filter(window, examples_dir):
    w = window
    w.tree_filter.field.setText("sraz")
    assert w.open_model(examples_dir / "krabicka.json")
    assert w.tree_filter.field.text() == "" and not w.tree_filter.note.isVisibleTo(w)
    assert all(not w.tree.topLevelItem(i).isHidden() for i in range(w.tree.topLevelItemCount()))
    w.tree_filter.field.setText("x")
    w.session.dirty = False
    assert w.new_model()
    assert w.tree_filter.field.text() == ""


def test_ctrl_f_opens_hidden_model_panel(window):
    w = window
    w.workspace.model_action.trigger()
    assert w.model_dock.isHidden()
    w.tree_filter_action.trigger()
    assert not w.model_dock.isHidden() and w.tree_filter.field.hasFocus()
    assert w.tree_filter_action.shortcut().toString() == "Ctrl+F"


def test_nested_rows_keep_parents_of_matches(app):  # noqa: F811
    tree = QTreeWidget()
    parent = QTreeWidgetItem(["Podsestava"])
    child = QTreeWidgetItem(["Šroub M6"])
    other = QTreeWidgetItem(["Matice"])
    child.setData(0, SEARCH_ROLE, "Šroub M6 sroub1")
    parent.addChildren([child, other])
    tree.addTopLevelItem(parent)
    tree.addTopLevelItem(QTreeWidgetItem(["Deska"]))
    flt = TreeFilter(tree, placeholder="", nouns=("dílu", "dílů", "dílů"))
    flt.field.setText("sroub1")
    assert not parent.isHidden() and not child.isHidden() and other.isHidden()
    assert tree.topLevelItem(1).isHidden()
    assert flt.visible_matches() == [child]
    assert "1 z 4 dílů" in flt.note.text()


def test_packaged_tree_filter_driver_uses_real_keys(window):
    from skodacad.gui.app import _self_test_tree_filter

    w = window
    w.tree.setCurrentItem(w.tree.topLevelItem(1))
    before = snapshot(w)
    lines = []
    assert _self_test_tree_filter(w, lines), lines
    assert lines[-1].startswith("✓ Filtr stromu prvků")
    assert w._selected_id == "deska" and len(visible(w)) == 6  # výběr vrácen, filtr prázdný
    assert snapshot(w) == before


# --- P7.41: filtr stromu komponent v okně sestavy ---------------------------------

from test_assembly_gui import dialogs, main_window, project  # noqa: E402, F401


@pytest.fixture
def assembly(main_window, project):  # noqa: F811
    window = main_window.open_assembly(project / "sestavy" / "krabicka_s_vazbami.json")
    assert window is not None
    window.resize(1400, 900)
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)
    return window


def all_rows(tree):
    found = []

    def walk(item):
        found.append(item)
        for index in range(item.childCount()):
            walk(item.child(index))

    for index in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(index))
    return found


def shown_keys(w):
    import json

    return [json.loads(item.data(0, Qt.ItemDataRole.UserRole)) for item in all_rows(w.tree)
            if not item.isHidden() and (item.parent() is None or not item.parent().isHidden())]


def assembly_snapshot(w):
    session = w.session
    return (session.assembly.to_dict(), session.result, list(session._undo),
            list(session._redo), session.dirty, dict(w._visibility), w._isolated)


def test_assembly_filter_components_and_constraints_without_changes(assembly):
    w = assembly
    before = assembly_snapshot(w)
    rows = all_rows(w.tree)
    shown_parts = len(w.visible_instances())
    w.tree_filter_action.trigger()
    assert w.tree_filter.field.hasFocus()
    QTest.keyClicks(w.tree_filter.field, "nozicka")  # i, t, h jsou zkratky okna – pole je přijme
    assert w.tree_filter.field.text() == "nozicka"
    keys = shown_keys(w)
    assert [k for k in keys if isinstance(k, list)] == [[f"nozicka_{i}"] for i in range(1, 5)]
    # vazby nožiček se najdou podle názvu komponenty; skupina „Vazby“ zůstane jako rodič
    assert [k["constraint"] for k in keys if isinstance(k, dict)] == ["v4", "v5", "v6", "v7"]
    assert None in keys
    assert "z 14 položek" in w.tree_filter.note.text()
    w.tree_filter.field.setText("vazba")
    assert [k for k in shown_keys(w) if isinstance(k, list)] == []
    assert len([k for k in shown_keys(w) if isinstance(k, dict)]) == 7
    w.tree_filter.field.setText("dily/vicko.json")  # podle souboru dílu
    assert [k for k in shown_keys(w) if isinstance(k, list)] == [["vicko"]]
    QTest.keyClick(w.tree_filter.field, Qt.Key.Key_Escape)
    assert len(shown_keys(w)) == len(rows) and all_rows(w.tree) == rows
    assert len(w.visible_instances()) == shown_parts  # filtr nikdy neskrývá 3D
    assert assembly_snapshot(w) == before


def test_assembly_filter_keeps_selection_visible_and_ctrl_a_selects_matches(assembly):
    w = assembly
    w.select_many([("krabicka",)])
    w.tree_filter.field.setText("nozicka")
    assert ["krabicka"] in shown_keys(w)  # vybraná komponenta se neskryje
    w.tree.setFocus()
    QTest.keyClick(w.tree, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._selection == tuple((f"nozicka_{i}",) for i in range(1, 5))
    assert ["krabicka"] not in shown_keys(w)  # už není vybraná, filtru neodpovídá
    before = len(w.visible_instances())
    QTest.keyClick(w.tree, Qt.Key.Key_H)  # skryje právě nalezené nožičky
    assert len(w.visible_instances()) == before - 4
    w.tree_filter.clear()
    w.tree.setFocus()
    QTest.keyClick(w.tree, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert len(w._selection) == 6  # bez filtru jako dosud všechny komponenty


def test_assembly_filter_enter_selects_and_3d_pick_reveals_row(assembly):
    w = assembly
    QTest.keyClicks(w.tree_filter.field, "vicko na okraji")
    QTest.keyClick(w.tree_filter.field, Qt.Key.Key_Return)
    assert w._constraint == "v1" and w.tree.hasFocus()
    w.tree_filter.field.setText("krabicka")
    assert ["nozicka_2"] not in shown_keys(w)
    w.select_many([("nozicka_2",)])  # jako klik ve 3D: signály stromu jsou blokované
    assert ["nozicka_2"] in shown_keys(w) and ["krabicka"] in shown_keys(w)


def test_assembly_filter_survives_rebuild_and_clears_on_open(assembly, project):  # noqa: F811
    w = assembly
    w.tree_filter.field.setText("nozicka")
    w.reload_action.trigger()  # znovu načíst díly = nové výsledky ve stejných řádcích
    assert [k for k in shown_keys(w) if isinstance(k, list)] == [[f"nozicka_{i}"] for i in
                                                               range(1, 5)]
    assert w.open_assembly(project / "sestavy" / "krabicka_s_vickem.json")
    assert w.tree_filter.field.text() == ""
    assert all(not item.isHidden() for item in all_rows(w.tree))


def test_packaged_assembly_tree_filter_driver(assembly):
    from skodacad.gui.app import _self_test_assembly_tree_filter

    w = assembly
    w.select_many([("vicko",)])
    before = assembly_snapshot(w)
    lines = []
    assert _self_test_assembly_tree_filter(w, lines), lines
    assert lines[-1].startswith("✓ Filtr stromu komponent")
    assert w._selection == (("vicko",),) and w.tree_filter.field.text() == ""
    assert assembly_snapshot(w) == before


def test_assembly_shift_range_skips_rows_hidden_by_filter(assembly):
    w = assembly
    w.select_many([("krabicka",)])
    w.tree_filter.field.setText("4")  # Nožička 4 a její vazba; krabička zůstane jako vybraná
    first = next(i for i in all_rows(w.tree) if i.data(0, SEARCH_ROLE).startswith("Krabička"))
    last = next(i for i in all_rows(w.tree) if i.data(0, SEARCH_ROLE).startswith("Nožička 4"))
    w.tree.setFocus()
    QTest.mouseClick(w.tree.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, w.tree.visualItemRect(first).center())
    QTest.mouseClick(w.tree.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.ShiftModifier, w.tree.visualItemRect(last).center())
    # skryté Víčko a Nožičky 1–3 mezi nimi se nevyberou ani neodkryjí
    assert w._selection == (("krabicka",), ("nozicka_4",))
    assert [k for k in shown_keys(w) if isinstance(k, list)] == [["krabicka"], ["nozicka_4"]]
