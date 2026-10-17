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


# --- 07C.2: odhad, citlivost na krok a výpočet na pozadí -----------------------------------


def volume_session():
    from test_ndt_session import coverage_session
    from test_ndt_volume_session import target

    session = coverage_session()  # deska, přímá sonda Ø10 přiložená shora uprostřed
    session.set_ndt_volume_target("s1", target())  # hranol 10 × 10 × 20 mm = 2000 mm³
    return session


def test_estimate_counts_cells_and_positions_and_refuses_what_compute_would_refuse():
    from skodacad.ndt.coverage import _scan_positions

    session = volume_session()
    estimate = session.ndt_coverage_estimate(step_mm=25, target_step_mm=5)
    positions = len(_scan_positions(session.ndt_placement, "face", 25, 50))
    assert (estimate.cells, estimate.positions, estimate.ok) == (2 * 2 * 4, positions, True)
    assert estimate.legs == session.ndt_beam.bounces + 1
    assert estimate.text == f"Odhad: 16 buněk cíle, {positions} poloh sondy."
    assert "hrubší běh" in session.ndt_coverage_estimate(step_mm=25, target_step_mm=5,
                                                         convergence=True).text
    fine = session.ndt_coverage_estimate(step_mm=25, target_step_mm=0.3)
    assert not fine.ok and fine.cells == 34 * 34 * 67 and "příliš jemný" in fine.text
    with pytest.raises(DocumentError, match="příliš jemná"):  # stejná ochrana jako výpočet
        session.compute_ndt_coverage(step_mm=25, target_step_mm=0.3)
    crowded = session.ndt_coverage_estimate(step_mm=0.5, target_step_mm=5)
    assert not crowded.ok and "příliš mnoho poloh" in crowded.text
    line = session.ndt_coverage_estimate(mode="line", step_mm=5, target_step_mm=5)
    assert not line.ok and "nevymezuje pokrytý objem" in line.text
    assert session.ndt_coverage_estimate(mode="line", spread_deg=5, step_mm=5,
                                         target_step_mm=5).ok


def test_estimate_is_only_for_volume_targets():
    from test_ndt_session import coverage_session

    with pytest.raises(DocumentError, match="jen pro objemový cíl"):
        coverage_session().ndt_coverage_estimate()


def test_session_convergence_matches_direct_comparison_and_is_reported():
    from skodacad.ndt.volume_coverage import check_volume_convergence

    session = volume_session()
    plain = session.compute_ndt_coverage(step_mm=25, target_step_mm=5)
    assert "Citlivost na krok neověřena." in plain.summary()
    result = session.compute_ndt_coverage(step_mm=25, target_step_mm=5, convergence=True)
    found = result.assumptions["convergence"]
    assert found["fine_steps_mm"] == (25.0, 5.0) and found["coarse_steps_mm"] == (50.0, 10.0)
    assert found["tolerance_mm"] == pytest.approx(25 * math.sqrt(0.5))  # z jemného běhu
    direct = check_volume_convergence(
        session._ndt_geometry(), session.ndt_placement, target=session.ndt_study("s1")["target"],
        mode="face", scan_step=25, target_step=5, angle_deg=session.ndt_placement_request[2])
    assert found["delta_pp"] == pytest.approx(direct.delta_pct)
    assert found["fine_pct"] == pytest.approx(direct.fine)
    assert any(line.startswith("Citlivost na krok: největší rozdíl")
               for line in result.summary())
    assert result.total_volume == pytest.approx(2000)
    assert math.fsum(result.volume(s) for s in ("covered", "uncovered", "uncertain")) \
        == pytest.approx(2000)


def test_failed_comparison_keeps_fine_result_but_never_claims_stability(monkeypatch):
    import skodacad.session as module
    from skodacad.ndt.coverage import CoverageError

    def broken(*args, **kwargs):
        raise CoverageError("hrubší běh selhal")

    monkeypatch.setattr(module, "check_volume_convergence", broken)
    result = volume_session().compute_ndt_coverage(step_mm=25, target_step_mm=5,
                                                   convergence=True)
    assert "convergence" not in result.assumptions
    assert "Citlivost na krok se nepodařilo ověřit: hrubší běh selhal" in result.summary()


def test_background_coverage_with_convergence_matches_synchronous():
    from skodacad.worker import BackgroundRebuilder
    from test_ndt_session import coverage_session
    from test_ndt_volume_session import target

    expected = volume_session().compute_ndt_coverage(step_mm=25, target_step_mm=5,
                                                     convergence=True)
    runner = BackgroundRebuilder()
    try:
        session = coverage_session(runner)
        session.set_ndt_volume_target("s1", target())
        assert session.wait(30)
        session.start_ndt_coverage(step_mm=25, target_step_mm=5, convergence=True)
        assert session.coverage_pending and session.ndt_coverage is None
        assert session.wait(60), session.failure
        assert not session.coverage_pending
        found = session.ndt_coverage.assumptions["convergence"]
        assert found == expected.assumptions["convergence"]
    finally:
        runner.close()
