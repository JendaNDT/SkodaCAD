"""Pomocné objemy: analytické obsahy, skutečný materiál, orientace a bezpečný formát."""

import copy
import math

import pytest
from build123d import Align, Box

from conftest import EXAMPLES
from skodacad import Document, rebuild
from skodacad.ndt.welds import TargetError, normalize_target, resolve_target


def volume_target(**updates):
    return {"kind": "volume", "frame": {"origin": [0, 0, 0], "axis": [0, 1, 0],
                                        "across": [1, 0, 0]}, "length_mm": 20,
            "profile_mm": [[0, 0], [10, 0], [10, 30], [0, 30]], **updates}


def v_target(**updates):
    return {"kind": "weld", "weld_type": "butt_v", "frame": {
        "origin": [0, -50, 0], "axis": [0, 1, 0], "across": [1, 0, 0]}, "length_mm": 100,
        "dimensions": {"thickness_mm": 12, "angle_deg": 60, "root_gap_mm": 2,
                       "cap_width_mm": 20, "cap_top_width_mm": 14, "cap_height_mm": 2,
                       "root_width_mm": 6, "root_tip_width_mm": 4, "root_height_mm": 1},
        **updates}


def fillet_target(left=False):
    sign = -1 if left else 1
    return {"kind": "weld", "weld_type": "fillet", "frame": {
        "origin": [sign * 5, -sign * 50, 10], "axis": [0, sign, 0],
        "across": [sign, 0, 0]}, "length_mm": 100,
        "dimensions": {"leg_across_mm": 7, "leg_height_mm": 7}}


@pytest.fixture(scope="module")
def material():
    return Box(200, 200, 100, align=(Align.CENTER, Align.CENTER, Align.MIN))


def test_volume_and_rotated_frame_preserve_size_and_placement(material):
    target = volume_target()
    result = resolve_target(material, target)
    assert result.volume_mm3 == pytest.approx(6000)
    box = result.shape.bounding_box()
    assert tuple(box.min) == pytest.approx((0, 0, 0))
    assert tuple(box.max) == pytest.approx((10, 20, 30))
    rotated = volume_target(frame={"origin": [-30, -30, 0], "axis": [2, 2, 0],
                                   "across": [3, -3, 0]})
    # across × axis míří vzhůru; otočený a přeložený hranol zůstává uvnitř materiálu.
    shifted = resolve_target(material, rotated)
    assert shifted.volume_mm3 == pytest.approx(6000)
    assert shifted.outside_volume_mm3 == pytest.approx(0, abs=1e-6)
    saved = normalize_target(rotated)
    assert math.hypot(*saved["frame"]["axis"]) == pytest.approx(1)
    assert normalize_target(saved) == saved  # ukládání nesmí směry opakovaně měnit
    assert rotated["frame"]["axis"] == [2, 2, 0]  # vstupní data se nemění


def test_concave_profile_and_reversed_order_have_the_same_volume(material):
    profile = [[0, 0], [10, 0], [10, 4], [4, 4], [4, 10], [0, 10]]
    for polygon in (profile, profile[::-1], profile + [profile[0]]):
        result = resolve_target(material, volume_target(profile_mm=polygon))
        assert result.volume_mm3 == pytest.approx((100 - 36) * 20)


def test_generic_volume_is_clipped_to_material_and_empty_intersection_is_error(material):
    target = volume_target(frame={"origin": [0, 0, 90], "axis": [0, 1, 0],
                                  "across": [1, 0, 0]})
    result = resolve_target(material, target)
    assert result.requested_volume_mm3 == pytest.approx(6000)
    assert result.volume_mm3 == pytest.approx(2000)
    assert result.outside_volume_mm3 == pytest.approx(4000)
    for z in (100, 150):
        target["frame"]["origin"][2] = z
        with pytest.raises(TargetError, match="žádný společný objem"):
            resolve_target(material, target)


