"""Stavová pilulka a přepínač pohledů dole nad 3D (P7.53, návrh hlavního okna 1a).

Pilulka (dole uprostřed, výška 32 px, 12 px) ukazuje stav přepočtu („✓ Spočítáno“,
„⏳ Přepočítávám… 3 s“ se Zastavit, chyba) a vedle za oddělovačem poslední zprávu
okna (výběr, hlášení). Zprávy dál zapisuje ``QMainWindow.statusBar()``, který je
skrytý (R5): pilulka jen čte ``messageChanged``. Nápověda k myši je pod F1.

Přepínač pohledů (vpravo dole) má tlačítka Izo, Zepředu, Shora, Celý díl. Jsou to
tytéž ``QAction`` jako v nabídce a zkratky 0/1/7/F, aktivní pohled je zvýrazněný.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from skodacad.gui import ui_theme

HEIGHT = 32
TEXT_WIDTH = 520  # nejdelší zpráva v pilulce, delší se zkrátí „…“ (celá v bublině)
STATUS = {"ok": "✓ Spočítáno", "error": "✕ Chyba v modelu", "empty": "Bez dílu"}
LABELS = {"iso": "Izo", "front": "Zepředu", "top": "Shora", "fit": "Celý díl"}


def _font(widget: QWidget, size: int, weight=QFont.Weight.Normal) -> QFont:
    font = QFont(widget.font())
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


class StatusPill(QWidget):
    """Obsah pilulky: stav | zpráva. Ukazatel přepočtu (štítek, pruh, Zastavit) vkládá okno."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("status_pill")
        self.setFixedHeight(HEIGHT - 2)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)
        self.state = QLabel()
        self.state.setObjectName("status_pill_state")
        self.state.setFont(_font(self, 12, QFont.Weight.DemiBold))
        layout.addWidget(self.state)
        self._progress = QHBoxLayout()
        self._progress.setSpacing(6)
        layout.addLayout(self._progress)
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.Shape.VLine)
        self.separator.setStyleSheet("color: palette(mid);")
        self.separator.setFixedHeight(14)
        layout.addWidget(self.separator)
        self.context = QLabel()
        self.context.setObjectName("status_pill_context")
        self.context.setFont(_font(self, 12))
        self.context.setTextFormat(Qt.TextFormat.PlainText)
        self.context.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.context)
        self._kind = "empty"
        self._message = ""

    def add_progress(self, *widgets: QWidget) -> None:
        for widget in widgets:
            self._progress.addWidget(widget)

    def set_state(self, kind: str) -> None:
        """``ok`` / ``error`` / ``empty``; během přepočtu se stav schová (ukazatel)."""
        self._kind = kind
        self._refresh()

    def set_message(self, text: str) -> None:
        self._message = text or ""
        self._refresh()

    def set_computing(self, computing: bool) -> None:
        self.state.setVisible(not computing)
        self.updateGeometry()

    @property
    def message(self) -> str:
        return self._message

    def _refresh(self) -> None:
        t = ui_theme.tokens()
        colors = {"ok": t["ok"], "error": t["err"], "empty": t["fg3"]}
        self.state.setText(STATUS[self._kind])
        self.state.setStyleSheet(f"color: {colors[self._kind]};")
        metrics = self.context.fontMetrics()
        self.context.setText(metrics.elidedText(self._message, Qt.TextElideMode.ElideRight,
                                                TEXT_WIDTH))
        self.context.setToolTip(self._message if self.context.text() != self._message else "")
        self.context.setStyleSheet(f"color: {t['fg2']};")
        self.separator.setVisible(bool(self._message))
        self.context.setVisible(bool(self._message))
        self.updateGeometry()

    def refresh_style(self) -> None:
        self._refresh()


class ViewSwitcher(QWidget):
    """Izo | Zepředu | Shora | Celý díl – sdílené akce pohledů, aktivní zvýrazněný."""

    def __init__(self, view_actions: dict, fit_action, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("view_switcher")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.buttons: dict[str, QToolButton] = {}
        self.actions = {}
        for key, text in LABELS.items():
            action = fit_action if key == "fit" else view_actions[key]
            # Bez setDefaultAction: tlačítko by si při každé změně akce vzalo její dlouhý
            # název („Izometrie“). Klik spustí tutéž akci, dostupnost se přebírá.
            button = QToolButton()
            button.setObjectName(f"view_{key}")
            button.setText(text)
            button.setAutoRaise(True)
            button.setFont(_font(self, 12))
            button.setAccessibleName(action.text())
            shortcut = action.shortcut().toString()
            button.setToolTip(action.text() + (f" ({shortcut})" if shortcut else ""))
            button.clicked.connect(action.trigger)
            action.changed.connect(lambda b=button, a=action: b.setEnabled(a.isEnabled()))
            button.setEnabled(action.isEnabled())
            layout.addWidget(button)
            self.buttons[key] = button
            self.actions[key] = action
            if key != "fit":
                action.triggered.connect(lambda _checked=False, k=key: self.set_active(k))
        self.active = "iso"
        self.set_active("iso")

    def set_active(self, key: str) -> None:
        """Zvýrazní naposledy zvolený standardní pohled (Celý díl pohled nemění)."""
        if key in self.buttons and key != "fit":
            self.active = key
        self.refresh_style()

    def refresh_style(self) -> None:
        t = ui_theme.tokens()
        active = ui_theme.opaque(t["accentbg"], ui_theme.card_color()).name()
        for key, button in self.buttons.items():
            if key == self.active:
                button.setStyleSheet(f"QToolButton {{ background: {active}; color: {t['accent']};"
                                     f" font-weight: 600; border: none; border-radius: 6px;"
                                     f" padding: 3px 9px; }}")
            else:
                button.setStyleSheet(f"QToolButton {{ background: transparent;"
                                     f" color: {t['fg']}; border: none; border-radius: 6px;"
                                     f" padding: 3px 9px; }}")
