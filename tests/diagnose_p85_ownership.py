"""Three diagnostic cycles: hosted Qt event spans, weak ownership and native VM regions.

No budget evaluation, threshold change, primary GC, or production monkeypatch fix.
All original soak scenarios/physics remain in place. Observations add overhead;
vmmap may briefly suspend the target, so its intervals are recorded separately.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import queue
import subprocess
import sys
import threading
import time
import weakref
from pathlib import Path

import benchmark_p8 as baseline
import budget_p8
import diagnose_p85
import soak_p8

CYCLES = 3
QUESTION = (
    "On hosted macOS, do obsolete transferred BuildResults accumulate across original cycles, "
    "which native VM region categories grow, and which timed GUI calls/events overlap Qt gaps?"
)


def child(folder):
    from PySide6 import QtWidgets

    import skodacad.worker as worker
    import soak_p8_gui
    from skodacad.gui.main_window import MainWindow
    from skodacad.gui.viewer import OccViewer
    from skodacad.step_task import _resident_bytes

    started = time.perf_counter()
    results, shapes, trace_box, snapshots, snapshot_errors = [], [], [], [], []
    stream = (folder / "ownership.jsonl").open("x", encoding="utf-8")
    tasks = queue.Queue(maxsize=CYCLES + 3)
    checkpoint = 0

    def record(kind, **extra):
        rss = _resident_bytes(os.getpid())
        if rss is None or rss <= 0:
            raise RuntimeError("Missing positive native parent RSS")
        stream.write(json.dumps({
            "kind": kind, "at_s": time.perf_counter() - started, "rss_bytes": rss,
            "live_results": [i for i, ref in enumerate(results) if ref() is not None],
            "live_shape_wrappers": sum(ref() is not None for ref in shapes), **extra,
        }, allow_nan=False) + "\n")
        stream.flush()

    record("identity", pid=os.getpid(), epoch_perf_s=started)

    class EventApplication(QtWidgets.QApplication):
        def notify(self, receiver, event):
            wall, cpu = time.perf_counter(), time.thread_time()
            receiver_type, event_type = type(receiver).__name__, int(event.type())
            try:
                return super().notify(receiver, event)
            finally:
                elapsed = time.perf_counter() - wall
                if elapsed >= .05 and trace_box and not trace_box[0].stream.closed:
                    trace = trace_box[0]
                    trace.emit({
                        "type": "qt_event_span", "receiver_type": receiver_type,
                        "event_type": event_type, "start_s": wall - trace.started,
                        "wall_s": elapsed, "thread_cpu_s": time.thread_time() - cpu,
                        "active": list(getattr(trace.local, "stack", [])),
                        "note": "Inclusive event span; nested waits/events must not be summed.",
                    })

    original_trace = diagnose_p85.Trace

    class RootTrace(original_trace):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not kwargs.get("prefix") and len(args) == 1:
                trace_box.append(self)

    def native_snapshots():
        while True:
            task = tasks.get()
            if task is None:
                return
            label, requested = task
            path = folder / f"vmmap-{label}.txt"
            before = time.perf_counter()
            row = {"label": label, "requested_s": requested - started,
                   "start_s": before - started, "pid": os.getpid(),
                   "command": ["/usr/bin/vmmap", "-summary", str(os.getpid())]}
            try:
                completed = subprocess.run(row["command"], capture_output=True, text=True,
                                           timeout=20, check=False)
                path.write_text(completed.stdout + "\nSTDERR:\n" + completed.stderr,
                                encoding="utf-8")
                row.update(exit=completed.returncode, file=path.name,
                           sha256=baseline.digest(path))
                if completed.returncode or "REGION TYPE" not in completed.stdout:
                    snapshot_errors.append(f"Native allocation snapshot unavailable: {label}")
            except Exception as exc:  # noqa: BLE001 -- preserve capability failures explicitly
                row["error"] = f"{type(exc).__name__}: {exc}"
                snapshot_errors.append(row["error"])
            row["end_s"] = time.perf_counter() - started
            snapshots.append(row)

    observer = threading.Thread(target=native_snapshots, name="p85-vmmap-observer", daemon=True)
    observer.start()
    original_decode = worker.decode_result

    @functools.wraps(original_decode)
    def decode(data):
        record("before-decode", payload_parts=len(data["parts_before"]))
        wall, cpu = time.perf_counter(), time.thread_time()
        result = original_decode(data)
        results.append(weakref.ref(result))
        shapes.extend(weakref.ref(part) for part in [result.part, *result.parts_before.values()]
                      if part is not None)
        record("after-decode", result_number=len(results) - 1,
               wall_s=time.perf_counter() - wall, thread_cpu_s=time.thread_time() - cpu)
        return result

    original_show = OccViewer.show_part

    @functools.wraps(original_show)
    def show(self, *args, **kwargs):
        record("before-show", viewer=id(self))
        wall, cpu = time.perf_counter(), time.thread_time()
        try:
            return original_show(self, *args, **kwargs)
        finally:
            record("after-show", viewer=id(self), wall_s=time.perf_counter() - wall,
                   thread_cpu_s=time.thread_time() - cpu)

    original_resources = soak_p8_gui.resources

    @functools.wraps(original_resources)
    def resources(app):
        nonlocal checkpoint
        value = original_resources(app)
        mains = [w for w in app.topLevelWidgets() if isinstance(w, MainWindow)]
        current = [i for i, ref in enumerate(results) if ref() is not None
                   and any(ref() is window.session.result for window in mains)]
        record("checkpoint", checkpoint=checkpoint, current_results=current, resources=value)
        # Original order: initial, eight phases per cycle, before/after final diagnostic GC,
        # normal close. Snapshot launch does not replace or move any original observation.
        if checkpoint == 0:
            tasks.put_nowait(("initial", time.perf_counter()))
        elif checkpoint <= CYCLES * len(soak_p8.PHASES) and checkpoint % len(soak_p8.PHASES) == 0:
            tasks.put_nowait((f"cycle-{checkpoint // len(soak_p8.PHASES) - 1}",
                              time.perf_counter()))
        elif checkpoint == CYCLES * len(soak_p8.PHASES) + 3:
            tasks.put_nowait(("normal-close", time.perf_counter()))
        checkpoint += 1
        return value

    worker.decode_result = decode
    OccViewer.show_part = show
    soak_p8_gui.resources = resources
    QtWidgets.QApplication = EventApplication
    diagnose_p85.Trace = RootTrace
    try:
        diagnose_p85.child(folder, cycles=CYCLES)
    finally:
        tasks.put(None, timeout=25)
        observer.join(timeout=110)
        if observer.is_alive():
            snapshot_errors.append("Native observer did not stop")
        record("after-diagnostic-close")
        stream.close()
        baseline.write(folder / "ownership-summary.json", {
            "diagnostic_only": True, "budget_acceptance": False, "cycles": CYCLES,
            "decoded_results": len(results), "shape_wrappers_observed": len(shapes),
            "live_results_after_close": [i for i, ref in enumerate(results) if ref() is not None],
            "live_shape_wrappers_after_close": sum(ref() is not None for ref in shapes),
            "native_snapshots": snapshots, "native_snapshot_errors": snapshot_errors,
            "limitations": ["Weakrefs cover Python wrappers, not all native owners.",
                            "Current closed-window references alone do not prove growing leaks.",
                            "Diagnostic event hooks/observers add overhead; not budget timings.",
                            "vmmap intervals can suspend the target; match them to Qt gaps.",
                            "Three cycles do not replace 20+2 acceptance or prove leak freedom."],
        })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child)
        return
    if not args.output or args.output.exists():
        parser.error("A fresh diagnostic output directory is required")
    if sys.platform != "darwin":
        parser.error("This native allocation diagnostic is macOS only")
    folder = args.output.resolve()
    folder.mkdir(parents=True)
    before = budget_p8.manifest()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    plan = {"schema": "skodacad-p85-ownership-diagnostic-v1", "question": QUESTION,
            "budget_acceptance": False, "cycles": CYCLES, "warmups": 0, "commit": head,
            "source_hashes": before, "diagnostic_sha256": baseline.digest(Path(__file__)),
            "vmmap_effect": "Potential suspension is timed separately, not a product stall claim."}
    baseline.write(folder / "plan.json", plan)
    started = time.perf_counter()
    with (folder / "process.log").open("x", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                    "--child", str(folder)], stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            baseline.stop_process(process)
            code = "timeout"
    unchanged = before == budget_p8.manifest()
    report = {**plan, "exit": code, "wall_s": time.perf_counter() - started,
              "source_hashes_unchanged": unchanged, "status": "incomplete"}
    if code == 0 and unchanged:
        events, error = soak_p8.read_events(folder / "events.jsonl")
        if error:
            raise RuntimeError(error)
        footer = json.loads((folder / "footer.json").read_text())
        soak_p8.validate_runtime(events, footer, CYCLES, 0)
        timing = json.loads((folder / "timing-summary.json").read_text())
        ownership = json.loads((folder / "ownership-summary.json").read_text())
        if timing["cycles"] != CYCLES or timing["errors"]:
            raise RuntimeError("Incorrect or failed diagnostic timing scope")
        report.update(status="complete", original_runtime_validation="PASS",
                      timing=timing, ownership=ownership)
        if [s["label"] for s in ownership["native_snapshots"]] != [
                "initial", "cycle-0", "cycle-1", "cycle-2", "normal-close"]:
            raise RuntimeError("Missing or reordered native allocation snapshots")
        worker_traces = []
        for path in sorted(folder.glob("worker-*-timing.jsonl")):
            rows, partial = diagnose_p85.read_worker_trace(path)
            if not rows or rows[0]["type"] != "identity" or len(rows) >= 20000:
                raise RuntimeError(f"Missing or capped worker trace: {path.name}")
            worker_traces.append({"file": path.name, "pid": rows[0]["pid"],
                                  "records": len(rows), "partial_tail_bytes": partial})
        if not worker_traces:
            raise RuntimeError("No actual worker timing evidence")
        for path in folder.glob("worker-*-summary.json"):
            if json.loads(path.read_text())["errors"]:
                raise RuntimeError(f"Worker timing errors: {path.name}")
        report["worker_traces"] = worker_traces
        if ownership["native_snapshot_errors"]:
            report["status"] = "native-snapshot-unavailable"
    baseline.write(folder / "diagnostic.json", report)
    print("P85_DIAG_ENV " + json.dumps({"commit": head, "source_hashes": before}))
    print("Diagnostic only: three cycles, no budget acceptance or release claim")
    if report["status"] != "complete":
        raise RuntimeError("Diagnostic incomplete; preserve its original evidence")


if __name__ == "__main__":
    main()
