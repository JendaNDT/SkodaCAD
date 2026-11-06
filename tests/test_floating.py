"""P7.49: plovoucí karty nad 3D pohledem (rozměry z návrhu 1a, rozhraní jako QDockWidget)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QRect  # noqa: E402

from skodacad.gui import floating  # noqa: E402


class View(QtWidgets.QWidget):
    """Náhrada 3D pohledu: pamatuje si, kolik zakrývají karty."""

    insets = None

    def set_view_insets(self, left, right, top=0):
        self.insets = (left, right, top)


@pytest.fixture
def view():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widget = View()
    widget.resize(1440, 760)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()


def scroll_of(height):
    content = QtWidgets.QWidget()
    content.setMinimumHeight(height)
    area = QtWidgets.QScrollArea()
    area.setWidget(content)
    area.setWidgetResizable(True)
    return area


def test_cards_follow_design_positions_and_report_free_space(view):
    layer = floating.CardLayer(view)
    left = layer.card("Model", "model_dock", "left")
    left.setWidget(scroll_of(2000))
    right = layer.card("Úprava prvku", "editor_dock", "right")
    right.setWidget(scroll_of(200))
    ndt = layer.card("NDT", "ndt_dock", "right")
    ndt.setWidget(scroll_of(200))
    ndt.hide()
    left.show()
    right.show()
    layer.relayout()
    assert left.parentWidget() is view and right.parentWidget() is view
    assert left.geometry() == QRect(14, 14, 268, 760 - 14 - 60)
    geometry = right.geometry()
    assert (geometry.left(), geometry.top(), geometry.width()) == (1440 - 14 - 304, 14, 304)
    # Výška podle obsahu, ne přes celou výšku pohledu.
    assert geometry.height() == right.preferred_height() < 760 - 28
    assert layer.free_rect() == QRect(282, 0, 1440 - 282 - 318, 760)
    assert view.insets == (282 + floating.GAP, 318 + floating.GAP, 0)
    right.hide()
    ndt.show()
    layer.relayout()
    assert ndt.geometry().width() == 320  # NDT má podle návrhu širší kartu
    assert view.insets[1] == 14 + 320 + floating.GAP


def test_long_content_is_limited_to_view_and_resize_moves_cards(view):
    layer = floating.CardLayer(view)
    card = layer.card("NDT", "ndt_dock", "right")
    card.setWidget(scroll_of(3000))
    card.show()
    layer.relayout()
    assert card.geometry().height() == 760 - 28
    view.resize(1024, 600)
    QtWidgets.QApplication.processEvents()
    assert card.geometry() == QRect(1024 - 14 - 320, 14, 320, 600 - 28)


def test_card_offers_dock_interface_and_visibility_signal(view):
    layer = floating.CardLayer(view)
    card = layer.card("Měření", "measure_dock", "right")
    content = QtWidgets.QLabel("obsah")
    title = QtWidgets.QLabel("hlavička")
    seen = []
    card.visibilityChanged.connect(seen.append)
    card.setWidget(content)
    card.setTitleBarWidget(title)
    card.setFeatures(None)
    card.setAllowedAreas(None)
    assert card.widget() is content and card.titleBarWidget() is title
    assert card.windowTitle() == "Měření"
    card.show()
    card.hide()
    assert seen == [True, False]
    # Zaoblené rohy: levý horní roh je mimo masku, střed uvnitř.
    card.show()
    layer.relayout()
    assert not card.mask().contains(card.rect().topLeft())
    assert card.mask().contains(card.rect().center())


def test_command_palette_is_centered_between_side_cards_and_reported_as_top_inset(view):
    """P7.50: paleta příkazů nahoře uprostřed volného místa; „Celý díl“ ji obejde."""
    layer = floating.CardLayer(view)
    left = layer.card("Model", "model_dock", "left")
    left.setWidget(scroll_of(400))
    right = layer.card("Úprava prvku", "editor_dock", "right")
    right.setWidget(scroll_of(200))
    row = QtWidgets.QWidget()
    row.setFixedSize(400, 50)
    palette = layer.card("Příkazy", "command_palette", "top")
    palette.setWidget(row)
    for card in (left, right, palette):
        card.show()
    layer.relayout()
    free = layer.free_rect()
    geometry = palette.geometry()
    assert geometry.top() == 14 and geometry.width() == 402
    assert abs(geometry.center().x() - free.center().x()) <= 1
    assert view.insets[2] == geometry.bottom() + 1 + floating.GAP
    row.setFixedSize(2000, 50)  # širší než volné místo: paleta nepřesáhne mezi karty
    layer.relayout()
    assert palette.geometry().left() >= free.left() and palette.geometry().right() <= free.right()
