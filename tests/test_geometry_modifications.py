"""P1.2A: úpravy hran/stěn, závěrečná pojistka a geometrický rollback prvku."""

import math
from dataclasses import replace
from types import SimpleNamespace

import pytest
from build123d import Box, Compound, Part, Pos, Rectangle

from conftest import box_features, make_doc
from skodacad import features as builders
from skodacad import rebuild
from skodacad.features import FEATURE_TYPES, VOLUME_FEATURES, BuildContext, FeatureError
from skodacad.geometry_validation import GeometryValidationError, inspect_volume
from skodacad.rebuild import _run_feature


def test_every_current_3d_type_is_classified_for_the_final_guard():
    assert set(FEATURE_TYPES) == VOLUME_FEATURES | {"sketch"}
    assert {"fillet", "chamfer", "shell"} <= VOLUME_FEATURES


@pytest.mark.parametrize(("kind", "key", "volume"), [
    ("fillet", "radius", 3000 + (4 - math.pi) * 10),
    ("chamfer", "distance", 3020),
])
def test_inner_corner_modifications_can_add_material(kind, key, volume):
    result = rebuild(make_doc([
        {"id": "s", "type": "sketch", "elements": [{"shape": "polygon", "points": [
            [0, 0], [20, 0], [20, 10], [10, 10], [10, 20], [0, 20],
        ]}]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 10},
        {"id": "edit", "type": kind, key: 2, "edges": {"near": [10, 10, 5]}},
    ]))
    assert result.ok, result.first_error
    facts = inspect_volume(result.part)
    assert facts.solids == 1 and facts.volume == pytest.approx(volume, abs=1e-6)
    assert facts.bounds == pytest.approx((0, 0, 0, 20, 20, 10), abs=1e-6)
    assert result.part.is_inside((10.5, 10.5, 5))
    assert not result.part.is_inside((15, 15, 5))
    before = result.parts_before["edit"]
    assert before.volume == pytest.approx(3000)
    assert not before.is_inside((10.5, 10.5, 5))


def test_chamfer_four_vertical_corners_matches_formula_and_preserves_body_count():
    result = rebuild(make_doc(box_features() + [
        {"id": "c", "type": "chamfer", "distance": 2, "edges": {"parallel": "Z"}},
    ]))
    assert result.ok
    facts = inspect_volume(result.part)
    assert facts.volume == pytest.approx(24000 - 4 * (2**2 / 2) * 40)
    assert facts.solids == 1
    assert result.part.is_inside((0, 0, 20)) and not result.part.is_inside((9.5, 14.5, 20))


def test_open_shell_keeps_envelope_floor_and_wall_material():
    result = rebuild(make_doc(box_features(50, 30, 20) + [
        {"id": "sh", "type": "shell", "thickness": 2, "open_faces": ["top"]},
    ]))
    assert result.ok
    facts = inspect_volume(result.part)
    assert facts.solids == 1 and facts.volume == pytest.approx(8472)
    assert facts.bounds == pytest.approx((-25, -15, 0, 25, 15, 20), abs=1e-6)
    assert result.part.is_inside((24, 0, 10)) and result.part.is_inside((0, 0, 1))
    assert not result.part.is_inside((22, 0, 10)) and not result.part.is_inside((0, 0, 3))


@pytest.mark.parametrize("values", [{}, {"open_faces": []},
                                    {"open_faces": ["top"], "thickness": 99}])
def test_shell_without_openings_or_with_impossible_wall_is_rejected(values):
    result = rebuild(make_doc(box_features(50, 30, 20) + [
        {"id": "sh", "type": "shell", "thickness": 2, **values},
        {"id": "tail", "type": "chamfer", "distance": 1, "edges": "all"},
    ]))
    assert not result.ok and result.first_error.id == "sh"
    if values.get("thickness") != 99:
        assert "alespoň jednu otevřenou plochu" in result.first_error.message
    assert result.statuses[-1].status == "skipped"
    facts = inspect_volume(result.part)
    assert facts.volume == pytest.approx(30000) and facts.solids == 1
    assert facts.bounds == pytest.approx((-25, -15, 0, 25, 15, 20), abs=1e-6)
    assert result.part.is_inside((0, 0, 10))  # plný původní díl, ne zmenšený náhradní kvádr


@pytest.mark.parametrize(("kind", "key"), [
    ("fillet", "radius"), ("chamfer", "distance"), ("shell", "thickness"),
])
@pytest.mark.parametrize("number", [0, -1, math.nan, math.inf])
def test_invalid_modification_dimensions_keep_previous_geometry(kind, key, number):
    result = rebuild(make_doc(box_features() + [
        {"id": "edit", "type": kind, key: number, "edges": "all", "open_faces": ["top"]},
        {"id": "tail", "type": "sketch", "elements": [{"shape": "circle", "diameter": 2}]},
    ]))
    assert result.first_error.id == "edit" and result.statuses[-1].status == "skipped"
    assert inspect_volume(result.part).volume == pytest.approx(24000)
    assert result.part.is_inside((0, 0, 20))


