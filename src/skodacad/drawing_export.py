"""Jednostránkový pracovní výkres do PDF/DXF v milimetrech.

Bez tolerancí a značek není výkres automaticky způsobilý k výrobě. PDF podporuje
úsečky, lomené B-spliny prvního stupně a kružnice (aproximace max. 0,005 mm
na listu); ostatní křivky odmítne. DXF předává geometrii jádru přes build123d.
"""
from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from typing import Any

from build123d import Edge, ExportDXF, GeomType, Location
from build123d.exporters import LineType

from skodacad.document import Document, DocumentError
from skodacad.drawing_annotations import AnnotationSet, annotations
from skodacad.drawing_section_mark import section_mark
from skodacad.drawing_sheet import MARGIN, TITLE_HEIGHT, Sheet
from skodacad.rebuild import BuildResult, require_complete_part

_TOLERANCE = 0.005  # mm na listu; maximální průhyb kruhového oblouku
_MAX_SEGMENTS = 4096


def _check(document: Document, result: BuildResult, sheet: Sheet) -> AnnotationSet:
    require_complete_part(result)
    section_mark(sheet)
    values = annotations(document, result, sheet)
    if values.warnings:
        raise DocumentError("Výkres nelze vyvést: " + " ".join(values.warnings))
    if len(values.items) != len((document.drawing or {}).get("dimensions", [])):
        raise DocumentError("Některou kótu se nepodařilo zobrazit – export byl zastaven.")
    for item in values.items:
        x, y = item.label
        if x + len(item.text) * 2.5 > sheet.width - MARGIN or y + 2.5 > sheet.height - MARGIN:
            raise DocumentError(f"Popisek kóty {item.id} se nevejde na list – změň umístění.")
    return values


def _frame(sheet: Sheet) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    x0, y0, x1, y1 = MARGIN, MARGIN, sheet.width - MARGIN, sheet.height - MARGIN
    return [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)),
            ((x0, y1), (x0, y0)), ((x0, y0 + TITLE_HEIGHT), (x1, y0 + TITLE_HEIGHT)),
            ((x1 - 60, y0 + 24), (x1 - 10, y0 + 24))]


