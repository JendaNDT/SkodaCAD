"""Barvy a písmo okna podle návrhu hlavního okna 1a (P7.48).

Hodnoty jsou převzaté z tabulky „Design Tokens“ v ``docs/p7-48-navrh-okna/README.md``.
Poloprůhledné tokeny (``float``, ``sep``, ``accentbg`` …) jsou tu jako RGBA; Qt je
kreslí přes jinou barvu, proto ``opaque`` dává jejich neprůhlednou podobu nad podkladem
(karty nad nativním 3D jsou podle rozhodnutí R1 neprůhledné).

Modul mění jen vzhled okna: paletu aplikace a písmo. Model, výpočty ani soubory
se jím nemění.
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "win": "#ececec", "tb": "#f6f6f6", "float": (247, 247, 249, .88),
    "fg": "#1d1d1f", "fg2": "#56565b", "fg3": "#86868b",
    "sep": (0, 0, 0, .09), "sep2": (0, 0, 0, .17),
    "ctl": "#ffffff", "accent": "#0a64d8", "accentbg": (10, 100, 216, .13),
    "btn": "#0a64d8", "vp1": "#f2f5fa", "vp2": "#b8c4d6",
    "ok": "#166534", "okbg": (22, 101, 52, .1),
    "warn": "#8a5a0b", "warnbg": (185, 119, 14, .13), "err": "#b42318",
    "skbg": "#fbfbfb", "skgrid": "#ececec", "skfree": "#1f5fbf", "sktext": "#666666",
}
DARK = {
    "win": "#1f1f21", "tb": "#2a2a2c", "float": (42, 42, 45, .86),
    "fg": "#f2f2f4", "fg2": "#b4b4ba", "fg3": "#8c8c92",
    "sep": (255, 255, 255, .08), "sep2": (255, 255, 255, .17),
    "ctl": "#3a3a3d", "accent": "#4a9eff", "accentbg": (74, 158, 255, .2),
    "btn": "#0a6ad8", "vp1": "#3b4049", "vp2": "#16181c",
    "ok": "#9bdab5", "okbg": (155, 218, 181, .14),
    "warn": "#e8b45c", "warnbg": (232, 180, 92, .16), "err": "#ffb0a6",
    "skbg": "#1c1d20", "skgrid": (255, 255, 255, .05), "skfree": "#6aa5ff", "sktext": "#a8a8ae",
}
APPEARANCES = ("system", "light", "dark")
# Průhlednost vybraných ploch ikon Duo (README návrhu, Assets).
ICON_FILL = {False: .24, True: .30}


def color(value) -> QColor:
    """Token jako QColor; RGBA n-tice nese průhlednost v alfa kanálu."""
    if isinstance(value, tuple):
        r, g, b, a = value
        return QColor(r, g, b, round(a * 255))
    return QColor(value)


def opaque(value, background) -> QColor:
    """Poloprůhledný token smíchaný s podkladem – barva, kterou oko skutečně uvidí."""
    top, under = color(value), color(background)
    a = top.alphaF()
    return QColor.fromRgbF(*(a * t + (1 - a) * u for t, u in zip(
        (top.redF(), top.greenF(), top.blueF()),
        (under.redF(), under.greenF(), under.blueF()), strict=True)))


def is_dark(appearance: str | None = None) -> bool:
    """Tmavý vzhled: volba uživatele, u „Podle systému“ schéma systému."""
    app = QApplication.instance()
    appearance = appearance or (app.property("skodacadAppearance") if app else None) or "system"
    if appearance in ("light", "dark"):
        return appearance == "dark"
    return app is not None and app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def tokens(dark: bool | None = None) -> dict:
    return DARK if (is_dark() if dark is None else dark) else LIGHT


def card_color(dark: bool | None = None) -> QColor:
    """Neprůhledná barva plovoucí karty (R1) nad horní barvou 3D pozadí."""
    t = tokens(dark)
    return opaque(t["float"], t["vp1"])


def palette(dark: bool) -> QPalette:
    t = tokens(dark)
    window, base = card_color(dark), QColor(t["ctl"])
    result = QPalette(base, window)  # dopočítá stíny (Light, Mid, Dark …)
    roles = QPalette.ColorRole
    for role, value in ((roles.Window, window), (roles.WindowText, QColor(t["fg"])),
                        (roles.Base, base), (roles.AlternateBase, QColor(t["tb"])),
                        (roles.Text, QColor(t["fg"])), (roles.Button, base),
                        (roles.ButtonText, QColor(t["fg"])),
                        (roles.BrightText, QColor("#ffffff")),
                        (roles.Highlight, QColor(t["btn"])),
                        (roles.HighlightedText, QColor("#ffffff")),
                        (roles.Link, QColor(t["accent"])),
                        (roles.LinkVisited, QColor(t["accent"])),
                        (roles.PlaceholderText, QColor(t["fg3"])),
                        (roles.ToolTipBase, base), (roles.ToolTipText, QColor(t["fg"]))):
        result.setColor(role, value)
    disabled = QPalette.ColorGroup.Disabled
    for role in (roles.WindowText, roles.Text, roles.ButtonText):
        result.setColor(disabled, role, QColor(t["fg3"]))
    result.setColor(disabled, roles.Highlight, opaque(t["sep2"], window))
    return result


def font_family() -> str | None:
    """Písmo z návrhu, je-li v systému; jinak None (zůstane výchozí písmo Qt)."""
    if sys.platform == "darwin":
        return None  # výchozí písmo Qt na Macu je už systémové SF Pro
    families = set(QFontDatabase.families())
    for name in ("Segoe UI Variable Text", "Segoe UI"):
        if name in families:
            return name
    return None


def apply(app: QApplication | None = None) -> bool:
    """Nastaví paletu a písmo podle zvoleného vzhledu. Vrací True, když byl tmavý."""
    app = app or QApplication.instance()
    dark = is_dark()
    if app.property("skodacadThemeDark") is not dark or app.palette() != palette(dark):
        app.setProperty("skodacadThemeDark", dark)
        app.setPalette(palette(dark))
    family = font_family()
    if family and app.font().family() != family:
        font = QFont(app.font())
        font.setFamily(family)  # velikost zatím beze změny (P7.50 upraví lištu a rozměry)
        app.setFont(font)
    if not app.property("skodacadThemeHooked"):
        app.setProperty("skodacadThemeHooked", True)
        app.styleHints().colorSchemeChanged.connect(lambda _scheme: apply(app))
    return dark
