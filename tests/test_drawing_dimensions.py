"""Kóty se přepočítají, jen pokud lze doložit jejich původ a aktuálnost."""
from __future__ import annotations

import copy

import pytest
from build123d import GeomType

from skodacad.document import VERSION, Document, DocumentError
from skodacad.drawing_dimensions import evaluate, new_cylinder, new_overall
from skodacad.rebuild import rebuild
from skodacad.session import ModelSession
from skodacad.worker import decode_result, encode_result


def model() -> Document:
    return Document(parameters={"D": 20, "H": 10}, features=[
        {"id": "plate_sketch", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": 100, "height": 60}]},
        {"id": "plate", "type": "extrude", "sketch": "plate_sketch", "distance": "H"},
        {"id": "hole_sketch", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "circle", "diameter": "D"}]},
        {"id": "hole", "type": "extrude", "sketch": "hole_sketch", "operation": "cut",
         "through_all": True},
    ])


def cylinder(result):
    return next(face for face in result.part.faces() if face.geom_type == GeomType.CYLINDER)


def test_parameter_changes_recompute_without_silent_retarget():
    document = model()
    result = rebuild(document)
    d = new_cylinder(document, result, "d1", cylinder(result), "diameter")
    assert evaluate(document, result, d).value == pytest.approx(20)
    changed = copy.deepcopy(document)
    changed.parameters["D"] = 24
    assert evaluate(changed, result, d).value is None  # stale result
    assert evaluate(changed, rebuild(changed), d).value == pytest.approx(24)
    changed.features = changed.features[:2]  # hole removed
    assert evaluate(changed, rebuild(changed), d).value is None


def test_overall_is_explicitly_the_complete_part_envelope():
    document = model()
    result = rebuild(document)
    d = new_overall(document, result, "d1", "z")
    assert evaluate(document, result, d).value == pytest.approx(10)
    document.parameters["H"] = 12
    assert evaluate(document, rebuild(document), d).value == pytest.approx(12)


def test_session_save_roundtrip_undo_and_worker():
    session = ModelSession()
    session.new_document()
    session.replace_document(model().to_dict())
    d = session.add_drawing_dimension("diameter", face=cylinder(session.result))
    assert session.drawing_dimensions()[0].value == pytest.approx(20)
    encoded = session.document.to_dict()
    assert encoded["version"] == 25
    loaded = Document.from_dict(encoded)
    assert loaded.drawing == session.document.drawing
    assert evaluate(loaded, decode_result(encode_result(session.result)),
                    loaded.drawing["dimensions"][0]).value == pytest.approx(20)
    session.remove_drawing_dimension(d)
    assert not session.drawing_dimensions()
    session.undo()
    assert session.drawing_dimensions()[0].value == pytest.approx(20)


def test_invalid_drawing_and_old_version_are_rejected():
    data = model().to_dict()
    data["version"] = VERSION
    data["drawing"] = {"dimensions": [{"id": "d1", "kind": "diameter"}]}
    with pytest.raises(DocumentError):
        Document.from_dict(data)
    data["version"] = VERSION - 1
    with pytest.raises(DocumentError, match="verze 25"):
        Document.from_dict(data)


def test_several_circles_in_one_feature_are_not_safe_to_bind():
    document = model()
    document.features[2]["elements"].append(
        {"shape": "circle", "diameter": "D", "center": [30, 0]})
    result = rebuild(document)
    with pytest.raises(DocumentError, match="jedné kruhové skici"):
        new_cylinder(document, result, "d1", cylinder(result), "diameter")


def test_failed_model_does_not_produce_a_dimension():
    document = model()
    result = rebuild(document)
    dimension = new_overall(document, result, "d1", "x")
    document.parameters["H"] = -1
    evaluated = evaluate(document, rebuild(document), dimension)
    assert evaluated.value is None
    assert evaluated.error


def test_assistant_replacement_preserves_user_drawing():
    from skodacad.assistant import ModelTools, ToolInputError

    session = ModelSession()
    session.new_document()
    session.replace_document(model().to_dict())
    session.add_drawing_dimension("overall", axis="x")
    drawing = copy.deepcopy(session.document.drawing)
    replacement = session.document.to_dict()
    replacement.pop("drawing")
    replacement["features"][0]["elements"][0]["width"] = 120
    ModelTools(session)._tool_replace_model({"model": replacement})
    assert session.document.drawing == drawing
    assert session.drawing_dimensions()[0].value == pytest.approx(120)
    replacement["drawing"] = {"dimensions": []}
    with pytest.raises(ToolInputError, match="Výkres"):
        ModelTools(session)._tool_replace_model({"model": replacement})
    assert session.document.drawing == drawing
