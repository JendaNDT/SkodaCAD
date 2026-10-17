"""07C: skutečná plocha řezu, vlastnictví na hranici a přenos bez OCCT objektů."""

import math
import pickle

import pytest
from build123d import Box, Cylinder

from skodacad.ndt.geometry import PartGeometry
from skodacad.ndt.volume_coverage import _sample_volume
from skodacad.ndt.volume_display import COLORS, DisplaySource, cross_section, target_preview
from skodacad.ndt.welds import normalize_target
from skodacad.section import SectionPlane
from test_ndt_welds import volume_target


def sampled(part, step=5, target=None):
    target = target or volume_target(frame={"origin": [-5, -5, -5], "axis": [0, 1, 0],
                                            "across": [1, 0, 0]}, length_mm=10,
                                     profile_mm=[[0, 0], [10, 0], [10, 10], [0, 10]])
    source = DisplaySource()
    samples, _, _ = _sample_volume(PartGeometry(part), normalize_target(target), step, 1, 1,
                                   source)
    assert not source.error
    return samples, pickle.loads(pickle.dumps(source))


def triangle_area(mesh):
    def area(a, b, c):
        u, v = [[p[i] - a[i] for i in range(3)] for p in (b, c)]
        return math.sqrt(sum(x * x for x in (u[1] * v[2] - u[2] * v[1],
                                              u[2] * v[0] - u[0] * v[2],
                                              u[0] * v[1] - u[1] * v[0]))) / 2
    return sum(area(*(mesh.nodes[i] for i in t)) for t in mesh.triangles)


@pytest.mark.parametrize("normal,expected", [((0, 1, 0), 100), ((0, -1, 0), 100),
                                             ((1, 1, 0), 100 * math.sqrt(2))])
def test_exact_cell_boundary_has_one_owner_no_blended_colors(normal, expected):
    samples, source = sampled(Box(10, 10, 10))
    states = ["covered" if s.cell[2] == 0 else "uncovered" for s in samples]
    plane = SectionPlane((0, 0, 0), normal)
    mesh = cross_section(source, states, plane, 5)
    assert not mesh.message
    assert mesh.area_mm2 == pytest.approx(expected)
    assert triangle_area(mesh) == pytest.approx(expected)
    assert all(abs(plane.side(p)) < 1e-6 for p in mesh.nodes)
    for triangle, sample in zip(mesh.triangles, mesh.samples, strict=True):
        assert {mesh.colors[i] for i in triangle} == {COLORS[states[sample]]}
    if normal == (0, 1, 0):
        assert set(mesh.colors) == {COLORS["covered"]}
    if normal == (0, -1, 0):
        assert set(mesh.colors) == {COLORS["uncovered"]}


def test_hole_is_not_filled_and_separate_pieces_keep_identity():
    # Válec ve směru Y: skutečný průřez čtverce s kruhovou dírou.
    part = Box(10, 10, 10) - Cylinder(2, 20, rotation=(90, 0, 0))
    samples, source = sampled(part, 20)
    mesh = cross_section(source, ["uncertain"] * len(samples),
                         SectionPlane((0, 0, 0), (0, 1, 0)), 20)
    assert mesh.area_mm2 == pytest.approx(100 - math.pi * 4)
    assert triangle_area(mesh) == pytest.approx(mesh.area_mm2, abs=.2)
    for triangle in mesh.triangles:
        center = [sum(mesh.nodes[i][j] for i in triangle) / 3 for j in range(3)]
        assert math.hypot(center[0], center[2]) > 1.98
    samples, source = sampled(Box(10, 10, 10) - Box(2, 20, 20), 20)
    assert len(samples) == 2
    mesh = cross_section(source, ["covered", "uncovered"],
                         SectionPlane((0, 0, 0), (0, 1, 0)), 20)
    assert mesh.area_mm2 == pytest.approx(80)
    assert set(mesh.samples) == {0, 1}


def test_rotated_frame_and_tangent_edge_and_outside():
    root = math.sqrt(.5)
    target = volume_target(frame={"origin": [0, 0, -5], "axis": [root, root, 0],
                                   "across": [root, -root, 0]}, length_mm=10,
                            profile_mm=[[0, 0], [10, 0], [10, 10], [0, 10]])
    samples, source = sampled(Box(60, 60, 60), 5, target)
    plane = SectionPlane((5 * root, 5 * root, 0), (root, root, 0))
    mesh = cross_section(source, ["covered"] * len(samples), plane, 5)
    assert mesh.area_mm2 == pytest.approx(100)
    assert triangle_area(mesh) == pytest.approx(100)
    samples, source = sampled(Box(10, 10, 10), 20)
    for plane in (SectionPlane((5, 5, 0), (1, 1, 0)),
                  SectionPlane((0, 20, 0), (0, 1, 0))):
        mesh = cross_section(source, ["covered"], plane, 20)
        assert mesh.triangles == [] and "neprotíná" in mesh.message


def test_display_failures_hide_entire_mesh_without_losing_numeric_samples(monkeypatch):
    from skodacad.ndt import volume_display as display

    samples, source = sampled(Box(10, 10, 10))
    monkeypatch.setattr(display, "MAX_TRIANGLES", 1)
    mesh = cross_section(source, ["covered"] * len(samples),
                         SectionPlane((0, 0, 0), (0, 1, 0)), 5)
    assert mesh.triangles == [] and "500 000" in mesh.message
    assert sum(s.volume_mm3 for s in samples) == pytest.approx(1000)
    monkeypatch.setattr(display, "MAX_BYTES", 100)
    source = DisplaySource()
    target = volume_target(profile_mm=[[0, 0], [4, 0], [4, 4], [0, 4]], length_mm=4)
    samples, resolved, _ = _sample_volume(PartGeometry(Box(20, 20, 20)),
                                         normalize_target(target), 5, 1, 1, source)
    assert source.error and not source.pieces
    assert sum(s.volume_mm3 for s in samples) == pytest.approx(resolved.volume_mm3)


def test_preview_mesh_reports_effective_and_requested_volume():
    target = volume_target(length_mm=10, profile_mm=[[0, 0], [10, 0], [10, 10], [0, 10]])
    saved, mesh, numbers = target_preview(Box(10, 10, 10), target)
    assert numbers == pytest.approx({"volume_mm3": 125, "requested_volume_mm3": 1000,
                                    "outside_volume_mm3": 875})
    assert mesh.triangles and len(set(mesh.colors)) == 1
    assert saved == normalize_target(target)


def test_concave_cap_and_prefilter_keep_the_same_exact_mesh():
    target = volume_target(frame={"origin": [0, 0, 0], "axis": [0, 1, 0],
                                   "across": [1, 0, 0]}, length_mm=10,
                            profile_mm=[[0, 0], [10, 0], [10, 4], [4, 4], [4, 10], [0, 10]])
    samples, source = sampled(Box(40, 40, 40), 3, target)
    plane = SectionPlane((0, 5, 0), (0, 1, 0))
    states = ["uncertain"] * len(samples)
    whole = cross_section(source, states, plane, 3)
    subset = source.for_plane(plane)
    assert len(subset.pieces) < len(source.pieces)
    clipped = cross_section(subset, states, plane, 3)
    assert whole.area_mm2 == clipped.area_mm2 == pytest.approx(64)
    assert triangle_area(clipped) == pytest.approx(64)
    assert clipped.samples == whole.samples
