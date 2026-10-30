"""Objemové váhy, nezávislé meze pokrytí a neztracená nejistota (07B)."""

import csv
import io
import math
import pickle
from dataclasses import replace

import pytest
from build123d import Align, Box, Location

from conftest import EXAMPLES
from skodacad import Document, rebuild
from skodacad.ndt import UT_DISCLAIMER
from skodacad.ndt.coverage import PERCENT_NOTE, CoverageError
from skodacad.ndt.devices import Probe, place
from skodacad.ndt.geometry import PartGeometry
from skodacad.ndt.volume_coverage import (
    _sample_volume,
    check_volume_convergence,
    compute_volume,
)
from skodacad.ndt.welds import normalize_target
from test_ndt_welds import fillet_target, v_target, volume_target


@pytest.fixture(scope="module")
def geo():
    return PartGeometry(Box(48, 40, 30, align=(Align.CENTER, Align.CENTER, Align.MIN)))


def target():
    return volume_target(frame={"origin": [-5, -5, 4], "axis": [0, 1, 0],
                                "across": [1, 0, 0]}, length_mm=10,
                         profile_mm=[[0, 0], [10, 0], [10, 8], [0, 8]])


def sample(geo, saved, step=7):
    return _sample_volume(geo, normalize_target(saved), step, 1, 1)


def test_nondividing_grid_preserves_6000_mm3_and_partial_cell_weights():
    material = PartGeometry(Box(50, 50, 50))
    saved = volume_target(profile_mm=[[0, 0], [10, 0], [10, 30], [0, 30]])
    saved["frame"]["origin"] = [0, -10, -15]
    samples, resolved, metadata = sample(material, saved)
    assert resolved.volume_mm3 == pytest.approx(6000)
    assert math.fsum(s.volume_mm3 for s in samples) == pytest.approx(6000)
    assert len({round(s.volume_mm3, 6) for s in samples}) > 1
    assert all(material.classify(s.point) == "inside" for s in samples)
    assert abs(metadata["volume_error_mm3"]) < 1e-6


def test_hole_splits_one_cell_into_two_weighted_pieces():
    # Z jediného hranolu odebrat celý prostřední pás: dva kusy v jedné buňce.
    part = Box(10, 10, 10) - Box(2, 20, 20)
    material = PartGeometry(part)
    saved = volume_target(frame={"origin": [-5, -5, -5], "axis": [0, 1, 0],
                                  "across": [1, 0, 0]}, length_mm=10,
                          profile_mm=[[0, 0], [10, 0], [10, 10], [0, 10]])
    samples, resolved, _ = sample(material, saved, 20)
    assert resolved.volume_mm3 == pytest.approx(800)
    assert len(samples) == 2
    assert sorted(s.volume_mm3 for s in samples) == pytest.approx([400, 400])
    assert all(material.classify(s.point) == "inside" for s in samples)


def test_concave_piece_uses_a_verified_interior_point(geo):
    saved = target() | {"profile_mm": [[0, 0], [10, 0], [10, 1], [1, 1], [1, 10], [0, 10]]}
    samples, _, _ = sample(geo, saved, 20)
    assert len(samples) == 1 and samples[0].volume_mm3 == pytest.approx(190)
    point = samples[0].point
    assert point is not None and geo.classify(point) == "inside"
    assert point[0] < -4 or point[2] < 5  # těžiště L by leželo mimo samotný cíl


def test_clipped_target_keeps_only_material_and_empty_is_error(geo):
    saved = target()
    saved["frame"]["origin"][2] = 26
    samples, resolved, _ = sample(geo, saved)
    assert resolved.requested_volume_mm3 == pytest.approx(800)
    assert math.fsum(s.volume_mm3 for s in samples) == pytest.approx(400)
    saved["frame"]["origin"][2] = 30
    with pytest.raises(ValueError, match="žádný společný objem"):
        sample(geo, saved)


@pytest.mark.parametrize("name,saved,expected", [
    ("tupy_svar", v_target(), 14613.84387633061),
    ("koutovy_svar", fillet_target(), 2450),
    ("koutovy_svar", fillet_target(True), 2450),
])
def test_reference_weld_weights_are_analytic(name, saved, expected):
    material = PartGeometry(rebuild(Document.load(EXAMPLES / "ndt" / f"{name}.json")).part)
    samples, resolved, _ = sample(material, saved, 8)
    assert resolved.volume_mm3 == pytest.approx(expected)
    assert math.fsum(s.volume_mm3 for s in samples) == pytest.approx(expected)
    assert all(s.point is not None for s in samples)


