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


def test_choice_text_short_and_capitalized():
    from skodacad.gui.feature_editor import choice_text

    assert choice_text("válcové zahloubení pro imbus (ISO 4762)") == "Válcové zahloubení"
    assert choice_text("horní plocha dílu") == "Horní plocha"
    assert choice_text("nové těleso") == "Nové těleso"
    assert choice_text("XY – vodorovná rovina") == "XY – vodorovná rovina"
    assert choice_text("") == ""


def test_feature_card_shows_point_table_and_readable_values_and_pill(plate):
    """P7.60, rám 2a: polohy jako číslovaná tabulka, hodnoty jen pro čtení běžnou barvou,
    pilulka „Vybráno: …“ podle prvku vybraného ve stromu."""
    from PySide6.QtGui import QPalette

    from skodacad.gui.main_window import SHORT_HINT

    w = plate
    w.workspace.show_panel("editor")
    assert w.status_pill.message == SHORT_HINT  # nic nevybráno
    item = next(w.tree.topLevelItem(i) for i in range(w.tree.topLevelItemCount())
                if w.tree.topLevelItem(i).data(0, model_card.NAME_ROLE) == "Upínání")
    w.tree.setCurrentItem(item)
    QtWidgets.QApplication.processEvents()
    assert w.status_pill.message == "Vybráno: Upínání · 4 díry M6"
    form = w.feature_editor.form
    view = form.point_view("positions")
    assert view is not None and view.isVisibleTo(form)
    assert not form.layout().isRowVisible(form.widget("positions"))  # pole skryté, data dál
    text = view.text()
    section = form.point_section("positions")  # P7.69: sekce s počtem vpravo
    assert section.button.text() == "Polohy děr" and section.count_label.text() == "4"
    assert section.expanded and text.count("<tr>") == 4
    assert ">1</td>" in text and ">4</td>" in text
    assert "A/2 - e" in text and "B/2 - e" in text
    assert form.widget("positions").toPlainText().count("\n") == 3  # původní pole beze změny
    # P7.69: nevyplněné volby sbalené v sekci „Další volby“ (rám 2a „Vlastní průměr“).
    extra = form.extra_section
    assert extra.isVisibleTo(form) and not extra.expanded and extra.button.isEnabled()
    assert int(extra.count_label.text()) >= 1 and "Vlastní průměr" in extra.toolTip()
    assert not form.layout().isRowVisible(form.widget("diameter"))
    assert not form.layout().isRowVisible(form.widget("name"))
    extra.button.click()
    assert form.layout().isRowVisible(form.widget("diameter"))  # jen pro čtení
    assert form.widget("diameter").isReadOnly()
    assert not form.layout().isRowVisible(form.widget("name"))  # název je v titulku
    section.button.click()  # sbalí tabulku poloh
    assert not view.isVisibleTo(form) and section.isVisibleTo(form)
    extra.button.click()
    assert not form.layout().isRowVisible(form.widget("diameter"))
    kind = form.widget("kind")
    # P7.72: krátké texty voleb jako v rámu 2a, celý popis v bublině, data beze změny
    assert kind.currentText() == "Válcové zahloubení" and kind.currentData() == "counterbore"
    assert kind.toolTip() == "válcové zahloubení pro imbus (ISO 4762)"
    plane = form.widget("plane")
    assert plane.currentText() == "Horní plocha" and plane.currentData() == "top"
    assert form.layout().labelForField(plane).text() == "Na ploše"
    # P7.73/P7.74: Skrz celý díl nad polohami, druh a id jen šedý popisek
    row = form.layout().getWidgetPosition
    assert row(form.widget("through_all"))[0] < row(section)[0]
    title = w.feature_editor.title.text()
    assert "Díra · upinani" in title and "<b>" not in title
    palette = kind.palette()
    assert not kind.isEnabled()
    assert (palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText)
            == palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText))
    w.statusBar().showMessage("Uloženo: deska.json", 8000)
    assert w.status_pill.message == "Uloženo: deska.json"  # hlášení má přednost
    w.statusBar().clearMessage()
    assert w.status_pill.message == "Vybráno: Upínání · 4 díry M6"
    w.tree.setCurrentItem(None)
    QtWidgets.QApplication.processEvents()
    assert w.status_pill.message == SHORT_HINT
