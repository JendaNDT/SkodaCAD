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
    # blok 80 × 50 × 25 minus uzavřená dutina 75 × 45 × 20; řez ve V = 15, víčko odsunuto o M = 8,
    # vnitřní lem W = 1,2 × H = 3 (vyroste z dutiny 75 × 45), drážka o vůli 0,2 širší a hlubší
    walls = 80 * 50 - 75 * 45
    tongue = (77.4 * 47.4 - 75 * 45) * 3
    groove = (77.8 * 47.8 - 75 * 45) * 3.2
    assert volume(result.part) == pytest.approx(80 * 50 * 25 - 75 * 45 * 20 + tongue - groove,
                                                abs=1e-6)
    base, lid = sorted(result.part.solids(), key=lambda s: s.bounding_box().min.Z)
    assert base.bounding_box().max.Z == pytest.approx(15 + 3, abs=1e-6)  # lem vyčnívá
    assert lid.bounding_box().min.Z == pytest.approx(15 + 8, abs=1e-6)
    assert lid.bounding_box().max.Z == pytest.approx(25 + 8, abs=1e-6)
    assert base.volume == pytest.approx(80 * 50 * 2.5 + walls * 12.5 + tongue, abs=1e-6)
    assert lid.volume == pytest.approx(walls * 7.5 + 80 * 50 * 2.5 - groove, abs=1e-6)
    assert document.to_dict()["version"] == 37


def test_example_changes_with_parameters():
    result = rebuild(Document.load("examples/rozriznuta_krabicka.json"), {"V": 10, "M": 3})
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    base, lid = sorted(result.part.solids(), key=lambda s: s.bounding_box().min.Z)
    assert base.bounding_box().max.Z == pytest.approx(10 + 3, abs=1e-6)
    assert lid.bounding_box().min.Z == pytest.approx(13, abs=1e-6)


# --- lem a drážka (P6.18) ----------------------------------------------------------------

def closed_box(corner_radius: float = 0.0):
    """Uzavřená krabička 80 × 50 × 25 s dutinou 75 × 45 × 20 (stěny a dno 2,5), z = 0…25."""
    from build123d import RectangleRounded, extrude

    outer = Pos(0, 0, 12.5) * Box(80, 50, 25)
    if corner_radius:
        cavity = Pos(0, 0, 2.5) * extrude(RectangleRounded(75, 45, corner_radius), amount=20)
    else:
        cavity = Pos(0, 0, 12.5) * Box(75, 45, 20)
    return outer - cavity


def lip_parts(lip, gap=0.0, box=None):
    result = split.apply(box or closed_box(), Plane.XY.offset(15), "both", gap, lip)
    base, lid = sorted(result.solids(), key=lambda s: s.bounding_box().min.Z)
    return base, lid


def test_inner_lip_adds_the_strip_to_the_base_and_cuts_the_wider_groove_into_the_lid():
    base, lid = lip_parts(split.Lip(1.2, 3, "inner", 0.2))
    ring = 77.4 * 47.4 - 75 * 45  # pás 1,2 mm kolem dutiny
    groove = (77.8 * 47.8 - 75 * 45) * 3.2  # pás 1,4 mm, hloubka 3,2
    assert base.volume == pytest.approx(80 * 50 * 2.5 + (80 * 50 - 75 * 45) * 12.5 + ring * 3,
                                        abs=1e-6)
    assert lid.volume == pytest.approx((80 * 50 - 75 * 45) * 7.5 + 80 * 50 * 2.5 - groove,
                                       abs=1e-6)
    assert base.bounding_box().max.Z == pytest.approx(18, abs=1e-6)
    assert len(base.solids()) == 1 and base.is_valid and lid.is_valid


def test_outer_lip_follows_the_outer_edge_of_the_section():
    base, lid = lip_parts(split.Lip(1.0, 2, "outer", 0.3))
    ring = 80 * 50 - 78 * 48  # pás 1 mm u vnějšího okraje
    groove = (80 * 50 - 77.4 * 47.4) * 2.3  # pás 1,3 mm, hloubka 2,3
    assert base.volume == pytest.approx(80 * 50 * 2.5 + (80 * 50 - 75 * 45) * 12.5 + ring * 2,
                                        abs=1e-6)
    assert lid.volume == pytest.approx((80 * 50 - 75 * 45) * 7.5 + 80 * 50 * 2.5 - groove,
                                       abs=1e-6)


