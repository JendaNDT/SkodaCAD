"""Výběr kliknutím: kliknutá hrana/plocha → popis významem, který platí i po změně rozměrů."""

import math

import pytest
from build123d import Vector

from conftest import box_features, edge_at, face_at, make_doc
from skodacad import Document, rebuild
from skodacad.picking import (
    edge_selector,
    face_reference,
    map_edges,
    open_face_name,
    split_shapes,
)
from skodacad.selectors import SelectionError, describe_edges, select_edges, select_faces


def build(document):
    result = rebuild(document)
    assert result.ok, result.first_error
    return result.part


def box(width=20, depth=30, height=40):
    return build(make_doc(box_features(width, depth, height)))


def same_set(found, expected):
    return len(found) == len(expected) and all(edge in expected for edge in found)


def test_single_vertical_edge_is_described_by_its_two_faces():
    part = box()
    edge = edge_at(part, 10, -15, 20)  # svislá hrana vpravo vpředu
    spec = edge_selector(part, [edge])
    assert spec == {"between": ["front", "right"]}
    assert describe_edges(spec) == "hrana mezi přední a pravou plochou"


def test_whole_groups_get_the_simplest_description():
    part = box()
    top = select_faces(part, "top")[0].edges()
    assert edge_selector(part, list(top)) == {"face": "top"}
    vertical = [edge for edge in part.edges() if edge.tangent_at(0).Z ** 2 > 0.99]
    assert edge_selector(part, vertical) == {"parallel": "Z"}
    assert edge_selector(part, list(part.edges())) == "all"
    # Horní hrany + svislé hrany = dva popisy dohromady.
    spec = edge_selector(part, [*top, *vertical])
    assert sorted(map(str, spec)) == sorted(map(str, [{"face": "top"}, {"parallel": "Z"}]))


@pytest.mark.parametrize("example", ["priruba", "krabicka", "hridel"])
def test_every_single_edge_of_examples_is_found_exactly(examples_dir, example):
    part = build(Document.load(examples_dir / f"{example}.json"))
    for edge in part.edges():
        spec = edge_selector(part, [edge])
        assert same_set(select_edges(part, spec, float), [edge]), spec


def test_one_of_four_equal_holes_is_told_apart_by_nearest_point(examples_dir):
    part = build(Document.load(examples_dir / "priruba.json"))
    holes = [edge for edge in part.edges() if edge.geom_type.name == "CIRCLE"
             and abs(edge.radius - 9) < 1e-6 and edge.position_at(0.5).Z > 17]
    assert len(holes) == 4
    spec = edge_selector(part, holes[:1])
    assert spec["face"] == "top" and spec["radius"] == 9 and "near" in spec
    assert edge_selector(part, holes) == {"face": "top", "radius": 9}


def test_picked_fillet_follows_parameter_change():
    """Zaoblení svislé hrany vpředu vpravo, pak změna šířky: pořád ta samá hrana (objem)."""
    radius = 3
    part = box()
    spec = edge_selector(part, [edge_at(part, 10, -15, 20)])
    for width in (20, 50):
        features = [*box_features("w", 30, 40),
                    {"id": "f", "type": "fillet", "edges": spec, "radius": radius}]
        filleted = build(make_doc(features, {"w": width}))
        corner_loss = (radius ** 2 - math.pi * radius ** 2 / 4) * 40
        assert filleted.volume == pytest.approx(width * 30 * 40 - corner_loss, rel=1e-6)
        assert filleted.is_valid
        # Zaoblený je právě roh vpravo vpředu, ostatní rohy zůstaly ostré.
        assert not filleted.is_inside(Vector(width / 2 - 0.2, -15 + 0.2, 20))
        assert filleted.is_inside(Vector(-width / 2 + 0.2, -15 + 0.2, 20))


def test_edges_of_other_part_are_refused():
    with pytest.raises(SelectionError, match="nepatří"):
        edge_selector(box(), [box(10, 10, 10).edges()[0]])
    with pytest.raises(SelectionError, match="Nejsou vybrané"):
        edge_selector(box(), [])


def stepped_part():
    """Deska 40 × 30 × 10 a na její levé polovině kvádr 20 × 30 × 10 (schod nahoře vpravo)."""
    return make_doc([
        *box_features(40, 30, 10),
        {"id": "s2", "type": "sketch", "plane": "top",
         "elements": [{"shape": "rectangle", "width": 20, "height": 30, "center": [-10, 0]}]},
        {"id": "e2", "type": "extrude", "sketch": "s2", "distance": 10},
    ])


