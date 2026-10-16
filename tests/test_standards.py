"""Normalizované díly: tvary podle tabulek, objemy podle vzorců, poloha na ploše, kapsy."""

import math

import pytest

from conftest import box_features, make_doc
from skodacad import Document, rebuild
from skodacad.features import describe
from skodacad.standards import (
    ANGLE,
    BEARING,
    COUNTERSUNK_HEAD,
    HEX_HEAD,
    IPE,
    KEY,
    KINDS,
    NUT,
    PIN,
    SOCKET_HEAD,
    UPN,
    WASHER,
    StandardError,
    normalize_section,
    part_shape,
    rhs_radii,
    section_area,
    section_sketch,
)

HEX = math.sqrt(3) / 2  # plocha šestiúhelníku = HEX · s² (s = rozměr přes plochy)


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


def standard(kind, size, **extra):
    return {"id": "n", "type": "standard", "kind": kind, "size": size, **extra}


def cylinder(diameter, height):
    return math.pi * diameter**2 / 4 * height


# --- tabulky a tvary ------------------------------------------------------------------------


def test_every_size_of_every_part_builds():
    for kind, spec in KINDS.items():
        length = 40 if spec.length else None
        for size in spec.sizes:
            shape = part_shape(kind, size, length)
            assert shape.is_valid and shape.volume > 0, (kind, size)
            pocket = part_shape(kind, size, length, pocket=True, clearance=0.2)
            assert pocket.is_valid and pocket.volume > shape.volume, (kind, size)


def test_thread_tables_are_consistent():
    assert set(SOCKET_HEAD) == set(HEX_HEAD) == set(NUT) == set(WASHER)
    assert set(COUNTERSUNK_HEAD) <= set(SOCKET_HEAD)
    for size, (dk, k, _s, _t) in COUNTERSUNK_HEAD.items():  # hlava 90°: k = (dk − d) / 2
        assert k == pytest.approx((dk - float(size[1:])) / 2, abs=0.01)
    for size, (s, _m) in NUT.items():
        assert HEX_HEAD[size][0] == s  # klíč na šroub i matici stejný
    for d, big, width in BEARING.values():
        assert d < big and width > 0
    for low, high, t1, _t2 in KEY.values():
        assert low < high and t1 > 0
    for c in PIN.values():
        assert c > 0


@pytest.mark.parametrize("designation", ["IPE 80", "IPE 100", "IPE 200", "IPE 400", "UPN 80",
                                         "UPN 100", "UPN 160", "UPN 240", "L 20x3", "L 50x5",
                                         "L 120x12"])
def test_section_area_matches_the_table(designation):
    """Plocha nakresleného průřezu (i se zaobleními) souhlasí s tabulkovou do 0,5 %."""
    area = sum(face.area for face in section_sketch(designation).faces())
    assert area == pytest.approx(section_area(designation), rel=5e-3)


def test_section_shapes_by_formula():
    h, b, tw, tf, r, _a = IPE[100]
    ipe = section_sketch("IPE 100")
    assert ipe.area == pytest.approx(2 * b * tf + (h - 2 * tf) * tw + (4 - math.pi) * r**2)
    box = ipe.bounding_box()  # na výšku, střed v počátku
    assert (box.size.X, box.size.Y, box.center().X, box.center().Y) == pytest.approx(
        (b, h, 0, 0), abs=1e-9)
    outer, inner = rhs_radii(2)
    assert (outer, inner) == (4, 2)
    rhs = section_sketch("RHS 40x20x2")
    assert rhs.area == pytest.approx(2 * 2 * (40 + 20 - 2 * 2) - (4 - math.pi) * (outer**2
                                                                                  - inner**2))
    assert section_sketch("CHS 48.3x2.6").area == pytest.approx(
        math.pi / 4 * (48.3**2 - (48.3 - 5.2)**2))
    upn = section_sketch("UPN 100").bounding_box()
    assert (upn.size.X, upn.size.Y) == pytest.approx((UPN[100][1], UPN[100][0]))
    angle = section_sketch("L 50x5").bounding_box()
    assert (angle.size.X, angle.size.Y) == pytest.approx((50, 50))
    assert all(r2 == r1 / 2 for r1, r2, _a in ANGLE.values())  # zaoblení okrajů r2 = r1 / 2


