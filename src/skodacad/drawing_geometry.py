"""P4.2: přesná geometrie ortogonálních pohledů a rovinného řezu.

Souřadnice vrácených hran jsou v mm na listu. Nejde o hotový výkres,
ukládání pohledů ani doklad o souladu s výkresovou normou.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Compound, Edge, Part, Vector
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepLib import BRepLib

from skodacad.geometry_validation import GeometryValidationError, inspect_volume
from skodacad.section import SectionError, SectionPlane, axis_plane, cut


class DrawingGeometryError(ValueError):
    """Pohled nebo řez nelze bezpečně vypočítat."""


@dataclass(frozen=True)
class DrawingView:
    """Projekce na list: plné hrany, skryté hrany a čáry šrafování."""

    visible: tuple[Edge, ...]
    hidden: tuple[Edge, ...]
    hatching: tuple[Edge, ...] = ()


# Směr k pozorovateli a směr nahoru na listu odpovídají prohlížeči.
_VIEWS = {
    "front": ((0, -1, 0), (0, 0, 1)),
    "top": ((0, 0, 1), (0, 1, 0)),
    "right": ((1, 0, 0), (0, 0, 1)),
}
_MAX_HATCH_LINES = 2000
_MAX_HATCH_INTERSECTIONS = 20000
_MAX_EDGE_COMPARISONS = 50000


def _validate(part: Part | None, scale: float) -> None:
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale):
        raise DrawingGeometryError("Měřítko musí být kladné konečné číslo.")
    if scale <= 0:
        raise DrawingGeometryError("Měřítko musí být kladné konečné číslo.")
    try:
        facts = inspect_volume(part)
    except (GeometryValidationError, ValueError, TypeError) as exc:
        raise DrawingGeometryError(f"Pohled potřebuje platný objemový díl: {exc}") from exc
    if facts.solids != 1:
        raise DrawingGeometryError("Pohled zatím podporuje právě jedno těleso.")


def _with_regularity(part: Part) -> Compound:
    """Kopie dílu se zapsanou plynulostí hran pro skrývání čar.

    Bez ní OCCT bere šev válce, kužele či koule a hranu mezi dvěma částmi téže
    hladké plochy (navazující stejná díra) jako ostrou hranu a nakreslí čáru,
    která na dílu není. Hladké hrany (C2 a víc) se pak nekreslí, tečné (zaoblení)
    a ostré zůstávají. Kopie topologie: originál sdílí okno, jeho hrany se nemění.
    """
    copy = BRepBuilderAPI_Copy(part.wrapped, False).Shape()
    BRepLib.EncodeRegularity_s(copy)
    return Compound(copy)


def _project(part: Part, direction: Vector, up: Vector, anchor: Vector,
             scale: float) -> DrawingView:
    box = part.bounding_box()
    distance = max(1.0, box.diagonal * 4 + (box.center() - anchor).length)
    try:
        visible, hidden = _with_regularity(part).project_to_viewport(
            anchor + direction * distance, viewport_up=up, look_at=anchor
        )
        if not visible:
            raise DrawingGeometryError("Pohled neobsahuje žádné viditelné hrany.")
        hidden = _remove_visible_from_hidden(visible, hidden)
        return DrawingView(tuple(edge.scale(scale) for edge in visible),
                           tuple(edge.scale(scale) for edge in hidden))
    except DrawingGeometryError:
        raise
    except Exception as exc:  # noqa: BLE001 -- selhání jádra je nutné oznámit
        raise DrawingGeometryError(
            f"Pohled se nepodařilo vypočítat ({type(exc).__name__})."
        ) from exc


def _remove_visible_from_hidden(visible, hidden) -> tuple[Edge, ...]:
    """Viditelná hrana překryje shodnou část skryté, zbytek skryté zůstane."""
    if len(visible) * len(hidden) > _MAX_EDGE_COMPARISONS:
        raise DrawingGeometryError("Pohled má příliš mnoho hran pro bezpečné zpracování.")
    remaining = []
    for edge in hidden:
        difference = edge.cut(*visible)
        if difference is not None:
            remaining.extend(piece for piece in difference.edges() if piece.length > 1e-8)
    return tuple(remaining)


def project_view(part: Part | None, view: str, scale: float = 1.0) -> DrawingView:
    """Zepředu, shora nebo zprava; měřítko 1:2 se zadává jako 0,5."""
    _validate(part, scale)
    if view not in _VIEWS:
        raise DrawingGeometryError("Neznámý pohled; zvol zepředu, shora nebo zprava.")
    direction, up = _VIEWS[view]
    return _project(part, Vector(*direction), Vector(*up), Vector(0, 0, 0), scale)


def _hatch(faces, plane: SectionPlane, scale: float, spacing_mm: float) -> tuple[Edge, ...]:
    if (isinstance(spacing_mm, bool) or not isinstance(spacing_mm, (int, float))
            or not math.isfinite(spacing_mm) or spacing_mm <= 0):
        raise DrawingGeometryError("Rozteč šraf musí být kladné konečné číslo.")
    frame = plane.plane()
    flat = [frame.to_local_coords(face) for face in faces]
    if not flat:
        raise DrawingGeometryError("Řez nemá průřezovou plochu pro šrafování.")
    spacing = spacing_mm / scale
    if not math.isfinite(spacing) or spacing <= 0:
        raise DrawingGeometryError("Měřítko a rozteč šraf jsou mimo podporovaný rozsah.")
    boxes = [face.bounding_box() for face in flat]
    xmin = min(b.min.X for b in boxes)
    xmax = max(b.max.X for b in boxes)
    ymin = min(b.min.Y for b in boxes)
    ymax = max(b.max.Y for b in boxes)
    # Přímky y = x + k; vzdálenost sousedních čar na listu je spacing_mm.
    step = spacing * math.sqrt(2)
    if not math.isfinite(step) or step <= 0:
        raise DrawingGeometryError("Měřítko a rozteč šraf jsou mimo podporovaný rozsah.")
    first = math.floor((ymin - xmax) / step) - 1
    last = math.ceil((ymax - xmin) / step) + 1
    if last - first + 1 > _MAX_HATCH_LINES:
        raise DrawingGeometryError("Řez má příliš mnoho šraf; zvětši jejich rozteč.")
    if (last - first + 1) * len(flat) > _MAX_HATCH_INTERSECTIONS:
        raise DrawingGeometryError("Řez je pro šrafování příliš složitý; zvětši rozteč šraf.")
    margin = max(xmax - xmin, ymax - ymin, 1.0)
    lines = []
    try:
        for index in range(first, last + 1):
            k = index * step
            line = Edge.make_line((xmin - margin, xmin - margin + k, 0),
                                  (xmax + margin, xmax + margin + k, 0))
            for face in flat:
                clipped = face.intersect(line)
                if clipped is not None:
                    lines.extend(edge.scale(scale) for edge in clipped.edges()
                                 if edge.length > 1e-8)
    except Exception as exc:  # noqa: BLE001 -- neúplné šrafování se nesmí vrátit jako hotové
        raise DrawingGeometryError(f"Šrafování řezu selhalo ({type(exc).__name__}).") from exc
    return tuple(lines)


def project_section(part: Part | None, axis: str, position: float, *, flipped: bool = False,
                    scale: float = 1.0, hatch_spacing_mm: float = 3.0) -> DrawingView:
    """Úplný řez osovou rovinou: průřez, hrany za řezem a šrafy na listu."""
    _validate(part, scale)
    if (isinstance(position, bool) or not isinstance(position, (int, float))
            or not math.isfinite(position)):
        raise DrawingGeometryError("Poloha řezu musí být konečné číslo v mm.")
    try:
        plane = axis_plane(axis, position, flipped=flipped)
        section = cut(part, plane)
        frame = plane.plane()
        result = _project(section.part, frame.z_dir, frame.y_dir, Vector(*plane.origin), scale)
        return DrawingView(result.visible, result.hidden,
                           _hatch(section.faces, plane, scale, hatch_spacing_mm))
    except SectionError as exc:
        raise DrawingGeometryError(str(exc)) from exc
