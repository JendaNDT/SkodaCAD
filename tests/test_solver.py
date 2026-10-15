"""Skicář: obrys z úseček a oblouků, vazby řeší SolveSpace (slvs). Ověřujeme rozměry a objem."""

import copy
import math
import subprocess
import sys
import textwrap

import pytest

from conftest import make_doc
from skodacad import rebuild
from skodacad.schema import SHAPE_DEFAULTS
from skodacad.solver import CONSTRAINT_LABELS, SolveError, loops, solve


def rounded(points):
    return {name: (round(x, 6) + 0.0, round(y, 6) + 0.0) for name, (x, y) in points.items()}


def d_shape(width="sirka", radius=10):
    """Obdélník zakončený vpravo tečným půlkruhem; nakreslený schválně nepřesně."""
    return {
        "shape": "profile",
        "points": {"A": [0, 0], "B": [38, 2], "C": [41, 18], "M": [41, 10], "D": [-1, 21]},
        "segments": {
            "s1": {"type": "line", "start": "A", "end": "B"},
            "s2": {"type": "arc", "start": "B", "end": "C", "center": "M"},
            "s3": {"type": "line", "start": "C", "end": "D"},
            "s4": {"type": "line", "start": "D", "end": "A"},
        },
        "constraints": [
            {"type": "coincident", "point": "A", "on": "origin"},
            {"type": "horizontal", "segment": "s1"},
            {"type": "horizontal", "segment": "s3"},
            {"type": "vertical", "segment": "s4"},
            {"type": "length", "segment": "s1", "value": width},
            {"type": "radius", "segment": "s2", "value": radius},
            {"type": "tangent", "segments": ["s1", "s2"]},  # úsečka první – obal to otočí
            {"type": "tangent", "segments": ["s2", "s3"]},
        ],
    }


