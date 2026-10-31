"""Small original CAD glyphs painted at several device pixel ratios (no assets/dependency)."""

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


def _draw(p, kind):
    def line(*points):
        p.drawPolyline(QPolygonF([QPointF(*point) for point in points]))

    def box():
        line((4, 8), (12, 3), (20, 8), (12, 13), (4, 8), (4, 17), (12, 22),
             (20, 17), (20, 8))
        line((12, 13), (12, 22))

    if kind in ("box", "extrude", "shell", "hole", "loft", "sweep"):
        if kind == "loft":
            line((8, 4), (16, 4), (20, 20), (4, 20), (8, 4), (16, 4))
            line((8, 4), (6, 8), (6, 14), (4, 20))
            line((16, 4), (18, 8), (18, 14), (20, 20))
        elif kind == "sweep":
            path = QPainterPath(QPointF(4, 18))
            path.cubicTo(18, 22, 6, 2, 20, 5)
            p.drawPath(path)
            p.drawEllipse(QRectF(1, 15, 6, 6))
        else:
            box()
            if kind == "extrude":
                line((12, 10), (12, 0), (9, 3))
                line((12, 0), (15, 3))
            elif kind == "hole":
                p.drawEllipse(QRectF(9, 6, 6, 4))
            elif kind == "shell":
                line((7, 8), (12, 5), (17, 8), (12, 11), (7, 8))
    elif kind == "sketch":
        p.drawRect(QRectF(3, 7, 13, 13))
        line((10, 14), (18, 3), (21, 5), (13, 16), (10, 17), (10, 14))
    elif kind == "revolve":
        line((12, 1), (12, 23))
        p.drawArc(QRectF(3, 5, 18, 14), 35*16, 290*16)
        line((20, 6), (21, 11), (16, 10))
    elif kind == "fillet":
        path = QPainterPath(QPointF(3, 22))
        path.lineTo(3, 11)
        path.quadTo(3, 3, 11, 3)
        path.lineTo(22, 3)
        p.drawPath(path)
        line((10, 21), (10, 14), (14, 10), (21, 10))
    elif kind == "chamfer":
        line((3, 22), (3, 11), (11, 3), (22, 3))
        line((10, 21), (10, 14), (14, 10), (21, 10))
    elif kind == "pattern":
        for x in (3, 14):
            for y in (3, 14):
                p.drawRect(QRectF(x, y, 7, 7))
    elif kind == "mirror":
        line((12, 1), (12, 23))
        line((8, 5), (2, 19), (8, 19), (8, 5))
        line((16, 5), (22, 19), (16, 19), (16, 5))
    elif kind in ("measure", "section"):
        if kind == "section":
            box()
        else:
            p.drawRect(QRectF(2, 7, 20, 10))
        for x in (6, 10, 14, 18):
            line((x, 8), (x, 12))
    elif kind == "ndt":
        p.drawRect(QRectF(7, 2, 10, 5))
        line((12, 7), (3, 20), (20, 20))
        line((12, 7), (17, 14))
    elif kind == "document":
        line((5, 2), (15, 2), (20, 7), (20, 22), (5, 22), (5, 2))
        line((15, 2), (15, 7), (20, 7))
        line((8, 12), (16, 12))
        line((8, 17), (16, 17))
    elif kind == "params":
        path = QPainterPath(QPointF(7, 22))
        path.cubicTo(16, 22, 7, 2, 17, 2)
        p.drawPath(path)
        line((7, 10), (17, 10))
    else:
        box()


@lru_cache(maxsize=128)
def icon(kind: str, color_name: str) -> QIcon:
    result = QIcon()
    for size in (16, 24, 32):
        for ratio in (1., 1.25, 1.5, 2., 3.):
            pixmap = QPixmap(round(size*ratio), round(size*ratio))
            pixmap.setDevicePixelRatio(ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.scale(size/24, size/24)
            pen = QPen(QColor(color_name), 1.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            _draw(painter, kind)
            painter.end()
            result.addPixmap(pixmap)
    return result
