"""07C.1: podklady editoru cílového objemu – objem ze vzorce, směry, kontrola v dílu bez
změny modelu, pomůcka z rovné hrany a náhled cíle ve 3D (i v řezu)."""

import math

import pytest

from conftest import EXAMPLES, edge_at, face_at
from skodacad import DocumentError
from skodacad.ndt.welds import (
    DIRECTIONS,
    direction_name,
    height_direction,
    nominal_volume,
    section_area,
    target_profiles,
)
from skodacad.session import ModelSession
from test_ndt_welds import fillet_target, v_target, volume_target

V_BODY = (2 * 12 + 12**2 * math.tan(math.radians(30))) * 100  # tělo V svaru [mm³]
V_TOTAL = V_BODY + (20 + 14) / 2 * 2 * 100 + (6 + 4) / 2 * 1 * 100  # + převýšení, podkořen


def opened(path):
    session = ModelSession()
    session.open(EXAMPLES / "ndt" / path)
    return session


def test_nominal_volume_matches_analytic_formulas():
    assert V_TOTAL == pytest.approx(14_613.843876, abs=1e-6)
    assert nominal_volume(v_target()) == pytest.approx(V_TOTAL, rel=1e-12)
    assert nominal_volume(fillet_target()) == pytest.approx(7 * 7 / 2 * 100)
    assert nominal_volume(volume_target()) == pytest.approx(10 * 30 * 20)
    # tělo, převýšení a podkořen jsou tři polygony, které se dotýkají jen hranou
    assert len(target_profiles(v_target())) == 3
    assert section_area(target_profiles(v_target())) == pytest.approx(V_TOTAL / 100)
    bare = v_target(dimensions={"thickness_mm": 12, "angle_deg": 60, "root_gap_mm": 2})
    assert nominal_volume(bare) == pytest.approx(V_BODY)


def test_direction_names_and_height_rule():
    assert direction_name([0, 3, 0]) == "+Y" and direction_name([0, 0, -1]) == "-Z"
    assert direction_name([0.6, 0.8, 0]) is None and direction_name([0, 0, 0]) is None
    assert height_direction(DIRECTIONS["+Y"], DIRECTIONS["+X"]) == (0, 0, 1)  # napříč × osa
    assert height_direction(DIRECTIONS["-Y"], DIRECTIONS["-X"]) == (0, 0, 1)  # levý koutový


def test_outline_validates_without_part():
    saved, profiles, volume = ModelSession.ndt_target_outline(fillet_target())
    assert saved["frame"]["axis"] == [0.0, 1.0, 0.0] and volume == pytest.approx(2450)
    assert profiles == [[[0, 0], [7.0, 0], [0, 7.0]]]
    with pytest.raises(DocumentError, match="kolmé"):
        ModelSession.ndt_target_outline(volume_target(frame={
            "origin": [0, 0, 0], "axis": [0, 1, 0], "across": [0, 1, 0]}))
    with pytest.raises(DocumentError, match="protíná"):
        ModelSession.ndt_target_outline(volume_target(
            profile_mm=[[0, 0], [10, 10], [10, 0], [0, 10]]))


def test_check_in_part_does_not_change_model_and_explains_errors():
    session = opened("cilove_objemy/tupy_svar_objem.json")
    before, undo = session.document.to_dict(), len(session._undo)
    resolved = session.check_ndt_volume_target(v_target())
    assert resolved.volume_mm3 == pytest.approx(V_TOTAL)
    assert resolved.outside_volume_mm3 == pytest.approx(0, abs=1e-6)
    thick = v_target()
    thick["dimensions"]["thickness_mm"] = 20
    with pytest.raises(DocumentError, match="není celý v materiálu dílu – chybí"):
        session.check_ndt_volume_target(thick)
    away = volume_target(frame={"origin": [0, 0, 500], "axis": [0, 1, 0],
                                "across": [1, 0, 0]})
    with pytest.raises(DocumentError, match="nemá žádný společný objem"):
        session.check_ndt_volume_target(away)
    assert session.document.to_dict() == before and len(session._undo) == undo
    assert not session.dirty


def test_frame_from_straight_edge_points_to_positive_coordinates():
    session = opened("cilove_objemy/tupy_svar_objem.json")
    part = session.result.part
    edge = edge_at(part, 10, 0, 12)  # okraj převýšení podél svaru
    frame = session.ndt_frame_from_edge([edge.wrapped])
    assert frame == {"origin": [10.0, -50.0, 12.0], "axis": [0.0, 1.0, 0.0],
                     "length_mm": 100.0}
    with pytest.raises(DocumentError, match="rovnou hranu"):
        session.ndt_frame_from_edge([face_at(part, 50, 0, 12).wrapped])
    with pytest.raises(DocumentError, match="rovnou hranu"):
        session.ndt_frame_from_edge([])


def test_preview_is_effective_target_cut_by_section_and_cached():
    session = opened("cilove_objemy/tupy_svar_objem.json")
    body, outline = session.ndt_target_preview("s1")
    assert body.volume == pytest.approx(V_TOTAL) and outline is None  # svar je celý v dílu
    assert session.ndt_target_preview("s1")[0] is body  # znovu se nepočítá
    session.set_section_axis("Y", 0)
    half, _ = session.ndt_target_preview("s1")
    assert half.volume == pytest.approx(V_TOTAL / 2)
    session.set_section_axis("Y", 80)  # řez mimo svar; výchozí strana (−Y) ho odřízne celý
    assert session.ndt_target_preview("s1") is None
    session.flip_section()  # … z druhé strany zůstane celý
    assert session.ndt_target_preview("s1")[0].volume == pytest.approx(V_TOTAL)
    session.clear_section()
    assert session.ndt_target_preview(None) is None


def test_preview_outline_only_when_prism_sticks_out_and_none_for_faces():
    session = opened("deska.json")
    assert session.ndt_target_preview("s1") is None  # plochy – náhled objemu není
    sticking = volume_target(frame={"origin": [0, 0, 10], "axis": [0, 1, 0],
                                    "across": [1, 0, 0]})  # hranol 10 × 30 výšky, deska 20 mm
    session.set_ndt_volume_target("s1", sticking)
    body, outline = session.ndt_target_preview("s1")
    assert body.volume == pytest.approx(10 * 10 * 20)  # jen z = 10 … 20 je materiál
    assert outline.volume == pytest.approx(10 * 30 * 20)
    assert session.ndt_target_preview("neni") is None
