"""P6.17 – rozříznutí dílu rovinou (docs/p6-17-rozriznuti.md): objemy podle vzorců, strany roviny,
odmítnutí roviny mimo díl a zápis formátu 37.

Očekávané objemy jsou spočítané ze vzorců (kvádr × výška řezu), ne převzaté z výsledku.
"""

from __future__ import annotations

import copy

import pytest
from build123d import Box, Plane, Pos

from skodacad import split
from skodacad.document import VERSION, Document, DocumentError
from skodacad.features import VOLUME_FEATURES, tree_summary
from skodacad.rebuild import rebuild


def volume(part) -> float:
    return sum(solid.volume for solid in part.solids())


BLOCK = Pos(0, 0, 10) * Box(60, 40, 20)  # z od 0 do 20, objem 48 000
AREA = 60 * 40


# --- geometrie ---------------------------------------------------------------------------


def test_below_and_above_keep_the_exact_part_of_the_block():
    below = split.apply(BLOCK, Plane.XY.offset(7), "below")
    above = split.apply(BLOCK, Plane.XY.offset(7), "above")
    assert volume(below) == pytest.approx(AREA * 7, abs=1e-6)
    assert volume(above) == pytest.approx(AREA * 13, abs=1e-6)
    assert below.bounding_box().max.Z == pytest.approx(7, abs=1e-6)
    assert above.bounding_box().min.Z == pytest.approx(7, abs=1e-6)
    assert len(below.solids()) == len(above.solids()) == 1 and below.is_valid and above.is_valid


def test_both_parts_keep_the_total_volume_and_gap_moves_the_upper_part_along_the_normal():
    result = split.apply(BLOCK, Plane.XY.offset(7), "both", 5)
    assert len(result.solids()) == 2 and result.is_valid
    assert volume(result) == pytest.approx(AREA * 20, abs=1e-6)
    box = result.bounding_box()
    assert (box.min.Z, box.max.Z) == pytest.approx((0, 25), abs=1e-6)  # 20 + mezera 5
    lower, upper = sorted(result.solids(), key=lambda s: s.bounding_box().min.Z)
    assert upper.bounding_box().min.Z - lower.bounding_box().max.Z == pytest.approx(5, abs=1e-6)


def test_both_without_gap_gives_two_touching_bodies():
    result = split.apply(BLOCK, Plane.XY.offset(7), "both")
    assert len(result.solids()) == 2
    assert volume(result) == pytest.approx(AREA * 20, abs=1e-6)


def test_above_follows_the_plane_normal_also_for_xz_which_points_to_minus_y():
    # rovina XZ s posunem 5 leží v y = −5, normála míří do −Y: „nad“ je y < −5 (šířka 15)
    above = split.apply(BLOCK, Plane.XZ.offset(5), "above")
    box = above.bounding_box()
    assert (box.min.Y, box.max.Y) == pytest.approx((-20, -5), abs=1e-6)
    assert volume(above) == pytest.approx(60 * 15 * 20, abs=1e-6)


def test_shelled_box_splits_into_base_and_lid_with_exact_volumes():
    box = BLOCK - Pos(0, 0, 12) * Box(56, 36, 20)  # dno 2 mm, stěny 2 mm, nahoře otevřená
    base = split.apply(box, Plane.XY.offset(12), "below")
    lid = split.apply(box, Plane.XY.offset(12), "above")
    assert volume(base) == pytest.approx(AREA * 2 + (AREA - 56 * 36) * 10, abs=1e-6)
    assert volume(lid) == pytest.approx((AREA - 56 * 36) * 8, abs=1e-6)
    assert volume(base) + volume(lid) == pytest.approx(volume(box), abs=1e-6)


def test_part_with_two_bodies_keeps_every_cut_piece():
    other = Pos(100, 0, 10) * Box(20, 20, 20)
    part = split.Part(split.Compound([*BLOCK.solids(), *other.solids()]).wrapped)
    below = split.apply(part, Plane.XY.offset(5), "below")
    assert len(below.solids()) == 2
    assert volume(below) == pytest.approx(AREA * 5 + 20 * 20 * 5, abs=1e-6)


# --- odmítnutí ---------------------------------------------------------------------------


@pytest.mark.parametrize("offset", [25, -3, 20, 0])
@pytest.mark.parametrize("keep", ["below", "above", "both"])
def test_plane_outside_or_on_the_surface_is_rejected(offset, keep):
    with pytest.raises(split.SplitError, match="neprotíná"):
        split.apply(BLOCK, Plane.XY.offset(offset), keep)


@pytest.mark.parametrize("gap", [-1, float("nan"), float("inf"), 1e6])
def test_bad_gap_is_rejected(gap):
    with pytest.raises(split.SplitError, match="Mezera"):
        split.apply(BLOCK, Plane.XY.offset(7), "both", gap)


def test_gap_needs_both_parts():
    with pytest.raises(split.SplitError, match="obou částí"):
        split.apply(BLOCK, Plane.XY.offset(7), "below", 3)


def test_validate_rejects_unknown_key_keep_and_gap_without_both():
    base = {"id": "r", "type": "split", "plane": "XY", "offset": 7, "keep": "below"}
    split.validate(base)
    with pytest.raises(split.SplitError, match="neznámý klíč"):
        split.validate({**base, "angle": 5})
    with pytest.raises(split.SplitError, match="Ponechaná část"):
        split.validate({**base, "keep": "middle"})
    with pytest.raises(split.SplitError, match="jen při ponechání obou"):
        split.validate({**base, "gap": 2})
    split.validate({**base, "keep": "both", "gap": "G"})


