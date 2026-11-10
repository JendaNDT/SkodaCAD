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
    decimal_comma,
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
    assert focus_text("Rozteč os: 40.00 mm") == "Rozteč os 40,00 mm"
    assert decimal_comma("Plocha: 1 493.91 mm², krok 2.5. Konec.") == \
        "Plocha: 1 493,91 mm², krok 2,5. Konec."  # tečka za větou zůstane


def test_measure_card_rows_buttons_sections_and_pill(plate):
    w = plate
    w.workspace.show_panel("measure")
    assert not w.measure_list.isVisibleTo(w.measure_dock)  # bez výběru žádné řádky
    assert w.measure_sections["saved"].expanded and not w.measure_sections["drawing"].expanded
    assert w.measure_sections["saved"].count_label.text()  # zkratka Ctrl+Shift+M vpravo
    w.viewer.click(threads(w))
    rows = [w.measure_list.item(i).text() for i in range(w.measure_list.count())]
    assert rows[0] == "Rozteč os: 40.00 mm" and w.measure_list.currentRow() == 0
    # rám 3b (P7.62): poslední řádek „Osy · rovnoběžné“ jen pro informaci – nejde vybrat
    relation = w.measure_list.item(len(rows) - 1)
    assert rows[-1] == "Osy: rovnoběžné" and relation.flags() == Qt.ItemFlag.NoItemFlags
    # rám 3b: řádky výsledků bez posouvání, výška = počet řádků
    assert w.measure_list.height() == len(rows) * ROW_HEIGHT
    assert w.measure_list.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert w.measure_hint.text() == "Vybráno: 2 díry · Závity M8 ×2"  # rám 3b (P7.62)
    # tlačítka v jedné řadě: Uložit (primární), Přejmenovat…, Smazat (vedlejší)
    buttons = w.measure_buttons
    assert [b.text() for b in buttons.values()] == ["Uložit", "Přejmenovat…", "Smazat"]
    assert buttons["save"].property("role") == "primary" and buttons["save"].isEnabled()
    assert not buttons["rename"].isEnabled() and not buttons["delete"].isEnabled()
    assert buttons["save"].toolTip() == "Uložit měření do modelu: Rozteč os: 40.00 mm"
    # pilulka: hlavní hodnota vlevo (zeleně), zpráva ji neopakuje
    assert w.status_pill.focus == ("measure", "Rozteč os 40,00 mm")  # desetinná čárka
    assert w.status_pill.state.text() == "Rozteč os 40,00 mm"
    assert "Zelená čára" in w.status_pill.message and "40," not in w.status_pill.message
    assert w.viewer.measurement[0][2] == "40,00 mm"  # popisek čáry ve 3D
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
    assert w.status_pill.focus == ("measure", "Rozteč os 40,00 mm")  # uložené je vybrané
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
    assert w.section_area.text() == f"{number(section.area)} mm²".replace(".", ",")
    assert w.section_range_label.text() == "-40,00 až 40,00 mm"  # deska B = 80
    assert w.section_position_label.text() == "Poloha"  # rám 3c (P7.70)
    assert w.section_field.toolTip() == "Poloha Y [mm]"
    assert w.section_combo.currentText() == "Kolmo na Y"
    assert w.section_info.text() == ("Řez je jen pohled. Model se nemění a do souboru "
                                     "se neukládá.")
    assert "cihlově" in w.section_info.toolTip()
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
    assert w.viewer.highlight_preview and w.viewer.highlighted  # hrany náhledu modře (P7.58)
    w._refresh_tree()  # obnova stromu řádek náhledu zachová
    assert preview_rows(w)[-1].data(0, PREVIEW_ROLE)
    w.cancel_feature_preview()
    assert [item.text(0) for item in preview_rows(w)] == before
    assert not any(item.data(0, PREVIEW_ROLE) for item in preview_rows(w))
    assert w.ribbon.isEnabled() and w.status_pill.focus is None
    assert not w.viewer.highlight_preview  # vybraný prvek zase růžově


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