def _arrows(lines: tuple[Any, ...]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    a, b = lines[-1]
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length <= 1e-9:
        raise DocumentError("Kótovací čára má nulovou délku.")
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    result = []
    for (x, y), sign in ((a, 1), (b, -1)) if len(lines) == 3 else ((a, 1),):
        base = (x + sign * ux * 2, y + sign * uy * 2)
        result.extend([((x, y), (base[0] - uy * 0.7, base[1] + ux * 0.7)),
                       ((x, y), (base[0] + uy * 0.7, base[1] - ux * 0.7))])
    return result


def _title(document: Document) -> str:
    # Kótovací jádro neověřuje toleranci, materiálové ani technologické požadavky.
    if (len(document.name) + len(document.material) > 80
            or any(ord(c) < 32 for c in document.name + document.material)):
        raise DocumentError("Název nebo materiál nelze bezpečně umístit do popisového pole.")
    return f"{document.name} | {document.material} | Pracovní výkres – ověřit před výrobou"


def _scale_label(scale: float) -> str:
    return {0.1: "1:10", 0.2: "1:5", 0.5: "1:2", 1: "1:1", 2: "2:1", 5: "5:1"}[scale]


def _pdf_points(edge: Edge, dx: float, dy: float) -> list[tuple[float, float]]:
    if edge.geom_type == GeomType.LINE:
        count = 1
    elif edge.geom_type == GeomType.CIRCLE:
        radius = edge.radius
        if not math.isfinite(radius) or radius <= 0:
            raise DocumentError("Kruhovou hranu nelze bezpečně převést do PDF.")
        step = 2 * math.acos(max(-1.0, 1 - min(_TOLERANCE / radius, 1.0)))
        if not math.isfinite(step) or step <= 0:
            raise DocumentError("Kruhová hrana je pro PDF příliš velká – export byl zastaven.")
        count = max(2, math.ceil((edge.length / radius) / step))
        if count > _MAX_SEGMENTS:
            raise DocumentError("Kruhová hrana je pro přesný PDF náhled příliš složitá.")
    elif edge.geom_type == GeomType.BSPLINE:
        from OCP.BRepAdaptor import BRepAdaptor_Curve

        curve = BRepAdaptor_Curve(edge.wrapped)
        spline = curve.BSpline()
        if spline.Degree() != 1:
            raise DocumentError("PDF zatím nepodporuje zakřivený B-spline – export byl zastaven.")
        first, last = curve.FirstParameter(), curve.LastParameter()
        knots = [spline.Knot(i) for i in range(1, spline.NbKnots() + 1)]
        params = [first, *(k for k in knots if first < k < last), last]
        if len(params) > _MAX_SEGMENTS:
            raise DocumentError("Hrana je pro PDF příliš složitá – export byl zastaven.")
        return [(curve.Value(t).X() + dx, curve.Value(t).Y() + dy) for t in params]
    else:
        raise DocumentError("PDF zatím nepodporuje některý tvar křivky – export byl zastaven.")
    return [(edge.position_at(i / count).X + dx, edge.position_at(i / count).Y + dy)
            for i in range(count + 1)]


def _pdf(document: Document, sheet: Sheet, dimensions: AnnotationSet, target: str) -> None:
    from PySide6.QtCore import QMarginsF, QPointF, QSizeF, Qt
    from PySide6.QtGui import (
        QFont,
        QGuiApplication,
        QPageLayout,
        QPageSize,
        QPainter,
        QPdfWriter,
        QPen,
        QPolygonF,
    )

    if QGuiApplication.instance() is None:
        raise DocumentError("Export PDF potřebuje spuštěné grafické prostředí aplikace.")
    writer = QPdfWriter(target)
    writer.setResolution(254)  # přesně 10 bodů tiskárny na mm
    if not writer.setPageSize(QPageSize(QSizeF(sheet.width, sheet.height),
                                        QPageSize.Unit.Millimeter)):
        raise DocumentError("Velikost PDF stránky nelze nastavit.")
    if not writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter):
        raise DocumentError("Okraje PDF stránky nelze nastavit.")
    painter = QPainter(writer)
    if not painter.isActive():
        raise DocumentError("PDF nelze vytvořit.")
    try:
        def point(x: float, y: float) -> QPointF:
            return QPointF(x * 10, (sheet.height - y) * 10)

        def draw_line(a: tuple[float, float], b: tuple[float, float]) -> None:
            painter.drawLine(point(*a), point(*b))

        painter.setPen(QPen(Qt.GlobalColor.black, 2.5))
        for a, b in _frame(sheet):
            draw_line(a, b)
        font = QFont("Arial")
        font.setPixelSize(25)
        painter.setFont(font)
        painter.drawText(point(MARGIN + 3, MARGIN + 6), _title(document))
        painter.drawText(point(MARGIN + 3, MARGIN + 12),
                         f"Měřítko {_scale_label(sheet.scale)} | mm")
        painter.drawText(point(sheet.width - MARGIN - 60, MARGIN + 27), "Kontrola: 50 mm")
        for view in sheet.views:
            for edges, style in ((view.geometry.visible, Qt.PenStyle.SolidLine),
                                 (view.geometry.hidden, Qt.PenStyle.DashLine),
                                 (view.geometry.hatching, Qt.PenStyle.SolidLine)):
                painter.setPen(QPen(Qt.GlobalColor.black, 2.5, style))
                for edge in edges:
                    points = _pdf_points(edge, *view.offset)
                    painter.drawPolyline(QPolygonF([point(*p) for p in points]))
            if view.name == "section":
                painter.drawText(point(view.bounds[0], view.bounds[3] + 2), sheet.section_label)
        mark = section_mark(sheet)
        if mark is not None:
            painter.setPen(QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.DashDotLine))
            draw_line(*mark.line)
            painter.setPen(QPen(Qt.GlobalColor.black, 2))
            for a, b in mark.arrows:
                draw_line(a, b)
            for label in mark.labels:
                painter.drawText(point(*label), "A")
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        for dimension in dimensions.items:
            for a, b in (*dimension.lines, *_arrows(dimension.lines)):
                draw_line(a, b)
            painter.drawText(point(*dimension.label), dimension.text)
    finally:
        painter.end()
        del writer


