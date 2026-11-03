"""Měřič nesmí zaměnit chybějící paměť, neúplný cyklus či trend za úspěch."""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from soak_p8 import PHASES, Memory, read_events, summarize, trend, validate_runtime


def test_rss_totals_are_simultaneous_samples_not_sum_of_process_peaks():
    values = iter([100, 300, 400, 200])
    memory = Memory(1000, reader=lambda _pid: next(values), processes=lambda: [os.getpid()+1])
    memory.sample()
    memory.sample()
    report = memory.report()
    assert sorted(report["observed_peak_rss_bytes"].values()) == [300, 400]
    assert report["observed_pool_peak_rss_bytes"] == 600  # nikoli součet maxim 700
    assert report["sample_count"] == 2


def test_missing_worker_rss_is_not_reported_as_zero():
    memory = Memory(1000, reader=lambda pid: 100 if pid == os.getpid() else None,
                    processes=lambda: [os.getpid()+1])
    row = memory.sample()
    assert row["total_rss_bytes"] is None and row["worker_count"] == 1
    assert memory.report()["missing_worker_samples"] == 1
    assert memory.report()["observed_pool_peak_rss_bytes"] == 0


def test_missing_parent_rss_and_exceeded_guard_are_failures():
    memory = Memory(1000, reader=lambda _pid: None, processes=lambda: [])
    with pytest.raises(RuntimeError, match="RSS hlavního"):
        memory.sample()
    memory = Memory(99, reader=lambda _pid: 100, processes=lambda: [])
    memory.sample()
    with pytest.raises(RuntimeError, match="rozpočet"):
        memory.check()


def test_trend_excludes_order_bias_from_unequal_cycle_numbers():
    result = trend([(2, 100), (4, 120), (6, 140), (8, 160)])
    assert result["median_pairwise_bytes_per_cycle"] == 10
    assert result["change_bytes"] == 60
    assert trend([(1, 200), (2, 200), (3, 200)])["change_bytes"] == 0
    assert trend([(1, 300), (2, 200), (3, 100)])["median_pairwise_bytes_per_cycle"] == -100


def events():
    return [{"phase": phase, "cycle": cycle, "warmup": cycle == 0,
             "memory": {"parent_pid": 123, "rss_bytes": {"123": 900 if cycle == 0 else 100},
                        "worker_count": 3}, "resources": {"assembly_windows": 1}}
            for cycle in range(3) for phase in PHASES]


def test_summary_excludes_warmup_without_hiding_raw_samples():
    rows = events()
    before = copy.deepcopy(rows)
    summary = summarize(rows, cycles=2, warmups=1)
    assert summary["parent_cycle_end_rss"]["first_third_median_bytes"] == 100
    assert summary["cycle_end_worker_counts"] == [3, 3]
    assert rows == before


@pytest.mark.parametrize("bad", ["missing-phase", "reordered", "missing-cycle", "missing-rss"])
def test_summary_rejects_incomplete_evidence(bad):
    rows = events()
    if bad == "missing-phase":
        rows.pop(0)
    elif bad == "reordered":
        rows[0], rows[1] = rows[1], rows[0]
    elif bad == "missing-cycle":
        rows = [row for row in rows if row["cycle"] != 2]
    else:
        rows[-1]["memory"]["rss_bytes"]["123"] = None
    with pytest.raises(ValueError):
        summarize(rows, cycles=2, warmups=1)


def test_cli_preserves_existing_evidence(tmp_path):
    output = tmp_path / "soak.json"
    output.write_text("Původní důkaz", encoding="utf-8")
    script = Path(__file__).with_name("soak_p8.py")
    process = subprocess.run([sys.executable, str(script), "--output", str(output)],
                             capture_output=True, timeout=15)
    assert process.returncode == 2
    assert output.read_text(encoding="utf-8") == "Původní důkaz"
    assert not output.with_suffix("").exists()


def test_truncated_timeout_event_preserves_complete_prefix_and_reports_failure(tmp_path):
    path = tmp_path / "events.jsonl"
    assert read_events(path) == ([], "")
    path.write_text('{"phase":"open"}\n{"phase":', encoding="utf-8")
    rows, error = read_events(path)
    assert rows == [{"phase": "open"}] and error.endswith("2")
    path.write_text('{"phase":"open"}\n', encoding="utf-8")
    assert read_events(path) == ([{"phase": "open"}], "")


@pytest.fixture
def complete_report():
    path = Path(__file__).resolve().parents[1] / "docs/baselines/p8-4-macos-arm64-pool-release.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_saved_native_long_run_has_complete_cases_and_reproducible_summary(complete_report):
    report = complete_report
    assert report["status"] == "ok" and report["exit"] == 0
    assert report["cycles"] == 20 and report["warmups"] == 2
    validate_runtime(report["events"], report["footer"], 20, 2)
    assert summarize(report["events"], 20, 2) == report["summary"]


@pytest.mark.parametrize("bad", ["geometry", "cancel", "native", "pool", "window", "pid", "rss"])
def test_native_evidence_rejects_missing_physics_or_resources(complete_report, bad):
    report = complete_report
    phase = {"geometry": "open", "cancel": "cancel-recover", "native": "assembly-preview-close",
             "pool": "assembly-preview-close",
             "window": "cycle-end", "pid": "cycle-end", "rss": "cycle-end"}[bad]
    row = next(e for e in report["events"] if e["phase"] == phase)
    if bad == "geometry":
        row["facts"]["volume_mm3"] += 1
    elif bad == "cancel":
        row["facts"]["cancelled_process_dead"] = False
    elif bad == "native":
        row["facts"]["preview_native_ready"] = False
    elif bad == "pool":
        row["facts"]["assembly_pool_closed"] = False
    elif bad == "window":
        row["resources"]["assembly_windows"] = 1
    elif bad == "pid":
        row["facts"]["owned_worker_pids"] = []
    else:
        row["memory"]["total_rss_bytes"] += 1
    with pytest.raises(ValueError):
        validate_runtime(report["events"], report["footer"], 20, 2)


def test_original_window_only_baseline_is_preserved_as_historical_evidence():
    import hashlib

    path = Path(__file__).resolve().parents[1] / "docs/baselines/p8-4-macos-arm64.json"
    # Přesné dvě varianty checkoutu; Windows Git převádí LF na CRLF.
    assert hashlib.sha256(path.read_bytes()).hexdigest() in {
        "4ac76750072402d7a02f16e08c9bec3bd7f861ad0f9fb508894d0a8c066dd295",
        "fb27294bbdf8b9c6389df995af0095f4297c5160cd7acb688b56ae0a42afed25",
    }
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["schema"] == "skodacad-p8.4-v1"
    assert report["summary"]["cycle_end_worker_counts"] == [4]*20
