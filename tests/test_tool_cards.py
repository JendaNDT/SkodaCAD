"""P7.54: karty Měření, Řez, Mapa tloušťky a náhled prvku podle rámů 3a–3c návrhu 1a."""

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402

from conftest import face_at  # noqa: E402
from skodacad.gui.main_window import MainWindow  # noqa: E402
from skodacad.gui.model_card import PREVIEW_ROLE  # noqa: E402
from skodacad.gui.tool_cards import (  # noqa: E402
    ROW_HEIGHT,
    STATE_ROLE,
    focus_text,
    split_value,
)
from skodacad.inspection import number  # noqa: E402
from test_gui import FakeViewer, action  # noqa: E402

FEATURE_ID = Qt.ItemDataRole.UserRole  # id prvku v řádku stromu


@pytest.fixture
def plate(examples_dir, tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    model = tmp_path / "deska.json"
    shutil.copy(examples_dir / "deska.json", model)
    window = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert window.open_model(model)
    window.resize(1440, 900)
    window.show()
    app.processEvents()
    yield window
    if window.feature_preview is not None:
        window.cancel_feature_preview()
    window.session.dirty = False
    window.close()


def threads(w):
    """Dvě díry se závitem M8 v ose X ±20 mm (deska.json): rozteč 40 mm."""
    part = w.session.result.part
    holes = [face_at(part, sx * 20 + 3.4, 0, 10) for sx in (-1, 1)]
    assert all(h.geom_type.name == "CYLINDER" for h in holes)
    return holes


def test_value_text_is_split_into_label_and_value():
    assert split_value("Rozteč os: 40.00 mm") == ("Rozteč os", "40.00 mm")
    assert split_value("Tloušťka desky: 15.00 mm") == ("Tloušťka desky", "15.00 mm")
    assert split_value("⏳ Tloušťka desky") == ("⏳ Tloušťka desky", "")
    assert focus_text("Rozteč os: 40.00 mm") == "Rozteč os 40.00 mm"


def test_measure_card_rows_buttons_sections_and_pill(plate):
    w = plate
    w.workspace.show_panel("measure")
    assert not w.measure_list.isVisibleTo(w.measure_dock)  # bez výběru žádné řádky
    assert w.measure_sections["saved"].expanded and not w.measure_sections["drawing"].expanded
    assert w.measure_sections["saved"].count_label.text()  # zkratka Ctrl+Shift+M vpravo
    w.viewer.click(threads(w))
    rows = [w.measure_list.item(i).text() for i in range(w.measure_list.count())]
    assert rows[0] == "Rozteč os: 40.00 mm" and w.measure_list.currentRow() == 0
    # rám 3b: řádky výsledků bez posouvání, výška = počet řádků
    assert w.measure_list.height() == len(rows) * ROW_HEIGHT
    assert w.measure_list.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert w.measure_hint.text().startswith("Vybráno: 2")
    # tlačítka v jedné řadě: Uložit (primární), Přejmenovat…, Smazat (vedlejší)
    buttons = w.measure_buttons
    assert [b.text() for b in buttons.values()] == ["Uložit", "Přejmenovat…", "Smazat"]
    assert buttons["save"].property("role") == "primary" and buttons["save"].isEnabled()
    assert not buttons["rename"].isEnabled() and not buttons["delete"].isEnabled()
    assert buttons["save"].toolTip() == "Uložit měření do modelu: Rozteč os: 40.00 mm"
    # pilulka: hlavní hodnota vlevo (zeleně), zpráva ji neopakuje
    assert w.status_pill.focus == ("measure", "Rozteč os 40.00 mm")
    assert w.status_pill.state.text() == "Rozteč os 40.00 mm"
    assert "Zelená čára" in w.status_pill.message and "40.00" not in w.status_pill.message
    w.measure_list.setCurrentRow(1)  # nejkratší vzdálenost
    assert w.status_pill.focus[1].startswith("Nejkratší vzdálenost")
    w.workspace.show_panel("editor")  # mimo panel Měření zase stav přepočtu
    assert w.status_pill.focus is None and w.status_pill.state.text() == "✓ Spočítáno"
    w.workspace.show_panel("measure")
    assert w.status_pill.focus[0] == "measure"

    assert w.saved_empty.isVisibleTo(w.measure_dock)
    w.measure_list.setCurrentRow(0)
    buttons["save"].click()  # skutečné tlačítko spustí akci
    saved = w.saved_list
    assert saved.count() == 1 and saved.item(0).text() == "Rozteč os: 40.00 mm"
    assert saved.item(0).data(STATE_ROLE) == "ok" and not w.saved_empty.isVisibleTo(
        w.measure_dock)
    assert saved.height() == ROW_HEIGHT and buttons["delete"].isEnabled()
    assert w.status_pill.focus == ("measure", "Rozteč os 40.00 mm")  # uložené je vybrané
    buttons["delete"].click()
    assert saved.count() == 0 and not saved.isVisibleTo(w.measure_dock)
    assert w.status_pill.focus is None


def test_saved_filter_shortcut_opens_collapsed_section(plate):
    w = plate
    w.measure_sections["saved"].set_expanded(False)
    action(w, "Filtrovat uložená měření").trigger()
    assert w.workspace.active == "measure" and w.measure_sections["saved"].expanded
    assert w.saved_filter.field.hasFocus() or not w.isActiveWindow()


def test_drawing_section_is_collapsed_and_keeps_its_controls(plate):
    w = plate
    section = w.measure_sections["drawing"]
    w.workspace.show_panel("measure")
    assert not w.drawing_paper.isVisibleTo(w.measure_dock)
    section.set_expanded(True)
    assert w.drawing_paper.isVisibleTo(w.measure_dock)
    assert w.dimension_upper.sizePolicy().horizontalPolicy() == \
        QtWidgets.QSizePolicy.Policy.Ignored  # pole nerozšíří kartu podle rozsahu čísel


def test_section_card_toggle_area_and_note(plate):
    w = plate
    w.workspace.show_panel("section")
    assert not w.section_toggle.isChecked() and not w.section_area_row.isVisibleTo(
        w.section_dock)
    assert [b.text() for b in w.section_buttons.values()] == ["Otočit stranu",
                                                              "Export DXF/SVG…"]
    assert not w.section_buttons["flip"].isEnabled()
    w.section_toggle.click()
    section = w.session.section
    assert section is not None and w.section_action.isChecked()
    assert w.section_buttons["flip"].isEnabled() and w.section_buttons["export"].isEnabled()
    assert w.section_area.text() == f"{number(section.area)} mm²"
    assert w.section_range_label.text() == "-40.00 až 40.00 mm"  # deska B = 80
    assert w.section_position_label.text() == "Poloha Y"
    assert w.section_info.property("cardNote") is True and "jen pohled" in \
        w.section_info.text()
    assert w.status_pill.focus == ("section", "Řez · Y = 0 mm")
    w.section_buttons["flip"].click()
    assert w.session.section_settings.flipped
    w.workspace.show_panel("measure")  # řez je vidět i s jiným panelem
    assert w.status_pill.focus[0] == "section"
    w.section_toggle.click()
    assert w.session.section is None and w.status_pill.focus is None


def test_map_card_toggle_button(plate):
    w = plate
    w.workspace.show_panel("map")
    toggle = w.map_buttons["toggle"]
    assert toggle.text() == "Zapnout mapu" and toggle.property("role") == "primary"
    assert not w.map_buttons["export"].isEnabled()
    w.map_fields["step"].setText("10")  # hrubý krok, ať je mapa rychlá
    w.map_fields["step"].editingFinished.emit()
    toggle.click()
    assert w.session.map_visible and w.thickness_map_action.isChecked()
    assert toggle.text() == "Vypnout mapu" and toggle.property("role") == "secondary"
    assert w.map_buttons["export"].isEnabled() and "Nejčastější" in w.map_summary.text()
    toggle.click()
    assert not w.session.map_visible and toggle.text() == "Zapnout mapu"


def preview_rows(w):
    return [w.tree.topLevelItem(i) for i in range(w.tree.topLevelItemCount())]


def test_new_feature_preview_row_pill_and_palette(plate):
    w = plate
    before = [item.text(0) for item in preview_rows(w)]
    edge = next(e for e in w.session.result.part.edges() if e.center().Z > 14.9)
    w.start_feature_preview("chamfer", shapes=[edge.wrapped])
    rows = preview_rows(w)
    assert [item.text(0) for item in rows[:-1]] == before
    extra = rows[-1]  # rám 3a: řádek náhledu na konci stromu, kam se prvek vloží
    assert extra.data(0, PREVIEW_ROLE) and extra.data(0, FEATURE_ID) is None  # bez id prvku
    assert extra.text(0) == w.feature_preview.preview.session.feature(
        w.feature_preview.preview.feature_id)["name"]
    assert not extra.flags() & Qt.ItemFlag.ItemIsSelectable
    kind, text = w.status_pill.focus
    assert kind == "preview" and text == f"● Náhled · {extra.text(0)}"
    assert w.status_pill.message.startswith("Potvrzení přidá jeden krok Zpět")
    assert not w.ribbon.isEnabled()  # paleta během náhledu neaktivní
    w._refresh_tree()  # obnova stromu řádek náhledu zachová
    assert preview_rows(w)[-1].data(0, PREVIEW_ROLE)
    w.cancel_feature_preview()
    assert [item.text(0) for item in preview_rows(w)] == before
    assert not any(item.data(0, PREVIEW_ROLE) for item in preview_rows(w))
    assert w.ribbon.isEnabled() and w.status_pill.focus is None


def test_edit_preview_marks_existing_row_and_confirm_clears_it(plate):
    w = plate
    hole = w.session.document.features[2]
    w._selected_id = hole["id"]
    w._reload_all()
    count = w.tree.topLevelItemCount()
    w.start_feature_edit()
    marked = [item.data(0, FEATURE_ID) for item in preview_rows(w) if item.data(0, PREVIEW_ROLE)]
    assert marked == [hole["id"]] and w.tree.topLevelItemCount() == count
    assert w.status_pill.focus == ("preview", "● Náhled · Upínání")
    assert "jako jeden krok Zpět" in w.status_pill.message
    w.feature_preview.accept_button.click()
    assert w.feature_preview is None
    assert not any(item.data(0, PREVIEW_ROLE) for item in preview_rows(w))
    assert w.status_pill.focus is None and w.ribbon.isEnabled()
