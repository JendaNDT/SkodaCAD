"""Společné geometrické jádro NDT (etapa 02) – výsledky proti ručním výpočtům.

Hraniční případy (paprsek po povrchu, přes hranu, tečně) musí být „nejisté“ a nikdy se
nesmí započítat jako materiál – žádná tichá falešná kladná odpověď.
"""

import math
import time

import pytest
from build123d import Box, Pos, Sphere

from conftest import EXAMPLES
from skodacad import Document, rebuild
from skodacad.ndt.geometry import (
    ALONG_SURFACE,
    GRAZING,
    ON_EDGE,
    THROUGH_EDGE,
    GeometryError,
    PartGeometry,
)

NDT = EXAMPLES / "ndt"
S2 = math.sqrt(2)


def geometry(name, **overrides):
    result = rebuild(Document.load(NDT / f"{name}.json"), overrides or None)
    return PartGeometry(result.part)


def lengths(ray):
    return [pytest.approx(s.length) for s in ray.segments]


# --- paprsek -------------------------------------------------------------------------------


def test_plate_straight_and_angled():
    plate = geometry("deska")
    ray = plate.cast((30, 10, 50), (0, 0, -1))
    assert ray.certain and len(ray.segments) == 1
    [segment] = ray.segments
    assert (segment.start, segment.end) == (pytest.approx(30), pytest.approx(50))
    assert segment.entry.incidence == pytest.approx(0) and segment.entry.entering
    assert segment.entry.normal == pytest.approx((0, 0, 1))
    assert segment.exit.normal == pytest.approx((0, 0, -1)) and not segment.exit.entering
    assert ray.material_length == pytest.approx(20)
    angled = plate.cast((0, 0, 20), (1, 0, -1))  # z horní plochy pod 45°
    assert angled.material_length == pytest.approx(20 * S2)
    assert angled.segments[0].entry.incidence == pytest.approx(45)
    assert angled.segments[0].exit.point == pytest.approx((20, 0, 0))  # půlkrok 20 mm
    thicker = geometry("deska", t=30).cast((30, 10, 50), (0, 0, -1))
    assert thicker.material_length == pytest.approx(30)


def test_ray_starting_inside_material_and_limited_length():
    plate = geometry("deska")
    inside = plate.cast((0, 0, 5), (0, 0, 1))
    assert inside.segments[0].entry is None and inside.material_length == pytest.approx(15)
    short = plate.cast((0, 0, 50), (0, 0, -1), max_length=40)  # končí v materiálu
    assert short.segments[0].exit is None and short.material_length == pytest.approx(10)
    assert short.point_at(40) == pytest.approx((0, 0, 10))


def test_hole_plate():
    holed = geometry("otvor")
    across = holed.cast((-120, 0, 10), (1, 0, 0))  # podél X přes otvor
    assert lengths(across) == [90, 90] and across.certain
    assert across.segments[0].exit.normal == pytest.approx((1, 0, 0))  # stěna otvoru ven
    assert holed.cast((5, 0, 50), (0, 0, -1)).segments == ()  # osou otvoru – nic
    assert holed.cast((12, 0, 50), (0, 0, -1)).material_length == pytest.approx(20)


def test_pipe_radial_and_chord():
    pipe = geometry("trubka")
    radial = pipe.cast((0, 0, 100), (0, 0, -1))
    assert lengths(radial) == [6, 6]
    inner = radial.segments[0].exit  # vnitřní stěna: normála míří do otvoru (ven z materiálu)
    assert inner.point == pytest.approx((0, 0, 51.15)) and inner.normal == pytest.approx(
        (0, 0, -1))
    chord = pipe.cast((0, 54, 100), (0, 0, -1))  # 54 mm od osy – vnitřek mine
    assert lengths(chord) == [2 * math.sqrt(57.15**2 - 54**2)]  # 37,42 mm
    assert chord.segments[0].entry.incidence == pytest.approx(
        math.degrees(math.asin(54 / 57.15)))  # 70,9°


