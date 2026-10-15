"""Úpravy obrysu pro skicář (bez okna): kreslení, mazání, vazby z výběru, kóty."""

import copy
import math

import pytest

from skodacad.profile_edit import (
    EditError,
    add_arc,
    add_line,
    add_point,
    arc_through,
    auto_constraints,
    constraints_for,
    empty_profile,
    measure,
    remove,
    toggle_construction,
)
from skodacad.schema import SHAPE_DEFAULTS
from skodacad.session import ModelSession


def triangle():
    profile = empty_profile()
    a, b, c = (add_point(profile, *xy) for xy in ((0, 0), (50, 0.5), (0.3, 30)))
    lines = [add_line(profile, a, b), add_line(profile, b, c), add_line(profile, c, a)]
    return profile, (a, b, c), lines


@pytest.fixture
def session():
    s = ModelSession()
    s.new_document()
    return s


def test_drawn_triangle_with_constraints_solves_exactly(session):
    profile, (a, b, c), (s1, s2, s3) = triangle()
    assert (a, b, c, s1, s2, s3) == ("P1", "P2", "P3", "s1", "s2", "s3")
    profile["constraints"] += auto_constraints(profile, s1) + auto_constraints(profile, s3)
    assert profile["constraints"] == [{"type": "horizontal", "segment": "s1"},
                                      {"type": "vertical", "segment": "s3"}]
    profile["constraints"] += constraints_for(profile, "coincident", [a, "origin"])
    for line, value in ((s1, 50), (s3, 30)):
        [dimension] = constraints_for(profile, "dimension", [line])
        assert dimension["value"] == pytest.approx(measure(profile, dimension))
        dimension["value"] = value
        profile["constraints"].append(dimension)
    solution = session.solve_profile(profile)
    assert solution.ok and solution.dof == 0
    assert solution.points[b] == pytest.approx((50, 0))
    assert solution.points[c] == pytest.approx((0, 30))


def test_arc_through_three_points_orientation():
    center, ccw = arc_through((10, 0), (-10, 0), (0, 10))  # horní půlkruh zprava doleva
    assert center == pytest.approx((0, 0)) and ccw
    center, ccw = arc_through((10, 0), (-10, 0), (0, -10))  # dolní: musí se prohodit
    assert not ccw
    with pytest.raises(EditError, match="přímce"):
        arc_through((0, 0), (10, 0), (5, 0))


def test_rounded_end_with_tangent_arc(session):
    profile = empty_profile()
    p = [add_point(profile, *xy) for xy in ((0, 0), (40, 0), (40, 20), (0, 20))]
    center, ccw = arc_through((40, 0), (40, 20), (50, 10))
    assert ccw
    m = add_point(profile, *center)
    s1, s3, s4 = add_line(profile, p[0], p[1]), add_line(profile, p[2], p[3]), \
        add_line(profile, p[3], p[0])
    arc = add_arc(profile, p[1], p[2], m)
    profile["constraints"] = [
        *constraints_for(profile, "coincident", ["origin", p[0]]),
        *constraints_for(profile, "horizontal", [s1]),
        *constraints_for(profile, "horizontal", [s3]),
        *constraints_for(profile, "vertical", [s4]),
        *constraints_for(profile, "tangent", [s1, arc]),
        *constraints_for(profile, "tangent", [arc, s3]),
        {**constraints_for(profile, "dimension", [s1])[0], "value": 60},
        {**constraints_for(profile, "dimension", [arc])[0], "value": 15},
    ]
    solution = session.solve_profile(profile)
    assert solution.ok and solution.dof == 0, solution.message
    assert solution.points[p[2]] == pytest.approx((60, 30))
    assert solution.points[m] == pytest.approx((60, 15))


@pytest.mark.parametrize(("kind", "selection", "message"), [
    ("horizontal", ["s1", "s2"], "jednu úsečku nebo dva body"),
    ("parallel", ["s1"], "dvě úsečky"),
    ("tangent", ["s1", "s2"], "oblouk"),
    ("midpoint", ["P1", "P2"], "bod a úsečku"),
    ("fix", ["origin"], "bodů"),
    ("dimension", ["P1", "s1", "s2"], "úsečku"),
    ("equal", ["neni", "s1"], "už v obrysu není"),
])
def test_wrong_selection_says_what_to_select(kind, selection, message):
    profile, _, _ = triangle()
    with pytest.raises(EditError, match=message):
        constraints_for(profile, kind, selection)


def test_dimensions_by_selection():
    profile, (a, b, c), (s1, s2, s3) = triangle()
    assert constraints_for(profile, "dimension", [a, c]) == [
        {"type": "distance", "points": [a, c], "value": 30}]
    [angle] = constraints_for(profile, "dimension", [s1, s3])
    assert angle["type"] == "angle" and angle["value"] == pytest.approx(91.15, abs=0.01)
    [distance] = constraints_for(profile, "dimension", [c, s1])
    assert distance == {"type": "distance", "point": c, "segment": s1,
                        "value": 30}  # 29.996 → zaokrouhleno


def test_remove_point_takes_lines_and_constraints_with_it():
    profile = copy.deepcopy(SHAPE_DEFAULTS["profile"])
    remove(profile, ["B"])
    assert set(profile["segments"]) == {"s3", "s4"}
    assert set(profile["points"]) == {"A", "C", "D"}
    assert all("s1" not in str(c) and "s2" not in str(c) for c in profile["constraints"])
    remove(profile, ["s3"])
    assert set(profile["points"]) == {"A", "D"}  # C zůstal bez čáry → pryč


def test_construction_toggle():
    profile, _, (s1, _, _) = triangle()
    toggle_construction(profile, [s1])
    assert profile["segments"][s1]["construction"] is True
    toggle_construction(profile, [s1])
    assert "construction" not in profile["segments"][s1]
    with pytest.raises(EditError):
        toggle_construction(profile, ["P1"])


def test_session_reports_errors_without_exception(session):
    profile = copy.deepcopy(SHAPE_DEFAULTS["profile"])
    profile["constraints"].append({"type": "length", "segment": "s3", "value": 99})
    solution = session.solve_profile(profile)
    assert not solution.ok and "odporují" in solution.message and solution.failed
    profile["constraints"][-1]["value"] = "neexistuje * 2"
    assert "neznámý parametr" in session.solve_profile(profile).message


def test_add_feature_with_values_is_one_undo_step(session):
    profile = copy.deepcopy(SHAPE_DEFAULTS["profile"])
    sketch = session.add_feature("sketch", values={"elements": [profile], "id": "jine"})
    assert sketch == "sketch1"  # id se přepsat nedá
    assert session.feature(sketch)["elements"][0]["shape"] == "profile"
    session.add_feature("extrude")
    assert session.properties.volume_mm3 == pytest.approx(40 * 30 * 10)
    session.undo()
    session.undo()
    assert session.document.features == []
    assert math.isclose(len(session.document.features), 0)