def test_preview_card_short_edges_auto_refresh_and_section_pill(plate):
    """P7.61, rámy 3a a 3c: hrany jako krátká hodnota, Náhled jen po chybě, věta o řezu."""
    from skodacad.gui.main_window import SECTION_HINT, SHORT_HINT

    w = plate
    top = max(w.session.result.part.faces(), key=lambda f: (round(f.center().Z, 6), f.area))
    w.start_feature_preview("chamfer", shapes=[e.wrapped for e in top.outer_wire().edges()])
    panel = w.feature_preview
    edges = panel.editor.form.widget("edges")
    summary = edges.findChild(QtWidgets.QLabel, "edges_summary")
    hint = edges.findChild(QtWidgets.QLabel, "edges_hint")
    assert summary.text()[:1].isupper() and "Vybráno ve 3D" not in summary.text()
    # P7.81, rám 3a: hrany tvoří celý obrys horní plochy → krátký popis místo výčtu významem
    assert summary.text() == "Obvod horní plochy"
    # P7.82: nový prvek se v náhledu jmenuje sám, pole Název tu není (hodnota zůstává)
    name = panel.editor.form.widget("name")
    assert not name.isVisibleTo(panel)
    assert panel.preview.session.feature(panel.preview.feature_id)["name"].startswith("Sražení")
    assert "Přidat vybrané hrany" in summary.toolTip()
    assert not hint.isVisibleTo(panel)  # během náhledu se ve 3D hrany nevybírají
    assert panel.accept_button.isEnabled() and not panel.refresh_button.isVisibleTo(panel)
    assert panel.message.text().startswith("Náhled je připravený: objem")
    assert "svítí ve 3D modře" in panel.message.text()
    distance = panel.editor.form.widget("distance")
    distance.setText("1+")  # chybná hodnota → původní díl a tlačítko pro nový pokus
    distance.editingFinished.emit()
    assert panel.refresh_button.isVisibleTo(panel) and not panel.accept_button.isEnabled()
    distance.setText("1")
    panel.refresh_button.click()
    assert panel.accept_button.isEnabled() and not panel.refresh_button.isVisibleTo(panel)
    panel.accept_button.click()
    assert w.feature_preview is None
    QtWidgets.QApplication.processEvents()  # karta prvku se načte po potvrzení
    # Prohlížecí karta hotového sražení: krátký popis i věta, jak výběr změnit.
    edges = w.feature_editor.form.widget("edges")
    assert edges.findChild(QtWidgets.QLabel, "edges_hint").isVisibleTo(w.editor_dock)
    assert edges.findChild(QtWidgets.QLabel, "edges_summary").text() == "Obvod horní plochy"

    w._selected_id = None
    w._reload_all()
    w.statusBar().clearMessage()
    assert w.status_pill.message == SHORT_HINT
    w.workspace.show_panel("section")
    w.section_toggle.click()  # rám 3c: bez hlášení pilulka řekne, co s řezem jde
    w.statusBar().clearMessage()
    assert w.status_pill.focus[0] == "section" and w.status_pill.message == SECTION_HINT
    w.section_toggle.click()
    assert w.status_pill.focus is None and w.status_pill.message == SHORT_HINT


