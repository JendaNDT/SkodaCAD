"""PT – geometrická přístupnost povrchu (etapa 11, ``ndt/pt.py``).

Očekávané hodnoty jsou ručně spočítané v ``docs/ndt/19-navrh-etapa-11.md`` (oddíl 4)
a ``docs/ndt/05-referencni-dily.md`` (díl 9): pás u vnitřního rohu, kam se kulička nástroje
poloměru r nedostane, je r · cot(θ/2); výhled pod úhlem k povrchu ≥ 30° ze štěrbiny šířky w
do hloubky w · tg 60°. Testy jsou krátké (body místo celých map) kvůli časovému limitu
kroku *Testy* na Windows.
"""

import math

import pytest

from conftest import EXAMPLES
from skodacad.ndt import PT_DISCLAIMER, PT_MAP
from skodacad.ndt.geometry import PartGeometry
from skodacad.ndt.pt import (
    PtError,
    PtSettings,
    Sampler,
    _grade,
    compute,
    estimate,
    study_faces,
)
from skodacad.session import ModelSession

NDT = EXAMPLES / "ndt"
S = math.sqrt(0.5)


def opened(name):
    session = ModelSession()
    session.open(NDT / f"{name}.json")
    return session


@pytest.fixture(scope="module")
def weld():
    session = opened("koutovy_svar")
    return session, Sampler(PartGeometry(session.result.part), PtSettings())


@pytest.fixture(scope="module")
def pocket():
    session = opened("kapsa")
    return session, Sampler(PartGeometry(session.result.part), PtSettings())


@pytest.fixture(scope="module")
def slot():
    session = opened("sterbina")
    return session, Sampler(PartGeometry(session.result.part), PtSettings())


def kinds(sample):
    return {kind for kind, _ in sample.reasons}


# --- nastavení -------------------------------------------------------------------------------


def test_settings_defaults_round_trip_and_czech_errors():
    default = PtSettings()
    assert default.to_dict() == {
        "cleaning": "wipe", "tool_mm": 10.0, "fine_tool_mm": 3.0, "tool_length_mm": 100.0,
        "spray_deg": 60.0, "spray_limit_deg": 85.0, "view_deg": 30.0, "view_limit_deg": 5.0,
        "view_distance_mm": 600.0, "eye_mm": 50.0, "open_warning": 10.0}
    assert PtSettings.from_dict(None) == default
    assert PtSettings.from_dict(default.to_dict()) == default
    custom = PtSettings.from_dict({"tool_mm": 8, "step_mm": 2})
    assert custom.tool_mm == 8 and custom.to_dict()["step_mm"] == 2
    for data, message in [({"nastroj": 8}, "nezná nastroj"),
                          ({"fine_tool_mm": 12}, "Jemný nástroj"),
                          ({"spray_deg": 70, "spray_limit_deg": 65}, "Nástřik šikmo"),
                          ({"view_deg": 20, "view_limit_deg": 25}, "Prohlídka šikmo"),
                          ({"cleaning": "kartac"}, "Postup čištění"),
                          ({"tool_mm": -1}, "Hlavní nástroj"),
                          ({"tool_mm": True}, "Hlavní nástroj"),
                          ([], "musí být objekt")]:
        with pytest.raises(PtError, match=message):
            PtSettings.from_dict(data)
    assert any("zvoleno pro výpočet, ne z normy" in line for line in default.lines())
    assert any("ASME BPVC V čl. 9" in line for line in default.lines())


def test_uncertain_ray_never_counts_as_accessible():
    assert _grade(10, 10, 60, 85) == "ok"
    assert _grade(None, 10, 60, 85) == "uncertain"  # volný je jen nejistý paprsek
    assert _grade(70, 10, 60, 85) == "uncertain"  # jistě jen šikmo, nejistě i kolmo
    assert _grade(70, 70, 60, 85) == "limited"
    assert _grade(None, 80, 60, 85) == "uncertain"
    assert _grade(None, None, 60, 85) == "blocked"


# --- koutový svar: rohy 135° -----------------------------------------------------------------


@pytest.mark.parametrize("x, tool", [
    (0.45, "blocked"), (0.80, "limited"), (1.95, "limited"), (2.25, "ok"), (4.95, "ok")])
