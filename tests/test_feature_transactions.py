"""P1.2B: vlastnictví pracovních dat a přijetí celého prvku."""

import copy
import math
from dataclasses import fields, replace

import pytest
from build123d import Align, Box, Compound, Part, Plane, Pos, Rectangle

from conftest import box_features, make_doc
from skodacad import features as builders
from skodacad import rebuild
from skodacad.expressions import ExpressionError
from skodacad.features import FEATURE_TYPES, BuildContext, FeatureError
from skodacad.geometry_validation import GeometryValidationError, inspect_volume
from skodacad.rebuild import _run_feature
from skodacad.selectors import SelectionError


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
        "params", "part", "sketches", "operations", "recording", "history"}


def test_candidate_cannot_change_history_of_accepted_parts(accepted_context):
    """P2.3: historie dílů pro pojistku původu je v kandidátovi jen ke čtení."""
    ctx = accepted_context
    ctx.history.append(("base", ctx.part))
    candidate, _ = ctx._fork_for_feature(feature_input())
    assert candidate.history == tuple(ctx.history)
    with pytest.raises(AttributeError):
        candidate.history.append(("leak", None))
    assert ctx.history == [("base", ctx.part)]


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


@pytest.mark.parametrize("error_type", [FeatureError, ExpressionError, SelectionError,
                                       GeometryValidationError, RuntimeError])
def test_whole_feature_failure_discards_all_context_changes(accepted_context, monkeypatch,
                                                          error_type):
    ctx, original = accepted_context, feature_input()
    before = snapshot(ctx)
    aliases = (ctx.params, ctx.part, ctx.sketches, ctx.operations,
               ctx.operations["base"], ctx.recording)

    def fail(candidate, data):
        candidate.params["t"] = 41
        candidate.part = Box(1, 1, 1)
        del candidate.sketches["s"]
        candidate.sketches["leak"] = (Plane.YZ, Rectangle(1, 1))
        candidate.operations["base"].clear()
        candidate.operations["leak"] = [(candidate.part, "add")]
        candidate.recording.append((candidate.part, "cut"))
        data["metadata"]["values"].append(3)
        raise error_type("Řízená pozdní chyba.")

    monkeypatch.setitem(FEATURE_TYPES, "sketch", replace(FEATURE_TYPES["sketch"], build=fail))
    message = _run_feature(ctx, original)
    assert "Řízená pozdní chyba." in message
    assert ("Neočekávaná chyba jádra" in message) == (error_type is RuntimeError)
    assert snapshot(ctx) == before and original == feature_input()
    assert all(a is b for a, b in zip(aliases, (
        ctx.params, ctx.part, ctx.sketches, ctx.operations,
        ctx.operations["base"], ctx.recording), strict=True))
    assert "next" not in ctx.operations and "leak" not in ctx.sketches


@pytest.mark.parametrize("kind", ["linear", "circular", "mirror"])
def test_complete_recording_is_replayed_once_in_original_order(accepted_context, monkeypatch,
                                                             kind):
    ctx = accepted_context
    original = {"id": "boss", "type": "extrude"}
    tool1 = Pos(20, 0, 0) * Box(10, 10, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
    tool2 = Pos(20, 0, 0) * Box(2, 2, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))
    tools_before = [inspect_volume(s) for s in (ctx.part, tool1, tool2)]
    old_recording = ctx.recording
    older_lists = (ctx.operations["base"], ctx.operations["cut"])

    def two_operations(candidate, _data):
        candidate.apply(tool1, "add", "Výstupek")
        candidate.apply(tool2, "cut", "Otvor")

    with monkeypatch.context() as patch:
        patch.setitem(FEATURE_TYPES, "extrude",
                      replace(FEATURE_TYPES["extrude"], build=two_operations))
        assert _run_feature(ctx, original) is None
    assert ctx.part.volume == pytest.approx(24980)
    assert len(ctx.part.solids()) == 2
    assert [mode for _, mode in ctx.operations["boss"]] == ["add", "cut"]
    source_ops = ctx.operations["boss"]
    if kind == "mirror":
        repeated = {"id": "copy", "type": "mirror", "features": ["boss"], "plane": "YZ"}
        point = (-20, 0, 2)
    elif kind == "circular":
        repeated = {"id": "copy", "type": "pattern", "features": ["boss"],
                    "kind": "circular", "count": 2, "axis": "Z"}
        point = (-20, 0, 2)
    else:
        repeated = {"id": "copy", "type": "pattern", "features": ["boss"],
                    "kind": "linear", "count": 2, "direction": "Y", "spacing": 50}
        point = (20, 50, 2)
    assert _run_feature(ctx, repeated) is None
    assert ctx.part.volume == pytest.approx(25960)
    assert len(ctx.part.solids()) == 3
    assert not ctx.part.is_inside(point) and ctx.part.is_inside((0, 0, 20))
    assert [mode for _, mode in ctx.operations["copy"]] == ["add", "cut"]
    assert source_ops == [(tool1, "add"), (tool2, "cut")]
    assert ctx.recording is old_recording
    assert [inspect_volume(s) for s in (older_lists[0][0][0], tool1, tool2)] == tools_before


