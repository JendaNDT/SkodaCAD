"""Tuhé otočení výběru: skutečné vrcholy/těžiště, parametry, vazby a atomická historie."""

import copy
import math

import numpy as np
import pytest

from skodacad.assembly import AssemblyError
from skodacad.assembly_build import rotation_matrix
from skodacad.assembly_session import AssemblySession
from skodacad.expressions import evaluate
from test_assembly import assembly_data, component, part_data, write
from test_assembly_batch_move import assert_unchanged, linked, snapshot  # noqa: F401


@pytest.fixture
def group(tmp_path):
    source = write(tmp_path / "dily/a.json", part_data())
    write(tmp_path / "dily/b.json", part_data(10, 10, 10, center=(5, 5)))
    path = write(tmp_path / "sestava.json", assembly_data([
        component("pevny", "dily/a.json", fixed=True),
        component("a", "dily/a.json", position=(100, 0, 0), rotation=(10, 20, 30)),
        component("b", "dily/b.json", position=(-50, 80, -10), rotation=(0, 10, 35)),
    ], parameters={"k": 5, "uhel": 37.5}))
    s = AssemblySession()
    s.open(path)
    return s, source


def rodrigues(axis, angle):
    e = np.eye(3)["xyz".index(axis)] if isinstance(axis, str) else np.array(axis, dtype=float)
    e /= np.linalg.norm(e)
    x, y, z = e
    cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    t = math.radians(angle)
    return np.eye(3)*math.cos(t)+(1-math.cos(t))*np.outer(e, e)+math.sin(t)*cross


def vertices(part):
    return np.array([tuple(v) for v in part.vertices()])


@pytest.mark.parametrize("axis", "xyz")
@pytest.mark.parametrize("angle", [90, -90, 37.5, 180])
def test_group_rotation_matches_rigid_geometry_and_one_undo(group, axis, angle):
    s, source = group
    raw, recipe = source.read_bytes(), s.assembly.to_dict()
    old = {i.ids: vertices(i.part) for i in s.result.instances}
    poses = {c.id: s._pose(c.id) for c in s.assembly.components}
    center = np.array(s.rotation_center(["a", "b", "a"]))
    parts = {i.ids[0]: i.part for i in s.result.instances}
    # Různé objemy: 6000 a 1000 mm³, materiál ani pevný nevybraný díl střed neovlivní.
    assert center == pytest.approx((6*np.array(tuple(parts["a"].center()))
                                    + np.array(tuple(parts["b"].center())))/7)
    q = rodrigues(axis, angle)
    result = s.turn_many_around(["b", "a", "a"], axis, angle)
    assert result.complete and result.volume_mm3 == pytest.approx(13000)
    assert all(i.part.is_valid for i in result.instances)
    for i in result.instances:
        expected = ((q @ (old[i.ids]-center).T).T+center if i.ids[0] != "pevny" else old[i.ids])
        assert len(vertices(i.part)) == len(expected)
        assert all(min(np.linalg.norm(expected-p, axis=1)) < 1e-6 for p in vertices(i.part))
    for cid in ("a", "b", "pevny"):
        r, p = s._pose(cid)
        old_r, old_p = poses[cid]
        assert r == pytest.approx(q @ old_r if cid != "pevny" else old_r, abs=1e-10)
        assert p == pytest.approx(center+q @ (old_p-center) if cid != "pevny" else old_p)
    assert s.rotation_center(["a", "b"]) == pytest.approx(center, abs=1e-7)
    assert len(s._undo) == 1 and source.read_bytes() == raw
    moved = s.assembly.to_dict()
    s.undo()
    assert s.assembly.to_dict() == recipe and not s.can_undo
    s.redo()
    assert s.assembly.to_dict() == moved and len(s._undo) == 1


@pytest.mark.parametrize("axis", "xyz")
def test_parameter_positions_are_rotated_as_expressions_not_frozen(group, axis):
    s, _ = group
    s.set_placement("a", position=["20*k", "k+2", "k-3"])
    s.set_placement("b", position=["-10*k", "uhel", "k*2"])
    original = copy.deepcopy(s.assembly)
    pivot = np.array(s.rotation_center(["a", "b"]))
    q = rodrigues(axis, 37.5)
    s.turn_many_around(["a", "b"], axis, "uhel")
    s.set_parameters({"k": 8, "uhel": 42})
    for cid in ("a", "b"):
        position = [evaluate(v, s.result.parameters) for v in original.component(cid).position]
        assert s._pose(cid)[1] == pytest.approx(pivot+q @ (position-pivot), abs=1e-6)
        expected_rotation = q @ rotation_matrix(original.component(cid).rotation)
        assert s._pose(cid)[0] == pytest.approx(expected_rotation, abs=1e-10)


