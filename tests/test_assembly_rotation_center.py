"""Vlastní střed: nezávislá tuhá geometrie, parametry, atomické odmítnutí a uložení."""

import copy

import numpy as np
import pytest

from skodacad.assembly import AssemblyError
from skodacad.assembly_session import AssemblySession
from skodacad.expressions import evaluate
from test_assembly import part_data, write
from test_assembly_batch_move import assert_unchanged, linked, snapshot  # noqa: F401
from test_assembly_batch_rotation import group, rodrigues, vertices  # noqa: F401


@pytest.mark.parametrize("axis", "xyz")
@pytest.mark.parametrize("pivot", [(0, 0, 0), (12.5, -31, 18)])
def test_custom_center_rotates_actual_vertices_and_single_history(request, axis, pivot):
    s, source = request.getfixturevalue("group")
    raw, recipe = source.read_bytes(), s.assembly.to_dict()
    old = {i.ids: vertices(i.part) for i in s.result.instances}
    q, center = rodrigues(axis, -37.5), np.array(pivot)
    s.turn_many_around(["a", "b", "a"], axis, -37.5, center=pivot)
    assert s.result.complete and s.result.volume_mm3 == pytest.approx(13000)
    for i in s.result.instances:
        expected = (center+(q @ (old[i.ids]-center).T).T
                    if i.ids[0] != "pevny" else old[i.ids])
        assert all(min(np.linalg.norm(expected-v, axis=1)) < 1e-6 for v in vertices(i.part))
        assert i.part.is_valid
    assert source.read_bytes() == raw and len(s._undo) == 1
    changed = s.assembly.to_dict()
    s.undo()
    assert s.assembly.to_dict() == recipe and not s.can_undo
    s.redo()
    assert s.assembly.to_dict() == changed and len(s._undo) == 1


def test_center_expressions_are_snapshot_but_position_parameters_remain_live(request):
    s, _ = request.getfixturevalue("group")
    s.set_placement("a", position=["20*k", "k+2", "k-3"])
    original = copy.deepcopy(s.assembly)
    point = ["k/2", "-2*k", "uhel"]
    pivot = np.array(s.rotation_center(["a", "b"], point))
    assert pivot == pytest.approx([2.5, -10, 37.5])
    s.turn_many_around(["a", "b"], "z", 90, center=point)
    s.set_parameters({"k": 8, "uhel": 12})
    for cid in ("a", "b"):
        position = [evaluate(v, s.result.parameters) for v in original.component(cid).position]
        assert s._pose(cid)[1] == pytest.approx(pivot+rodrigues("z", 90) @ (position-pivot))


@pytest.mark.parametrize("point,reason", [
    ("123", "tři souřadnice"), ([0, 0], "tři souřadnice"),
    ({"x": 0, "y": 0, "z": 0}, "tři souřadnice"),
    ([True, 0, 0], "logickou"), ([0, float("nan"), 0], "konečné"),
    ([0, 0, float("inf")], "konečné"), ([0, "chybi", 0], "neznámý parametr"),
    ([0, "1/0", 0], "nulou"), ([10**400, 0, 0], "příliš velký"),
])
def test_bad_custom_center_is_atomic_even_for_full_turn(request, point, reason):
    s, _ = request.getfixturevalue("group")
    s.turn_many_around(["a", "b"], "z", 30)
    s.undo()
    state = snapshot(s)
    for angle in (30, 360):
        with pytest.raises(AssemblyError, match=reason):
            s.turn_many_around(["a", "b"], "z", angle, center=point)
        assert_unchanged(s, state)


def test_custom_center_queries_and_full_turn_keep_redo_and_sources(request):
    s, source = request.getfixturevalue("group")
    s.turn_many_around(["a", "b"], "z", 30, center=[2, 3, 4])
    s.undo()
    state, raw = snapshot(s), source.read_bytes()
    assert s.rotation_center(["a", "b"], ["k", 0, 0]) == (5, 0, 0)
    assert s.turn_many_around(["a", "b"], "x", 720, center=["k", 0, 0]) is state[1]
    assert_unchanged(s, state)
    assert source.read_bytes() == raw


def test_custom_center_still_respects_fixed_constraints_and_source_changes(request):
    s = request.getfixturevalue("linked")
    state = snapshot(s)
    with pytest.raises(AssemblyError, match="Vazb"):
        s.turn_many_around(["a", "c"], "x", 90, center=[12, -5, 8])
    assert_unchanged(s, state)
    s, source = request.getfixturevalue("group")
    state = snapshot(s)
    with pytest.raises(AssemblyError, match="pevné"):
        s.turn_many_around(["a", "pevny"], "z", 30, center=[0, 0, 0])
    assert_unchanged(s, state)
    write(source, part_data(height=20))
    with pytest.raises(AssemblyError, match="změnil zdroj"):
        s.turn_many_around(["a", "b"], "z", 30, center=[0, 0, 0])
    assert_unchanged(s, state)


def test_custom_rotation_save_reopen_and_step_geometry(request, tmp_path):
    from build123d import import_step

    s, _ = request.getfixturevalue("group")
    s.turn_many_around(["a", "b"], "y", 37.5, center=[12.5, -31, 18])
    expected = {i.ids: tuple(i.part.center()) for i in s.result.instances}
    s.save(tmp_path/"otocene.json")
    other = AssemblySession()
    other.open(tmp_path/"otocene.json")
    assert other.result.complete and other.result.volume_mm3 == pytest.approx(13000)
    assert "rotation_center" not in other.assembly.to_dict()
    for i in other.result.instances:
        assert tuple(i.part.center()) == pytest.approx(expected[i.ids])
    other.export_step(tmp_path/"otocene.step")
    restored = import_step(tmp_path/"otocene.step")
    assert len(restored.solids()) == 3 and restored.volume == pytest.approx(13000, abs=1e-5)
