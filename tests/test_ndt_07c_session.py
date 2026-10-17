"""07C: atomický návrh cíle, nezávislost pohledu a skutečné střídání procesů."""

import copy

import pytest

from skodacad import DocumentError
from skodacad.section import SectionPlane
from skodacad.worker import BackgroundRebuilder
from test_ndt_session import coverage_session
from test_ndt_volume_session import opened, target


def small_target():
    saved = target()
    saved["length_mm"] = 10
    return saved


def test_preview_cancel_then_atomic_apply_and_noop_preserve_history_and_geometry():
    session = opened()
    before, history, part = session.document.to_dict(), len(session._undo), session.result.part
    session.start_ndt_target_preview(small_target())
    assert session.ndt_target_preview[2]["numbers"]["volume_mm3"] == pytest.approx(1000)
    assert session.document.to_dict() == before and len(session._undo) == history
    session.cancel_ndt_preview()
    assert session.document.to_dict() == before
    session.start_ndt_target_preview(small_target())
    sid = session.apply_ndt_target_preview()
    assert sid == "s2" and session.ndt_studies[1].state == "ok"
    assert session.result.part is part and len(session._undo) == history + 1
    applied = session.document.to_dict()
    session.start_ndt_target_preview(session.ndt_study(sid)["target"], sid)
    session.apply_ndt_target_preview()
    assert session.document.to_dict() == applied and len(session._undo) == history + 1
    session.undo()
    assert session.document.to_dict() == before
    session.redo()
    assert session.document.to_dict() == applied


def test_preview_does_not_confirm_stale_or_verified_and_rejects_old_document():
    session = opened()
    session.set_ndt_volume_target("s1", small_target())
    session.verify_ndt_study("s1", "Technik")
    session.start_ndt_target_preview(small_target(), "s1")
    session.apply_ndt_target_preview()
    assert "verified" in session.ndt_study("s1")  # beze změny opravdu nic neruší
    session.set_parameter("t", "22")
    session.start_ndt_target_preview(small_target() | {"length_mm": 8}, "s1")
    session.apply_ndt_target_preview()
    assert session.ndt_studies[0].state == "stale"
    assert "verified" not in session.ndt_study("s1")
    session.start_ndt_target_preview(small_target(), "s1")
    session.rename_ndt_study("s1", "Nový název")
    with pytest.raises(DocumentError, match="znovu ověř"):
        session.apply_ndt_target_preview()


def test_volume_section_changes_only_drawing_and_convergence_keeps_fine_map(tmp_path):
    session = coverage_session()
    session.set_ndt_volume_target("s1", small_target())
    settings = dict(mode="face", step_mm=25, target_step_mm=5, tolerance_mm=None,
                    length_mm=50, spread_deg=0)
    result = session.compute_ndt_coverage(**settings, capture_display=True)
    doc, undo = session.document.to_dict(), len(session._undo)
    states, source = list(result.states), session._volume_source
    session.set_section_target("s1")
    assert session.section_range() == (0, 10)
    assert session.section_plane == SectionPlane((0, 5, 0), (0, 1, 0))
    session.request_ndt_volume_view()
    assert session.visible_ndt_coverage()[1]
    assert session._volume_view.area_mm2 == pytest.approx(100)
    session.flip_section()
    session.request_ndt_volume_view()
    assert session._volume_view.area_mm2 == pytest.approx(100)
    session.set_section_position(15)
    assert not session.visible_ndt_coverage()[1]  # starý řez okamžitě zmizí
    session.request_ndt_volume_view()
    assert "neprotíná" in session.ndt_volume_view_message
    session.start_ndt_convergence(**settings)
    assert session.ndt_coverage is result and result.states == states
    assert session._volume_source is source
    assert "convergence" in result.assumptions
    assert result.assumptions["convergence"]["tolerance_mm"] == result.assumptions["tolerance_mm"]
    assert session.document.to_dict() == doc and len(session._undo) == undo
    session.export_ndt_coverage(tmp_path / "prurez.csv")
    session.set_ndt_volume_target("s1", small_target() | {"length_mm": 8})
    assert session.ndt_coverage is None and session._volume_source is None


def test_deleted_target_disables_target_section_with_reason():
    session = opened()
    session.set_ndt_volume_target("s1", small_target())
    session.set_section_target("s1")
    session.remove_ndt_study("s1")
    assert session.section_plane is None and session.section_settings is None
    assert "Řez cílem byl vypnut" in session.presentation_error


def test_background_capture_does_not_change_numeric_volume_results():
    session = coverage_session()
    session.set_ndt_volume_target("s1", small_target())
    plain = session.compute_ndt_coverage(step_mm=25, target_step_mm=5)
    drawn = session.compute_ndt_coverage(step_mm=25, target_step_mm=5, capture_display=True)
    assert plain.samples == drawn.samples and plain.states == drawn.states
    assert plain.hits == drawn.hits and plain.total_volume == drawn.total_volume
    assert session._volume_source.samples == len(drawn.samples)
    session.turn_ndt_probe(90)
    assert session.ndt_coverage is None and session._volume_source is None


def test_worker_preview_slice_cancel_crash_and_new_process_keep_numeric_map():
    runner = BackgroundRebuilder()
    try:
        session = coverage_session(runner)
        session.start_ndt_target_preview(small_target(), "s1")
        assert session.wait(60) and session.ndt_target_preview
        session.apply_ndt_target_preview()
        before = copy.deepcopy(session.document.to_dict())
        session.start_ndt_coverage(step_mm=25, target_step_mm=5, capture_display=True)
        coverage_pid = runner._active.process.pid
        assert session.wait(60) and not session.failure
        result = session.ndt_coverage
        source = session._volume_source
        assert result.total_volume == pytest.approx(1000) and source.pieces
        session.set_section_target("s1")
        session.request_ndt_volume_view()
        assert runner._active.process.pid != coverage_pid
        assert session.wait(60) and session.visible_ndt_coverage()[1]
        session.set_section_position(2)
        session.request_ndt_volume_view()
        runner._active.process.kill()
        assert session.wait(15)
        assert session.ndt_coverage is result and session._volume_source is source
        assert not session.visible_ndt_coverage()[1] and "spadl" in session.presentation_error
        session.set_section_position(3)
        session.request_ndt_volume_view()
        session.cancel()
        assert session.ndt_coverage is result and session.document.to_dict() == before
        assert "zastaven" in session.ndt_volume_view_message
        session.set_section_position(4)
        session.request_ndt_volume_view()
        assert session.wait(60) and session.visible_ndt_coverage()[1]
        # Pozdní odpověď jiné roviny se nesmí kreslit.
        old = session._volume_view
        pending = ("slice", before, (id(result), session.section_plane))
        session.set_section_position(6)
        session._accept_presentation(pending, old, "")
        assert not session.visible_ndt_coverage()[1]
        session.request_ndt_volume_view()
        session.clear_section()
        assert not session.computing and session.ndt_coverage is result
        session.set_section_target("s1")
        session.request_ndt_volume_view()
        assert session.wait(60) and session.visible_ndt_coverage()[1]
    finally:
        runner.close()
