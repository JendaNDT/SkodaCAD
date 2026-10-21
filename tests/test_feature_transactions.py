"""P1.2B: vlastnictví pracovních dat a přijetí celého prvku."""

import copy
import math
from dataclasses import fields

import pytest
from build123d import Align, Box, Plane, Pos, Rectangle

from skodacad.features import BuildContext, FeatureError
from skodacad.geometry_validation import inspect_volume


@pytest.fixture
def accepted_context():
    part = Box(20, 30, 40, align=(Align.CENTER, Align.CENTER, Align.MIN))
    tool = Box(2, 3, 4)
    return BuildContext(
        {"t": 40.0, "n": 2.0}, part=part,
        sketches={"s": (Plane.XY.offset(3), Rectangle(4, 6))},
        operations={"base": [(part, "add")], "cut": [(tool, "cut")], "sketch": []},
        recording=[(tool, "cut")])


def feature_input():
    return {"id": "next", "type": "sketch", "elements": [
        {"shape": "rectangle", "width": 1, "height": 2}],
        "metadata": {"values": [1, 2], "active": True}}


def snapshot(ctx):
    """Hodnoty uložené před výpočtem; pozdější změna aliasu je nemůže přepsat."""
    return {
        "params": tuple(ctx.params.items()), "part": inspect_volume(ctx.part),
        "sketches": [(key, tuple(p.origin), tuple(p.x_dir), tuple(p.z_dir), s.area,
                      tuple(s.bounding_box().min), tuple(s.bounding_box().max))
                     for key, (p, s) in ctx.sketches.items()],
        "operations": [(key, [(inspect_volume(tool), mode) for tool, mode in ops])
                       for key, ops in ctx.operations.items()],
        "recording": None if ctx.recording is None else [
            (inspect_volume(tool), mode) for tool, mode in ctx.recording],
    }


def test_every_context_field_is_accounted_for():
    assert {f.name for f in fields(BuildContext)} == {
        "params", "part", "sketches", "operations", "recording"}


def test_candidate_container_changes_cannot_mutate_accepted_aliases(accepted_context):
    ctx = accepted_context
    original, before = feature_input(), snapshot(ctx)
    aliases = (ctx.params, ctx.sketches, ctx.operations, ctx.operations["base"], ctx.recording)
    candidate, data = ctx._fork_for_feature(original)
    assert candidate.part is ctx.part
    assert candidate.sketches["s"] is ctx.sketches["s"]  # tvary/roviny se jen čtou
    candidate.params["t"] = 99
    del candidate.sketches["s"]
    candidate.sketches["leak"] = (Plane.YZ, Rectangle(1, 1))
    candidate.operations["base"].clear()
    candidate.operations["extra"] = []
    candidate.recording.append((ctx.part, "add"))
    candidate.part = Box(1, 1, 1)
    data["metadata"]["values"].append(3)
    assert snapshot(ctx) == before
    assert aliases == (ctx.params, ctx.sketches, ctx.operations,
                       ctx.operations["base"], ctx.recording)
    assert original == feature_input()


@pytest.mark.parametrize("change", ["value", "type", "order"])
def test_changed_working_parameters_are_rejected_before_any_publication(accepted_context, change):
    ctx, original = accepted_context, feature_input()
    before = snapshot(ctx)
    candidate, data = ctx._fork_for_feature(original)
    candidate.part = Box(1, 1, 1)
    if change == "value":
        candidate.params["t"] = 41.0
    elif change == "type":
        candidate.params["n"] = 2  # stejná číselná hodnota, jiný vstupní typ
    else:
        candidate.params = dict(reversed(list(candidate.params.items())))
    with pytest.raises(FeatureError, match="vstupní parametry"):
        ctx._accept_feature(candidate, original, data)
    assert snapshot(ctx) == before


@pytest.mark.parametrize("change", ["nested", "boolean", "key", "order"])
def test_changed_nested_json_is_rejected_without_mutating_the_source(accepted_context, change):
    ctx, original = accepted_context, feature_input()
    before = snapshot(ctx)
    candidate, data = ctx._fork_for_feature(original)
    if change == "nested":
        data["metadata"]["values"].append(3)
    elif change == "boolean":
        data["elements"][0]["width"] = True  # True == 1, ale zadání není stejné
    elif change == "key":
        data["metadata"]["new"] = 1
    else:
        data["metadata"] = dict(reversed(list(data["metadata"].items())))
    candidate.part = Box(1, 1, 1)
    with pytest.raises(FeatureError, match="změnil své zadání"):
        ctx._accept_feature(candidate, original, data)
    assert snapshot(ctx) == before and original == feature_input()


def test_unchanged_unused_nan_does_not_mask_the_existing_geometry_rules(accepted_context):
    original = feature_input()
    original["metadata"]["unused"] = math.nan
    candidate, data = accepted_context._fork_for_feature(original)
    accepted_context._accept_feature(candidate, original, data)
    assert accepted_context.operations["next"] == []


def test_success_records_all_operations_once_and_preserves_older_aliases(accepted_context):
    ctx, original = accepted_context, feature_input()
    aliases = (ctx.params, ctx.operations["base"], ctx.operations["cut"], ctx.recording)
    before = snapshot(ctx)
    candidate, data = ctx._fork_for_feature(original)
    tool1, tool2 = Box(1, 2, 3), Box(2, 3, 4)
    candidate.recording.extend([(tool1, "add"), (tool2, "cut")])
    ctx._accept_feature(candidate, original, data)
    assert list(ctx.operations) == ["base", "cut", "sketch", "next"]
    assert ctx.operations["next"] == [(tool1, "add"), (tool2, "cut")]
    candidate.recording.clear()
    assert len(ctx.operations["next"]) == 2  # seznam už není pracovní recording
    assert ctx.params is aliases[0] and ctx.recording is aliases[3]
    assert aliases[1] == [(ctx.part, "add")]
    assert snapshot(ctx)["operations"][:-1] == before["operations"]


def test_mutation_of_an_owned_shape_copy_cannot_change_original_geometry(accepted_context):
    ctx, original = accepted_context, feature_input()
    before = snapshot(ctx)
    candidate, _data = ctx._fork_for_feature(original)
    candidate.part = copy.deepcopy(candidate.part)
    candidate.part.move(Pos(100, 0, 0))
    plane, sketch = candidate.sketches["s"]
    candidate.sketches["s"] = (copy.deepcopy(plane), copy.deepcopy(sketch))
    candidate.sketches["s"][1].move(Pos(200, 0, 0))
    assert candidate.part.is_inside((100, 0, 20))
    assert not candidate.part.is_inside((0, 0, 20))
    assert snapshot(ctx) == before and ctx.part.is_inside((0, 0, 20))


def test_missing_recording_rejects_before_publication(accepted_context):
    ctx, original = accepted_context, feature_input()
    before = snapshot(ctx)
    candidate, data = ctx._fork_for_feature(original)
    candidate.part, candidate.recording = Box(1, 1, 1), None
    with pytest.raises(FeatureError, match="chybí záznam"):
        ctx._accept_feature(candidate, original, data)
    assert snapshot(ctx) == before