def test_lip_on_a_rounded_cavity_matches_the_offset_formula():
    import math

    r = 4.0
    box = closed_box(r)
    perimeter = 2 * (75 - 2 * r) + 2 * (45 - 2 * r) + 2 * math.pi * r
    w, h = 1.2, 3.0
    base, _ = lip_parts(split.Lip(w, h, "inner", 0.2), box=box)
    plain, _ = lip_parts(None, box=box)
    ring = perimeter * w + math.pi * w * w  # odsazení konvexního obrysu: P·w + π·w²
    assert base.volume - plain.volume == pytest.approx(ring * h, abs=1e-6)


@pytest.mark.parametrize("side", ["inner", "outer"])
def test_the_lid_fits_onto_the_lip_without_collision(side):
    def overlap(base, lid) -> float:
        common = base & lid  # prázdný průnik = None
        return 0.0 if common is None else sum(s.volume for s in common.solids())

    # víčko dosedá na rovinu řezu: lem musí zapadnout do drážky, bez průniku
    assert overlap(*lip_parts(split.Lip(1.0, 3, side, 0.2), gap=0)) == pytest.approx(0, abs=1e-6)
    # bez vůle se lem a víčko dotýkají v plochách, ale nepronikají
    assert overlap(*lip_parts(split.Lip(1.0, 3, side, 0.0), gap=0)) == pytest.approx(0, abs=1e-6)
    # kontrola, že měření průniku něco odhalí: víčko zasunuté o 1 mm dolů do lemu naráží
    base, lid = lip_parts(split.Lip(1.0, 3, side, 0.2), gap=0)
    from build123d import Location
    assert overlap(base, lid.moved(Location((0, 0, -1)))) > 1.0


def test_lip_follows_the_cut_height_without_references():
    for height in (8, 15, 20):
        result = split.apply(closed_box(), Plane.XY.offset(height), "both", 0,
                             split.Lip(1.2, 3, "inner", 0.2))
        base, lid = sorted(result.solids(), key=lambda s: s.bounding_box().min.Z)
        assert base.bounding_box().max.Z == pytest.approx(height + 3, abs=1e-6)
        assert lid.bounding_box().min.Z == pytest.approx(height, abs=1e-6)


@pytest.mark.parametrize("lip,message", [
    (split.Lip(2.5, 3), "stejně široká"),  # lem je celá stěna
    (split.Lip(2.4, 3, "inner", 0.2), "stejně široká"),  # s vůlí by drážka sežrala stěnu
    (split.Lip(1.2, 11, "inner", 0.2), "hlubší než stěna"),  # drážka přes celé víčko
    (split.Lip(0, 3), "Šířka lemu"),
    (split.Lip(1.2, -1), "Výška lemu"),
    (split.Lip(1.2, 3, "inner", -0.1), "Vůle"),
    (split.Lip(1.2, 3, "middle"), "Strana lemu"),
])
def test_lip_that_does_not_fit_is_rejected(lip, message):
    with pytest.raises(split.SplitError, match=message):
        split.apply(closed_box(), Plane.XY.offset(15), "both", 0, lip)


def test_inner_lip_needs_a_cavity_in_the_section():
    with pytest.raises(split.SplitError, match="nemá kde vést"):
        split.apply(BLOCK, Plane.XY.offset(7), "both", 0, split.Lip(1, 2, "inner"))


def test_lip_needs_both_parts_and_validate_checks_the_lip_keys():
    with pytest.raises(split.SplitError, match="obou částí"):
        split.apply(closed_box(), Plane.XY.offset(15), "below", 0, split.Lip(1, 2))
    base = {"id": "r", "type": "split", "plane": "XY", "offset": 15, "keep": "both"}
    split.validate({**base, "lip_width": 1, "lip_height": 2, "lip_side": "outer",
                    "lip_clearance": "C"})
    with pytest.raises(split.SplitError, match="výšku"):
        split.validate({**base, "lip_width": 1})
    with pytest.raises(split.SplitError, match="jen s šířkou"):
        split.validate({**base, "lip_height": 2})
    with pytest.raises(split.SplitError, match="Strana lemu"):
        split.validate({**base, "lip_width": 1, "lip_height": 2, "lip_side": "x"})
    with pytest.raises(split.SplitError, match="obou částí"):
        split.validate({**base, "keep": "below", "lip_width": 1, "lip_height": 2})


