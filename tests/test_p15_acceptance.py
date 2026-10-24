"""P1.5: missing spatial oracles and exact boundary diagnostics; no GUI dependency."""

import math

import pytest
from build123d import GeomType

from conftest import box_features, make_doc
from skodacad import rebuild
from skodacad.geometry_validation import inspect_volume
from skodacad.section import axis_plane, cut


def test_vertical_fillet_keeps_material_and_radius_at_all_four_corners():
    result = rebuild(make_doc(box_features() + [
        {"id": "round", "type": "fillet", "edges": {"parallel": "Z"}, "radius": 3},
    ]))
    assert result.ok, result.first_error
    part = result.part
    original = result.parts_before["round"]
    before = inspect_volume(original)
    facts = inspect_volume(part)
    assert facts.solids == 1
    assert facts.volume == pytest.approx(24000 - (4 - math.pi) * 9 * 40, rel=1e-9)
    assert facts.bounds == pytest.approx((-10, -15, 0, 10, 15, 40), rel=0, abs=1e-6)
    curved = [face for face in part.faces() if face.geom_type == GeomType.CYLINDER]
    assert len(curved) == 4
    assert all(face.radius == pytest.approx(3, rel=0, abs=1e-6) for face in curved)
    for z in (5, 20, 35):
        for sx in (-1, 1):
            for sy in (-1, 1):
                assert part.is_inside((sx * 8, sy * 13, z))
                assert part.is_inside((sx * 9.5, sy * 12, z))
                assert not part.is_inside((sx * 9.9, sy * 14.9, z))
                assert original.is_inside((sx * 9.9, sy * 14.9, z))
    assert inspect_volume(original) == before


@pytest.mark.parametrize("shape", ["rectangle", "circle"])
def test_loft_has_analytic_sections_and_material_on_the_correct_side(shape):
    def sketch(key, size, offset):
        element = ({"shape": shape, "width": size, "height": size} if shape == "rectangle"
                   else {"shape": shape, "diameter": size})
        return {"id": key, "type": "sketch", "plane": "XY", "offset": offset,
                "elements": [element]}

    result = rebuild(make_doc([sketch("a", 40, 0), sketch("b", 20, 30),
                               {"id": "l", "type": "loft", "sketches": ["a", "b"],
                                "ruled": shape == "rectangle"}]))
    assert result.ok, result.first_error
    part = result.part
    before = inspect_volume(part)
    expected_volume = 28000 if shape == "rectangle" else 7000 * math.pi
    assert before.solids == 1 and before.volume == pytest.approx(expected_volume, rel=1e-9)
    assert before.bounds == pytest.approx((-20, -20, 0, 20, 20, 30), rel=0, abs=1e-6)
    for z in (5, 15, 25):
        half_width = 20 - z / 3
        expected_area = (4 if shape == "rectangle" else math.pi) * half_width**2
        section = cut(part, axis_plane("Z", z))
        assert len(section.faces) == 1
        assert section.area == pytest.approx(expected_area, rel=1e-9)
        bounds = section.faces[0].bounding_box()
        assert (*bounds.min, *bounds.max) == pytest.approx(
            (-half_width, -half_width, z, half_width, half_width, z), rel=0, abs=1e-6)
        for x, y in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            assert part.is_inside((x * (half_width - 0.1), y * (half_width - 0.1), z))
            assert not part.is_inside((x * (half_width + 0.1), y * (half_width + 0.1), z))
        if shape == "rectangle":
            assert part.is_inside((half_width - 0.1, half_width - 0.1, z))
        else:
            assert not part.is_inside((0.8 * half_width, 0.8 * half_width, z))
    assert inspect_volume(part) == before


@pytest.mark.parametrize(("feature", "reason"), [
    ({"id": "bad", "type": "chamfer", "edges": {"parallel": "Z"}, "distance": 50},
     "Sražení"),
    ({"id": "bad", "type": "shell", "thickness": 2, "open_faces": [
        {"at": [0, 0, 10], "type": "cylinder", "radius": 99}]}, "ploch"),
])
def test_impossible_chamfer_and_missing_shell_face_leave_the_whole_box(feature, reason):
    document = make_doc(box_features() + [feature, {"id": "tail", "type": "sketch",
                                                  "elements": [{"shape": "circle",
                                                                "diameter": 2}]}])
    recipe = document.to_dict()
    result = rebuild(document)
    assert not result.ok and result.first_error.id == "bad"
    assert reason in result.first_error.message
    assert result.statuses[-1].status == "skipped"
    facts = inspect_volume(result.part)
    assert facts.solids == 1 and facts.volume == pytest.approx(24000, rel=1e-9)
    assert facts.bounds == pytest.approx((-10, -15, 0, 10, 15, 40), rel=0, abs=1e-6)
    assert result.part.is_inside((9.9, 14.9, 20))
    assert result.part.is_inside((0, 0, 20))
    assert facts == inspect_volume(result.parts_before["bad"])
    assert document.to_dict() == recipe


@pytest.mark.parametrize(("gap", "counts"), [(1e-5, (2,)), (1e-8, (1, 2))])
def test_microgap_result_reports_the_actual_body_count_without_claiming_connection(gap, counts):
    document = make_doc(box_features() + [
        {"id": "island", "type": "sketch", "plane": "XY", "elements": [
            {"shape": "rectangle", "width": 5, "height": 5,
             "center": [12.5 + gap, -12.5]}]},
        {"id": "add", "type": "extrude", "sketch": "island", "distance": 10,
         "operation": "add"},
    ])
    original = document.to_dict()
    result = rebuild(document)
    assert result.ok, result.first_error
    facts = inspect_volume(result.part)
    assert facts.solids in counts and facts.volume == pytest.approx(24250, rel=1e-9)
    assert facts.bounds == pytest.approx((-10, -15, 0, 15 + gap, 15, 40), rel=0, abs=1e-6)
    assert result.part.is_inside((0, 0, 20))
    assert result.part.is_inside((12.5 + gap, -12.5, 5))
    assert result.statuses[-1].message == f"Počet těles: 1 → {facts.solids}."
    assert document.to_dict() == original