def test_palette_fits_narrow_window_with_icons_and_more_menu(plate):
    """P7.64: paleta bez vodorovného posuvníku – plné popisky, jen ikony, nabídka „»“."""
    from skodacad.gui.ribbon import RibbonButton

    w = plate
    ribbon = w.ribbon
    index = ribbon.stack.currentIndex()
    scroll, more = ribbon._pages[index], ribbon._more[index]
    buttons = [b for _s, members in ribbon._groups[index] for b in members]
    full = Qt.ToolButtonStyle.ToolButtonTextUnderIcon

    ribbon.fit_width(5000)  # dost místa: plné popisky, nic skrytého
    assert all(b.toolButtonStyle() == full and not b.isHidden() for b in buttons)
    assert more.isHidden()
    wide = ribbon.preferred_width()

    ribbon.fit_width(wide - 1)  # o kousek méně: jen ikony, všechny příkazy dál vidět
    assert all(b.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly for b in buttons)
    assert not any(b.isHidden() for b in buttons) and more.isHidden()
    assert ribbon.preferred_width() < wide
    assert all(b.toolTip() and b.accessibleName() for b in buttons)  # název zůstává

    ribbon.fit_width(160)  # velmi úzko: zbytek v nabídce „»“, žádný posuvník
    hidden = [b for b in buttons if b.isHidden()]
    assert hidden and not more.isHidden() and not buttons[0].isHidden()
    assert ribbon.preferred_width() <= 160 or len(hidden) == len(buttons) - 1
    entries = more.menu().actions()  # (bez zpracování událostí – karta by paletu přepočítala)
    assert len(entries) == len(hidden)
    for button, entry in zip(hidden, entries, strict=True):  # stejné akce, stejné podnabídky
        source = button.menu() or button.defaultAction().menu()
        assert entry is button.defaultAction() or (
            entry.menu().actions() == source.actions() and entry.text() == button.text())
    more_features = next(b for b in buttons if b.text() == "Další prvky")
    assert more_features.defaultAction().menu() is w.add_feature_button.menu()  # otevře nabídku

    ribbon.fit_width(5000)  # zpět: vše vidět s popisky
    assert all(not b.isHidden() and b.toolButtonStyle() == full for b in buttons)
    assert more.isHidden() and not more.menu().actions()
    assert isinstance(buttons[0], RibbonButton)

    w.resize(960, 600)  # skutečné rozmístění karet: paleta se vejde do volného místa
    QtWidgets.QApplication.processEvents()
    w.card_layer.relayout()
    free = w.card_layer.free_rect()
    assert w.palette_card.geometry().width() <= free.width()
    content = w.palette_card.widget()
    assert content.preferred_width() + 2 <= w.palette_card.geometry().width()
    row = ribbon._rows[index]  # žádný vodorovný posuvník: řada se vejde do palety
    assert row.sizeHint().width() <= scroll.viewport().width() + 1


def test_main_bar_search_gives_way_to_activity_tabs(plate):
    """P7.65: v úzkém okně se zúží hledání (bez zkratky, pak jen lupa), záložky zůstanou."""
    bar = plate.main_bar
    search = bar.search
    modes = {}
    for mode in ("full", "short", "icon"):
        bar.fit(bar.needed_width(mode))  # (lištu rozmisťuje panel okna, proto fit přímo)
        modes[mode] = (search.mode, search.width(), search.text_label.isVisibleTo(search),
                       search.key_label.isVisibleTo(search))
    assert modes["full"][0] == "full" and modes["full"][2] and modes["full"][3]
    assert modes["short"][0] == "short" and modes["short"][2] and not modes["short"][3]
    assert modes["icon"][0] == "icon" and not modes["icon"][2] and not modes["icon"][3]
    assert modes["full"][1] > modes["short"][1] > modes["icon"][1]
    assert search.toolTip().startswith("Najít příkaz") and search.accessibleName()
    bar.fit(bar.needed_width("icon") - 50)  # užší už ne: aspoň lupa
    assert search.mode == "icon" and search.isVisibleTo(bar)
    plate.resize(1440, 900)  # skutečné okno: dost místa → plné pole, záložky celé
    QtWidgets.QApplication.processEvents()
    assert bar.tabs.width() >= bar.tabs.sizeHint().width() - 1
    assert search.action is plate.command_search_action  # klik spouští stejné hledání


def test_pill_shortens_message_to_its_room(plate):
    """P7.66: dlouhá zpráva se v úzké pilulce zkrátí „…“, celá je v bublině."""
    pill = plate.status_pill
    text = "Plocha – rovinná, obsah 20 000.00 mm², normála (0.00, 0.00, 1.00) · " * 3
    pill.set_message(text)
    pill.fit_width(5000)
    wide = pill.context.text()
    pill.fit_width(260)
    short = pill.context.text()
    assert short.endswith("…") and len(short) < len(wide) and pill.context.toolTip() == text
    assert pill.sizeHint().width() <= 260 + 4
    assert pill.state.text()  # stav vlevo zůstává celý
    plate.resize(960, 600)  # skutečné rozmístění: pilulka se vejde mezi karty
    QtWidgets.QApplication.processEvents()
    plate.card_layer.relayout()
    card = plate.pill_card
    assert pill.sizeHint().width() + 2 <= card.geometry().width() + 1
