"""P7.52: pravá karta (inspektor) podle návrhu 1a – hlavička, patička, sekce, bez posouvání."""

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402

from skodacad.gui.floating import ContentScroll  # noqa: E402
from skodacad.gui.main_window import MainWindow  # noqa: E402
from skodacad.gui.workspace import Section  # noqa: E402
from test_gui import FakeViewer  # noqa: E402


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


def test_content_scroll_reports_whole_content_not_a_capped_height():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    content = QtWidgets.QWidget()
    content.setMinimumHeight(1200)
    plain, full = QtWidgets.QScrollArea(), ContentScroll()
    tall = QtWidgets.QWidget()
    tall.setMinimumHeight(1200)
    plain.setWidget(tall)
    plain.setWidgetResizable(True)
    full.setWidget(content)
    app.processEvents()
    assert full.sizeHint().height() >= 1200  # běžná QScrollArea ohlásí jen ~24 řádků
    assert plain.sizeHint().height() < 1200
    full.resize(full.sizeHint())
    full.show()
    app.processEvents()
    assert not full.overflowing()  # v ohlášené velikosti se obsah vejde bez posuvníku
    full.resize(full.width(), 600)
    app.processEvents()
    assert full.overflowing()  # menší pohled: posuvník jako pojistka
    full.close()


def test_card_heading_follows_selection_and_preview(plate):
    w = plate
    heading = w.workspace.headings["editor"]
    menu = w.workspace.menu_buttons["editor"]
    assert heading.text() == "Úprava prvku" and menu.text() == "Úprava prvku"
    hole = w.session.document.features[2]
    w._selected_id = hole["id"]
    w._reload_all()
    assert heading.text() == hole["name"] == "Upínání"
    w.start_feature_edit()
    panel = w.feature_preview
    assert panel is not None
    assert menu.text() == "Úprava prvku · náhled" and heading.text() == "Upínání"
    w.cancel_feature_preview()
    assert menu.text() == "Úprava prvku" and heading.text() == "Upínání"
    w._selected_id = None
    w._reload_all()
    assert heading.text() == "Úprava prvku"
    assert w.workspace.headings["measure"].text() == "Měření"


def test_preview_footer_and_card_fit_without_scrolling(plate):
    w = plate
    w._selected_id = w.session.document.features[2]["id"]
    w._reload_all()
    w.start_feature_edit()
    panel = w.feature_preview
    for _ in range(4):
        QtWidgets.QApplication.processEvents()
        w.card_layer.relayout()
    row = panel.accept_button.parentWidget().layout()
    footer = [panel.esc_hint, panel.cancel_button, panel.accept_button]
    # Rám 3a: Náhled se obnovuje sám, tlačítko Náhled je jen pro nový pokus po chybě (P7.61).
    assert not panel.refresh_button.isVisibleTo(panel)
    positions = [panel.layout().indexOf(x) for x in footer]
    assert positions == [-1] * 3  # patička je jeden řádek, ne samostatné prvky panelu
    assert row is panel.layout()
    xs = [x.mapTo(panel, x.rect().topLeft()).x() for x in footer]
    assert xs == sorted(xs)  # Esc zahodí · Zrušit · Potvrdit zleva doprava
    assert panel.accept_button.property("role") == "primary"
    assert panel.cancel_button.property("role") == "secondary"
    assert panel.esc_hint.text() == "Esc zahodí"
    assert panel.message.property("cardInfo") is True
    assert not panel.editor.help.isVisible() and panel.editor.title.toolTip()
    card = w.editor_dock
    # Výška karty = obsah, nejvýš celý pohled. Zda se formulář vejde bez posuvníku, záleží
    # na skutečném písmu – ověřuje nativní self-test „Pravá karta“ (offscreen má širší).
    available = w.viewer.height() - 28
    assert card.geometry().height() == min(card.preferred_height(), available)
    if card.preferred_height() <= available:  # karta se vejde → žádný posuvník
        assert not panel.scroll.overflowing()
    # Odhad výšky smí být o pár px opatrnější (Windows offscreen: 792 > 779, a přesto
    # bez posuvníku), proto se opačný směr nevynucuje.
    assert panel.editor.form._layout.labelAlignment() & Qt.AlignmentFlag.AlignRight
    w.cancel_feature_preview()


def test_section_has_count_and_keeps_toggle_interface():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    content = QtWidgets.QLabel("obsah")
    section = Section("Polohy děr", content, True)
    seen = []
    section.toggled.connect(seen.append)
    section.set_count(4)
    assert section.count_label.text() == "4" and not section.count_label.isHidden()
    section.set_count("")
    assert section.count_label.isHidden()
    section.button.click()
    app.processEvents()
    assert seen == [False] and not section.expanded and content.isHidden()
