"""Geometrický model UT paprsku (NDT etapa 04) – výsledky proti ručním výpočtům.

Hodnoty odpovídají docs/ndt/05-referencni-dily.md a návrhu 09-navrh-etapa-04.md:
přímá a úhlová sonda, půlkrok a celý krok, lom podle Snellova zákona se zadanými rychlostmi,
odrazy od stěn a zastavení na nejednoznačném dopadu (hrana, roh).
"""

import math

import pytest

from conftest import EXAMPLES
from skodacad import Document, rebuild
from skodacad.ndt.devices import Probe, place
from skodacad.ndt.geometry import THROUGH_EDGE, PartGeometry
from skodacad.ndt.ut import (
    ALGORITHM,
    STOPPED_UNCERTAIN,
    BeamError,
    refract,
    trace_beam,
)

NDT = EXAMPLES / "ndt"
ANGLE = Probe.angle()
STRAIGHT = Probe.straight(10)
TO_X = (1, 0, 0)
TO_RIB = (-1, 0, 0)


@pytest.fixture(scope="module")
def parts():
    return {name: PartGeometry(rebuild(Document.load(NDT / f"{name}.json")).part)
            for name in ("deska", "kapsa", "zebro", "otvor", "trubka", "tupy_svar")}


# --- 1. Deska: přímá sonda, úhlová 45°/60°/70°, půlkrok a celý krok -----------------------


def test_plate_straight_probe_and_thickness_change(parts):
    plate = parts["deska"]
    placed = place(plate, STRAIGHT, (0, 0, 20))
    beam = trace_beam(plate, placed)
    assert beam.certain and beam.beta == 0 and beam.bounces == 0
    assert len(beam.legs) == 1
    [leg] = beam.legs
    assert leg.length == pytest.approx(20) and leg.depth == pytest.approx(20)
    assert leg.horizontal == pytest.approx(0, abs=1e-6)
    assert leg.end == pytest.approx((0, 0, 0)) and leg.incidence == pytest.approx(0)
    assert beam.total_length == pytest.approx(20)
    assert beam.points == (pytest.approx((0, 0, 20)), pytest.approx((0, 0, 0)))

    thicker = PartGeometry(rebuild(Document.load(NDT / "deska.json"), {"t": 30}).part)
    beam_30 = trace_beam(thicker, place(thicker, STRAIGHT, (0, 0, 30)))
    assert beam_30.total_length == pytest.approx(30) and beam_30.legs[0].depth == pytest.approx(30)


@pytest.mark.parametrize("beta, half_skip, leg_len", [
    (45, 20.0, 20.0 / math.cos(math.radians(45))),       # 20,00 a 28,28 mm
    (60, 20.0 * math.tan(math.radians(60)), 40.0),       # 34,64 a 40,00 mm
    (70, 20.0 * math.tan(math.radians(70)), 20.0 / math.cos(math.radians(70))),  # 54,95 a 58,48 mm
])
def test_plate_angle_probe_half_skip_and_full_skip(parts, beta, half_skip, leg_len):
    plate = parts["deska"]
    placed = place(plate, ANGLE, (-50, 0, 20), TO_X)
    beam = trace_beam(plate, placed, beta=beta, bounces=1)
    assert beam.certain and len(beam.legs) == 2 and beam.actual_bounces == 1
    leg1, leg2 = beam.legs
    assert leg1.length == pytest.approx(leg_len, abs=1e-3)
    assert leg1.horizontal == pytest.approx(half_skip, abs=1e-3)
    assert leg1.depth == pytest.approx(20) and leg1.incidence == pytest.approx(beta, abs=1e-3)
    assert leg1.end == pytest.approx((-50 + half_skip, 0, 0), abs=1e-3)

    assert leg2.length == pytest.approx(leg_len, abs=1e-3)
    assert leg2.horizontal == pytest.approx(2 * half_skip, abs=1e-3)
    assert leg2.depth == pytest.approx(0, abs=1e-3)
    assert leg2.end == pytest.approx((-50 + 2 * half_skip, 0, 20), abs=1e-3)
    assert beam.half_skip == pytest.approx(half_skip, abs=1e-3)
    assert beam.full_skip == pytest.approx(2 * half_skip, abs=1e-3)
    assert beam.total_length == pytest.approx(2 * leg_len, abs=1e-3)


# --- 2. Blok s kapsou a 4. Deska s otvorem -------------------------------------------------


