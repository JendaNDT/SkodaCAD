"""P1.3 C.1: groups versus single references, ties, hard filters and physical rollback."""

import copy
import math

import pytest
from build123d import Box, Cylinder, Edge, Part, Pos, Vector

from conftest import box_features, make_doc
from reference_cases import OrderedShapes
from skodacad import rebuild
from skodacad.selectors import (
    SelectionError,
    face_plane,
    find_face,
    select_edges,
    select_faces,
)


@pytest.fixture
def box():
    return Box(20, 30, 40)


@pytest.mark.parametrize("reverse", [False, True])
def test_equidistant_edges_reject_without_removing_original_material(reverse):
    doc = make_doc(box_features() + [
        {"id": "edit", "type": "fillet", "radius": 3,
         "edges": {"parallel": "Z", "near": [0, -15, 20]}},
        {"id": "tail", "type": "sketch", "elements": [{"shape": "circle", "diameter": 2}]},
    ])
    original = copy.deepcopy(doc.to_dict())
    result = rebuild(doc)
    assert result.first_error.id == "edit" and "není jednoznačný" in result.first_error.message
    assert result.statuses[-1].status == "skipped"
    assert result.part.is_valid and len(result.part.solids()) == 1
    assert result.part.volume == pytest.approx(24000)
    assert result.part.is_inside((9.9, -14.9, 20))
    assert result.part.is_inside((-9.9, -14.9, 20))
    assert doc.to_dict() == original
    part = result.parts_before["edit"]
    view = OrderedShapes(edges=part.edges(), reverse=reverse)
    with pytest.raises(SelectionError, match="2 hrany"):
        select_edges(view, doc.features[-2]["edges"], float)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("gap", [0, 0.5e-4, 1e-4, 2e-4])
@pytest.mark.parametrize("third", [False, True])
def test_edge_distance_boundary_and_duplicates(monkeypatch, reverse, gap, third):
    edges = [Edge.make_line((x, 0, 0), (x, 0, 5)) for x in (0, 2, 4)]
    distances = [1.0, 1.0 + gap, 10.0]
    for edge, distance in zip(edges, distances, strict=True):
        monkeypatch.setattr(edge, "distance_to", lambda _p, d=distance: d)
    chosen = edges if third else edges[:2]
    view = OrderedShapes(edges=[*chosen, edges[0]], reverse=reverse)
    if gap <= 1e-4:
        with pytest.raises(SelectionError, match="2 hrany"):
            select_edges(view, {"near": [0, 0, 0]}, float)
    else:
        assert select_edges(view, {"near": [0, 0, 0]}, float) == [edges[0]]


@pytest.mark.parametrize("gap", [0.5e-4, 2e-4])
def test_distance_tie_on_real_geometry(gap):
    edges = [Edge.make_line((x, 0, -5), (x, 0, 5)) for x in (0, gap)]
    view = OrderedShapes(edges=edges)
    if gap < 1e-4:
        with pytest.raises(SelectionError, match="není jednoznačný"):
            select_edges(view, {"near": [0, 0, 0]}, float)
    else:
        assert select_edges(view, {"near": [0, 0, 0]}, float) == [edges[0]]


@pytest.mark.parametrize("reverse", [False, True])
def test_two_bodies_have_ambiguous_faces_but_a_valid_named_plane(reverse):
    pair = Part((Pos(-20, 0, 0) * Box(20, 20, 10)).solids()
                + (Pos(20, 0, 0) * Box(20, 20, 10)).solids())
    assert pair.is_valid and len(pair.solids()) == 2 and pair.volume == pytest.approx(8000)
    view = OrderedShapes(faces=[*pair.faces(), pair.faces()[0]], reverse=reverse)
    with pytest.raises(SelectionError, match="2 stejně vhodných ploch"):
        find_face(view, {"at": [0, 0, 5], "normal": [0, 0, 1], "type": "plane"})
    assert len(select_faces(view, "top")) == 2
    assert tuple(face_plane(view, "top").origin) == pytest.approx((0, 0, 5))
    assert len(select_edges(pair, {"face": "top"}, float)) == 8