def test_functions_and_pi_survive_affine_composition(group):
    s, _ = group
    s.set_placement("a", position=["sin(k)*pi*30", "2+3", "10"])
    s.set_placement("b", position=["cos(k)+20", "2*k", "10"])
    original = copy.deepcopy(s.assembly)
    center = np.array(s.rotation_center(["a", "b"]))
    s.turn_many_around(["a", "b"], "z", 90)
    s.set_parameters({"k": 8})
    for cid in ("a", "b"):
        p = [evaluate(v, s.result.parameters) for v in original.component(cid).position]
        assert s._pose(cid)[1] == pytest.approx(center+rodrigues("z", 90) @ (p-center), abs=1e-6)


def test_rotation_expression_z_is_preserved_and_xy_refuses_atomically(group):
    s, _ = group
    s.set_placement("a", rotation=["k", "2*k", "k+1"])
    before = copy.deepcopy(s.assembly)
    s.turn_many_around(["a", "b"], "z", 25)
    assert s.assembly.component("a").rotation[:2] == ["k", "2*k"]
    s.set_parameters({"k": 9})
    old_r = rotation_matrix([evaluate(v, {"k": 9}) for v in before.component("a").rotation])
    assert s._pose("a")[0] == pytest.approx(rodrigues("z", 25) @ old_r, abs=1e-10)
    for axis in "xy":
        state = snapshot(s)
        with pytest.raises(AssemblyError, match="výrazem"):
            s.turn_many_around(["a", "b"], axis, 30)
        assert_unchanged(s, state)


def test_repeated_rotation_does_not_expand_expressions_and_opposite_restores_pose(group):
    s, _ = group
    s.set_placement("a", position=["20*k", "k+2", "k-3"])
    s.set_placement("b", position=["-10*k", "uhel", "k*2"])
    poses = {cid: s._pose(cid) for cid in ("a", "b")}
    for _ in range(12):
        s.turn_many_around(["a", "b"], "x", 37.5)
        s.turn_many_around(["a", "b"], "x", -37.5)
    for cid, (r, p) in poses.items():
        assert s._pose(cid)[0] == pytest.approx(r, abs=1e-9)
        assert s._pose(cid)[1] == pytest.approx(p, abs=1e-6)
        assert max(len(str(v)) for v in s.assembly.component(cid).position) < 500


@pytest.mark.parametrize("angle", [0, 360, -720, "360*k"])
def test_full_turn_preserves_history_result_dirty_and_redo(group, angle):
    s, _ = group
    s.turn_many_around(["a", "b"], "z", 30)
    s.undo()
    state = snapshot(s)
    assert s.turn_many_around(["a", "b"], "z", angle) is state[1]
    assert_unchanged(s, state)


@pytest.mark.parametrize("ids,axis,angle,reason", [
    (["a", "pevny"], "z", 30, "pevné"),
    (["a", "chybi"], "z", 30, "chybi"),
    ([], "z", 30, "Vyber"),
    ([("a", "dil"), "b"], "z", 30, "podsestav"),
    (["a", "b"], "q", 30, "Neznámá osa"),
    (["a", "b"], "x", True, "logickou"),
    (["a", "b"], "x", float("nan"), "konečné"),
    (["a", "b"], "x", float("inf"), "konečné"),
    (["a", "b"], "x", "neznamy", "neznámý parametr"),
    (["a", "b"], "x", "1/0", "nulou"),
    (["a", "b"], "x", 10**400, "příliš velký"),
])
def test_bad_rotation_preserves_entire_state_and_redo(group, ids, axis, angle, reason):
    s, _ = group
    s.turn_many_around(["a", "b"], "z", 30)
    s.undo()
    state = snapshot(s)
    with pytest.raises(AssemblyError, match=reason):
        s.turn_many_around(ids, axis, angle)
    assert_unchanged(s, state)


@pytest.mark.parametrize("axis", "xyz")
def test_internal_constraint_rotates_as_rigid_group(request, axis):
    s = request.getfixturevalue("linked")
    center = np.array(s.rotation_center(["a", "b"]))
    old = {cid: s._pose(cid) for cid in ("a", "b", "c")}
    s.turn_many_around(["a", "b"], axis, 37.5)
    assert s.result.complete and len(s._undo) == 1
    q = rodrigues(axis, 37.5)
    for cid in ("a", "b", "c"):
        assert s._pose(cid)[1] == pytest.approx(
            center+q @ (old[cid][1]-center) if cid != "c" else old[cid][1], abs=1e-6)


