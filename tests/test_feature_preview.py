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