def test_pocket_block_and_hole_plate(parts):
    pocket = parts["kapsa"]
    under = trace_beam(pocket, place(pocket, STRAIGHT, (0, 0, 0)))
    assert under.certain and under.total_length == pytest.approx(15)
    assert under.legs[0].end == pytest.approx((0, 0, 15))
    outside = trace_beam(pocket, place(pocket, STRAIGHT, (40, 0, 0)))
    assert outside.certain and outside.total_length == pytest.approx(40)

    holed = parts["otvor"]
    placed = place(holed, STRAIGHT, (16, 0, 20))
    assert placed.ok
    assert trace_beam(holed, placed).total_length == pytest.approx(20)


# --- 3. Deska se žebrem (milník M1) --------------------------------------------------------


def test_ribbed_plate_reaching_root_under_rib(parts):
    rib = parts["zebro"]
    # 45° bez rezervy: z x = 20 (vůle 3 mm) dopadne 1. rameno přesně pod osu žebra (0, 0, 0)
    placed_45 = place(rib, ANGLE, (20, 0, 20), TO_RIB)
    assert placed_45.ok and placed_45.clearance == pytest.approx(3)
    beam_45 = trace_beam(rib, placed_45, beta=45, bounces=1)
    assert beam_45.certain and beam_45.legs[0].end == pytest.approx((0, 0, 0))
    assert beam_45.legs[1].end == pytest.approx((-20, 0, 20))

    # 45° s rezervou 5 mm: nejbližší přípustné přiložení x = 22 → dopadne v x = 2 (chybí 2 mm)
    reserve_probe = Probe.angle(reserve=5)
    placed_res = place(rib, reserve_probe, (22, 0, 20), TO_RIB)
    assert placed_res.ok
    beam_res = trace_beam(rib, placed_res, beta=45, bounces=0)
    assert beam_res.legs[0].end == pytest.approx((2, 0, 0))

    # 60° s rezervou 5 mm: z x = 20*tg(60°) = 34,64 mm dosáhne do (0, 0, 0) s vůlí 17,64 mm
    x_60 = 20.0 * math.tan(math.radians(60))
    placed_60 = place(rib, reserve_probe, (x_60, 0, 20), TO_RIB)
    assert placed_60.ok and placed_60.clearance == pytest.approx(x_60 - 17, abs=1e-3)
    beam_60 = trace_beam(rib, placed_60, beta=60, bounces=0)
    assert beam_60.legs[0].end == pytest.approx((0, 0, 0), abs=1e-3)
    assert beam_60.total_length == pytest.approx(40)

    # Přímá sonda zespodu: pod žebrem 80 mm, vedle žebra 20 mm
    assert trace_beam(rib, place(rib, STRAIGHT, (0, 0, 0))).total_length == pytest.approx(80)
    assert trace_beam(rib, place(rib, STRAIGHT, (30, 0, 0))).total_length == pytest.approx(20)


# --- 5. Trubka: radiální a obvodový paprsek ------------------------------------------------


def test_pipe_radial_and_circumferential_cutoff_angle(parts):
    pipe = parts["trubka"]
    radial = trace_beam(pipe, place(pipe, STRAIGHT, (0, 0, 57.15)))
    assert radial.certain and radial.total_length == pytest.approx(6)
    assert radial.legs[0].end == pytest.approx((0, 0, 51.15))
    assert radial.legs[0].incidence == pytest.approx(0)

    # Obvodový paprsek: mezní úhel asin(51,15 / 57,15) = 63,51°
    around = place(pipe, ANGLE, (0, 0, 57.15), (0, 1, 0))
    hit_inner = trace_beam(pipe, around, beta=60, bounces=0)
    assert hit_inner.certain
    end_60 = hit_inner.legs[0].end
    assert math.hypot(end_60[1], end_60[2]) == pytest.approx(51.15, abs=1e-3)  # vnitřní stěna

    miss_inner = trace_beam(pipe, around, beta=70, bounces=0)
    assert miss_inner.certain
    end_70 = miss_inner.legs[0].end
    assert math.hypot(end_70[1], end_70[2]) == pytest.approx(57.15, abs=1e-3)  # vnější stěna
    assert miss_inner.total_length == pytest.approx(2 * 57.15 * math.cos(math.radians(70)),
                                                    abs=1e-2)  # 39,09 mm


# --- 6. Tupý svar V: dosažení kořene 45° / 60° / 70° ---------------------------------------