def test_sketch_on_clicked_inner_face_makes_hole_there():
    document = stepped_part()
    part = build(document)
    step = face_at(part, 10, 0, 10)
    reference = face_reference(part, step, (12, 3, 10))
    assert (reference.plane, reference.offset, reference.point) == ("top", -10, (12, 3))

    document.features += [
        {"id": "s3", "type": "sketch", "plane": reference.plane, "offset": reference.offset,
         "elements": [{"shape": "circle", "diameter": 6, "center": list(reference.point)}]},
        {"id": "e3", "type": "extrude", "sketch": "s3", "operation": "cut", "distance": 4},
    ]
    holed = build(document)
    assert holed.volume == pytest.approx(40 * 30 * 10 + 20 * 30 * 10 - math.pi * 9 * 4)
    assert not holed.is_inside(Vector(12, 3, 8))  # díra je v místě kliknutí
    assert holed.is_inside(Vector(12, 3, 5))  # a jen 4 mm hluboko


@pytest.mark.parametrize(("point", "expected"), [
    ((-10, 0, 20), ("top", 0)),
    ((0, 0, 0), ("bottom", 0)),
    ((0, -15, 5), ("front", 0)),
    ((20, 0, 5), ("right", 0)),
    ((10, 0, 10), ("top", -10)),  # schod
    ((0, 0, 15), ("right", -20)),  # svislá stěna schodu míří doprava
])
def test_face_reference_for_each_direction(point, expected):
    part = build(stepped_part())
    reference = face_reference(part, face_at(part, *point))
    assert (reference.plane, reference.offset) == expected


def test_curved_face_cannot_hold_a_sketch(examples_dir):
    part = build(Document.load(examples_dir / "hridel.json"))
    cylinder = next(face for face in part.faces() if face.geom_type.name == "CYLINDER")
    with pytest.raises(SelectionError, match="zakřivená"):
        face_reference(part, cylinder)


def test_open_face_only_outer_faces():
    part = build(stepped_part())
    assert open_face_name(part, face_at(part, -10, 0, 20)) == "top"
    with pytest.raises(SelectionError, match="krajní horní"):
        open_face_name(part, face_at(part, 10, 0, 10))


def test_split_shapes_sorts_faces_and_edges():
    part = box()
    face = select_faces(part, "top")[0]
    edge = face.edges()[0]
    faces, edges = split_shapes([face.wrapped, edge.wrapped, edge.wrapped, part.vertices()[0]])
    assert faces == [face] and edges == [edge]


def test_map_edges_finds_trimmed_edge_in_earlier_part():
    before = box()
    spec = edge_selector(before, [edge_at(before, 10, -15, 20)])
    after = build(make_doc([*box_features(),
                            {"id": "f", "type": "fillet", "edges": spec, "radius": 3}]))
    trimmed = edge_at(after, 0, -15, 40)  # horní přední hrana, zaoblení ji zkrátilo
    assert trimmed.length == pytest.approx(17)
    mapped = map_edges([trimmed], before)
    assert len(mapped) == 1 and mapped[0].length == pytest.approx(20)
    with pytest.raises(SelectionError, match="neexistuje"):
        map_edges([edge_at(after, 10, -15, 20)], before)  # hrana zaoblení dřív nebyla


@pytest.mark.parametrize(("spec", "message"), [
    ({"between": ["front"]}, "dvě plochy"),
    ({"between": ["front", "nahore"]}, "Neznámá plocha"),
    ({"near": [1, 2]}, r"bod \[x, y, z\]"),
    ([], "prázdný"),
    ([[{"face": "top"}]], "další seznam"),
    ([{"face": "top"}, {"radius": 99}], "nenašel žádnou hranu"),
])
def test_bad_edge_selectors_explain_in_czech(spec, message):
    with pytest.raises(SelectionError, match=message):
        select_edges(box(), spec, float)


def test_list_of_selectors_is_union_without_duplicates():
    part = box()
    edges = select_edges(part, [{"face": "top"}, {"face": "front"}], float)
    assert len(edges) == 7  # 4 + 4, společná hrana jen jednou