# --- prvek v modelu ----------------------------------------------------------------------


def block_document(features, params=None) -> dict:
    return {
        "format": "skodacad", "version": VERSION, "name": "rozrez",
        "parameters": params or {},
        "features": [
            {"id": "obrys", "type": "sketch", "plane": "XY",
             "elements": [{"shape": "rectangle", "width": 60, "height": 40}]},
            {"id": "blok", "type": "extrude", "sketch": "obrys", "distance": 20},
            *features,
        ],
    }


def split_feature(**changes) -> dict:
    feature = {"id": "rez", "type": "split", "plane": "XY", "offset": 7, "keep": "below"}
    feature.update(changes)
    return feature


def build(features, params=None):
    return rebuild(Document.from_dict(block_document(features, params)))


def status_of(result, feature_id):
    return next(item for item in result.statuses if item.id == feature_id)


def test_feature_keeps_the_part_below_the_plane_and_is_registered():
    result = build([split_feature()])
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    assert volume(result.part) == pytest.approx(AREA * 7, abs=1e-6)
    assert "split" in VOLUME_FEATURES


def test_feature_with_both_parts_and_parameters_gives_two_bodies():
    result = build([split_feature(keep="both", offset="H", gap="G")], {"H": 8, "G": 4})
    assert status_of(result, "rez").status == "ok", status_of(result, "rez")
    assert len(result.part.solids()) == 2
    assert volume(result.part) == pytest.approx(AREA * 20, abs=1e-6)
    assert result.part.bounding_box().max.Z == pytest.approx(24, abs=1e-6)


def test_plane_from_a_face_name_splits_at_that_face():
    # „top“ je horní plocha dílu (z = 20) – rovina na povrchu díl neprotíná
    result = build([split_feature(plane="top", offset=-6, keep="above")])
    assert status_of(result, "rez").status == "ok", status_of(result, "rez")
    assert volume(result.part) == pytest.approx(AREA * 6, abs=1e-6)


def test_plane_missing_the_part_is_an_error_and_keeps_the_part_unchanged():
    result = build([split_feature(offset=50)])
    status = status_of(result, "rez")
    assert status.status == "error" and "Rozříznutí" in status.message
    assert "neprotíná" in status.message
    assert volume(result.part) == pytest.approx(AREA * 20, abs=1e-6)


def test_feature_after_the_split_still_works_on_the_remaining_part():
    chamfer = {"id": "skos", "type": "chamfer", "edges": {"face": "top"}, "distance": 1}
    result = build([split_feature(), chamfer])
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    assert volume(result.part) < AREA * 7


def test_tree_summary_names_the_kept_part():
    assert tree_summary(split_feature(), {}) == "pod rovinou"
    assert tree_summary(split_feature(keep="above"), {}) == "nad rovinou"
    assert tree_summary(split_feature(keep="both"), {}) == "obě části"


# --- formát ------------------------------------------------------------------------------


def test_split_needs_format_37_and_saves_as_37():
    document = Document.from_dict(block_document([split_feature()]))
    assert document.to_dict()["version"] == 37
    without = Document.from_dict(block_document([]))
    assert without.to_dict()["version"] < 37 and VERSION >= 37


def test_split_in_older_format_is_rejected():
    data = block_document([split_feature()])
    data["version"] = 36
    with pytest.raises(DocumentError, match="verze 37"):
        Document.from_dict(data)


def test_invalid_split_record_is_rejected_when_loading():
    with pytest.raises(DocumentError, match="Ponechaná část"):
        Document.from_dict(block_document([split_feature(keep="middle")]))


def test_round_trip_keeps_split_unchanged():
    document = Document.from_dict(block_document([split_feature(keep="both", gap=3)]))
    again = Document.from_dict(copy.deepcopy(document.to_dict()))
    assert again.features == document.features


def test_example_box_splits_into_base_and_lid_matching_formula():
    document = Document.load("examples/rozriznuta_krabicka.json")
    result = rebuild(document)
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    # blok 80 × 50 × 25 minus uzavřená dutina 75 × 45 × 20; řez ve V = 15, víčko odsunuto o M = 8
    assert volume(result.part) == pytest.approx(80 * 50 * 25 - 75 * 45 * 20, abs=1e-6)
    base, lid = sorted(result.part.solids(), key=lambda s: s.bounding_box().min.Z)
    assert base.bounding_box().max.Z == pytest.approx(15, abs=1e-6)
    assert lid.bounding_box().min.Z == pytest.approx(15 + 8, abs=1e-6)
    assert lid.bounding_box().max.Z == pytest.approx(25 + 8, abs=1e-6)
    # základna: dno 2,5 a stěny do výšky 15; víčko: stěny 2,5 od roviny a strop 2,5
    walls = 80 * 50 - 75 * 45
    assert base.volume == pytest.approx(80 * 50 * 2.5 + walls * 12.5, abs=1e-6)
    assert lid.volume == pytest.approx(walls * 7.5 + 80 * 50 * 2.5, abs=1e-6)
    assert document.to_dict()["version"] == 37


def test_example_changes_with_parameters():
    result = rebuild(Document.load("examples/rozriznuta_krabicka.json"), {"V": 10, "M": 3})
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    base, lid = sorted(result.part.solids(), key=lambda s: s.bounding_box().min.Z)
    assert base.bounding_box().max.Z == pytest.approx(10, abs=1e-6)
    assert lid.bounding_box().min.Z == pytest.approx(13, abs=1e-6)