def extruded(profile, parameters, height=5):
    document = make_doc([
        {"id": "s", "type": "sketch", "plane": "XY", "elements": [profile]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": height},
    ], parameters)
    result = rebuild(document)
    assert result.ok, result.first_error
    return result.part


def test_rough_rectangle_snaps_to_exact_dimensions():
    result = solve(SHAPE_DEFAULTS["profile"], float)
    assert result.dof == 0
    assert rounded(result.points) == {"A": (0, 0), "B": (40, 0), "C": (40, 30), "D": (0, 30)}


def test_d_shape_is_fully_defined_and_tangent():
    result = solve(d_shape(), lambda v: 40 if v == "sirka" else float(v))
    assert result.dof == 0
    assert rounded(result.points) == {"A": (0, 0), "B": (40, 0), "C": (40, 20), "M": (40, 10),
                                      "D": (0, 20)}


@pytest.mark.parametrize("width", [40, 75])
def test_extruded_profile_volume_follows_parameter(width):
    part = extruded(d_shape(), {"sirka": width})
    assert part.volume == pytest.approx((width * 20 + math.pi * 10 ** 2 / 2) * 5)
    assert part.is_valid
    box = part.bounding_box()
    assert (box.min.X, box.max.X, box.max.Y) == pytest.approx((0, width + 10, 20))


def test_profile_can_be_a_hole():
    hole = d_shape(width=20, radius=5)
    hole["mode"] = "subtract"
    hole["center"] = [10, 10]
    document = make_doc([
        {"id": "s", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": 100, "height": 60, "center": [40, 20]}, hole]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 4},
    ])
    part = rebuild(document).part
    assert part.volume == pytest.approx((100 * 60 - (20 * 10 + math.pi * 25 / 2)) * 4)


def test_underdefined_profile_reports_missing_dimensions():
    profile = d_shape()
    profile["constraints"] = [c for c in profile["constraints"] if c["type"] != "length"]
    assert solve(profile, float).dof == 1  # chybí délka


def test_conflicting_constraints_are_named():
    profile = copy.deepcopy(SHAPE_DEFAULTS["profile"])
    profile["constraints"].append({"type": "length", "segment": "s3", "value": 50})
    with pytest.raises(SolveError, match="odporují") as error:
        solve(profile, float)
    assert error.value.failed  # okno je zvýrazní červeně


def test_conflict_shows_in_feature_tree_in_czech():
    profile = copy.deepcopy(SHAPE_DEFAULTS["profile"])
    profile["constraints"].append({"type": "length", "segment": "s3", "value": 50})
    result = rebuild(make_doc([{"id": "s", "type": "sketch", "elements": [profile]}]))
    assert result.first_error.message.startswith("Obrys: Vazby si odporují")


@pytest.mark.parametrize(("change", "message"), [
    (lambda p: (p["segments"].pop("s4"), p["constraints"].pop(4)), "volný konec"),
    (lambda p: p["segments"]["s1"].update(end="Z"), "bod „Z“"),
    (lambda p: p["segments"]["s1"].update(type="bezier"), "line"),
    (lambda p: p["constraints"].append({"type": "tangent", "segments": ["s1", "s2"]}),
     "jen s obloukem"),
    (lambda p: p["constraints"].append({"type": "radius", "segment": "s1", "value": 3}),
     "není oblouk"),
    (lambda p: p["constraints"].append({"type": "length", "segment": "s1"}), "chybí hodnota"),
    (lambda p: p["constraints"].append({"type": "length", "segment": "s1", "value": -2}),
     "kladná"),
    (lambda p: p["constraints"].append({"type": "sroubovice"}), "neznámý druh"),
    (lambda p: p["points"].update(origin=[1, 1]), "počátek"),
])
def test_bad_profiles_explain_in_czech(change, message):
    profile = copy.deepcopy(SHAPE_DEFAULTS["profile"])
    change(profile)
    with pytest.raises(SolveError, match=message):
        solve(profile, float)
        loops(profile, solve(profile, float).points)


def test_self_crossing_outline_is_refused():
    profile = copy.deepcopy(SHAPE_DEFAULTS["profile"])
    profile["points"] = {"A": [0, 0], "B": [10, 10], "C": [10, 0], "D": [0, 10]}
    profile["constraints"] = []
    result = rebuild(make_doc([{"id": "s", "type": "sketch", "elements": [profile]}]))
    assert "kříží" in result.first_error.message


def test_construction_line_is_not_part_of_outline():
    profile = copy.deepcopy(SHAPE_DEFAULTS["profile"])
    profile["segments"]["diag"] = {"type": "line", "start": "A", "end": "C",
                                   "construction": True}
    points = solve(profile, float).points
    assert [len(loop) for loop in loops(profile, points)] == [4]


def test_every_constraint_kind_in_both_orders_does_not_crash():
    """slvs při špatném volání shodí celý proces – proto zkouška v samostatném procesu."""
    script = textwrap.dedent("""
        import copy, itertools
        from skodacad.solver import solve, SolveError
        base = {
          "points": {"A": [0, 0], "B": [30, 1], "C": [30, 12], "M": [31, 6], "D": [0, 11],
                     "P": [15, 5], "Q": [20, 7], "K": [10, 5], "L": [18, 6]},
          "segments": {"l1": {"type": "line", "start": "A", "end": "B"},
                       "a1": {"type": "arc", "start": "B", "end": "C", "center": "M"},
                       "l2": {"type": "line", "start": "C", "end": "D"},
                       "l3": {"type": "line", "start": "D", "end": "A"},
                       "k1": {"type": "circle", "center": "K", "radius": 3},
                       "k2": {"type": "circle", "center": "L", "radius": 2}},
          "constraints": []}
        kinds = [
          {"type": "fix", "point": "A"},
          {"type": "coincident", "point": "A", "on": "origin"},
          {"type": "coincident", "point": "P", "on": "l1"},
          {"type": "coincident", "point": "P", "on": "a1"},
          {"type": "horizontal", "segment": "l1"},
          {"type": "horizontal", "points": ["A", "B"]},
          {"type": "vertical", "segment": "l3"},
          {"type": "vertical", "points": ["B", "C"]},
          {"type": "parallel", "segments": ["l1", "l2"]},
          {"type": "perpendicular", "segments": ["l1", "l3"]},
          {"type": "tangent", "segments": ["l1", "a1"]},
          {"type": "tangent", "segments": ["a1", "l2"]},
          {"type": "equal", "segments": ["l1", "l2"]},
          {"type": "midpoint", "point": "P", "segment": "l1"},
          {"type": "length", "segment": "l1", "value": 30},
          {"type": "distance", "points": ["A", "C"], "value": 20},
          {"type": "distance", "point": "P", "segment": "l2", "value": 4},
          {"type": "radius", "segment": "a1", "value": 6},
          {"type": "angle", "segments": ["l1", "l3"], "value": 90},
          # kružnice a vazby mezi tvary
          {"type": "coincident", "point": "P", "on": "k1"},
          {"type": "coincident", "point": "K", "on": "origin"},
          {"type": "tangent", "segments": ["l1", "k1"]},
          {"type": "tangent", "segments": ["a1", "k2"]},
          {"type": "tangent", "segments": ["k1", "k2"]},
          {"type": "tangent", "segments": ["l3", "a1"]},
          {"type": "equal", "segments": ["k1", "k2"]},
          {"type": "equal", "segments": ["a1", "k1"]},
          {"type": "concentric", "segments": ["k1", "a1"]},
          {"type": "concentric", "segments": ["k1", "k2"]},
          {"type": "symmetric", "points": ["P", "Q"], "segment": "l2"},
          {"type": "radius", "segment": "k1", "value": 4},
          {"type": "diameter", "segment": "k2", "value": 5},
          {"type": "diameter", "segment": "a1", "value": 12},
          {"type": "distance", "point": "K", "segment": "l1", "value": 6},
          {"type": "horizontal", "points": ["K", "L"]},
        ]
        seen = set()
        for constraint in kinds:
            for key in ("points", "segments"):
                if key in constraint:
                    for order in (constraint[key], constraint[key][::-1]):
                        variant = dict(constraint, **{key: order})
                        profile = copy.deepcopy(base)
                        profile["constraints"] = [variant]
                        try:
                            solve(profile, float)
                        except SolveError:
                            pass
            profile = copy.deepcopy(base)
            profile["constraints"] = [constraint]
            solve(profile, float)
            seen.add(constraint["type"])
        print(",".join(sorted(seen)))
    """)
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                         timeout=60)
    assert run.returncode == 0, f"řešič spadl: {run.stderr[-500:]}"
    assert set(run.stdout.strip().split(",")) == set(CONSTRAINT_LABELS)


def belt_area(length, big, small):
    """Plocha „pásu“ kolem dvou kružnic (tečny + výseče) – tvar páky."""
    phi = math.asin((big - small) / length)
    tangent = math.sqrt(length ** 2 - (big - small) ** 2)
    return ((big + small) * tangent + big ** 2 * (math.pi + 2 * phi) / 2
            + small ** 2 * (math.pi - 2 * phi) / 2)


@pytest.mark.parametrize("overrides", [{}, {"L": 120, "R": 25}, {"r": 6, "d2": 5}])
def test_lever_example_follows_parameters(examples_dir, overrides):
    from skodacad import Document

    document = Document.load(examples_dir / "paka.json")
    result = rebuild(document, overrides)
    assert result.ok, result.first_error
    p = {**document.parameters, **overrides}
    holes = math.pi * (p["d1"] ** 2 + p["d2"] ** 2) / 4
    expected = (belt_area(p["L"], p["R"], p["r"]) - holes) * p["t"]
    assert result.part.volume == pytest.approx(expected, rel=1e-6)
    box = result.part.bounding_box()
    assert (box.min.X, box.max.X) == pytest.approx((-p["R"], p["L"] + p["r"]))
