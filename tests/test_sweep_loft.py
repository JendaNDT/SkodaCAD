"""Tažení profilu po trase a přechod mezi skicami: objemy podle vzorců, poloha, chyby česky."""

import math

import pytest

from conftest import box_features, make_doc
from skodacad import Document, rebuild
from skodacad.features import describe
from skodacad.section import axis_plane, cut
from skodacad.thickness_map import MapSettings, compute


def build(features, parameters=None):
    return rebuild(make_doc(features, parameters))


def build_ok(features, parameters=None):
    result = build(features, parameters)
    assert result.ok, [(s.label, s.message) for s in result.statuses if s.status != "ok"]
    assert result.part.is_valid
    return result.part


def error_of(features):
    result = build(features)
    assert not result.ok
    return result.first_error.message


def circle_sketch(sketch_id, diameter, offset=0):
    return {"id": sketch_id, "type": "sketch", "plane": "XY", "offset": offset,
            "elements": [{"shape": "circle", "diameter": diameter}]}


def square_sketch(sketch_id, side, offset=0):
    return {"id": sketch_id, "type": "sketch", "plane": "XY", "offset": offset,
            "elements": [{"shape": "rectangle", "width": side, "height": side}]}


def frustum(big, small, height):
    """Objem komolého kužele z poloměrů podstav."""
    return math.pi * height / 3 * (big**2 + big * small + small**2)


ELBOW = {"id": "koleno", "type": "sweep", "path": [[0, 0, 0], [0, 0, 100], [100, 0, 100]],
         "bend_radius": 40, "profile": "circle", "diameter": 30, "wall": 2}
ELBOW_LENGTH = 2 * (100 - 40) + math.pi / 2 * 40  # dvě rovné části + čtvrtkruh R40
ELBOW_VOLUME = math.pi * (15**2 - 13**2) * ELBOW_LENGTH  # Pappova věta: průřez × dráha těžiště


# --- tažení -------------------------------------------------------------------------------


def test_pipe_elbow_volume_is_cross_section_times_centerline():
    part = build_ok([ELBOW])
    assert part.volume == pytest.approx(ELBOW_VOLUME, rel=1e-9)
    box = part.bounding_box()  # začátek svisle v počátku, konec vodorovně v X = 100
    assert (box.min.X, box.min.Y, box.min.Z) == pytest.approx((-15, -15, 0))
    assert (box.max.X, box.max.Y, box.max.Z) == pytest.approx((100, 15, 115))


def test_sharp_corner_gives_mitered_rhs_frame():
    part = build_ok([{"id": "ram", "type": "sweep", "path": [[0, 0, 0], [100, 0, 0],
                                                            [100, 100, 0]],
                      "profile": "rectangle", "width": 40, "height": 20, "wall": 2}])
    # spoj na pokos: každý kus je hranol seříznutý rovinou přes osu → průřez × délka osy
    assert part.volume == pytest.approx((40 * 20 - 36 * 16) * 200)
    box = part.bounding_box()  # šířka 40 vodorovně (Y), výška 20 svisle (Z)
    assert (box.min.X, box.min.Y, box.min.Z) == pytest.approx((0, -20, -10))
    assert (box.max.X, box.max.Y, box.max.Z) == pytest.approx((120, 100, 10))
    assert len(part.solids()) == 1


def test_sketch_profile_with_hole_starts_at_the_first_point():
    part = build_ok([
        {"id": "p", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "rectangle", "width": 10, "height": 6},
                      {"shape": "circle", "diameter": 3, "mode": "subtract"}]},
        {"id": "t", "type": "sweep", "path": [[0, 0, 0], [0, 0, 50]], "profile": "sketch",
         "sketch": "p"},
    ])
    assert part.volume == pytest.approx((10 * 6 - math.pi * 1.5**2) * 50)
    box = part.bounding_box()  # svislá trasa: osa X skici zůstane osou X
    assert (box.min.X, box.min.Y, box.max.X, box.max.Y, box.max.Z) == pytest.approx(
        (-5, -3, 5, 3, 50))


