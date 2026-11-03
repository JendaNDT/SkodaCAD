"""P8.2: stejné vstupy P8.1, kontrola a vnořený rozpad času na hodinách.

python tests/profile_p8.py --output out/p82.json --repeats 3
Žádné produkční úpravy. Každý případ a režim běží v novém procesu.
"""
from __future__ import annotations

import argparse
import functools
import importlib.metadata
import inspect
import json
import os
import platform
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import benchmark_p8 as baseline

ROOT = baseline.ROOT
MODES = ("control", "spans")
CASES = ("gui-assembly", "history-60")


class Recorder:
    """Vnořené intervaly: inclusive pro orientaci, self bez dvojího součtu."""
    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.thread_id = threading.get_ident()
        self.stack = []
        self.rows = {}

    @contextmanager
    def span(self, name):
        frame = [self.clock(), 0.]
        self.stack.append(frame)
        try:
            yield
        finally:
            elapsed = self.clock()-frame[0]
            self.stack.pop()
            row = self.rows.setdefault(name, {"calls": 0, "inclusive_s": 0., "self_s": 0.})
            row["calls"] += 1
            row["inclusive_s"] += elapsed
            row["self_s"] += elapsed-frame[1]
            if self.stack:
                self.stack[-1][1] += elapsed

    @contextmanager
    def patch(self, targets):
        originals = []
        try:
            for owner, attribute, label in targets:
                raw = inspect.getattr_static(owner, attribute)
                descriptor = type(raw) if isinstance(raw, (staticmethod, classmethod)) else None
                original = raw.__func__ if descriptor else raw

                def decorate(function, name):
                    @functools.wraps(function)
                    def wrapped(*args, **kwargs):
                        if threading.get_ident() != self.thread_id or not self.stack:
                            return function(*args, **kwargs)
                        with self.span(name):
                            return function(*args, **kwargs)
                    return wrapped

                wrapper = decorate(original, label)
                setattr(owner, attribute, descriptor(wrapper) if descriptor else wrapper)
                originals.append((owner, attribute, raw))
            yield
        finally:
            for owner, attribute, raw in reversed(originals):
                setattr(owner, attribute, raw)


def gui_targets():
    from skodacad import assembly_build, assembly_session
    from skodacad.assembly_build import AssemblyResult
    from skodacad.assembly_session import AssemblySession
    from skodacad.gui import assembly_parameter_preview, assembly_parameters
    from skodacad.gui.assembly_parameter_preview import AssemblyParameterPreviewDialog
    from skodacad.gui.assembly_parameters import AssemblyParametersDialog
    from skodacad.gui.assembly_window import AssemblyWindow
    from skodacad.gui.viewer import OccViewer

    return [(AssemblySession, "open", "session_open"),
            (AssemblySession, "preview_parameters", "session_preview"),
            (AssemblyWindow, "_fill_tree", "tree"),
            (AssemblyWindow, "_refresh_tree_visibility", "tree_visibility"),
            (AssemblyWindow, "_refresh", "window_refresh_other"),
            (AssemblyWindow, "_show_visible", "main_scene_other"),
            (AssemblyWindow, "_exec_dialog", "modal_event_loop_other"),
            (AssemblyWindow, "_exec_parameter_preview", "modal_event_loop_other"),
            (AssemblyParametersDialog, "__init__", "editor_widgets"),
            (AssemblyParametersDialog, "_refresh_usage", "usage_widgets_other"),
            (assembly_parameters, "parameter_usage", "usage_analysis"),
            (AssemblyParameterPreviewDialog, "__init__", "preview_widgets_other"),
            (assembly_parameter_preview, "placement_changes", "placement_comparison"),
            (AssemblyParameterPreviewDialog, "_show_model", "preview_scene_other"),
            (AssemblyResult, "compound", "compound"),
            (assembly_session, "_source_hashes", "source_hashes"),
            (assembly_build, "read_source", "source_read"),
            (assembly_build, "locate", "source_locate"),
            (assembly_build, "_build_level", "build_level_other"),
            (OccViewer, "show_part", "viewer_show_part"),
            (OccViewer, "_initialize", "viewer_initialize_other"),
            (OccViewer, "_open_view", "viewer_open_view"),
            (OccViewer, "_redraw", "viewer_redraw"),
            (OccViewer, "highlight", "viewer_highlight")]


def history_targets():
    import importlib

    from skodacad import features, worker
    from skodacad.features import BuildContext

    rebuild_module = importlib.import_module("skodacad.rebuild")
    return [(rebuild_module, "_run_feature", "feature_other"),
            (rebuild_module, "inspect_volume", "volume_validation"),
            (features, "inspect_volume", "volume_validation"),
            (features, "extrude", "extrude_tool"),
            (BuildContext, "apply", "boolean_apply_other"),
            (BuildContext, "_fork_for_feature", "feature_fork"),
            (BuildContext, "_accept_feature", "feature_accept"),
            (worker, "_shape_bytes", "shape_encode"),
            (worker, "_shape_from", "shape_decode")]