def test_butt_weld_root_reachability(parts):
    weld = parts["tupy_svar"]
    closest = place(weld, ANGLE, (22, 0, 12), TO_RIB)  # čelo v x = 10 u paty převýšení
    assert closest.ok

    b45 = trace_beam(weld, closest, beta=45, bounces=0)
    assert b45.half_skip == pytest.approx(12)
    assert b45.legs[0].end == pytest.approx((10, 0, 0))  # chybí 10 mm ke kořeni

    # 60° z x = 22: v rovině plechu z = 0 (po dráze 24 mm) míjí kořen (0, 0, 0) o 1,22 mm;
    # protože podkořen (šířka 6 mm) vystupuje o p = 1 mm dolů, paprsek vyjde až na z = -1 mm.
    b60_at_plate = trace_beam(weld, closest, beta=60, bounces=0, max_length=24)
    t60 = math.tan(math.radians(60))
    assert b60_at_plate.legs[0].end == pytest.approx((22 - 12 * t60, 0, 0), abs=1e-2)  # x = 1,22 mm
    b60 = trace_beam(weld, closest, beta=60, bounces=0)
    assert b60.legs[0].depth == pytest.approx(13)  # t + p = 12 + 1 mm (spodek podkořene)
    assert b60.half_skip == pytest.approx(13 * t60, abs=1e-2)

    # 70° z x = 32,97 mm: projde přesně kořenem (0, 0, 0) a vystoupí spodkem podkořene z = -1 mm
    x_70 = 12.0 * math.tan(math.radians(70))  # 32,97 mm
    placed_70 = place(weld, ANGLE, (x_70, 0, 12), TO_RIB)
    assert placed_70.ok
    s_root = 12.0 / math.cos(math.radians(70))  # 35,09 mm do (0, 0, 0)
    b70_root = trace_beam(weld, placed_70, beta=70, bounces=0, max_length=s_root)
    assert b70_root.legs[0].end == pytest.approx((0, 0, 0), abs=1e-3)
    b70 = trace_beam(weld, placed_70, beta=70, bounces=0)
    assert b70.certain and b70.legs[0].incidence == pytest.approx(25)  # šikmý bok podkořene 45°
    x_70_bottom = 13.0 * math.tan(math.radians(70))
    b70_bottom = trace_beam(weld, place(weld, ANGLE, (x_70_bottom, 0, 12), TO_RIB), beta=70,
                            bounces=0)
    assert b70_bottom.legs[0].end == pytest.approx((0, 0, -1), abs=1e-3)


# --- Snellův zákon (lom na rozhraní předsádka → díl) ---------------------------------------


def test_snell_refraction_and_critical_angle(parts):
    # Plexisklo (2730 m/s) → ocel příčná vlna (3250 m/s): pro β = 45° spočítáme α
    alpha_45 = math.degrees(math.asin((2730 / 3250) * math.sin(math.radians(45))))
    ref = refract(alpha_45, c_wedge=2730, c_material=3250, wave="shear")
    assert ref.beta == pytest.approx(45.0, abs=1e-4)
    assert ref.critical_angle == pytest.approx(math.degrees(math.asin(2730 / 3250)), abs=1e-4)
    assert "Snellův zákon" in ref.label and "příčná vlna" in ref.label

    placed = place(parts["deska"], ANGLE, (0, 0, 20), TO_X)
    beam = trace_beam(parts["deska"], placed, bounces=1, refraction=ref)
    assert beam.half_skip == pytest.approx(20.0, abs=1e-3)
    assert beam.assumptions["algorithm"] == ALGORITHM
    assert beam.assumptions["refraction"]["c_wedge_m_s"] == 2730

    # Pomalý materiál (c2 < c1): kritický úhel neexistuje
    slow = refract(30, c_wedge=3000, c_material=1500, wave="longitudinal")
    assert slow.critical_angle is None and slow.beta < 30


@pytest.mark.parametrize("kwargs, message", [
    ({"alpha": 60, "c_wedge": 2730, "c_material": 3250}, "Nadkritický úhel.*totální odraz"),
    ({"alpha": 0, "c_wedge": 2730, "c_material": 3250}, "Úhel v předsádce musí být mezi 0° a 90°"),
    ({"alpha": 90, "c_wedge": 2730, "c_material": 3250}, "Úhel v předsádce"),
    ({"alpha": 35, "c_wedge": -100, "c_material": 3250}, "Rychlost vlny v předsádce"),
    ({"alpha": 35, "c_wedge": 2730, "c_material": 50}, "Rychlost vlny v materiálu"),
    ({"alpha": 35, "c_wedge": 2730, "c_material": 3250, "wave": "surface"}, "Druh vlny"),
])
def test_bad_refraction_raises_czech_error(kwargs, message):
    with pytest.raises(BeamError, match=message):
        refract(**kwargs)


