"""P2.4: návrh nemění model, potvrzení a neplatné výběry."""

import copy
import math

import pytest
from build123d import Vector

from conftest import EXAMPLES, face_at
from skodacad.assistant import ModelTools
from skodacad.document import DocumentError
from skodacad.session import ModelSession


@pytest.fixture
def session():
    session = ModelSession()
    session.new_document("Test")
    session.add_feature("sketch")
    session.add_feature("extrude")
    return session


def test_preview_apply_and_undo_are_atomic(session, tmp_path):
    before = copy.deepcopy(session.document)
    face = face_at(session.result.part, 0, 0, 10)
    preview = session.preview_direct_edit("move_face", [face], (0, 0, 10), 2)
    assert session.document == before
    assert preview.feature["origin"] == "extrude1"
    assert preview.result.part.volume == pytest.approx(40 * 30 * 12)
    session.apply_direct_edit(preview)
    assert session.result.part.volume == pytest.approx(40 * 30 * 12)
    session.undo()
    assert session.document == before
    session.redo()
    assert session.result.part.volume == pytest.approx(40 * 30 * 12)
    path = tmp_path / "model.json"
    session.document.save(path)
    reopened = ModelSession()
    reopened.open(path)
    assert reopened.result.ok
    assert reopened.result.part.volume == pytest.approx(40 * 30 * 12)


def test_rejected_and_stale_previews_do_not_change_model(session):
    face = face_at(session.result.part, 0, 0, 10)
    before = copy.deepcopy(session.document)
    with pytest.raises(DocumentError, match="Původní model se nezměnil"):
        session.preview_direct_edit("move_face", [face], (0, 0, 10), -100)
    with pytest.raises(DocumentError):
        session.preview_direct_edit("face_diameter", [face], (0, 0, 10), 12)
    assert session.document == before
    preview = session.preview_direct_edit("move_face", [face], (0, 0, 10), 2)
    session.set_info(name="Změněno")
    changed = copy.deepcopy(session.document)
    with pytest.raises(DocumentError, match="změnil"):
        session.apply_direct_edit(preview)
    assert session.document == changed


def test_hole_preview_changes_radius_and_volume(session):
    session.add_feature("hole", values={"kind": "clearance", "plane": "top",
                                        "positions": [[0, 0]], "diameter": 10,
                                        "through_all": True})
    assert session.result.ok
    face = face_at(session.result.part, 5, 0, 5)
    preview = session.preview_direct_edit("face_diameter", [face], (5, 0, 5), 12)
    assert preview.result.part.volume == pytest.approx(40 * 30 * 10 - math.pi * 6**2 * 10)
    assert preview.feature["origin"] == "hole1"


def test_existing_selection_and_value_preview_preserve_origin(session):
    face = face_at(session.result.part, 0, 0, 10)
    first = session.preview_direct_edit("move_face", [face], (0, 0, 10), 2)
    feature_id = session.apply_direct_edit(first)
    before = copy.deepcopy(session.document)
    feature = session.feature(feature_id)
    feature["distance"] = 3
    changed = session.preview_direct_feature(feature)
    assert session.document == before
    assert changed.feature["origin"] == first.feature["origin"]
    assert changed.result.part.volume == pytest.approx(40 * 30 * 13)
    bottom = face_at(session.result.part, 0, 0, 0)
    selected = session.preview_direct_edit("move_face", [bottom], (0, 0, 0), 2, feature_id)
    assert selected.feature["face"]["normal"] == pytest.approx([0, 0, -1])
    assert selected.feature["origin"] == "extrude1"
    session.apply_direct_edit(selected)
    assert session.result.part.volume == pytest.approx(40 * 30 * 12)


def test_assistant_direct_edit_requires_confirmation_and_blocks_bypass(session):
    before = copy.deepcopy(session.document)
    requests = []
    tools = ModelTools(session, direct_edit=lambda kind, value: requests.append((kind, value))
                       or False)
    output = tools.run("propose_direct_edit", {"kind": "move_face", "value": 2})
    assert not output.changed and requests == [("move_face", 2)]
    assert session.document == before
    output = tools.run("add_feature", {"feature": {"type": "move_face"}})
    assert output.is_error and session.document == before
    model = before.to_dict()
    model["features"].append({"id": "x", "type": "move_face"})
    assert tools.run("replace_model", {"model": model}).is_error
    assert session.document == before


def test_wrong_selected_point_is_rejected(session):
    face = face_at(session.result.part, 0, 0, 10)
    with pytest.raises(DocumentError, match="neleží"):
        session.preview_direct_edit("move_face", [face], Vector(0, 0, 100), 2)


def test_q24_ndt_stales_and_saved_measurement_updates_then_undo():
    session = ModelSession()
    session.open(EXAMPLES / "ndt" / "deska.json")
    assert all(study.state == "ok" for study in session.ndt_studies)
    face = face_at(session.result.part, 0, 0, 20)
    session.add_measurement([face], "thickness", (0, 0, 20))
    face = face_at(session.result.part, 0, 0, 20)
    assert "20.00 mm" in session.measurements[0].text
    preview = session.preview_direct_edit("move_face", [face], (0, 0, 20), 5)
    assert all(study.state == "ok" for study in session.ndt_studies)
    session.apply_direct_edit(preview)
    assert all(study.state == "stale" for study in session.ndt_studies)
    assert "25.00 mm" in session.measurements[0].text
    session.undo()
    assert all(study.state == "ok" for study in session.ndt_studies)
    assert "20.00 mm" in session.measurements[0].text
