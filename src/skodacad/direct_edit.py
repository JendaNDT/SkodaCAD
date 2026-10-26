"""Přímé úpravy plochy (P2): posunutí rovinné plochy a změna průměru válcové plochy.

Schválené rozhodnutí P2.1 (G1–G8) a P2.2 (H1–H8), návrhy
`docs/p2-1-navrh-rozsahu-primeho-modelovani.md` a `docs/p2-2-navrh-zapisu-prime-upravy.md`.

Úprava mění hotový díl jádrem OCCT (`BRepOffset_MakeOffset` s posunem jen vybrané plochy;
sousední plochy se prodlouží nebo zkrátí). Jádro v průzkumu tiše pustilo tři chybné
výsledky (plocha z jiného tělesa, zaniklé sražení, rozbitá tečnost zaoblení), proto
výsledek prochází kontrolami G5 a vstup kontrolami G6. Nic se neopravuje ani nezkouší
s větší tolerancí – buď celý výsledek projde, nebo se odmítne českou chybou.

Pojistka původu (H3): plocha si pamatuje id prvku, od kterého v místě odkazu na díle
nepřetržitě existuje. Při přepočtu se původ spočítá znovu a musí souhlasit.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from build123d import Compound, Face, GeomType, Part, Solid, Vector, Vertex
from OCP.BRep import BRep_Tool
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepOffset import BRepOffset_MakeOffset, BRepOffset_Skin
from OCP.GeomAbs import GeomAbs_C0, GeomAbs_Intersection

from skodacad.geometry_validation import (
    GeometryValidationError,
    VolumeFacts,
    check_modification,
    inspect_volume,
    volume_tolerance,
)

ON_FACE = 1e-6  # mm – bod leží na ploše (jako picking._ON_FACE)
LENGTH = 1e-6  # mm – εL z P1.1: poloha upravené plochy
MIN_FACE_AREA = 1e-6  # mm² – plocha s menší výměrou = zaniklý soused (G5)
TANGENT_DEGREES = 1.0  # sousedé s menším úhlem normál navazují tečně (G6)
_NORMAL = 1e-6  # shoda směrů normál

History = Sequence[tuple[str, Part | None]]  # (id prvku, díl po něm) v pořadí receptu


class DirectEditError(ValueError):
    """Úpravu nejde provést – zpráva je česky pro uživatele."""


# --- původ plochy (H3) ---------------------------------------------------------------------


def _carrier(face: Face, other: Face) -> bool:
    from skodacad.picking import _same_surface

    return _same_surface(other, face)


def present(part: Part | None, face: Face, point: Vector) -> bool:
    """Má díl v bodě ``point`` plochu se stejnou nosnou geometrií i orientací jako ``face``?"""
    if part is None:
        return False
    normal = face.normal_at(point)
    for other in part.faces():
        if not _carrier(face, other):
            continue
        distance, on_other, _ = other.distance_to_with_closest_points(Vertex(point))
        if distance <= ON_FACE and other.normal_at(on_other).dot(normal) > 1 - _NORMAL:
            return True
    return False


def face_origin(history: History, face: Face, point: Vector) -> str | None:
    """Id prvku, od kterého plocha v bodě nepřetržitě existuje (hledá se odzadu)."""
    found = None
    for feature_id, part in reversed(history):
        if not present(part, face, point):
            break
        found = feature_id
    return found


def check_origin(history: History, face: Face, point: Vector, stored: object,
                 label: str) -> None:
    """Pojistka H3/H4: uložený původ musí existovat a souhlasit s nalezenou plochou."""
    if not isinstance(stored, str) or not stored:
        raise DirectEditError(
            f"{label}: chybí původ plochy („origin“) – vyber plochu znovu ve 3D, aby šlo "
            "ověřit, že se upravuje ta správná.")
    if stored not in {feature_id for feature_id, _ in history}:
        raise DirectEditError(
            f"{label}: plocha měla vzniknout prvkem „{stored}“, ten ale před touto úpravou "
            "není (smazaný, přesunutý nebo s chybou) – vyber plochu znovu.")
    actual = face_origin(history, face, point)
    if actual != stored:
        source = f"z prvku „{actual}“" if actual else "z neznámého prvku"
        raise DirectEditError(
            f"{label}: nalezená plocha teď pochází {source}, úprava byla zadaná na plochu "
            f"z prvku „{stored}“. Dřívější změna ji nejspíš odstranila nebo posunula – "
            "vyber plochu znovu.")


# --- kontroly vstupu (G6) --------------------------------------------------------------


def _owner(part: Part, face: Face) -> tuple[Solid, list[Solid]]:
    solids = list(part.solids())
    for index, solid in enumerate(solids):
        if any(face.is_same(own) for own in solid.faces()):
            return solid, solids[:index] + solids[index + 1:]
    raise DirectEditError("Vybraná plocha nepatří k aktuálnímu dílu – vyber ji znovu.")


def tangent_neighbours(solid: Solid, face: Face) -> int:
    """Počet hran plochy, kde soused navazuje hladce (tečně nebo spojitě jako závit)."""
    count = 0
    for edge in face.edges():
        middle = edge.position_at(0.5)
        for other in solid.faces():
            if other.is_same(face) or not any(e.is_same(edge) for e in other.edges()):
                continue
            smooth = (BRep_Tool.HasContinuity_s(edge.wrapped, face.wrapped, other.wrapped)
                      and BRep_Tool.Continuity_s(edge.wrapped, face.wrapped, other.wrapped)
                      != GeomAbs_C0)
            angle = math.degrees(face.normal_at(middle).get_angle(other.normal_at(middle)))
            if smooth or angle < TANGENT_DEGREES:
                count += 1
    return count


def _check_input(solid: Solid, face: Face, kind: GeomType, label: str) -> None:
    names = {GeomType.PLANE: "rovinnou", GeomType.CYLINDER: "válcovou"}
    if face.geom_type != kind:
        raise DirectEditError(f"{label} umí jen {names[kind]} plochu – vybraná plocha je jiná "
                              "(kužel, koule, obecná plocha z tažení nebo přechodu).")
    if tangent_neighbours(solid, face):
        raise DirectEditError(
            f"{label}: na plochu hladce navazuje soused (zaoblení nebo plošky vymodelovaného "
            "závitu). Takovou plochu první verze přímých úprav neumí – uprav prvek, který ji "
            "vytvořil, nebo zaoblení přesuň ve stromu až za úpravu.")


# --- výpočet a kontroly výsledku (G5) ------------------------------------------------------


def _offset(solid: Solid, face: Face, distance: float, label: str) -> Solid:
    maker = BRepOffset_MakeOffset()
    # Vstupem musí být jedno těleso – se složeninou vrátí jádro jen skořápku (průzkum P2.1).
    maker.Initialize(solid.wrapped, 0.0, 1e-7, BRepOffset_Skin, False, False,
                     GeomAbs_Intersection, False, False)
    maker.SetOffsetOnFace(face.wrapped, distance)
    try:
        maker.MakeOffsetShape()
        shape = maker.Shape() if maker.IsDone() else None
    except Exception:  # noqa: BLE001 – selhání jádra = odmítnutí, ne pád
        shape = None
    if shape is None or shape.IsNull() or not BRepCheck_Analyzer(shape).IsValid():
        raise DirectEditError(
            f"{label}: úpravu nejde spočítat – sousední plocha by zanikla, plocha by "
            "splynula s jinou nebo by vnikla do jiné části tělesa. Zkus menší hodnotu.")
    return Solid(shape)


def _assemble(edited: Solid, others: list[Solid]) -> Part:
    return Part(Compound([*others, edited]).wrapped)


def _check_result(before_part: Part, before: VolumeFacts, result: Part, label: str) -> None:
    try:
        facts = inspect_volume(result)
        check_modification(before, facts)
    except GeometryValidationError as exc:
        raise DirectEditError(f"{label}: {exc}") from None
    if len(result.faces()) != len(before_part.faces()):
        raise DirectEditError(
            f"{label}: úprava by změnila počet ploch dílu ({len(before_part.faces())} → "
            f"{len(result.faces())}) – nějaká plocha by zanikla nebo vznikla. Zkus menší "
            "hodnotu.")
    smallest = min(face.area for face in result.faces())
    if smallest <= MIN_FACE_AREA:
        raise DirectEditError(
            f"{label}: sousední plocha by zanikla (zůstala by s nulovou výměrou, např. "
            "sražení). Zkus menší hodnotu.")
    if abs(facts.volume - before.volume) <= volume_tolerance(before.volume, facts.volume):
        raise DirectEditError(f"{label}: úprava nemá rozlišitelný účinek na objem.")


def _has_plane(part: Part, normal: Vector, point: Vector) -> bool:
    return any(face.geom_type == GeomType.PLANE
               and face.normal_at().dot(normal) > 1 - _NORMAL
               and abs((face.center() - point).dot(normal)) <= LENGTH
               for face in part.faces())


def _cylinder_radius(face: Face) -> float:
    """Poloměr válce přes adaptér plochy – `Face.radius` u kopie z pole vrací None."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    return BRepAdaptor_Surface(face.wrapped).Cylinder().Radius()


