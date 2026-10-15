"""Pole a zrcadlení prvků: objem podle vzorce, poloha kopií, chyby česky."""

import math

import pytest

from conftest import box_features, make_doc
from skodacad import rebuild
from skodacad.holes import hole_shape, removed_volume

PLATE = box_features(100, 60, 10)  # deska 100 × 60 × 10, střed v počátku, z = 0 … 10
PLATE_VOLUME = 100 * 60 * 10


def build(features, parameters=None):
    return rebuild(make_doc(features, parameters))


def build_ok(features, parameters=None):
    result = build(features, parameters)
    assert result.ok, [(s.label, s.message) for s in result.statuses if s.status != "ok"]
    assert result.part.is_valid
    return result.part


def error_of(features):
    result = build(features)
    assert not result.ok
    return result.first_error.message


def pin_hole(x=25, y=0, diameter=6, feature_id="dira"):
    """Slepá válcová díra hloubky 5 z horní plochy (skica + řez)."""
    return [
        {"id": f"{feature_id}_skica", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": diameter, "center": [x, y]}]},
        {"id": feature_id, "type": "extrude", "sketch": f"{feature_id}_skica",
         "operation": "cut", "distance": 5},
    ]


def hole_centers(part, diameter=6):
    """Středy válcových děr daného průměru (x, y) – zaokrouhlené, seřazené."""
    top = part.bounding_box().max.Z
    centers = []
    for edge in part.edges():
        if (edge.geom_type.name == "CIRCLE" and math.isclose(edge.radius, diameter / 2)
                and math.isclose(edge.arc_center.Z, top)):
            center = edge.arc_center
            centers.append((round(center.X, 6) + 0.0, round(center.Y, 6) + 0.0))
    return sorted(centers)


# --- kruhové pole --------------------------------------------------------------------


def test_circular_pattern_full_circle():
    part = build_ok(PLATE + pin_hole() + [
        {"id": "pole", "type": "pattern", "features": ["dira"], "kind": "circular",
         "count": 6},
    ])
    assert part.volume == pytest.approx(PLATE_VOLUME - 6 * math.pi * 3**2 * 5)
    expected = sorted((round(25 * math.cos(math.radians(a)), 6) + 0.0,
                       round(25 * math.sin(math.radians(a)), 6) + 0.0)
                      for a in range(0, 360, 60))
    assert hole_centers(part) == pytest.approx(expected, abs=1e-6)


def test_circular_pattern_partial_angle_puts_last_copy_on_the_edge():
    # 4 kusy na 90° → 0°, 30°, 60°, 90° (krajní kusy na okrajích úhlu)
    part = build_ok(PLATE + pin_hole(x=20) + [
        {"id": "pole", "type": "pattern", "features": ["dira"], "kind": "circular",
         "count": 4, "angle": 90},
    ])
    expected = sorted((round(20 * math.cos(math.radians(a)), 6) + 0.0,
                       round(20 * math.sin(math.radians(a)), 6) + 0.0)
                      for a in (0, 30, 60, 90))
    assert hole_centers(part) == pytest.approx(expected, abs=1e-6)


def test_circular_pattern_around_axis_through_point():
    # osa Z vedená bodem [30, 0, 0]: díra v [40, 0] se otáčí kolem [30, 0]
    part = build_ok(PLATE + pin_hole(x=40) + [
        {"id": "pole", "type": "pattern", "features": ["dira"], "kind": "circular",
         "count": 2, "center": [30, 0, 0]},
    ])
    assert hole_centers(part) == pytest.approx([(20, 0), (40, 0)], abs=1e-6)


def test_circular_pattern_of_revolved_boss_around_x():
    # rotační čep kolem osy X opakovaný kolem osy X → objem jen jednou (leží na sobě)
    # – proto raději žebro: kvádr na boku válce opakovaný 4× kolem osy X
    features = [
        {"id": "s", "type": "sketch", "plane": "YZ",
         "elements": [{"shape": "circle", "diameter": 20}]},
        {"id": "valec", "type": "extrude", "sketch": "s", "distance": 40},
        {"id": "z_s", "type": "sketch", "plane": "XY", "offset": 10,
         "elements": [{"shape": "rectangle", "width": 10, "height": 4, "center": [20, 0]}]},
        {"id": "zebro", "type": "extrude", "sketch": "z_s", "distance": 5},
        {"id": "pole", "type": "pattern", "features": ["zebro"], "kind": "circular",
         "axis": "X", "count": 4},
    ]
    part = build_ok(features)
    assert part.volume == pytest.approx(math.pi * 10**2 * 40 + 4 * 10 * 4 * 5)
    bbox = part.bounding_box()
    assert (bbox.min.Y, bbox.max.Y, bbox.min.Z, bbox.max.Z) == pytest.approx((-15, 15, -15, 15))


# --- lineární pole a mřížka -----------------------------------------------------------


def test_linear_pattern_of_boss_adds_material():
    boss = [
        {"id": "b_s", "type": "sketch", "plane": "top",
         "elements": [{"shape": "rectangle", "width": 8, "height": 8, "center": [-40, 0]}]},
        {"id": "vystupek", "type": "extrude", "sketch": "b_s", "distance": 6},
    ]
    part = build_ok(PLATE + boss + [
        {"id": "pole", "type": "pattern", "features": ["vystupek"], "kind": "linear",
         "direction": "X", "count": 5, "spacing": 20},
    ])
    assert part.volume == pytest.approx(PLATE_VOLUME + 5 * 8 * 8 * 6)
    assert len(part.solids()) == 1


def test_grid_pattern_with_negative_spacing():
    part = build_ok(PLATE + pin_hole(x=40, y=20) + [
        {"id": "mriz", "type": "pattern", "features": ["dira"], "kind": "linear",
         "direction": "X", "count": 4, "spacing": -15,
         "direction2": "Y", "count2": 3, "spacing2": -20},
    ])
    assert part.volume == pytest.approx(PLATE_VOLUME - 12 * math.pi * 3**2 * 5)
    expected = sorted((40 - 15 * i + 0.0, 20 - 20 * j + 0.0) for i in range(4) for j in range(3))
    assert hole_centers(part) == pytest.approx(expected, abs=1e-6)


def test_pattern_count_from_parameter_and_original_change_updates_copies():
    features = PLATE + pin_hole(diameter="d") + [
        {"id": "pole", "type": "pattern", "features": ["dira"], "kind": "circular",
         "count": "n"},
    ]
    part = build_ok(features, {"n": 4, "d": 6})
    assert part.volume == pytest.approx(PLATE_VOLUME - 4 * math.pi * 3**2 * 5)
    part = build_ok(features, {"n": 8, "d": 4})
    assert part.volume == pytest.approx(PLATE_VOLUME - 8 * math.pi * 2**2 * 5)


def test_pattern_repeats_several_features_in_model_order():
    # výstupek a díra do něj: kopie musí mít díru taky (díra až po výstupku)
    features = PLATE + [
        {"id": "b_s", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": 12, "center": [30, 0]}]},
        {"id": "cep", "type": "extrude", "sketch": "b_s", "distance": 8},
        {"id": "d_s", "type": "sketch", "plane": "XY", "offset": 18,
         "elements": [{"shape": "circle", "diameter": 5, "center": [30, 0]}]},
        {"id": "dira", "type": "extrude", "sketch": "d_s", "operation": "cut", "distance": 6},
        {"id": "pole", "type": "pattern", "features": ["dira", "cep"], "kind": "circular",
         "count": 3},
    ]
    part = build_ok(features)
    one = math.pi * 6**2 * 8 - math.pi * 2.5**2 * 6
    assert part.volume == pytest.approx(PLATE_VOLUME + 3 * one)


def test_pattern_of_table_hole_with_counterbore():
    single = build_ok(PLATE + [
        {"id": "dira", "type": "hole", "kind": "counterbore", "size": "M6", "plane": "top",
         "positions": [[20, 0]], "through_all": True},
    ])
    removed = PLATE_VOLUME - single.volume
    shape = hole_shape("counterbore", "M6", through_all=True)
    assert removed == pytest.approx(removed_volume(shape, through_length=10), rel=1e-6)
    part = build_ok(PLATE + [
        {"id": "dira", "type": "hole", "kind": "counterbore", "size": "M6", "plane": "top",
         "positions": [[20, 0]], "through_all": True},
        {"id": "pole", "type": "pattern", "features": ["dira"], "kind": "circular",
         "count": 4},
    ])
    assert part.volume == pytest.approx(PLATE_VOLUME - 4 * removed)


def test_pattern_of_modeled_thread():
    plate = box_features(40, 40, 8)
    hole = {"id": "dira", "type": "hole", "kind": "tapped", "size": "M8", "plane": "top",
            "positions": [[10, 0]], "through_all": True, "modeled_thread": True}
    single = build_ok(plate + [hole])
    removed = 40 * 40 * 8 - single.volume
    part = build_ok(plate + [hole, {"id": "pole", "type": "pattern", "features": ["dira"],
                                    "kind": "circular", "count": 3}])
    assert part.volume == pytest.approx(40 * 40 * 8 - 3 * removed, rel=1e-3)


# --- zrcadlení -------------------------------------------------------------------------


def test_mirror_feature_across_yz():
    part = build_ok(PLATE + pin_hole(x=30, y=10) + [
        {"id": "zrc", "type": "mirror", "features": ["dira"], "plane": "YZ"},
    ])
    assert part.volume == pytest.approx(PLATE_VOLUME - 2 * math.pi * 3**2 * 5)
    assert hole_centers(part) == pytest.approx([(-30, 10), (30, 10)], abs=1e-6)
    assert part.center().X == pytest.approx(0, abs=1e-6)


def test_mirror_feature_across_offset_plane():
    part = build_ok(PLATE + pin_hole(x=30, y=10) + [
        {"id": "zrc", "type": "mirror", "features": ["dira"], "plane": "XZ", "offset": 5},
    ])
    # posun jde po normále roviny jako u skici – u XZ je to −Y, rovina je tedy v y = −5
    assert hole_centers(part) == pytest.approx([(30, -20), (30, 10)], abs=1e-6)


def test_mirror_whole_part_across_its_face_doubles_it():
    part = build_ok(PLATE + pin_hole(x=30) + [
        {"id": "zrc", "type": "mirror", "plane": "right"},
    ])
    assert part.volume == pytest.approx(2 * (PLATE_VOLUME - math.pi * 3**2 * 5))
    bbox = part.bounding_box()
    assert (bbox.min.X, bbox.max.X) == pytest.approx((-50, 150))
    assert len(part.solids()) == 1
    assert hole_centers(part) == pytest.approx([(30, 0), (70, 0)], abs=1e-6)


def test_mirror_whole_half_part_makes_symmetric_part():
    # polovina dílu do kladného X, zrcadlení podle YZ dá celý souměrný díl
    half = [
        {"id": "s", "type": "sketch", "elements": [
            {"shape": "polygon", "points": [[0, 0], [40, 0], [40, 10], [10, 30], [0, 30]]}]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 5},
    ]
    one = build_ok(half).volume
    part = build_ok(half + [{"id": "zrc", "type": "mirror", "plane": "YZ"}])
    assert part.volume == pytest.approx(2 * one)
    assert part.center().X == pytest.approx(0, abs=1e-6)
    assert len(part.solids()) == 1


def test_mirror_of_pattern_and_pattern_of_mirror():
    part = build_ok(PLATE + pin_hole(x=30, y=15) + [
        {"id": "rada", "type": "pattern", "features": ["dira"], "kind": "linear",
         "direction": "X", "count": 2, "spacing": 12},
        {"id": "zrc", "type": "mirror", "features": ["dira", "rada"], "plane": "YZ"},
        {"id": "zrc2", "type": "mirror", "features": ["dira", "rada", "zrc"], "plane": "XZ"},
    ])
    assert part.volume == pytest.approx(PLATE_VOLUME - 8 * math.pi * 3**2 * 5)
    expected = sorted((sx * x + 0.0, sy * 15.0) for x in (30, 42) for sx in (1, -1)
                      for sy in (1, -1))
    assert hole_centers(part) == pytest.approx(expected, abs=1e-6)


# --- chyby --------------------------------------------------------------------------


def test_pattern_of_fillet_explains_what_can_be_repeated():
    message = error_of(PLATE + [
        {"id": "zaobleni", "type": "fillet", "edges": {"face": "top"}, "radius": 1},
        {"id": "pole", "type": "pattern", "features": ["zaobleni"], "count": 3},
    ])
    assert "nepřidává ani neubírá materiál" in message


def test_pattern_of_later_or_missing_feature():
    message = error_of(PLATE + [
        {"id": "pole", "type": "pattern", "features": ["dira"], "count": 3},
        *pin_hole(),
    ])
    assert "„dira“ neexistuje nebo je ve stromu až za tímto prvkem" in message
    assert "vyber prvky" in error_of(PLATE + [{"id": "pole", "type": "pattern", "count": 3}])


@pytest.mark.parametrize(("values", "text"), [
    ({"kind": "linear", "count": 3, "spacing": 0}, "Rozteč nesmí být 0"),
    ({"kind": "linear", "count": 1}, "aspoň 2 kusy"),
    ({"kind": "circular", "count": 1}, "aspoň 2 kusy"),
    ({"kind": "circular", "count": 2.5}, "celé kladné číslo"),
    ({"kind": "circular", "count": 3, "angle": 400}, "(0, 360]"),
    ({"kind": "linear", "count": 2, "spacing": 5, "direction2": "X", "count2": 2,
      "spacing2": 5}, "Druhý směr mřížky"),
    ({"kind": "linear", "count": 30, "spacing": 1, "direction2": "Y", "count2": 30,
      "spacing2": 1}, "víc než 500"),
    ({"kind": "linear", "count": 3, "spacing": 200}, "kopie leží mimo díl"),
    ({"kind": "spiral", "count": 3}, "neznámou hodnotu „spiral“"),
])
def test_pattern_errors_are_czech(values, text):
    message = error_of(PLATE + pin_hole() + [
        {"id": "pole", "type": "pattern", "features": ["dira"], **values}])
    assert text in message


def test_mirror_errors_are_czech():
    assert "už souměrný" in error_of(PLATE + [{"id": "zrc", "type": "mirror", "plane": "YZ"}])
    message = error_of(PLATE + pin_hole(x=0) + [
        {"id": "zrc", "type": "mirror", "features": ["dira"], "plane": "YZ"}])
    assert "na stejném místě" in message