def test_closed_path_makes_a_frame_mitered_or_bent():
    """Uzavřená trasa (poslední bod = první): rám, všechny rohy stejné, objem = průřez × osa."""
    area = 40 * 20 - 36 * 16
    corners = [[0, 0, 0], [800, 0, 0], [800, 500, 0], [0, 500, 0], [0, 0, 0]]
    frame = build_ok([{"id": "r", "type": "sweep", "path": corners, "profile": "rectangle",
                       "width": 40, "height": 20, "wall": 2}])
    assert frame.volume == pytest.approx(area * 2600)
    assert len(frame.solids()) == 1
    box = frame.bounding_box()
    assert (box.size.X, box.size.Y, box.size.Z) == pytest.approx((840, 540, 20))
    bent = build_ok([{"id": "r", "type": "sweep", "path": corners, "bend_radius": 60,
                      "profile": "circle", "diameter": 30, "wall": 2}])
    centerline = 2600 - 8 * 60 + 2 * math.pi * 60  # rohy nahradí čtvrtkruhy R60
    assert bent.volume == pytest.approx(math.pi * (15**2 - 13**2) * centerline, rel=1e-6)
    straight = build_ok([{"id": "r", "type": "sweep", "path": [[0, 0, 0], [50, 0, 0],
                                                               [100, 0, 0], [100, 80, 0]],
                          "bend_radius": 20, "profile": "circle", "diameter": 10}])
    assert straight.volume == pytest.approx(  # bod uprostřed rovné části nevadí
        math.pi * 25 * (180 - 2 * 20 + math.pi / 2 * 20), rel=1e-6)


def test_sweep_cut_makes_a_groove_and_parameters_work():
    part = build_ok(box_features(20, 100, 20) + [
        {"id": "dr", "type": "sweep", "path": [[0, "-L/2", 20], [0, "L/2", 20]],
         "profile": "circle", "diameter": "d", "operation": "cut"},
    ], {"L": 100, "d": 10})
    assert part.volume == pytest.approx(20 * 100 * 20 - math.pi * 5**2 / 2 * 100)


def test_pattern_repeats_a_sweep():
    part = build_ok([ELBOW, {"id": "pole", "type": "pattern", "features": ["koleno"],
                             "kind": "linear", "direction": "Y", "count": 3, "spacing": 50}])
    assert part.volume == pytest.approx(3 * ELBOW_VOLUME, rel=1e-9)
    assert len(part.solids()) == 3


def test_sweep_errors_are_czech():
    assert "aspoň 2 body" in error_of([{**ELBOW, "path": [[0, 0, 0]]}])
    assert "se nevejde" in error_of([{**ELBOW, "path": [[0, 0, 0], [0, 0, 10], [10, 0, 10]],
                                      "bend_radius": 50}])
    assert "moc tlustá" in error_of([{**ELBOW, "wall": 20}])
    assert "jsou stejné" in error_of([{**ELBOW, "path": [[0, 0, 0], [0, 0, 0]]}])
    assert "[x, y, z]" in error_of([{**ELBOW, "path": [[0, 0], [0, 10]]}])
    assert "záporný" in error_of([{**ELBOW, "bend_radius": -5}])
    assert "moc tlustá" in error_of([{"id": "j", "type": "sweep", "path": [[0, 0, 0],
                                                                          [0, 0, 9]],
                                      "profile": "rectangle", "width": 20, "height": 10,
                                      "wall": 5}])


# --- přechod ------------------------------------------------------------------------------


def test_ruled_loft_between_squares_is_a_pyramid_frustum():
    part = build_ok([square_sketch("a", 40), square_sketch("b", 20, offset=30),
                     {"id": "l", "type": "loft", "sketches": ["a", "b"], "ruled": True}])
    big, small = 40**2, 20**2
    assert part.volume == pytest.approx(30 / 3 * (big + small + math.sqrt(big * small)))


def test_loft_between_circles_is_a_cone_frustum():
    part = build_ok([circle_sketch("a", 40), circle_sketch("b", 20, offset=30),
                     {"id": "l", "type": "loft", "sketches": ["a", "b"]}])
    assert part.volume == pytest.approx(frustum(20, 10, 30), rel=1e-6)