@pytest.mark.parametrize("bad", ["empty", "mixed", "two_bodies"])
def test_fillet_kernel_candidate_is_checked_before_assignment(monkeypatch, bad):
    original = Box(20, 30, 40)
    before = inspect_volume(original)
    if bad == "empty":
        candidate = Part()
    elif bad == "mixed":
        candidate = Compound([Box(20, 30, 40), Pos(100, 0, 0) * Rectangle(2, 2).faces()[0]])
    else:
        candidate = Compound([Box(5, 5, 10), Pos(100, 0, 0) * Box(5, 5, 10)])
    monkeypatch.setattr(builders, "fillet", lambda *_args, **_kwargs: candidate)
    ctx = BuildContext({}, part=original, recording=[])
    with pytest.raises(FeatureError) as error:
        builders.build_fillet(ctx, {"radius": 2, "edges": "all"})
    if bad == "two_bodies":
        assert "počet těles se změnil" in str(error.value)
    else:
        assert "poloměr je" not in str(error.value)  # skutečná příčina není velký poloměr
    assert ctx.part is original and inspect_volume(original) == before and ctx.recording == []


@pytest.mark.parametrize("bad", ["none", "empty", "mixed"])
def test_final_guard_rejects_a_builder_bypassing_the_acceptance_path(monkeypatch, bad):
    candidate = {"none": None, "empty": Part(), "mixed": Compound([
        Box(20, 30, 40), Pos(100, 0, 0) * Rectangle(2, 2).faces()[0],
    ])}[bad]

    def faulty(ctx, _feature):
        ctx.part = candidate

    monkeypatch.setitem(FEATURE_TYPES, "fillet", replace(FEATURE_TYPES["fillet"], build=faulty))
    result = rebuild(make_doc(box_features() + [
        {"id": "edit", "type": "fillet", "radius": 2, "edges": "all"},
        {"id": "tail", "type": "chamfer", "distance": 1, "edges": "all"},
    ]))
    assert result.first_error.id == "edit" and result.statuses[-1].status == "skipped"
    assert inspect_volume(result.part).volume == pytest.approx(24000)
    assert result.part.is_inside((0, 0, 20))


def test_unchanged_identity_does_not_bypass_guard_and_sketch_only_is_valid(monkeypatch):
    monkeypatch.setitem(FEATURE_TYPES, "fillet", replace(FEATURE_TYPES["fillet"],
                                                       build=lambda _ctx, _f: None))
    original = Part()  # vadný vstup řízeně předaný mimo běžný přepočet
    ctx = BuildContext({}, part=original)
    message = _run_feature(ctx, {"id": "edit", "type": "fillet"})
    assert message is not None and "nemá žádný objem" in message
    assert ctx.part is original
    result = rebuild(make_doc([box_features()[0]]))
    assert result.ok and result.part is None and "s" in result.sketches


def test_wrong_union_volume_is_not_accepted_or_recorded(monkeypatch):
    original = Box(20, 30, 40)
    tool = Pos(100, 0, 0) * Box(5, 5, 10)
    wrong = Box(40, 40, 40)
    monkeypatch.setattr(type(original), "__add__", lambda _self, _other: wrong)
    ctx = BuildContext({}, part=original, recording=[])
    with pytest.raises(FeatureError, match="větší objem, než dovolují vstupy"):
        ctx.apply(tool, "add", "Vysunutí")
    assert ctx.part is original and ctx.recording == [] and original.volume == pytest.approx(24000)


def test_nonfinite_kernel_bounds_are_rejected(monkeypatch):
    part = Box(20, 30, 40)
    monkeypatch.setattr(part, "bounding_box", lambda **_kwargs: SimpleNamespace(
        min=(math.nan, -15, -20), max=(10, 15, 20)))
    with pytest.raises(GeometryValidationError, match="konečné souřadnice"):
        inspect_volume(part)


def test_late_pattern_failure_restores_geometry_before_the_whole_feature():
    features = box_features(100, 80, 10)
    for name, x in (("h1", -20), ("h2", 45)):
        features.extend([
            {"id": name + "s", "type": "sketch", "plane": "top", "elements": [
                {"shape": "circle", "diameter": 4, "center": [x, 0]},
            ]},
            {"id": name, "type": "extrude", "sketch": name + "s", "distance": 5,
             "operation": "cut"},
        ])
    result = rebuild(make_doc(features + [
        {"id": "p", "type": "pattern", "features": ["h1", "h2"], "kind": "linear",
         "direction": "X", "count": 2, "spacing": 20},
        {"id": "tail", "type": "chamfer", "distance": 1, "edges": "all"},
    ]))
    assert result.first_error.id == "p" and result.statuses[-1].status == "skipped"
    assert inspect_volume(result.part).volume == pytest.approx(80000 - 40 * math.pi)
    assert result.part.is_inside((0, 0, 7.5))  # první kopie se nesměla částečně přijmout
    assert not result.part.is_inside((-20, 0, 7.5))
    assert not result.part.is_inside((45, 0, 7.5))
    assert inspect_volume(result.part) == inspect_volume(result.parts_before["p"])
