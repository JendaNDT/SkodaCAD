"""P1.2A: objemová smlouva, prostorový účinek a nepřijetí vadného kandidáta."""

import math

import pytest
from build123d import Align, Box, Compound, Cylinder, Edge, Part, Pos, Rectangle, Shell, Solid
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS_Compound

from conftest import make_doc
from skodacad import rebuild
from skodacad.features import BuildContext, FeatureError
from skodacad.geometry_validation import (
    GeometryValidationError,
    VolumeFacts,
    check_boolean,
    check_cut_volume,
    inspect_volume,
)


def block(width=20, depth=30, height=40, origin=(0, 0, 0)):
    return Pos(*origin) * Box(width, depth, height, align=(Align.MIN,) * 3)


def bad_shape(kind):
    if kind == "empty":
        return Part()
    if kind == "surface":
        return Rectangle(2, 2).faces()[0]
    if kind == "open":
        box = Box(20, 30, 40)
        return Solid(Shell([face for face in box.faces() if face.center().Z < 19]))
    if kind == "face":
        return Compound([block(), Pos(100, 0, 0) * Rectangle(2, 2).faces()[0]])
    if kind == "edge":
        return Compound([block(), Edge.make_line((100, 0, 0), (101, 0, 0))])
    if kind == "empty_component":
        empty = TopoDS_Compound()
        BRep_Builder().MakeCompound(empty)
        return Compound([block(), Compound(empty)])
    if kind == "small_component":
        return Compound([block(), block(0.0001, 0.0001, 0.0001, (100, 0, 0))])
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", [
    "empty", "surface", "open", "face", "edge", "empty_component", "small_component",
])
def test_bad_volume_tool_is_rejected_whole_without_changing_part_or_recording(kind):
    original = block()
    before = inspect_volume(original)
    ctx = BuildContext({}, part=original, recording=[(original, "add")])
    tool = bad_shape(kind)
    with pytest.raises(GeometryValidationError):
        inspect_volume(tool)
    with pytest.raises(FeatureError, match="Vysunutí:"):
        ctx.apply(tool, "add", "Vysunutí")
    assert ctx.part is original and inspect_volume(original) == before
    assert len(ctx.recording) == 1 and ctx.recording[0][0] is original
    assert original.is_inside((10, 15, 20))


def test_empty_part_is_valid_in_kernel_but_is_not_a_volume():
    empty = Part()
    assert empty.is_valid and empty.volume == 0 and len(empty.solids()) == 0
    ctx = BuildContext({}, recording=[])
    with pytest.raises(FeatureError, match="nemá žádný objem"):
        ctx.apply(empty, "new", "Vysunutí")
    assert ctx.part is None and ctx.recording == []


def test_open_shell_can_have_positive_volume_without_being_acceptable():
    open_solid = bad_shape("open")
    assert open_solid.volume == pytest.approx(19200)
    with pytest.raises(GeometryValidationError):
        inspect_volume(open_solid)


def test_incomplete_volume_of_nested_container_cannot_silently_drop_a_body():
    nested = Compound([Compound([block()]), block(5, 5, 10, (100, 0, 0))])
    assert len(nested.solids()) == 2
    assert sum(s.volume for s in nested.solids()) == pytest.approx(24250)
    # build123d 0.13 čte objem Compound přes get_type, které vnořený compound vynechá.
    assert nested.volume == pytest.approx(250)
    with pytest.raises(GeometryValidationError, match="objem celku neodpovídá"):
        inspect_volume(nested)


def test_valid_separate_solids_and_a_closed_cavity_are_preserved():
    separated = Compound([block(), block(5, 5, 10, (100, 0, 0))])
    facts = inspect_volume(separated)
    assert facts.solids == 2 and facts.volume == pytest.approx(24250)
    hollow = block() - block(10, 20, 30, (5, 5, 5))
    facts = inspect_volume(hollow)
    assert facts.solids == 1 and facts.volume == pytest.approx(18000)
    assert not hollow.is_inside((10, 15, 20)) and hollow.is_inside((2, 15, 20))


