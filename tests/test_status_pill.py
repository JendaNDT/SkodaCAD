"""P7.53: stavová pilulka a přepínač pohledů dole nad 3D (návrh hlavního okna 1a)."""

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QRect  # noqa: E402

from skodacad.gui import floating  # noqa: E402
from skodacad.gui.main_window import HELP_HINT, SHORT_HINT, MainWindow  # noqa: E402
from skodacad.gui.status_pill import HEIGHT, StatusPill  # noqa: E402
from test_floating import View, scroll_of  # noqa: E402
from test_gui import FakeViewer, edit  # noqa: E402


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
    window.card_layer.relayout()
    yield window
    window.session.dirty = False
    window.close()


def test_pill_shows_state_and_shortens_long_messages():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    pill = StatusPill()
    pill.set_state("ok")
    pill.set_message("Vybráno: Upínání")
    assert pill.state.text() == "✓ Spočítáno" and pill.context.text() == "Vybráno: Upínání"
    pill.set_state("error")
    assert pill.state.text() == "✕ Chyba v modelu"
    long = "Plocha – rovinná, " * 40
    pill.set_message(long)
    assert pill.context.text().endswith("…") and pill.context.toolTip() == long
    pill.set_computing(True)
    assert pill.state.isHidden()  # během přepočtu je místo stavu ukazatel průběhu
    pill.set_message("")
    assert pill.separator.isHidden() and pill.context.isHidden()
    assert pill.height() <= HEIGHT
    app.processEvents()


def test_window_messages_go_to_pill_and_status_bar_is_hidden(plate):
    w = plate
    bar = w.statusBar()
    assert bar.isHidden() and bar.currentMessage() == HELP_HINT  # zprávy dál ve statusBar
    assert w.status_pill.message == SHORT_HINT and w.status_pill.state.text() == "✓ Spočítáno"
    bar.showMessage("Uloženo: deska.json", 8000)
    assert w.status_pill.message == "Uloženo: deska.json"
    bar.clearMessage()
    assert w.status_pill.message == SHORT_HINT  # nápověda k myši je pod F1 (R5)
    for widget in (w.progress_label, w.progress_bar, w.stop_button):
        assert w.status_pill.isAncestorOf(widget)  # přepočet „⏳ … s“ a Zastavit v pilulce
    edit(w, "t", "-5")  # neplatná tloušťka → chyba modelu
    assert w.status_pill.state.text() == "✕ Chyba v modelu"


def test_pill_and_view_switcher_sit_at_the_bottom_of_the_3d_view(plate):
    w = plate
    view = w.viewer.rect()
    pill, corner = w.pill_card.geometry(), w.view_card.geometry()
    assert pill.bottom() == view.bottom() - 14 and corner.bottom() == view.bottom() - 14
    assert corner.right() == view.right() - 14
    assert not pill.intersects(corner) and not pill.intersects(w.model_dock.geometry())
    assert abs(pill.center().x() - view.center().x()) <= 2  # pilulka uprostřed okna
    buttons = w.view_switcher.buttons
    assert [b.text() for b in buttons.values()] == ["Izo", "Zepředu", "Shora", "Celý díl"]
    views = []
    w.viewer.set_standard_view = views.append
    buttons["top"].click()
    assert views == ["top"] and w.view_switcher.active == "top"
    w.view_actions["front"].trigger()  # zkratka 1 / nabídka: zvýraznění se přepne také
    assert w.view_switcher.active == "front"
    w.view_actions["iso"].setEnabled(False)
    assert not buttons["iso"].isEnabled() and buttons["iso"].text() == "Izo"
    w.view_actions["iso"].setEnabled(True)


def test_view_switcher_moves_beside_a_tall_right_card_and_bottom_inset_is_reported():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    view = View()
    view.resize(1440, 760)
    view.show()
    layer = floating.CardLayer(view)
    right = layer.card("NDT", "ndt_dock", "right")
    right.setWidget(scroll_of(3000))  # karta až dolů
    corner = layer.card("Pohledy", "view_switcher_card", "corner")
    box = QtWidgets.QWidget()
    box.setFixedSize(260, 28)
    corner.setWidget(box)
    pill = layer.card("Stav", "status_pill_card", "bottom")
    message = QtWidgets.QWidget()
    message.setFixedSize(300, 30)
    pill.setWidget(message)
    for card in (right, corner, pill):
        card.show()
    layer.relayout()
    assert corner.geometry().right() < right.geometry().left()  # nepřekryje pravou kartu
    assert not pill.geometry().intersects(corner.geometry())
    assert view.insets[3] == 760 - min(pill.geometry().top(), corner.geometry().top()) \
        + floating.GAP
    right.hide()
    layer.relayout()
    assert corner.geometry() == QRect(1440 - 14 - 262, 760 - 14 - 30, 262, 30)
    view.close()
    app.processEvents()
