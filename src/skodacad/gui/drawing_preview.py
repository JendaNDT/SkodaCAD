"""Pracovní náhled rozmístění pohledů; nenahrazuje export ani výrobní výkres."""
from __future__ import annotations

from build123d import GeomType
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from skodacad.drawing_annotations import AnnotationSet
from skodacad.drawing_sheet import MARGIN, TITLE_HEIGHT, Sheet


class SheetPreview(QWidget):
    def __init__(self, sheet: Sheet, dimensions: AnnotationSet | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sheet = sheet
        self.dimensions = dimensions or AnnotationSet((), ())
        self.setMinimumSize(500, 360)

    def paintEvent(self, _event) -> None:  # noqa: N802 – metoda Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#e6e6e6"))
        page = self.sheet
        scale = min((self.width() - 20) / page.width, (self.height() - 20) / page.height)
        left = (self.width() - page.width * scale) / 2
        top = (self.height() - page.height * scale) / 2

        def point(x: float, y: float) -> QPointF:
            return QPointF(left + x * scale, top + (page.height - y) * scale)

        painter.setPen(QPen(QColor("#555"), 1))
        painter.setBrush(QColor("white"))
        painter.drawRect(QRectF(left, top, page.width * scale, page.height * scale))
        b = point(page.width - MARGIN, page.height - MARGIN)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#222"), 1))
        painter.drawRect(QRectF(b.x() - (page.width - 2 * MARGIN) * scale, b.y(),
                                (page.width - 2 * MARGIN) * scale,
                                (page.height - 2 * MARGIN) * scale))
        painter.drawLine(point(MARGIN, MARGIN + TITLE_HEIGHT),
                         point(page.width - MARGIN, MARGIN + TITLE_HEIGHT))
        for view in page.views:
            dx, dy = view.offset
            for edges, style in ((view.geometry.visible, Qt.PenStyle.SolidLine),
                                 (view.geometry.hidden, Qt.PenStyle.DashLine)):
                painter.setPen(QPen(QColor("#111"), 1.2, style))
                for edge in edges:
                    steps = 1 if edge.geom_type == GeomType.LINE else 96
                    previous = edge.position_at(0)
                    for i in range(1, steps + 1):
                        current = edge.position_at(i / steps)
                        painter.drawLine(point(previous.X + dx, previous.Y + dy),
                                         point(current.X + dx, current.Y + dy))
                        previous = current
        painter.setPen(QPen(QColor("#145d9c"), 1))
        painter.setBrush(QColor("#145d9c"))
        for dimension in self.dimensions.items:
            for start, end in dimension.lines:
                painter.drawLine(point(*start), point(*end))
            start, end = dimension.lines[-1]
            a, b = point(*start), point(*end)
            length = ((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5
            if length > 1:
                ux, uy = (b.x() - a.x()) / length, (b.y() - a.y()) / length
                for tip, direction in ((a, 1), (b, -1)) if len(dimension.lines) == 3 else ((a, 1),):
                    back = QPointF(tip.x() + direction * ux * 6, tip.y() + direction * uy * 6)
                    painter.drawPolygon(QPolygonF([tip,
                        QPointF(back.x() - uy * 2.5, back.y() + ux * 2.5),
                        QPointF(back.x() + uy * 2.5, back.y() - ux * 2.5)]))
            label = point(*dimension.label)
            painter.drawText(QPointF(label.x() + 3, label.y() - 3), dimension.text)
        painter.end()


class DrawingPreviewDialog(QDialog):
    def __init__(self, sheet: Sheet, dimensions: AnnotationSet | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pracovní náhled listu")
        layout = QVBoxLayout(self)
        note = QLabel("Pracovní náhled pohledů a kót. Řez, popisové pole a export zatím "
                      "nejsou hotové; zkontroluj čitelnost kót.")
        note.setWordWrap(True)
        layout.addWidget(note)
        if dimensions and dimensions.warnings:
            warning = QLabel("Nezobrazené kóty – oprav jejich vazbu nebo umístění:\n"
                             + "\n".join(dimensions.warnings))
            warning.setWordWrap(True)
            warning.setTextFormat(Qt.TextFormat.PlainText)
            warning.setStyleSheet("color: #b42318; font-weight: bold;")
            layout.addWidget(warning)
        layout.addWidget(SheetPreview(sheet, dimensions))
        self.resize(900, 650)
