"""P6.15 – sloupek (docs/p6-15-sloupek.md): objem podle vzorce, spojení s tělesem, otvor jen
do sloupku, odmítnutí a zápis formátu 36.

Očekávané objemy jsou spočítané ze vzorců (válec a otvor), ne převzaté z výsledku.
"""

from __future__ import annotations

import math

import pytest
from build123d import Box, Plane, Pos

from skodacad import boss
from skodacad.document import VERSION, Document, DocumentError
from skodacad.features import REPEATABLE_FEATURES, VOLUME_FEATURES, tree_summary
from skodacad.rebuild import rebuild


def volume(part) -> float:
    return sum(solid.volume for solid in part.solids())


PLATE = Pos(0, 0, 1) * Box(60, 60, 2)  # z od 0 do 2
START = Plane.XY.offset(10)  # sloupek vede od z = 10 dolů k desce (délka 8)


def post(diameter=8, length=8):
    return math.pi * (diameter / 2) ** 2 * length


# --- geometrie ---------------------------------------------------------------------------


def test_full_post_is_cylinder_from_start_plane_to_the_plate():
    result = boss.build(START, PLATE, [(0, 0)], 8, None, None, "reverse")
    assert volume(result) == pytest.approx(post(), abs=1e-6)
    box = result.bounding_box()
    assert (box.min.Z, box.max.Z) == pytest.approx((2, 10), abs=1e-6)
    joined = PLATE + result
    assert len(joined.solids()) == 1 and joined.is_valid
    assert volume(joined) == pytest.approx(60 * 60 * 2 + post(), abs=1e-6)


def test_hole_goes_through_the_post_only_and_leaves_the_plate_intact():
    result = boss.build(START, PLATE, [(0, 0)], 8, 3.2, None, "reverse")
    assert volume(result) == pytest.approx(post() - post(3.2), abs=1e-6)
    joined = PLATE + result
    assert volume(joined) == pytest.approx(60 * 60 * 2 + post() - post(3.2), abs=1e-6)
    # deska pod otvorem zůstala celá: bod uprostřed otvoru v z = 1 je v materiálu
    assert joined.is_inside((0, 0, 1))
    assert not joined.is_inside((0, 0, 5))  # v otvoru sloupku je vzduch


def test_blind_hole_depth_limits_the_hole():
    result = boss.build(START, PLATE, [(0, 0)], 8, 3.2, 5, "reverse")
    assert volume(result) == pytest.approx(post() - post(3.2, 5), abs=1e-6)


def test_several_positions_make_several_posts_in_one_solid_each():
    result = boss.build(START, PLATE, [(-20, -20), (20, -20), (0, 20)], 8, 3, None, "reverse")
    assert volume(result) == pytest.approx(3 * (post() - post(3)), abs=1e-6)
    assert len(result.solids()) == 3
    assert len((PLATE + result).solids()) == 1


def test_post_going_up_from_the_underside_uses_normal_direction():
    start = Plane.XY.offset(-6)  # od z = −6 nahoru k desce (délka 6 do z = 0)
    result = boss.build(start, PLATE, [(0, 0)], 6, None, None, "normal")
    assert volume(result) == pytest.approx(post(6, 6), abs=1e-6)


def test_post_partly_embedded_in_a_wall_keeps_only_the_free_part():
    # stěna 4 mm vysoká 12 mm podél x = −30…−26; sloupek Ø8 s osou ve stěně (x = −26)
    wall = Pos(-28, 0, 6) * Box(4, 60, 12)
    body = PLATE + wall
    result = boss.build(START, body, [(-26, 0)], 8, None, None, "reverse")
    assert len((body + result).solids()) == 1
    assert volume(result) < post(8, 10 - 2) + 1e-9  # část válce leží ve stěně
    assert result.bounding_box().min.Z == pytest.approx(2, abs=1e-6)


# --- odmítnutí ---------------------------------------------------------------------------


def test_post_toward_empty_space_is_rejected():
    with pytest.raises(boss.BossError, match="přečnívá"):
        boss.build(START, PLATE, [(0, 0)], 8, None, None, "normal")


def test_post_hanging_over_the_plate_edge_is_rejected():
    with pytest.raises(boss.BossError, match="přečnívá"):
        boss.build(START, PLATE, [(28, 0)], 8, None, None, "reverse")


def test_start_inside_material_is_rejected():
    with pytest.raises(boss.BossError, match="nic nepřidal"):
        boss.build(Plane.XY.offset(1), PLATE, [(0, 0)], 8, None, None, "reverse")


@pytest.mark.parametrize("diameter,hole,depth,message", [
    (0, None, None, "Průměr sloupku"),
    (8, 8, None, "moc velký"),
    (8, 7.7, None, "moc velký"),
    (8, 0, None, "Průměr otvoru"),
    (8, 3, 0, "Hloubka otvoru"),
])
def test_bad_dimensions_are_rejected(diameter, hole, depth, message):
    with pytest.raises(boss.BossError, match=message):
        boss.build(START, PLATE, [(0, 0)], diameter, hole, depth, "reverse")