def _cylinder_axis(face: Face) -> tuple[Vector, Vector]:
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    axis = BRepAdaptor_Surface(face.wrapped).Cylinder().Axis()
    location, direction = axis.Location(), axis.Direction()
    return (Vector(location.X(), location.Y(), location.Z()),
            Vector(direction.X(), direction.Y(), direction.Z()))


def _has_cylinder(part: Part, origin: Vector, direction: Vector, radius: float) -> bool:
    for face in part.faces():
        if face.geom_type != GeomType.CYLINDER:
            continue
        if abs(_cylinder_radius(face) - radius) > LENGTH * max(1.0, radius):
            continue
        location, axis = _cylinder_axis(face)
        if (abs(axis.dot(direction)) >= 1 - _NORMAL
                and (location - origin).cross(direction).length <= LENGTH):
            return True
    return False


def move_face(part: Part, face: Face, point: Vector, distance: float,
              label: str = "Posunutí plochy") -> Part:
    """Posune rovinnou plochu ``face`` o ``distance`` mm po vnější normále (+ přidá)."""
    if not math.isfinite(distance) or distance == 0:
        raise DirectEditError(f"{label}: posun musí být konečné číslo různé od 0 – "
                              "úprava jinak nic nemění.")
    solid, others = _owner(part, face)
    _check_input(solid, face, GeomType.PLANE, label)
    normal = face.normal_at(point)
    before = inspect_volume(part)
    result = _assemble(_offset(solid, face, distance, label), others)
    _check_result(part, before, result, label)
    if not _has_plane(result, normal, point + normal * distance):
        raise DirectEditError(f"{label}: upravená plocha není na požadovaném místě – "
                              "výsledek jádra nejde přijmout.")
    return result


