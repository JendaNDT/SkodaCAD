"""P8.5: předem uložené rozpočty nad skutečnými cykly P8.4 a Qt časovačem.

python tests/budget_p8.py --profile author-m4 --output out/p85.json
Původní fyzikální měřiče a zmrazené limity zůstávají beze změny. Výstup se nepřepisuje.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import benchmark_p8 as baseline
import soak_p8 as soak

POLICY = baseline.ROOT / "tests/p85-budgets.json"
MIB = 1024**2
GAP_BOUNDS = (.05, .075, .1, .15, .25, .5, 1., 2., 3., 5., 10.)


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def percentile(values, fraction=.95):
    if not values or not all(positive(x) for x in values):
        raise ValueError("Časování musí být úplné, konečné a kladné")
    return sorted(values)[math.ceil(len(values)*fraction)-1]


class LoopProbe:
    """Pauzy doručování skutečného Qt časovače; pevný histogram, žádný rostoucí seznam."""
    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.last = None
        self.count = 0
        self.maximum = self.total = 0.
        self.buckets = [0]*(len(GAP_BOUNDS)+1)

    def start(self):
        self.last = self.clock()

    def tick(self):
        now = self.clock()
        gap = now-self.last
        if not positive(gap):
            raise ValueError("Čas Qt sondy není monotónní")
        self.last = now
        self.count += 1
        self.total += gap
        self.maximum = max(self.maximum, gap)
        bucket = next((i for i, bound in enumerate(GAP_BOUNDS) if gap <= bound),
                      len(GAP_BOUNDS))
        self.buckets[bucket] += 1

    def report(self):
        return {"interval_s": .05, "count": self.count, "max_gap_s": self.maximum,
                "total_gap_s": self.total, "bounds_s": list(GAP_BOUNDS),
                "buckets": self.buckets}


def gap_p95(probe):
    count, buckets = probe["count"], probe["buckets"]
    if (probe.get("errors") or type(count) is not int or count < 100 or probe["interval_s"] != .05
            or probe["bounds_s"] != list(GAP_BOUNDS) or len(buckets) != len(GAP_BOUNDS)+1
            or any(type(x) is not int or x < 0 for x in buckets) or sum(buckets) != count
            or not positive(probe["max_gap_s"]) or not positive(probe["total_gap_s"])):
        raise ValueError("Neúplná sonda obsluhy okna")
    maximum = probe["max_gap_s"]
    if not maximum <= probe["total_gap_s"] <= count*maximum:
        raise ValueError("Rozporný součet časování Qt")
    max_bucket = next((i for i, bound in enumerate(GAP_BOUNDS) if maximum <= bound),
                      len(GAP_BOUNDS))
    if not buckets[max_bucket] or any(buckets[max_bucket+1:]):
        raise ValueError("Histogram neodpovídá nejdelší pauze Qt")
    cumulative = 0
    for index, n in enumerate(buckets):
        cumulative += n
        if cumulative >= math.ceil(count*.95):
            return min(GAP_BOUNDS[index], maximum) if index < len(GAP_BOUNDS) else maximum
    raise ValueError("Chybí percentil Qt")


def manifest():
    result = soak.manifest()
    for path in (Path(__file__).resolve(), POLICY):
        result[str(path.relative_to(baseline.ROOT))] = baseline.digest(path)
    return result


def evaluate(report, policy, profile):
    """Nekalibruje limity podle kandidáta; chybějící důkaz je chyba, překročení FAIL."""
    if (report["schema"] != "skodacad-p8.5-v1" or report["status"] != "ok"
            or report["exit"] != 0 or report["cycles"] != 20 or report["warmups"] != 2
            or report.get("failure") or report.get("evidence_error")):
        raise ValueError("P8.5 potřebuje úspěšný úplný nativní běh 2 + 20")
    if policy["schema"] != "skodacad-p8.5-budgets-v1":
        raise ValueError("Neznámá verze rozpočtů")
    budget = policy["profiles"][profile]
    environment = report["footer"]["environment"]
    if (not environment["system"].startswith(budget["system_prefix"])
            or (budget.get("cpu") and environment["cpu"] != budget["cpu"])):
        raise ValueError("Zařízení neodpovídá zvolenému profilu")
    rows, footer = report["events"], report["footer"]
    if not positive(report["wall_s"]) or rows[-1]["at_s"] > report["wall_s"]:
        raise ValueError("Rozporný celkový čas")
    soak.validate_runtime(rows, footer, 20, 2)
    summary = soak.summarize(rows, 20, 2)
    durations = {phase: [] for phase in soak.PHASES}
    previous = 0.
    cycles = {}
    for row in rows:
        at = row["at_s"]
        if not positive(at) or at <= previous:
            raise ValueError("Nemonotónní čas pracovních kroků")
        delta = at-previous
        if row.get("warmup") is False:
            durations[row["phase"]].append(delta)
            cycles[row["cycle"]] = cycles.get(row["cycle"], 0.)+delta
        previous = at
    if any(len(v) != 20 for v in durations.values()):
        raise ValueError("Neúplné časování pracovních kroků")
    memory = footer["memory"]
    if (memory["sample_count"] < len(rows) or memory["requested_interval_s"] != .5
            or not 0 <= memory["missing_worker_samples"] <= memory["sample_count"]
            or memory["limit_bytes"] != 3072*MIB):
        raise ValueError("Změněný nebo neúplný dohled RSS")
    peak = memory["observed_pool_peak_rss_bytes"]
    if not positive(peak) or peak > memory["limit_bytes"]:
        raise ValueError("Nativní běh překročil ochrannou mez")
    parent_peak = memory["observed_peak_rss_bytes"][str(memory["parent_pid"])]
    if not positive(parent_peak) or parent_peak > peak:
        raise ValueError("Rozporné maximum rodiče")
    for row in rows:
        if row["memory"]["parent_pid"] != memory["parent_pid"]:
            raise ValueError("Neshodné PID hlavního procesu")
        if row["memory"]["total_rss_bytes"] > peak:
            raise ValueError("Vzorkované maximum je nižší než kontrolní bod")
        for pid, value in row["memory"]["rss_bytes"].items():
            if memory["observed_peak_rss_bytes"].get(pid, 0) < value:
                raise ValueError("Maximum PID je nižší než kontrolní bod")
    metrics = {}
    limits = {}
    for phase, values in durations.items():
        metrics[f"{phase}.p95_s"] = percentile(values)
        metrics[f"{phase}.max_s"] = max(values)
        limits[f"{phase}.p95_s"] = budget["phase_p95_s"][phase]
        limits[f"{phase}.max_s"] = budget["phase_p95_s"][phase]*1.5
    metrics.update({"cycle.p95_s": percentile(list(cycles.values())),
                    "parent.peak_mib": parent_peak/MIB, "processes.peak_mib": peak/MIB,
                    "parent.growth_mib": summary["parent_cycle_end_rss"]["change_bytes"]/MIB,
                    "parent.slope_mib_per_cycle":
                        summary["parent_cycle_end_rss"]["median_pairwise_bytes_per_cycle"]/MIB,
                    "qt.p95_gap_s": gap_p95(report["qt_probe"]),
                    "qt.max_gap_s": report["qt_probe"]["max_gap_s"]})
    limits.update(budget["limits"])
    if set(metrics) != set(limits) or not all(positive(v) for v in limits.values()):
        raise ValueError("Neúplné nebo neplatné rozpočty")
    checks = [{"metric": name, "actual": value, "limit": limits[name],
               "ok": math.isfinite(value) and value <= limits[name]}
              for name, value in metrics.items()]
    return {"profile": profile, "status": "pass" if all(c["ok"] for c in checks) else "fail",
            "checks": checks, "summary": summary,
            "phase_medians_s": {k: statistics.median(v) for k, v in durations.items()}}


def child(folder):
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    probe, timer, errors = LoopProbe(), QTimer(), []
    timer.setTimerType(Qt.TimerType.PreciseTimer)

    def tick():
        try:
            probe.tick()
        except Exception as exc:  # Qt slot nesmí tiše spolknout chybu sondy
            errors.append(str(exc))
            timer.stop()

    def start():
        probe.start()
        timer.start(50)

    timer.timeout.connect(tick)
    QTimer.singleShot(0, start)
    try:
        soak.child(folder, 20, 2, 3072*MIB)
    finally:
        timer.stop()
        # Zahrnuje i poslední doručení až do konce běžné obsluhy a úklidu procesu.
        if probe.last is not None:
            probe.tick()
        baseline.write(folder / "qt-probe.json", {**probe.report(), "errors": errors})
    if errors:
        raise RuntimeError(str(errors))
    del app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", choices=("author-m4", "ci-macos", "ci-windows"))
    parser.add_argument("--child", type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child)
        return 0
    if (not args.output or not args.profile or args.output.exists()
            or args.output.with_suffix("").exists()):
        parser.error("Zadej profil a nový výstup; existující evidenci nelze přepsat")
    folder = args.output.resolve().with_suffix("")
    folder.mkdir(parents=True)
    before, started = manifest(), time.perf_counter()
    env = {**os.environ, "SKODACAD_HOME": str(folder / "profile")}
    with (folder / "process.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                    "--child", str(folder)], stdout=log, stderr=subprocess.STDOUT,
                                   env=env, start_new_session=os.name != "nt")
        try:
            code = process.wait(timeout=2400)
        except subprocess.TimeoutExpired:
            baseline.stop_process(process)
            code = "timeout"
    rows, error = soak.read_events(folder / "events.jsonl")
    report = {"schema": "skodacad-p8.5-v1", "commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=baseline.ROOT, text=True).strip(),
        "created_utc": datetime.now(UTC).isoformat(), "cycles": 20, "warmups": 2,
        "profile": args.profile, "exit": code, "status": "failed", "events": rows,
        "hashes": before, "policy_sha256": baseline.digest(POLICY),
        "wall_s": time.perf_counter()-started, "launcher_system": platform.platform()}
    try:
        if code != 0 or error or manifest() != before:
            raise ValueError(error or "Proces, manifest nebo úplnost zkoušky selhaly")
        report["footer"] = json.loads((folder / "footer.json").read_text(encoding="utf-8"))
        report["qt_probe"] = json.loads((folder / "qt-probe.json").read_text(encoding="utf-8"))
        if report["qt_probe"]["errors"]:
            raise ValueError("Sonda Qt ohlásila chybu")
        report["status"] = "ok"
        report["evaluation"] = evaluate(report, json.loads(POLICY.read_text()), args.profile)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        report.update(status="failed", evidence_error=str(exc))
    baseline.write(args.output, report)
    print("P85_ENV "+json.dumps({"commit": report["commit"], "hashes": before}))
    print("P85_RESULT "+json.dumps({k: v for k, v in report.items()
                                   if k not in ("events", "hashes", "footer")}, ensure_ascii=False))
    return 0 if report["status"] == "ok" and report["evaluation"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