def test_fillet_weld_tool_band_follows_cot_formula(weld, x, tool):
    """Plocha svaru z rohu u stojiny (5, 0, 17) k patě (12, 0, 10): pás Ø 10 = 5 · cot 67,5°
    = 2,07 mm, Ø 3 = 0,62 mm – u obou konců stejně."""
    _, sampler = weld
    length = 7 * math.sqrt(2)
    for distance in (x, length - x):  # od stojiny i od paty svaru
        point = (5 + distance * S, 0.0, 17 - distance * S)
        sample = sampler.sample(point, (S, 0.0, S))
        assert sample.tool == tool, distance
        assert sample.spray == "ok" and sample.view == "ok"


# --- kapsa: rohy 90° -------------------------------------------------------------------------


@pytest.mark.parametrize("gap, tool", [(1.0, "blocked"), (2.0, "limited"), (4.8, "limited"),
                                       (5.2, "ok")])
def test_pocket_floor_and_wall_bands_are_tool_radius(pocket, gap, tool):
    _, sampler = pocket
    floor = sampler.sample((-20 + gap, 0.0, 15.0), (0, 0, 1))  # stěna kapsy x = −20
    wall = sampler.sample((0.0, -15.0, 15 + gap), (0, 1, 0))  # dno z = 15
    for sample in (floor, wall):
        assert sample.tool == tool
        assert sample.spray == "ok" and sample.view == "ok"


def test_pocket_floor_center_is_fully_accessible_and_openness_matches_solid_angle(pocket):
    _, sampler = pocket
    sample = sampler.sample((0.0, 0.0, 15.0), (0, 0, 1))
    assert sample.state == "ok" and sample.tool_mm == 10
    # prostorový úhel otvoru 40 × 30 ve výšce 25: 4·asin(ab / √((a²+4h²)(b²+4h²))) = 20,8 %
    solid = 4 * math.asin(1200 / math.sqrt(4100 * 3400))
    assert sample.openness == pytest.approx(100 * solid / (2 * math.pi), abs=3)


# --- díl 9: štěrbina a slepý otvor -----------------------------------------------------------


@pytest.mark.parametrize("y", [0.0, 19.0])  # uprostřed i 1 mm od čela štěrbiny
@pytest.mark.parametrize("depth, grade", [(1.5, "ok"), (2.0, "limited"), (11.0, "limited"),
                                          (11.6, "blocked")])
def test_slot_wall_view_and_spray_follow_tangent_of_limit(slot, y, depth, grade):
    """Štěrbina w = 1 mm: jde do w · tg 60° = 1,73 mm, šikmo do w · tg 85° = 11,43 mm."""
    _, sampler = slot
    sample = sampler.sample((-25.5, y, 30 - depth), (1, 0, 0))
    assert sample.spray == grade and sample.view == grade
    assert sample.tool == "blocked" and sample.state == "blocked"
    assert sample.gap == pytest.approx(1.0)
    assert "slit" in kinds(sample)  # úzká štěrbina – upozornění, ne výpočet vzlínání


def test_slot_wall_minimum_free_angle_is_exact(slot):
    _, sampler = slot
    sample = sampler.sample((-25.5, 0.0, 25.0), (1, 0, 0))  # hloubka 5 mm
    assert sample.spray_angle == pytest.approx(math.degrees(math.atan(5 / 1)), abs=0.2)


@pytest.mark.parametrize("rho, tool", [(0.0, "limited"), (1.4, "limited"), (1.6, "blocked")])
def test_blind_hole_bottom_only_fine_tool_near_axis(slot, rho, tool):
    _, sampler = slot
    sample = sampler.sample((25.0 + rho, 0.0, 10.0), (0, 0, 1))
    assert sample.tool == tool and sample.view == "ok" and sample.spray == "ok"
    assert sample.openness < 10 and "deep" in kinds(sample)


@pytest.mark.parametrize("depth, view", [(5.0, "ok"), (10.0, "ok"), (11.0, "limited"),
                                         (18.0, "limited")])
def test_blind_hole_wall_view_follows_diameter_times_tangent(slot, depth, view):
    """Stěna otvoru Ø 6: výhled ≥ 30° k povrchu do hloubky 6 · tg 60° = 10,39 mm."""
    _, sampler = slot
    sample = sampler.sample((22.0, 0.0, 30 - depth), (1, 0, 0))
    assert sample.view == view
    assert sample.spray_angle == pytest.approx(math.degrees(math.atan(depth / 6)), abs=0.3)
    assert sample.tool == "limited" and sample.tool_mm == 3  # jen jemný nástroj
    assert sample.gap == pytest.approx(6.0) and "gap" in kinds(sample)


