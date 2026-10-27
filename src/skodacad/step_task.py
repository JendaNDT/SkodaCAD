"""Izolovaný experiment P3.3: zrušitelná diagnostika STEP bez Qt."""
from __future__ import annotations

import io
import multiprocessing
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skodacad.step_probe import MAX_STEP_BYTES, StepFacts, StepProbeError

MAX_RSS = 1024 * 1024 * 1024
DEFAULT_TIMEOUT = 60.0


def _worker(conn: Any, source: bytes | Path) -> None:
    from build123d import Compound
    from OCP.BinTools import BinTools

    from skodacad.step_probe import _inspect_step
    from skodacad.step_source import read_source_file

    try:
        data = read_source_file(source) if isinstance(source, Path) else source
        facts, shape = _inspect_step(data)
        output = io.BytesIO()
        BinTools.Write_s(Compound([shape.solids()[0]]).wrapped, output)
        raw = output.getvalue()
        if len(raw) > 64 * 1024 * 1024:
            raise StepProbeError("Převedené těleso je příliš velké.")
        conn.send((True, (facts, raw, data if isinstance(source, Path) else None)))
    except Exception as exc:  # noqa: BLE001 -- pomocný proces musí vrátit chybu
        conn.send((False, str(exc) if isinstance(exc, StepProbeError)
                   else f"Kontrola STEP selhala ({type(exc).__name__})."))
    finally:
        conn.close()


def _resident_bytes(pid: int) -> int | None:
    """Aktuální fyzická paměť procesu; měření je kontrola, nikoliv pevný OS limit."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters),
                                               wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x1000 | 0x0010, False, pid)
        if not handle:
            return None
        try:
            data = Counters()
            data.cb = ctypes.sizeof(data)
            return data.WorkingSetSize if psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(data), data.cb) else None
        finally:
            kernel.CloseHandle(handle)
    if sys.platform == "darwin" or sys.platform.startswith("linux"):
        try:
            result = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True,
                                    text=True, timeout=2, check=True)
            return int(result.stdout.strip()) * 1024
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    return None


@dataclass(frozen=True)
class StepOutcome:
    facts: StepFacts | None = None
    shape_bytes: bytes | None = None
    source_bytes: bytes | None = None
    error: str = ""


class StepTask:
    """Kontrola a převzetí výsledku běží nezávisle na volání ``poll``."""

    def __init__(self, data: bytes | Path, timeout: float = DEFAULT_TIMEOUT,
                 max_rss: int = MAX_RSS) -> None:
        if not isinstance(data, (bytes, Path)):
            raise StepProbeError("Zdroj STEP musí být soubor nebo bajty.")
        if isinstance(data, bytes) and (not data or len(data) > MAX_STEP_BYTES):
            raise StepProbeError("STEP je prázdný nebo větší než povolených 16 MiB.")
        if timeout <= 0 or max_rss <= 0:
            raise ValueError("Mez času a paměti musí být kladná.")
        context = multiprocessing.get_context("spawn")
        self._conn, child = context.Pipe(duplex=False)
        self._process = context.Process(target=_worker, args=(child, data), daemon=True,
                                        name="skodacad-step-kontrola")
        try:
            self._process.start()
        except BaseException:
            child.close()
            self._conn.close()
            raise
        child.close()
        self._deadline = time.monotonic() + timeout
        self._max_rss = max_rss
        self._done = threading.Event()
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._outcome: StepOutcome | None = None
        self._delivered = False
        threading.Thread(target=self._monitor, daemon=True, name="step-monitor").start()
        threading.Thread(target=self._receive, daemon=True, name="step-result").start()

    def _publish(self, outcome: StepOutcome) -> bool:
        with self._lock:
            if self._done.is_set():
                return False
            self._outcome = outcome
            self._done.set()
            return True

    def _stop_process(self) -> None:
        if self._process.is_alive():
            self._process.terminate()
        self._process.join(timeout=2)
        if self._process.is_alive():
            self._process.kill()
            self._process.join(timeout=2)
        self._stopped.set()

    def _monitor(self) -> None:
        while not self._done.is_set():
            if time.monotonic() >= self._deadline:
                error = "Kontrola STEP překročila časový limit."
            elif not self._process.is_alive():
                return  # odpověď či konec roury převezme čtecí vlákno
            else:
                try:
                    memory = _resident_bytes(self._process.pid)
                except Exception:  # noqa: BLE001 -- selhání měření nesmí vypnout dohled
                    memory = None
                if memory is None and self._process.is_alive():
                    error = "Nelze ověřit využití paměti kontroly STEP."
                elif memory is not None and memory > self._max_rss:
                    error = "Kontrola STEP překročila limit paměti."
                else:
                    self._done.wait(0.1)
                    continue
            if self._publish(StepOutcome(error=error)):
                self._stop_process()
            return

    def _receive(self) -> None:
        try:
            success, result = self._conn.recv()
            outcome = (StepOutcome(facts=result[0], shape_bytes=result[1], source_bytes=result[2])
                       if success else StepOutcome(error=result))
        except (EOFError, OSError):
            outcome = StepOutcome(error="Pomocný proces kontroly STEP skončil bez výsledku.")
        finally:
            self._conn.close()
        if self._publish(outcome):
            self._stop_process()

    def cancel(self) -> None:
        if self._publish(StepOutcome(error="Kontrola STEP byla zrušena.")):
            self._stop_process()
        self._delivered = True

    def poll(self) -> StepOutcome | None:
        if not self._done.is_set() or self._delivered:
            return None
        self._delivered = True
        return self._outcome