@pytest.mark.parametrize("operation", ["new", "add"])
def test_first_body_and_two_separate_sketch_regions_are_supported(operation):
    result = rebuild(make_doc([
        {"id": "s", "type": "sketch", "elements": [
            {"shape": "circle", "diameter": 10, "center": [-15, 0]},
            {"shape": "circle", "diameter": 10, "center": [15, 0]},
        ]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 10,
         "operation": operation},
    ]))
    assert result.ok
    facts = inspect_volume(result.part)
    assert facts.solids == 2 and facts.volume == pytest.approx(500 * math.pi)
    assert facts.bounds == pytest.approx((-20, -5, 0, 20, 5, 10), abs=1e-6)
    assert result.part.is_inside((-15, 0, 5)) and result.part.is_inside((15, 0, 5))
    assert not result.part.is_inside((0, 0, 5))


@pytest.mark.parametrize(("origin", "size", "volume", "counts", "maximum"), [
    ((10, 0, 0), (20, 30, 40), 36000, (1,), (30, 30, 40)),
    ((20, 0, 0), (5, 5, 10), 24250, (1,), (25, 30, 40)),
    ((100, 0, 0), (5, 5, 10), 24250, (2,), (105, 30, 40)),
    ((20, 30, 0), (5, 5, 10), 24250, (2,), (25, 35, 40)),
    ((20, 30, 40), (5, 5, 10), 24250, (2,), (25, 35, 50)),
    ((20.00001, 0, 0), (5, 5, 10), 24250, (2,), (25.00001, 30, 40)),
    ((20.00000001, 0, 0), (5, 5, 10), 24250, (1, 2), (25.00000001, 30, 40)),
])
def test_add_overlap_contacts_separation_and_kernel_resolution(
        origin, size, volume, counts, maximum):
    original = block()
    before = inspect_volume(original)
    tool = block(*size, origin)
    ctx = BuildContext({}, part=original, recording=[])
    ctx.apply(tool, "add", "Vysunutí")
    facts = inspect_volume(ctx.part)
    assert facts.volume == pytest.approx(volume, abs=1e-9 * volume)
    assert facts.solids in counts
    assert facts.bounds == pytest.approx((0, 0, 0, *maximum), abs=1e-6)
    assert ctx.part.is_inside((5, 15, 20))  # původní materiál nezmizel
    inside_tool = tuple(p + length / 2 for p, length in zip(origin, size, strict=True))
    assert ctx.part.is_inside(inside_tool)
    assert inspect_volume(original) == before  # ani nepřímá mutace vstupu
    assert len(ctx.recording) == 1 and ctx.recording[0][0] is tool


@pytest.mark.parametrize("tool", ["inside", "same"])
def test_add_without_effect_is_an_error_and_does_not_record_an_operation(tool):
    part = block()
    before = inspect_volume(part)
    ctx = BuildContext({}, part=part, recording=[])
    tool = block(5, 5, 10, (1, 1, 1)) if tool == "inside" else block()
    with pytest.raises(FeatureError, match="nepřidalo rozlišitelný materiál"):
        ctx.apply(tool, "add", "Vysunutí")
    assert ctx.part is part and inspect_volume(part) == before and ctx.recording == []


@pytest.mark.parametrize(("tool", "volume", "solids", "empty_point"), [
    ((5, 5, 10, (2, 3, 30)), 23750, 1, (4, 5, 35)),
    ((2, 40, 50, (9, -5, -5)), 21600, 2, (10, 15, 20)),
])
def test_cut_removes_material_at_the_requested_location(tool, volume, solids, empty_point):
    original = block()
    before = inspect_volume(original)
    ctx = BuildContext({}, part=original)
    ctx.apply(block(*tool), "cut", "Vysunutí")
    facts = inspect_volume(ctx.part)
    assert facts.volume == pytest.approx(volume) and facts.solids == solids
    assert facts.bounds == pytest.approx((0, 0, 0, 20, 30, 40), abs=1e-6)
    assert not ctx.part.is_inside(empty_point)
    assert ctx.part.is_inside((5, 15, 20)) and ctx.part.is_inside((15, 15, 20))
    assert inspect_volume(original) == before


def test_two_cutters_make_both_holes_and_one_remaining_body():
    part = block(40, 40, 10, (-20, -20, 0))
    tool = Compound([Pos(x, 0, -1) * Cylinder(2, 12, align=(Align.CENTER,) * 2 + (Align.MIN,))
                     for x in (-10, 10)])
    assert inspect_volume(tool).solids == 2
    ctx = BuildContext({}, part=part)
    ctx.apply(tool, "cut", "Díra")
    facts = inspect_volume(ctx.part)
    assert facts.solids == 1 and facts.volume == pytest.approx(16000 - 80 * math.pi)
    assert not ctx.part.is_inside((-10, 0, 5)) and not ctx.part.is_inside((10, 0, 5))
    assert ctx.part.is_inside((0, 0, 5))


