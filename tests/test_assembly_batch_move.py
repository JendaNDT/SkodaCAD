"""Společný posun: skutečná geometrie, parametrické polohy, vazby a atomická historie."""

import copy
import hashlib
import json

import numpy as np
import pytest

from skodacad.assembly import AssemblyError
from skodacad.assembly_build import rotation_matrix
from skodacad.assembly_session import AssemblySession
from test_assembly import assembly_data, component, part_data, write


@pytest.fixture
def group(tmp_path):
    source = write(tmp_path / "dily/kvadr.json", part_data())
    path = write(tmp_path / "sestava.json", assembly_data([
        component("pevny", "dily/kvadr.json", fixed=True),
        component("a", "dily/kvadr.json", position=(100, 0, 0), rotation=(0, 0, 90)),
        component("b", "dily/kvadr.json", position=(140, 20, 10), rotation=(10, 20, 30)),
    ], parameters={"krok": 5}))
    session = AssemblySession()
    session.open(path)
    return session, source


def snapshot(session):
    return (copy.deepcopy(session.assembly.to_dict()), session.result,
            list(session._undo), list(session._redo), session.dirty, session.notice)


def assert_unchanged(session, before):
    assert session.assembly.to_dict() == before[0]
    assert session.result is before[1]
    assert session._undo == before[2] and session._redo == before[3]
    assert session.dirty == before[4] and session.notice == before[5]


def bounds(result):
    return {i.ids: np.array([tuple(i.part.bounding_box().min),
                            tuple(i.part.bounding_box().max)]) for i in result.instances}


def test_batch_move_global_axes_keeps_relative_geometry_and_one_undo(group):
    session, source = group
    old = bounds(session.result)
    recipe = session.assembly.to_dict()
    rotations = {c.id: list(c.rotation) for c in session.assembly.components}
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    moved = session.move_many_by(["b", "a", "a"], ["2*krok", -2.5, 4])
    new = bounds(moved)
    for ids in (("a",), ("b",)):
        assert new[ids] == pytest.approx(old[ids] + [10, -2.5, 4])
    assert new[("pevny",)] == pytest.approx(old[("pevny",)])
    assert new[("a",)]-new[("b",)] == pytest.approx(old[("a",)]-old[("b",)])
    assert moved.complete and moved.volume_mm3 == pytest.approx(18000)
    assert all(i.part.is_valid and i.part.volume == pytest.approx(6000) for i in moved.instances)
    assert {c.id: c.rotation for c in session.assembly.components} == rotations
    assert len(session._undo) == 1 and session.dirty
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    session.undo()
    assert session.assembly.to_dict() == recipe and not session.can_undo
    for ids, box in old.items():
        assert bounds(session.result)[ids] == pytest.approx(box)
    session.redo()
    for ids, box in new.items():
        assert bounds(session.result)[ids] == pytest.approx(box)


def test_batch_zero_preserves_result_history_dirty_and_redo(group):
    session, _ = group
    session.move_many_by(["a", "b"], [1, 0, 0])
    session.undo()
    before = snapshot(session)
    assert session.move_many_by(["a", "b"], [0, "krok-krok", -0.0]) is before[1]
    assert_unchanged(session, before)


@pytest.mark.parametrize("ids,delta,reason", [
    (["a", "pevny"], [1, 2, 3], "pevné"),
    (["a", "chybi"], [1, 2, 3], "chybi"),
    ([], [1, 2, 3], "Vyber"),
    ([("a", "dil"), "b"], [1, 2, 3], "podsestavy"),
    (["a", "b"], [1, 2], "trojice"),
    (["a", "b"], "123", "trojice"),
    (["a", "b"], [True, 0, 0], "logickou"),
    (["a", "b"], [float("nan"), 0, 0], "konečná"),
    (["a", "b"], [0, float("inf"), 0], "konečná"),
    (["a", "b"], ["neznamy", 0, 0], "neznámý parametr"),
    (["a", "b"], ["1/0", 0, 0], "nulou"),
    (["a", "b"], [10**400, 0, 0], "příliš velký"),
])
def test_batch_invalid_or_fixed_refuses_everything_and_keeps_redo(group, ids, delta, reason):
    session, _ = group
    session.move_many_by(["a", "b"], [1, 0, 0])
    session.undo()
    before = snapshot(session)
    with pytest.raises(AssemblyError, match=reason):
        session.move_many_by(ids, delta)
    assert_unchanged(session, before)


def test_batch_keeps_position_expressions_and_combines_repeated_offsets(group):
    session, _ = group
    session.set_placement("a", position=["10*krok", 0, "krok"])
    session.set_placement("b", position=["20*krok", "-krok", "krok+2"])
    original = copy.deepcopy(session.assembly)
    for _ in range(4):
        session.move_many_by(["a", "b"], [2, 0, -1])
    assert session.assembly.component("a").position == ["(10*krok) + (8)", 0, "(krok) + (-4)"]
    session.set_parameters({"krok": 7})
    assert tuple(session._pose("a")[1]) == pytest.approx((78, 0, 3))
    assert tuple(session._pose("b")[1]) == pytest.approx((148, -7, 5))
    for _ in range(4):
        session.move_many_by(["a", "b"], [-2, 0, 1])
    assert session.assembly.component("a").position == original.component("a").position
    assert session.assembly.component("b").position == original.component("b").position