def _dxf(document: Document, sheet: Sheet, dimensions: AnnotationSet, target: str) -> None:
    exporter = ExportDXF()
    exporter.add_layer("obrys", line_weight=0.25)
    exporter.add_layer("skryte", line_type=LineType.HIDDEN, line_weight=0.18)
    exporter.add_layer("srafy", line_weight=0.18)
    exporter.add_layer("rovina_rezu", line_type=LineType.CENTER, line_weight=0.18)
    exporter.add_layer("koty", line_weight=0.18)
    exporter.add_layer("popisy", line_weight=0.18)
    # Výchozí typy knihovny jsou v palcových délkách; 6,35mm čárka by skrytou
    # 5mm hranu vykreslila jako plnou. Definice níže mají rozměry v mm na listu.
    exporter._document.linetypes.new("SKODA_SKRYTA", dxfattribs={
        "description": "Skryta hrana", "pattern": [1.5, 1.0, -0.5]})
    exporter._document.linetypes.new("SKODA_REZ", dxfattribs={
        "description": "Rovina rezu", "pattern": [6.0, 4.0, -1.0, 0.5, -0.5]})
    exporter._document.layers.get("skryte").dxf.linetype = "SKODA_SKRYTA"
    exporter._document.layers.get("rovina_rezu").dxf.linetype = "SKODA_REZ"

    def add_lines(lines: Any, layer: str) -> None:
        shapes = [Edge.make_line((*a, 0), (*b, 0)) for a, b in lines
                  if math.dist(a, b) > 1e-9]
        if shapes:
            exporter.add_shape(shapes, layer=layer)

    add_lines(_frame(sheet), "obrys")
    for view in sheet.views:
        move = Location((*view.offset, 0))
        for edges, layer in ((view.geometry.visible, "obrys"), (view.geometry.hidden, "skryte"),
                             (view.geometry.hatching, "srafy")):
            if edges:
                before = len(exporter._modelspace)
                exporter.add_shape([edge.moved(move) for edge in edges], layer=layer)
                if len(exporter._modelspace) - before < len(edges):
                    raise DocumentError("Některé hrany nelze převést do DXF – export byl zastaven.")
        if view.name == "section":
            exporter._modelspace.add_text(sheet.section_label, dxfattribs={  # pinned build123d API
                "insert": (view.bounds[0], view.bounds[3] + 2, 0),
                "height": 2.5, "layer": "popisy"})
    mark = section_mark(sheet)
    if mark is not None:
        add_lines((mark.line,), "rovina_rezu")
        add_lines(mark.arrows, "obrys")
        for label in mark.labels:
            exporter._modelspace.add_text("A", dxfattribs={
                "insert": (*label, 0), "height": 2.5, "layer": "popisy"})
    for dimension in dimensions.items:
        add_lines((*dimension.lines, *_arrows(dimension.lines)), "koty")
        exporter._modelspace.add_text(dimension.text, dxfattribs={  # pinned build123d API
            "insert": (*dimension.label, 0), "height": 2.5, "layer": "koty"})
    for y, text in ((MARGIN + 6, _title(document)),
                    (MARGIN + 12, f"Měřítko {_scale_label(sheet.scale)} | mm")):
        exporter._modelspace.add_text(text, dxfattribs={  # pinned build123d API
            "insert": (MARGIN + 3, y, 0), "height": 2.5, "layer": "popisy"})
    exporter._modelspace.add_text("Kontrola: 50 mm", dxfattribs={
        "insert": (sheet.width - MARGIN - 60, MARGIN + 27, 0), "height": 2.5,
        "layer": "popisy"})
    exporter.write(target)


def export(document: Document, result: BuildResult, sheet: Sheet, path: str | Path) -> Path:
    """Uloží PDF/DXF až po kompletní kontrole; při chybě zachová původní soubor."""
    target = Path(path)
    suffix = target.suffix.lower()
    if suffix not in (".pdf", ".dxf"):
        raise DocumentError("Výkres lze uložit do PDF nebo DXF.")
    values = _check(document, result, sheet)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=suffix, delete=False) as out:
            temporary = out.name
        if suffix == ".pdf":
            _pdf(document, sheet, values, temporary)
        else:
            _dxf(document, sheet, values, temporary)
        if not Path(temporary).stat().st_size:
            raise DocumentError("Export vytvořil prázdný soubor.")
        if suffix == ".pdf":
            with open(temporary, "rb") as file:
                header = file.read(5)
                file.seek(max(0, os.fstat(file.fileno()).st_size - 64))
                tail = file.read()
            if header != b"%PDF-" or b"%%EOF" not in tail:
                raise DocumentError("PDF není úplné – export byl zastaven.")
        os.replace(temporary, target)
        temporary = None
        return target
    except (DocumentError, OSError):
        raise
    except Exception as exc:  # noqa: BLE001 – chyba exportu nesmí ukončit okno aplikace
        raise DocumentError(f"Výkres se nepodařilo uložit ({type(exc).__name__}).") from exc
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
