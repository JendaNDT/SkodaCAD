"""P6.13/P6.14 – žebro (docs/p6-13-zebro.md): objem podle vzorce, spojení s tělesem, odmítnutí
a zápis formátu 36.

Očekávané objemy jsou spočítané ze vzorců (plocha mezi trasou a tělesem × tloušťka), ne převzaté
z výsledku.
"""

from __future__ import annotations

import copy

import pytest
from build123d import Box, Plane, Pos

from skodacad import rib
from skodacad.document import VERSION, Document, DocumentError
from skodacad.features import REPEATABLE_FEATURES, VOLUME_FEATURES, tree_summary
from skodacad.rebuild import rebuild


def volume(part) -> float:
    return sum(solid.volume for solid in part.solids())


PLATE = Pos(0, 0, 2) * Box(60, 60, 4)  # z od 0 do 4


def plate_document(features: list[dict], params: dict | None = None) -> dict:
    return {
        "format": "skodacad", "version": VERSION, "name": "zebro",
        "parameters": params or {},
        "features": [
            {"id": "obrys", "type": "sketch", "plane": "XY",
             "elements": [{"shape": "rectangle", "width": 60, "height": 60}]},
            {"id": "deska", "type": "extrude", "sketch": "obrys", "distance": 4},
            *features,
        ],
    }


def rib_feature(**changes) -> dict:
    feature = {"id": "zebro", "type": "rib", "plane": "XZ", "points": [[-20, 14], [20, 14]],
               "thickness": 3, "side": "right"}
    feature.update(changes)
    return feature


# --- geometrie ---------------------------------------------------------------------------


def test_rib_on_plate_adds_prism_between_route_and_plate_and_stays_one_solid():
    result = rib.build(Plane.XZ, PLATE, [(-20, 14), (20, 14)], 3, "right")
    # 40 mm dlouhé, od z = 4 do z = 14 (10 mm), tloušťka 3
    assert volume(result) == pytest.approx(40 * 10 * 3, abs=1e-6)
    joined = PLATE + result
    assert len(joined.solids()) == 1
    assert joined.is_valid
    assert volume(joined) == pytest.approx(60 * 60 * 4 + 1200, abs=1e-6)


def test_rib_is_symmetric_around_sketch_plane():
    result = rib.build(Plane.XZ, PLATE, [(-20, 14), (20, 14)], 3, "right")
    box = result.bounding_box()
    assert (box.min.Y, box.max.Y) == pytest.approx((-1.5, 1.5), abs=1e-6)
    assert (box.min.Z, box.max.Z) == pytest.approx((4, 14), abs=1e-6)


def test_rib_offset_plane_moves_rib():
    result = rib.build(Plane.XZ.offset(10), PLATE, [(-20, 14), (20, 14)], 3, "right")
    # rovina XZ má normálu −Y, posun 10 jde do −Y
    assert result.bounding_box().center().Y == pytest.approx(-10, abs=1e-6)


def test_polyline_route_volume_is_area_under_route_times_thickness():
    route = [(-20, 10), (-5, 14), (5, 14), (20, 10)]
    result = rib.build(Plane.XZ, PLATE, route, 3, "right")
    # (10 + 14)/2 − 4 = 8 mm střední výška na 15 mm, 10 mm na 10 mm a znovu 15 mm
    area = (12 - 4) * 15 + (14 - 4) * 10 + (12 - 4) * 15
    assert volume(result) == pytest.approx(area * 3, abs=1e-6)


def l_bracket():
    floor = Pos(0, 0, 2) * Box(60, 40, 4)  # x −30…30, z 0…4
    upright = Pos(-28, 0, 15) * Box(4, 40, 30)  # x −30…−26, z 0…30
    return floor + upright


def test_gusset_between_wall_and_floor_is_the_triangle_in_the_corner():
    # úhlopříčka od stěny (x = −26, z = 20) k podlaze (x = −6, z = 4): trojúhelník 20 × 16
    result = rib.build(Plane.XZ, l_bracket(), [(-26, 20), (-6, 4)], 3, "right")
    assert volume(result) == pytest.approx(0.5 * 20 * 16 * 3, abs=1e-6)
    joined = l_bracket() + result
    assert len(joined.solids()) == 1 and joined.is_valid


def test_rib_across_cavity_ends_on_floor_and_walls():
    # krabička 60 × 40 × 20, stěny 2 mm, dno 2 mm, nahoře otevřená
    box = Pos(0, 0, 10) * Box(60, 40, 20) - Pos(0, 0, 12) * Box(56, 36, 20)
    # trasa zasahuje do stěn, žebro tak končí na stěnách i na dně
    result = rib.build(Plane.XZ, box, [(-29, 12), (29, 12)], 3, "right")
    assert volume(result) == pytest.approx(56 * 10 * 3, abs=1e-6)
    joined = box + result
    assert len(joined.solids()) == 1 and joined.is_valid


def test_pieces_behind_the_body_are_dropped():
    # trasa přes celou desku: kusy pod deskou (za materiálem) žebro nepřidá
    result = rib.build(Plane.XZ, PLATE, [(-29, 14), (29, 14)], 3, "right")
    assert result.bounding_box().min.Z == pytest.approx(4, abs=1e-6)
    assert volume(result) == pytest.approx(58 * 10 * 3, abs=1e-6)


# --- odmítnutí ---------------------------------------------------------------------------


def test_rib_toward_empty_space_is_rejected():
    with pytest.raises(rib.RibError, match="přečnívá|nic nepřidalo"):
        rib.build(Plane.XZ, PLATE, [(-20, 14), (20, 14)], 3, "left")


