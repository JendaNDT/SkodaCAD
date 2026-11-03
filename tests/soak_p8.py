"""P8.4: dlouhý nativní provoz v jednom procesu, RSS rodiče i jeho workerů.

python tests/soak_p8.py --output out/p84.json --cycles 20 --warmups 2
Paměť se zaznamenává před diagnostickým GC; měřič neukládá vzorky do rostoucího seznamu.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import os
import statistics
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import benchmark_p8 as baseline
from profile_p8 import hashes

ROOT = baseline.ROOT
PHASES = ("open", "edit-undo-redo", "save-reopen", "cancel-recover", "crash-recover",
          "step-limit-recover", "assembly-preview-close", "cycle-end")


class Memory:
    """Současné RSS a vzorkovaná maxima, bez uchovávání všech průběžných vzorků."""
    def __init__(self, limit_bytes, reader=None, processes=None):
        from skodacad.step_task import _resident_bytes

        self.reader = reader or _resident_bytes
        self.processes = processes or (
            lambda: [p.pid for p in multiprocessing.active_children() if p.is_alive()])
        self.limit_bytes = limit_bytes
        self.parent = os.getpid()
        self.peaks = {}
        self.pool_peak = self.samples = self.missing_worker_samples = 0
        self.error = ""
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, name="p84-rss", daemon=True)

    def sample(self):
        pids = {self.parent, *self.processes()}
        values = {str(pid): self.reader(pid) for pid in pids}
        if values[str(self.parent)] is None:
            raise RuntimeError("Nelze změřit RSS hlavního procesu")
        complete = all(value is not None for value in values.values())
        total = sum(values.values()) if complete else None
        with self.lock:
            self.samples += 1
            self.missing_worker_samples += not complete
            for pid, value in values.items():
                if value is not None:
                    self.peaks[pid] = max(self.peaks.get(pid, 0), value)
            if total is not None:
                self.pool_peak = max(self.pool_peak, total)
                if total > self.limit_bytes:
                    self.error = "Měřený součet RSS překročil ochranný rozpočet zkoušky"
        return {"parent_pid": self.parent, "rss_bytes": values, "total_rss_bytes": total,
                "worker_count": len(pids)-1}

    def run(self):
        while not self.stop.wait(.5):
            try:
                self.sample()
            except Exception as exc:  # noqa: BLE001 -- dohled nesmí tiše přestat měřit
                self.error = f"Měření RSS selhalo: {exc}"
                return

    def check(self):
        if self.error:
            raise RuntimeError(self.error)

    def __enter__(self):
        self.sample()
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.stop.set()
        self.thread.join(timeout=5)

    def report(self):
        with self.lock:
            return {"parent_pid": self.parent, "sample_count": self.samples,
                    "missing_worker_samples": self.missing_worker_samples,
                    "observed_peak_rss_bytes": dict(self.peaks),
                    "observed_pool_peak_rss_bytes": self.pool_peak,
                    "requested_interval_s": .5, "limit_bytes": self.limit_bytes,
                    "error": self.error}


def trend(points):
    """Popisná změna a medián párových sklonů, nikoli test významnosti nebo práh úniku."""
    if len(points) < 2:
        raise ValueError("Pro trend jsou potřeba alespoň dva cykly")
    count = max(1, len(points)//3)
    first = statistics.median(value for _, value in points[:count])
    last = statistics.median(value for _, value in points[-count:])
    slopes = [(b-a)/(j-i) for k, (i, a) in enumerate(points)
              for j, b in points[k+1:] if j > i]
    return {"cycles": len(points), "first_third_median_bytes": first,
            "last_third_median_bytes": last, "change_bytes": last-first,
            "median_pairwise_bytes_per_cycle": statistics.median(slopes)}


def summarize(events, cycles, warmups):
    rows = [e for e in events if e["phase"] == "cycle-end" and not e["warmup"]]
    if len(rows) != cycles or [r["cycle"] for r in rows] != list(range(warmups, warmups+cycles)):
        raise ValueError("Chybějí dokončené měřené cykly")
    for cycle in range(warmups+cycles):
        selected = [e for e in events if e.get("cycle") == cycle]
        actual = [e["phase"] for e in selected]
        if actual != list(PHASES):
            raise ValueError("Cyklus neprovedl všechny operace ve správném pořadí")
        if any(e["warmup"] != (cycle < warmups) for e in selected):
            raise ValueError("Nesprávně označené zahřívací cykly")
    points = [(e["cycle"], e["memory"]["rss_bytes"][str(e["memory"]["parent_pid"])])
              for e in rows]
    if any(value is None or value <= 0 for _, value in points):
        raise ValueError("Chybí kladné RSS hlavního procesu")
    return {"parent_cycle_end_rss": trend(points),
            "cycle_end_worker_counts": [e["memory"]["worker_count"] for e in rows],
            "cycle_end_assembly_windows": [e["resources"]["assembly_windows"] for e in rows],
            "note": "RSS může zůstat alokované knihovně. "
                    "Trend sám neprokazuje únik ani jeho absenci."}


def validate_runtime(events, footer, cycles, warmups):
    """Ověří provedené případy i skutečně uvolněné prostředky, bez prahu trendu RSS."""
    def check(condition, message):
        if not condition:
            raise ValueError(message)

    check(footer["cycles_completed"] == cycles and footer["warmups_completed"] == warmups
          and footer["events"] == len(events) == 4+(cycles+warmups)*len(PHASES),
          "Nesouhlasí počet úplných pracovních cyklů")
    check(footer["native_view_ready"] and footer["owned_workers_dead"]
          and not footer["memory"]["error"], "Nativní pohled nebo úklid procesů selhal")
    check([e["phase"] for e in events if "cycle" not in e] == [
        "initial", "before-diagnostic-gc", "after-diagnostic-gc", "normal-close"],
        "Chybí oddělená diagnostika před/po GC a běžné zavření")
    check(events[-1]["memory"]["worker_count"] == 0
          and events[-1]["facts"]["owned_workers_dead"], "Po ukončení zůstal worker")
    for event in events:
        memory = event["memory"]
        values = memory["rss_bytes"]
        check(values and str(memory["parent_pid"]) in values
              and all(isinstance(v, int) and v > 0 for v in values.values())
              and memory["total_rss_bytes"] == sum(values.values())
              and memory["worker_count"] == len(values)-1, "Neúplné nebo rozporné RSS")
        if "cycle" not in event:
            continue
        facts, phase = event["facts"], event["phase"]
        if phase in ("open", "edit-undo-redo", "save-reopen", "cancel-recover",
                     "crash-recover", "cycle-end"):
            thickness = 10 if phase == "open" else 11 if phase in (
                "edit-undo-redo", "save-reopen") else 12
            check(facts["features"] == 122 and facts["holes"] == 60 and facts["solids"] == 1
                  and facts["faces"] == 126 and facts["parts_before"] == 122
                  and math.isclose(facts["volume_mm3"], 248*20*thickness-180*math.pi,
                                   abs_tol=1e-6), "Nesouhlasí fyzika historie")
        if phase == "cancel-recover":
            check(facts["cancelled_process_dead"], "Zrušený worker přežil")
        elif phase == "crash-recover":
            check(facts["crashed_process_dead"] and facts["error_shown"],
                  "Pád workeru nebyl skutečně zpracován")
        elif phase == "step-limit-recover":
            check(facts["limited_process_dead"] and facts["recovery_process_dead"]
                  and facts["limit_bytes"] == 1 and facts["payload_bytes"] > 0
                  and facts["step_bytes"] > 0 and facts["solids"] == 1
                  and math.isclose(facts["volume_mm3"], 248*20*12-180*math.pi, abs_tol=1e-6),
                  "STEP limit nebo obnova geometrie neprošly")
        elif phase == "assembly-preview-close":
            check(facts["instances"] == 800 and facts["volume_mm3"] == 800000
                  and facts["selection"] == "c799" and facts["native_view_ready"]
                  and facts["preview_native_ready"] and facts["cancel_model_unchanged"],
                  "Velká sestava nebo skutečný náhled neprošly")
            check(facts["assembly_pool_closed"] and len(facts["assembly_worker_pids"]) == 2
                  and set(facts["assembly_worker_pids"]).isdisjoint(map(int, values)),
                  "Po zavřené sestavě přežil její pomocný proces")
        elif phase == "cycle-end":
            actual = {int(pid) for pid in values if int(pid) != memory["parent_pid"]}
            check(memory["worker_count"] == 2 and actual == set(facts["owned_worker_pids"]),
                  "Na konci cyklu zůstal cizí worker nebo chybí pool hlavního dílu")
            check(event["resources"]["assembly_windows"] == 0
                  and event["resources"]["parameter_dialogs"] == 0,
                  "Po cyklu zůstalo zavřené okno nebo dialog")


def manifest():
    result = hashes()
    for name in ("tests/soak_p8.py", "tests/soak_p8_gui.py"):
        result[name] = baseline.digest(ROOT / name)
    return result


def child(folder, cycles, warmups, limit_bytes):
    from soak_p8_gui import run

    memory = Memory(limit_bytes)
    try:
        with memory:
            footer = run(folder, cycles, warmups, memory)
            memory.check()
    except BaseException as exc:
        baseline.write(folder / "failure.json", {
            "error": f"{type(exc).__name__}: {exc}", "memory": memory.report()})
        raise
    footer["memory"] = memory.report()
    baseline.write(folder / "footer.json", footer)


def read_events(path):
    """I po tvrdém timeoutu uchová úplné řádky; poškození nikdy není úspěch."""
    rows = []
    if path.exists():
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                return rows, f"Neúplný nebo poškozený řádek událostí {index}"
    return rows, ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--max-total-rss-mib", type=int, default=3072)
    parser.add_argument("--timeout", type=int, default=2400)
    parser.add_argument("--child", type=Path)
    args = parser.parse_args()
    if not (2 <= args.cycles <= 100 and 0 <= args.warmups <= 5
            and 256 <= args.max_total_rss_mib <= 8192 and 30 <= args.timeout <= 3600):
        parser.error("Cykly2–100, zahřátí0–5, rozpočet256–8192MiB a timeout30–3600s")
    if args.child:
        child(args.child, args.cycles, args.warmups, args.max_total_rss_mib*1024**2)
        return 0
    if not args.output or args.output.exists() or args.output.with_suffix("").exists():
        parser.error("Zadej nový výstup; existující evidenci nelze přepsat")
    output = args.output.resolve()
    folder = output.with_suffix("")
    folder.mkdir(parents=True)
    before = manifest()
    env = {**os.environ, "SKODACAD_HOME": str(folder / "profile")}
    command = [sys.executable, str(Path(__file__).resolve()), "--child", str(folder),
               "--cycles", str(args.cycles), "--warmups", str(args.warmups),
               "--max-total-rss-mib", str(args.max_total_rss_mib)]
    started = time.perf_counter()
    with (folder / "process.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   env=env, start_new_session=os.name != "nt")
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            baseline.stop_process(process)
            code = "timeout"
    events, evidence_error = read_events(folder / "events.jsonl")
    success = code == 0 and (folder / "footer.json").is_file() and not evidence_error
    report = {"schema": "skodacad-p8.4-v2", "commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "created_utc": datetime.now(UTC).isoformat(), "cycles": args.cycles,
        "warmups": args.warmups, "exit": code, "status": "ok" if success else "failed",
        "wall_s": time.perf_counter()-started, "hashes": before, "events": events,
        "limits": ["Jeden dlouho žijící nativní GUI proces, nikoli nové procesy pro každý cyklus.",
                   "Primární body jsou před vynuceným GC; diagnostické GC následuje po cyklech.",
                   "RSS čte procesy postupně; součet není unikátní fyzická paměť ani GPU paměť.",
                   "Vzorkovaná maxima mohou minout krátkou špičku; dohled není tvrdý OS limit.",
                   "Omezené cykly nenahrazují celodenní provoz či přejímku na cizích modelech."]}
    if evidence_error:
        report["evidence_error"] = evidence_error
    if (folder / "failure.json").exists():
        report["failure"] = json.loads((folder / "failure.json").read_text(encoding="utf-8"))
    if success:
        report["footer"] = json.loads((folder / "footer.json").read_text(encoding="utf-8"))
        try:
            report["summary"] = summarize(events, args.cycles, args.warmups)
            validate_runtime(events, report["footer"], args.cycles, args.warmups)
        except (ValueError, KeyError, TypeError) as exc:
            report.update(status="failed", evidence_error=str(exc))
            success = False
    if manifest() != before:
        raise RuntimeError("Zdroje nebo měřiče se během zkoušky změnily")
    baseline.write(output, report)
    print("P84_RESULT " + json.dumps({key: value for key, value in report.items()
                                     if key not in ("events", "hashes")}, ensure_ascii=False),
          flush=True)
    print("P84_ENV " + json.dumps({"commit": report["commit"], "hashes": before},
                                 ensure_ascii=False), flush=True)
    if not success:
        print((folder / "process.log").read_text(encoding="utf-8")[-12000:], flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
