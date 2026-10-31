"""Dodatečné geometrické pojistky výslovného normálového loftu.

Vzorkování není důkaz globální konstantní tloušťky. Zachytí mimo jiné platně
vypadající obrácené offsety kužele, které projdou kontrolou samotného objemu.
NDT měřidlo s filtrem protější stěny se zde nepoužívá ani nemění.
"""

from build123d import GeomType, Part, Vertex
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector


def check_normal_wall(original: Part, candidate: Part, openings: list, wall: float) -> None:
    """Ponechaný povrch, otevřená čela, normálové paprsky a vzdálenost vnitřní stěny."""
    body, = candidate.solids()  # počet předem ověřil P1
    sides = [f for f in original.faces() if not any(f.is_same(end) for end in openings)]
    tolerance = max(2e-5, wall * 1e-6)
    step = min(1e-5, wall / 10)
    ray = IntCurvesFace_ShapeIntersector()
    ray.Load(candidate.wrapped, 1e-7)
    for face in sides:
        measured = 0
        for u in (0.2, 0.5, 0.8):
            for v in (0.2, 0.5, 0.8):
                point = face.position_at(u, v)
                if not face.is_inside(point):
                    continue
                if min(e.distance_to(point) for e in face.edges()) < 1e-4:
                    continue
                normal = face.normal_at(point)
                if (not body.is_inside(point - normal * step)
                        or body.is_inside(point + normal * step)):
                    raise ValueError("offset nezachoval vnější stěnu")
                ray.Perform(gp_Lin(gp_Pnt(*point), gp_Dir(*(-normal))), 1e-6, 1e9)
                distances = [ray.WParameter(i) for i in range(1, ray.NbPnt() + 1)
                             if ray.WParameter(i) > 1e-6]
                if not distances or min(distances) < wall - tolerance:
                    raise ValueError("normálový průchod materiálem je kratší než zadaná stěna")
                measured += 1
        if measured == 0:
            raise ValueError("vnější stěnu nelze v kontrolních bodech ověřit")
    for end in openings:
        # Musí existovat alespoň jeden ověřený průchod otvorem do dutiny.
        normal = end.normal_at()
        if not any(end.is_inside(p := end.position_at(u, v))
                   and not body.is_inside(p - normal * step)
                   for u in (0.2, 0.5, 0.8) for v in (0.2, 0.5, 0.8)):
            raise ValueError("čelo přechodu není prokazatelně otevřené")
    interior_found = False
    for face in candidate.faces():
        if face.geom_type == GeomType.PLANE and any(
                abs(abs(face.normal_at().dot(end.normal_at())) - 1) < 1e-6
                and abs((face.center() - end.center()).dot(end.normal_at())) < 1e-6
                for end in openings):
            continue  # čelní prstenec mezi vnější a vnitřní stěnou
        points = [p for u in (0, 0.5, 1) for v in (0, 0.5, 1)
                  if face.is_inside(p := face.position_at(u, v))]
        if not points:
            raise ValueError("plochu přechodu nelze ověřit")
        distances = [min(side.distance_to(Vertex(p)) for side in sides) for p in points]
        if all(d < 1e-6 for d in distances):
            continue  # zachovaný vnější povrch
        interior_found = True
        if min(distances) < wall - tolerance:
            raise ValueError("vnitřní offset se obrátil nebo přiblížil k vnějšímu povrchu")
    if not interior_found:
        raise ValueError("nebyla nalezena ověřitelná vnitřní stěna")