def test_spherical_cavity():
    block = Box(40, 40, 40) - Pos(0, 0, 0) * Sphere(10)  # dutina uprostřed
    cavity = PartGeometry(block)
    ray = cavity.cast((0, 0, 50), (0, 0, -1))
    assert lengths(ray) == [10, 10] and ray.material_length == pytest.approx(20)
    assert ray.segments[0].exit.normal == pytest.approx((0, 0, -1))  # do dutiny
    assert cavity.classify((0, 0, 0)) == "outside"  # v dutině
    assert cavity.classify((0, 0, 15)) == "inside"


def test_butt_weld_through_cap_and_root():
    assert geometry("tupy_svar").cast((0, 0, 30), (0, 0, -1)).material_length == pytest.approx(
        12 + 2 + 1)


# --- hraniční případy: nejisté, nikdy materiál ------------------------------------------


def test_ray_lying_in_a_face_is_uncertain_not_material():
    plate = geometry("deska")
    ray = plate.cast((-150, 0, 20), (1, 0, 0))  # přesně v horní ploše
    assert not ray.certain and ALONG_SURFACE in ray.reasons
    assert ray.material_length == 0  # naivně by vyšlo 200 mm


def test_ray_through_an_edge_is_uncertain():
    plate = geometry("deska")
    ray = plate.cast((-120, 0, 40), (1, 0, -1))  # přes hranu x = −100, z = 20
    assert THROUGH_EDGE in ray.reasons
    assert all(not s.certain for s in ray.segments)
    assert ray.material_length == 0


def test_tangent_ray_on_pipe_never_counts_as_material():
    pipe = geometry("trubka")
    ray = pipe.cast((0, 57.15, 100), (0, 0, -1))  # tečna k vnějšímu plášti
    assert ray.material_length == 0
    assert not ray.segments or not ray.certain
    if ray.hits:
        assert GRAZING in ray.reasons or THROUGH_EDGE in ray.reasons


# --- bod uvnitř / vně ----------------------------------------------------------------------


def test_classify_points():
    holed = geometry("otvor")
    assert holed.classify((50, 0, 10)) == "inside"
    assert holed.classify((0, 0, 10)) == "outside"  # v otvoru
    assert holed.classify((50, 0, 20)) == "surface"
    assert holed.classify((50, 0, 30)) == "outside"


def test_bad_input_is_czech_error():
    plate = geometry("deska")
    with pytest.raises(GeometryError, match="nesmí být nulový"):
        plate.cast((0, 0, 0), (0, 0, 0))
    with pytest.raises(GeometryError, match="tři čísla"):
        plate.cast((0, 0), (0, 0, 1))
    with pytest.raises(GeometryError, match="kladná"):
        plate.cast((0, 0, 0), (0, 0, 1), max_length=0)
    with pytest.raises(GeometryError, match="nemá těleso"):
        PartGeometry(None)


def test_thousand_rays_through_pipe_are_fast():
    pipe = geometry("trubka")
    start = time.perf_counter()
    total = sum(pipe.cast((0, -50 + i / 10, 100), (0.1, 0, -1)).material_length
                for i in range(1000))
    assert total > 0
    assert time.perf_counter() - start < 3.0


# --- bod plochy -----------------------------------------------------------------------------


def test_surface_point_on_pipe_plate_and_hole():
    pipe = geometry("trubka")
    outer = pipe.surface_at((0, 0, 57.2))  # kousek nad pláštěm → nejbližší bod pláště
    assert outer.kind == "cylinder" and outer.point == pytest.approx((0, 0, 57.15))
    assert outer.distance == pytest.approx(0.05)
    assert outer.normal == pytest.approx((0, 0, 1))
    assert outer.curvatures == pytest.approx((1 / 57.15, 0))  # vypouklá po obvodu
    assert outer.radii == (pytest.approx(57.15), math.inf)
    assert [abs(c) for c in outer.directions[0]] == pytest.approx([0, 1, 0])  # po obvodu
    assert [abs(c) for c in outer.directions[1]] == pytest.approx([1, 0, 0])  # podél osy
    inner = pipe.surface_at((0, 0, 51.15))
    assert inner.normal == pytest.approx((0, 0, -1))  # do otvoru trubky
    assert inner.curvatures == pytest.approx((-1 / 51.15, 0))  # vydutá
    top = geometry("deska").surface_at((10, 5, 20))
    assert (top.kind, top.curvatures, top.radii) == ("plane", (0, 0), (math.inf, math.inf))
    assert top.certain
    hole = geometry("otvor").surface_at((10, 0, 10))
    assert hole.normal == pytest.approx((-1, 0, 0)) and hole.curvatures == pytest.approx(
        (-0.1, 0))


