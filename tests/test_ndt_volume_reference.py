"""Referenční zkouška objemového pokrytí V svaru (rozbor docs/ndt/15-rozbor-citlivosti-v-svaru.md).

Výřez 10 mm z ukázkového V svaru (12 mm plech), úhlová sonda 70° zprava, bez odrazů. Paprsek
leží v rovině XZ, pokrytí proto stačí spočítat v průřezu – vzorcem, nezávisle na mřížce:
výstup osy x0 = x + tg 70° · (12 − z) musí být ≥ 22 mm (čelo sondy 12 mm před výstupem
naráží na převýšení končící v x = 10 mm) a u podkořene musí dráha projít rovinou z = 0
uvnitř jeho šířky ±3 mm. Vyjde 15,18 % průřezu.
"""

import math

import pytest

from conftest import EXAMPLES, face_at
from skodacad.ndt.volume_coverage import (
    CONVERGENCE_RULE,
    compute_volume,
    recommended_target_step,
)
from skodacad.ndt.welds import _weld_profiles, normalize_target
from skodacad.session import ModelSession
from test_ndt_welds import fillet_target, v_target, volume_target

SLICE = v_target(frame={"origin": [0, -5, 0], "axis": [0, 1, 0], "across": [1, 0, 0]},
                 length_mm=10)
PROBE = {"kind": "angle", "length": 40, "width": 20, "front": 12, "beam_angle": 70,
         "height": 25, "bounces": 0, "max_gap": 0.5, "reserve": 0}


def reference_percent() -> float:
    """Pokrytá část průřezu V svaru [%] ořezem mnohoúhelníků (bez sondy a bez mřížky)."""
    k = math.tan(math.radians(70))

    def clip(polygon, keep):
        result = []
        for i, a in enumerate(polygon):
            b = polygon[(i + 1) % len(polygon)]
            fa, fb = keep(a), keep(b)
            if fa >= 0:
                result.append(a)
            if (fa >= 0) != (fb >= 0):
                t = fa / (fa - fb)
                result.append([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])
        return result

    def area(polygon):
        return abs(sum(a[0] * b[1] - a[1] * b[0] for a, b in
                       zip(polygon, polygon[1:] + polygon[:1], strict=True))) / 2 \
            if len(polygon) > 2 else 0.0

    profiles = _weld_profiles(normalize_target(SLICE))
    covered = 0.0
    for polygon in profiles:
        part = clip(polygon, lambda v: v[0] + k * (12 - v[1]) - 22)
        if min(v[1] for v in polygon) < 0:  # podkořen
            part = clip(part, lambda v: 3 - (v[0] - k * v[1]))
        covered += area(part)
    return 100 * covered / sum(area(p) for p in profiles)


@pytest.fixture(scope="module")
def weld_slice():
    session = ModelSession()
    session.open(EXAMPLES / "ndt" / "cilove_objemy" / "tupy_svar_objem.json")
    session.set_ndt_volume_target("s1", SLICE)
    session.set_ndt_device("s1", PROBE)
    part = session.result.part
    session.place_ndt_probe("s1", [face_at(part, 50, 0, 12).wrapped], (50, 0, 12), 180)
    return session


@pytest.fixture(scope="module")
def default_result(weld_slice):
    """Výchozí nastavení okna: pojezd 5 mm, krok cíle doporučený, citlivost zapnutá."""
    return weld_slice.compute_ndt_coverage(step_mm=5, convergence=True)


def test_reference_formula_value():
    assert reference_percent() == pytest.approx(15.184, abs=0.01)


def test_recommended_target_step_is_sixth_of_smaller_section_size():
    assert recommended_target_step(normalize_target(SLICE)) == 2.5  # průřez 20 × 15 mm
    assert recommended_target_step(normalize_target(fillet_target())) == 1.0  # 7 × 7 mm
    assert recommended_target_step(normalize_target(volume_target())) == 1.5  # 10 × 30 mm
    long = normalize_target(volume_target(length_mm=100_000,
                                          profile_mm=[[0, 0], [6, 0], [6, 6], [0, 6]]))
    from skodacad.ndt.volume_coverage import MAX_CELLS, grid_extent

    step = recommended_target_step(long)  # 1 mm by dalo 3,6 milionu buněk
    assert step > 1 and step % 0.5 == 0
    assert math.prod(grid_extent(long, step)[2]) <= MAX_CELLS
    assert math.prod(grid_extent(long, step - 0.5)[2]) > MAX_CELLS


def test_default_settings_match_reference_and_comparison_is_fair(default_result):
    result = default_result
    assert result.assumptions["target_step_mm"] == 2.5
    assert result.percent("covered") == pytest.approx(reference_percent(), abs=1.0)
    found = result.assumptions["convergence"]
    assert found["rule"] == CONVERGENCE_RULE
    assert found["tolerance_mm"] == pytest.approx(5 * math.sqrt(0.5))
    assert found["coarse_tolerance_mm"] == pytest.approx(10 * math.sqrt(0.5))
    assert found["delta_pp"] <= 1  # dřívější pravidlo hledalo hrubě jen 3,54 mm daleko
    assert found["coarse_pct"]["covered"] == pytest.approx(reference_percent(), abs=1.0)
    assert "tolerance 3.54 / 7.07 mm" in result.assumptions["convergence_text"]


def test_scan_step_does_not_change_result_when_search_covers_its_grid(weld_slice,
                                                                      default_result):
    """Na rovině je tolerance jen poloměr hledání – každý zásah se přesně ověří."""
    geo, placed = weld_slice._ndt_geometry(), weld_slice.ndt_placement
    fine = default_result  # pojezd 5 mm, krok cíle 2,5 mm
    coarse = compute_volume(geo, placed, target=SLICE, scan_step=10, target_step=2.5,
                            angle_deg=180)
    assert coarse.assumptions["tolerance_mm"] == pytest.approx(10 * math.sqrt(0.5))
    assert coarse.percent("covered") == pytest.approx(fine.percent("covered"), abs=0.05)
    assert "tolerance_warning" not in fine.assumptions


def test_small_explicit_tolerance_is_flagged():
    from test_ndt_target_editor import volume_session

    session = volume_session()
    geo, placed = session._ndt_geometry(), session.ndt_placement
    target = session.ndt_study("s1")["target"]
    small = compute_volume(geo, placed, target=target, scan_step=25, target_step=10,
                           tolerance_mm=5)
    assert "hledání nemusí najít všechny paprsky" in small.assumptions["tolerance_warning"]
    assert small.assumptions["tolerance_warning"] in small.summary()
    exact = compute_volume(geo, placed, target=target, scan_step=25, target_step=10,
                           tolerance_mm=25 * math.sqrt(0.5))
    assert "tolerance_warning" not in exact.assumptions