def profiled_measure(folder, mode, repeats):
    def measure(name, operation, check, _repeats):
        expected = check(operation())  # stejné nezapočítané zahřátí jako P8.1
        samples, traces = [], []
        hooks = gui_targets() if name.startswith(("open-", "select-")) else history_targets()
        for _index in range(repeats):
            recorder = Recorder()
            with recorder.patch(hooks):
                start = time.perf_counter()
                with recorder.span("operation_other"):
                    outcome = operation()
                elapsed = time.perf_counter()-start
            samples.append(elapsed)
            if check(outcome) != expected:
                raise RuntimeError(f"Profilování změnilo výsledek {name}")
            accounted = sum(row["self_s"] for row in recorder.rows.values())
            root_s = recorder.rows["operation_other"]["inclusive_s"]
            if abs(accounted-root_s) > max(1e-8, root_s*1e-9) or any(
                    row["self_s"] < 0 for row in recorder.rows.values()):
                raise RuntimeError("Intervaly nerozdělují čas operace")
            trace = {"spans": recorder.rows, "accounted_wall_s": accounted,
                     "timer_envelope_s": elapsed-root_s}
            traces.append(trace)
        import statistics

        return {"name": name, "warmups": 1, "samples_s": samples,
                "median_s": statistics.median(samples), "min_s": min(samples),
                "max_s": max(samples), "correctness": expected, "traces": traces}
    return measure


def child(case, mode, folder, repeats):
    if mode == "control":
        return baseline.run_child(case, folder, repeats)
    old = baseline.measure
    measure = profiled_measure(folder, mode, repeats)
    baseline.measure = measure
    import benchmark_p8_gui

    old_gui = benchmark_p8_gui.measure
    benchmark_p8_gui.measure = measure
    try:
        return baseline.run_child(case, folder, repeats)
    finally:
        baseline.measure = old
        benchmark_p8_gui.measure = old_gui


def hashes():
    paths = [p for p in (ROOT / "src").rglob("*.py") if p.name != "_build.py"]
    paths += list((ROOT / "examples").rglob("*.json"))
    paths += [Path(__file__).resolve(), ROOT / "tests/benchmark_p8.py",
              ROOT / "tests/benchmark_p8_gui.py"]
    return {p.relative_to(ROOT).as_posix(): baseline.digest(p) for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cases", default=",".join(CASES))
    parser.add_argument("--child", choices=CASES)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--folder", type=Path)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10:
        parser.error("Opakování musí být 1–10")
    if args.child:
        baseline.write(args.folder / "result.json",
                       child(args.child, args.mode, args.folder, args.repeats))
        return 0
    cases = args.cases.split(",")
    if (not args.output or any(c not in CASES for c in cases)
            or len(cases) != len(set(cases))):
        parser.error("Nový výstup a známé neopakující se případy")
    output = args.output.resolve()
    folder = output.with_suffix("")
    if output.exists() or folder.exists():
        parser.error("Evidence již existuje; zvol jiné jméno")
    folder.mkdir(parents=True)
    before = hashes()
    report = {"schema": "skodacad-p8.2-v1", "created_utc": datetime.now(UTC).isoformat(),
        "commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "environment": {"system": platform.platform(), "python": platform.python_version(),
                        "cpu": baseline.processor_name(), "logical_cpus": os.cpu_count(),
                        "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None,
                        "packages": {d.metadata["Name"]: d.version
                            for d in importlib.metadata.distributions()
                            if any(token in d.metadata["Name"].lower() for token in
                                   ("build123d", "ocp", "pyside6", "numpy"))}},
        "hashes": before, "repeats": args.repeats, "results": [],
        "limits": ["Instrumentace má režii; nejde o nové rychlostní výsledky.",
                   "Inclusive intervaly se překrývají, sčítat lze pouze self_s.",
                   "Self interval je čas na hodinách včetně čekání; není to čistý CPU čas.",
                   "Intervaly sledují volající hlavní vlákno, nikoli worker či GPU.",
                   "Neinstrumentovaný control a režimy mají stejné vstupy, vlastní procesy.",
                   "Případy GUI včetně událostí/čekání odpovídají P8.1, žádné glFinish/FPS."]}
    for case in cases:
        for mode in MODES:
            name = f"{case}-{mode}"
            path = folder / name
            path.mkdir()
            command = [sys.executable, str(Path(__file__).resolve()), "--child", case,
                       "--mode", mode, "--folder", str(path), "--repeats", str(args.repeats)]
            with (path / "process.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                    env={**os.environ, "SKODACAD_HOME": str(path / "profile")},
                    start_new_session=os.name != "nt")
                try:
                    code = process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    baseline.stop_process(process)
                    code = "timeout"
            result = (json.loads((path / "result.json").read_text(encoding="utf-8"))
                      if code == 0 else {"case": case, "log": f"{name}/process.log"})
            result.update(mode=mode, status="ok" if code == 0 else "failed", exit=code)
            report["results"].append(result)
            print(f"P82_CASE {name}: {result['status']}", flush=True)
            if code == 0:
                print("P82_RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
            if code != 0:
                print((path / "process.log").read_text(encoding="utf-8")[-8000:], flush=True)
    if hashes() != before:
        raise RuntimeError("Zdroj, reference nebo měřič se během profilování změnil")
    for case in cases:
        results = [r for r in report["results"] if r["case"] == case and r["status"] == "ok"]
        if len(results) == len(MODES):
            facts = [{m["name"]: m["correctness"] for m in r["metrics"]} for r in results]
            if any(f != facts[0] for f in facts[1:]) or any(
                    r["input_sha256"] != results[0]["input_sha256"] for r in results[1:]):
                raise RuntimeError("Režimy profilování mají jiné vstupy nebo geometrii")
    print("P82_ENV " + json.dumps({k: report[k] for k in (
        "commit", "environment", "hashes", "repeats")}, ensure_ascii=False), flush=True)
    baseline.write(output, report)
    return 0 if all(r["status"] == "ok" for r in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
