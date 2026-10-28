"""Označení roviny řezu a směru pohledu v odpovídajícím pohledu na listu."""
from __future__ import annotations

from dataclasses import dataclass

from skodacad.document import DocumentError
from skodacad.drawing_sheet import MARGIN, Sheet
from skodacad.section import AXIS_NORMALS

Point = tuple[float, float]
Line = tuple[Point, Point]


@dataclass(frozen=True)
class SectionMark:
    line: Line
    arrows: tuple[Line, ...]
    labels: tuple[Point, Point]


def section_mark(sheet: Sheet) -> SectionMark | None:
    if sheet.section_key is None:
        return None
    axis, position, flipped = sheet.section_key
    source = "front" if axis == "Z" else "top"
    view = next((v for v in sheet.views if v.name == source), None)
    if view is None:
        raise DocumentError("Pro označení roviny řezu chybí odpovídající pohled.")
    xmin, ymin, xmax, ymax = view.bounds
    normal = AXIS_NORMALS[axis]["XYZ".index(axis)]
    direction = normal if flipped else -normal  # šipka do ponechané části tělesa
    if axis == "X":
        x = position * sheet.scale + view.offset[0]
        first, last = (x, ymin - 3), (x, ymax + 3)
        targets = ((x + direction * 4, first[1]), (x + direction * 4, last[1]))
        labels = ((first[0] + 1, first[1] - 3), (last[0] + 1, last[1] + 1))
        wings = ((-direction * 1.2, -0.7), (-direction * 1.2, 0.7))
    else:
        y = position * sheet.scale + view.offset[1]
        first, last = (xmin - 3, y), (xmax + 3, y)
        targets = ((first[0], y + direction * 4), (last[0], y + direction * 4))
        labels = ((first[0] - 3, first[1] + 1), (last[0] + 1, last[1] + 1))
        wings = ((-0.7, -direction * 1.2), (0.7, -direction * 1.2))
    arrows: list[Line] = []
    for start, target in zip((first, last), targets, strict=True):
        arrows.append((start, target))
        arrows.extend((target, (target[0] + dx, target[1] + dy)) for dx, dy in wings)
    points = [first, last, *targets, *labels, *(p for line in arrows for p in line)]
    if not all(MARGIN <= x <= sheet.width - MARGIN and MARGIN <= y <= sheet.height - MARGIN
               for x, y in points):
        raise DocumentError("Označení řezu se nevejde na list – změň měřítko nebo list.")
    if any(x + 2.5 > sheet.width - MARGIN or y + 2.5 > sheet.height - MARGIN
           for x, y in labels):
        raise DocumentError("Popisek řezu se nevejde na list – změň měřítko nebo list.")
    return SectionMark((first, last), tuple(arrows), labels)
