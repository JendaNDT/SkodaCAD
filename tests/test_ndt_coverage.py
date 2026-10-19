"""Pokrytí ověřené geometrií referenčních dílů, ne existencí návratové hodnoty."""

from dataclasses import replace

import pytest

from conftest import EXAMPLES, face_at
from skodacad import Document, rebuild
from skodacad.ndt import UT_DISCLAIMER
from skodacad.ndt.coverage import (
    CONVERGENCE_RULE,
    PERCENT_NOTE,
    CoverageError,
    check_convergence,
    compute,
)
from skodacad.ndt.devices import Probe, place
from skodacad.ndt.geometry import PartGeometry


@pytest.fixture(scope="module")
def parts():
    return {name: PartGeometry(rebuild(Document.load(EXAMPLES / "ndt" / f"{name}.json")).part)
            for name in ("deska", "kapsa", "zebro", "tupy_svar", "pristup", "trubka")}


def test_plate_line_includes_only_centers_where_probe_fits(parts, tmp_path):
    geo = parts["deska"]
    placed = place(geo, Probe.straight(10), (-100, 0, 20), face=face_at(geo.part, 0, 0, 20))
    targets = [(-98, 0, 0), (-95, 0, 0), (0, 0, 0), (95, 0, 0), (98, 0, 0)]
    result = compute(geo, placed, points=targets, mode="line", length_mm=200,
                     scan_step=5, target_step=1, tolerance_mm=0.01)
    assert result.states == ["uncovered", "covered", "covered", "covered", "uncovered"]
    assert result.valid_positions == 39
    assert result.hits[2].distance == pytest.approx(20)
    assert result.total_area == 0
    text = result.write_csv(tmp_path / "coverage.csv").read_text(encoding="utf-8-sig")
    assert UT_DISCLAIMER in text and PERCENT_NOTE in text
    assert "Geometricky nepokryto" in text and "20,000000" in text


def test_plate_area_and_mesh_are_weighted_and_three_colors_are_discrete(parts):
    geo = parts["deska"]
    placed = place(geo, Probe.straight(10), (0, 0, 20))
    result = compute(geo, placed, faces=[face_at(geo.part, 0, 0, 0)],
                     scan_step=5, target_step=5)
    assert result.total_area == pytest.approx(200 * 100)
    # Numerická tolerance nesmí rozšířit obrys za platný otisk sondy.
    assert result.percent("covered") == pytest.approx(85.5, abs=2)
    assert sum(result.percent(s) for s in ("covered", "uncovered", "uncertain")) == 100
    nodes, triangles, colors = result.mesh()
    assert len(triangles) == len(result.states) and len(nodes) == 3 * len(triangles)
    assert len(set(colors)) >= 2
    assert all(colors[a] == colors[b] == colors[c] for a, b, c in triangles)


@pytest.mark.parametrize("reserve,expected", [(0, "covered"), (5, "uncovered")])
def test_rib_root_with_handling_reserve(parts, reserve, expected):
    geo = parts["zebro"]
    placed = place(geo, Probe.angle(reserve=reserve), (40, 0, 20), angle=180)
    result = compute(geo, placed, points=[(0, 0, 0)], mode="line", length_mm=30,
                     angle_deg=180, bounces=0, scan_step=1, tolerance_mm=0.01)
    assert result.states == [expected]


def test_grid_tolerance_does_not_bridge_rib_blind_spot(parts):
    geo = parts["zebro"]
    placed = place(geo, Probe.angle(reserve=5), (40, 0, 20), angle=180)
    result = compute(geo, placed, points=[(0, 0, 0)], mode="line", length_mm=30,
                     angle_deg=180, bounces=0, scan_step=2, target_step=5)
    assert result.states == ["uncovered"]  # nejbližší platná osa končí v x = +2 mm


