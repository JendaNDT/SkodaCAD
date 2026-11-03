"""P8.1: opakovatelná zátěž, každý případ ve vlastním procesu; bez prahů rychlosti.

python tests/benchmark_p8.py --output out/p8-baseline.json --repeats 3
python tests/benchmark_p8.py --output out/p8-gui.json --cases gui-history,gui-assembly
Výstup ani sousední složka evidence nesmějí existovat. Produkční kód se nemění.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import signal
import statistics
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ("startup", "history-10", "history-30", "history-60", "assembly-50",
         "assembly-200", "assembly-800", "constraints-8", "constraints-24",
         "worker", "step-history", "ndt-multi", "gui-history", "gui-assembly")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return path


def history_data(holes):
    """2+2N skutečných prvků: slepé válcové kapsy, nikoli prázdné položky historie."""
    width = 4*holes + 8
    features = [
        {"id": "base", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "rectangle", "width": width, "height": 20}]},
        {"id": "plate", "type": "extrude", "sketch": "base", "distance": "t"}]
    for i in range(holes):
        features.extend([
            {"id": f"s{i}", "type": "sketch", "plane": "top",
             "elements": [{"shape": "circle", "diameter": 2,
                           "center": [4*i - 2*(holes-1), 0]}]},
            {"id": f"h{i}", "type": "extrude", "sketch": f"s{i}",
             "operation": "cut", "distance": 3}])
    return {"format": "skodacad", "version": 24, "name": f"P8 historie {2+2*holes}",
            "parameters": {"t": 10}, "features": features}


def assembly_data(count):
    return {"format": "skodacad", "kind": "assembly", "version": 29,
            "name": f"P8 sestava {count}", "units": "mm", "parameters": {"pitch": 20},
            "components": [{"id": f"c{i}", "source": {"path": "box.json"},
                            "placement": {"position": [f"{i%40}*pitch", (i//40)*20, 0],
                                          "rotation": [0, 0, 0]}} for i in range(count)]}


def make_assembly(folder, count):
    box = history_data(0)
    box["features"][0]["elements"][0].update(width=10, height=10)
    write(folder / "box.json", box)
    return write(folder / "assembly.json", assembly_data(count))


def make_constraints(folder, groups):
    """Nezávislé skupiny šesti dílů a sedmi vazeb; není to jedna velká soustava rovnic."""
    import copy
    import shutil

    shutil.copytree(ROOT / "examples/sestavy", folder / "sestavy")
    shutil.copy(ROOT / "examples/krabicka.json", folder / "krabicka.json")
    sample = json.loads((folder / "sestavy/krabicka_s_vazbami.json").read_text(encoding="utf-8"))
    data = {**sample, "components": [], "constraints": []}
    for i in range(groups):
        for raw in sample["components"]:
            c = copy.deepcopy(raw)
            c["id"] = f"g{i}_{c['id']}"
            c["placement"]["position"][0] += 150*i
            data["components"].append(c)
        for raw in sample["constraints"]:
            c = copy.deepcopy(raw)
            c["id"] = f"g{i}_{c['id']}"
            for side in ("a", "b"):
                c[side]["component"] = f"g{i}_{c[side]['component']}"
            data["constraints"].append(c)
    return write(folder / "sestavy/many.json", data)


class Sampler:
    """Vzorkované RSS, odděleně rodič a každý worker; časování zahrnuje tuto režii."""
    def __init__(self):
        self.workers = lambda: []
        self.samples = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._start = 0.

    def _sample(self):
        from skodacad.step_task import _resident_bytes

        pids = {os.getpid(), *self.workers()}
        self.samples.append({"at_s": time.perf_counter()-self._start,
                             "rss_bytes": {str(pid): _resident_bytes(pid) for pid in pids}})

    def _run(self):
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(.1)

    def __enter__(self):
        self._start = time.perf_counter()
        self._sample()
        self._thread.start()
        return self

    def __exit__(self, *_args):
        self._stop.set()
        self._thread.join(timeout=5)
        self._sample()

    def report(self):
        peaks = {}
        for sample in self.samples:
            for pid, value in sample["rss_bytes"].items():
                if value is not None:
                    peaks[pid] = max(peaks.get(pid, 0), value)
        totals = [sum(s["rss_bytes"].values()) for s in self.samples
                  if s["rss_bytes"] and all(v is not None for v in s["rss_bytes"].values())]
        return {"parent_pid": os.getpid(), "observed_peak_rss_bytes": peaks,
                "observed_pool_peak_rss_bytes": max(totals) if totals else None,
                "samples": self.samples, "requested_interval_s": .1}


def measure(name, operation, inspect, repeats):
    expected = inspect(operation())
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        outcome = operation()
        samples.append(time.perf_counter()-start)
        if inspect(outcome) != expected:
            raise RuntimeError(f"Nestálý výsledek {name}")
    return {"name": name, "warmups": 1, "samples_s": samples,
            "median_s": statistics.median(samples), "min_s": min(samples),
            "max_s": max(samples), "correctness": expected}


def inspect_history(result, holes, thickness=10):
    expected = (4*holes+8)*20*thickness - holes*math.pi*3
    if (not result.ok or result.part is None or not result.part.is_valid
            or len(result.part.solids()) != 1
            or not math.isclose(result.part.volume, expected, rel_tol=1e-8, abs_tol=1e-6)
            or len(result.statuses) != 2+2*holes):
        raise RuntimeError("Historie nedává platný analytický objem nebo úplný počet prvků")
    return {"features": len(result.statuses), "holes": holes, "solids": 1,
            "volume_mm3": round(result.part.volume, 6), "parts_before": len(result.parts_before),
            "faces": len(result.part.faces())}


def inspect_assembly(result, count, constraints=0):
    if (not result.complete or len(result.instances) != count
            or len(result.constraints) != constraints):
        raise RuntimeError("Neúplná sestava nebo nesplněné vazby")
    if not constraints and not math.isclose(result.volume_mm3, count*1000, abs_tol=1e-6):
        raise RuntimeError("Objem kopií sestavy neodpovídá vzorci")
    if not all(i.part.is_valid for i in result.instances):
        raise RuntimeError("Sestava obsahuje neplatné těleso")
    return {"instances": count, "constraints_ok": constraints,
            "volume_mm3": round(result.volume_mm3, 6)}


def worker_pids(runner):
    active = runner._active
    return [w.process.pid for w in [*runner._idle, *([active] if active else [])]
            if w.process.pid is not None]


def worker_case(folder, repeats, memory):
    from skodacad import Document
    from skodacad.session import ModelSession
    from skodacad.worker import BackgroundRebuilder

    start = time.perf_counter()
    runner = BackgroundRebuilder()
    memory.workers = lambda: worker_pids(runner)
    session = ModelSession(runner=runner)
    path = write(folder / "history.json", history_data(30))
    session.open(path)
    if not session.wait(timeout=150) or session.failure:
        raise RuntimeError(f"Studený worker nedokončil: {session.failure}")
    cold_s = time.perf_counter()-start
    inspect_history(session.result, 30)
    try:
        def rebuild_and_receive():
            session.rebuild()
            if not session.wait(timeout=150) or session.failure:
                raise RuntimeError(f"Worker nedokončil: {session.failure}")
            return session.result

        measured = measure("warm-worker-rebuild-receive", rebuild_and_receive,
                           lambda r: inspect_history(r, 30), repeats)
        # Oba procesy už absolvovaly přepočet; nerušíme pouhé první načítání knihoven.
        # Běžný rebuild průběžné zprávy neposílá. Požadavek po 100 ms není mez rychlosti.
        heavy = Document.from_dict(history_data(120))
        runner.submit(heavy.to_dict())
        time.sleep(.1)
        item = runner.poll()
        if item is not None:
            if item.error:
                raise RuntimeError(item.error)
            if item.result is not None:
                inspect_history(item.result, 120)
                return [measured], {"first_worker_open_receive_s": cold_s,
                                    "cancel_after_submit_s": None,
                                    "note": "Úloha skončila před požadavkem Zastavit; "
                                            "rychlost není chyba a rušení zde není změřené."}
        cancelled_process = runner._active.process
        cancelled_pid = cancelled_process.pid
        start = time.perf_counter()
        runner.cancel()
        cancel_s = time.perf_counter()-start
        if cancelled_process.is_alive():
            raise RuntimeError("Zrušený pracovní proces zůstal živý")
        start = time.perf_counter()
        recovery = rebuild_and_receive()
        recovery_s = time.perf_counter()-start
        inspect_history(recovery, 30)
        return [measured], {"first_worker_open_receive_s": cold_s,
                             "cancel_after_submit_s": cancel_s,
                             "requested_cancel_wait_s": .1,
                             "cancelled_pid": cancelled_pid,
                             "recovery_s": recovery_s,
                             "recovery_geometry_ok": True, "child_pids": worker_pids(runner)}
    finally:
        runner.close()


def step_case(folder, repeats, memory):
    from skodacad.session import ModelSession
    from skodacad.step_task import StepTask

    session = ModelSession()
    session.open(write(folder / "history.json", history_data(60)))
    path = session.export(folder / "part.step")
    data = path.read_bytes()
    pids = []
    memory.workers = lambda: list(pids)

    def import_step():
        task = StepTask(data, timeout=150)
        pids[:] = [task._process.pid]
        try:
            deadline = time.monotonic()+155
            while time.monotonic() < deadline:
                outcome = task.poll()
                if outcome is not None:
                    if outcome.error:
                        raise RuntimeError(outcome.error)
                    return outcome
                time.sleep(.002)
            raise RuntimeError("STEP worker nedokončil")
        finally:
            task.cancel()
            pids.clear()

    def inspect(outcome):
        facts = outcome.facts
        expected = 248*20*10-60*math.pi*3
        if (facts.solids != 1 or not outcome.shape_bytes or facts.unit != "millimetre"
                or not math.isclose(facts.volume_mm3, expected, abs_tol=1e-5)
                or any(not math.isclose(a, b, abs_tol=1e-5) for a, b in zip(
                    facts.bounds_mm, (-124, -10, 0, 124, 10, 10), strict=True))):
            raise RuntimeError("STEP změnil objem, jednotky, tělesa nebo rozměry")
        return {"solids": 1, "volume_mm3": round(facts.volume_mm3, 6),
                "step_bytes": len(data), "shape_bytes": len(outcome.shape_bytes)}

    return [measure("step-worker-import-receive", import_step, inspect, repeats)], {
        "step_input_sha256": digest(path), "step_geometry": "60 slepých válcových kapes"}


def ndt_case(folder, repeats):
    from skodacad.ndt import mt, pt
    from skodacad.session import ModelSession

    session = ModelSession()
    path = ROOT / "examples/ndt/kapsa.json"
    session.open(path)
    session.set_ndt_pt_settings("s2", {"step_mm": 12})
    session.set_ndt_mt_settings("s3", {"step_mm": 12, "center_step_mm": 24,
                                     "apply": False, "inspect": False})
    write(folder / "configured-ndt.json", session.document.to_dict())
    before, result = session.document.to_dict(), session.result

    def compute():
        return session.compute_ndt_pt("s2"), session.compute_ndt_mt("s3")

    def inspect(maps):
        summary = []
        for map_, module, area in zip(maps, (pt, mt), (4700, 1200), strict=True):
            if not map_.samples or not math.isfinite(map_.total_area) or map_.total_area <= 0:
                raise RuntimeError("NDT mapa nemá platné vzorky nebo plochu")
            if not math.isclose(map_.total_area, area, abs_tol=1e-6):
                raise RuntimeError("Cílová plocha NDT mapy neodpovídá analytické kapse")
            if any(s.state not in module.STATES for s in map_.samples):
                raise RuntimeError("Neznámý stav NDT vzorku")
            summary.append({"algorithm": module.ALGORITHM, "samples": len(map_.samples),
                            "total_area_mm2": round(map_.total_area, 6),
                            "area_by_state_mm2": {state: round(map_.area(state), 6)
                                                  for state in module.STATES}})
        if session.document.to_dict() != before or session.result is not result:
            raise RuntimeError("Výpočet NDT změnil model")
        return {"maps": summary, "source_model_unchanged": True}

    return [measure("pt-and-mt-geometric-maps", compute, inspect, repeats)], {
        "reference": "ndt/kapsa.json", "pt_step_mm": 12, "mt_step_mm": 12,
        "mt_center_step_mm": 24, "mt_apply": False, "mt_inspect": False,
        "note": "Geometrická přístupnost, nikoli odborná nebo fyzická validace NDT."}


def run_child(case, folder, repeats):
    start = time.perf_counter()
    from skodacad import Document, rebuild
    from skodacad.assembly_build import Cache, build
    from skodacad.assembly_session import AssemblySession

    imported_s = time.perf_counter()-start
    metrics, details = [], {}
    with Sampler() as memory:
        if case == "startup":
            details = {"cad_import_s": imported_s, "note": "nový proces, bez okna a bez modelu"}
        elif case.startswith("history-"):
            import pickle

            from skodacad.worker import decode_result, encode_result

            holes = int(case.split("-")[1])
            data = history_data(holes)
            write(folder / "history.json", data)
            doc = Document.from_dict(data)
            original = doc.to_dict()
            metrics.append(measure("full-rebuild", lambda: rebuild(doc),
                                   lambda r: inspect_history(r, holes), repeats))
            reference = rebuild(doc)

            def transfer():
                payload = pickle.dumps(encode_result(reference))
                return len(payload), decode_result(pickle.loads(payload))

            metrics.append(measure("encode-pickle-decode", transfer,
                                   lambda r: {"payload_bytes": r[0],
                                              **inspect_history(r[1], holes)}, repeats))
            if doc.to_dict() != original:
                raise RuntimeError("Měření změnilo zdrojový recept")
        elif case.startswith(("assembly-", "constraints-")):
            constrained = case.startswith("constraints-")
            size = int(case.split("-")[1])
            path = make_constraints(folder, size) if constrained else make_assembly(folder, size)
            session = AssemblySession()
            session.open(path)
            count, constraints = (6*size, 7*size) if constrained else (size, 0)
            def inspect(result):
                return inspect_assembly(result, count, constraints)

            metrics.append(measure("fresh-geometry-cache-build",
                                   lambda: build(session.assembly, path, Cache()),
                                   inspect, repeats))
            metrics.append(measure("warm-cache-rebuild", session.rebuild, inspect, repeats))
            before, result = session.assembly.to_dict(), session.result
            parameters = {"mezera": 12.5} if constrained else {"pitch": 21}
            metrics.append(measure("parameter-preview",
                                   lambda: session.preview_parameters(parameters),
                                   lambda p: inspect(p.result), repeats))
            if session.assembly.to_dict() != before or session.result is not result:
                raise RuntimeError("Náhled změnil původní sestavu")
            if not constrained and size == 200:
                from build123d import import_step

                export = folder / "assembly.step"

                def inspect_step(path):
                    part = import_step(path)
                    if (not part.is_valid or len(part.solids()) != size
                            or not math.isclose(part.volume, size*1000, abs_tol=1e-6)):
                        raise RuntimeError("STEP nepřenesl všechny kopie a jejich objem")
                    return {"solids": size, "volume_mm3": round(part.volume, 6)}

                metrics.append(measure("step-export", lambda: session.export_step(export),
                                       inspect_step, repeats))
                details["step_bytes"] = export.stat().st_size
        elif case == "worker":
            metrics, details = worker_case(folder, repeats, memory)
        elif case == "step-history":
            metrics, details = step_case(folder, repeats, memory)
        elif case == "ndt-multi":
            metrics, details = ndt_case(folder, repeats)
        elif case.startswith("gui-"):
            from benchmark_p8_gui import gui_case

            metrics, details = gui_case(case, folder, repeats, memory, case_started=start)
        else:
            raise ValueError(case)
    return {"case": case, "cad_import_s": imported_s, "metrics": metrics, "details": details,
            "memory": memory.report(), "input_sha256": {
                p.relative_to(folder).as_posix(): digest(p) for p in folder.rglob("*.json")
                if p.name not in ("result.json", "okno.json", "nastaveni.json")}}


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=15, check=False)
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=15)


def processor_name():
    if sys.platform == "darwin":
        return subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"],
                                       text=True, timeout=5).strip()
    return platform.processor()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cases", default=",".join(CASES))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--child", choices=CASES)
    parser.add_argument("--folder", type=Path)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10 or not 1 <= args.timeout <= 600:
        parser.error("Opakování 1–10 a ochranný timeout 1–600 sekund")
    if args.child:
        write(args.folder / "result.json", run_child(args.child, args.folder, args.repeats))
        return 0
    cases = args.cases.split(",")
    if not args.output or any(c not in CASES for c in cases) or len(set(cases)) != len(cases):
        parser.error("Zadej nový --output a známé, neopakující se --cases")
    output = args.output.resolve()
    evidence = output.with_suffix("")
    if output.exists() or evidence.exists():
        parser.error("Výstup nebo složka evidence již existuje; zvol nové jméno")
    evidence.mkdir(parents=True)
    sources = {p.relative_to(ROOT).as_posix(): digest(p) for p in (ROOT / "src").rglob("*.py")
               if p.name != "_build.py"}
    examples = {p.relative_to(ROOT).as_posix(): digest(p)
                for p in (ROOT / "examples").rglob("*.json")}
    report = {"schema": "skodacad-p8.1-v1", "created_utc": datetime.now(UTC).isoformat(),
              "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                 text=True).strip(),
              "source_sha256": hashlib.sha256(
                  json.dumps(sources, sort_keys=True).encode()).hexdigest(),
              "benchmark_sha256": digest(Path(__file__)),
              "gui_benchmark_sha256": digest(Path(__file__).with_name("benchmark_p8_gui.py")),
              "examples_sha256": examples,
              "environment": {"python": platform.python_version(), "system": platform.system(),
                              "release": platform.release(), "machine": platform.machine(),
                              "logical_cpus": os.cpu_count(),
                              "processor": processor_name(),
                              "load_average": (os.getloadavg()
                                               if hasattr(os, "getloadavg") else None),
                              "thread_env": {k: os.environ.get(k) for k in
                                             ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                              "MKL_NUM_THREADS", "QT_QPA_PLATFORM", "QT_OPENGL")},
                              "packages": {d.metadata["Name"]: d.version
                                           for d in importlib.metadata.distributions()
                                           if any(token in d.metadata["Name"].lower() for token in
                                                  ("build123d", "ocp", "pyside6", "numpy"))}},
              "repeats": args.repeats, "case_timeout_s": args.timeout, "results": [],
              "limits": ["Časy nemají práh úspěchu; timeout chrání stroj před zaseknutím.",
                         "Každý případ je nový Python proces; OS a diskové cache se nemažou.",
                         "1 zahřátí a N měření operací; validace je mimo měřený čas.",
                         "RSS je vzorkované po 100 ms; krátké špičky mohou chybět.",
                         "RSS rodiče/workery odděleně; maxima nejsou součtem ve stejný čas.",
                         "Vzorkování paměti má režii, zahrnutou do časů.",
                         "Součet RSS čte procesy postupně; nezahrnuje GPU ani jiné aplikace.",
                         "Porovnávat jen stejný scénář, stroj, knihovny a zatížení.",
                         "Syntetické historie a kopie nenahrazují reálné modely autora.",
                         "Skupiny vazeb jsou nezávislé, neměří jednu velkou spojenou soustavu."]}
    for case in cases:
        runs = range(args.repeats) if case == "startup" else range(1)
        for index in runs:
            name = f"{case}-{index}" if case == "startup" else case
            folder = evidence / name
            folder.mkdir()
            env = {**os.environ, "SKODACAD_HOME": str(folder / "profile")}
            command = [sys.executable, str(Path(__file__).resolve()), "--child", case,
                       "--folder", str(folder), "--repeats", str(args.repeats)]
            started = time.perf_counter()
            with (folder / "process.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env,
                                           start_new_session=os.name != "nt")
                try:
                    code = process.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    stop_process(process)
                    code = "timeout"
            elapsed = time.perf_counter()-started
            if code == 0 and (folder / "result.json").is_file():
                result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
                result.update(status="ok", child_process_wall_s=elapsed)
            else:
                result = {"case": case, "status": "failed", "exit": code,
                          "child_process_wall_s": elapsed, "log": f"{name}/process.log"}
            report["results"].append(result)
            print(f"{name}: {result['status']} ({elapsed:.3f} s)", flush=True)
            if result["status"] == "ok":
                memory = result["memory"]
                summary = {k: result[k] for k in ("case", "cad_import_s", "metrics", "details")}
                summary["observed_parent_peak_rss_bytes"] = memory[
                    "observed_peak_rss_bytes"].get(str(memory["parent_pid"]))
                summary["observed_pool_peak_rss_bytes"] = memory["observed_pool_peak_rss_bytes"]
                print("P81_CASE " + json.dumps(summary, ensure_ascii=False), flush=True)
    if any(digest(ROOT / name) != sha for name, sha in sources.items()):
        raise RuntimeError("Produkční zdroj se během měření změnil")
    if any(digest(ROOT / name) != sha for name, sha in examples.items()):
        raise RuntimeError("Původní ukázka se během měření změnila")
    if (digest(Path(__file__)) != report["benchmark_sha256"]
            or digest(Path(__file__).with_name("benchmark_p8_gui.py"))
            != report["gui_benchmark_sha256"]):
        raise RuntimeError("Měřič se během běhu změnil; tento běh není srovnávací evidence")
    write(output, report)
    print("P81_ENV " + json.dumps({k: report[k] for k in
                                  ("environment", "commit", "source_sha256", "benchmark_sha256",
                                   "gui_benchmark_sha256")}, ensure_ascii=False), flush=True)
    return 0 if all(r["status"] == "ok" for r in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
