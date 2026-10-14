"""Geometrické testy prvků: výsledek se ověřuje fyzikou (objem, rozměry, platnost)."""

import math

import pytest

from conftest import box_features, make_doc
from skodacad import rebuild


def build_ok(features, parameters=None):
    result = rebuild(make_doc(features, parameters))
    assert result.ok, [(s.label, s.message) for s in result.statuses if s.status != "ok"]
    assert result.part.is_valid
    return result.part


def size(part):
    s = part.bounding_box().size
    return (round(s.X, 6), round(s.Y, 6), round(s.Z, 6))


def test_rectangle_extrude_gives_exact_box():
    part = build_ok(box_features(20, 30, 40))
    assert part.volume == pytest.approx(20 * 30 * 40)
    assert len(part.faces()) == 6
    assert size(part) == (20, 30, 40)


@pytest.mark.parametrize(
    ("direction", "z_range"),
    [("normal", (0, 10)), ("reverse", (-10, 0)), ("both", (-5, 5))],
)
def test_extrude_directions(direction, z_range):
    part = build_ok([
        {"id": "s", "type": "sketch", "elements": [{"shape": "circle", "diameter": 10}]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 10, "direction": direction},
    ])
    bbox = part.bounding_box()
    assert (bbox.min.Z, bbox.max.Z) == pytest.approx(z_range)


def test_sketch_with_subtracted_circle_makes_ring():
    part = build_ok([
        {"id": "s", "type": "sketch", "elements": [
            {"shape": "circle", "diameter": 100},
            {"shape": "circle", "diameter": 40, "mode": "subtract"},
        ]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 10},
    ])
    assert part.volume == pytest.approx(math.pi / 4 * (100**2 - 40**2) * 10)


def test_cut_through_all_from_top_face():
    features = box_features(40, 40, 10) + [
        {"id": "h", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": 10}]},
        {"id": "c", "type": "extrude", "sketch": "h", "operation": "cut", "through_all": True},
    ]
    part = build_ok(features)
    assert part.volume == pytest.approx(40 * 40 * 10 - math.pi * 5**2 * 10)


def test_blind_cut_goes_into_material_by_default():
    features = box_features(40, 40, 10) + [
        {"id": "h", "type": "sketch", "plane": "top",
         "elements": [{"shape": "rectangle", "width": 10, "height": 10}]},
        {"id": "c", "type": "extrude", "sketch": "h", "operation": "cut", "distance": 4},
    ]
    part = build_ok(features)
    assert part.volume == pytest.approx(40 * 40 * 10 - 10 * 10 * 4)
    assert size(part) == (40, 40, 10)


def test_add_on_top_face_raises_height():
    features = box_features(40, 40, 10) + [
        {"id": "h", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": 20}]},
        {"id": "a", "type": "extrude", "sketch": "h", "distance": 15},
    ]
    part = build_ok(features)
    assert size(part) == (40, 40, 25)
    assert part.volume == pytest.approx(40 * 40 * 10 + math.pi * 10**2 * 15)


def test_sketch_on_side_face_cuts_side_wall():
    features = box_features(40, 40, 20) + [
        {"id": "h", "type": "sketch", "plane": "front",
         "elements": [{"shape": "circle", "diameter": 6, "center": [0, 10]}]},
        {"id": "c", "type": "extrude", "sketch": "h", "operation": "cut", "distance": 5},
    ]
    part = build_ok(features)
    assert part.volume == pytest.approx(40 * 40 * 20 - math.pi * 3**2 * 5)
    hole_faces = [f for f in part.faces() if f.geom_type.name == "CYLINDER"]
    assert hole_faces and all(f.center().Y < -14 for f in hole_faces)  # díra je v přední stěně


def test_revolve_makes_tube():
    part = build_ok([
        {"id": "p", "type": "sketch", "plane": "XZ",
         "elements": [{"shape": "rectangle", "width": 10, "height": 20, "center": [15, 10]}]},
        {"id": "r", "type": "revolve", "sketch": "p", "axis": "Z"},
    ])
    assert part.volume == pytest.approx(math.pi * (20**2 - 10**2) * 20)


def test_circle_pattern_hole_count_and_volume():
    features = [
        {"id": "s", "type": "sketch", "elements": [
            {"shape": "circle", "diameter": 100},
            {"shape": "circle_pattern", "count": 6, "pitch_diameter": 70, "diameter": 8,
             "mode": "subtract"},
        ]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 5},
    ]
    part = build_ok(features)
    assert part.volume == pytest.approx(math.pi / 4 * (100**2 - 6 * 8**2) * 5)


@pytest.mark.parametrize(
    ("element", "area"),
    [
        ({"shape": "regular_polygon", "sides": 6, "diameter": 20}, 3 * math.sqrt(3) / 2 * 10**2),
        ({"shape": "slot", "length": 20, "width": 6}, 20 * 6 + math.pi * 3**2),
        ({"shape": "polygon", "points": [[0, 0], [10, 0], [0, 10]]}, 50),
        ({"shape": "rectangle", "width": 20, "height": 10, "corner_radius": 2},
         20 * 10 - (4 - math.pi) * 2**2),
    ],
)
def test_sketch_shapes_have_expected_area(element, area):
    part = build_ok([
        {"id": "s", "type": "sketch", "elements": [element]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 1},
    ])
    assert part.volume == pytest.approx(area)


def test_shape_angle_rotates_around_center():
    part = build_ok([
        {"id": "s", "type": "sketch", "elements": [
            {"shape": "polygon", "points": [[0, 0], [40, 0], [40, 10], [0, 10]],
             "center": [5, 5], "angle": 90},
        ]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 1},
    ])
    bbox = part.bounding_box()
    assert (bbox.min.X, bbox.max.X, bbox.min.Y, bbox.max.Y) == pytest.approx((-5, 5, 5, 45))


def test_fillet_vertical_edges():
    part = build_ok(box_features(20, 30, 40) + [
        {"id": "f", "type": "fillet", "edges": {"parallel": "Z"}, "radius": 3},
    ])
    assert part.volume == pytest.approx(20 * 30 * 40 - (4 - math.pi) * 3**2 * 40)


def test_chamfer_top_edges():
    part = build_ok(box_features(20, 30, 40) + [
        {"id": "c", "type": "chamfer", "edges": {"face": "top"}, "distance": 2},
    ])
    assert part.volume < 20 * 30 * 40
    assert size(part) == (20, 30, 40)


def test_shell_open_top():
    part = build_ok(box_features(50, 30, 20) + [
        {"id": "sh", "type": "shell", "thickness": 2, "open_faces": ["top"]},
    ])
    assert part.volume == pytest.approx(50 * 30 * 20 - 46 * 26 * 18)


def test_expressions_drive_geometry():
    part = build_ok(box_features("a", "a * 2", "a + 5"), parameters={"a": 10})
    assert size(part) == (10, 20, 15)
