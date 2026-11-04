"""One instrumented native cycle for diagnosis, never budget acceptance."""
from __future__ import annotations

import argparse
import functools
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

import benchmark_p8 as baseline
import budget_p8
import soak_p8


class Trace:
    def __init__(self, folder):
        self.stream = (folder / "timing.jsonl").open("x", encoding="utf-8")
        self.started = time.perf_counter()
        self.main = threading.get_ident()
        self.lock = threading.RLock()
        self.local = threading.local()
        self.recent = deque(maxlen=20)
        self.totals = {}
        self.count = self.serial = 0
        self.errors = []

    def emit(self, row):
        with self.lock:
            if self.count >= 20000:
                if not self.errors:
                    self.errors.append("Diagnostic record cap reached")
                return
            self.count += 1
            self.stream.write(json.dumps(row, allow_nan=False) + "\n")
            self.stream.flush()

    def wrap(self, owner, name):
        original = getattr(owner, name)
        label = owner.__name__ + "." + name

        @functools.wraps(original)
        def measured(*args, **kwargs):
            main = threading.get_ident() == self.main
            wall, cpu, thread = time.perf_counter(), time.process_time(), time.thread_time()
            stack = getattr(self.local, "stack", [])
            self.local.stack = stack
            with self.lock:
                self.serial += 1
                number = self.serial
            stack.append((number, label))
            try:
                return original(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - wall
                process_cpu = time.process_time() - cpu
                thread_cpu = time.thread_time() - thread
                stack.pop()
                row = {"type": "span", "id": number, "label": label,
                       "start_s": wall - self.started, "wall_s": elapsed,
                       "process_cpu_s": process_cpu, "thread_cpu_s": thread_cpu,
                       "main_thread": main, "parents": list(stack)}
                with self.lock:
                    key = label + (":main" if main else ":other")
                    total = self.totals.setdefault(key, {"calls": 0, "wall_s": 0.,
                        "thread_cpu_s": 0., "max_wall_s": 0.})
                    total["calls"] += 1
                    total["wall_s"] += elapsed
                    total["thread_cpu_s"] += thread_cpu
                    total["max_wall_s"] = max(total["max_wall_s"], elapsed)
                    if main and elapsed >= .05:
                        self.recent.append(row)
                if elapsed >= .05:
                    self.emit(row)

        setattr(owner, name, measured)


def child(folder):
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication

    import skodacad.worker as worker
    import soak_p8_gui
    from skodacad.gui.assembly_window import AssemblyWindow
    from skodacad.gui.main_window import MainWindow
    from skodacad.gui.viewer import OccViewer

    app = QApplication([])
    trace = Trace(folder)
    targets = (
        (worker, ("decode_result", "_shape_from")),
        (worker.BackgroundRebuilder, ("poll", "_spawn", "close")),
        (MainWindow, ("open_model", "open_assembly", "_poll", "_reload_all",
                      "_refresh_all", "_assembly_window_destroyed")),
        (AssemblyWindow, ("_poll", "_refresh", "_refresh_tree_visibility", "closeEvent")),
        (OccViewer, ("show_part", "_sync_size")),
        (soak_p8_gui.Driver, ("ready", "edit")),
        (soak_p8_gui, ("preview_and_close", "step_roundtrip", "inspect_history")),
        (soak_p8.Memory, ("sample",)),
    )
    for owner, names in targets:
        for name in names:
            trace.wrap(owner, name)
    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    last = time.perf_counter()
    ticks, maximum = 0, 0.

    def tick():
        nonlocal last, ticks, maximum
        now = time.perf_counter()
        gap = now - last
        ticks += 1
        maximum = max(maximum, gap)
        if gap >= .1:
            trace.emit({"type": "qt_gap", "start_s": last - trace.started,
                        "end_s": now - trace.started, "wall_s": gap,
                        "active": list(getattr(trace.local, "stack", [])),
                        "recent": list(trace.recent), "loadavg": list(os.getloadavg()),
                        "process_cpu_s": time.process_time()})
        last = now

    timer.timeout.connect(tick)
    timer.start(50)
    try:
        soak_p8.child(folder, 1, 0, 3072 * 1024**2)
    finally:
        timer.stop()
        tick()
        trace.stream.close()
        baseline.write(folder / "timing-summary.json", {
            "diagnostic_only": True, "budget_acceptance": False,
            "cycles": 1, "warmups": 0, "ticks": ticks, "max_gap_s": maximum,
            "span_totals_inclusive_do_not_sum": trace.totals,
            "errors": trace.errors, "record_count": trace.count})
    if trace.errors:
        raise RuntimeError(str(trace.errors))
    del app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child)
        return
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    before = budget_p8.manifest()
    started = time.perf_counter()
    with (folder / "process.log").open("w") as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                    "--child", str(folder)], stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            baseline.stop_process(process)
            code = "timeout"
    unchanged = before == budget_p8.manifest()
    report = {"schema": "skodacad-p85-diagnostic-v1", "budget_acceptance": False,
              "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "source_hashes": before, "source_hashes_unchanged": unchanged,
              "diagnostic_sha256": baseline.digest(Path(__file__).resolve()),
              "cycles": 1, "warmups": 0, "exit": code,
              "wall_s": time.perf_counter() - started}
    baseline.write(folder / "diagnostic.json", report)
    if code != 0 or not unchanged:
        raise RuntimeError("Diagnostic process failed or sources changed")
    rows, error = soak_p8.read_events(folder / "events.jsonl")
    if error:
        raise RuntimeError(error)
    footer = json.loads((folder / "footer.json").read_text())
    soak_p8.validate_runtime(rows, footer, 1, 0)
    print("Diagnostic cycle complete; NOT a budget acceptance or release pass")


if __name__ == "__main__":
    main()
