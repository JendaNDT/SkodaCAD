"""Skica a díra na šikmé ploše a na tečné rovině k zakřivené ploše – objem podle vzorce."""

import math

import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface

from conftest import make_doc
from skodacad import rebuild
from skodacad.selectors import SelectionError, describe_plane, face_plane_at

BLOCK = [  # kvádr 40 × 30 × 20, horní přední hrana sražená 10 mm (šikmá plocha 45°)
    {"id": "s", "type": "sketch", "elements": [{"shape": "rectangle", "width": 40, "height": 30}]},
    {"id": "e", "type": "extrude", "sketch": "s", "distance": 20},
    {"id": "c", "type": "chamfer", "edges": {"between": ["top", "front"]}, "distance": 10},
]
BLOCK_VOLUME = 40 * 30 * 20 - 0.5 * 10 * 10 * 40
CHAMFER = {"at": [0, -10, 15], "normal": [0, -0.7071, 0.7071]}  # střed šikmé plochy

SHAFT = [  # hřídel Ø D podél osy X, délka 80, uprostřed v počátku
    {"id": "s", "type": "sketch", "plane": "YZ",
     "elements": [{"shape": "circle", "diameter": "D"}]},
    {"id": "e", "type": "extrude", "sketch": "s", "distance": 80, "direction": "both"},
]


def build_ok(features, parameters=None):
    result = rebuild(make_doc(features, parameters))
    assert result.ok, [(s.label, s.message) for s in result.statuses if s.status != "ok"]
    assert result.part.is_valid
    return result.part


def cylinder_axes(part):
    axes = []
    for face in part.faces():
        if face.geom_type.name == "CYLINDER":
            d = BRepAdaptor_Surface(face.wrapped).Cylinder().Axis().Direction()
            axes.append((round(d.X(), 4) + 0.0, round(d.Y(), 4) + 0.0, round(d.Z(), 4) + 0.0))
    return axes


def integrate(f, a, b, n=4000):
    step = (b - a) / n
    return sum(f(a + (i + 0.5) * step) for i in range(n)) * step


def test_sketch_on_inclined_face_cuts_perpendicular_to_it():
    part = build_ok(BLOCK + [
        {"id": "k", "type": "sketch", "plane": CHAMFER,
         "elements": [{"shape": "circle", "diameter": 6}]},
        {"id": "rez", "type": "extrude", "sketch": "k", "operation": "cut", "distance": 5},
    ])
    assert part.volume == pytest.approx(BLOCK_VOLUME - math.pi * 9 * 5)
    assert cylinder_axes(part) == [(0.0, -0.7071, 0.7071)]  # osa díry kolmo k šikmé ploše


def test_sketch_origin_is_the_picked_point_and_x_runs_along_the_face():
    part = build_ok(BLOCK)
    plane = face_plane_at(part, CHAMFER)
    assert tuple(plane.origin) == pytest.approx((0, -10, 15))
    assert tuple(plane.z_dir) == pytest.approx((0, -math.sqrt(0.5), math.sqrt(0.5)))
    assert tuple(plane.x_dir) == pytest.approx((1, 0, 0))  # vodorovně po ploše
    moved = face_plane_at(part, {"at": [5, -12, 13], "normal": CHAMFER["normal"]})
    assert tuple(moved.origin) == pytest.approx((5, -12, 13))  # bod na ploše zůstane


def test_table_hole_on_inclined_face():
    part = build_ok(BLOCK + [
        {"id": "d", "type": "hole", "kind": "clearance", "size": "M6", "plane": CHAMFER,
         "positions": [[0, 0], [12, 0]], "depth": 8},
    ])
    removed = 2 * (math.pi * 3.3**2 * 8 + math.pi * 3.3**2 * (3.3 / math.tan(math.radians(59)))
                   / 3)  # 2 díry Ø6,6 hl. 8 se špičkou vrtáku 118°
    assert part.volume == pytest.approx(BLOCK_VOLUME - removed)


