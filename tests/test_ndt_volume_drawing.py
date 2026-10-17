"""07C.3: kresba objemového pokrytí – povrch cíle a průřez obarvené podle buněk 07B.

Plochy kresby se porovnávají s rozměry cíle (povrch kvádru, průřez), šedá „nerozlišeno
v kresbě“ nesmí nikdy nahradit zelenou a řez nesmí změnit čísla výsledku."""

import dataclasses
import math

import pytest

from conftest import EXAMPLES, face_at
from skodacad.ndt.coverage import COLORS
from skodacad.ndt.volume_coverage import VolumeSample
from skodacad.ndt.volume_drawing import GREY, UNRESOLVED, mesh_areas, state_at, volume_mesh
from skodacad.ndt.welds import resolve_target
from skodacad.session import ModelSession
from test_ndt_target_editor import volume_session

GREEN, RED = COLORS["covered"], COLORS["uncovered"]


def sample(lo, hi, piece=0):
    return VolumeSample((0, 0, 0), piece, ((0, 0, 0), (10, 10, 10)), None, 1.0, "", (lo, hi))


def test_state_lookup_uses_piece_bounds_and_never_guesses():
    left, right = sample((0, 0, 0), (4, 10, 10)), sample((6, 0, 0), (10, 10, 10), 1)
    assert state_at([(left, "uncovered")], (8, 5, 5)) == "uncovered"  # jediný kus
    pieces = [(left, "covered"), (right, "uncovered")]
    assert state_at(pieces, (2, 5, 5)) == "covered"
    assert state_at(pieces, (8, 5, 5)) == "uncovered"
    assert state_at(pieces, (5, 5, 5)) == UNRESOLVED  # mezi kusy
    overlapping = [(left, "covered"), (sample((3, 0, 0), (10, 10, 10), 1), "uncovered")]
    assert state_at(overlapping, (3.5, 5, 5)) == UNRESOLVED  # oba kvádry – nehádat
    same = [(left, "covered"), (dataclasses.replace(right, piece_bounds=None), "covered")]
    assert state_at(same, (5, 5, 5)) == "covered"  # stejný stav = jednoznačná barva
    unknown = [(dataclasses.replace(left, piece_bounds=None), "covered"),
               (dataclasses.replace(right, piece_bounds=None), "uncovered")]
    assert state_at(unknown, (2, 5, 5)) == UNRESOLVED


def test_fully_covered_box_is_green_and_drawing_area_equals_surface():
    session = volume_session()  # hranol 10 × 10 × 20 mm pod přímou sondou
    result = session.compute_ndt_coverage(step_mm=25, target_step_mm=5)
    assert all(s.piece_bounds == s.bounds for s in result.samples)  # krychle = celá buňka
    areas = mesh_areas(session.visible_ndt_coverage())
    assert areas == {GREEN: pytest.approx(2 * (10 * 10 + 10 * 20 + 10 * 20))}


def test_states_are_drawn_per_cell_band():
    session = volume_session()
    result = session.compute_ndt_coverage(step_mm=25, target_step_mm=5)
    for i, item in enumerate(result.samples):  # první vrstva podél osy (0 … 5 mm) nepokrytá
        if item.cell[2] == 0:
            result.states[i] = "uncovered"
    shape = resolve_target(session.result.part, result.assumptions["target"]).shape
    areas = mesh_areas(volume_mesh(result, shape))
    # čelo 10 × 10 + čtyři pásy 10 × 5 mm = 300 mm² červeně, zbytek povrchu zeleně
    assert areas[RED] == pytest.approx(10 * 10 + 4 * 10 * 5)
    assert areas[GREEN] == pytest.approx(1000 - 300)


def test_section_through_target_colours_the_cross_section_without_changing_numbers():
    session = volume_session()
    result = session.compute_ndt_coverage(step_mm=25, target_step_mm=5)
    percent = result.percent("covered")
    session.set_section_target(session.ndt_study("s1")["target"])
    assert session.section_range() == (0.0, 20.0)
    assert session.section_settings.position == 10.0
    assert session.section_plane.origin == (0.0, 10.0, 0.0)
    assert session.section_plane.normal == (0.0, -1.0, 0.0)  # k pozorovateli v izometrii
    assert mesh_areas(session.visible_ndt_coverage()) == {GREEN: pytest.approx(600)}
    session.set_section_position(5)  # zbude 10 × 10 × 15 mm
    assert session.section_settings.target is not None  # posun drží druh řezu
    assert mesh_areas(session.visible_ndt_coverage()) == {GREEN: pytest.approx(800)}
    session.flip_section()  # z druhé strany zbude 10 × 10 × 5 mm
    assert session.section_plane.normal == (0.0, 1.0, 0.0)
    assert mesh_areas(session.visible_ndt_coverage()) == {GREEN: pytest.approx(400)}
    assert session.ndt_coverage is result and result.percent("covered") == percent
    session.clear_section()
    assert mesh_areas(session.visible_ndt_coverage()) == {GREEN: pytest.approx(1000)}


def test_cell_with_two_pieces_around_hole_is_resolved_by_piece_bounds():
    from skodacad.ndt.devices import Probe

    session = ModelSession()
    session.open(EXAMPLES / "ndt" / "otvor.json")  # deska 200 × 100 × 20, otvor Ø 20 uprostřed
    across = {"kind": "volume", "frame": {"origin": [0, -5, 0], "axis": [0, 1, 0],
                                          "across": [1, 0, 0]},
              "length_mm": 10, "profile_mm": [[-15, 5], [15, 5], [15, 15], [-15, 15]]}
    session.set_ndt_volume_target("s1", across)
    session.set_ndt_device("s1", Probe.straight(10))
    session.place_ndt_probe("s1", [face_at(session.result.part, 50, 0, 20).wrapped], (50, 0, 20))
    result = session.compute_ndt_coverage(step_mm=25, target_step_mm=30)
    assert len(result.samples) == 2 and {s.cell for s in result.samples} == {(0, 0, 0)}
    left = min(range(2), key=lambda i: result.samples[i].piece_bounds[0][0])
    result.states[left], result.states[1 - left] = "covered", "uncovered"
    shape = resolve_target(session.result.part, result.assumptions["target"]).shape
    areas = mesh_areas(volume_mesh(result, shape))
    assert set(areas) == {GREEN, RED}  # žádná šedá
    assert areas[GREEN] == pytest.approx(areas[RED], rel=1e-3)  # kusy jsou souměrné
    assert areas[GREEN] + areas[RED] == pytest.approx(shape.area, rel=1e-3)
    for i in range(2):  # meze kusů neznámé → kresba nehádá, celá buňka šedě
        result.samples[i] = dataclasses.replace(result.samples[i], piece_bounds=None)
    areas = mesh_areas(volume_mesh(result, shape))
    assert set(areas) == {GREY} and areas[GREY] == pytest.approx(shape.area, rel=1e-3)
    assert math.isclose(sum(s.volume_mm3 for s in result.samples), result.total_volume,
                        rel_tol=1e-9)
