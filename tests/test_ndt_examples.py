"""Referenční díly NDT (etapa 00): stavějí se, objem podle vzorce, rozměry pro pozdější etapy.

Očekávané výsledky každého dílu jsou ručně spočítané v docs/ndt/05-referencni-dily.md.
Paprsek (``RayCaster``) tu jen ověřuje rozměry dílu – není to fyzikální model UT.
"""

import math

import pytest

from conftest import EXAMPLES
from skodacad import Document, rebuild
from skodacad.measure import RayCaster

NDT = EXAMPLES / "ndt"

VOLUMES = {  # objem podle vzorce (mm³)
    "deska": 200 * 100 * 20,
    "kapsa": 120 * 80 * 40 - 40 * 30 * 25,
    "navrh_kapsa": 120 * 80 * 40 - 40 * 30 * 25,
    "zebro": 200 * 100 * 20 + 10 * 100 * 60,
    "otvor": 200 * 100 * 20 - math.pi * 10**2 * 20,
    "trubka": math.pi / 4 * (114.3**2 - 102.3**2) * 300,
    # plechy + převýšení (lichoběžník 20/14 × 2) + podkořen (lichoběžník 6/4 × 1), délka 100
    "tupy_svar": 300 * 100 * 12 + (20 + 14) / 2 * 2 * 100 + (6 + 4) / 2 * 1 * 100,
    # pásnice + stojina + 2 koutové svary (trojúhelník 7 × 7 / 2), délka 100
    "koutovy_svar": 200 * 100 * 10 + 10 * 100 * 80 + 2 * 7 * 7 / 2 * 100,
    "pristup": 200 * 100 * 15 + 2 * 10 * 100 * 50,
    # PT (etapa 11): blok − štěrbina 40 × 1 × 20 − slepý otvor Ø 6 × 20
    "sterbina": 100 * 60 * 30 - 40 * 1 * 20 - math.pi * 3**2 * 20,
}


def build(name, **overrides):
    result = rebuild(Document.load(NDT / f"{name}.json"), overrides or None)
    assert result.ok, [(s.label, s.message) for s in result.statuses if s.status != "ok"]
    return result.part


def path_length(part, start, direction):
    """Délka paprsku v materiálu od bodu na povrchu k protější stěně (mm)."""
    depth, oblique = RayCaster(part).thickness(start, direction)
    assert not oblique
    return depth


def test_all_reference_parts_are_there():
    assert sorted(path.stem for path in NDT.glob("*.json")) == sorted(VOLUMES)


@pytest.mark.parametrize("name", sorted(VOLUMES))
def test_reference_part_is_one_valid_solid_with_formula_volume(name):
    part = build(name)
    assert part.is_valid
    assert len(part.solids()) == 1
    assert part.volume == pytest.approx(VOLUMES[name], rel=1e-9)


def test_plate_thickness_follows_parameter():
    assert path_length(build("deska"), (30, 10, 20), (0, 0, -1)) == pytest.approx(20)
    assert path_length(build("deska", t=30), (30, 10, 30), (0, 0, -1)) == pytest.approx(30)


def test_pocket_floor_and_full_height_from_below():
    part = build("kapsa")
    assert path_length(part, (0, 0, 0), (0, 0, 1)) == pytest.approx(40 - 25)  # pod kapsou
    assert path_length(part, (40, 0, 0), (0, 0, 1)) == pytest.approx(40)  # vedle kapsy
    bottom = [f for f in part.faces() if f.center().Z == pytest.approx(15)]
    assert len(bottom) == 1 and bottom[0].area == pytest.approx(40 * 30)  # dno kapsy


def test_rib_thickness_and_height():
    part = build("zebro")
    assert path_length(part, (5, 0, 50), (-1, 0, 0)) == pytest.approx(10)  # žebro z boku
    assert path_length(part, (0, 0, 0), (0, 0, 1)) == pytest.approx(20 + 60)  # pod žebrem
    assert path_length(part, (40, 0, 20), (0, 0, -1)) == pytest.approx(20)  # vedle žebra


def test_hole_has_no_material_inside_and_full_plate_outside():
    part = build("otvor")
    assert RayCaster(part).thickness((5, 0, 20), (0, 0, -1)) == (None, False)  # v otvoru
    assert path_length(part, (12, 0, 20), (0, 0, -1)) == pytest.approx(20)  # u kraje otvoru


def test_pipe_wall_and_flat_probe_lift_off():
    part = build("trubka")
    assert path_length(part, (0, 0, 57.15), (0, 0, -1)) == pytest.approx(6)
    radius = 114.3 / 2
    gap = radius - math.sqrt(radius**2 - 10**2)  # rovná sonda šířky 20 napříč obvodem
    assert gap == pytest.approx(0.8817, abs=1e-4)
    limit = math.degrees(math.asin((radius - 6) / radius))  # obvodový paprsek mine vnitřek
    assert limit == pytest.approx(63.51, abs=0.01)


def test_butt_weld_cap_root_and_skip_distances():
    part = build("tupy_svar")
    assert path_length(part, (0, 0, 14), (0, 0, -1)) == pytest.approx(12 + 2 + 1)  # osa svaru
    assert path_length(part, (40, 0, 12), (0, 0, -1)) == pytest.approx(12)  # plech
    needed = 20 / 2 + 12  # čelo sondy (výstupní bod 12 mm od čela) mimo převýšení
    half_skip = {angle: 12 * math.tan(math.radians(angle)) for angle in (45, 60, 70)}
    assert [half_skip[a] >= needed for a in (45, 60, 70)] == [False, False, True]
    assert needed - half_skip[60] == pytest.approx(1.22, abs=0.01)


def test_fillet_weld_toes_and_web():
    part = build("koutovy_svar")
    assert path_length(part, (0, 0, 0), (0, 0, 1)) == pytest.approx(10 + 80)  # pod stojinou
    assert path_length(part, (5, 0, 50), (-1, 0, 0)) == pytest.approx(10)  # stojina z boku
    toes = [e for e in part.edges() if e.geom_type.name == "LINE"
            and abs(e.center().Z - 10) < 1e-6 and abs(abs(e.center().X) - 12) < 1e-6]
    assert len(toes) == 2  # paty svarů 12 mm od osy stojiny


def test_narrow_gap_between_ribs():
    part = build("pristup")
    inner = sorted(f.center().X for f in part.faces()
                   if abs(abs(f.normal_at().X) - 1) < 1e-9 and abs(f.center().X) < 20)
    assert inner == pytest.approx([-15, 15])  # světlá mezera 30 mm
    assert path_length(part, (0, 0, 0), (0, 0, 1)) == pytest.approx(15)  # pod mezerou
    assert path_length(part, (20, 0, 0), (0, 0, 1)) == pytest.approx(15 + 50)  # pod žebrem