def test_section_names_are_forgiving():
    assert normalize_section("l 50×5") == "L 50x5"
    assert normalize_section("IPE100") == "IPE 100"
    assert normalize_section("chs 48,3 x 2,6") == "CHS 48.3x2.6"
    with pytest.raises(StandardError, match="v tabulce není"):
        section_sketch("IPE 110")


# --- objemy dílů podle vzorců ---------------------------------------------------------------


def test_socket_head_screw_volume_and_position():
    part = build_ok([standard("socket_screw", "M6", length=20)])
    dk, k, s, t = SOCKET_HEAD["M6"]
    assert part.volume == pytest.approx(cylinder(dk, k) - HEX * s**2 * t + cylinder(6, 20))
    box = part.bounding_box()  # hlava nad rovinou, dřík pod ní
    assert (box.min.Z, box.max.Z, box.size.X) == pytest.approx((-20, k, dk))


def test_hex_screw_nut_and_washer_volumes():
    s, k = HEX_HEAD["M8"]
    part = build_ok([standard("hex_screw", "M8", length=30)])
    assert part.volume == pytest.approx(HEX * s**2 * k + cylinder(8, 30))
    s, m = NUT["M10"]
    assert build_ok([standard("nut", "M10")]).volume == pytest.approx(
        HEX * s**2 * m - cylinder(10, m))
    d1, d2, h = WASHER["M12"]
    assert build_ok([standard("washer", "M12")]).volume == pytest.approx(
        cylinder(d2, h) - cylinder(d1, h))


def test_countersunk_screw_head_is_flush_with_the_plane():
    dk, k, s, t = COUNTERSUNK_HEAD["M6"]
    part = build_ok([standard("countersunk_screw", "M6", length=20)])
    cone = math.pi * k / 3 * ((dk / 2)**2 + dk / 2 * 3 + 3**2)  # komolý kužel hlavy
    assert part.volume == pytest.approx(cone - HEX * s**2 * t + cylinder(6, 20 - k))
    box = part.bounding_box()
    assert (box.min.Z, box.max.Z) == pytest.approx((-20, 0), abs=1e-6)  # délka i s hlavou


def test_bearing_pin_and_key_volumes():
    d, big, width = BEARING["6204"]
    assert build_ok([standard("bearing", "6204")]).volume == pytest.approx(
        cylinder(big, width) - cylinder(d, width))
    c = PIN["6"]  # sražení 45° na obou koncích: prstenec π·c²·(R − c/3)
    pin = build_ok([standard("pin", "6", length=30)])
    assert pin.volume == pytest.approx(cylinder(6, 30) - 2 * math.pi * c**2 * (3 - c / 3))
    key = build_ok([standard("key", "8x7", length=40)])
    assert key.volume == pytest.approx((8 * (40 - 8) + math.pi * 4**2) * 7)
    box = key.bounding_box()  # pero leží v drážce: spodek t1 pod rovinou, délka podél X
    assert (box.size.X, box.size.Y, box.min.Z) == pytest.approx((40, 8, -KEY["8x7"][2]))


def test_steel_bar_length_and_angle():
    bar = build_ok([standard("profile", "IPE 100", length="L", angle=90)], {"L": 1000})
    assert bar.volume == pytest.approx(section_sketch("IPE 100").area * 1000)
    box = bar.bounding_box()  # natočeno o 90°: výška profilu podél X
    assert (box.size.X, box.size.Y, box.size.Z) == pytest.approx((100, 55, 1000))


# --- v dílu: poloha, kapsy, drážka ------------------------------------------------------


def test_screws_on_top_face_at_positions_and_pattern():
    part = build_ok(box_features(60, 40, 10) + [
        standard("socket_screw", "M5", length=8, plane="top", positions=[[-20, 0], [20, 0]]),
        {"id": "pole", "type": "pattern", "features": ["n"], "kind": "linear",
         "direction": "Y", "count": 2, "spacing": 12},
    ])
    dk, k, s, t = SOCKET_HEAD["M5"]
    head = cylinder(dk, k) - HEX * s**2 * t  # dřík je v materiálu – objem nepřidá
    assert part.volume == pytest.approx(60 * 40 * 10 + 4 * head)
    assert part.bounding_box().max.Z == pytest.approx(10 + k)


