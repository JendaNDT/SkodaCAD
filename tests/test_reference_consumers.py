"""P1.3 C.2: rejected references cannot become valid measurements/projections/NDT targets."""

import copy
import math

import pytest
from build123d import Edge, Plane, Rectangle

from conftest import box_features, face_at, make_doc
from reference_cases import OrderedShapes
from skodacad import DocumentError, rebuild
from skodacad.measure import MeasureError, face_reference, reference_for
from skodacad.ndt import mt, pt, rt
from skodacad.ndt.geometry import PartGeometry
from skodacad.ndt.study import StudyError, target_for
from skodacad.profile_edit import add_circle, add_point, add_reference, empty_profile
from skodacad.projection import ProjectionError
from skodacad.projection import reference_for as projected_reference
from skodacad.session import ModelSession


def blocks():
    features = []
    for number in (1, 2):
        features.extend([
            {"id": f"s{number}", "type": "sketch", "elements": [
                {"shape": "rectangle", "width": 20, "height": 20,
                 "center": [f"x{number}", 0]}]},
            {"id": f"e{number}", "type": "extrude", "sketch": f"s{number}",
             "distance": 10, "operation": "add"},
        ])
    return make_doc(features, {"x1": -20, "x2": 20})


def session_for(document):
    session = ModelSession()
    session.document = document
    session.rebuild()
    assert session.result.ok
    return session


@pytest.mark.parametrize("method", ["UT", "PT", "MT", "RT"])
def test_ambiguous_study_cannot_be_confirmed_and_repair_has_undo_history(method):
    session = session_for(blocks())
    face = face_at(session.result.part, -20, 0, 10)
    sid = session.add_ndt_study(method, [face.wrapped], (-20, 0, 10))
    session.verify_ndt_study(sid, "Regresní test")  # pouze test stavu metadat, ne odborná validace
    face = face_at(session.result.part, -20, 0, 10)
    mid = session.add_measurement([face.wrapped], "area", (-20, 0, 10))
    assert next(m for m in session.measurements if m.id == mid).value.value == pytest.approx(400)
    session.set_parameter("x1", "-60")
    assert session.result.ok and session.result.part.is_valid
    assert session.result.part.volume == pytest.approx(8000)
    assert len(session.result.part.solids()) == 2
    assert session.ndt_studies[0].state == "broken"
    assert "není jednoznačná" in session.ndt_studies[0].messages[0]
    saved = next(m for m in session.measurements if m.id == mid)
    assert saved.value is None and "není jednoznačná" in saved.error
    before = copy.deepcopy(session.document.to_dict())
    with pytest.raises(DocumentError, match="Studii nejde potvrdit.*není jednoznačná"):
        session.confirm_ndt_study(sid)
    assert session.document.to_dict() == before
    assert session.ndt_study(sid)["target"]["faces"][0]["face"]["at"] == [-20, 0, 10]
    session.undo()  # odmítnuté potvrzení nepřidalo krok; vrací se posunutí kvádru
    assert session.result.parameters["x1"] == -20 and session.ndt_studies[0].state == "ok"
    session.redo()
    assert session.ndt_studies[0].state == "broken"
    face = face_at(session.result.part, -60, 0, 10)
    session.set_ndt_target(sid, [face.wrapped], (-60, 0, 10))
    assert session.ndt_studies[0].state == "stale"
    assert not session.ndt_study(sid).get("verified")
    session.confirm_ndt_study(sid)  # správná nová vazba neruší samostatnou kontrolu studie
    assert session.ndt_studies[0].state == "ok"
    session.undo()
    assert session.ndt_studies[0].state == "stale"
    session.undo()
    assert session.ndt_studies[0].state == "broken"
    session.redo()
    assert session.ndt_studies[0].state == "stale"
    session.redo()
    assert session.ndt_studies[0].state == "ok"


def test_fixed_radius_change_is_visible_until_explicit_new_selection():
    doc = make_doc([
        {"id": "s", "type": "sketch", "elements": [{"shape": "circle", "diameter": "D"}]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 10},
    ], {"D": 10})
    session = session_for(doc)
    face = face_at(session.result.part, 5, 0, 5)
    sid = session.add_ndt_study("PT", [face.wrapped], (5, 0, 5))
    face = face_at(session.result.part, 5, 0, 5)
    mid = session.add_measurement([face.wrapped], "diameter", (5, 0, 5))
    assert session.measurements[0].value.value == pytest.approx(10)
    session.set_parameter("D", "12")
    assert session.result.ok and session.result.part.volume == pytest.approx(math.pi * 36 * 10)
    assert session.measurements[0].value is None and session.ndt_studies[0].state == "broken"
    before = copy.deepcopy(session.document.to_dict())
    with pytest.raises(DocumentError, match="Studii nejde potvrdit"):
        session.confirm_ndt_study(sid)
    assert session.document.to_dict() == before
    face = face_at(session.result.part, 6, 0, 5)
    session.set_ndt_target(sid, [face.wrapped], (6, 0, 5))
    assert session.ndt_studies[0].state == "stale"
    session.confirm_ndt_study(sid)
    assert session.ndt_studies[0].state == "ok"
    session.remove_measurement(mid)
    face = face_at(session.result.part, 6, 0, 5)
    session.add_measurement([face.wrapped], "diameter", (6, 0, 5))
    assert session.measurements[0].value.value == pytest.approx(12)