def test_blind_hole_wall_near_bottom_has_no_tool(slot):
    _, sampler = slot
    assert sampler.sample((22.0, 0.0, 11.0), (1, 0, 0)).tool == "blocked"  # 1 mm nad dnem
    assert sampler.sample((22.0, 0.0, 12.0), (1, 0, 0)).tool == "limited"  # 2 mm nad dnem


def test_rinse_turns_tool_check_off_but_keeps_slit_warning(slot):
    session, _ = slot
    sampler = Sampler(PartGeometry(session.result.part), PtSettings(cleaning="rinse"))
    shallow = sampler.sample((-25.5, 0.0, 28.5), (1, 0, 0))
    assert shallow.tool == "off" and shallow.spray == "ok" and shallow.view == "ok"
    assert shallow.state == "limited" and "slit" in kinds(shallow)
    assert sampler.sample((-25.5, 0.0, 15.0), (1, 0, 0)).state == "blocked"


def test_eye_cannot_look_into_deep_bore():
    """Slepý otvor Ø 6 hluboký 700 mm: dno je vidět jen po ose a oko (Ø 50) se nevejde blíž
    než 600 mm."""
    from build123d import Box, Cylinder, Location

    part = Box(40, 40, 710) - Cylinder(3, 700).moved(Location((0, 0, 5)))  # dno z = −345
    sampler = Sampler(PartGeometry(part), PtSettings())
    sample = sampler.sample((0.0, 0.0, -345.0), (0, 0, 1))
    assert sample.spray == "ok"
    assert sample.view == "blocked" and "view_eye" in kinds(sample)
    near = Sampler(PartGeometry(part), PtSettings(view_distance_mm=1000))
    assert near.sample((0.0, 0.0, -345.0), (0, 0, 1)).view == "ok"


def test_open_plate_is_accessible_everywhere():
    session = opened("deska")
    sample = Sampler(PartGeometry(session.result.part), PtSettings()).sample(
        (30.0, 10.0, 20.0), (0, 0, 1))
    assert sample.state == "ok" and sample.openness == 100 and not sample.reasons


# --- mapa, souhrn, CSV -----------------------------------------------------------------------


def test_map_summary_csv_and_repeatable(slot, tmp_path):
    session, _ = slot
    part = session.result.part
    faces = study_faces(PartGeometry(part), session.ndt_study("s3"))[:1]  # dno otvoru
    settings = PtSettings(step_mm=2)
    count, step, seconds = estimate(part, faces, settings)
    first, second = compute(part, faces, settings), compute(part, faces, settings)
    assert len(first.samples) == count and step == 2 and seconds > 0
    assert [s.state for s in first.samples] == [s.state for s in second.samples]
    assert first.total_area == pytest.approx(math.pi * 9, rel=0.02)  # síť: mnohoúhelník
    assert sum(first.percent(state) for state in ("ok", "limited", "blocked", "uncertain")) \
        == pytest.approx(100)
    nodes, triangles, colors = first.mesh()
    assert len(triangles) == count and len(colors) == len(nodes) == 3 * count
    assert len(first.mesh("tool")[2]) == 3 * count
    lines = first.summary()
    assert lines[:2] == [PT_MAP, PT_DISCLAIMER]
    assert any(line.startswith("Otření nástrojem:") for line in lines)
    assert any("ISO 3059" in line for line in lines)
    index = first.nearest((25.0, 0.0, 10.0))
    assert first.describe(index)[0].startswith("Omezené – nástřik jde")
    path = first.write_csv(tmp_path / "pt.csv")
    rows = path.read_text(encoding="utf-8-sig").splitlines()
    assert rows[0] == PT_MAP and rows[1] == PT_DISCLAIMER
    header = next(i for i, row in enumerate(rows) if row.startswith("x [mm]"))
    assert len(rows) - header - 1 == count


def test_study_faces_need_pt_study_with_faces(pocket, weld):
    session, _ = pocket
    geo = PartGeometry(session.result.part)
    with pytest.raises(PtError, match="jen pro PT"):
        study_faces(geo, session.ndt_study("s1"))  # UT studie
    assert len(study_faces(geo, session.ndt_study("s2"))) == 5
    with pytest.raises(PtError, match="PT posuzuje povrch"):
        study_faces(geo, {"method": "PT", "target": {"kind": "volume"}})
    with pytest.raises(PtError, match="nemá plochy"):
        study_faces(geo, {"method": "PT", "target": {"kind": "faces", "faces": []}})
    weld_session, _ = weld
    assert len(study_faces(PartGeometry(weld_session.result.part),
                           weld_session.ndt_study("s1"))) == 2
