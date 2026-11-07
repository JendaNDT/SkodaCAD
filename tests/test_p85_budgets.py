"""Rozpočty nesmějí přijmout neúplnou geometrii, chybějící měření ani pomalý výsledek."""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from budget_p8 import GAP_BOUNDS, POLICY, LoopProbe, evaluate, gap_p95, percentile


@pytest.fixture
def report():
    # Skutečná neměnná P8.4 fyzikální evidence; Qt data jsou pouze syntetická jednotková fixture.
    path = POLICY.parents[1]/"docs/baselines/p8-4-macos-arm64-pool-release.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(schema="skodacad-p8.5-v1", qt_probe={
        "interval_s": .05, "count": 1000, "max_gap_s": .06, "total_gap_s": 60.,
        "bounds_s": list(GAP_BOUNDS), "buckets": [0, 1000]+[0]*(len(GAP_BOUNDS)-1),
        "errors": []})
    return data


def policy():
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_complete_native_facts_can_be_evaluated_without_mutation(report):
    before = copy.deepcopy(report)
    result = evaluate(report, policy(), "author-m4")
    assert result["status"] == "pass" and len(result["checks"]) == 23
    assert result["summary"]["parent_cycle_end_rss"]["change_bytes"] > 0
    assert report == before


@pytest.mark.parametrize("metric", ["open.p95_s", "edit-undo-redo.max_s", "cycle.p95_s",
                                    "parent.peak_mib", "processes.peak_mib", "parent.growth_mib",
                                    "parent.slope_mib_per_cycle", "qt.p95_gap_s", "qt.max_gap_s"])
def test_over_budget_is_failure_even_when_runtime_is_valid(report, metric):
    rules = policy()
    original = evaluate(report, rules, "author-m4")
    actual = next(c["actual"] for c in original["checks"] if c["metric"] == metric)
    limits = rules["profiles"]["author-m4"]
    if metric.endswith(".p95_s") and metric != "cycle.p95_s":
        limits["phase_p95_s"][metric.split(".")[0]] = actual*.99
    elif metric.endswith(".max_s"):
        limits["phase_p95_s"][metric.split(".")[0]] = actual/1.5*.99
    else:
        limits["limits"][metric] = actual*.99
    result = evaluate(report, rules, "author-m4")
    assert result["status"] == "fail"
    assert not next(c["ok"] for c in result["checks"] if c["metric"] == metric)


@pytest.mark.parametrize("damage", ["failed", "exit", "cycles", "physics", "pool", "time",
                                   "nan", "rss", "peak", "probe", "device"])
def test_invalid_evidence_cannot_become_acceptance(report, damage):
    if damage == "failed":
        report["status"] = "failed"
    elif damage == "exit":
        report["exit"] = 1
    elif damage == "cycles":
        report["events"].pop(1)
    elif damage == "physics":
        report["events"][1]["facts"]["volume_mm3"] += 1
    elif damage == "pool":
        next(e for e in report["events"] if e["phase"] == "assembly-preview-close")[
            "facts"]["assembly_pool_closed"] = False
    elif damage == "time":
        report["events"][1]["at_s"] = report["events"][0]["at_s"]
    elif damage == "nan":
        report["events"][1]["at_s"] = float("nan")
    elif damage == "rss":
        report["events"][1]["memory"]["total_rss_bytes"] += 1
    elif damage == "peak":
        report["footer"]["memory"]["observed_pool_peak_rss_bytes"] = 1
    elif damage == "probe":
        report["qt_probe"]["errors"] = ["timer stopped"]
    else:
        report["footer"]["environment"]["cpu"] = "jiné zařízení"
    with pytest.raises(ValueError):
        evaluate(report, policy(), "author-m4")


def test_nearest_rank_percentile_and_real_pause_are_not_averaged_away():
    times = iter([0., .05, .1, 2.1])
    probe = LoopProbe(clock=lambda: next(times))
    probe.start()
    for _ in range(3):
        probe.tick()
    result = probe.report()
    assert result["count"] == 3 and result["max_gap_s"] == 2.
    assert sum(result["buckets"]) == 3
    assert percentile([.05]*19+[2.]) == .05
    assert percentile([.05]*18+[2.]*2) == 2.


def test_measurer_check_is_removed_from_qt_interval_but_still_runs():
    # Rozhodnutí autora 7. 11. 2026: kontrola 800 kopií je práce měřiče, ne obsluha okna.
    times = iter([0., .05, .1, 3.1, 3.15])
    probe = LoopProbe(clock=lambda: next(times))
    probe.start()
    probe.tick()
    ran = []
    with probe.exclude("assembly-800-copies"):
        ran.append(True)
    probe.tick()
    result = probe.report()
    assert ran and result["count"] == 2 and result["max_gap_s"] == pytest.approx(.1)
    assert result["excluded"] == {"assembly-800-copies": {
        "count": 1, "total_s": pytest.approx(3.), "max_s": pytest.approx(3.)}}


