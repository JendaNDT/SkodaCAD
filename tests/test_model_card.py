"""P7.51: levá karta Prvky | Parametry | Díl (návrh hlavního okna 1a)."""

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from skodacad.gui import model_card  # noqa: E402
from skodacad.gui.main_window import MainWindow  # noqa: E402
from skodacad.gui.window_state import load_state  # noqa: E402
from test_gui import FakeViewer, tree_texts  # noqa: E402


@pytest.fixture
def plate(examples_dir, tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    model = tmp_path / "deska.json"
    shutil.copy(examples_dir / "deska.json", model)
    window = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert window.open_model(model)
    window.resize(1440, 860)
    window.show()
    app.processEvents()
    yield window
    window.session.dirty = False
    window.close()


@pytest.mark.parametrize("count, text", [(0, "0 prvků"), (1, "1 prvek"), (2, "2 prvky"),
                                         (4, "4 prvky"), (5, "5 prvků"), (12, "12 prvků")])
def test_feature_count_uses_czech_plural(count, text):
    assert model_card.count_text(count) == text


def test_left_card_has_three_tabs_and_tree_rows_keep_their_data(plate):
    w = plate
    tabs = w.model_tabs.tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Prvky", "Parametry", "Díl"]
    assert w.model_dock.widget() is w.model_tabs
    assert w.model_tabs.current == "features" and w.tree.isVisible()
    # Text řádku se stavem zůstává (testy, filtr, čtečky); kreslí se jen jinak.
    assert tree_texts(w)[0] == "✓  Skica „Obrys desky“"
    assert w.feature_count_label.text() == "6 prvků"
    item = w.tree.topLevelItem(2)
    assert item.data(0, model_card.STATUS_ROLE) == "ok" and not item.icon(0).isNull()
    assert w.tree.isHeaderHidden() and item.text(1) == "1 → 1"
    option = QtWidgets.QStyleOptionViewItem()
    delegate = w.tree.itemDelegate()
    delegate.initStyleOption(option, w.tree.indexFromItem(item, 0))
    assert option.text == "Upínání"  # krátký název podle rámu 2a (P7.59), stav vpravo
    option = QtWidgets.QStyleOptionViewItem()
    delegate.initStyleOption(option, w.tree.indexFromItem(item, 1))
    assert option.text == "M6 ×4  ✓"  # údaj prvku místo počtu těles (ten je v bublině)
    assert "Počet těles: 1 → 1" in item.toolTip(0) and "M6" in item.toolTip(0)
    assert delegate.sizeHint(option, w.tree.indexFromItem(item, 0)).height() >= 26
    first = w.tree.topLevelItem(0)  # skica bez údaje: vpravo jen stav
    option = QtWidgets.QStyleOptionViewItem()
    delegate.initStyleOption(option, w.tree.indexFromItem(first, 1))
    assert option.text == "✓"
    assert first.data(0, model_card.NAME_ROLE) == "Obrys desky"


def test_tree_names_and_summaries_follow_the_design():
    from skodacad.features import tree_name, tree_summary

    hole = {"id": "h1", "type": "hole", "name": "Upínání", "size": "M6",
            "positions": [[0, 0]] * 4}
    assert (tree_name(hole), tree_summary(hole)) == ("Upínání", "M6 ×4")
    assert tree_summary({**hole, "positions": [[0, 0]]}) == "M6"
    assert tree_name({"id": "fillet1", "type": "fillet"}) == "Zaoblení fillet1"
    assert tree_summary({"id": "f", "type": "fillet", "radius": "r"}, {"r": 2.0}) == "R2"
    assert tree_summary({"id": "c", "type": "chamfer", "distance": 1}) == "1 mm"
    assert tree_summary({"id": "p", "type": "pattern", "count": 3}) == "×3"
    assert tree_summary({"id": "p", "type": "pattern", "kind": "linear", "count": 3,
                         "direction2": [0, 1, 0], "count2": 2}) == "3 × 2"
    assert tree_summary({"id": "e", "type": "extrude", "distance": 10}) == ""


def test_shortcuts_open_the_right_tab_and_parameters_section_follows_tab(plate):
    w = plate
    w.model_tabs.select("part")
    QTest.keyClick(w, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert w.model_tabs.current == "features" and w.tree_filter.field.hasFocus()
    section = w.sidebar_sections["parameters"]
    seen = []
    section.toggled.connect(seen.append)
    QTest.keyClick(w, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.ShiftModifier)
    assert w.model_tabs.current == "parameters" and section.expanded
    assert w.param_filter.field.hasFocus()
    section.set_expanded(False)  # „sbalení“ Parametrů = návrat na strom prvků
    assert w.model_tabs.current == "features" and seen == [True, False]
    w.model_tabs.select("part")
    assert w.name_edit.isVisible() and w.props_label.isVisible()


def test_tab_is_saved_and_reset_starts_with_features(plate):
    w = plate
    w.model_tabs.select("part")
    w.workspace.save()
    assert load_state(w.workspace.path)["left_tab"] == "part"
    w.workspace.reset()
    assert w.model_tabs.current == "features"
    assert w.sidebar_sections["info"].expanded and w.sidebar_sections["properties"].expanded
    w.model_tabs.select("parameters")
    w.workspace.save()
    w.model_tabs.select("features")
    w.workspace._restored = False
    w.workspace.state = load_state(w.workspace.path)
    w.workspace.restore()
    assert w.model_tabs.current == "parameters"


def test_tree_refresh_without_change_reports_no_row_change(plate):
    """P8.5: nová QIcon při každé obnově hlásila změnu všech řádků a sloupec
    s ResizeToContents pak přeměřil celý strom (obnova 3 → 27 ms u 122 řádků)."""
    w = plate
    changes = []
    w.tree.model().dataChanged.connect(lambda *args: changes.append(args))
    w._refresh_tree()
    assert changes == []
    first = w.tree.topLevelItem(0)
    assert first.data(0, model_card.ICON_ROLE) and not first.icon(0).isNull()
    w.workspace.set_appearance("dark")  # jiná barva ikon = skutečná změna
    QtWidgets.QApplication.processEvents()
    changes.clear()
    w._refresh_tree()
    assert first.data(0, model_card.ICON_ROLE).endswith(
        QtWidgets.QApplication.palette().color(QtWidgets.QApplication.palette().ColorRole.Link).name())
    w.workspace.set_appearance("light")


def test_tree_refresh_measures_rows_once_not_once_per_changed_row(plate, examples_dir):
    """P8.5: změna textu sloupce těles (ResizeToContents) u každého řádku přeměřila
    celý strom → řádky × řádky volání vlastní kresby (200–270 ms u 122 řádků)."""
    w = plate
    assert w.open_model(examples_dir / "priruba.json", template=True)
    calls = []

    class Counting(model_card.FeatureRowDelegate):
        def sizeHint(self, option, index):  # noqa: N802
            calls.append(index.row())
            return super().sizeHint(option, index)

    w.tree.setItemDelegate(Counting(w.tree))
    rows = w.tree.topLevelItemCount()
    assert rows >= 4
    for i in range(rows):  # jako přechod „přepočítává se“ → hotovo
        w.tree.topLevelItem(i).setText(1, "")
    QtWidgets.QApplication.processEvents()
    calls.clear()
    w._refresh_tree()
    QtWidgets.QApplication.processEvents()
    assert len(calls) <= 4 * rows, (len(calls), rows)
    header = w.tree.header()
    assert header.sectionResizeMode(1) == header.ResizeMode.ResizeToContents