@pytest.mark.parametrize("angle,expected", [(0, "uncovered"), (90, "covered")])
def test_narrow_access_allows_only_probe_along_ribs(parts, angle, expected):
    geo = parts["pristup"]
    placed = place(geo, Probe.angle(), (0, -15, 15), angle=angle)
    result = compute(geo, placed, points=[(0, 0, 0)], mode="face", scan_step=10,
                     target_step=5, angle_deg=angle, bounces=0)
    assert result.states == [expected]
    assert bool(result.valid_positions) == (angle == 90)


@pytest.mark.parametrize("angle,expected", [(45, "uncovered"), (60, "uncovered"),
                                          (70, "covered")])
def test_butt_weld_root_reach(parts, angle, expected):
    geo = parts["tupy_svar"]
    placed = place(geo, Probe.angle(beam_angle=angle), (50, 0, 12), angle=180)
    result = compute(geo, placed, points=[(0, 0, 0)], mode="line", length_mm=35,
                     angle_deg=180, bounces=0, scan_step=0.5, tolerance_mm=0.1)
    assert result.states == [expected]


def test_pocket_two_material_depths(parts):
    geo = parts["kapsa"]
    placed = place(geo, Probe.straight(10), (0, 0, 0))
    result = compute(geo, placed, points=[(0, 0, 15), (40, 0, 40)], mode="line",
                     length_mm=40, scan_step=5, tolerance_mm=0.01)
    assert result.states == ["covered", "covered"]
    assert [h.distance for h in result.hits] == pytest.approx([15, 40])


def test_edge_hit_is_uncertain_and_limited_reach_cannot_cover_beyond_endpoint(parts):
    geo = parts["deska"]
    placed = place(geo, Probe.angle(), (80, 0, 20))
    edge = compute(geo, placed, points=[(100, 0, 0)], mode="line", length_mm=0,
                   bounces=0, tolerance_mm=0.01)
    assert edge.states == ["uncertain"] and edge.reasons[0]
    limited = compute(geo, place(geo, Probe.straight(10), (0, 0, 20)),
                      points=[(0, 0, 0)], mode="line", length_mm=0,
                      max_length=10, tolerance_mm=20)
    assert limited.states == ["uncovered"]


def test_reflection_is_counted_only_when_allowed(parts):
    geo = parts["deska"]
    placed = place(geo, Probe.angle(), (-60, 0, 20))
    settings = dict(points=[(-20, 0, 20)], mode="line", length_mm=0, tolerance_mm=0.01)
    assert compute(geo, placed, bounces=0, **settings).states == ["uncovered"]
    reflected = compute(geo, placed, bounces=1, **settings)
    assert reflected.states == ["covered"]
    assert reflected.hits[0].leg == 2
    assert reflected.hits[0].distance == pytest.approx(40 * 2**0.5)


@pytest.mark.parametrize("direction", [0, 180])
@pytest.mark.parametrize("bounces", [1, 2])
def test_intermediate_source_is_resolved_through_side_wall_reflections(parts, direction, bounces):
    import math

    geo = parts["deska"]
    sign = 1 if direction == 0 else -1
    placed = place(geo, Probe.angle(beam_angle=60), (sign * 80, 0, 20), angle=direction)
    # Zrcadlení na boční stěně x = ±100 obrátí vliv posunu zdroje.
    # Zdroj x = ±84 leží mezi uzly pojezdu; následuje případně druhý odraz ode dna.
    target = (sign * (200 - 84 - 20 * bounces * math.tan(math.radians(60))),
              0, 0 if bounces == 1 else 20)
    settings = dict(points=[target], mode="line", length_mm=8, bounces=bounces,
                    tolerance_mm=4.8, angle_deg=direction)
    coarse = compute(geo, placed, scan_step=8, **settings)
    fine = compute(geo, placed, scan_step=4, **settings)
    assert coarse.valid_positions == 2
    assert coarse.states == fine.states == ["covered"]
    assert coarse.hits[0].origin == pytest.approx((sign * 84, 0, 20))
    assert coarse.hits[0].leg == bounces + 1
    assert coarse.hits[0].distance == pytest.approx(40 * bounces)
    assert compute(geo, placed, scan_step=8, **{**settings, "bounces": bounces - 1}).states == [
        "uncovered"]
    assert compute(geo, placed, scan_step=8, **{**settings, "length_mm": 2}).states == [
        "uncovered"]