def test_feature_with_lip_uses_parameters_default_clearance_and_summary():
    def box_features(**changes):
        return [
            {"id": "s0", "type": "sketch", "plane": "XY",
             "elements": [{"shape": "rectangle", "width": 80, "height": 50}]},
            {"id": "b", "type": "extrude", "sketch": "s0", "distance": 25},
            {"id": "s1", "type": "sketch", "plane": "XY", "offset": 2.5,
             "elements": [{"shape": "rectangle", "width": 75, "height": 45}]},
            {"id": "d", "type": "extrude", "sketch": "s1", "operation": "cut",
             "direction": "normal", "distance": 20},
            split_feature(offset=15, keep="both", lip_width="W", lip_height=3, **changes),
        ]

    doc = Document.from_dict({"format": "skodacad", "version": VERSION, "name": "x",
                              "parameters": {"W": 1.2}, "features": box_features()})
    result = rebuild(doc)
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    groove = (77.8 * 47.8 - 75 * 45) * 3.2  # výchozí vůle 0,2 mm
    tongue = (77.4 * 47.4 - 75 * 45) * 3
    assert volume(result.part) == pytest.approx(80 * 50 * 25 - 75 * 45 * 20 + tongue - groove,
                                                abs=1e-6)
    assert tree_summary(doc.features[-1], {}) == "obě části s lemem"
    wide = rebuild(Document.from_dict({"format": "skodacad", "version": VERSION, "name": "x",
                                       "parameters": {"W": 2.4}, "features": box_features()}))
    status = status_of(wide, "rez")
    assert status.status == "error" and "stejně široká" in status.message


# --- rozložení pro tisk (P6.19) ------------------------------------------------------------


def print_layout(gap=6.0, lip=None, plane=None, box=None):
    result = split.apply(box or closed_box(), plane or Plane.XY.offset(15), "both", gap, lip,
                         "print")
    base, lid = sorted(result.solids(), key=lambda s: s.bounding_box().min.X)
    return base, lid


def test_print_layout_puts_the_lid_upside_down_beside_the_base_on_the_same_plate():
    base, lid = print_layout(gap=6)
    base_box, lid_box = base.bounding_box(), lid.bounding_box()
    # základna beze změny (dno z = 0), víčko 80 × 50 × 10 otočené: strop na desce (z = 0)
    assert (base_box.min.Z, base_box.max.Z) == pytest.approx((0, 15), abs=1e-6)
    assert (lid_box.min.Z, lid_box.max.Z) == pytest.approx((0, 10), abs=1e-6)
    # vedle ve směru X s mezerou 6 mm, vystředěné ve směru Y
    assert lid_box.min.X - base_box.max.X == pytest.approx(6, abs=1e-6)
    assert (lid_box.center().Y, base_box.center().Y) == pytest.approx((0, 0), abs=1e-6)
    # objem obou částí se otočením a přesunem nezměnil
    assert base.volume + lid.volume == pytest.approx(volume(closed_box()), abs=1e-6)
    assert base.is_valid and lid.is_valid


def test_print_layout_opens_the_lid_upwards_and_the_groove_faces_up():
    base, lid = print_layout(gap=6, lip=split.Lip(1.2, 3, "inner", 0.2))
    box = lid.bounding_box()
    center = (box.center().X, box.center().Y)
    top = box.max.Z  # otevřená strana (původní rovina řezu) je teď nahoře
    assert top == pytest.approx(10, abs=1e-6)
    # drážka je u dutiny (vnitřní pás 37,5 – 38,9 od osy), hluboká 3,2 mm od otevřené strany
    in_groove = (center[0] + 38.2, center[1], top - 1.0)
    in_wall = (center[0] + 39.5, center[1], top - 1.0)  # vnější půlka stěny zůstala
    in_groove_deep = (center[0] + 38.2, center[1], top - 4.0)  # pod dnem drážky je materiál
    assert not lid.is_inside(in_groove)
    assert lid.is_inside(in_wall)
    assert lid.is_inside(in_groove_deep)
    # lem základny míří nahoru: nad pásem u dutiny je materiál, nad vnější půlkou stěny ne
    assert base.bounding_box().max.Z == pytest.approx(18, abs=1e-6)
    assert base.is_inside((38.2, 0, 16.5))  # základna je vystředěná v počátku
    assert not base.is_inside((39.5, 0, 16.5))