def test_nut_pocket_with_clearance_for_3d_print():
    part = build_ok(box_features(40, 40, 10) + [
        standard("nut", "M6", plane="top", operation="cut", direction="reverse",
                 clearance=0.2, positions=[[-10, 0], [10, 0]]),
    ])
    s, m = NUT["M6"]  # kapsa bez díry, o vůli větší na každou stranu, hloubka m + vůle
    assert part.volume == pytest.approx(40 * 40 * 10 - 2 * HEX * (s + 0.4)**2 * (m + 0.2))


def test_bearing_pocket_is_a_full_cylinder():
    d, big, width = BEARING["608"]
    part = build_ok(box_features(40, 40, 20) + [
        standard("bearing", "608", plane="top", operation="cut", direction="reverse"),
    ])
    assert part.volume == pytest.approx(40 * 40 * 20 - cylinder(big, width))


def test_keyway_on_shaft_has_depth_t1():
    """Pero 8 × 7 odebrané na tečné rovině hřídele Ø30 = drážka hloubky t1 = 4 mm."""
    part = build_ok([
        {"id": "s", "type": "sketch", "plane": "YZ",
         "elements": [{"shape": "circle", "diameter": 30}]},
        {"id": "e", "type": "extrude", "sketch": "s", "distance": 100},
        standard("key", "8x7", length=40, operation="cut",
                 plane={"at": [50, 0, 15], "normal": [0, 0, 1]}),
    ])
    t1 = KEY["8x7"][2]
    steps = 4000  # průřez drážky: hloubka od povrchu válce po dno, délka slotu v daném y
    removed = 0.0
    for i in range(steps):
        y = -4 + 8 * (i + 0.5) / steps
        depth = math.sqrt(15**2 - y**2) - (15 - t1)
        removed += depth * (32 + 2 * math.sqrt(16 - y**2)) * 8 / steps
    assert part.volume == pytest.approx(cylinder(30, 100) - removed, rel=1e-5)
    assert part.bounding_box().max.Z == pytest.approx(15)


def test_steel_section_in_sketch_and_sweep():
    part = build_ok([
        {"id": "p", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "steel", "section": "L 50×5", "center": [100, 0]}]},
        {"id": "e", "type": "extrude", "sketch": "p", "distance": 500},
    ])
    assert part.volume == pytest.approx(section_sketch("L 50x5").area * 500)
    assert part.bounding_box().center().X == pytest.approx(100)
    frame = build_ok([{"id": "r", "type": "sweep", "path": [[0, 0, 0], [1000, 0, 0],
                                                            [1000, 1000, 0]],
                       "profile": "steel", "section": "RHS 40x20x2"}])
    assert frame.volume == pytest.approx(section_sketch("RHS 40x20x2").area * 2000)


# --- chyby, popis, formát ------------------------------------------------------------------


def test_errors_are_czech():
    assert "v tabulce není" in error_of([standard("nut", "M7")])
    assert "Chybí" in error_of([standard("socket_screw", "M6")])
    assert "výška hlavy" in error_of([standard("countersunk_screw", "M8", length=4)])
    assert "šířka pera" in error_of([standard("key", "8x7", length=5)])
    assert "otoč do materiálu" in error_of(box_features(40, 40, 10) + [
        standard("nut", "M6", plane="top", operation="cut")])
    assert "Vůle kapsy" in error_of(box_features(40, 40, 10) + [
        standard("nut", "M6", plane="top", operation="cut", direction="reverse",
                 clearance=-1)])
    assert "povolené" in error_of([standard("rivet", "M6")])


def test_tree_descriptions():
    assert describe(standard("socket_screw", "M6", length=20, positions=[[0, 0], [1, 1]])) == (
        "Normalizovaný díl n – ISO 4762 M6 × 20, 2 ks")
    assert describe(standard("nut", "M6", operation="cut")) == (
        "Normalizovaný díl n – ISO 4032 M6 (kapsa)")
    assert describe(standard("bearing", "608")) == "Normalizovaný díl n – ložisko 608 (8 × 22 × 7)"
    assert describe(standard("profile", "UPN 100", length="L"), {"L": 2000}) == (
        "Normalizovaný díl n – U 100 (UPN) × 2000")
    assert describe(standard("key", "8x7", length=40)) == "Normalizovaný díl n – pero 8 × 7 × 40"


def test_format_version_12():
    data = {"format": "skodacad", "features": [standard("nut", "M6")]}
    assert rebuild(Document.from_dict({**data, "version": 12})).ok
    assert Document.from_dict({**data, "version": 11}).features[0]["type"] == "standard"
