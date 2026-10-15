"""Díry podle strojnických tabulek: objem podle vzorce, poloha, tabulky a chybové hlášky."""

import math

import pytest
from build123d import Vector

from conftest import box_features, make_doc
from skodacad import rebuild
from skodacad.features import describe
from skodacad.holes import (
    CLEARANCE,
    COUNTERBORE,
    COUNTERSINK,
    INSERT,
    PITCH,
    TAP_DRILL,
    hole_shape,
    nominal,
    removed_volume,
)
from skodacad.schema import new_feature

BOX = 60 * 40 * 20  # kvádr 60 × 40 × 20, střed v počátku, z = 0 … 20
TAN59 = math.tan(math.radians(59))  # polovina vrcholového úhlu vrtáku 118°


def drilled(hole, parameters=None):
    features = [*box_features(60, 40, 20), {"id": "h", "type": "hole", "plane": "top", **hole}]
    result = rebuild(make_doc(features, parameters))
    assert result.ok, result.first_error
    assert result.part.is_valid
    return result.part


def cylinder(diameter, length):
    return math.pi * diameter ** 2 / 4 * length


# Objem jedné díry spočítaný ručně (nezávisle na holes.removed_volume).
@pytest.mark.parametrize(("hole", "expected"), [
    # Závitová M6 hl. 12: vrták Ø5 + kužel vrtáku 118°.
    ({"kind": "tapped", "size": "M6", "depth": 12},
     cylinder(5.0, 12) + math.pi * 2.5 ** 2 * (2.5 / TAN59) / 3),
    # Průchozí M6 střední řada Ø6,6 skrz 20 mm.
    ({"kind": "clearance", "size": "M6", "through_all": True}, cylinder(6.6, 20)),
    # Průchozí M8 hrubá Ø10.
    ({"kind": "clearance", "size": "M8", "fit": "coarse", "through_all": True},
     cylinder(10.0, 20)),
    # Válcové zahloubení M6: Ø11 × 6,4 + díra Ø6,6 pod ním.
    ({"kind": "counterbore", "size": "M6", "through_all": True},
     cylinder(11, 6.4) + cylinder(6.6, 20 - 6.4)),
    # Kuželové 90° M6: komolý kužel Ø13,7 → Ø6,6 výšky 3,55 + díra Ø6,6.
    ({"kind": "countersink", "size": "M6", "through_all": True},
     math.pi * 3.55 / 3 * (6.85 ** 2 + 6.85 * 3.3 + 3.3 ** 2) + cylinder(6.6, 20 - 3.55)),
    # Zálisná matice M3: Ø4 s plochým dnem, výchozí hloubka 2·3 + 1 = 7.
    ({"kind": "insert", "size": "M3"}, cylinder(4.0, 7)),
    # Šroub do plastu M3: vrták pod závit Ø2,5, ploché dno, hloubka 8.
    ({"kind": "plastic", "size": "M3", "depth": 8}, cylinder(2.5, 8)),
    # Vlastní průměr přepíše tabulku.
    ({"kind": "insert", "size": "M3", "diameter": 4.2, "depth": 6}, cylinder(4.2, 6)),
])
def test_hole_volume_matches_formula(hole, expected):
    part = drilled(hole)
    assert BOX - part.volume == pytest.approx(expected, rel=1e-6)
    shape = hole_shape(hole["kind"], hole["size"], hole.get("fit", "medium"),
                       depth=hole.get("depth"), through_all=hole.get("through_all", False),
                       diameter=hole.get("diameter"))
    assert removed_volume(shape, 20) == pytest.approx(expected, rel=1e-9)


def test_several_holes_at_parametric_positions():
    hole = {"kind": "tapped", "size": "M5", "depth": 10,
            "positions": [["roztec/2", 0], ["-roztec/2", 0], [0, 12]]}
    for spacing in (30, 44):
        part = drilled(hole, {"roztec": spacing})
        one = cylinder(4.2, 10) + math.pi * 2.1 ** 2 * (2.1 / TAN59) / 3
        assert BOX - part.volume == pytest.approx(3 * one, rel=1e-6)
        assert not part.is_inside(Vector(spacing / 2, 0, 15))  # díra je tam, kde má být
        assert part.is_inside(Vector(spacing / 2, 0, 5))  # a jen 10 mm hluboko (+ špička)


def test_hole_on_side_face_goes_into_material():
    features = [*box_features(60, 40, 20),
                {"id": "h", "type": "hole", "plane": "front", "kind": "clearance",
                 "size": "M4", "through_all": True, "positions": [[0, 10]]}]
    part = rebuild(make_doc(features)).part
    assert BOX - part.volume == pytest.approx(cylinder(4.5, 40), rel=1e-6)
    assert not part.is_inside(Vector(0, 0, 10))


