"""Native enumeration, moved carriers and explicit residual identity limits (S20)."""

import copy
import math

import pytest
from build123d import Box, Compound, Cone, Cylinder, Edge, Pos, Rot, Sphere, Torus

from reference_cases import OrderedShapes
from skodacad.features import sketch_plane
from skodacad.picking import face_reference, map_edges, map_faces
from skodacad.section import axis_plane, cut
from skodacad.selectors import SelectionError, find_face, select_edges, select_faces


def test_native_enumeration_deduplicates_occurrences_but_keeps_distinct_coincident_shapes():
    box = Box(20, 30, 40)
    repeated = Compound([box, box])
    assert len(select_edges(repeated, "all", float)) == 12
    assert len(select_faces(repeated, "top")) == 1
    assert find_face(repeated, {"at": [0, 0, 20], "type": "plane",
                                "normal": [0, 0, 1]})[0].area == pytest.approx(600)
    distinct = Compound([box, copy.deepcopy(box)])
    assert len(select_edges(distinct, "all", float)) == 24
    assert len(select_faces(distinct, "top")) == 2
    with pytest.raises(SelectionError, match="není jednoznačný"):
        select_edges(distinct, {"near": [10, -15, 0]}, float)
    with pytest.raises(SelectionError, match="není jednoznačná"):
        find_face(distinct, {"at": [0, 0, 20], "type": "plane", "normal": [0, 0, 1]})


@pytest.mark.parametrize("factory", [lambda: Cylinder(10, 20), lambda: Cone(10, 5, 20),
                                   lambda: Sphere(10), lambda: Torus(10, 3)])
def test_moved_rotated_section_maps_global_carriers_without_mutating_inputs(factory):
    part = Pos(50, 25, -10) * Rot(15, 25, 35) * factory()
    before = (part.volume, part.area, tuple(part.bounding_box().min))
    section = cut(part, axis_plane("Y", 25))
    assert section.part.is_valid and section.faces
    accepted = 0
    for face in section.part.faces():
        if any(face.is_same(cap) for cap in section.faces):
            with pytest.raises(SelectionError, match="nemá žádný doložený"):
                map_faces([face], part)
        else:
            [original] = map_faces([face], part)
            assert original.geom_type == face.geom_type
            assert any(original.is_same(own) for own in part.faces())
            accepted += 1
    assert accepted and (part.volume, part.area, tuple(part.bounding_box().min)) == before


def test_almost_parallel_circle_carriers_are_not_the_same_plane():
    source = Rot(0.05, 0, 0) * Edge.make_circle(5)
    target = Edge.make_circle(5)
    assert abs(source.normal().dot(target.normal())) > 1 - 1e-6
    assert target.distance_to(source.position_at(0.25)) > 0.004
    with pytest.raises(SelectionError, match="neexistuje"):
        map_edges([source], OrderedShapes(edges=[target]))


def test_carrier_position_and_radius_errors_cannot_each_consume_the_full_distance_band():
    source = Pos(0.000009, 0, 0) * Edge.make_circle(5.000009)
    target = Edge.make_circle(5)
    assert target.distance_to(source.start_point()) > 1e-5
    with pytest.raises(SelectionError, match="neexistuje"):
        map_edges([source], OrderedShapes(edges=[target]))


def test_deleted_hole_can_still_resolve_to_a_different_unique_geometric_match():
    plate = Pos(0, 0, 5) * Box(60, 30, 10)
    left = Pos(-10, 0, 5) * Cylinder(3, 10)
    right = Pos(10, 0, 5) * Cylinder(3, 10)
    before, after = plate - left - right, plate - right
    spec = {"at": [-7, 0, 5], "normal": [-1, 0, 0], "type": "cylinder", "radius": 3}
    first, point_before = find_face(before, spec)
    replacement, point_after = find_face(after, spec)
    assert first.geom_type == replacement.geom_type
    assert tuple(point_before) == pytest.approx((-7, 0, 5))
    assert tuple(point_after) == pytest.approx((7, 0, 5))
    assert not before.is_inside((-10, 0, 5)) and after.is_inside((-10, 0, 5))
    assert before.volume == pytest.approx(18000 - 180 * math.pi)
    assert after.volume == pytest.approx(18000 - 90 * math.pi)
    assert before.is_valid and after.is_valid
    # Charakterizace přiznaného R04: unikátní geometrický dotaz nedokazuje původ díry.


def test_geometric_replacement_has_no_persisted_topological_identity():
    before, replacement = Box(20, 30, 40), Box(20, 30, 40)
    spec = {"at": [0, 0, 20], "normal": [0, 0, 1], "type": "plane"}
    old_face, _ = find_face(before, spec)
    new_face, point = find_face(replacement, spec)
    assert not old_face.is_same(new_face)
    assert tuple(point) == pytest.approx((0, 0, 20))
    assert before.volume == replacement.volume == pytest.approx(24000)
    assert before.is_valid and replacement.is_valid


def test_top_offset_survives_deleted_pocket_without_proving_a_physical_floor():
    plate = Pos(0, 0, 5) * Box(40, 30, 10)
    pocket = Pos(0, 0, 8.5) * Cylinder(5, 3)
    before = plate - pocket
    floor, _ = find_face(before, {"at": [0, 0, 7], "normal": [0, 0, 1], "type": "plane"})
    reference = face_reference(before, floor, (0, 0, 7))
    assert reference.plane == "top" and reference.offset == -3
    spec = {"plane": reference.plane, "offset": reference.offset}
    assert sketch_plane(before, spec, {}).origin.Z == pytest.approx(7)
    assert sketch_plane(plate, spec, {}).origin.Z == pytest.approx(7)
    assert not before.is_inside((0, 0, 8)) and plate.is_inside((0, 0, 8))
    assert before.volume == pytest.approx(12000 - 75 * math.pi)
    assert plate.volume == pytest.approx(12000)
    assert before.is_valid and plate.is_valid