def test_volume_hit_and_endpoint_limit_have_independently_known_weights(geo):
    placed = place(geo, Probe.straight(4), (0, 0, 30))
    settings = dict(target=target(), scan_step=8, target_step=4, bounces=0)
    full = compute_volume(geo, placed, **settings)
    assert full.total_volume == pytest.approx(800)
    assert full.volume("covered") == pytest.approx(800)
    assert full.percent("covered") == pytest.approx(100)
    partial = compute_volume(geo, placed, max_length=22, **settings)
    assert partial.volume("covered") == pytest.approx(400)
    assert partial.volume("uncovered") == pytest.approx(400)
    assert all(hit.distance <= 22 + 1e-7 for hit in partial.hits if hit)
    missed = compute_volume(geo, placed, max_length=5, tolerance_mm=100, **settings)
    assert missed.volume("uncovered") == pytest.approx(800)


def test_rigid_rotation_preserves_grid_weights_and_hit_states(geo):
    placed = place(geo, Probe.straight(4), (0, 0, 30))
    original = compute_volume(geo, placed, target=target(), scan_step=12, target_step=7)
    transform = Location((10, 20, 5), (0, 0, 1), 30)
    rotated_geo = PartGeometry(geo.part.located(transform))
    angle = math.radians(30)

    def point(p):
        return [10 + p[0]*math.cos(angle) - p[1]*math.sin(angle),
                20 + p[0]*math.sin(angle) + p[1]*math.cos(angle), p[2] + 5]

    saved = target()
    saved["frame"] = {"origin": point(saved["frame"]["origin"]),
                      "axis": [-math.sin(angle), math.cos(angle), 0],
                      "across": [math.cos(angle), math.sin(angle), 0]}
    rotated = compute_volume(rotated_geo, place(rotated_geo, Probe.straight(4), point((0, 0, 30)),
                                              angle=30), target=saved, angle_deg=30,
                             scan_step=12, target_step=7)
    assert [s.volume_mm3 for s in rotated.samples] == pytest.approx(
        [s.volume_mm3 for s in original.samples])
    assert rotated.states == original.states


def test_missing_interior_point_stays_uncertain_and_csv_keeps_tiny_weight(geo, monkeypatch,
                                                                      tmp_path):
    from skodacad.ndt import volume_coverage as module

    monkeypatch.setattr(module._InteriorSearch, "point", lambda *a: None)
    saved = target() | {"length_mm": 0.001}
    result = compute_volume(geo, place(geo, Probe.straight(4), (0, 0, 30)), target=saved,
                            scan_step=12, target_step=20)
    assert result.volume("uncertain") == pytest.approx(0.08)
    assert result.samples[0].point is None and result.hits == [None]
    tiny = replace(result.samples[0], volume_mm3=1e-12)
    result = replace(result, samples=[tiny], total_volume=1e-12)
    text = result.write_csv(tmp_path / "tiny.csv").read_text(encoding="utf-8-sig")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    header = next(i for i, row in enumerate(rows) if row[0] == "buňka")
    row = rows[header + 1]
    assert row[2:5] == ["", "", ""] and float(row[5].replace(",", ".")) == 1e-12
    assert UT_DISCLAIMER in text and PERCENT_NOTE in text and "objem [mm³]" in text
    assert "mm²" not in text


def test_classification_budget_keeps_all_known_weights_uncertain(geo, monkeypatch):
    from skodacad.ndt import volume_coverage as module

    monkeypatch.setattr(module, "MAX_CLASSIFICATIONS", 0)
    samples, _, _ = sample(geo, target(), 7)
    assert math.fsum(s.volume_mm3 for s in samples) == pytest.approx(800)
    assert all(s.point is None and s.reason for s in samples)


@pytest.mark.parametrize("failure", ["exception", "lost_volume"])
def test_kernel_failure_or_lost_weight_cannot_produce_percent(geo, monkeypatch, failure):
    from skodacad.ndt import volume_coverage as module

    def broken(*args):
        if failure == "exception":
            raise RuntimeError("porucha jádra")
        return None

    monkeypatch.setattr(module, "_intersection", broken)
    with pytest.raises(CoverageError, match="Průnik|nezachovalo objem"):
        sample(geo, target(), 20)


@pytest.mark.parametrize("settings", [{"target_step": 0.1}, {"mode": "line"},
                                       {"scan_step": False}, {"spread_deg": float("nan")},
                                       {"tolerance_mm": -1}])
def test_invalid_or_oversized_settings_fail_before_cell_intersections(geo, monkeypatch, settings):
    from skodacad.ndt import volume_coverage as module

    def forbidden(*args):
        pytest.fail("Drahý průnik se neměl spustit.")

    monkeypatch.setattr(module, "_intersection", forbidden)
    with pytest.raises(CoverageError):
        compute_volume(geo, place(geo, Probe.straight(4), (0, 0, 30)), target=target(),
                       **settings)