@pytest.mark.parametrize("reverse", [False, True])
def test_named_plane_uses_extreme_not_first_level_inside_group_band(reverse):
    pair = Part((Pos(-20, 0, 0) * Box(20, 20, 10)).solids()
                + (Pos(20, 0, 0.00005) * Box(20, 20, 10)).solids())
    view = OrderedShapes(faces=pair.faces(), reverse=reverse)
    assert len(select_faces(view, "top")) == 2
    assert face_plane(view, "top").origin.Z == pytest.approx(5.00005, abs=1e-10)


def test_group_union_keeps_every_prescribed_edge_once(box):
    edges = select_edges(box, [{"face": "top"}, {"face": "front"}], float)
    assert len(edges) == 7
    assert sum(edge.length for edge in edges) == pytest.approx(200)
    view = OrderedShapes(edges=[*box.edges(), *box.edges()])
    assert len(select_edges(view, "all", float)) == 12
    assert len(select_edges(box, {"parallel": "Z"}, float)) == 4


@pytest.mark.parametrize("normal", [None, [1, -1, 0]])
def test_edge_point_on_two_faces_needs_a_distinguishing_normal(box, normal):
    spec = {"at": [10, -15, 0]}
    if normal is not None:
        spec["normal"] = normal
    with pytest.raises(SelectionError, match="není jednoznačná"):
        find_face(box, spec)
    face, _ = find_face(box, {**spec, "normal": [100, 0, 0]})
    assert tuple(face.normal_at()) == pytest.approx((1, 0, 0))
    assert face.area == pytest.approx(1200)


@pytest.mark.parametrize("gap", [0, 0.5e-6, 1e-6, 2e-6])
def test_normal_score_boundary_is_independent_of_order(monkeypatch, gap):
    faces = [Box(1, 1, 1).faces()[0], Box(1, 1, 1).faces()[0]]
    point = Vector(0, 0, 0)
    for face, score in zip(faces, [1.0, 1.0 - gap], strict=True):
        monkeypatch.setattr(face, "distance_to_with_closest_points", lambda _v: (0, point, point))
        normal = Vector(math.sqrt(1 - score**2), 0, score)
        monkeypatch.setattr(face, "normal_at", lambda _p=None, n=normal: n)
    for reverse in (False, True):
        view = OrderedShapes(faces=faces, reverse=reverse)
        if gap <= 1e-6:
            with pytest.raises(SelectionError, match="není jednoznačná"):
                find_face(view, {"at": [0, 0, 0], "normal": [0, 0, 1]})
        else:
            assert find_face(view, {"at": [0, 0, 0], "normal": [0, 0, 1]})[0] is faces[0]


def test_equal_geometry_is_not_the_same_face_but_repeated_same_shape_is(box):
    face, _ = find_face(box, {"at": [0, 0, 20], "normal": [0, 0, 1]})
    duplicate = copy.deepcopy(face)
    assert not duplicate.is_same(face)
    spec = {"at": [0, 0, 20], "normal": [0, 0, 1]}
    assert find_face(OrderedShapes(faces=[face, face]), spec)[0] is face
    with pytest.raises(SelectionError, match="2 stejně vhodných ploch"):
        find_face(OrderedShapes(faces=[face, duplicate]), spec)


@pytest.mark.parametrize("gap", [0, 0.5e-4, 1e-4, 2e-4])
def test_face_distance_band_boundary(monkeypatch, gap):
    faces = [Box(1, 1, 1).faces()[0], Box(1, 1, 1).faces()[0]]
    point = Vector(0, 0, 0)
    for face, distance in zip(faces, [1.0, 1.0 + gap], strict=True):
        monkeypatch.setattr(face, "distance_to_with_closest_points",
                            lambda _v, d=distance: (d, point, point))
    for reverse in (False, True):
        view = OrderedShapes(faces=faces, reverse=reverse)
        if gap <= 1e-4:
            with pytest.raises(SelectionError, match="není jednoznačná"):
                find_face(view, {"at": [0, 0, 0]})
        else:
            assert find_face(view, {"at": [0, 0, 0]})[0] is faces[0]