def test_explicit_geometric_spread_is_distinct_from_grid_tolerance(parts):
    geo = parts["deska"]
    placed = place(geo, Probe.straight(10), (0, 0, 20))
    settings = dict(points=[(5, 0, 0)], mode="line", length_mm=0, tolerance_mm=0)
    assert compute(geo, placed, **settings).states == ["uncovered"]
    assert compute(geo, placed, spread_deg=20, **settings).states == ["covered"]


def test_line_colors_intersected_triangles_even_when_centers_miss_axis(parts):
    geo = parts["deska"]
    placed = place(geo, Probe.straight(10), (0, 0, 20))
    result = compute(geo, placed, faces=[face_at(geo.part, 0, 0, 0)], mode="line",
                     length_mm=20, scan_step=5, target_step=10)
    green = [[result.nodes[i] for i in tri]
             for tri, state in zip(result.triangles, result.states, strict=True)
             if state == "covered"]
    assert green
    for triangle in green:
        assert min(p[1] for p in triangle) <= 1e-7
        assert max(p[1] for p in triangle) >= -1e-7
    for x in (2, 6, 10, 14, 18):
        assert any(min(p[0] for p in tri) <= x <= max(p[0] for p in tri) for tri in green)


def test_curved_source_does_not_promote_numerical_proximity_to_certain_hit(parts):
    geo = parts["trubka"]
    placed = place(geo, Probe.straight(10), (0, 0, 57.15))
    result = compute(geo, placed, points=[(0, 0, 51.15), (1, 0, 51.15)],
                     mode="line", length_mm=0, tolerance_mm=2)
    assert result.states == ["covered", "uncertain"]


def test_coarse_grid_on_disk_keeps_the_known_placement():
    from build123d import Align, Cylinder

    geo = PartGeometry(Cylinder(10, 20, align=(Align.CENTER, Align.CENTER, Align.MIN)))
    placed = place(geo, Probe.straight(5), (0, 0, 20))
    result = compute(geo, placed, points=[(0, 0, 0)], scan_step=1000, tolerance_mm=0.01)
    assert result.valid_positions >= 1 and result.states == ["covered"]


def test_certain_hit_wins_over_earlier_uncertain_placement(parts, monkeypatch):
    from skodacad.ndt import coverage

    geo = parts["deska"]
    placed = place(geo, Probe.straight(10), (0, 0, 20))
    original = coverage.place

    def uncertain_first(*args, **kwargs):
        result = original(*args, **kwargs)
        return replace(result, state="uncertain") if result.origin[0] < 1 else result

    monkeypatch.setattr(coverage, "place", uncertain_first)
    result = compute(geo, placed, points=[(0, 0, 0)], mode="line", length_mm=5,
                     scan_step=5, tolerance_mm=6, spread_deg=20)
    assert result.states == ["covered"]
    assert result.uncertain_positions == 1 and result.valid_positions == 1


def test_convergence_searches_coarse_grid_and_reports_percentage_points(parts):
    geo = parts["deska"]
    placed = place(geo, Probe.straight(10), (0, 0, 20))
    result = check_convergence(geo, placed, points=[(0, 0, 0)], mode="line", length_mm=10,
                               scan_step=5, tolerance_mm=0.01)
    assert result.delta_pct == 0 and result.stable
    # Výslovná malá tolerance platí jen pro jemný běh; hrubý hledá podle svých kroků 10/8 mm.
    assert result.tolerances == pytest.approx((0.01, 6))
    assert "procentního bodu" in result.text and "tolerance 0.01 / 6 mm" in result.text