@pytest.mark.parametrize("with_part", [False, True])
def test_failed_sketch_is_not_published_in_build_result(monkeypatch, with_part):
    real_build = FEATURE_TYPES["sketch"].build

    def late_failure(ctx, feature):
        real_build(ctx, feature)
        if feature["id"] == "bad":
            assert "bad" in ctx.sketches
            raise FeatureError("Pozdní chyba skici.")

    monkeypatch.setitem(FEATURE_TYPES, "sketch",
                        replace(FEATURE_TYPES["sketch"], build=late_failure))
    features = box_features() if with_part else []
    features += [
        {"id": "bad", "type": "sketch", "elements": [
            {"shape": "rectangle", "width": 2, "height": 3}]},
        {"id": "tail", "type": "sketch", "elements": [
            {"shape": "circle", "diameter": 2}]},
    ]
    result = rebuild(make_doc(features))
    assert result.first_error.id == "bad" and result.statuses[-1].status == "skipped"
    assert set(result.sketches) == ({"s"} if with_part else set())
    if with_part:
        assert result.part.volume == pytest.approx(24000)
        assert result.parts_before["bad"] is result.part
    else:
        assert result.part is None
    valid = rebuild(make_doc([box_features()[0]]))
    assert valid.ok and valid.part is None and set(valid.sketches) == {"s"}


@pytest.mark.parametrize("bad", ["none", "empty", "mixed"])
def test_final_volume_guard_rejects_metadata_together_with_bad_geometry(accepted_context,
                                                                     monkeypatch, bad):
    ctx = accepted_context
    original = {**feature_input(), "type": "extrude"}
    before = snapshot(ctx)
    invalid = {"none": None, "empty": Part(), "mixed": Compound([
        Box(1, 1, 1), Pos(100, 0, 0) * Rectangle(1, 1).faces()[0]])}[bad]

    def unchecked(candidate, _data):
        candidate.part = invalid
        candidate.sketches["leak"] = (Plane.XY, Rectangle(1, 1))
        candidate.operations["base"].clear()
        candidate.recording.append((ctx.part, "add"))

    monkeypatch.setitem(FEATURE_TYPES, "extrude",
                        replace(FEATURE_TYPES["extrude"], build=unchecked))
    assert _run_feature(ctx, original) is not None
    assert snapshot(ctx) == before and "next" not in ctx.operations