def test_surface_point_on_edge_is_ambiguous():
    corner = geometry("deska").surface_at((100, 0, 20))  # hrana horní a boční plochy
    assert ON_EDGE in corner.reasons and not corner.certain


# --- viditelnost ----------------------------------------------------------------------------


def test_visibility_past_the_rib():
    ribbed = geometry("zebro")
    blocked = ribbed.visible((30, 0, 20), (-1, 0, 1))  # k žebru pod 45°
    assert not blocked.visible and blocked.certain
    assert blocked.distance == pytest.approx(25 * S2)  # 35,36 mm
    assert blocked.blocker.point == pytest.approx((5, 0, 45))
    clear = ribbed.visible((30, 0, 20), (-1, 0, 3))  # přejde nad žebrem (z = 95 > 80)
    assert clear.visible and clear.blocker is None and clear.certain
    assert ribbed.visible((30, 0, 20), (0, 0, 1)).visible  # kolmo vzhůru
    into = ribbed.visible((30, 0, 20), (0, 0, -1))  # do materiálu
    assert not into.visible and into.distance == 0
    short = ribbed.visible((30, 0, 20), (-1, 0, 1), max_length=20)  # žebro je dál
    assert short.visible


def test_visibility_along_the_surface_is_uncertain():
    flat = geometry("deska").visible((0, 0, 20), (1, 0, 0))  # po ploše k okraji
    assert ALONG_SURFACE in flat.reasons and not flat.certain


# --- kolize ---------------------------------------------------------------------------------


def probe(x, z=20.0):
    """Kvádr 40 × 20 × 25 (sonda) stojící na rovině z, střed v x."""
    return Pos(x, 0, z + 12.5) * Box(40, 20, 25)


def test_probe_collision_with_rib_and_clearance():
    ribbed = geometry("zebro")
    top = ribbed.surface_at((60, 0, 20)).face
    pushed = ribbed.collision(probe(22), [top])  # zasunutá 3 mm do žebra
    assert pushed.colliding and pushed.volume == pytest.approx(3 * 20 * 25)
    assert pushed.clearance == 0
    free = ribbed.collision(probe(30), [top])  # 5 mm od žebra
    assert not free.colliding and free.volume == pytest.approx(0, abs=1e-6)
    assert free.clearance == pytest.approx(5)
    assert free.points[0][0] == pytest.approx(5)  # nejbližší bod na boku žebra
    touching = ribbed.collision(probe(25), [top])  # čelo sondy přesně u žebra
    assert not touching.colliding and touching.clearance == pytest.approx(0, abs=1e-6)
    lifted = geometry("deska").collision(probe(0, 20.5))  # 0,5 mm nad deskou
    assert not lifted.colliding and lifted.clearance == pytest.approx(0.5)
    assert ribbed.collision(probe(30)).clearance == pytest.approx(0, abs=1e-6)  # stojí na ploše


# --- plochy studie --------------------------------------------------------------------------


def test_faces_of_study_target():
    plate = geometry("deska")
    target = {"kind": "faces", "faces": [
        {"face": {"at": [0, 0, 20], "normal": [0, 0, 1], "type": "plane"}},
        {"face": {"at": [0, 0, 10], "normal": [0, 0, 1], "type": "cylinder", "radius": 3}}]}
    faces, problems = plate.faces_of(target)
    assert len(faces) == 1 and faces[0].center().Z == pytest.approx(20)
    assert problems == ["Plocha č. 2: Plocha u bodu [0; 0; 10] už na dílu není – vyber ji "
                        "znovu ve 3D."]
    assert plate.faces_of(None) == ([], [])