def test_only_the_approved_check_can_be_removed_from_qt_measurement():
    probe = LoopProbe(clock=lambda: 0.)
    with pytest.raises(ValueError), probe.exclude("open"):
        pass
    assert probe.excluded == {}


@pytest.mark.parametrize("damage", ["unknown", "count", "missing", "total"])
def test_qt_exclusion_must_match_one_check_per_cycle(report, damage):
    entry = {"count": 22, "total_s": 44., "max_s": 3.}
    report["qt_probe"]["excluded"] = {"assembly-800-copies": entry}
    assert evaluate(report, policy(), "author-m4")["status"] == "pass"
    if damage == "unknown":
        report["qt_probe"]["excluded"]["open"] = dict(entry)
    elif damage == "count":
        entry["count"] = 21
    elif damage == "missing":
        report["qt_probe"]["excluded"] = {}
    else:
        entry["total_s"] = 1.
    with pytest.raises(ValueError):
        evaluate(report, policy(), "author-m4")


def test_exact_budget_boundary_is_accepted_but_missing_limit_is_not(report):
    rules = policy()
    result = evaluate(report, rules, "author-m4")
    value = next(c["actual"] for c in result["checks"] if c["metric"] == "qt.max_gap_s")
    rules["profiles"]["author-m4"]["limits"]["qt.max_gap_s"] = value
    assert evaluate(report, rules, "author-m4")["status"] == "pass"
    del rules["profiles"]["author-m4"]["limits"]["qt.max_gap_s"]
    with pytest.raises(ValueError, match="rozpočty"):
        evaluate(report, rules, "author-m4")


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_policy_cannot_disable_a_budget(report, value):
    rules = policy()
    rules["profiles"]["author-m4"]["limits"]["qt.max_gap_s"] = value
    with pytest.raises(ValueError, match="rozpočty"):
        evaluate(report, rules, "author-m4")


@pytest.mark.parametrize("damage", ["count", "bucket", "max", "total", "interval", "nan"])
def test_probe_histogram_must_be_complete_and_consistent(report, damage):
    p = report["qt_probe"]
    if damage == "count":
        p["count"] = 1
    elif damage == "bucket":
        p["buckets"][-1] = 1
    elif damage == "max":
        p["max_gap_s"] = .04
    elif damage == "total":
        p["total_gap_s"] = 10000
    elif damage == "interval":
        p["interval_s"] = 1
    else:
        p["max_gap_s"] = float("nan")
    with pytest.raises(ValueError):
        gap_p95(p)


def test_cli_preserves_existing_report(tmp_path):
    path = tmp_path/"report.json"
    path.write_text("původní důkaz", encoding="utf-8")
    r = subprocess.run([sys.executable, str(Path(__file__).with_name("budget_p8.py")),
                        "--profile", "author-m4", "--output", str(path)],
                       capture_output=True, timeout=15)
    assert r.returncode == 2 and path.read_text(encoding="utf-8") == "původní důkaz"


def test_child_starts_real_qt_timer_and_writes_telemetry(tmp_path):
    # Jen smoke test zapojení sondy; náhrada CAD zkoušky není přejímkový důkaz.
    script = """
import sys
from pathlib import Path
sys.path.insert(0, 'tests')
import budget_p8
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
def short_event_loop(*args):
    import soak_p8_gui
    with soak_p8_gui.MEASURER_CHECK("assembly-800-copies"):  # zapojení skutečné zkoušky
        pass
    QTimer.singleShot(180, QApplication.instance().quit)
    QApplication.instance().exec()
budget_p8.soak.child = short_event_loop
budget_p8.child(Path(sys.argv[1]))
"""
    r = subprocess.run([sys.executable, "-c", script, str(tmp_path)], cwd=POLICY.parents[1],
                       env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                       capture_output=True, timeout=15)
    assert r.returncode == 0, r.stderr.decode("utf-8", errors="replace")
    data = json.loads((tmp_path/"qt-probe.json").read_text(encoding="utf-8"))
    # Alespoň jedno skutečné doručení + závěrečný bod; přesnou frekvenci OS neslibuje.
    assert data["count"] >= 2 and data["max_gap_s"] > 0 and data["errors"] == []
    # P8.5 dosadí sondu do zkoušky P8.4; vyjmutí se zapíše do důkazu.
    assert data["excluded"]["assembly-800-copies"]["count"] == 1


def test_saved_p85_native_measurement_matches_fixed_policy_and_original_sources():
    path = POLICY.parents[1]/"docs/baselines/p8-5-macos-arm64.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["evaluation"] == evaluate(data, policy(), "author-m4")
    assert data["evaluation"]["status"] == "pass" and len(data["hashes"]) == 150
    original = json.loads((path.parent/"p8-4-macos-arm64-pool-release.json").read_text(
        encoding="utf-8"))
    assert all(data["hashes"][k] == v for k, v in original["hashes"].items())
