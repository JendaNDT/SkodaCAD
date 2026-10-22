"""P1.3 C.2: prove the whole selected geometry, not merely one matching point."""

import copy
import math

import pytest
from build123d import Box, Cone, Cylinder, Edge, Face, Plane, Pos, Rectangle, Sphere, Torus
from build123d.topology.shape_core import downcast

from reference_cases import OrderedShapes
from skodacad.picking import edge_selector, face_reference, map_edges, map_faces
from skodacad.section import axis_plane, cut
from skodacad.selectors import SelectionError, select_edges


def test_fallback_recovers_with_sufficient_precision_and_is_rechecked():
    edges = [Edge.make_line((x, 0, -5), (x, 0, 5)) for x in (0.0001, 0.0003)]
    part = OrderedShapes(edges=edges)
    spec = edge_selector(part, [edges[1]])
    assert select_edges(part, spec, float) == [edges[1]]
    one = spec[0] if isinstance(spec, list) else spec
    assert one["near"] == [0.0003, 0, 0]


def test_final_fallback_refuses_an_unrepresentable_selection():
    first = Edge.make_line((0, 0, 0), (0, 0, 5))
    second = copy.deepcopy(first)
    assert not first.is_same(second)
    with pytest.raises(SelectionError, match="nelze jednoznačně popsat"):
        edge_selector(OrderedShapes(edges=[first, second]), [first])


def test_curved_face_reference_must_resolve_to_the_actual_clicked_shape():
    part = Cylinder(10, 20)
    face = next(f for f in part.faces() if f.geom_type.name == "CYLINDER")
    reference = face_reference(part, face, (10, 0, 0))
    assert reference.plane["at"] == [10, 0, 0]
    with pytest.raises(SelectionError, match="nepatří k aktuálnímu dílu"):
        face_reference(part, copy.deepcopy(face), (10, 0, 0))


def test_named_plane_reference_also_refuses_a_foreign_clicked_face():
    part = Box(20, 20, 10)
    face = next(f for f in part.faces() if f.normal_at().Z > 0.99)
    assert face_reference(part, face).plane == "top"
    with pytest.raises(SelectionError, match="nepatří k aktuálnímu dílu"):
        face_reference(part, copy.deepcopy(face))


def test_line_mapping_checks_both_endpoints_and_all_candidates():
    source = Edge.make_line((0, 0, 0), (10, 0, 0))
    longer = Edge.make_line((-5, 0, 0), (15, 0, 0))
    short = Edge.make_line((4, 0, 0), (6, 0, 0))
    assert map_edges([source], OrderedShapes(edges=[longer])) == [longer]
    with pytest.raises(SelectionError, match="neexistuje"):
        map_edges([source], OrderedShapes(edges=[short]))
    for reverse in (False, True):
        with pytest.raises(SelectionError, match="více protějšků"):
            view = OrderedShapes(edges=[longer, copy.deepcopy(longer)], reverse=reverse)
            map_edges([source], view)
    # Skutečná totožnost má přednost před pouze geometrickým protějškem.
    assert map_edges([source], OrderedShapes(edges=[longer, source, source])) == [source]


@pytest.mark.parametrize(("source_angles", "target_angles", "accepted"), [
    ((350, 370), (340, 380), True), ((350, 370), (0, 180), False),
    ((0, 270), (0, 180), False), ((20, 70), (0, 90), True),
    ((0, 360), (0, 270), False), ((20, 70), (0, 360), True),
    ((270, 360), (180, 360), True), ((0, 359), (0, 270), False),
])
def test_entire_circular_arc_interval_is_contained(source_angles, target_angles, accepted):
    source = Edge.make_circle(5, Plane.XY, *source_angles)
    target = Edge.make_circle(5, Plane.XY, *target_angles)
    assert source.length == pytest.approx(5 * math.radians(source_angles[1] - source_angles[0]))
    if accepted:
        assert map_edges([source], OrderedShapes(edges=[target])) == [target]
    else:
        with pytest.raises(SelectionError, match="neexistuje"):
            map_edges([source], OrderedShapes(edges=[target]))


