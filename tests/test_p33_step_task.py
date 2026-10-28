"""Životní cyklus izolovaného průzkumného procesu STEP."""
import time
from pathlib import Path

from skodacad.step_task import StepTask

SOURCE = Path(__file__).parent / "fixtures" / "step" / "01-jedno-teleso.step"


def wait(task):
    for _ in range(500):
        result = task.poll()
        if result is not None:
            return result
        time.sleep(0.02)
    task.cancel()
    raise AssertionError("Proces nedokončil kontrolu")


def test_valid_step_in_child():
    task = StepTask(SOURCE.read_bytes())
    try:
        result = wait(task)
        assert not result.error
        assert result.facts.solids == 1
        assert result.facts.volume_mm3 == 24000
        from skodacad.worker import _shape_from

        restored = _shape_from(("Part", result.shape_bytes))
        assert len(restored.solids()) == 1
        assert restored.volume == 24000
    finally:
        task.cancel()


def test_timeout_stops_process():
    task = StepTask(SOURCE.read_bytes(), timeout=0.001)
    time.sleep(0.02)
    outcome = wait(task)
    assert "časový limit" in outcome.error
    assert task._stopped.wait(5)
    assert not task._process.is_alive()


def test_cancel_stops_process():
    task = StepTask(SOURCE.read_bytes())
    task.cancel()
    assert not task._process.is_alive()
    assert task.poll() is None


def test_memory_limit_stops_process(monkeypatch):
    monkeypatch.setattr("skodacad.step_task._resident_bytes", lambda _: 1024)
    task = StepTask(SOURCE.read_bytes(), max_rss=1)
    outcome = wait(task)
    assert "limit paměti" in outcome.error
    assert task._stopped.wait(5)
    assert not task._process.is_alive()


def test_reported_repair_is_rejected_in_child():
    path = Path(__file__).parent / "fixtures" / "step-p33" / "obracena-plocha.step"
    task = StepTask(path.read_bytes())
    try:
        outcome = wait(task)
        assert outcome.facts is None
        assert "oprava" in outcome.error
    finally:
        task.cancel()


def test_limits_enforced_without_polling(monkeypatch):
    monkeypatch.setattr("skodacad.step_task._resident_bytes", lambda _: 1024)
    task = StepTask(SOURCE.read_bytes(), max_rss=1)
    assert task._done.wait(5)
    assert task._stopped.wait(5)
    assert not task._process.is_alive()
    assert "limit paměti" in task.poll().error


def test_memory_monitor_exception_stops_process(monkeypatch):
    def fail(_pid):
        raise RuntimeError("neočekávaná chyba měření")

    monkeypatch.setattr("skodacad.step_task._resident_bytes", fail)
    task = StepTask(SOURCE.read_bytes())
    outcome = wait(task)
    assert "ověřit využití paměti" in outcome.error
    assert task._stopped.wait(5)
    assert not task._process.is_alive()


def test_existing_worker_guard_kills_step_without_polling(monkeypatch):
    from skodacad.worker import BackgroundRebuilder

    monkeypatch.setattr("skodacad.step_task._resident_bytes", lambda _pid: 2**31)
    runner = BackgroundRebuilder()
    worker = runner._idle[0]
    try:
        worker.step_phase.set()
        deadline = time.monotonic() + 5
        while not worker.limit_error and time.monotonic() < deadline:
            time.sleep(0.02)
        assert "limit paměti" in worker.limit_error
        worker.process.join(timeout=3)
        assert not worker.process.is_alive()
    finally:
        runner.close()


def test_file_is_read_inside_controlled_process(tmp_path):
    path = tmp_path / "source.step"
    original = SOURCE.read_bytes()
    path.write_bytes(original)
    task = StepTask(path)
    try:
        result = wait(task)
        assert not result.error
        assert result.source_bytes == original
        assert result.facts.size_bytes == len(original)
    finally:
        task.cancel()


def test_missing_file_reports_error_in_child(tmp_path):
    task = StepTask(tmp_path / "neexistuje.step")
    try:
        result = wait(task)
        assert result.facts is None
        assert "nelze přečíst" in result.error
    finally:
        task.cancel()
