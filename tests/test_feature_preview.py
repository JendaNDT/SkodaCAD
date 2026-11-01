"""Návrh nového prvku: fyzika, izolace, čerstvost a jediný krok historie."""
import copy
import math

import pytest

from conftest import edge_at
from skodacad.document import DocumentError
from skodacad.session import ModelSession


@pytest.fixture
def session():
    s = ModelSession()
    s.new_document()
    s.add_feature("sketch")
    return s


def test_preview_edits_apply_one_step_and_survive_save(session, tmp_path):
    original = copy.deepcopy(session.document)
    result, count, dirty = session.result, len(session._undo), session.dirty
    preview = session.begin_feature_preview("extrude")
    for distance in (20, 30):
        f = preview.session.feature(preview.feature_id)
        f["distance"] = distance
        preview.session.update_feature(preview.feature_id, f)
        assert preview.session.properties.volume_mm3 == pytest.approx(40*30*distance)
        assert session.document == original and session.result is result
        assert len(session._undo) == count and session.dirty == dirty
    session.apply_feature_preview(preview)
    assert len(session._undo) == count+1 and session.result.part.is_valid
    assert session.properties.size_mm == pytest.approx((40, 30, 30))
    session.undo()
    assert session.document == original
    session.redo()
    assert session.properties.volume_mm3 == pytest.approx(36000)
    path = session.save(tmp_path/"potvrzeny.json")
    reopened = ModelSession()
    reopened.open(path)
    assert reopened.properties.volume_mm3 == pytest.approx(36000)
    with pytest.raises(DocumentError, match="ukončen"):
        session.apply_feature_preview(preview)


def test_cancel_preserves_saved_source_redo_and_exports(session, tmp_path):
    session.add_feature("extrude")
    session.set_info(name="Další název")
    session.undo()
    session.save(tmp_path/"puvodni.json")
    before = copy.deepcopy(session.document)
    result, undo, redo = session.result, list(session._undo), list(session._redo)
    preview = session.begin_feature_preview("hole")
    assert preview.session.properties.volume_mm3 < 12000
    session.export(tmp_path/"puvodni.step")
    assert session.document == before and not session.dirty
    preview.cancel()
    preview.cancel()
    assert session.result is result and session._undo == undo and session._redo == redo
    with pytest.raises(DocumentError, match="ukončen"):
        session.apply_feature_preview(preview)
    session.redo()
    assert session.document.name == "Další název"


def test_invalid_preview_cannot_be_applied_and_can_be_repaired(session):
    preview = session.begin_feature_preview("extrude")
    f = preview.session.feature(preview.feature_id)
    f["distance"] = "neni_parametr"
    preview.session.update_feature(preview.feature_id, f)
    before = copy.deepcopy(session.document)
    with pytest.raises(DocumentError, match="potvrdit"):
        session.apply_feature_preview(preview)
    assert session.document == before and not preview.closed
    f["distance"] = 25
    preview.session.update_feature(preview.feature_id, f)
    session.apply_feature_preview(preview)
    assert session.properties.volume_mm3 == pytest.approx(30000)


def test_stale_or_more_than_one_change_is_rejected(session):
    preview = session.begin_feature_preview("extrude")
    session.set_info(name="Zdroj změněn")
    with pytest.raises(DocumentError, match="změnil"):
        session.apply_feature_preview(preview)
    newer = session.begin_feature_preview("extrude")
    newer.session.set_info(name="Nepatří k novému prvku")
    with pytest.raises(DocumentError, match="další změny"):
        session.apply_feature_preview(newer)


def test_insert_before_later_features_and_selection_are_physical(session):
    session.add_feature("extrude")
    preview = session.begin_feature_preview("sketch", after_id="sketch1")
    session.apply_feature_preview(preview)
    assert [f["id"] for f in session.document.features] == ["sketch1", "sketch2", "extrude1"]
    assert session.properties.volume_mm3 == pytest.approx(12000)
    edge = edge_at(session.result.part, 20, -15, 5)
    preview = session.begin_feature_preview("fillet", shapes=[edge.wrapped])
    assert preview.session.properties.volume_mm3 == pytest.approx(12000-(4-math.pi)*10)
    assert session.properties.volume_mm3 == pytest.approx(12000)
    session.apply_feature_preview(preview)
    assert session.result.part.is_valid
    assert session.properties.volume_mm3 == pytest.approx(12000-(4-math.pi)*10)


def test_background_preview_latest_result_and_cancel_do_not_touch_source(session):
    from skodacad.worker import BackgroundRebuilder

    runner = BackgroundRebuilder()
    before = copy.deepcopy(session.document)
    try:
        preview = session.begin_feature_preview("extrude", runner=runner)
        with pytest.raises(DocumentError, match="spočítaný"):
            session.apply_feature_preview(preview)
        f = preview.session.feature(preview.feature_id)
        f["distance"] = 20
        preview.session.update_feature(preview.feature_id, f)
        assert preview.session.wait(45) and preview.session.result.ok
        assert session.document == before
        session.apply_feature_preview(preview)
        assert session.properties.volume_mm3 == pytest.approx(24000)
        before, result = copy.deepcopy(session.document), session.result
        another = session.begin_feature_preview("hole", runner=runner)
        another.cancel()
        assert not another.session.computing
        assert session.document == before and session.result is result
    finally:
        runner.close()