@pytest.mark.parametrize(("hole", "message"), [
    ({"kind": "countersink", "size": "M16"}, "Kuželové zahloubení pro M16 v tabulce není"),
    ({"kind": "insert", "size": "M8"}, "zálisnou matici pro M8"),
    ({"kind": "tapped", "size": "M7"}, "Neznámá velikost"),
    ({"kind": "vrtat", "size": "M6"}, "neznámou hodnotu"),
    ({"kind": "tapped", "size": "M6", "depth": 6, "thread_depth": 9}, "se nevejde"),
    ({"kind": "counterbore", "size": "M6", "depth": 5}, "mělčí než zahloubení"),
    ({"kind": "tapped", "size": "M6", "depth": -3}, "kladná"),
    ({"kind": "clearance", "size": "M6", "fit": "volna"}, "Řada průchozí díry"),
    ({"kind": "tapped", "size": "M6", "positions": [[500, 0]]}, "neodebral žádný materiál"),
])
def test_bad_holes_explain_in_czech(hole, message):
    features = [*box_features(60, 40, 20), {"id": "h", "type": "hole", "plane": "top", **hole}]
    error = rebuild(make_doc(features)).first_error
    assert error is not None and message in error.message


def test_hole_needs_a_part():
    error = rebuild(make_doc([{"id": "h", "type": "hole", "size": "M6"}])).first_error
    assert "existující díl" in error.message


# --- kontrola tabulek proti sobě a proti rozměrům šroubů --------------------------------

ISO_4762_HEAD = {"M3": 5.5, "M4": 7, "M5": 8.5, "M6": 10, "M8": 13, "M10": 16, "M12": 18,
                 "M16": 24, "M20": 30, "M24": 36}  # dk max, hlava válcová (Würth, fasten.it)
ISO_10642_HEAD = {"M3": 6.72, "M4": 8.96, "M5": 11.2, "M6": 13.44, "M8": 17.92, "M10": 22.4,
                  "M12": 26.88}  # dk teoreticky max (Engineers Edge)


def test_tables_are_consistent():
    assert set(TAP_DRILL) == set(PITCH) == set(CLEARANCE)
    for size, pitch in PITCH.items():
        d = nominal(size)
        assert abs(TAP_DRILL[size] - (d - pitch)) <= 0.06, size  # vrták ≈ d − P
        fine, medium, coarse = CLEARANCE[size]
        assert d < fine < medium < coarse, size
    for size, (diameter, depth) in COUNTERBORE.items():
        assert diameter > ISO_4762_HEAD[size], size  # hlava se vejde
        assert depth > nominal(size), size  # hlava (výška = d) se zapustí
    for size, diameter in COUNTERSINK.items():
        assert ISO_10642_HEAD[size] < diameter < ISO_10642_HEAD[size] + 0.5, size
    for size, diameter in INSERT.items():
        assert diameter > CLEARANCE[size][2], size  # matice je širší než šroub


def test_new_hole_defaults_and_tree_label():
    features = [*box_features(60, 40, 20)]
    hole = new_feature("hole", features)
    assert hole["plane"] == "top" and hole["size"] == "M6" and hole["kind"] == "tapped"
    assert describe(hole) == "Díra „Díra 1“ – M6 závit"
    hole["positions"] = [[0, 0], [10, 0]]
    assert describe(hole).endswith("M6 závit, 2×")
    features.append(hole)
    assert rebuild(make_doc(features)).ok


@pytest.mark.parametrize("overrides", [{}, {"A": 150, "e": 15}, {"t": 20}])
def test_plate_example_follows_parameters(examples_dir, overrides):
    from skodacad import Document

    document = Document.load(examples_dir / "deska.json")
    result = rebuild(document, overrides)
    assert result.ok, result.first_error
    p = {**document.parameters, **overrides}
    t = p["t"]
    plate = p["A"] * p["B"] * t - (4 - math.pi) * 6 ** 2 * t  # rohy R6
    removed = (4 * removed_volume(hole_shape("counterbore", "M6", through_all=True), t)
               + 2 * removed_volume(hole_shape("tapped", "M8", depth=12))
               + 2 * removed_volume(hole_shape("countersink", "M5", through_all=True), t)
               + 2 * removed_volume(hole_shape("clearance", "M4", "fine", through_all=True), t))
    assert result.part.volume == pytest.approx(plate - removed, rel=1e-6)
