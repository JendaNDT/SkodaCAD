"""Kružnice v obrysu, díry (víc smyček) a vazby mezi tvary – výsledek podle vzorce."""

import copy
import math

import pytest

from conftest import make_doc
from skodacad import rebuild
from skodacad.schema import SHAPE_DEFAULTS
from skodacad.solver import SolveError, loops, solve


def plate(*extra_constraints, holes=None):
    """Obdélník 40 × 30 (roh v počátku, plně určený) + kružnice ``holes`` {jméno: (x, y, r)}."""
    profile = copy.deepcopy(SHAPE_DEFAULTS["profile"])
    for index, (name, (x, y, r)) in enumerate((holes or {}).items()):
        center = f"K{index + 1}"
        profile["points"][center] = [x, y]
        profile["segments"][name] = {"type": "circle", "center": center, "radius": r}
    profile["constraints"] += list(extra_constraints)
    return profile


def extruded_volume(profile, height=10):
    result = rebuild(make_doc([
        {"id": "s", "type": "sketch", "elements": [profile]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": height},
    ]))
    assert result.ok, result.first_error and result.first_error.message
    assert result.part.is_valid
    return result.part.volume


def test_circle_hole_with_dimensions_is_fully_defined():
    profile = plate(
        {"type": "diameter", "segment": "k1", "value": 10},
        {"type": "distance", "point": "K1", "segment": "s1", "value": 12},
        {"type": "distance", "point": "K1", "segment": "s4", "value": 15},
        holes={"k1": (14, 11, 4)},
    )
    result = solve(profile, float)
    assert result.dof == 0
    assert result.points["K1"] == pytest.approx((15, 12))
    assert result.radii["k1"] == pytest.approx(5)
    assert extruded_volume(profile) == pytest.approx((40 * 30 - math.pi * 5**2) * 10)


def test_hole_inside_hole_is_material_again():
    # čtverec 40 × 30, v něm díra Ø24 a v ní ostrůvek Ø10 (soustředně)
    profile = plate(
        {"type": "concentric", "segments": ["k1", "k2"]},
        {"type": "diameter", "segment": "k1", "value": 24},
        {"type": "diameter", "segment": "k2", "value": 10},
        holes={"k1": (20, 15, 11), "k2": (21, 14, 4)},
    )
    assert extruded_volume(profile) == pytest.approx(
        (40 * 30 - math.pi * 12**2 + math.pi * 5**2) * 10)


def test_separate_islands_both_count():
    profile = plate(holes={"k1": (70, 15, 5)})  # kružnice vedle obdélníku = druhý ostrov
    assert extruded_volume(profile) == pytest.approx((40 * 30 + math.pi * 25) * 10)


def test_crossing_loops_are_refused():
    profile = plate(holes={"k1": (40, 15, 5)})  # kružnice přes pravou hranu
    result = rebuild(make_doc([{"id": "s", "type": "sketch", "elements": [profile]}]))
    assert "se navzájem kříží" in result.first_error.message


def test_construction_circle_is_not_a_hole():
    profile = plate(holes={"k1": (20, 15, 5)})
    profile["segments"]["k1"]["construction"] = True
    assert extruded_volume(profile) == pytest.approx(40 * 30 * 10)
    assert len(loops(profile, solve(profile, float).points)) == 1


def test_point_on_circle_and_equal_radius():
    profile = plate(
        {"type": "coincident", "point": "K1", "on": "origin"},
        {"type": "diameter", "segment": "k1", "value": 20},
        {"type": "equal", "segments": ["k1", "k2"]},
        {"type": "coincident", "point": "K2", "on": "k1"},
        holes={"k1": (1, 1, 9), "k2": (8, 6, 3)},
    )
    result = solve(profile, float)
    assert result.radii["k2"] == pytest.approx(10)
    assert math.dist(result.points["K2"], (0, 0)) == pytest.approx(10)


def test_symmetric_hole_centers_about_construction_line():
    profile = plate(
        {"type": "symmetric", "points": ["K1", "K2"], "segment": "osa"},
        holes={"k1": (10, 10, 3), "k2": (31, 9, 3)},
    )
    profile["points"].update(O1=[20, 0], O2=[20, 30])
    profile["segments"]["osa"] = {"type": "line", "start": "O1", "end": "O2",
                                  "construction": True}
    profile["constraints"] += [{"type": "midpoint", "point": "O1", "segment": "s1"},
                               {"type": "vertical", "segment": "osa"}]
    result = solve(profile, float)
    (x1, y1), (x2, y2) = result.points["K1"], result.points["K2"]
    assert (x1 + x2) / 2 == pytest.approx(20) and y1 == pytest.approx(y2)


@pytest.mark.parametrize(("start_y", "expected_y"), [(8.0, 10.0), (-7.0, -10.0)])
def test_line_tangent_to_circle(start_y, expected_y):
    profile = {
        "shape": "profile",
        "points": {"M": [0, 0], "A": [-20, start_y], "B": [20, start_y]},
        "segments": {"k": {"type": "circle", "center": "M", "radius": 10},
                     "l": {"type": "line", "start": "A", "end": "B", "construction": True}},
        "constraints": [{"type": "coincident", "point": "M", "on": "origin"},
                        {"type": "diameter", "segment": "k", "value": 20},
                        {"type": "horizontal", "segment": "l"},
                        {"type": "tangent", "segments": ["l", "k"]}],
    }
    points = solve(profile, float).points
    assert points["A"][1] == pytest.approx(expected_y)
    assert points["B"][1] == pytest.approx(expected_y)


@pytest.mark.parametrize(("other", "distance"), [((18, 1), 15), ((3, 1), 5)])
def test_circles_tangent_outside_and_inside(other, distance):
    # Ø20 a Ø10: zvenku se středy vzdálí na 15, zevnitř (malá uvnitř velké) na 5
    profile = {
        "shape": "profile",
        "points": {"M": [0, 0], "N": list(other)},
        "segments": {"big": {"type": "circle", "center": "M", "radius": 10},
                     "small": {"type": "circle", "center": "N", "radius": 4}},
        "constraints": [{"type": "coincident", "point": "M", "on": "origin"},
                        {"type": "diameter", "segment": "big", "value": 20},
                        {"type": "diameter", "segment": "small", "value": 10},
                        {"type": "horizontal", "points": ["M", "N"]},
                        {"type": "tangent", "segments": ["small", "big"]}],
    }
    result = solve(profile, float)
    assert result.dof == 0
    assert math.dist(result.points["M"], result.points["N"]) == pytest.approx(distance)


def test_hole_concentric_with_arc_of_outline():
    # obrys „D“: oblouk vpravo, díra soustředně s ním
    profile = {
        "shape": "profile",
        "points": {"A": [0, 0], "B": [30, 0], "C": [30, 20], "D": [0, 20], "M": [30, 10],
                   "K": [28, 11]},
        "segments": {"s1": {"type": "line", "start": "A", "end": "B"},
                     "a1": {"type": "arc", "start": "B", "end": "C", "center": "M"},
                     "s2": {"type": "line", "start": "C", "end": "D"},
                     "s3": {"type": "line", "start": "D", "end": "A"},
                     "k1": {"type": "circle", "center": "K", "radius": 4}},
        "constraints": [{"type": "concentric", "segments": ["k1", "a1"]},
                        {"type": "diameter", "segment": "k1", "value": 8}],
    }
    result = solve(profile, float)
    assert result.points["K"] == pytest.approx(result.points["M"])
    area = 30 * 20 + math.pi * 10**2 / 2 - math.pi * 4**2
    assert extruded_volume(profile) == pytest.approx(area * 10)


@pytest.mark.parametrize(("change", "message"), [
    (lambda p: p["segments"]["k1"].pop("radius"), "kladný poloměr"),
    (lambda p: p["constraints"].append({"type": "concentric", "segments": ["k1", "s1"]}),
     "není oblouk nebo kružnice"),
    (lambda p: p["constraints"].append({"type": "equal", "segments": ["k1", "s1"]}),
     "stejně velké"),
    (lambda p: p["constraints"].append({"type": "symmetric", "points": ["K1", "K1"],
                                        "segment": "s1"}), "dva různé body"),
    (lambda p: p["constraints"].append({"type": "tangent", "segments": ["s1", "s3"]}),
     "jen s obloukem nebo kružnicí"),
    (lambda p: p["constraints"].append({"type": "diameter", "segment": "k1", "value": 0}),
     "kladná"),
])
def test_circle_errors_are_czech(change, message):
    profile = plate(holes={"k1": (20, 15, 5)})
    change(profile)
    with pytest.raises(SolveError, match=message):
        solve(profile, float)