def test_nominal_v_weld_matches_analytic_volume_in_reference_part():
    part = rebuild(Document.load(EXAMPLES / "ndt/tupy_svar.json")).part
    before = part.volume
    result = resolve_target(part, v_target())
    expected = (2 * 12 + 12**2 * math.tan(math.radians(30))) * 100 + 3900
    assert result.requested_volume_mm3 == pytest.approx(expected)
    assert result.volume_mm3 == pytest.approx(14613.84387633061)
    assert result.outside_volume_mm3 == pytest.approx(0, abs=1e-6)
    assert part.volume == before == pytest.approx(363900)
    assert len(result.requested.solids()) == 1
    target = v_target()
    target["frame"]["origin"][0] = 150
    with pytest.raises(TargetError, match="není celý v materiálu"):
        resolve_target(part, target)


def test_v_without_root_gap_and_caps_is_a_triangle(material):
    target = v_target(dimensions={"thickness_mm": 12, "angle_deg": 60, "root_gap_mm": 0},
                      frame=volume_target()["frame"], length_mm=20)
    result = resolve_target(material, target)
    assert result.volume_mm3 == pytest.approx(12**2 * math.tan(math.radians(30)) * 20)


def test_two_fillet_welds_have_correct_sides_and_independent_volumes():
    part = rebuild(Document.load(EXAMPLES / "ndt/koutovy_svar.json")).part
    right, left = (resolve_target(part, fillet_target(side)) for side in (False, True))
    assert right.volume_mm3 == left.volume_mm3 == pytest.approx(2450)
    assert right.shape.bounding_box().min.X == pytest.approx(5)
    assert left.shape.bounding_box().max.X == pytest.approx(-5)
    assert (right.shape & left.shape).volume == pytest.approx(0)
    assert part.volume == pytest.approx(284900)


@pytest.mark.parametrize("patch", [
    {"length_mm": 0}, {"length_mm": -1}, {"length_mm": True},
    {"length_mm": float("inf")}, {"length_mm": float("nan")}, {"length_mm": "20"},
    {"length_mm": 1e7}, {"unknown": 1}, {"kind": "guess"},
    {"profile_mm": [[0, 0], [1, 0], [2, 0]]},
    {"profile_mm": [[0, 0], [1, 1], [0, 1], [1, 0]]},
    {"profile_mm": [[0, 0], [1, 0], [1, 0], [0, 1]]},
    {"profile_mm": [[0, 0], [2, 0], [1, 0], [0, 1]]},
    {"profile_mm": [[0, 0], [1, 0], [0, 1], [0, 0], [-1, 0]]},
    {"profile_mm": [[0, 0], [1, 0], [0, float("nan")]]},
    {"profile_mm": [[0, 0], [1, 0], [False, 1]]},
    {"profile_mm": [[0, 0]] * 258},
    {"frame": {"origin": [0, 0, 0], "axis": [0, 0, 0], "across": [1, 0, 0]}},
    {"frame": {"origin": [0, 0, 0], "axis": [0, 1, 0], "across": [1, 1, 0]}},
    {"frame": {"origin": [0, 0], "axis": [0, 1, 0], "across": [1, 0, 0]}},
])
def test_invalid_targets_fail_before_geometry(patch):
    with pytest.raises(TargetError):
        normalize_target(volume_target(**patch))


@pytest.mark.parametrize("patch", [
    {"angle_deg": 180}, {"angle_deg": 0}, {"root_gap_mm": -1}, {"thickness_mm": False},
    {"cap_height_mm": 0}, {"cap_width_mm": 0}, {"root_tip_width_mm": -1}, {"guess": 1},
])
def test_bad_weld_dimensions_are_rejected(patch):
    target = v_target()
    target["dimensions"].update(patch)
    with pytest.raises(TargetError):
        normalize_target(target)


def test_no_competing_profile_or_unknown_weld_type_is_silently_accepted():
    for patch in ({"profile_mm": [[0, 0], [1, 0], [0, 1]]}, {"weld_type": "circumferential"}):
        with pytest.raises(TargetError):
            normalize_target(v_target(**patch))


def test_resolve_does_not_modify_the_saved_recipe(material):
    target = volume_target()
    before = copy.deepcopy(target)
    resolve_target(material, target)
    assert target == before
