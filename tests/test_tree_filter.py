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
