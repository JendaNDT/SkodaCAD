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