@pytest.mark.parametrize("target", [
    Edge.make_circle(5, Plane(origin=(10, 0, 0))),
    Edge.make_circle(5, Plane.XZ), Edge.make_circle(6),
])
def test_equal_radius_or_a_common_point_is_not_the_same_circle(target):
    source = Edge.make_circle(5, Plane.XY, -45, 45)
    with pytest.raises(SelectionError, match="neexistuje"):
        map_edges([source], OrderedShapes(edges=[target]))


def test_general_curve_requires_native_identity_for_cross_state_mapping():
    source = Edge.make_spline([(0, 0, 0), (1, 1, 0), (2, 0, 0)])
    assert map_edges([source], OrderedShapes(edges=[source])) == [source]
    with pytest.raises(SelectionError, match="obecná křivka nemá prokázaný protějšek"):
        map_edges([source], OrderedShapes(edges=[copy.deepcopy(source)]))


def test_arc_mapping_is_independent_of_the_carriers_axis_orientation():
    plane = Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, -1))
    source = Edge.make_circle(5, plane, 0, 90)
    target = Edge.make_circle(5, Plane.XY, 260, 360)
    assert source.position_at(0.5).Y < 0
    assert map_edges([source], OrderedShapes(edges=[target])) == [target]


def fingerprint(part):
    return (part.volume, part.area, tuple(part.bounding_box().min), tuple(part.bounding_box().max),
            [(face.area, face.wrapped.Orientation(), tuple(face.bounding_box().size))
             for face in part.faces()])


@pytest.mark.parametrize("kind", ["box", "cylinder", "sphere", "cone", "torus"])
def test_real_section_fragments_map_without_mutating_original_geometry(kind):
    part = {"box": lambda: Box(40, 30, 10), "cylinder": lambda: Cylinder(10, 20),
            "sphere": lambda: Sphere(10), "cone": lambda: Cone(10, 5, 20),
            "torus": lambda: Torus(10, 3)}[kind]()
    section = cut(part, axis_plane("Y", 0)).part
    before, clipped = fingerprint(part), fingerprint(section)
    accepted = refused = 0
    for face in section.faces():
        # Umělá řezná plocha leží v rovině Y=0, původní plochy ji nemají.
        cap = (face.geom_type.name == "PLANE" and abs(face.normal_at().Y) > 0.99
               and abs(face.center().Y) < 1e-6)
        if cap:
            with pytest.raises(SelectionError, match="nemá žádný doložený"):
                map_faces([face], part)
            refused += 1
        else:
            [found] = map_faces([face], part)
            assert any(found.is_same(own) for own in part.faces())
            accepted += 1
    assert accepted and refused
    assert fingerprint(part) == before and fingerprint(section) == clipped
    assert part.is_valid and section.is_valid


def test_one_interior_point_cannot_map_a_fragment_spanning_two_original_faces():
    whole = Rectangle(20, 10).faces()[0]
    left = (Pos(-5, 0, 0) * Rectangle(10, 10)).faces()[0]
    right = (Pos(5, 0, 0) * Rectangle(10, 10)).faces()[0]
    for reverse in (False, True):
        with pytest.raises(SelectionError, match="nemá žádný doložený"):
            map_faces([whole], OrderedShapes(faces=[left, right], reverse=reverse))


def test_distinct_containing_faces_are_ambiguous_and_opposite_orientation_is_refused():
    small = Rectangle(5, 5).faces()[0]
    whole = Rectangle(20, 20).faces()[0]
    with pytest.raises(SelectionError, match="není jednoznačná"):
        map_faces([small], OrderedShapes(faces=[whole, copy.deepcopy(whole)]))
    opposite = Face(downcast(whole.wrapped.Reversed()))
    with pytest.raises(SelectionError, match="nemá žádný doložený"):
        map_faces([small], OrderedShapes(faces=[opposite]))
    assert map_faces([small], OrderedShapes(faces=[whole, small, small])) == [small]
