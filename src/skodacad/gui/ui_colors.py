"""Palette-based UI colors, independent of the geometry and document."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def contrast(foreground: QColor, background: QColor) -> float:
    def luminance(color):
        values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                  for v in (color.redF(), color.greenF(), color.blueF())]
        return sum(a*b for a, b in zip(values, (.2126, .7152, .0722), strict=True))
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b + .05) / (a + .05)


def secondary_color(palette=None) -> QColor:
    palette = palette or QApplication.palette()
    bg = palette.color(QPalette.ColorRole.Window)
    fg = palette.color(QPalette.ColorRole.WindowText)
    mixed = QColor.fromRgbF(*[.8*a + .2*b for a, b in zip(
        (fg.redF(), fg.greenF(), fg.blueF()), (bg.redF(), bg.greenF(), bg.blueF()), strict=True)])
    return mixed if contrast(mixed, bg) >= 4.5 else fg


def status_color(status, palette=None) -> QColor:
    palette = palette or QApplication.palette()
    dark = palette.color(QPalette.ColorRole.Window).lightnessF() < .5
    colors = ({"ok": "#9bdab5", "error": "#ffb0a6", "pending": "#b9c3d2",
               "skipped": "#d2c8b8"} if dark else
              {"ok": "#166534", "error": "#b42318", "pending": "#536070",
               "skipped": "#715b35"})
    return QColor(colors.get(status, colors["pending"]))
