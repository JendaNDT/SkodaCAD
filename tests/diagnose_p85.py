"""One instrumented native cycle for diagnosis, never budget acceptance."""
from __future__ import annotations

import argparse
import functools
import importlib
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
    def __init__(self, folder, prefix="", started=None):
        self.stream = (folder / f"{prefix}timing.jsonl").open("x", encoding="utf-8")
        self.started = time.perf_counter() if started is None else started
        self.main = threading.get_ident()
        self.lock = threading.RLock()
        self.local = threading.local()
        self.recent = deque(maxlen=20)
        self.totals = {}
        self.count = self.serial = 0
        self.errors = []
        self.context = {}
        self.emit({"type": "identity", "pid": os.getpid(), "parent_pid": os.getppid(),
                   "epoch_perf_s": self.started, "at_s": time.perf_counter()-self.started,
                   "process_cpu_s": time.process_time()})

    def emit(self, row):
        with self.lock:
            if self.count >= 20000:
                if not self.errors:
                    self.errors.append("Diagnostic record cap reached")
                return
            self.count += 1
            self.stream.write(json.dumps({"pid": os.getpid(), **row}, allow_nan=False) + "\n")
            self.stream.flush()

    def wrap(self, owner, name):
        original = getattr(owner, name)
        label = owner.__name__ + "." + name

        @functools.wraps(original)
        def measured(*args, **kwargs):
            main = threading.get_ident() == self.main
            detail = {}
            if name == "_refresh_next_standard_icon" and args[0]._standard_icon_queue:
                action, standard = args[0]._standard_icon_queue[0]
                detail = {"icon_action": action.text(), "standard_icon": int(standard)}
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
                       "main_thread": main, "parents": list(stack),
                       "job_context": dict(self.context), **detail}
                with self.lock:
                    key = label + (":main" if main else ":other")
                    total = self.totals.setdefault(key, {"calls": 0, "wall_s": 0.,
                        "process_cpu_s": 0., "thread_cpu_s": 0., "max_wall_s": 0.})
                    total["calls"] += 1
                    total["wall_s"] += elapsed
                    total["process_cpu_s"] += process_cpu
                    total["thread_cpu_s"] += thread_cpu
                    total["max_wall_s"] = max(total["max_wall_s"], elapsed)
                    if main and elapsed >= .05:
                        self.recent.append(row)
                if elapsed >= .05:
                    self.emit(row)
                if owner is TracedConnection and name == "send":
                    self.snapshot(args[0].summary)

        setattr(owner, name, measured)

    def snapshot(self, path, loop_finished=False):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "diagnostic_only": True, "budget_acceptance": False, "pid": os.getpid(),
            "epoch_perf_s": self.started, "record_count": self.count,
            "loop_finished": loop_finished, "last_job_context": dict(self.context),
            "span_totals_inclusive_do_not_sum": self.totals, "errors": self.errors,
        }, allow_nan=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)


class TracedConnection:
    """Forward the original messages without changing the worker protocol."""

    def __init__(self, connection, trace, summary):
        self.connection, self.trace, self.summary = connection, trace, summary

    def recv(self):
        message = self.connection.recv()
        if isinstance(message, tuple) and len(message) >= 3:
            kind, job, data = message[:3]
            self.trace.context = {"kind": kind, "job": job,
                "features": len(data.get("features", ())) if isinstance(data, dict) else None}
            self.trace.emit({"type": "request", "at_s": time.perf_counter()-self.trace.started,
                             **self.trace.context})
        return message

    def send(self, message):
        self.connection.send(message)
        self.trace.emit({"type": "reply", "at_s": time.perf_counter()-self.trace.started,
                         "kind": message[0], "job": message[1]})
        # Production close/cancel terminates workers. Keep totals after each reply,
        # rather than relying on a finally block that SIGTERM would bypass.
        self.trace.snapshot(self.summary)


def traced_worker_main(connection, step_phase):
    """Top-level spawn target; the production worker loop stays unchanged."""
    from skodacad import features, worker

    rebuild = importlib.import_module("skodacad.rebuild")
    folder = Path(os.environ["SKODACAD_P85_TRACE_FOLDER"])
    prefix = f"worker-{os.getpid()}-"
    summary = folder / f"{prefix}summary.json"
    trace = Trace(folder, prefix, float(os.environ["SKODACAD_P85_TRACE_EPOCH"]))
    for owner, names in ((worker, ("encode_result", "_shape_bytes")),
                         (rebuild, ("rebuild", "_run_feature", "inspect_volume")),
                         (features, ("inspect_volume",)),
                         (TracedConnection, ("recv", "send"))):
        for name in names:
            trace.wrap(owner, name)
    try:
        worker._worker_main(TracedConnection(connection, trace, summary), step_phase)
    finally:
        # Terminated workers may have no summary; flushed rows still identify them.
        trace.stream.close()
        trace.snapshot(summary, loop_finished=True)


