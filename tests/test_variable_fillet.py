"""P6: analytický objem, kruhové řezy, tečnost, odmítnutí a přenos historie."""

import copy
import json
import math

import pytest
from build123d import Axis, Box, Compound, Cylinder, GeomType, Part, Pos, Vector

from skodacad import rebuild, variable_fillet
from skodacad.document import VERSION, Document, DocumentError
from skodacad.ndt.study import part_fingerprint
from skodacad.selectors import select_edges
from skodacad.session import ModelSession


def removed(r1, r2, length=20):
    return (1 - math.pi / 4) * length / 3 * (r1**2 + r1 * r2 + r2**2)


def model(r1=2, r2=6, reverse=False):
    return Document.from_dict({"format": "skodacad", "version": VERSION,
        "parameters": {"H": 20}, "features": [
        {"id": "sketch", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": 40, "height": 30}]},
        {"id": "block", "type": "extrude", "sketch": "sketch", "distance": "H"},
        {"id": "round", "type": "variable_fillet", "radius_start": r1, "radius_end": r2,
         "edges": {"near": [20, 15, 10], "parallel": "Z"}, "direction": [0, 0, 1],
         "origin": "block", "normals": [[1, 0, 0], [0, 1, 0]], "reverse": reverse}]})


@pytest.mark.parametrize(("r1", "r2", "reverse"), [(3, 3, False), (2, 6, False),
                                                    (6, 2, False), (2, 6, True)])
def test_volume_sections_and_tangency_along_entire_edge(r1, r2, reverse):
    result = rebuild(model(r1, r2, reverse))
    assert result.ok, result.first_error
    part = result.part
    assert part.is_valid and len(part.solids()) == 1
    assert part.volume == pytest.approx(24000 - removed(r1, r2), abs=2e-6)
    curved, = [f for f in part.faces() if f.geom_type != GeomType.PLANE]
    # Independent geometry: every sampled point lies on the requested horizontal circle.
    for u in [0.1, 0.3, 0.5, 0.7, 0.9]:
        for v in [0.05, 0.2, 0.4, 0.6, 0.8, 0.95]:
            p = curved.position_at(u, v)
            t = p.Z / 20
            radius = r1 + (r2 - r1) * (1 - t if reverse else t)
            center = Vector(20 - radius, 15 - radius, p.Z)
            assert (p - center).length == pytest.approx(radius, abs=2e-6)
    contacts = [e for e in curved.edges() if e.bounding_box().size.Z > 19]
    assert len(contacts) == 2
    for edge in contacts:
        for t in [0.05, 0.25, 0.5, 0.75, 0.95]:
            p = edge.position_at(t)
            normal = curved.normal_at(p)
            wanted = Vector(1, 0, 0) if abs(p.X - 20) < 1e-6 else Vector(0, 1, 0)
            assert normal.dot(wanted) > 1 - 1e-8


@pytest.mark.parametrize("angle", [0, 31, 180])
def test_spatial_orientation_and_other_solid_are_preserved(angle):
    body = Box(40, 30, 20).rotate(Axis.Y, angle)
    other = Pos(100, 0, 0) * Box(4, 5, 6)
    part = Part(Compound([body, other]).wrapped)
    where = Vector(20, 15, 0).rotate(Axis.Y, angle)
    edge, = select_edges(part, {"type": "line", "near": list(where)}, float)
    ref = variable_fillet.reference(part, edge, [("body", part)])
    result = variable_fillet.apply(part, edge, 2, 6, ref["direction"], normals=ref["normals"])
    assert result.is_valid and len(result.solids()) == 2
    assert result.volume == pytest.approx(24120 - removed(2, 6), abs=2e-6)
    assert any(s.volume == pytest.approx(120) and s.center().X == pytest.approx(100)
               for s in result.solids())
    assert part.volume == pytest.approx(24120)


def test_distant_hole_survives_and_near_hole_is_rejected():
    for x, y, accepted in [(0, 0, True), (18, 13, False)]:
        part = Box(40, 30, 20) - Pos(x, y, 0) * Cylinder(1.5, 20)
        edge, = select_edges(part, {"near": [20, 15, 0], "parallel": "Z"}, float)
        ref = variable_fillet.reference(part, edge, [("body", part)])
        if accepted:
            result = variable_fillet.apply(part, edge, 2, 6, ref["direction"],
                                            normals=ref["normals"])
            assert result.volume == pytest.approx(24000 - math.pi * 1.5**2 * 20
                                                  - removed(2, 6), abs=2e-6)
        else:
            with pytest.raises(variable_fillet.VariableFilletError, match="detailu"):
                variable_fillet.apply(part, edge, 2, 6, ref["direction"], normals=ref["normals"])
        assert part.volume == pytest.approx(24000 - math.pi * 1.5**2 * 20)


@pytest.mark.parametrize(("change", "message"), [
    ({"origin": "missing"}, "Původ"), ({"normals": [[-1, 0, 0], [0, -1, 0]]}, "Boky"),
    ({"direction": [1, 0, 0]}, "Směr"), ({"direction": [0, 0, 0]}, "nulový"),
    ({"reverse": "yes"}, "ano/ne"), ({"radius_start": 0}, "větší než 0"),
    ({"radius_end": -2}, "větší než 0"), ({"radius_start": 80, "radius_end": 80}, "nevejde"),
    ({"edges": {"parallel": "Z"}}, "právě jednu"),
])
def test_rejection_keeps_previous_geometry_and_skips_following(change, message):
    doc = model()
    doc.features[-1].update(change)
    doc.features.append({"id": "after", "type": "fillet", "edges": "all", "radius": 1})
    result = rebuild(doc)
    assert not result.ok and message in result.first_error.message
    assert result.part is result.parts_before["round"]
    assert result.part.volume == pytest.approx(24000)
    assert result.statuses[-1].status == "skipped"


def test_curves_and_concave_edges_are_rejected_before_construction():
    cylinder = Cylinder(5, 20)
    circle, = select_edges(cylinder, {"type": "circle", "near": [5, 0, 10]}, float)
    with pytest.raises(variable_fillet.VariableFilletError, match="přímou"):
        variable_fillet.reference(cylinder, circle, [("body", cylinder)])
    concave = Box(40, 30, 20) - Pos(10, 7.5, 0) * Box(20, 15, 20)
    edge, = select_edges(concave, {"near": [0, 0, 0], "parallel": "Z"}, float)
    with pytest.raises(variable_fillet.VariableFilletError, match="vnitřní kout"):
        variable_fillet.reference(concave, edge, [("body", concave)])


def test_oblique_end_face_is_rejected():
    part = Box(40, 30, 20) - Pos(0, 0, 10) * Box(100, 100, 10).rotate(Axis.X, 15)
    edge, = select_edges(part, {"near": [20, 15, 0], "parallel": "Z"}, float)
    with pytest.raises(variable_fillet.VariableFilletError, match="konce"):
        variable_fillet.reference(part, edge, [("body", part)])


def test_session_selection_direction_undo_save_and_old_format(tmp_path):
    path = tmp_path / "part.json"
    doc = model()
    doc.features.pop()
    doc.save(path)
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 24
    session = ModelSession()
    session.open(path)
    before = part_fingerprint(session.document)
    edge, = select_edges(session.result.part, {"near": [20, 15, 10], "parallel": "Z"}, float)
    fid = session.add_from_selection("variable_fillet", [edge.wrapped])
    feature = session.feature(fid)
    feature.update(radius_start=2, radius_end=6)
    session.update_feature(fid, feature)
    assert session.result.part.volume == pytest.approx(24000 - removed(2, 6), abs=2e-6)
    assert part_fingerprint(session.document) != before
    session.set_parameter("H", "30")
    assert session.result.part.volume == pytest.approx(36000 - removed(2, 6, 30), abs=2e-6)
    session.undo()
    lines = session.feature_direction(fid)
    assert lines[0][0].Z == pytest.approx(0) and lines[1][1].Z == pytest.approx(20)
    feature["reverse"] = True
    session.update_feature(fid, feature)
    assert session.feature_direction(fid)[0][0].Z == pytest.approx(20)
    session.undo()
    assert session.feature_direction(fid)[0][0].Z == pytest.approx(0)
    session.redo()
    session.document.save(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["version"] == 32
    reopened = ModelSession()
    reopened.open(path)
    assert reopened.result.ok and reopened.document == session.document
    assert reopened.result.part.volume == pytest.approx(session.result.part.volume, abs=1e-6)
    saved["version"] = 31
    with pytest.raises(DocumentError, match="32"):
        Document.from_dict(saved)
    old = copy.deepcopy(doc)
    for number in range(1, 33):
        data = old.to_dict()
        data["version"] = number
        assert rebuild(Document.from_dict(data)).ok