def test_coarse_run_finds_beams_between_its_positions(parts):
    """Rozbor docs/ndt/15, oddíl 8: na rovině je tolerance jen poloměr hledání. Body leží
    přesně mezi polohami hrubého běhu (5 mm od nich); se starou tolerancí 3 mm by je hrubý
    běh nenašel a porovnání by ukázalo 100 p. b. místo 0."""
    geo = parts["deska"]
    placed = place(geo, Probe.straight(10), (-20, 0, 20), face=face_at(geo.part, 0, 0, 20))
    options = dict(points=[(-15, 0, 0), (-5, 0, 0), (5, 0, 0), (15, 0, 0)], mode="line",
                   length_mm=40, scan_step=5)
    fine = compute(geo, placed, **options)
    assert fine.states == ["covered"] * 4 and fine.assumptions["tolerance_mm"] == 3
    old_rule = compute(geo, placed, **(options | {"scan_step": 10, "target_step": 8,
                                                  "tolerance_mm": 3}))
    assert old_rule.states == ["uncovered"] * 4
    assert "hledání nemusí najít všechny paprsky" in old_rule.assumptions["tolerance_warning"]
    result = check_convergence(geo, placed, fine=fine, **options)
    assert result.delta_pct == 0 and result.tolerances == (3, 6)
    found = fine.assumptions["convergence"]
    assert found["rule"] == CONVERGENCE_RULE and found["coarse_tolerance_mm"] == 6
    assert found["coarse_pct"]["covered"] == 100
    assert fine.assumptions["convergence_text"] == result.text


def test_small_explicit_tolerance_is_flagged_in_summary_and_csv(parts, tmp_path):
    geo = parts["deska"]
    placed = place(geo, Probe.straight(10), (0, 0, 20))
    small = compute(geo, placed, points=[(0, 0, 0)], mode="line", length_mm=10,
                    scan_step=5, tolerance_mm=0.01)
    warning = small.assumptions["tolerance_warning"]
    assert "krok pojezdu × 0,6 = 3 mm" in warning
    assert warning in small.summary()
    assert "hledání nemusí" in small.write_csv(tmp_path / "c.csv").read_text("utf-8-sig")
    exact = compute(geo, placed, points=[(0, 0, 0)], mode="line", length_mm=10, scan_step=5)
    assert "tolerance_warning" not in exact.assumptions


@pytest.mark.parametrize("kwargs", [{"scan_step": 0}, {"scan_step": float("nan")},
                                   {"spread_deg": 90}, {"tolerance_mm": -1},
                                   {"mode": "other"}, {"scan_step": 0.1,
                                    "length_mm": 100000, "mode": "line"}])
def test_invalid_settings_fail_before_expensive_scan(parts, kwargs):
    geo = parts["deska"]
    with pytest.raises(CoverageError):
        compute(geo, place(geo, Probe.straight(), (0, 0, 20)), points=[(0, 0, 0)], **kwargs)


def test_contact_face_is_not_covered_by_the_beam_leaving_it(tmp_path):
    """Rozhodnutí autora 19. 10. 2026 (otázka z etapy 09): sonda stojí na dně žebra, které je
    zároveň cílem. První rameno z plochy jen vychází – nepočítá se (dřív 56,35 % při kroku
    10 mm). Odražené rameno, které se na dno vrátí (celý krok), se počítá dál."""
    from skodacad.ndt.coverage import CONTACT_NOTE
    from skodacad.session import ModelSession

    session = ModelSession()
    session.open(EXAMPLES / "ndt" / "zebro.json")
    bottom = face_at(session.result.part, 50, 0, 0)
    session.place_ndt_probe("s1", [bottom.wrapped], (50, 0, 0), 180)
    direct = session.compute_ndt_coverage(mode="face", step_mm=20, bounces=0)
    assert direct.percent("covered") == 0 and direct.assumptions["contact_samples"] > 0
    assert CONTACT_NOTE in direct.summary()
    assert CONTACT_NOTE in direct.write_csv(tmp_path / "pokryti.csv").read_text(
        encoding="utf-8-sig")
    skip = session.compute_ndt_coverage(mode="face", step_mm=20, bounces=1)
    covered = [h for s, h in zip(skip.states, skip.hits, strict=True) if s == "covered"]
    assert covered and all(hit.leg >= 2 for hit in covered)  # jen odražený paprsek