def test_convergence_uses_fixed_tolerance_and_reports_all_states(geo):
    placed = place(geo, Probe.straight(4), (0, 0, 30))
    settings = dict(target=target(), scan_step=8, target_step=4, max_length=22, bounces=0)
    fine = compute_volume(geo, placed, **settings)
    result = check_volume_convergence(geo, placed, fine=fine, **settings)
    assert result.fine == pytest.approx({"covered": 50, "uncovered": 50, "uncertain": 0})
    assert result.delta_pct == max(abs(result.fine[s] - result.coarse[s]) for s in result.fine)
    assert fine.assumptions["convergence"]["tolerance_mm"] == 8 * math.sqrt(0.5)
    assert result.coarse_steps == (16, 8)
    assert "Nelze spolehlivě vyhodnotit" in result.text
    assert "Citlivost na krok neověřena" not in "\n".join(fine.summary())
    restored = pickle.loads(pickle.dumps(fine))
    assert restored.samples == fine.samples and restored.states == fine.states


def test_line_with_explicit_spread_is_supported_and_does_not_make_tolerance_physical(geo):
    placed = place(geo, Probe.straight(4), (0, 0, 30))
    result = compute_volume(geo, placed, target=target(), mode="line", length_mm=0,
                            scan_step=5, target_step=4, spread_deg=30, tolerance_mm=0)
    assert result.volume("covered") == pytest.approx(800)


def test_all_uncertain_placements_cannot_cover_known_volume(geo, monkeypatch):
    from skodacad.ndt import coverage

    original = coverage.place
    monkeypatch.setattr(coverage, "place", lambda *a, **kw: replace(original(*a, **kw),
                                                                 state="uncertain"))
    result = compute_volume(geo, place(geo, Probe.straight(4), (0, 0, 30)), target=target(),
                            scan_step=8, target_step=20)
    assert result.volume("covered") == 0
    assert result.volume("uncertain") == pytest.approx(800)


def test_volume_uses_verified_intermediate_source_after_side_wall_reflection():
    geo = PartGeometry(rebuild(Document.load(EXAMPLES / "ndt/deska.json")).part)
    x = 200 - 84 - 15 * math.tan(math.radians(60))
    saved = volume_target(frame={"origin": [x - 0.1, -0.1, 4.9], "axis": [0, 1, 0],
                                  "across": [1, 0, 0]}, length_mm=0.2,
                          profile_mm=[[0, 0], [0.2, 0], [0.2, 0.2], [0, 0.2]])
    placed = place(geo, Probe.angle(beam_angle=60), (80, 0, 20))
    settings = dict(target=saved, mode="line", length_mm=8, scan_step=8,
                    target_step=1, spread_deg=0.1, tolerance_mm=4.8)
    result = compute_volume(geo, placed, bounces=1, **settings)
    assert result.states == ["covered"] and result.hits[0].leg == 2
    assert result.hits[0].origin == pytest.approx((84, 0, 20))
    assert result.hits[0].distance == pytest.approx(30)
    assert compute_volume(geo, placed, bounces=0, **settings).states == ["uncovered"]


def test_plate_grid_refinement_approaches_known_855_percent_volume():
    geo = PartGeometry(rebuild(Document.load(EXAMPLES / "ndt/deska.json")).part)
    # Spodní vrstva 5 mm: přímý paprsek svítí kolmo, pokrytí na hloubce nezávisí a
    # buněk je 4× méně než přes celou tloušťku 20 mm (stejných 85,5 %).
    saved = volume_target(frame={"origin": [-100, -50, 0], "axis": [0, 1, 0],
                                  "across": [1, 0, 0]}, length_mm=100,
                          profile_mm=[[0, 0], [200, 0], [200, 5], [0, 5]])
    placed = place(geo, Probe.straight(10), (0, 0, 20))
    coarse = compute_volume(geo, placed, target=saved, scan_step=10, target_step=10, bounces=0)
    fine = compute_volume(geo, placed, target=saved, scan_step=10, target_step=5, bounces=0)
    assert fine.total_volume == pytest.approx(100000)
    assert fine.volume("covered") == pytest.approx(85500)
    assert fine.percent("covered") == pytest.approx(85.5)
    assert abs(fine.percent("covered") - 85.5) < abs(coarse.percent("covered") - 85.5)
    assert sum(fine.volume(s) for s in ("covered", "uncovered", "uncertain")) == pytest.approx(
        fine.total_volume)
