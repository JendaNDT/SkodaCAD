"""Kresba karet nástrojů Měření, Řez a Mapa tloušťky (P7.54, rámy 3b a 3c návrhu 1a).

Data seznamů se nemění: položka nese dál celý text „Rozteč os: 40.00 mm“ (čtou ho testy,
filtr uložených měření i čtečky obrazovky). Delegát ho jen kreslí jako řádek výsledku –
popisek vlevo, hodnota vpravo – a řádek, jehož čára je právě ve 3D, zvýrazní podkladem
``--okbg`` a hodnotou ``--ok`` tučně. Seznamy se nikdy neposouvají: výška = počet
viditelných řádků (u uložených měření nejvýš ``SAVED_ROWS``, pak pojistka posuvníkem).
"""

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QListWidget,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QWidget,
)

from skodacad.gui import ui_theme

ROW_HEIGHT = 28
SAVED_ROWS = 6  # víc uložených měření → posuvník jen jako pojistka (filtr je zúží)
STATE_ROLE = Qt.ItemDataRole.UserRole + 43  # "ok" / "error" / "pending" u uložených měření
GLYPHS = {"ok": "✓", "error": "✕"}
SECTION_COLOR = (0.82, 0.38, 0.33)  # plochy řezu ve 3D (viewer.py, „cihlově“)
SECTION_GREY = (0.62, 0.62, 0.62)  # plochy řezu pod objemovou mapou pokrytí


def split_value(text: str) -> tuple[str, str]:
    """„Rozteč os: 40.00 mm“ → („Rozteč os“, „40.00 mm“); bez dvojtečky celý text vlevo."""
    label, separator, value = text.partition(": ")
    return (label, value) if separator else (text, "")


def focus_text(text: str) -> str:
    """Hlavní hodnota do pilulky bez dvojtečky (rám 3b: „Rozteč os 40.00 mm“)."""
    label, value = split_value(text)
    return f"{label} {value}" if value else label


class ValueRowDelegate(QStyledItemDelegate):
    """Řádek výsledku měření: popisek vlevo, hodnota vpravo, aktuální řádek zvýrazněný."""

    def sizeHint(self, option, index):  # noqa: N802
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter, option, index):  # noqa: N802
        view = self.parent()
        t = ui_theme.tokens()
        current = isinstance(view, QAbstractItemView) and view.currentIndex() == index
        label, value = split_value(index.data(Qt.ItemDataRole.DisplayRole) or "")
        state = index.data(STATE_ROLE)
        glyph = GLYPHS.get(state, "")
        rect = QRectF(option.rect).adjusted(0, 1, 0, -1)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if current:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ui_theme.opaque(t["okbg"], ui_theme.card_color()))
            painter.drawRoundedRect(rect, 6, 6)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ui_theme.opaque(t["sep"], ui_theme.card_color()))
            painter.drawRoundedRect(rect, 6, 6)
        text_rect = rect.adjusted(10, 0, -10, 0)
        align = Qt.AlignmentFlag.AlignVCenter
        base = QFont(option.font)
        if glyph:
            painter.setFont(base)
            painter.setPen(ui_theme.color(t["ok"] if state == "ok" else t["err"]))
            painter.drawText(text_rect, align | Qt.AlignmentFlag.AlignLeft, glyph)
            text_rect.setLeft(text_rect.left() + painter.fontMetrics().horizontalAdvance(
                glyph) + 8)
        error = state == "error"
        value_font = QFont(base)
        if current:
            value_font.setWeight(QFont.Weight.Bold)
        painter.setFont(value_font)
        value_width = painter.fontMetrics().horizontalAdvance(value) if value else 0
        painter.setPen(ui_theme.color(t["err"] if error else t["ok"] if current else t["fg"]))
        if value:
            painter.drawText(text_rect, align | Qt.AlignmentFlag.AlignRight, value)
        label_font = QFont(base)
        if current:
            label_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(label_font)
        room = int(text_rect.width() - value_width - (12 if value else 0))
        shown = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, room)
        painter.setPen(ui_theme.color(t["err"] if error else t["fg"] if current else t["fg2"]))
        painter.drawText(text_rect, align | Qt.AlignmentFlag.AlignLeft, shown)
        if option.state & QStyle.StateFlag.State_HasFocus and view.hasFocus():
            pen = QPen(ui_theme.color(t["accent"]))
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        painter.restore()


def result_list(name: str) -> QListWidget:
    """Seznam výsledků bez rámečku a podkladu; výšku nastavuje ``fit_rows``."""
    widget = QListWidget()
    widget.setObjectName(name)
    widget.setFrameShape(QFrame.Shape.NoFrame)
    widget.setItemDelegate(ValueRowDelegate(widget))
    widget.setMouseTracking(True)
    widget.setStyleSheet("QListWidget { background: transparent; border: none; }")
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    widget.currentRowChanged.connect(lambda _row: widget.viewport().update())
    return widget


def fit_rows(widget: QListWidget, limit: int | None = None) -> int:
    """Výška seznamu = viditelné řádky (nejvýš ``limit``), bez nich se seznam skryje."""
    shown = sum(not widget.item(row).isHidden() for row in range(widget.count()))
    rows = shown if limit is None else min(shown, limit)
    widget.setVerticalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded if rows < shown
        else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setFixedHeight(rows * ROW_HEIGHT + 2 * widget.frameWidth())
    widget.setVisible(shown > 0)
    return shown


def swatch(rgb: tuple[float, float, float], size: int = 12) -> QLabel:
    """Čtvereček barvy (vzorek plochy řezu, rám 3c)."""
    label = QLabel()
    label.setFixedSize(size, size)
    set_swatch(label, rgb)
    return label


def set_swatch(label: QLabel, rgb: tuple[float, float, float]) -> None:
    color = QColor.fromRgbF(*rgb)
    if label.property("swatch") == color.name():
        return
    label.setProperty("swatch", color.name())
    label.setStyleSheet(f"background: {color.name()}; border-radius: 3px;")


def set_role(button: QPushButton, text: str, role: str) -> None:
    """Text a role tlačítka zapnout/vypnout (primární = hlavní krok karty)."""
    button.setText(text)
    if button.property("role") != role:
        button.setProperty("role", role)
        button.style().unpolish(button)  # QSS podle vlastnosti se jinak neobnoví
        button.style().polish(button)


def separator() -> QWidget:
    """Linka 0,5 px mezi částmi karty (jako nad sbalitelnou sekcí)."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: palette(mid);")
    return line
