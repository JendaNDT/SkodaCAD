"""Plovoucí karty nad 3D pohledem (P7.49, návrh hlavního okna 1a).

Karta nahrazuje dřívější ``QDockWidget`` hlavního okna. Je to obyčejný widget, dítě
3D prohlížeče, položený nad nativní plochou OCCT. Podle rozhodnutí R1 je neprůhledná,
protože pod nativní plochu nejde kreslit poloprůhledně (zkouška P7.48). Zaoblené rohy
dělá maska, okraj linka ``--sep2``.

Karta umí tu část rozhraní ``QDockWidget``, kterou okno a ``Workspace`` používají
(``setWidget``/``widget``, ``setTitleBarWidget``, ``visibilityChanged``,
``setFeatures``/``setAllowedAreas`` jako prázdné volby). Nic z toho nemění model.
"""

from PySide6.QtCore import QEvent, QObject, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPalette, QPen, QRegion
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from skodacad.gui import ui_theme

MARGIN = 14  # odstup karet od okraje 3D pohledu
RADIUS = 12
LEFT_WIDTH = 268
RIGHT_WIDTH = 304
WIDE_RIGHT = {"ndt_dock": 320, "audit_dock": 320, "design_dock": 320}
LEFT_BOTTOM = 60  # pod levou kartou zůstává místo pro stavovou pilulku (P7.53)
MIN_HEIGHT = 120
BOTTOM_PAD = 10  # spodní okraj obsahu karty
GAP = 8  # mezera mezi kartou a místem, kam „Celý díl“ přizpůsobí díl


