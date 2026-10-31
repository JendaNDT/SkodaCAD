"""CAD stěna: analytika, aktuální finální díl, nejistoty a přenos bez změny receptu."""

import copy
import math

import pytest
from build123d import Box, Pos

from conftest import EXAMPLES
from skodacad import Document, rebuild
from skodacad.document import DocumentError
from skodacad.loft_inspection import _sample, inspect_loft
from skodacad.ndt.geometry import PartGeometry
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder, Finished
from test_loft_wall_mode import rectangular_loft

EXAMPLE = EXAMPLES / "loft_stena.json"


@pytest.mark.parametrize("mode,expected", [("normal", 3), ("sections", 3 / math.sqrt(1 + 1/9))])
def test_cone_report_is_normal_length_and_does_not_change_geometry_or_recipe(mode, expected):
    doc = Document.load(EXAMPLE)
    doc.features[-1]["wall_mode"] = mode
    recipe = copy.deepcopy(doc.to_dict())
    result = rebuild(doc)
    part, volume = result.part, result.part.volume
    report = inspect_loft(doc, result, "prechod")
    assert len(report.samples) == 25 and not report.truncated
    assert report.requested == 3 and report.mode == mode
    assert report.lengths == pytest.approx([expected] * 25, abs=2e-5)
    assert report.counts["nominal" if mode == "normal" else "below"] == 25
    for sample in report.samples:
        assert math.dist(sample.point, sample.end) == pytest.approx(expected, abs=2e-5)
        assert math.dist((0, 0, 0), sample.direction) == pytest.approx(1)
    assert result.part is part and result.part.volume == volume and doc.to_dict() == recipe


@pytest.mark.parametrize("kind", ["straight", "inclined", "rounded"])
@pytest.mark.parametrize("mode", ["normal", "sections"])
def test_planar_and_rounded_reference_profiles(kind, mode):
    doc = rectangular_loft(kind, mode)
    report = inspect_loft(doc, rebuild(doc), "l")
    assert report.lengths
    expected = [3 / math.sqrt(1.25), 3 / math.sqrt(1.0625)] if (
        kind == "inclined" and mode == "sections") else [3]
    assert all(min(abs(value - e) for e in expected) < 2e-5 for value in report.lengths)
    assert report.counts["unknown"] == 0


def test_cylinder_and_legacy_hopper():
    doc = Document.load(EXAMPLE)
    doc.parameters["d"] = 80
    report = inspect_loft(doc, rebuild(doc), "prechod")
    assert report.lengths == pytest.approx([3] * 25, abs=2e-5)
    doc = Document.load(EXAMPLES / "vysypka.json")
    report = inspect_loft(doc, rebuild(doc), "vysypka")
    assert report.mode == "legacy" and "wall_mode" not in doc.features[-1]
    assert min(report.lengths) == pytest.approx(2.6088026446, abs=2e-5)
    assert max(report.lengths) == pytest.approx(2.7692307692, abs=2e-5)
    assert report.counts == {"below": 120, "nominal": 0, "longer": 0, "unknown": 5}
    assert all(s.length is None and s.end is None and "hran" in s.reason
               for s in report.samples if s.status == "unknown")


def test_report_measures_final_model_after_a_cut():
    doc = rectangular_loft("straight", "normal")
    # Odebrání vnitřku od x=38: původní stěna 3 mm na +X má nyní 2 mm.
    doc.features += [
        {"id": "cut_s", "type": "sketch", "plane": "XY", "offset": 5,
         "elements": [{"shape": "rectangle", "width": 76, "height": 44}]},
        {"id": "cut", "type": "extrude", "sketch": "cut_s", "distance": 20,
         "operation": "cut"},
    ]
    result = rebuild(doc)
    assert result.ok, result.first_error
    report = inspect_loft(doc, result, "l")
    assert min(report.lengths) == pytest.approx(2, abs=2e-5)
    assert max(report.lengths) == pytest.approx(3, abs=2e-5)
    assert report.counts["below"] > 0


def test_removed_or_covered_source_points_are_unknown_and_longer_paths_are_reported():
    geometry = PartGeometry(Pos(0, 0, 5) * Box(20, 20, 10))
    exact = _sample(geometry, (10, 0, 5), (-1, 0, 0), 20)
    assert exact.length == pytest.approx(20) and exact.status == "nominal"
    assert _sample(geometry, (10, 0, 5), (-1, 0, 0), 3).status == "longer"
    for point in [(9, 0, 5), (11, 0, 5), (10, 10, 5)]:
        sample = _sample(geometry, point, (-1, 0, 0), 3)
        assert sample.status == "unknown" and sample.length is None and sample.reason