def test_hollow_cone_has_wall_perpendicular_to_the_surface():
    part = build_ok([circle_sketch("a", 80), circle_sketch("b", 40, offset=60),
                     {"id": "l", "type": "loft", "sketches": ["a", "b"], "wall": 3}])
    # stěna 3 mm kolmo k plášti = vnitřní kužel menší v poloměru o 3 / cos(α)
    shift = 3 / math.cos(math.atan((40 - 20) / 60))
    expected = frustum(40, 20, 60) - frustum(40 - shift, 20 - shift, 60)
    assert part.volume == pytest.approx(expected, rel=1e-6)
    assert len(part.faces()) == 4  # vnější a vnitřní plášť, dva mezikruhové konce


def test_hollow_round_to_square_keeps_the_wall_in_the_sketch_planes():
    part = build_ok([square_sketch("a", 40), circle_sketch("b", 40, offset=50),
                     {"id": "l", "type": "loft", "sketches": ["a", "b"], "wall": 2}])
    bottom = cut(part, axis_plane("Z", 0.01))  # průřez u spodní skici: čtvercový rám
    assert bottom.area == pytest.approx(40**2 - 36**2, rel=1e-3)
    top = cut(part, axis_plane("Z", 49.99, flipped=True))  # u horní skici: mezikruží
    assert top.area == pytest.approx(math.pi * (20**2 - 18**2), rel=1e-3)
    assert part.bounding_box().size.Z == pytest.approx(50)  # konce jsou otevřené, ne víčka


def test_thickness_map_of_hollow_loft_equals_the_wall():
    part = build_ok([circle_sketch("a", 60), circle_sketch("b", 60, offset=100),
                     {"id": "l", "type": "loft", "sketches": ["a", "b"], "wall": 5}])
    assert part.volume == pytest.approx(math.pi * (30**2 - 25**2) * 100, rel=1e-6)
    found = compute(part, MapSettings(step=10))
    on_mantle = [v for v, (_x, _y, z) in zip(found.values, found.centers, strict=True)
                 if 0.5 < z < 99.5]
    assert on_mantle and all(v == pytest.approx(5, abs=1e-3) for v in on_mantle)


def test_loft_can_add_to_a_part():
    part = build_ok(box_features(40, 40, 10) + [
        square_sketch("a", 40, offset=10), circle_sketch("b", 20, offset=40),
        {"id": "l", "type": "loft", "sketches": ["a", "b"], "ruled": True},
    ])
    assert part.volume > 40 * 40 * 10
    assert len(part.solids()) == 1


def test_loft_errors_are_czech():
    with_hole = {"id": "p", "type": "sketch", "plane": "XY",
                 "elements": [{"shape": "rectangle", "width": 10, "height": 6},
                              {"shape": "circle", "diameter": 3, "mode": "subtract"}]}
    assert "bez děr" in error_of([with_hole, square_sketch("q", 10, offset=20),
                                  {"id": "l", "type": "loft", "sketches": ["p", "q"]}])
    assert "se nepodařil" in error_of([square_sketch("a", 40), square_sketch("b", 10, offset=50),
                                       {"id": "l", "type": "loft", "sketches": ["a", "b"],
                                        "wall": 6}])
    assert "aspoň 2 skici" in error_of([square_sketch("a", 40),
                                        {"id": "l", "type": "loft", "sketches": ["a"]}])
    assert "neexistuje" in error_of([square_sketch("a", 40),
                                     {"id": "l", "type": "loft", "sketches": ["a", "x"]}])


# --- popis, formát ------------------------------------------------------------------------


def test_tree_descriptions():
    assert describe(ELBOW) == "Tažení koleno – trubka Ø30 × 2, trasa z 3 bodů"
    assert describe({"id": "r", "type": "sweep", "profile": "rectangle", "width": "w",
                     "height": 20, "path": [[0, 0, 0], [1, 0, 0]]}, {"w": 40}) == (
        "Tažení r – obdélník 40 × 20, trasa z 2 bodů")
    assert describe({"id": "l", "type": "loft", "sketches": ["a", "b"], "wall": 2}) == (
        "Přechod l – mezi 2 skicami, dutý 2 mm")


def test_format_version_11_loads_and_old_files_still_open():
    base = {"format": "skodacad", "features": [ELBOW]}
    assert rebuild(Document.from_dict({**base, "version": 11})).ok
    assert Document.from_dict({**base, "version": 10}).features[0]["type"] == "sweep"
