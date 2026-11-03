"""Kompaktní panel sestavy: výška aktuální záložky a zpřístupnění skrytého pole."""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QScrollArea, QSizePolicy, QTabWidget


class MovementTabs(QTabWidget):
    """Nezabírá místo podle nejvyšší neaktivní záložky."""

    def __init__(self):
        super().__init__()
        self.setDocumentMode(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.currentChanged.connect(lambda _index: self.updateGeometry())

    def _height(self, page_height):
        return max(0, page_height) + self.tabBar().sizeHint().height() + 8

    def sizeHint(self):
        hint = QSize(super().sizeHint())
        if self.currentWidget() is not None:
            hint.setHeight(self._height(self.currentWidget().sizeHint().height()))
        return hint

    def minimumSizeHint(self):
        hint = QSize(super().minimumSizeHint())
        if self.currentWidget() is not None:
            hint.setHeight(self._height(self.currentWidget().minimumSizeHint().height()))
        return hint

    def hasHeightForWidth(self):
        page = self.currentWidget()
        return page is not None and page.hasHeightForWidth()

    def heightForWidth(self, width):
        page = self.currentWidget()
        if page is None:
            return -1
        return self._height(page.heightForWidth(width) if page.hasHeightForWidth()
                            else page.sizeHint().height())


class ComponentScroll(QScrollArea):
    """Přechod na konkrétní pole otevře jeho záložku a rozbalovací sekci."""

    def __init__(self, reveal):
        super().__init__()
        self._reveal = reveal

    def ensureWidgetVisible(self, child, xmargin=50, ymargin=50):
        self._reveal(child)
        super().ensureWidgetVisible(child, xmargin, ymargin)