def test_sample_limit_and_trimmed_coverage_are_explicit(monkeypatch):
    import skodacad.loft_inspection as module

    monkeypatch.setattr(module, "MAX_SAMPLES", 7)
    doc = Document.load(EXAMPLE)
    report = inspect_loft(doc, rebuild(doc), "prechod")
    assert report.truncated and len(report.samples) == 7


def test_missing_wall_incomplete_and_stale_model_are_refused():
    doc = Document.load(EXAMPLE)
    result = rebuild(doc)
    with pytest.raises(DocumentError, match="dutý přechod"):
        inspect_loft(doc, result, "missing")
    doc.features[-1].pop("wall")
    with pytest.raises(DocumentError, match="aktuální"):
        inspect_loft(doc, result, "prechod")
    with pytest.raises(DocumentError, match="kladnou"):
        inspect_loft(doc, rebuild(doc), "prechod")
    doc.features[-1]["wall"] = 50
    with pytest.raises(DocumentError):
        inspect_loft(doc, rebuild(doc), "prechod")


def test_session_invalidation_history_save_and_overlay(tmp_path):
    session = ModelSession()
    session.open(EXAMPLE)
    result, recipe = session.result, copy.deepcopy(session.document.to_dict())
    report = session.inspect_loft_wall("prechod")
    assert session.loft_wall_report("prechod") is report
    assert not session.dirty and not session.can_undo
    assert session.result is result and session.document.to_dict() == recipe
    line, = session.loft_wall_measurement("prechod", 0)
    assert (line[0] - line[1]).length == pytest.approx(3)
    assert session.loft_wall_measurement("prechod", -1) == []
    session.set_parameter("stena", "2")
    assert session.loft_wall_report("prechod") is None
    session.inspect_loft_wall("prechod")
    session.undo()
    assert session.loft_wall_report("prechod") is None
    session.redo()
    assert session.loft_wall_report("prechod") is None
    session.inspect_loft_wall("prechod")
    session.save(tmp_path / "model.json")
    assert session.document.to_dict()["version"] == 33
    session.open(tmp_path / "model.json")
    assert session.loft_wall_report("prechod") is None


def test_worker_report_transfer_and_cancel_without_geometry_replacement():
    runner = BackgroundRebuilder()
    try:
        session = ModelSession(runner)
        session.open(EXAMPLE)
        assert session.wait(30)
        result = session.result
        session.inspect_loft_wall("prechod")
        assert session.loft_wall_pending and not session.loft_wall_available("prechod")
        assert session.wait(30) and not session.failure
        assert session.loft_wall_report("prechod").lengths == pytest.approx([3] * 25, abs=2e-5)
        assert session.result is result and not session.dirty and not session.can_undo
        session.inspect_loft_wall("prechod")
        assert session.cancel() and not session.computing
        assert session.result is result and not session.dirty and not session.can_undo
        assert "zastaveno" in session.loft_wall_problem("prechod")
        session.inspect_loft_wall("prechod")
        session.set_parameter("stena", "2")
        assert session.wait(30)
        assert session.loft_wall_report("prechod") is None
        assert session.result.part.volume < result.part.volume
    finally:
        runner.close()


def test_late_report_from_previous_job_and_worker_error():
    class Runner:
        started = 0
        job = 0
        finished = None

        def submit(self, *_a, **_kw):
            self.job += 1
            return self.job

        submit_loft_wall = submit

        def poll(self):
            value, self.finished = self.finished, None
            return value

    runner = Runner()
    session = ModelSession()
    session.open(EXAMPLE)
    report = session.inspect_loft_wall("prechod")
    session._runner = runner
    session.inspect_loft_wall("prechod")
    old_job = session._job
    session.rebuild()
    runner.finished = Finished(old_job, loft_wall=report)
    assert not session.poll() and session.computing
    runner.finished = Finished(session._job, result=session.result)
    assert session.poll() and session.loft_wall_report("prechod") is None
    session.inspect_loft_wall("prechod")
    runner.finished = Finished(session._job, error="Simulovaná chyba měření.")
    assert session.poll() and not session.loft_wall_pending
    assert session.loft_wall_report("prechod") is None
    assert session.loft_wall_available("prechod")
    assert "Simulovaná" in session.loft_wall_problem("prechod")


def test_later_cut_removes_source_points_instead_of_inventing_zero_wall():
    doc = rectangular_loft("straight", "normal")
    doc.features += [
        {"id": "s_cut", "type": "sketch", "plane": "XY", "offset": 15,
         "elements": [{"shape": "rectangle", "width": 100, "height": 100}]},
        {"id": "cut", "type": "extrude", "sketch": "s_cut", "distance": 30,
         "operation": "cut"}]
    result = rebuild(doc)
    assert result.ok, result.first_error
    report = inspect_loft(doc, result, "l")
    assert report.counts["unknown"] > 0
    assert report.lengths == pytest.approx([3] * len(report.lengths), abs=2e-5)
    assert all(s.length is None for s in report.samples if s.status == "unknown")
