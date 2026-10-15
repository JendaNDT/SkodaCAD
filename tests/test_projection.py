"""Promítnutí hran dílu do skici: odkazy, vazby k nim, převzetí do obrysu, změna dílu."""

import copy
import math

import pytest
from build123d import Axis

from conftest import box_features, make_doc
from skodacad import rebuild
from skodacad.features import sketch_plane
from skodacad.profile_edit import (
    EditError,
    add_circle,
    add_point,
    add_reference,
    constraints_for,
    convert_references,
    empty_profile,
    kind_of,
    point_xy,
    remove,
)
from skodacad.projection import candidates, reference_for
from skodacad.solver import SolveError, solve

PARAMS = {"hx": 5}
FILLET_AREA = 4**2 - math.pi * 4**2 / 4  # co ubere zaoblení rohu R4 z půdorysu


def base_features():
    """Kvádr 40 × 30 × 10, díra Ø6 skrz v [hx, 3], zaoblený svislý roh vpravo vpředu R4."""
    return box_features(40, 30, 10) + [
        {"id": "d_s", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": 6, "center": ["hx", 3]}]},
        {"id": "dira", "type": "extrude", "sketch": "d_s", "operation": "cut",
         "through_all": True},
        {"id": "roh", "type": "fillet", "edges": {"between": ["front", "right"]}, "radius": 4},
    ]


def base_part(params=PARAMS):
    result = rebuild(make_doc(base_features(), params))
    assert result.ok
    return result.part


def top_candidates(part):
    plane = sketch_plane(part, {"plane": "top"}, PARAMS)
    return plane, candidates(part, plane)


def reference(part, plane, kind, near=None):
    """Odkaz na promítnutou hranu daného tvaru (nejbližší k bodu ``near``)."""
    found = [(edge, p) for edge, p in candidates(part, plane) if p.kind == kind]
    if near is not None:  # u úsečky rozhoduje její střed
        def where(p):
            if p.center is not None:
                return p.center
            (ax, ay), (bx, by) = p.points
            return (ax + bx) / 2, (ay + by) / 2

        found.sort(key=lambda item: math.dist(where(item[1]), near))
    return reference_for(part, found[0][0], plane)


def build_with(profile, operation="add", distance=5, params=PARAMS):
    return rebuild(make_doc(base_features() + [
        {"id": "skica", "type": "sketch", "plane": "top", "elements": [profile]},
        {"id": "vysunuti", "type": "extrude", "sketch": "skica", "operation": operation,
         "distance": distance},
    ], params))


def test_candidates_are_each_shape_once():
    part = base_part()
    _, found = top_candidates(part)
    kinds = sorted(p.kind for _, p in found)
    # horní a spodní obrys splynou, svislé hrany jsou jen body → 4 úsečky, oblouk, kružnice
    assert kinds == ["arc", "circle", "line", "line", "line", "line"]
    assert all(p.depth == pytest.approx(0) for _, p in found)  # vyhrály hrany na horní ploše
    [(_, arc)] = [(e, p) for e, p in found if p.kind == "arc"]
    assert arc.center == pytest.approx((16, -11)) and arc.radius == pytest.approx(4)
    # oblouk vede proti směru hodin: ze spodní hrany (y = −15) na pravou (x = 20)
    assert arc.points[0] == pytest.approx((16, -15)) and arc.points[1] == pytest.approx((20, -11))


def ring_around_hole(part):
    plane, _ = top_candidates(part)
    profile = empty_profile()
    hole = add_reference(profile, reference(part, plane, "circle"))
    outer = add_circle(profile, add_point(profile, 4, 4), 5)
    inner = add_circle(profile, add_point(profile, 6, 2), 2)
    profile["constraints"] += [
        {"type": "concentric", "segments": [outer, hole]},
        {"type": "concentric", "segments": [inner, hole]},
        {"type": "equal", "segments": [inner, hole]},
        {"type": "diameter", "segment": outer, "value": 12},
    ]
    return profile


def test_ring_around_projected_hole_follows_the_hole():
    profile = ring_around_hole(base_part())
    solved = solve(profile, float)
    assert solved.dof == 0
    assert solved.radii["k2"] == pytest.approx(3)  # stejný průměr jako díra
    expected = (40 * 30 - FILLET_AREA) * 10 - math.pi * 9 * 10 + math.pi * (36 - 9) * 5
    for hx in (5, -8):  # díra se posune parametrem – prstenec jde s ní
        result = build_with(profile, params={"hx": hx})
        assert result.ok, result.first_error and result.first_error.message
        assert result.part.volume == pytest.approx(expected)
        top = result.part.faces().sort_by(Axis.Z)[-1]
        assert (top.center().X, top.center().Y) == pytest.approx((hx, 3))


def test_convert_whole_top_face_into_outline():
    part = base_part()
    plane, found = top_candidates(part)
    profile = empty_profile()
    names = [add_reference(profile, reference_for(part, edge, plane)) for edge, _ in found]
    created = convert_references(profile, names)
    assert len(created) == 6 and len(profile["points"]) == 7  # 5 rohů obrysu + střed oblouku
    solved = solve(profile, float)                            # a střed kružnice
    assert solved.dof == 0
    result = build_with(profile, distance=2)
    assert result.ok, result.first_error and result.first_error.message
    top_area = 40 * 30 - FILLET_AREA - math.pi * 9  # i s dírou (kružnice uvnitř = díra)
    assert result.part.volume == pytest.approx(top_area * 10 + top_area * 2)


def test_point_on_projected_edge_and_distance_from_it():
    part = base_part()
    plane, _ = top_candidates(part)
    profile = empty_profile()
    left = add_reference(profile, reference(part, plane, "line", near=(-20, 0)))
    p = add_point(profile, -15, 5)
    add_circle(profile, p, 1)  # řešič chce aspoň jednu čáru
    profile["constraints"] += [
        {"type": "distance", "point": p, "segment": left, "value": 7},
        {"type": "coincident", "point": p, "on": f"{left}.start"},
    ]
    with pytest.raises(SolveError, match="odporují"):  # bod nemůže být na rohu a 7 mm od hrany
        solve(profile, float)
    profile["constraints"].pop()
    solved = solve(profile, float)
    assert abs(solved.points[p][0] - (-20)) == pytest.approx(7)


def test_constraints_only_between_fixed_things_are_refused():
    part = base_part()
    plane, _ = top_candidates(part)
    profile = empty_profile()
    add_circle(profile, add_point(profile, 1, 1), 1)
    hole = add_reference(profile, reference(part, plane, "circle"))
    profile["constraints"].append({"type": "coincident", "point": f"{hole}.center",
                                   "on": "origin"})
    with pytest.raises(SolveError, match="jen pevné prvky"):
        solve(profile, float)
    with pytest.raises(EditError, match="pevné"):
        constraints_for(profile, "coincident", [f"{hole}.center", "origin"])


def test_reference_helpers_and_removal():
    part = base_part()
    plane, _ = top_candidates(part)
    profile = empty_profile()
    data = reference(part, plane, "circle")
    hole = add_reference(profile, data)
    assert add_reference(profile, copy.deepcopy(data)) == hole  # stejná hrana podruhé ne
    assert kind_of(profile, hole) == "circle" and kind_of(profile, f"{hole}.center") == "point"
    assert point_xy(profile, f"{hole}.center") == pytest.approx((5, 3))
    circle = add_circle(profile, add_point(profile, 0, 0), 2)
    profile["constraints"].append({"type": "concentric", "segments": [circle, hole]})
    remove(profile, [f"{hole}.center"])  # bod promítnuté hrany smaže celou hranu
    assert not profile["references"] and profile["constraints"] == []
    assert circle in profile["segments"]


def test_vanished_edge_is_reported_in_czech():
    part = base_part()
    plane, _ = top_candidates(part)
    profile = ring_around_hole(part)
    broken = copy.deepcopy(profile)
    broken["references"]["r1"]["edge"] = {"face": "top", "type": "circle", "radius": 9}
    message = build_with(broken).first_error.message
    assert "Promítnutá hrana „r1“ už na dílu není" in message
    no_part = rebuild(make_doc([{"id": "s", "type": "sketch", "elements": [profile]}]))
    assert "žádný díl není" in no_part.first_error.message


@pytest.mark.parametrize(("rx", "ry"), [(80, 50), (60, 30)])
def test_standoffs_example_stay_on_holes(examples_dir, rx, ry):
    from skodacad import Document

    result = rebuild(Document.load(examples_dir / "sloupky.json"), {"rx": rx, "ry": ry})
    assert result.ok, result.first_error and result.first_error.message
    plate = 100 * 70 - (4 - math.pi) * 5**2  # zaoblené rohy R5
    hole = math.pi * 1.7**2  # průchozí M3 střední řada Ø3,4
    standoff = math.pi * (3.5**2 - 1.7**2)  # sloupek Ø7 s dírou Ø3,4
    assert result.part.volume == pytest.approx(plate * 3 - 4 * hole * 3 + 4 * standoff * 6)
    tops = [f for f in result.part.faces() if f.center().Z == pytest.approx(9)]
    centers = sorted((round(f.center().X, 6), round(f.center().Y, 6)) for f in tops)
    assert centers == sorted((sx * rx / 2, sy * ry / 2) for sx in (1, -1) for sy in (1, -1))