def test_print_layout_works_on_another_plane_with_axis_aligned_frame():
    # řez rovinou XZ (normála −Y): víčko leží vedle základny ve směru X roviny, na úrovni dna
    base, lid = print_layout(gap=4, plane=Plane.XZ.offset(5), box=BLOCK)
    assert len(base.solids()) == len(lid.solids()) == 1
    assert base.volume + lid.volume == pytest.approx(volume(BLOCK), abs=1e-6)
    assert lid.bounding_box().min.X - base.bounding_box().max.X == pytest.approx(4, abs=1e-6)
    # „nad“ rovinou XZ (y = −5, normála −Y) je pás y < −5 široký 15; po otočení leží strop
    # na úrovni dna základny (z = 0) a víčko u vzdálenějšího konce základny (y 5…20)
    lid_box = lid.bounding_box()
    assert (lid_box.min.Z, lid_box.max.Z) == pytest.approx((0, 20), abs=1e-6)
    assert (lid_box.min.Y, lid_box.max.Y) == pytest.approx((5, 20), abs=1e-6)


def test_print_layout_needs_both_parts_axis_aligned_plane_and_validates():
    with pytest.raises(split.SplitError, match="obou částí"):
        split.apply(closed_box(), Plane.XY.offset(15), "below", 0, None, "print")
    with pytest.raises(split.SplitError, match="Rozložení"):
        split.apply(closed_box(), Plane.XY.offset(15), "both", 0, None, "grid")
    tilted = Plane(origin=(0, 0, 15), z_dir=(0.2, 0, 1))
    with pytest.raises(split.SplitError, match="rovnoběžnou s osami"):
        split.apply(closed_box(), tilted, "both", 0, None, "print")
    base = {"id": "r", "type": "split", "plane": "XY", "offset": 15, "keep": "both"}
    split.validate({**base, "arrange": "print"})
    with pytest.raises(split.SplitError, match="Rozložení"):
        split.validate({**base, "arrange": "grid"})
    with pytest.raises(split.SplitError, match="obou částí"):
        split.validate({**base, "keep": "below", "arrange": "print"})


def test_print_layout_feature_needs_format_38_and_example_matches_formula():
    document = Document.from_dict(block_document([split_feature(keep="both", gap=5,
                                                                arrange="print")]))
    assert document.to_dict()["version"] == 38
    data = block_document([split_feature(keep="both", arrange="print")])
    data["version"] = 37
    with pytest.raises(DocumentError, match="verze 38"):
        Document.from_dict(data)
    # starý zápis (stack) zůstává ve verzi 37
    plain = Document.from_dict(block_document([split_feature(keep="both")]))
    assert plain.to_dict()["version"] == 37
    assert tree_summary(split_feature(keep="both", arrange="print"), {}) == "obě části, pro tisk"
    result = rebuild(document)
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    base, lid = sorted(result.part.solids(), key=lambda s: s.bounding_box().min.X)
    assert lid.bounding_box().min.X - base.bounding_box().max.X == pytest.approx(5, abs=1e-6)


def test_example_box_for_print_matches_formula():
    document = Document.load("examples/krabicka_pro_tisk.json")
    result = rebuild(document)
    assert all(item.status == "ok" for item in result.statuses), result.statuses
    assert document.to_dict()["version"] == 38
    tongue = (77.4 * 47.4 - 75 * 45) * 3
    groove = (77.8 * 47.8 - 75 * 45) * 3.2
    base, lid = sorted(result.part.solids(), key=lambda s: s.bounding_box().min.X)
    walls = 80 * 50 - 75 * 45
    assert base.volume == pytest.approx(80 * 50 * 2.5 + walls * 12.5 + tongue, abs=1e-6)
    assert lid.volume == pytest.approx(walls * 7.5 + 80 * 50 * 2.5 - groove, abs=1e-6)
    # obě části na jedné desce (dno z = 0), víčko otočené (výška 10) a 6 mm od základny
    assert base.bounding_box().min.Z == pytest.approx(0, abs=1e-6)
    assert (lid.bounding_box().min.Z, lid.bounding_box().max.Z) == pytest.approx((0, 10), abs=1e-6)
    assert lid.bounding_box().min.X - base.bounding_box().max.X == pytest.approx(6, abs=1e-6)