def test_batch_nested_parent_moves_all_children_once_without_touching_sources(tmp_path):
    part = write(tmp_path / "dily/kvadr.json", part_data())
    sub = write(tmp_path / "modul.json", assembly_data([
        component("prvni", "dily/kvadr.json", fixed=True),
        component("druhy", "dily/kvadr.json", position=(40, 0, 0))]))
    main = write(tmp_path / "sestava.json", assembly_data([
        component("a", "modul.json", position=(100, 0, 0), rotation=(0, 0, 90)),
        component("b", "modul.json", position=(0, 80, 20)),
        component("c", "dily/kvadr.json", position=(-100, 0, 0))]))
    raw = {p: p.read_bytes() for p in (part, sub)}
    session = AssemblySession()
    session.open(main)
    old = bounds(session.result)
    session.move_many_by(["a", "b"], [3, -4, 5])
    assert session.result.volume_mm3 == pytest.approx(30000) and session.result.complete
    for ids, box in bounds(session.result).items():
        assert box == pytest.approx(old[ids] + ([3, -4, 5] if ids[0] in ("a", "b") else 0))
    assert all(p.read_bytes() == content for p, content in raw.items())


@pytest.fixture
def linked(tmp_path):
    from test_assembly_constraints import assembly_data as with_constraints
    from test_assembly_constraints import constraint

    write(tmp_path / "kvadr.json", part_data())
    top = {"component": "a", "face": {"at": [0, 0, 10], "normal": [0, 0, 1], "type": "plane"}}
    bottom = {"component": "b", "face": {"at": [0, 0, 0], "normal": [0, 0, -1], "type": "plane"}}
    path = write(tmp_path / "sestava.json", with_constraints([
        component("a", "kvadr.json"), component("b", "kvadr.json", position=(0, 0, 10)),
        component("c", "kvadr.json", position=(100, 0, 0)),
    ], [constraint("v1", "mate", top, bottom)]))
    session = AssemblySession()
    session.open(path)
    assert session.result.complete
    return session


def test_batch_internal_constraints_translate_as_rigid_group(linked):
    session = linked
    old = bounds(session.result)
    session.move_many_by(["a", "b"], [3, 4, 5])
    for ids, box in bounds(session.result).items():
        assert box == pytest.approx(old[ids] + ([3, 4, 5] if ids[0] != "c" else 0))
    assert all(c.state == "ok" for c in session.result.constraints)
    assert len(session._undo) == 1 and session.result.volume_mm3 == pytest.approx(18000)


@pytest.mark.parametrize("ids", [["a", "c"], ["b", "c"]])
def test_batch_rejects_solver_pulling_neighbour_or_returning_selected_piece(linked, ids):
    session = linked
    session.move_many_by(["a", "b"], [1, 0, 0])
    session.undo()
    before = snapshot(session)
    with pytest.raises(AssemblyError, match="Vazby nedovolují"):
        session.move_many_by(ids, [0, 0, 5])
    assert_unchanged(session, before)
    assert session.result.complete and session.result.volume_mm3 == pytest.approx(18000)


def test_batch_allows_external_constraint_free_direction_without_moving_neighbour(linked):
    session = linked
    old = bounds(session.result)
    session.move_many_by(["a", "c"], [5, -2, 0])
    for ids, box in bounds(session.result).items():
        assert box == pytest.approx(old[ids] + ([5, -2, 0] if ids[0] != "b" else 0))
    assert all(c.state == "ok" for c in session.result.constraints)


def test_batch_source_changed_during_transaction_is_rejected(group):
    session, source = group
    before = snapshot(session)
    data = json.loads(source.read_text())
    data["features"][-1]["distance"] = 20
    source.write_text(json.dumps(data))
    with pytest.raises(AssemblyError, match="změnil zdroj"):
        session.move_many_by(["a", "b"], [5, 0, 0])
    assert_unchanged(session, before)


def test_batch_incomplete_assembly_cannot_be_partly_moved(group):
    session, source = group
    source.unlink()
    session.rebuild()
    before = snapshot(session)
    with pytest.raises(AssemblyError, match="úplně připravená"):
        session.move_many_by(["a", "b"], [5, 0, 0])
    assert_unchanged(session, before)


def test_batch_saved_recipe_and_step_keep_full_moved_assembly(group, tmp_path):
    from build123d import import_step

    session, _ = group
    session.move_many_by(["a", "b"], [5, -2, 3])
    physical = session.result.compound()
    session.save()
    saved = json.loads(session.path.read_text())
    assert saved["version"] == 29 and len(saved["components"]) == 3
    reopened = AssemblySession()
    reopened.open(session.path)
    assert bounds(reopened.result)[("a",)] == pytest.approx(bounds(session.result)[("a",)])
    target = tmp_path / "posun.step"
    reopened.export_step(target)
    exported = import_step(target)
    assert len(exported.solids()) == 3 and exported.volume == pytest.approx(18000)
    assert tuple(exported.bounding_box().min) == pytest.approx(tuple(physical.bounding_box().min))
    assert tuple(exported.bounding_box().max) == pytest.approx(tuple(physical.bounding_box().max))
    assert np.allclose(rotation_matrix(reopened.assembly.component("b").rotation),
                       rotation_matrix([10, 20, 30]), atol=1e-10, rtol=0)