def set_diameter(part: Part, face: Face, point: Vector, diameter: float,
                 label: str = "Průměr plochy") -> Part:
    """Změní průměr válcové plochy (díra i čep) na ``diameter`` mm; osa zůstane."""
    if not math.isfinite(diameter) or diameter <= 0:
        raise DirectEditError(f"{label}: průměr musí být kladné konečné číslo "
                              f"(je {diameter:g}).")
    solid, others = _owner(part, face)
    _check_input(solid, face, GeomType.CYLINDER, label)
    radius, new_radius = _cylinder_radius(face), diameter / 2
    if abs(new_radius - radius) <= LENGTH * max(1.0, radius):
        raise DirectEditError(f"{label}: průměr už je Ø{diameter:g} – úprava nic nemění.")
    location, direction = _cylinder_axis(face)
    radial = (point - location) - direction * (point - location).dot(direction)
    convex = face.normal_at(point).dot(radial) > 0  # čep: normála míří od osy
    distance = new_radius - radius if convex else radius - new_radius
    before = inspect_volume(part)
    result = _assemble(_offset(solid, face, distance, label), others)
    _check_result(part, before, result, label)
    if not _has_cylinder(result, location, direction, new_radius):
        raise DirectEditError(f"{label}: upravená plocha nemá požadovaný průměr – "
                              "výsledek jádra nejde přijmout.")
    return result
