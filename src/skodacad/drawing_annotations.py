"""Kóty pro pracovní náhled: 3D vazby se bezpečně promítnou do listu.

Nejde o exportní ani normový výkres. Nelze-li vazbu nebo pohled ověřit,
vrací se viditelné upozornění a žádná domnělá hodnota na listu.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from build123d import Edge, GeomType

from skodacad.document import Document
from skodacad.drawing_dimensions import _cylinders, _planes, evaluate
from skodacad.drawing_sheet import MARGIN, PlacedView, Sheet, section_key
from skodacad.measure import _surface_axis, inner_point
from skodacad.rebuild import BuildResult, model_signature

Point = tuple[float, float]
Line = tuple[Point, Point]
_AXES = {"front": ("x", "z"), "top": ("x", "y"), "right": ("y", "z")}
_DIRECTIONS = {"front": "y", "top": "z", "right": "x"}
_VIEW_NAMES = {"front": "zepředu", "top": "shora", "right": "zprava"}


@dataclass(frozen=True)
class Annotation:
    id: str
    view: str
    text: str
    lines: tuple[Line, ...]
    label: Point


@dataclass(frozen=True)
class AnnotationSet:
    items: tuple[Annotation, ...]
    warnings: tuple[str, ...]
    collisions: tuple[str, ...] = ()
    collision_check_complete: bool = True


def _project(point: Any, view: PlacedView, scale: float) -> Point:
    xaxis, yaxis = _AXES[view.name]
    return (getattr(point, xaxis.upper()) * scale + view.offset[0],
            getattr(point, yaxis.upper()) * scale + view.offset[1])


def _axis_for_cylinder(face: Any) -> tuple[str, Any]:
    center, direction = _surface_axis(face)
    coords = (direction.X, direction.Y, direction.Z)
    index = max(range(3), key=lambda i: abs(coords[i]))
    if abs(abs(coords[index]) - 1) > 1e-7:
        raise ValueError("Osa otvoru není rovnoběžná se základní osou.")
    return "xyz"[index], center


def _extreme_anchor(view: PlacedView, coordinate: float, horizontal: bool) -> Point:
    """Skutečný bod hrany s krajní souřadnicí, nikoli roh obálky ve vzduchu."""
    xmin, ymin, xmax, ymax = view.bounds
    dx, dy = view.offset
    if horizontal:
        edge = Edge.make_line((coordinate - dx, ymin - dy - 10, 0),
                              (coordinate - dx, ymax - dy + 10, 0))
    else:
        edge = Edge.make_line((xmin - dx - 10, coordinate - dy, 0),
                              (xmax - dx + 10, coordinate - dy, 0))
    candidates = [line.distance_to_with_closest_points(edge) for line in view.geometry.visible]
    distance, on_edge, _ = min(candidates, key=lambda item: item[0])
    if distance > 1e-5:
        raise ValueError("Krajní bod rozměru není v pohledu jednoznačně dostupný.")
    return (on_edge.X + dx, on_edge.Y + dy)


def _linear(did: str, text: str, view: PlacedView, first: Point, second: Point,
            horizontal: bool, side: str, offset: float) -> Annotation:
    xmin, ymin, xmax, ymax = view.bounds
    if horizontal:
        base = ymin if side == "low" else ymax
        line = base + (-offset if side == "low" else offset)
        p, q = (first[0], line), (second[0], line)
        lines = ((first, p), (second, q), (p, q))
        label = ((first[0] + second[0]) / 2, line + 1.5)
    else:
        base = xmin if side == "low" else xmax
        line = base + (-offset if side == "low" else offset)
        p, q = (line, first[1]), (line, second[1])
        lines = ((first, p), (second, q), (p, q))
        label = (line + 1.5, (first[1] + second[1]) / 2)
    return Annotation(did, view.name, text, lines, label)


def _fits(sheet: Sheet, annotation: Annotation) -> bool:
    points = [point for line in annotation.lines for point in line] + [annotation.label]
    return all(MARGIN <= x <= sheet.width - MARGIN and MARGIN <= y <= sheet.height - MARGIN
               for x, y in points)


def annotations(document: Document, result: BuildResult, sheet: Sheet) -> AnnotationSet:
    if (result.model_signature != sheet.model_signature
            or sheet.model_signature != model_signature(document)
            or sheet.section_key != section_key(document)):
        return AnnotationSet((), ("Náhled patří staršímu stavu modelu – vytvoř ho znovu.",))
    views = {view.name: view for view in sheet.views}
    items: list[Annotation] = []
    warnings: list[str] = []
    counts: dict[tuple[str, str, str], int] = {}
    for record in (document.drawing or {}).get("dimensions", []):
        did, kind = record["id"], record["kind"]
        value = evaluate(document, result, record)
        if value.value is None:
            warnings.append(f"Kóta {did}: {value.error}")
            continue
        try:
            axis = record.get("axis") if kind == "overall" else None
            face = None
            if kind == "distance":
                axis = record["a"]["normal"][1]
            elif kind in ("diameter", "radius"):
                face = _cylinders(document, result, record["origin"])[0]
                axis, center = _axis_for_cylinder(face)
            default_view = ({"x": "right", "y": "front", "z": "top"}[axis]
                            if face is not None else "top" if axis == "y" else "front")
            placement = record.get("placement") or {}
            name = placement.get("view", default_view)
            if "view" not in placement and name not in views:
                # Výchozí pohled je skrytý: kóta bez vlastního umístění jde do prvního
                # zobrazeného pohledu, kde ji lze nakreslit; hodnota se tím nemění.
                name = next((n for n in views if (_DIRECTIONS[n] == axis if face is not None
                                                  else axis in _AXES[n])), name)
            if name not in views:
                raise ValueError(f"Pohled {_VIEW_NAMES[name]} je na listu skrytý – zapni ho "
                                 "nebo kótu umísti do jiného pohledu.")
            view = views[name]
            if face is not None and _DIRECTIONS[name] != axis:
                raise ValueError("Otvor není v tomto pohledu vidět jako kružnice.")
            if face is None and axis not in _AXES[name]:
                raise ValueError("Směr kóty se do zvoleného pohledu nepromítá.")
            horizontal = face is None and _AXES[name][0] == axis
            side = placement.get("side", "low" if horizontal else "high")
            key = (name, "h" if horizontal else "v", side)
            default_offset = 6 + 6 * counts.get(key, 0)
            counts[key] = counts.get(key, 0) + 1
            offset = placement.get("offset", default_offset)
            label = f"{value.value:.9f}".rstrip("0").rstrip(".")
            if float(label) == 0 and value.value != 0:
                raise ValueError("Rozměr je příliš malý pro přesné zobrazení.")
            tolerance = record.get("tolerance")
            if tolerance is not None:
                def fmt(number: float) -> str:
                    return f"{number:.9f}".rstrip("0").rstrip(".") or "0"
                upper, lower = tolerance["upper"], tolerance["lower"]
                if value.value + lower < 0:
                    raise ValueError("Dolní mez rozměru je záporná; uprav toleranci.")
                if any(float(fmt(v)) != v for v in (upper, lower)):
                    raise ValueError("Odchylka má příliš mnoho desetinných míst pro zobrazení.")
                if upper == -lower:
                    label += " ±" + fmt(upper)
                else:
                    label += " +" + fmt(upper) + "/-" + fmt(-lower)
            if face is None:
                if kind == "overall":
                    box = result.part.bounding_box()
                    lower, upper = getattr(box.min, axis.upper()), getattr(box.max, axis.upper())
                    index = 0 if horizontal else 1
                    a = lower * sheet.scale + view.offset[index]
                    b = upper * sheet.scale + view.offset[index]
                    first = _extreme_anchor(view, a, horizontal)
                    second = _extreme_anchor(view, b, horizontal)
                else:
                    faces = [_planes(document, result, record[key])[0] for key in ("a", "b")]
                    first, second = (_project(inner_point(face), view, sheet.scale)
                                     for face in faces)
                annotation = _linear(did, label, view, first, second, horizontal, side, offset)
            else:
                cx, cy = _project(center, view, sheet.scale)
                radius = face.radius * sheet.scale
                matches = [edge for edge in view.geometry.visible
                           if edge.geom_type == GeomType.CIRCLE and edge.is_closed
                           and abs(edge.radius - radius) < 1e-6
                           and abs(edge.arc_center.X + view.offset[0] - cx) < 1e-6
                           and abs(edge.arc_center.Y + view.offset[1] - cy) < 1e-6]
                if len(matches) != 1:
                    raise ValueError("Otvor nemá v pohledu jednoznačný viditelný kruhový obrys.")
                sign = -1 if side == "low" else 1
                contact = (cx + sign * radius / math.sqrt(2), cy + radius / math.sqrt(2))
                end = (view.bounds[0] - offset if sign < 0 else view.bounds[2] + offset,
                       cy + radius + offset / 2)
                annotation = Annotation(did, name, ("Ø" if kind == "diameter" else "R") + label,
                                        ((contact, end),), end)
            if not _fits(sheet, annotation):
                raise ValueError("Kóta se nevejde na list; změň její umístění nebo měřítko.")
            items.append(annotation)
        except Exception as exc:  # noqa: BLE001 – nepodložená kóta se nesmí vykreslit jako platná
            warnings.append(f"Kóta {did}: {str(exc) or type(exc).__name__}")
    try:
        from skodacad.drawing_collisions import check

        report = check(sheet, tuple(items))
        return AnnotationSet(tuple(items), tuple(warnings), report.messages, report.complete)
    except Exception:  # noqa: BLE001 – neúspěšná kontrola se musí viditelně přiznat
        return AnnotationSet(tuple(items), tuple(warnings),
                             ("Kontrolu překrytí se nepodařilo dokončit.",), False)