def test_external_constraint_forbidden_motion_rejected_and_free_rotation_allowed(request):
    s = request.getfixturevalue("linked")
    state = snapshot(s)
    with pytest.raises(AssemblyError, match="Vazb"):
        s.turn_many_around(["a", "c"], "x", 90)
    assert_unchanged(s, state)
    old_b = s._pose("b")
    s.turn_many_around(["a", "c"], "z", 30)
    assert s.result.complete and len(s._undo) == 1
    assert s._pose("b")[0] == pytest.approx(old_b[0])
    assert s._pose("b")[1] == pytest.approx(old_b[1])


def test_source_change_and_incomplete_result_reject_entire_rotation(group):
    s, source = group
    state = snapshot(s)
    data = part_data(height=20)
    write(source, data)
    with pytest.raises(AssemblyError, match="změnil zdroj"):
        s.turn_many_around(["a", "b"], "z", 30)
    assert_unchanged(s, state)
    source.unlink()
    s.rebuild()
    state = snapshot(s)
    with pytest.raises(AssemblyError, match="úplně připravená"):
        s.turn_many_around(["a", "b"], "z", 30)
    assert_unchanged(s, state)


@pytest.mark.parametrize("pitch", [89.99999, -89.99999, 90, -90])
def test_existing_orientation_near_gimbal_keeps_full_rotation(group, pitch):
    s, _ = group
    s.set_placement("a", rotation=[10, pitch, 35])
    old = s._pose("a")[0]
    s.turn_many_around(["a", "b"], "y", .000001)
    assert s._pose("a")[0] == pytest.approx(rodrigues("y", .000001) @ old, abs=1e-10)


@pytest.mark.parametrize("point", [None, (12.5, -31, 18)])
@pytest.mark.parametrize("axis", ["y", (1, 2, 3)])
def test_nested_parents_rotate_all_children_and_keep_source_files(tmp_path, point, axis):
    part = write(tmp_path / "jinde/kvadr.json", part_data())
    sub = write(tmp_path / "moduly/modul.json", assembly_data([
        component("prvni", "../jinde/kvadr.json", fixed=True),
        component("druhy", "../jinde/kvadr.json", position=(40, 0, 0))]))
    path = write(tmp_path / "sestava.json", assembly_data([
        component("a", "moduly/modul.json", position=(100, 0, 0), rotation=(0, 0, 90)),
        component("b", "moduly/modul.json", position=(0, 80, 20)),
        component("c", "jinde/kvadr.json", position=(-100, 0, 0))]))
    raw = {p: p.read_bytes() for p in (part, sub)}
    s = AssemblySession()
    s.open(path)
    old = {i.ids: vertices(i.part) for i in s.result.instances}
    center = np.array(s.rotation_center(["a", "b"], point))
    q = rodrigues(axis, 37.5)
    s.turn_many_around(["a", "b"], axis, 37.5, center=point)
    for i in s.result.instances:
        expected = ((q @ (old[i.ids]-center).T).T+center if i.ids[0] != "c" else old[i.ids])
        assert all(min(np.linalg.norm(expected-p, axis=1)) < 1e-6 for p in vertices(i.part))
    assert s.result.complete and s.result.volume_mm3 == pytest.approx(30000)
    assert all(p.read_bytes() == content for p, content in raw.items())


@pytest.mark.parametrize("axis", ["x", (1, 2, 3)])
def test_rotated_recipe_save_reopen_and_step_have_same_complete_geometry(group, tmp_path, axis):
    from build123d import import_step

    s, _ = group
    s.turn_many_around(["a", "b"], axis, 37.5)
    old = {i.ids: np.array(tuple(i.part.center())) for i in s.result.instances}
    s.save(tmp_path / "kopie.json")
    reopened = AssemblySession()
    reopened.open(tmp_path / "kopie.json")
    assert reopened.result.complete and reopened.result.volume_mm3 == pytest.approx(13000)
    for i in reopened.result.instances:
        assert tuple(i.part.center()) == pytest.approx(old[i.ids], abs=1e-6)
    step = tmp_path / "otocene.step"
    reopened.export_step(step)
    restored = import_step(step)
    assert len(restored.solids()) == 3 and restored.volume == pytest.approx(13000, abs=1e-5)