def test_cut_can_remove_one_whole_component_and_keep_the_other():
    ctx = BuildContext({}, part=block())
    small = block(5, 5, 10, (100, 0, 0))
    ctx.apply(small, "add", "Vysunutí")
    assert inspect_volume(ctx.part).solids == 2
    ctx.apply(small, "cut", "Vysunutí")
    facts = inspect_volume(ctx.part)
    assert facts.solids == 1 and facts.volume == pytest.approx(24000)
    assert facts.bounds == pytest.approx((0, 0, 0, 20, 30, 40), abs=1e-6)


@pytest.mark.parametrize(("tool", "message"), [
    ((5, 5, 10, (100, 0, 0)), "neodebral žádný materiál"),
    ((5, 5, 10, (20, 0, 0)), "neodebral žádný materiál"),
    ((30, 40, 50, (-5, -5, -5)), "odebral celý díl"),
])
def test_rejected_cut_keeps_geometry_and_recording(tool, message):
    part = block()
    before = inspect_volume(part)
    ctx = BuildContext({}, part=part, recording=[])
    with pytest.raises(FeatureError, match=message):
        ctx.apply(block(*tool), "cut", "Vysunutí")
    assert ctx.part is part and inspect_volume(part) == before and ctx.recording == []


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("source", ["number", "parameter", "expression"])
def test_nonfinite_geometric_inputs_are_rejected_before_building(value, source):
    ctx = BuildContext({"a": value})
    raw = value if source == "number" else "a" if source == "parameter" else "a+1"
    with pytest.raises(ValueError, match="konečné reálné číslo"):
        ctx.num(raw)


def arithmetic_facts(volume):
    # Záměrně bez jádra: přesná rozhodovací hranice nezávisí na jeho mikrotoleranci.
    return VolumeFacts(volume, (volume,), (0, 0, 0, 1, 1, 1))


@pytest.mark.parametrize("power", [-10, 0, 10])
@pytest.mark.parametrize("factor", [0, 0.5, 1, 2])
def test_cut_effect_boundary_at_different_scales(power, factor):
    # 10^9 * 2^k dává přesnou epsilon 2^k; odečítání je zde přesné v binární aritmetice.
    epsilon = 2.0**power
    before = 1_000_000_000 * epsilon
    after = before - factor * epsilon
    if factor <= 1:
        with pytest.raises(GeometryValidationError, match="neodebral"):
            check_cut_volume(before, after, "uprav řez")
    else:
        check_cut_volume(before, after, "uprav řez")


@pytest.mark.parametrize("power", [-10, 0, 10])
@pytest.mark.parametrize("factor", [0, 0.5, 1, 2])
def test_add_effect_boundary_uses_result_and_not_tool_volume(power, factor):
    epsilon = 2.0**power
    after = 1_000_000_000 * epsilon
    before = after - factor * epsilon
    args = ("add", arithmetic_facts(before), arithmetic_facts(1e20), arithmetic_facts(after))
    if factor <= 1:
        with pytest.raises(GeometryValidationError, match="nepřidalo"):
            check_boolean(*args, empty_cut="uprav řez", empty_add="posuň přídavek")
    else:
        check_boolean(*args, empty_cut="uprav řez", empty_add="posuň přídavek")


def test_cut_just_on_each_side_of_boundary_and_nonfinite_result():
    before, boundary = 1_000_000_000.0, 999_999_999.0
    with pytest.raises(GeometryValidationError, match="neodebral"):
        check_cut_volume(before, math.nextafter(boundary, math.inf), "uprav řez")
    check_cut_volume(before, math.nextafter(boundary, -math.inf), "uprav řez")
    with pytest.raises(GeometryValidationError, match="konečný objem"):
        check_cut_volume(before, math.nan, "uprav řez")


@pytest.mark.parametrize("scale", [0.1, 1, 10])
def test_real_booleans_at_model_scales(scale):
    ctx = BuildContext({}, part=block(20 * scale, 30 * scale, 40 * scale))
    ctx.apply(block(20 * scale, 30 * scale, 40 * scale, (10 * scale, 0, 0)), "add", "Přidání")
    assert inspect_volume(ctx.part).volume == pytest.approx(36000 * scale**3, rel=1e-9)
    assert ctx.part.is_inside((25 * scale, 15 * scale, 20 * scale))
