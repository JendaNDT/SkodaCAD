"""Odhad překrytí kót v milimetrech na výkresovém listu.

Texty mají konzervativní obálku pro písmo 2,5 mm. Nález je možné překrytí,
ne důkaz nečitelnosti. Kontrola nepředstírá shodu s výkresovou normou ani
úplné rozpoznání všech optických kolizí.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from build123d import Edge, Face, Location, Plane

from skodacad.drawing_section_mark import section_mark
from skodacad.drawing_sheet import MARGIN, TITLE_HEIGHT, Sheet

if TYPE_CHECKING:
    from skodacad.drawing_annotations import Annotation

Point = tuple[float, float]
Line = tuple[Point, Point]
Rect = tuple[float, float, float, float]
_MAX_DIMENSIONS = 200
_MAX_GEOMETRY_CHECKS = 4000
_MAX_BOUNDING_CHECKS = 100000
_MAX_MESSAGES = 30


@dataclass(frozen=True)
class CollisionReport:
    messages: tuple[str, ...] = ()
    complete: bool = True


def _text_box(item: Annotation) -> Rect:
    # PDF/DXF umísťují text vlevo na základní čáru; 2,5 mm na znak je záměrná rezerva.
    x, y = item.label
    return (x - 0.3, y - 0.6, x + max(2.5, 2.5 * len(item.text)) + 0.3, y + 3.0)


def _boxes_overlap(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _line_hits_box(line: Line, box: Rect) -> bool:
    """Průnik úsečky s obdélníkem včetně jeho vnitřku (Liang–Barsky)."""
    (x0, y0), (x1, y1) = line
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - box[0]), (dx, box[2] - x0),
                 (-dy, y0 - box[1]), (dy, box[3] - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def _line_collision(a: Line, b: Line) -> bool:
    """Vnitřní průsečík nebo delší souběžné překrytí kótovacích čar."""
    (ax, ay), (bx, by) = a
    (cx, cy), (dx, dy) = b
    ux, uy, vx, vy = bx - ax, by - ay, dx - cx, dy - cy
    la, lb = math.hypot(ux, uy), math.hypot(vx, vy)
    if min(la, lb) < 1e-9:
        return False
    cross = ux * vy - uy * vx
    if abs(cross) <= 1e-9 * la * lb:
        if abs((cx - ax) * uy - (cy - ay) * ux) / la > 0.15:
            return False
        t0 = ((cx - ax) * ux + (cy - ay) * uy) / (la * la)
        t1 = ((dx - ax) * ux + (dy - ay) * uy) / (la * la)
        return (min(1.0, max(t0, t1)) - max(0.0, min(t0, t1))) * la > 0.5
    t = ((cx - ax) * vy - (cy - ay) * vx) / cross
    u = ((cx - ax) * uy - (cy - ay) * ux) / cross
    # Kontakty v koncových bodech bývají záměrné.
    margin_a = min(0.25 / la, 0.25)
    margin_b = min(0.25 / lb, 0.25)
    return margin_a < t < 1 - margin_a and margin_b < u < 1 - margin_b


def check(sheet: Sheet, dimensions: tuple[Annotation, ...]) -> CollisionReport:
    messages: list[str] = []
    complete = True
    if len(dimensions) > _MAX_DIMENSIONS:
        return CollisionReport(("Příliš mnoho kót pro úplnou kontrolu překrytí.",), False)
    boxes = {item.id: _text_box(item) for item in dimensions}
    mark = section_mark(sheet)
    for index, first in enumerate(dimensions):
        a = boxes[first.id]
        if a[1] < MARGIN + TITLE_HEIGHT:
            messages.append(f"Kóta {first.id}: text může zasahovat do popisového pole.")
        if (a[0] < MARGIN or a[1] < MARGIN or a[2] > sheet.width - MARGIN
                or a[3] > sheet.height - MARGIN):
            messages.append(f"Kóta {first.id}: text může přesahovat rámeček listu.")
        if mark is not None:
            text_hits_mark = any(_line_hits_box(line, a) for line in (mark.line, *mark.arrows))
            text_hits_label = any(_boxes_overlap(a, (x - 0.3, y - 0.6, x + 2.8, y + 3.0))
                                  for x, y in mark.labels)
            line_hits_mark = _line_collision(first.lines[-1], mark.line)
            if text_hits_mark or text_hits_label or line_hits_mark:
                messages.append(f"Kóta {first.id}: může se překrývat s označením řezu.")
        for second in dimensions[index + 1:]:
            b = boxes[second.id]
            if (_boxes_overlap(a, b)
                    or any(_line_hits_box(line, a) for line in second.lines)
                    or any(_line_hits_box(line, b) for line in first.lines)
                    or _line_collision(first.lines[-1], second.lines[-1])):
                messages.append(f"Kóty {first.id} a {second.id}: možné překrytí.")

    edge_count = sum(len(view.geometry.visible) + len(view.geometry.hidden)
                     + len(view.geometry.hatching) for view in sheet.views)
    if len(dimensions) * edge_count > _MAX_BOUNDING_CHECKS:
        messages.append("Geometrie je příliš složitá pro úplnou kontrolu překrytí.")
        return CollisionReport(tuple(messages[:_MAX_MESSAGES]), False)
    checks = 0
    for item in dimensions:
        rect = boxes[item.id]
        width, height = rect[2] - rect[0], rect[3] - rect[1]
        face = Face.make_rect(width, height, Plane(origin=((rect[0] + rect[2]) / 2,
                                                           (rect[1] + rect[3]) / 2, 0)))
        dimension_line = None
        if len(item.lines) == 3 and math.dist(*item.lines[-1]) > 1e-9:
            a, b = item.lines[-1]
            dimension_line = Edge.make_line((*a, 0), (*b, 0))
        hit = False
        for view in sheet.views:
            dx, dy = view.offset
            move = Location((dx, dy, 0))
            for edge in (*view.geometry.visible, *view.geometry.hidden, *view.geometry.hatching):
                bounds = edge.bounding_box()
                edge_box = (bounds.min.X + dx, bounds.min.Y + dy,
                            bounds.max.X + dx, bounds.max.Y + dy)
                if not _boxes_overlap(rect, (edge_box[0] - 1e-6, edge_box[1] - 1e-6,
                                             edge_box[2] + 1e-6, edge_box[3] + 1e-6)):
                    continue
                checks += 1
                if checks > _MAX_GEOMETRY_CHECKS:
                    complete = False
                    break
                if edge.moved(move).distance_to(face) <= 1e-6:
                    messages.append(f"Kóta {item.id}: text se může překrývat s geometrií.")
                    hit = True
                    break
            if hit or not complete:
                break
        if hit or not complete or dimension_line is None:
            if not complete:
                break
            continue
        for view in sheet.views:
            move = Location((*view.offset, 0))
            for edge in (*view.geometry.visible, *view.geometry.hidden):
                bounds = edge.bounding_box()
                dx, dy = view.offset
                edge_box = (bounds.min.X + dx - 1e-6, bounds.min.Y + dy - 1e-6,
                            bounds.max.X + dx + 1e-6, bounds.max.Y + dy + 1e-6)
                a, b = item.lines[-1]
                line_box = (min(a[0], b[0]) - 1e-6, min(a[1], b[1]) - 1e-6,
                            max(a[0], b[0]) + 1e-6, max(a[1], b[1]) + 1e-6)
                if not _boxes_overlap(line_box, edge_box):
                    continue
                checks += 1
                if checks > _MAX_GEOMETRY_CHECKS:
                    complete = False
                    break
                if edge.moved(move).distance_to(dimension_line) <= 1e-6:
                    messages.append(f"Kóta {item.id}: kótovací čára může křížit geometrii.")
                    hit = True
                    break
            if hit or not complete:
                break
        if not complete:
            break
    if not complete:
        messages.append("Geometrie je příliš složitá pro úplnou kontrolu překrytí.")
    if len(messages) > _MAX_MESSAGES:
        messages = messages[:_MAX_MESSAGES] + ["Další možná překrytí nejsou vypsaná."]
        complete = False
    return CollisionReport(tuple(messages), complete)
