"""Virtuální sonda a její přiložení (NDT etapa 03) – proti ručním výpočtům.

Hodnoty odpovídají docs/ndt/05-referencni-dily.md a návrhu 07-navrh-etapa-03.md:
úhlová sonda 40 × 20 × 25 mm s výstupním bodem 12 mm od čela, přímá Ø 10 × 25 mm.
"""

import math

import pytest

from conftest import EXAMPLES
from skodacad import Document, rebuild
from skodacad.ndt.devices import DeviceError, Probe, place, scan_line, with_limits
from skodacad.ndt.geometry import PartGeometry

NDT = EXAMPLES / "ndt"
ANGLE = Probe.angle()
TO_RIB = (-1, 0, 0)  # paprsek k žebru (osa x = 0)


@pytest.fixture(scope="module")
def parts():
    return {name: PartGeometry(rebuild(Document.load(NDT / f"{name}.json")).part)
            for name in ("zebro", "trubka", "otvor", "kapsa", "pristup", "koutovy_svar",
                         "deska")}


def gap_at(distance, radius=57.15):
    """Mezera rovné kontaktní plochy na válci ve vzdálenosti ``distance`` od přímky dotyku."""
    return radius - math.sqrt(radius**2 - distance**2)


# --- sonda -----------------------------------------------------------------------------------


def test_probe_defaults_label_and_round_trip():
    assert ANGLE.to_dict() == {"kind": "angle", "length": 40, "width": 20, "height": 25,
                               "front": 12, "beam_angle": 45, "bounces": 1,
                               "max_gap": 0.5, "reserve": 0}
    assert Probe.from_dict(ANGLE.to_dict()) == ANGLE
    straight = Probe.from_dict({"kind": "straight", "diameter": 12})
    assert straight.bounces == 0
    assert straight.label == "Přímá sonda Ø 12 × 25 mm"
    assert ANGLE.label == "Úhlová sonda 40 × 20 × 25 mm, výstupní bod 12 mm od čela"
    assert with_limits(ANGLE, reserve=5).reserve == 5
    assert ANGLE.body().volume == pytest.approx(40 * 20 * 25)
    box = ANGLE.body().bounding_box()  # výstupní bod v počátku, čelo 12 mm vpředu
    assert (box.min.X, box.max.X, box.min.Z) == (pytest.approx(-28), pytest.approx(12), 0)


@pytest.mark.parametrize("data, message", [
    ({"kind": "phased"}, "Druh sondy"),
    ({"kind": "angle", "length": -5}, "Délka sondy musí být číslo 1–500"),
    ({"kind": "angle", "front": 50}, "Výstupní bod .* musí ležet na sondě"),
    ({"kind": "angle", "beam_angle": 89}, "Úhel lomu v materiálu musí být číslo 1–85 °"),
    ({"kind": "angle", "bounces": 1.5}, "Počet odrazů musí být celé číslo 0–10"),
    ({"kind": "straight", "diameter": "deset"}, "Průměr sondy"),
    ({"kind": "straight", "length": 40}, "neznámá položka „length“"),
    ({"kind": "straight", "beam_angle": 45}, "neznámá položka „beam_angle“"),
    ({"kind": "angle", "max_gap": -1}, "Dovolená mezera"),
    ([], "musí být objekt"),
])
def test_bad_probe_is_czech_error(data, message):
    with pytest.raises(DeviceError, match=message):
        Probe.from_dict(data)


# --- přiložení: deska se žebrem ------------------------------------------------------------