@pytest.mark.parametrize("diameter", [20, 24])
def test_cross_hole_through_shaft_on_tangent_plane(diameter):
    r_shaft, r_hole = diameter / 2, 3.3  # průchozí M6 střední řada Ø6,6
    part = build_ok(SHAFT + [
        {"id": "d", "type": "hole", "kind": "clearance", "size": "M6", "through_all": True,
         "plane": {"at": [5, 0, r_shaft], "normal": [0, 0, 1]}},
    ], {"D": diameter})
    # díra Ø6,6 napříč válcem: řez v hloubce y má délku 2·√(R² − y²)
    removed = integrate(lambda y: 2 * math.sqrt(r_hole**2 - y * y)
                        * 2 * math.sqrt(r_shaft**2 - y * y), -r_hole, r_hole)
    assert math.pi * r_shaft**2 * 80 - part.volume == pytest.approx(removed, rel=1e-3)
    assert (0.0, 0.0, 1.0) in [tuple(abs(c) for c in axis) for axis in cylinder_axes(part)]


def test_tangent_plane_follows_shaft_diameter():
    spec = {"at": [5, 0, 10], "normal": [0, 0, 1]}
    for diameter in (20, 30):
        part = build_ok(SHAFT, {"D": diameter})
        plane = face_plane_at(part, spec)
        assert tuple(plane.origin) == pytest.approx((5, 0, diameter / 2))  # dotyk na povrchu
        assert tuple(plane.x_dir) == pytest.approx((1, 0, 0))  # podél osy hřídele


def test_keyway_on_shaft_runs_along_the_axis():
    part = build_ok(SHAFT + [
        {"id": "k", "type": "sketch", "plane": {"at": [0, 0, 10], "normal": [0, 0, 1]},
         "elements": [{"shape": "slot", "length": 20, "width": 6}]},
        {"id": "rez", "type": "extrude", "sketch": "k", "operation": "cut", "distance": 3},
    ], {"D": 20})
    # drážka 20 × 6 se zaoblenými konci, dno 3 mm pod nejvyšším bodem hřídele (z = 7)
    removed = integrate(lambda y: (20 + 2 * math.sqrt(9 - y * y)) * (math.sqrt(100 - y * y) - 7),
                        -3, 3)
    assert math.pi * 100 * 80 - part.volume == pytest.approx(removed, rel=1e-6)
    bottom = [f for f in part.faces() if f.geom_type.name == "PLANE"
              and f.normal_at().Z == pytest.approx(1)]
    assert [tuple(f.center()) for f in bottom] == [pytest.approx((0, 0, 7))]


def test_missing_face_and_bad_spec_are_czech():
    part = build_ok(BLOCK)
    with pytest.raises(SelectionError, match="už na dílu není"):
        face_plane_at(part, {"at": [0, -10, 15], "normal": [0, 0, -1]})  # nic tam nemíří dolů
    with pytest.raises(SelectionError, match="„at“"):
        face_plane_at(part, {"normal": [0, 0, 1]})
    result = rebuild(make_doc([{"id": "k", "type": "sketch", "plane": CHAMFER,
                                "elements": [{"shape": "circle", "diameter": 6}]}]))
    assert "potřebuje existující díl" in result.first_error.message
    assert describe_plane(CHAMFER) == "plocha vybraná ve 3D (u bodu 0; -10; 15)"
    assert describe_plane("top") == "horní plocha dílu"


@pytest.mark.parametrize("diameter", [20, 22])
def test_pin_example_follows_diameter(examples_dir, diameter):
    from skodacad import Document

    result = rebuild(Document.load(examples_dir / "cep.json"), {"D": diameter})
    assert result.ok, result.first_error and result.first_error.message
    r = diameter / 2
    hole = integrate(lambda y: 2 * math.sqrt(2.25**2 - y * y) * 2 * math.sqrt(r * r - y * y),
                     -2.25, 2.25)  # průchozí M4 Ø4,5 napříč čepem
    keyway = integrate(lambda y: (19 + 2 * math.sqrt(9 - y * y))
                       * (math.sqrt(r * r - y * y) - (r - 3.5)), -3, 3)  # pero 6 × 3,5 × 25
    assert result.part.volume == pytest.approx(math.pi * r * r * 80 - hole - keyway, rel=1e-4)
    bottom = [f for f in result.part.faces() if f.geom_type.name == "PLANE"
              and f.normal_at().Z == pytest.approx(1)]
    assert [tuple(f.center()) for f in bottom] == [pytest.approx((-15, 0, r - 3.5))]