@pytest.mark.parametrize(("method", "resolver", "error"), [
    ("PT", pt.study_faces, pt.PtError), ("MT", mt.study_faces, mt.MtError),
    ("RT", rt.study_target, rt.RtError),
])
def test_ndt_methods_cannot_silently_use_only_the_unbroken_subset(method, resolver, error):
    part = rebuild(blocks(), {"x1": -60}).part
    good = face_reference(face_at(part, 20, 0, 10), (20, 0, 10))
    bad = {"face": {"at": [-20, 0, 10], "normal": [0, 0, 1], "type": "plane"}}
    record = {"method": method, "target": {"kind": "faces", "faces": [good, bad]}}
    geo = PartGeometry(part)
    found, problems = geo.faces_of(record["target"])
    assert len(found) == len(problems) == 1 and "není jednoznačná" in problems[0]
    with pytest.raises(error, match="není jednoznačná"):
        resolver(geo, record)


def test_projection_reports_ambiguity_and_never_reuses_stale_points():
    profile = empty_profile()
    rid = add_reference(profile, {"edge": {"parallel": "Z", "near": [0, -15, 20]},
                                  "kind": "line", "points": [[-10, -15], [10, -15]]})
    add_circle(profile, add_point(profile, 0, 0), 1)
    doc = make_doc(box_features() + [
        {"id": "follow", "type": "sketch", "plane": "top", "elements": [profile]},
        {"id": "tail", "type": "extrude", "sketch": "follow", "distance": 2},
    ])
    original = copy.deepcopy(doc.to_dict())
    result = rebuild(doc)
    assert result.first_error.id == "follow" and result.statuses[-1].status == "skipped"
    assert "Promítnutá hrana" in result.first_error.message
    assert "není jednoznačný" in result.first_error.message
    assert result.part.volume == pytest.approx(24000) and len(result.part.solids()) == 1
    assert "follow" not in result.sketches and doc.to_dict() == original
    doc.features[-2]["elements"][0]["references"][rid]["edge"] = {"between": ["top", "front"]}
    repaired = rebuild(doc)
    assert repaired.ok and repaired.part.is_valid
    assert repaired.part.volume == pytest.approx(24000 + 2 * math.pi)
    assert not result.part.is_inside((0, 0, 41)) and repaired.part.is_inside((0, 0, 41))


def test_unrepresentable_new_references_use_each_consumers_domain_error():
    face = Rectangle(10, 10).faces()[0]
    part = OrderedShapes(faces=[face, copy.deepcopy(face)])
    with pytest.raises(MeasureError, match="není jednoznačná"):
        reference_for(part, face, (0, 0, 0))
    with pytest.raises(StudyError, match="není jednoznačná"):
        target_for(part, [face], (0, 0, 0))
    edge = Edge.make_line((0, 0, 0), (10, 0, 0))
    part = OrderedShapes(edges=[edge, copy.deepcopy(edge)])
    with pytest.raises(ProjectionError, match="nelze jednoznačně popsat"):
        projected_reference(part, edge, Plane.XY)


def test_a_later_merged_face_cannot_be_guessed_as_one_of_two_earlier_faces():
    doc = blocks()
    doc.features.extend([
        {"id": "follow", "type": "sketch", "plane": "top", "elements": [
            {"shape": "circle", "diameter": 2}]},
        {"id": "bridge_s", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": 60, "height": 20}]},
        {"id": "bridge", "type": "extrude", "sketch": "bridge_s", "distance": 10},
    ])
    session = session_for(doc)
    assert session.result.part.volume == pytest.approx(12000)
    assert len(session.result.part.solids()) == 1
    earlier = session.result.parts_before["follow"]
    assert len(earlier.solids()) == 2 and earlier.volume == pytest.approx(8000)
    face = face_at(session.result.part, 0, 0, 10)
    assert face.area == pytest.approx(1200)
    before = copy.deepcopy(session.document.to_dict())
    with pytest.raises(DocumentError, match="nemá žádný doložený protějšek"):
        session.apply_selection("follow", [face.wrapped])
    assert session.document.to_dict() == before
    assert session.result.part.volume == pytest.approx(12000)