# --- hraniční případy, omezení délky a neplatné vstupy -------------------------------------


def test_beam_hitting_corner_is_uncertain_and_stops_bouncing(parts):
    plate = parts["deska"]
    # Z x = 80 pod 45° směrem +X trefí paprsek přesně spodní hranu desky (100, 0, 0)
    placed = place(plate, ANGLE, (80, 0, 20), TO_X)
    beam = trace_beam(plate, placed, beta=45, bounces=2)
    assert not beam.certain
    assert len(beam.legs) == 1  # odraz na hraně se nesmí počítat
    assert THROUGH_EDGE in beam.reasons and STOPPED_UNCERTAIN in beam.reasons
    assert beam.total_length == 0  # nejisté rameno se nezapočítá jako potvrzená dráha
    assert beam.half_skip is None


def test_max_length_limits_beam_inside_material(parts):
    plate = parts["deska"]
    placed = place(plate, STRAIGHT, (0, 0, 20))
    short = trace_beam(plate, placed, max_length=12)
    assert short.certain and len(short.legs) == 1
    assert short.legs[0].length == pytest.approx(12)
    assert short.legs[0].hit is None and short.legs[0].incidence is None
    assert short.legs[0].end == pytest.approx((0, 0, 8))
    assert short.half_skip is None


@pytest.mark.parametrize("kwargs, message", [
    ({"beta": 0}, "Úhel lomu v materiálu musí být 1–85°"),
    ({"beta": 89}, "Úhel lomu v materiálu musí být 1–85°"),
    ({"beta": 45, "bounces": -1}, "Počet odrazů"),
    ({"beta": 45, "bounces": 20}, "Počet odrazů"),
    ({"beta": 45, "max_length": 0}, "Maximální délka dráhy musí být kladná"),
])
def test_bad_beam_parameters_raise_czech_error(parts, kwargs, message):
    placed = place(parts["deska"], ANGLE, (0, 0, 20), TO_X)
    with pytest.raises(BeamError, match=message):
        trace_beam(parts["deska"], placed, **kwargs)


def test_straight_probe_rejects_non_zero_angle(parts):
    placed = place(parts["deska"], STRAIGHT, (0, 0, 20))
    with pytest.raises(BeamError, match="Přímá sonda vysílá paprsek kolmo"):
        trace_beam(parts["deska"], placed, beta=45)


# --- příkazová řádka (skodacad sonda s paprskem) -------------------------------------------


def test_cli_probe_beam_and_snell(capsys):
    from skodacad.cli import main

    assert main(["sonda", str(NDT / "zebro.json"), "--bod", "20,0,20", "--smer", "-1,0,0",
                 "--uhel", "45"]) == 0
    out = capsys.readouterr().out
    assert "Dráha paprsku (úhel lomu 45.0°, nejvýš 1 odraz, algoritmus ndt-ut-paprsek 1):" in out
    assert "rameno 1: [20; 0; 20] → [0; 0; 0], délka 28.28 mm, vodorovně 20.00 mm" in out
    assert "rameno 2: [0; 0; 0] → [-20; 0; 20], délka 28.28 mm, vodorovně 40.00 mm" in out
    assert "celkem v materiálu: 56.57 mm, půlkrok 20.00 mm, celý krok 40.00 mm" in out

    assert main(["sonda", str(NDT / "deska.json"), "--bod", "0,0,20", "--smer", "1,0,0",
                 "--snell", "36.44,2730,3250", "--odrazy", "0"]) == 0
    out_snell = capsys.readouterr().out
    assert "Snellův zákon: α = 36.44°, c1 = 2730 m/s, c2 = 3250 m/s" in out_snell
    assert "bez odrazu" in out_snell

    assert main(["sonda", str(NDT / "deska.json"), "--bod", "0,0,20", "--uhel", "45",
                 "--snell", "36,2730,3250"]) == 2
    assert "buď --uhel, nebo --snell" in capsys.readouterr().err
    assert main(["sonda", str(NDT / "deska.json"), "--bod", "0,0,20",
                 "--snell", "60,2730,3250"]) == 2
    assert "Nadkritický úhel" in capsys.readouterr().err
