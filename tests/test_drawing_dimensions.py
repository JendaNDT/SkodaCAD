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


def test_distance_between_bound_faces_follows_parameter_and_invalidates_recipe():
    from skodacad.drawing_dimensions import new_distance

    document = Document(parameters={"W": 40, "H": 20}, features=[
        {"id": "sketch", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": "W", "height": 30}]},
        {"id": "body", "type": "extrude", "sketch": "sketch", "distance": "H"},
    ])
    result = rebuild(document)
    faces = [f for f in result.part.faces() if f.geom_type == GeomType.PLANE
             and abs(f.normal_at().X) > 0.9]
    record = new_distance(document, result, "d1", faces)
    document.drawing = {"dimensions": [record]}
    assert Document.from_dict(document.to_dict()).drawing == document.drawing
    assert evaluate(document, result, record).value == pytest.approx(40)
    document.parameters["W"] = 55
    assert evaluate(document, rebuild(document), record).value == pytest.approx(55)
    document.features[0]["elements"][0]["height"] = 31
    assert evaluate(document, rebuild(document), record).value is None


def test_nonparallel_faces_cannot_form_distance_dimension():
    from skodacad.drawing_dimensions import new_distance

    document = model()
    result = rebuild(document)
    faces = [f for f in result.part.faces() if f.geom_type == GeomType.PLANE]
    pair = next((a, b) for a in faces for b in faces
                if abs(a.normal_at().dot(b.normal_at())) < 0.1)
    with pytest.raises(DocumentError, match="rovnoběžné"):
        new_distance(document, result, "d1", list(pair))


def test_session_distance_accepts_two_selected_faces_and_undo():
    session = ModelSession()
    session.new_document()
    session.replace_document(model().to_dict())
    parallel = [face.wrapped for face in session.result.part.faces()
                if face.geom_type == GeomType.PLANE and abs(face.normal_at().Z) > 0.9]
    session.add_drawing_dimension("distance", faces=parallel)
    assert session.drawing_dimensions()[0].value == pytest.approx(10)
    session.set_parameter("H", "15")
    assert session.drawing_dimensions()[0].value == pytest.approx(15)
    session.undo()
    assert session.drawing_dimensions()[0].value == pytest.approx(10)