def test_collision_cannot_be_excluded_by_offset_clearance_cut():
    from build123d import Align, Box, Pos

    plate = Box(40, 40, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
    bump = Pos(3, 0, 20) * Box(1, 10, 0.0005,
                              align=(Align.CENTER, Align.CENTER, Align.MIN))
    placed = place(PartGeometry(plate + bump), Probe.straight(10), (0, 0, 20))
    assert placed.state == "collision" and placed.volume > 0.001


def test_angle_probe_next_to_rib(parts):
    rib = parts["zebro"]
    free = place(rib, ANGLE, (22, 0, 20), TO_RIB)
    assert free.ok and free.clearance == pytest.approx(5)  # čelo x = 10, žebro x = 5
    assert free.gap == pytest.approx(0, abs=1e-6) and free.overhang == 0
    assert free.origin == pytest.approx((22, 0, 20))
    assert free.x_dir == pytest.approx(TO_RIB) and free.z_dir == pytest.approx((0, 0, 1))
    assert free.text == "Přiloženo. Mezera pod sondou 0.00 mm, volno k překážkám 5.00 mm."
    touching = place(rib, ANGLE, (17, 0, 20), TO_RIB)  # čelo se žebra právě dotkne
    assert touching.ok and touching.clearance == pytest.approx(0, abs=1e-6)
    pushed = place(rib, ANGLE, (16, 0, 20), TO_RIB)
    assert pushed.state == "collision" and pushed.volume == pytest.approx(1 * 20 * 25)
    assert pushed.text == "Koliduje. Průnik těla sondy s dílem 500 mm³."


def test_handling_reserve(parts):
    reserve = Probe.angle(reserve=5)
    assert place(parts["zebro"], reserve, (22, 0, 20), TO_RIB).ok
    tight = place(parts["zebro"], reserve, (20, 0, 20), TO_RIB)
    assert tight.state == "tight" and tight.clearance == pytest.approx(3)
    assert tight.text == "Málo místa. Volno jen 3.00 mm, požadovaná rezerva 5.00 mm."


def test_scan_along_the_plate_toward_rib(parts):
    scan = scan_line(parts["zebro"], ANGLE, (70, 0, 20), TO_RIB, TO_RIB, 60, 1)
    assert scan.free_ranges == ((0, 53),)  # volně z x = 70 až po x = 17
    assert scan.positions[54][1].state == "collision"  # x = 16
    reserve = scan_line(parts["zebro"], Probe.angle(reserve=5), (70, 0, 20), TO_RIB, TO_RIB,
                        60, 1)
    assert reserve.free_ranges == ((0, 48),)  # s rezervou 5 mm jen po x = 22
    edge = scan_line(parts["zebro"], ANGLE, (80, 0, 20), TO_RIB, TO_RIB, 10, 1)
    assert edge.free_ranges == ((8, 10),)  # x > 72: zadní konec sondy přesahuje okraj desky
    assert edge.positions[0][1].state == "overhang"


# --- zakřivená a vydutá plocha -----------------------------------------------------------------


def test_probes_on_pipe(parts):
    pipe = parts["trubka"]
    small = place(pipe, Probe.straight(10), (0, 0, 57.15))
    assert small.ok and small.gap == pytest.approx(gap_at(5), abs=0.002)  # 0,219 mm
    assert small.clearance is None  # vnitřek trubky pod sondou není překážka
    big = place(pipe, Probe.straight(20), (0, 0, 57.15))
    assert big.state == "lift_off" and big.gap == pytest.approx(gap_at(10), abs=0.002)
    assert "Mezera pod sondou 0.88 mm, dovoleno 0.50 mm" in big.text
    along = place(pipe, ANGLE, (0, 0, 57.15), (1, 0, 0))  # šířka 20 napříč obvodem
    assert along.state == "lift_off" and along.gap == pytest.approx(gap_at(10), abs=0.002)
    around = place(pipe, ANGLE, (0, 0, 57.15), (0, 1, 0))  # zadní konec 28 mm od dotyku
    assert around.gap == pytest.approx(gap_at(28), abs=0.01)  # 7,33 mm
    relaxed = place(pipe, Probe.straight(20, max_gap=1.0), (0, 0, 57.15))
    assert relaxed.ok


def test_flat_probe_inside_hole_collides(parts):
    wall = place(parts["otvor"], Probe.straight(10), (10, 0, 10))  # vydutá stěna otvoru
    assert wall.state == "collision"


# --- přesah, kapsa, obtížný přístup, koutový svar ------------------------------------------


def test_straight_probe_near_hole(parts):
    hole = parts["otvor"]
    over = place(hole, Probe.straight(10), (12, 0, 20))  # přesahuje nad otvor
    assert over.state == "overhang" and 0 < over.overhang < 0.5
    assert "kontaktní plochy nemá pod sebou povrch" in over.text
    assert place(hole, Probe.straight(10), (16, 0, 20)).ok
    assert place(hole, Probe.straight(10), (15, 0, 20)).ok  # okraj sondy na okraji otvoru


def test_pocket_floor(parts):
    fits = place(parts["kapsa"], Probe.straight(20), (0, 0, 15))
    assert fits.ok and fits.clearance == pytest.approx(5)  # (30 − 20) / 2
    assert place(parts["kapsa"], Probe.straight(32), (0, 0, 15)).state == "collision"


def test_narrow_gap_between_ribs(parts):
    along = place(parts["pristup"], ANGLE, (0, 0, 15), (0, 1, 0))
    assert along.ok and along.clearance == pytest.approx(5)
    across = place(parts["pristup"], ANGLE, (0, 0, 15), (1, 0, 0))
    assert across.state == "collision" and across.volume == pytest.approx(10 * 20 * 25)


def test_angle_probe_toward_fillet_weld(parts):
    assert place(parts["koutovy_svar"], ANGLE, (24, 0, 10), TO_RIB).ok  # čelo u paty svaru
    near = place(parts["koutovy_svar"], ANGLE, (23, 0, 10), TO_RIB)
    assert near.state == "collision" and near.volume == pytest.approx(0.5 * 1 * 1 * 20)


# --- chybné přiložení ----------------------------------------------------------------------


def test_bad_placement_is_czech_error(parts):
    plate = parts["deska"]
    with pytest.raises(DeviceError, match="od povrchu dílu"):
        place(plate, ANGLE, (0, 0, 30), TO_RIB)
    with pytest.raises(DeviceError, match="míří kolmo do plochy"):
        place(plate, ANGLE, (0, 0, 20), (0, 0, -1))
    assert place(plate, Probe.straight(10), (0, 0, 20), (0, 0, -1)).ok  # přímé sondě nevadí
    with pytest.raises(DeviceError, match="Krok posunu"):
        scan_line(plate, ANGLE, (0, 0, 20), TO_RIB, TO_RIB, 10, 0)


def test_beam_by_angle_on_top_and_side_faces(parts):
    plate = parts["deska"]
    assert place(plate, ANGLE, (0, 0, 20), angle=0).x_dir == pytest.approx((1, 0, 0))
    assert place(plate, ANGLE, (0, 0, 20), angle=90).x_dir == pytest.approx((0, 1, 0))
    assert place(plate, ANGLE, (0, 0, 20), angle=180).x_dir == pytest.approx((-1, 0, 0))
    side = place(plate, Probe.straight(10), (100, 0, 10), angle=0)  # boční plocha kolmá na X
    assert side.z_dir == pytest.approx((1, 0, 0)) and side.x_dir == pytest.approx((0, 1, 0))