def read_worker_trace(path):
    """An owned worker can be terminated mid-write; only its partial last row is optional."""
    raw = path.read_bytes()
    lines, records = raw.splitlines(), []
    partial_tail_bytes = 0
    for index, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except (ValueError, UnicodeDecodeError):
            if index != len(lines)-1 or raw.endswith(b"\n"):
                raise
            partial_tail_bytes = len(line)
    return records, partial_tail_bytes


def child(folder, cycles=1):
    if cycles not in (1, 3):
        raise ValueError("Diagnostic cycles must be 1 or 3; this is never budget acceptance")
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication, QStyle

    import skodacad.worker as worker
    import soak_p8_gui
    from skodacad.assembly_session import AssemblySession
    from skodacad.gui import assembly_parameter_preview, main_window
    from skodacad.gui.assembly_parameter_preview import AssemblyParameterPreviewDialog
    from skodacad.gui.assembly_parameters import AssemblyParametersDialog
    from skodacad.gui.assembly_window import AssemblyWindow
    from skodacad.gui.main_window import MainWindow
    from skodacad.gui.viewer import OccViewer

    app = QApplication([])
    trace = Trace(folder)
    os.environ["SKODACAD_P85_TRACE_FOLDER"] = str(folder)
    os.environ["SKODACAD_P85_TRACE_EPOCH"] = str(trace.started)
    original_worker_main = worker._worker_main
    worker._worker_main = traced_worker_main
    targets = (
        (worker, ("decode_result", "_shape_from")),
        (worker.BackgroundRebuilder, ("poll", "_spawn", "_submit", "cancel", "close")),
        (main_window, ("install_macos_accessibility",)),
        (MainWindow, ("__init__", "show", "open_model", "open_assembly", "_poll", "_reload_all",
                      "_refresh_all", "_assembly_window_destroyed", "_create_actions",
                      "_build_side_panel", "_build_editor_panel", "_build_measure_panel",
                      "_build_map_panel", "_build_section_panel", "_build_ndt_panel",
                      "_build_audit_panel", "_build_design_panel", "_build_assistant_panel",
                      "_build_menus", "_build_ribbon", "_refresh_ui_icons",
                      "_refresh_next_standard_icon")),
        (QStyle, ("standardIcon",)),
        (AssemblyWindow, ("_poll", "_refresh", "_refresh_tree_visibility", "closeEvent",
                          "edit_parameters", "preview_parameters", "select",
                          "set_component_transparency", "isolate_selected", "show_all",
                          "reset_transparency")),
        (AssemblySession, ("preview_parameters", "rebuild")),
        (AssemblyParametersDialog, ("__init__", "_update", "_refresh_usage", "show_preview")),
        (AssemblyParameterPreviewDialog, ("__init__", "_show_model")),
        (assembly_parameter_preview, ("placement_changes",)),
        (OccViewer, ("_initialize", "_open_view", "_style", "_fit_camera",
                     "show_part", "_sync_size")),
        (soak_p8_gui.Driver, ("ready", "edit")),
        (soak_p8_gui, ("preview_and_close", "step_roundtrip", "inspect_history", "inspect_assembly",
                       "make_assembly", "write")),
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
        soak_p8.child(folder, cycles, 0, 3072 * 1024**2)
    finally:
        worker._worker_main = original_worker_main
        timer.stop()
        tick()
        trace.stream.close()
        baseline.write(folder / "timing-summary.json", {
            "diagnostic_only": True, "budget_acceptance": False,
            "cycles": cycles, "warmups": 0, "ticks": ticks, "max_gap_s": maximum,
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
    worker_logs = sorted(folder.glob("worker-*-timing.jsonl"))
    if not worker_logs:
        raise RuntimeError("Worker CPU diagnostic is missing")
    worker_traces = []
    for path in worker_logs:
        records, partial = read_worker_trace(path)
        if not records or len(records) >= 20000 or records[0]["type"] != "identity":
            raise RuntimeError(f"Incomplete diagnostic worker trace: {path.name}")
        worker_traces.append({"file": path.name, "pid": records[0]["pid"],
                              "records": len(records), "partial_tail_bytes": partial})
    for path in folder.glob("worker-*-summary.json"):
        if json.loads(path.read_text())["errors"]:
            raise RuntimeError(f"Worker diagnostic errors: {path.name}")
    baseline.write(folder / "worker-traces.json", {
        "diagnostic_only": True, "budget_acceptance": False, "workers": worker_traces,
        "note": "Owned cancellation/crash/close can terminate a worker before its summary."})
    print("Diagnostic cycle complete; NOT a budget acceptance or release pass")


if __name__ == "__main__":
    main()