def test_radius_boundary_remains_strict_for_faces_and_inclusive_for_edges():
    # Výběrová mez, nikoli slib objemového modelování libovolně malých dílů.
    part = Cylinder(2e-6, 1)
    assert len(select_edges(part, {"radius": 1e-6}, float)) == 2
    with pytest.raises(SelectionError, match="už na dílu není"):
        find_face(part, {"at": [2e-6, 0, 0], "type": "cylinder", "radius": 1e-6})


def test_fixed_face_radius_is_hard_and_missing_type_is_not_a_fallback():
    part = Cylinder(5, 10)
    spec = {"at": [5, 0, 0], "normal": [1, 0, 0], "type": "cylinder", "radius": 5}
    assert find_face(part, spec)[0].radius == pytest.approx(5)
    for changed in ({"radius": 99}, {"radius": 6}, {"type": "sphere"}):
        with pytest.raises(SelectionError, match="už na dílu není"):
            find_face(part, {**spec, **changed})
    with pytest.raises(SelectionError, match="už na dílu není"):
        find_face(part, {"at": [5, 0, 0], "normal": [1, 0, 0], "type": "plane"})


@pytest.mark.parametrize("bad", [
    None, [], {"at": [0, 0]}, {"at": [0, 0, 0, 0]}, {"at": "000"},
    {"at": [0, math.inf, 0]}, {"at": [0, 0, math.nan]}, {"at": [0, False, 0]},
    {"at": [0, 0, 0], "normal": [0, 0, 0]},
    {"at": [0, 0, 0], "normal": [0, math.inf, 1]},
    {"at": [0, 0, 0], "normal": [0, 1]},
    {"at": [0, 0, 0], "type": "unknown"}, {"at": [0, 0, 0], "type": []},
    {"at": [0, 0, 0], "radius": 5}, {"at": [0, 0, 0], "radius": 0, "type": "cylinder"},
    {"at": [0, 0, 0], "radius": -1, "type": "sphere"},
    {"at": [0, 0, 0], "radius": math.nan, "type": "cylinder"},
    {"at": [0, 0, 0], "radius": math.inf, "type": "cylinder"},
    {"at": [0, 0, 0], "type": "cone", "radius": 5}, {"at": [0, 0, 0], "surprise": 1},
])
def test_bad_face_input_is_rejected_before_accessing_geometry(bad):
    with pytest.raises(SelectionError):
        find_face(object(), bad)


@pytest.mark.parametrize("bad", [
    {"face": []}, {"between": ["top", {}]}, {"type": []}, {"parallel": []},
    {"near": [0, 0]}, {"near": [0, 0, 0, 0]}, {"near": [0, 0, math.nan]},
    {"near": [0, math.inf, 0]}, {"radius": 0}, {"radius": -1}, {"radius": math.nan},
    {"radius": math.inf}, {"radius": True}, {"surprise": 1},
])
def test_bad_edge_input_is_validated_before_any_geometry_filter(bad):
    with pytest.raises(SelectionError):
        select_edges(object(), bad, float)
    with pytest.raises(SelectionError):
        select_edges(object(), [{"radius": 99}, bad], float)


def test_invalid_near_is_not_hidden_by_an_empty_circle_filter(box):
    with pytest.raises(SelectionError, match="„near“ musí být bod"):
        select_edges(box, {"type": "circle", "near": [0, 0]}, float)


def test_split_top_face_rejects_point_in_slot_but_preserves_named_group():
    part = Box(40, 30, 10) - Box(4, 40, 4).moved(Pos(0, 0, 4))
    assert part.is_valid and len(part.solids()) == 1
    assert part.volume == pytest.approx(12000 - 4 * 30 * 3)
    assert len(select_faces(part, "top")) == 2
    assert face_plane(part, "top").origin.Z == pytest.approx(5)
    with pytest.raises(SelectionError, match="není jednoznačná"):
        find_face(part, {"at": [0, 0, 5], "normal": [0, 0, 1], "type": "plane"})