class ContentScroll(QScrollArea):
    """Posuvná oblast, která ohlásí celou výšku obsahu (P7.52: karta neposouvá).

    Běžná QScrollArea ohlásí nejvýš asi 24 řádků textu, takže karta zůstala malá
    a obsah se posouval. Tahle ohlásí obsah celý; posuvník se ukáže jen tehdy,
    když se karta nevejde ani do celé výšky pohledu (nouzová pojistka)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def sizeHint(self):  # noqa: N802
        content = self.widget()
        if content is None:
            return super().sizeHint()
        hint = content.sizeHint()
        height = _wanted(content)
        width = self.viewport().width()
        if content.hasHeightForWidth() and width > 0:
            # Zalamované řádky (formulář, popisky) jsou v úzké kartě vyšší.
            height = max(height, content.heightForWidth(width))
        return QSize(hint.width(), height + 2 * self.frameWidth())

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self.updateGeometry()  # jiná šířka = jiná výška zalomeného obsahu

    def overflowing(self) -> bool:
        """True, když se obsah nevejde a ukazuje se posuvník."""
        return self.verticalScrollBar().maximum() > 0


def _wanted(widget: QWidget) -> int:
    """Výška, kterou obsah chce: doporučená, nebo aspoň jeho nejmenší."""
    return max(widget.sizeHint().height(), widget.minimumSizeHint().height(),
               widget.minimumHeight())


class FloatingCard(QFrame):
    """Neprůhledná karta se zaoblenými rohy; obsah je jeden widget pod hlavičkou."""

    visibilityChanged = Signal(bool)  # noqa: N815 -- stejný název jako u QDockWidget

    def __init__(self, title: str, parent: QWidget, side: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        # "left", "right", "top" (paleta příkazů), "bottom" (stavová pilulka uprostřed)
        # nebo "corner" (přepínač pohledů vpravo dole)
        self.side = side
        self.bottom_pad = BOTTOM_PAD if side in ("left", "right") else 1
        self.radius = {"bottom": 16, "corner": 9}.get(side, RADIUS)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(1, 1, 1, self.bottom_pad)
        self._layout.setSpacing(0)
        self._title: QWidget | None = None
        self._widget: QWidget | None = None

    # --- rozhraní jako QDockWidget ---------------------------------------------

    def setWidget(self, widget: QWidget) -> None:  # noqa: N802
        if self._widget is not None:
            self._layout.removeWidget(self._widget)
            self._widget.removeEventFilter(self)
        self._widget = widget
        widget.setParent(self)
        self._layout.addWidget(widget, 1)
        widget.installEventFilter(self)
        content = widget.widget() if isinstance(widget, QScrollArea) else None
        if content is not None:
            content.installEventFilter(self)
        widget.show()
        self._changed()

    def widget(self) -> QWidget | None:
        return self._widget

    def setTitleBarWidget(self, widget: QWidget) -> None:  # noqa: N802
        if self._title is not None:
            self._layout.removeWidget(self._title)
        self._title = widget
        widget.setParent(self)
        self._layout.insertWidget(0, widget)
        widget.show()

    def titleBarWidget(self) -> QWidget | None:  # noqa: N802
        return self._title

    def setFeatures(self, _features) -> None:  # noqa: N802 -- karty se nepřesouvají
        pass

    def setAllowedAreas(self, _areas) -> None:  # noqa: N802
        pass

    # --- vzhled a rozměry --------------------------------------------------------

    def preferred_height(self) -> int:
        """Výška podle obsahu (bez posuvníku), ze které rozmístění vybere menší z možných."""
        height = 1 + self.bottom_pad + (self._title.sizeHint().height() if self._title else 0)
        widget = self._widget
        width = self.width() - 2  # okraje rozvržení karty 1 + 1 px
        if isinstance(widget, QScrollArea) and widget.widget() is not None:
            height += _wanted(widget.widget()) + 2 * widget.frameWidth()
        elif widget is not None:
            wanted = _wanted(widget)
            if widget.hasHeightForWidth() and width > 0:
                # zalomené popisky jsou v úzké kartě vyšší než podle sizeHint
                wanted = max(wanted, widget.heightForWidth(width))
            height += wanted
        return height

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.LayoutRequest:
            self._changed()
        return False

    def event(self, event: QEvent) -> bool:
        # Změna obsahu kdekoli uvnitř (nový formulář, náhled prvku) dojde jako žádost
        # o nové rozvržení až sem; výška karty se pak přepočítá.
        if event.type() == QEvent.Type.LayoutRequest:
            self._changed()
        return super().event(event)

    def _changed(self) -> None:
        layer = getattr(self.parentWidget(), "_card_layer", None)
        if layer is not None:
            layer.schedule()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.radius, self.radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        window = self.palette().color(QPalette.ColorRole.Window)
        line = ui_theme.opaque(ui_theme.tokens()["sep2"], window)
        painter.setPen(QPen(line, 1))
        painter.setBrush(window)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5),
                                self.radius - .5, self.radius - .5)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.raise_()  # vždy nad nativní plochou OCCT
        self._changed()
        self.visibilityChanged.emit(True)

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._changed()
        self.visibilityChanged.emit(False)


class CardLayer(QObject):
    """Rozmístí karty nad 3D pohledem: levou nahoru vlevo, pravou nahoru vpravo."""

    def __init__(self, view: QWidget) -> None:
        super().__init__(view)
        self.view = view
        view._card_layer = self
        self.cards: list[FloatingCard] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.relayout)
        view.installEventFilter(self)

    def card(self, title: str, name: str, side: str) -> FloatingCard:
        card = FloatingCard(title, self.view, side)
        card.setObjectName(name)
        self.cards.append(card)
        return card

    def schedule(self) -> None:
        self._timer.start(0)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.view and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.relayout()
        return False

    def width_of(self, card: FloatingCard) -> int:
        if card.side == "left":
            return LEFT_WIDTH
        return WIDE_RIGHT.get(card.objectName(), RIGHT_WIDTH)

    def _side_card(self, side: str) -> FloatingCard | None:
        return next((c for c in self.cards if c.side == side and not c.isHidden()), None)

    def geometry_of(self, card: FloatingCard) -> QRect:
        """Místo karty v souřadnicích 3D pohledu (rozměry podle návrhu 1a)."""
        area = self.view.rect()
        if card.side in ("bottom", "corner"):
            content = card.widget()
            hint = content.sizeHint() if content is not None else QSize(100, 30)
            height = max(hint.height(), content.minimumHeight() if content else 0) + 2
            width = max(hint.width(), content.minimumWidth() if content else 0) + 2
            top = area.height() - MARGIN - height
            right = self._side_card("right")
            low = right is not None and right.geometry().bottom() >= top - GAP
            if card.side == "corner":
                # Vpravo dole; sahá-li pravá karta až dolů, přepínač se posune vedle ní.
                limit = right.geometry().left() - GAP if low else area.width() - MARGIN
                return QRect(limit - width, top, width, height)
            corner = self._side_card("corner")
            left_edge = MARGIN
            left = self._side_card("left")
            if left is not None and left.geometry().bottom() >= top - GAP:
                left_edge = left.geometry().right() + 1 + GAP
            right_edge = area.width() - MARGIN
            if corner is not None:
                right_edge = min(right_edge, corner.geometry().left() - GAP)
            if low:
                right_edge = min(right_edge, right.geometry().left() - GAP)
            width = min(width, max(right_edge - left_edge, 0))
            x = min(max((area.width() - width) // 2, left_edge), right_edge - width)
            return QRect(x, top, width, height)
        if card.side == "top":  # paleta: nahoře uprostřed volného místa mezi kartami
            free = self.free_rect()
            room = max(free.width() - 4, 0)  # paleta smí využít celé volné místo
            content = card.widget()
            wanted = (max(content.sizeHint().width(), content.minimumWidth()) + 2
                      if content is not None else room)
            width = min(wanted, room)
            left = free.left() + (free.width() - width) // 2
            return QRect(left, MARGIN, width, card.preferred_height())
        width = min(self.width_of(card), max(area.width() - 2 * MARGIN, 0))
        if card.side == "left":
            height = area.height() - MARGIN - LEFT_BOTTOM
            return QRect(MARGIN, MARGIN, width, max(height, MIN_HEIGHT))
        available = max(area.height() - 2 * MARGIN, MIN_HEIGHT)
        height = max(min(card.preferred_height(), available), MIN_HEIGHT)
        return QRect(area.width() - MARGIN - width, MARGIN, width, height)

    def relayout(self) -> None:
        # Napřed boční karty; paleta nahoře se řídí volným místem mezi nimi, přepínač
        # pohledů pravou kartou a pilulka všemi ostatními.
        order = {"left": 0, "right": 0, "top": 1, "corner": 2, "bottom": 3}
        for card in sorted(self.cards, key=lambda c: order[c.side]):
            if not card.isHidden():
                rect = self.geometry_of(card)
                if card.geometry() != rect:
                    card.setGeometry(rect)
                card.raise_()
        setter = getattr(self.view, "set_view_insets", None)
        if setter is not None:  # zjednodušené prohlížeče v testech ho nemají
            free = self.free_rect()
            left = free.left() + GAP if free.left() > 0 else 0
            right = self.view.width() - free.right() - 1
            top = max((c.geometry().bottom() + 1 + GAP for c in self.cards
                       if c.side == "top" and not c.isHidden()), default=0)
            bottom = max((self.view.height() - c.geometry().top() + GAP for c in self.cards
                          if c.side in ("bottom", "corner") and not c.isHidden()), default=0)
            setter(left, right + GAP if right > 0 else 0, top, bottom)

    def free_rect(self) -> QRect:
        """Část 3D pohledu mezi viditelnými kartami (pro kontroly a snímky)."""
        area = self.view.rect()
        left, right = area.left(), area.right()
        for card in self.cards:
            if card.isHidden():
                continue
            if card.side == "left":
                left = max(left, card.geometry().right() + 1)
            elif card.side == "right":
                right = min(right, card.geometry().left() - 1)
        return QRect(left, area.top(), max(right - left + 1, 0), area.height())