@pytest.fixture
def plate():
    from pathlib import Path

    s = ModelSession()
    s.open(Path(__file__).parents[1]/"examples/deska_workflow.json")
    return s


def test_edit_rebuilds_successors_atomically_and_roundtrips(plate, tmp_path):
    before, result = copy.deepcopy(plate.document), plate.result
    undo = len(plate._undo)
    preview = plate.begin_feature_edit("extrude1")
    assert preview.editing and preview.ready
    for distance in (12, 15):
        f = preview.session.feature("extrude1")
        f["distance"] = distance
        preview.session.update_feature("extrude1", f)
        expected = (3984-32*math.pi)*distance  # four through holes and four R2 corners
        assert preview.session.result.part.is_valid
        assert preview.session.properties.solids == 1
        assert preview.session.properties.volume_mm3 == pytest.approx(expected)
        assert preview.session.properties.size_mm == pytest.approx((80, 50, distance))
        assert plate.document == before and plate.result is result
    plate.apply_feature_preview(preview)
    assert len(plate._undo) == undo+1
    assert [f["id"] for f in plate.document.features] == [f["id"] for f in before.features]
    plate.undo()
    assert plate.document == before
    plate.redo()
    path = plate.save(tmp_path/"uprava.json")
    reopened = ModelSession()
    reopened.open(path)
    assert reopened.result.part.is_valid
    assert reopened.properties.volume_mm3 == pytest.approx(expected)


def test_edit_cancel_and_no_change_preserve_saved_history(plate, tmp_path):
    plate.set_info(name="Znovu")
    plate.undo()
    path = plate.save(tmp_path/"puvodni.json")
    before, result = copy.deepcopy(plate.document), plate.result
    undo, redo = list(plate._undo), list(plate._redo)
    preview = plate.begin_feature_edit("extrude1")
    f = preview.session.feature("extrude1")
    f["distance"] = 20
    preview.session.update_feature("extrude1", f)
    preview.cancel()
    assert plate.document == before and plate.result is result
    assert plate._undo == undo and plate._redo == redo
    assert not plate.dirty and plate.path == path
    unchanged = plate.begin_feature_edit("extrude1")
    plate.apply_feature_preview(unchanged)
    assert unchanged.closed and plate._undo == undo and plate._redo == redo
    assert not plate.dirty


def test_edit_cannot_confirm_successful_feature_with_failed_successor(plate):
    before, result = copy.deepcopy(plate.document), plate.result
    preview = plate.begin_feature_edit("sketch1")
    f = preview.session.feature("sketch1")
    f["elements"][0]["width"] = 5
    preview.session.update_feature("sketch1", f)
    assert not preview.ready and not preview.session.result.ok
    assert preview.session.result.first_error.id == "hole1"
    with pytest.raises(DocumentError, match="potvrdit"):
        plate.apply_feature_preview(preview)
    assert plate.document == before and plate.result is result


def test_edit_repairs_invalid_source(plate):
    f = plate.feature("extrude1")
    f["distance"] = "neznamy"
    plate.update_feature("extrude1", f)
    assert not plate.result.ok
    preview = plate.begin_feature_edit("extrude1")
    assert not preview.ready
    f["distance"] = 10
    preview.session.update_feature("extrude1", f)
    plate.apply_feature_preview(preview)
    assert plate.result.part.is_valid
    assert plate.properties.volume_mm3 == pytest.approx(39840-320*math.pi)
    plate.undo()
    assert not plate.result.ok


@pytest.mark.parametrize("tamper", ["info", "order", "another", "stale"])
def test_edit_rejects_changes_outside_target(plate, tamper):
    preview = plate.begin_feature_edit("extrude1")
    if tamper == "info":
        preview.session.set_info(name="Jiný díl")
    elif tamper == "order":
        preview.session.move_feature("fillet2", -1)
    elif tamper == "another":
        f = preview.session.feature("fillet2")
        f["radius"] = 1
        preview.session.update_feature("fillet2", f)
    else:
        plate.set_info(name="Změněný zdroj")
    before = copy.deepcopy(plate.document)
    with pytest.raises(DocumentError):
        plate.apply_feature_preview(preview)
    assert plate.document == before


def test_background_edit_latest_result_and_cancel(plate):
    from skodacad.worker import BackgroundRebuilder

    runner = BackgroundRebuilder()
    original, result = copy.deepcopy(plate.document), plate.result
    try:
        preview = plate.begin_feature_edit("extrude1", runner=runner)
        for distance in (12, 15):
            f = preview.session.feature("extrude1")
            f["distance"] = distance
            preview.session.update_feature("extrude1", f)
        with pytest.raises(DocumentError, match="spočítaný"):
            plate.apply_feature_preview(preview)
        assert preview.session.wait(45) and preview.ready
        assert preview.session.properties.volume_mm3 == pytest.approx(59760-480*math.pi)
        assert plate.document == original and plate.result is result
        preview.cancel()
        assert not preview.session.computing
        assert plate.document == original and plate.result is result
        pending = plate.begin_feature_edit("extrude1", runner=runner)
        f["distance"] = 17
        pending.session.update_feature("extrude1", f)
        assert pending.session.computing
        pending.cancel()
        assert not pending.session.computing
        assert plate.document == original and plate.result is result
    finally:
        runner.close()