def test_validate_rejects_unknown_key_direction_and_positions():
    base = {"id": "s", "type": "boss", "plane": "XY", "positions": [[0, 0]], "diameter": 8}
    boss.validate(base)
    with pytest.raises(boss.BossError, match="neznámý klíč"):
        boss.validate({**base, "taper": 1})
    with pytest.raises(boss.BossError, match="Směr"):
        boss.validate({**base, "direction": "up"})
    with pytest.raises(boss.BossError, match="poloh"):
        boss.validate({**base, "positions": []})
    with pytest.raises(boss.BossError, match="dvojice"):
        boss.validate({**base, "positions": [[0, 0, 1]]})
    with pytest.raises(boss.BossError, match="průměr"):
        boss.validate({k: v for k, v in base.items() if k != "diameter"})


# --- prvek v modelu ----------------------------------------------------------------------


def plate_document(features, params=None):
    return {
        "format": "skodacad", "version": VERSION, "name": "sloupek",
        "parameters": params or {},
        "features": [
            {"id": "obrys", "type": "sketch", "plane": "XY",
             "elements": [{"shape": "rectangle", "width": 60, "height": 60}]},
            {"id": "deska", "type": "extrude", "sketch": "obrys", "distance": 2},
            *features,
        ],
    }


def boss_feature(**changes):
    feature = {"id": "sloupek", "type": "boss", "plane": "XY", "offset": 10,
               "positions": [[-15, -15], [15, 15]], "diameter": 8, "hole_diameter": 3.2,
               "direction": "reverse"}
    feature.update(changes)
    return feature


def build(features, params=None):
    return rebuild(Document.from_dict(plate_document(features, params)))


def status_of(result, feature_id):
    return next(item for item in result.statuses if item.id == feature_id)


def test_feature_in_model_adds_two_posts_and_is_registered():
    result = build([boss_feature()])
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    assert volume(result.part) == pytest.approx(60 * 60 * 2 + 2 * (post() - post(3.2)),
                                                abs=1e-6)
    assert len(result.part.solids()) == 1
    assert "boss" in VOLUME_FEATURES and "boss" in REPEATABLE_FEATURES


def test_parameters_drive_height_and_diameter():
    result = build([boss_feature(offset="H", diameter="D", hole_diameter=None,
                                 positions=[[0, 0]])], {"H": 12, "D": 6})
    assert volume(result.part) == pytest.approx(60 * 60 * 2 + post(6, 10), abs=1e-6)


def test_wrong_direction_is_an_error_not_a_crash():
    result = build([boss_feature(direction="normal")])
    status = status_of(result, "sloupek")
    assert status.status == "error" and "Sloupek" in status.message
    assert volume(result.part) == pytest.approx(60 * 60 * 2)  # díl beze změny


def test_linear_pattern_repeats_the_post():
    features = [boss_feature(positions=[[-20, -20]], hole_diameter=None),
                {"id": "pole", "type": "pattern", "features": ["sloupek"], "kind": "linear",
                 "direction": "X", "spacing": 20, "count": 3}]
    result = build(features)
    assert status_of(result, "pole").status == "ok", status_of(result, "pole")
    assert volume(result.part) == pytest.approx(60 * 60 * 2 + 3 * post(), abs=1e-6)
    assert len(result.part.solids()) == 1


def test_tree_summary_shows_diameter_and_count():
    assert tree_summary(boss_feature(), {}) == "Ø8 ×2"
    assert tree_summary(boss_feature(positions=[[0, 0]]), {}) == "Ø8"


# --- formát ------------------------------------------------------------------------------


def test_boss_needs_format_36_and_saves_as_36():
    document = Document.from_dict(plate_document([boss_feature()]))
    assert document.to_dict()["version"] == 36
    data = plate_document([boss_feature()])
    data["version"] = 35
    with pytest.raises(DocumentError, match="verze 36"):
        Document.from_dict(data)


def test_invalid_boss_record_is_rejected_when_loading():
    with pytest.raises(DocumentError, match="Směr"):
        Document.from_dict(plate_document([boss_feature(direction="up")]))


def test_round_trip_keeps_boss_unchanged():
    document = Document.from_dict(plate_document([boss_feature()]))
    assert Document.from_dict(document.to_dict()).features == document.features


def test_example_box_with_four_posts_matches_formula():
    document = Document.load("examples/sloupky_krabicka.json")
    result = rebuild(document)
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    # blok 80 × 50 × 20 − dutina 75 × 45 × 17,5 + čtyři sloupky Ø6 s otvorem Ø2,5 (výška 10)
    floor = 20 - 17.5
    height = 12 - floor  # rovina sloupků ve výšce 12 nad dnem krabičky
    expected = (80 * 50 * 20 - 75 * 45 * 17.5
                + 4 * (post(6, height) - post(2.5, height)))
    assert volume(result.part) == pytest.approx(expected, abs=1e-6)
    assert len(result.part.solids()) == 1 and result.part.is_valid
    assert document.to_dict()["version"] == 36
