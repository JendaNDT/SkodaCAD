"""Řez modelem: díl se přesně rozřízne rovinou a ukáže se jen jedna polovina.

Řez je jen pohled – model se nemění. Rovina řezu je kolmá na osu X, Y nebo Z (poloha
posuvníkem), nebo rovnoběžná s vybranou rovinnou plochou (posuvník posouvá řez do hloubky
dílu). Plochy řezu jsou skutečné plochy rozříznutého dílu: jde na ně kliknout a měřit.
Obrys řezu jde uložit jako 2D výkres (DXF pro jiné CADy, SVG jako obrázek do protokolu).

Směr ``normal`` míří od plochy řezu ven – ke straně, která se odřízne (a odkud se na řez
díváme). Výchozí směry míří k pozorovateli v izometrii, takže je řez hned vidět.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from build123d import Box, Face, GeomType, Part, Plane, Pos, Vector

Point = tuple[float, float, float]

# Výchozí směr řezu kolmého na osu (k pozorovateli v izometrii zepředu-zprava-shora).
AXIS_NORMALS: dict[str, Point] = {"X": (1.0, 0.0, 0.0), "Y": (0.0, -1.0, 0.0),
                                  "Z": (0.0, 0.0, 1.0)}
AXIS_NAMES = {"X": "kolmo na osu X", "Y": "kolmo na osu Y", "Z": "kolmo na osu Z"}
_ON_PLANE = 1e-6


class SectionError(ValueError):
    """Řez nejde udělat (zpráva je česky pro uživatele)."""


@dataclass(frozen=True)
class SectionPlane:
    """Rovina řezu: bod na ní a směr ke straně, která se odřízne."""

    origin: Point
    normal: Point

    def plane(self) -> Plane:
        """Rovina build123d; osa X vodorovně (jako při pohledu na řez), u vodorovného řezu
        podél osy X dílu."""
        normal = Vector(*self.normal).normalized()
        x_dir = Vector(0, 0, 1).cross(normal)
        if x_dir.length < 1e-9:
            x_dir = Vector(1, 0, 0)
        return Plane(origin=self.origin, x_dir=x_dir.normalized(), z_dir=normal)

    def side(self, point: Point) -> float:
        """Vzdálenost bodu od roviny se znaménkem: kladná = odřízne se, záporná = zůstane."""
        n = Vector(*self.normal).normalized()
        return (Vector(*point) - Vector(*self.origin)).dot(n)


@dataclass(frozen=True)
class Section:
    """Rozříznutý díl: zbylá polovina a plochy řezu."""

    plane: SectionPlane
    part: Part  # co z dílu zbylo
    faces: list[Face]  # plochy řezu (leží v rovině řezu)

    @property
    def area(self) -> float:
        """Obsah plochy řezu [mm²] – průřez dílu v rovině řezu."""
        return sum(face.area for face in self.faces)


def axis_plane(axis: str, position: float, flipped: bool = False) -> SectionPlane:
    """Řez kolmo na osu ``axis`` (X, Y, Z) v souřadnici ``position`` [mm]."""
    if axis not in AXIS_NORMALS:
        raise SectionError(f"Neznámá osa řezu „{axis}“ – umím X, Y nebo Z.")
    normal = AXIS_NORMALS[axis]
    if flipped:
        normal = (-normal[0], -normal[1], -normal[2])
    index = "XYZ".index(axis)
    origin = tuple(float(position) if i == index else 0.0 for i in range(3))
    return SectionPlane(origin, normal)


def axis_range(part: Part, axis: str) -> tuple[float, float]:
    """Kde všude může být řez kolmý na osu (rozměr dílu v té ose) [mm]."""
    box = part.bounding_box()
    index = "XYZ".index(axis)
    return (box.min.X, box.min.Y, box.min.Z)[index], (box.max.X, box.max.Y, box.max.Z)[index]


def face_base(face: Face, point: Any = None) -> SectionPlane:
    """Rovina rovinné plochy ``face`` (bod na ní a směr ven) – základ řezu rovnoběžně s ní."""
    if face.geom_type != GeomType.PLANE:
        raise SectionError("Řez jde vést jen rovnoběžně s rovinnou plochou – vybraná plocha "
                           "je zakřivená.")
    at = Vector(*point) if point is not None else face.center()
    return SectionPlane(_tuple(at), _tuple(face.normal_at(at)))


def offset_plane(base: SectionPlane, depth: float, flipped: bool = False) -> SectionPlane:
    """Řez rovnoběžně s plochou ``base`` ve hloubce ``depth`` mm pod ní.

    Odřízne se materiál mezi plochou a řezem (díváme se do dílu), s ``flipped`` naopak
    zbude jen ta vrstva pod plochou.
    """
    normal = Vector(*base.normal).normalized()
    origin = Vector(*base.origin) - normal * float(depth)
    return SectionPlane(_tuple(origin), _tuple(-normal if flipped else normal))


def face_plane(face: Face, depth: float, flipped: bool = False,
               point: Any = None) -> SectionPlane:
    """Řez rovnoběžně s rovinnou plochou ``face`` ve hloubce ``depth`` mm pod ní."""
    return offset_plane(face_base(face, point), depth, flipped)


def base_depth_range(part: Part, base: SectionPlane) -> tuple[float, float]:
    """Jak hluboko pod plochu může řez jít (0 = na ploše, až po druhý konec dílu) [mm]."""
    at, normal = Vector(*base.origin), Vector(*base.normal).normalized()
    box = part.bounding_box()
    corners = [Vector(x, y, z) for x in (box.min.X, box.max.X) for y in (box.min.Y, box.max.Y)
               for z in (box.min.Z, box.max.Z)]
    return 0.0, max(0.0, max((at - corner).dot(normal) for corner in corners))


def depth_range(part: Part, face: Face, point: Any = None) -> tuple[float, float]:
    """Jak hluboko pod plochu ``face`` může řez jít [mm]."""
    return base_depth_range(part, face_base(face, point))


def cut(part: Part | None, plane: SectionPlane) -> Section:
    """Rozřízne díl rovinou; zbude strana proti směru ``plane.normal``."""
    if part is None:
        raise SectionError("Řez potřebuje díl – model zatím nemá těleso.")
    box = part.bounding_box()
    size = 2 * box.diagonal + 2 * (Vector(*plane.origin) - box.center()).length + 1
    cutter = plane.plane().location * Pos(0, 0, size / 2) * Box(size, size, size)
    try:
        kept = part - cutter
    except Exception as exc:  # noqa: BLE001 – chyba jádra nesmí shodit okno
        raise SectionError(f"Řez se nepodařilo spočítat ({type(exc).__name__}). Zkus rovinu "
                           "kousek posunout.") from None
    volume = kept.volume if kept is not None and kept.solids() else 0.0
    if volume < 1e-9 * max(1.0, part.volume):
        raise SectionError("Rovina řezu odřízla celý díl – posuň ji do dílu nebo otoč stranu.")
    if abs(volume - part.volume) < 1e-9 * max(1.0, part.volume):
        raise SectionError("Rovina řezu díl míjí – nic se neodřízlo. Posuň ji do dílu.")
    normal = Vector(*plane.normal).normalized()
    faces = [face for face in kept.faces() if face.geom_type == GeomType.PLANE
             and face.normal_at().dot(normal) > 1 - 1e-6
             and abs(plane.side(_tuple(face.center()))) < _ON_PLANE * max(1.0, size)]
    return Section(plane, kept, faces)


def clip_mesh(nodes: list[Point], triangles: list[tuple[int, int, int]], colors: list[Any],
              plane: SectionPlane) -> tuple[list[Point], list[tuple[int, int, int]], list[Any]]:
    """Síť (mapa tloušťky) oříznutá rovinou řezu: trojúhelníky přes rovinu se rozdělí přesně
    na ní (nové uzly s dopočtenou polohou i barvou), takže okraj mapy je rovný."""
    normal = Vector(*plane.normal).normalized()
    ox, oy, oz = plane.origin
    side = [(x - ox) * normal.X + (y - oy) * normal.Y + (z - oz) * normal.Z
            for x, y, z in nodes]
    nodes, colors = list(nodes), list(colors)
    cache: dict[tuple[int, int], int] = {}

    def crossing(i: int, j: int) -> int:
        key = (i, j) if i < j else (j, i)
        if key not in cache:
            t = side[i] / (side[i] - side[j])
            nodes.append(tuple(a + (b - a) * t for a, b in zip(nodes[i], nodes[j],
                                                                 strict=True)))
            colors.append(tuple(a + (b - a) * t for a, b in zip(colors[i], colors[j],
                                                                  strict=True)))
            cache[key] = len(nodes) - 1
        return cache[key]

    kept: list[tuple[int, int, int]] = []
    for tri in triangles:
        inside = [side[i] <= 1e-9 for i in tri]
        if all(inside):
            kept.append(tri)
            continue
        if not any(inside):
            continue
        polygon = []  # Sutherland–Hodgman pro jednu rovinu, pořadí (orientace) zůstane
        for k in range(3):
            current, following = tri[k], tri[(k + 1) % 3]
            if inside[k]:
                polygon.append(current)
            if inside[k] != inside[(k + 1) % 3]:
                polygon.append(crossing(current, following))
        kept += [(polygon[0], polygon[i], polygon[i + 1]) for i in range(1, len(polygon) - 1)]
    return nodes, kept, colors


def export_2d(section: Section, path: str | Path) -> Path:
    """Obrys řezu jako 2D výkres v souřadnicích roviny řezu: ``.dxf`` nebo ``.svg``."""
    from build123d import ExportDXF, ExportSVG

    path = Path(path)
    if not section.faces:
        raise SectionError("Řez nemá žádnou plochu – není co uložit.")
    plane = section.plane.plane()
    flat = [plane.to_local_coords(face) for face in section.faces]
    suffix = path.suffix.lower()
    if suffix == ".dxf":
        exporter = ExportDXF()
        exporter.add_layer("rez")
        exporter.add_shape(flat, layer="rez")
        exporter.write(path)
    elif suffix == ".svg":
        exporter = ExportSVG(margin=2, line_weight=0.25)
        exporter.add_layer("rez", fill_color=(0.92, 0.63, 0.57), line_color=(0.15, 0.15, 0.15),
                           line_weight=0.25)
        exporter.add_shape(flat, layer="rez")
        exporter.write(path)
    else:
        raise SectionError(f"Řez umím uložit jako .dxf nebo .svg, ne „{path.suffix}“.")
    return path


def describe(plane: SectionPlane) -> str:
    """Rovina řezu česky, např. „X = 12.50 mm“ nebo „rovnoběžně s plochou“."""
    from skodacad.inspection import number

    n = Vector(*plane.normal).normalized()
    for axis, index in (("X", 0), ("Y", 1), ("Z", 2)):
        if abs(abs((n.X, n.Y, n.Z)[index]) - 1) < 1e-9:
            return f"{axis} = {number(plane.origin[index])} mm"
    return "rovnoběžně s vybranou plochou"


def _tuple(vector: Vector) -> Point:
    return (vector.X, vector.Y, vector.Z)