def test_rib_longer_than_the_plate_is_rejected_not_hanging_over_the_edge():
    with pytest.raises(rib.RibError, match="přečnívá"):
        rib.build(Plane.XZ, PLATE, [(-20, 14), (40, 14)], 3, "right")


def test_route_lying_inside_material_is_rejected():
    with pytest.raises(rib.RibError, match="nic nepřidalo"):
        rib.build(Plane.XZ, PLATE, [(-20, 2), (20, 2)], 3, "right")


@pytest.mark.parametrize("points,message", [
    ([(0, 5), (0, 5)], "stejném místě"),
    ([(-20, 14), (0, 14), (-10, 14), (20, 14)], "vrací"),
    ([(-20, 14)], "aspoň dvou"),
])
def test_bad_routes_are_rejected(points, message):
    with pytest.raises(rib.RibError, match=message):
        rib.build(Plane.XZ, PLATE, points, 3, "right")


@pytest.mark.parametrize("thickness", [0, -1, float("nan")])
def test_bad_thickness_is_rejected(thickness):
    with pytest.raises(rib.RibError, match="Tloušťka"):
        rib.build(Plane.XZ, PLATE, [(-20, 14), (20, 14)], thickness, "right")


def test_validate_rejects_unknown_key_side_and_point_count():
    base = rib_feature()
    rib.validate(base)
    with pytest.raises(rib.RibError, match="neznámý klíč"):
        rib.validate({**base, "taper": 1})
    with pytest.raises(rib.RibError, match="Strana"):
        rib.validate({**base, "side": "up"})
    with pytest.raises(rib.RibError, match="trasu"):
        rib.validate({**base, "points": [[0, 0]]})
    with pytest.raises(rib.RibError, match="dvojice"):
        rib.validate({**base, "points": [[0, 0], [1, 2, 3]]})


# --- prvek v modelu ----------------------------------------------------------------------


def build(features, params=None):
    return rebuild(Document.from_dict(plate_document(features, params)))


def status_of(result, feature_id):
    return next(item for item in result.statuses if item.id == feature_id)


def test_feature_in_model_adds_material_and_is_registered():
    result = build([rib_feature()])
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    assert volume(result.part) == pytest.approx(60 * 60 * 4 + 1200, abs=1e-6)
    assert "rib" in VOLUME_FEATURES and "rib" in REPEATABLE_FEATURES


def test_thickness_and_points_accept_parameters():
    result = build([rib_feature(thickness="t", points=[["-L", 14], ["L", 14]])],
                   {"t": 2, "L": 10})
    assert volume(result.part) == pytest.approx(60 * 60 * 4 + 20 * 10 * 2, abs=1e-6)


def test_rib_without_part_or_toward_nothing_is_an_error_not_a_crash():
    result = build([rib_feature(side="left")])
    status = status_of(result, "zebro")
    assert status.status == "error"
    assert "Žebro" in status.message
    assert "přečnívá" in status.message or "nic nepřidalo" in status.message
    assert volume(result.part) == pytest.approx(60 * 60 * 4)  # díl zůstal beze změny


def test_linear_pattern_repeats_the_rib():
    features = [rib_feature(), {"id": "pole", "type": "pattern", "features": ["zebro"],
                                "kind": "linear", "direction": "Y", "spacing": 10, "count": 3}]
    result = build(features)
    assert status_of(result, "pole").status == "ok", status_of(result, "pole")
    assert volume(result.part) == pytest.approx(60 * 60 * 4 + 3 * 1200, abs=1e-6)
    assert len(result.part.solids()) == 1


def test_tree_summary_shows_thickness():
    assert tree_summary(rib_feature(), {}) == "3 mm"


# --- formát ------------------------------------------------------------------------------


def test_format_36_only_with_rib():
    with_rib = Document.from_dict(plate_document([rib_feature()]))
    assert with_rib.to_dict()["version"] == 36
    without = Document.from_dict(plate_document([]))
    assert without.to_dict()["version"] < 36
    assert VERSION >= 36


def test_rib_in_older_format_is_rejected():
    data = plate_document([rib_feature()])
    data["version"] = 35
    with pytest.raises(DocumentError, match="verze 36"):
        Document.from_dict(data)


def test_invalid_rib_record_is_rejected_when_loading():
    data = plate_document([rib_feature(side="up")])
    with pytest.raises(DocumentError, match="Strana"):
        Document.from_dict(data)


def test_round_trip_keeps_rib_unchanged():
    data = plate_document([rib_feature()])
    document = Document.from_dict(copy.deepcopy(data))
    again = Document.from_dict(document.to_dict())
    assert again.features == document.features


def test_example_box_with_three_ribs_matches_formula():
    document = Document.load("examples/zebro_krabicka.json")
    result = rebuild(document)
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    # blok 80 × 50 × 25 minus dutina 75 × 45 × 22,5 plus tři žebra 75 × 9,5 × 2
    expected = 80 * 50 * 25 - 75 * 45 * 22.5 + 3 * 75 * 9.5 * 2
    assert volume(result.part) == pytest.approx(expected, abs=1e-6)
    assert len(result.part.solids()) == 1 and result.part.is_valid
    assert document.to_dict()["version"] == 36


def test_example_changes_with_parameters():
    document = Document.load("examples/zebro_krabicka.json")
    result = rebuild(document, {"T": 3, "Z": 10})
    expected = 80 * 50 * 25 - 75 * 45 * 22.5 + 3 * 75 * 7.5 * 3
    assert volume(result.part) == pytest.approx(expected, abs=1e-6)