@pytest.mark.parametrize("kind", ["pattern", "mirror"])
def test_real_late_failure_restores_operations_and_material(monkeypatch, kind):
    order = [-20, 45] if kind == "pattern" else [45, -20]
    features = box_features(100, 80, 10)
    for i, x in enumerate(order):
        features.extend([
            {"id": f"s{i}", "type": "sketch", "plane": "top", "elements": [
                {"shape": "circle", "diameter": 4, "center": [x, 0]}]},
            {"id": f"h{i}", "type": "extrude", "sketch": f"s{i}",
             "distance": 5, "operation": "cut"},
        ])
    ctx = BuildContext({})
    for feature in features:
        assert _run_feature(ctx, feature) is None
    before, parent_part = snapshot(ctx), ctx.part
    old_lists = list(ctx.operations.values())
    source = {"id": "bad", "type": kind, "features": ["h0", "h1"]}
    source.update({"kind": "linear", "direction": "X", "count": 2, "spacing": 20}
                  if kind == "pattern" else {"plane": "YZ", "offset": 20})
    real_apply = BuildContext.apply
    partial = []

    def observe(candidate, *args, **kwargs):
        result = real_apply(candidate, *args, **kwargs)
        partial.append((candidate.part.volume, len(candidate.recording)))
        assert snapshot(ctx) == before  # rodič se nemění ani mezi podoperacemi
        return result

    with monkeypatch.context() as patch:
        patch.setattr(BuildContext, "apply", observe)
        assert _run_feature(ctx, source) is not None
    assert len(partial) == 1 and partial[0][1] == 1
    assert partial[0][0] == pytest.approx(80000 - 60 * math.pi)
    assert snapshot(ctx) == before and ctx.part is parent_part
    assert all(old == now for old, now in zip(old_lists, ctx.operations.values(), strict=True))
    assert ctx.part.volume == pytest.approx(80000 - 40 * math.pi)
    assert ctx.part.is_inside((0 if kind == "pattern" else -5, 0, 7.5))
    assert not ctx.part.is_inside((-20, 0, 7.5))
    assert not ctx.part.is_inside((45, 0, 7.5))
    fixed = copy.deepcopy(source)
    fixed["spacing" if kind == "pattern" else "offset"] = -20 if kind == "pattern" else 0
    assert _run_feature(ctx, fixed) is None
    assert ctx.part.volume == pytest.approx(80000 - 80 * math.pi)
    assert len(ctx.part.solids()) == 1
    assert len(ctx.operations["bad"]) == 2


def test_thread_failure_after_drilling_discards_the_entire_hole(accepted_context, monkeypatch):
    ctx = accepted_context
    before = snapshot(ctx)
    captured = []
    real_build = FEATURE_TYPES["hole"].build

    def observe(candidate, feature):
        captured.append(candidate)
        real_build(candidate, feature)

    def fail_thread(*_args, **_kwargs):
        candidate = captured[0]
        assert candidate.part.volume < 24000 and len(candidate.recording) == 1
        assert not candidate.part.is_inside((0, 0, 38))
        assert snapshot(ctx) == before
        raise FeatureError("Pozdní chyba závitové drážky.")

    monkeypatch.setitem(FEATURE_TYPES, "hole", replace(FEATURE_TYPES["hole"], build=observe))
    monkeypatch.setattr(builders, "_thread_tool", fail_thread)
    message = _run_feature(ctx, {"id": "thread", "type": "hole", "kind": "tapped",
                                 "size": "M6", "plane": "top", "positions": [[0, 0]],
                                 "depth": 8, "modeled_thread": True})
    assert message == "Pozdní chyba závitové drážky."
    assert snapshot(ctx) == before and ctx.part.is_inside((0, 0, 38))
    assert "thread" not in ctx.operations


def test_unknown_type_never_prepares_a_candidate_and_preserves_state(accepted_context, monkeypatch):
    ctx, before = accepted_context, snapshot(accepted_context)

    def forbidden(*_args):
        pytest.fail("Neznámý typ nesmí připravovat kandidáta.")

    monkeypatch.setattr(BuildContext, "_fork_for_feature", forbidden)
    assert "Neznámý typ" in _run_feature(ctx, {"id": "bad", "type": "unknown"})
    assert snapshot(ctx) == before


def test_candidate_preparation_failure_is_reported_without_changes(accepted_context, monkeypatch):
    ctx, before = accepted_context, snapshot(accepted_context)

    def fail(*_args):
        raise RuntimeError("Nelze připravit kandidáta.")

    monkeypatch.setattr(BuildContext, "_fork_for_feature", fail)
    message = _run_feature(ctx, feature_input())
    assert "Neočekávaná chyba jádra" in message and "Nelze připravit" in message
    assert snapshot(ctx) == before


@pytest.mark.parametrize("change", ["params", "json", "boolean"])
def test_successful_return_does_not_accept_hidden_input_changes(accepted_context, monkeypatch,
                                                              change):
    ctx, original = accepted_context, feature_input()
    before = snapshot(ctx)

    def mutate(candidate, data):
        candidate.sketches["leak"] = (Plane.YZ, Rectangle(1, 1))
        if change == "params":
            candidate.params["t"] = 99
        elif change == "json":
            data["metadata"]["values"].append(3)
        else:
            data["elements"][0]["width"] = True

    monkeypatch.setitem(FEATURE_TYPES, "sketch", replace(FEATURE_TYPES["sketch"], build=mutate))
    assert "Vnitřní chyba prvku" in _run_feature(ctx, original)
    assert snapshot(ctx) == before and original == feature_input()
