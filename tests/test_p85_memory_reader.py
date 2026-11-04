"""Fresh current RSS, failed reads and the real macOS memory guard remain meaningful."""
import ctypes
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from skodacad import step_task


@pytest.mark.parametrize("returned", [0, -1, 1, 7])
def test_partial_or_failed_native_read_is_missing_not_zero(monkeypatch, returned):
    class Info(ctypes.Structure):
        _fields_ = [("resident_size", ctypes.c_uint64)]

    monkeypatch.setattr(step_task, "_macos_task_api", lambda: (lambda *_: returned, Info))
    assert step_task._macos_resident_bytes(123) is None


def test_native_reader_uses_fresh_independent_buffers(monkeypatch):
    class Info(ctypes.Structure):
        _fields_ = [("resident_size", ctypes.c_uint64)]

    def read(pid, _flavor, _arg, pointer, size):
        pointer._obj.resident_size = pid * 1024
        return size

    monkeypatch.setattr(step_task, "_macos_task_api", lambda: (read, Info))
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(step_task._macos_resident_bytes, range(1, 100))) == [
            pid * 1024 for pid in range(1, 100)]
    assert step_task._macos_resident_bytes(0) == 0  # úplný záznam, odlišný od chybějícího


def test_unavailable_native_api_does_not_invent_memory(monkeypatch):
    def fail():
        raise OSError("unavailable")

    monkeypatch.setattr(step_task, "_macos_task_api", fail)
    assert step_task._macos_resident_bytes(123) is None


@pytest.mark.skipif(sys.platform != "darwin", reason="Actual macOS libproc and ps reference")
def test_native_rss_matches_independent_ps_and_reads_without_starting_a_process(monkeypatch):
    child = subprocess.Popen([sys.executable, "-u", "-c",
        'import sys; a=bytearray(64*1024*1024); print("ready", flush=True); sys.stdin.read(1)'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        reference = int(subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(child.pid)], text=True).strip()) * 1024
        reader, info_type = step_task._macos_task_api()
        assert callable(reader) and ctypes.sizeof(info_type) == 96
        assert info_type.resident_size.offset == 8

        def forbidden(*_args, **_kwargs):
            raise AssertionError("RSS read must not start ps or any helper process")

        with monkeypatch.context() as patch:
            patch.setattr(subprocess, "Popen", forbidden)
            samples = [step_task._resident_bytes(child.pid) for _ in range(10)]
        assert all(value is not None and value >= 64*1024**2
                   and abs(value - reference) <= 1024**2 for value in samples)
    finally:
        child.stdin.write("x")
        child.stdin.flush()
        child.wait(timeout=10)
    assert step_task._resident_bytes(child.pid) is None


@pytest.mark.skipif(sys.platform != "darwin", reason="Actual macOS RSS guard")
def test_real_native_memory_guard_rejects_one_byte_and_stops_owned_step():
    source = Path(__file__).parent / "fixtures/step/01-jedno-teleso.step"
    task = step_task.StepTask(source, max_rss=1)
    try:
        assert task._done.wait(10) and task._stopped.wait(10)
        assert not task._process.is_alive()
        outcome = task.poll()
        assert outcome is not None and "limit paměti" in outcome.error
    finally:
        task.cancel()
