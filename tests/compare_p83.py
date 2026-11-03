"""P8.3: ověřitelné srovnání dvou GUI běhů nezměněného měřiče P8.2."""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

SOURCE = "src/skodacad/gui/assembly_window.py"
FACTS = {
    "open-build-tree-render": {"instances": 800, "constraints_ok": 0, "volume_mm3": 800000.0},
    "select-last-component": {"selected_id": "c799"},
    "open-parameter-preview-back": {"model_unchanged": True},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonnegative(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def validate(report):
    require(report["schema"] == "skodacad-p8.2-v1" and report["repeats"] == 3,
            "Neznámé schéma nebo počet vzorků")
    results = report["results"]
    require(len(results) == 2 and {r["mode"] for r in results} == {"control", "spans"},
            "Chybí právě dva režimy GUI")
    modes = {}
    for result in results:
        require(result["case"] == "gui-assembly" and result["status"] == "ok"
                and result["exit"] == 0 and result["details"]["native_view_ready"] is True,
                "GUI běh není úplný nebo nemá nativní okno")
        require(bool(result["input_sha256"]), "Chybí otisky vstupů")
        metrics = {m["name"]: m for m in result["metrics"]}
        require(len(result["metrics"]) == 3 and metrics.keys() == FACTS.keys(),
                "Chybí měřené operace")
        for name, metric in metrics.items():
            samples = metric["samples_s"]
            require(metric["warmups"] == 1 and len(samples) == 3
                    and all(nonnegative(s) and s > 0 for s in samples),
                    "Neplatné zahřátí nebo vzorky")
            require(metric["median_s"] == statistics.median(samples)
                    and metric["min_s"] == min(samples) and metric["max_s"] == max(samples),
                    "Souhrn neodpovídá surovým vzorkům")
            require(metric["correctness"] == FACTS[name], "Změněná geometrie nebo stav modelu")
            traces = metric.get("traces", [])
            require(len(traces) == (3 if result["mode"] == "spans" else 0),
                    "Nesprávný počet profilů")
            for sample, trace in zip(samples, traces, strict=False):
                spans = trace["spans"]
                root = spans["operation_other"]["inclusive_s"]
                tolerance = max(1e-8, root*1e-9)
                require(all(nonnegative(row["self_s"]) and nonnegative(row["inclusive_s"])
                            and row["self_s"] <= row["inclusive_s"]+tolerance
                            and isinstance(row["calls"], int) and row["calls"] > 0
                            for row in spans.values()), "Neplatný interval")
                require(abs(sum(row["self_s"] for row in spans.values())-root) <= tolerance
                        and abs(trace["accounted_wall_s"]-root) <= tolerance
                        and nonnegative(trace["timer_envelope_s"])
                        and abs(sample-root-trace["timer_envelope_s"]) <= tolerance,
                        "Intervaly nerozdělují skutečný čas operace")
                expected_calls = ({"source_read": 800, "source_locate": 800,
                                   "tree_visibility": 1} if name == "open-build-tree-render"
                                  else {"source_read": 1600, "source_locate": 1600,
                                        "usage_analysis": 5}
                                  if name == "open-parameter-preview-back" else {})
                require(all(spans.get(key, {}).get("calls") == count
                            for key, count in expected_calls.items()), "Změněné měřené volání")
        modes[result["mode"]] = (result["input_sha256"], metrics)
    require(modes["control"][0] == modes["spans"][0], "Režimy mají jiné vstupy")
    return modes


def compare(before, after):
    old, new = validate(before), validate(after)
    require(all(before["environment"][key] == after["environment"][key]
                for key in ("system", "python", "cpu", "logical_cpus", "packages")),
            "Odlišné prostředí měření")
    require(old["control"][0] == new["control"][0], "Srovnání má jiné vstupy")
    old_hashes, new_hashes = before["hashes"], after["hashes"]
    require(old_hashes.keys() == new_hashes.keys() and bool(old_hashes), "Jiná sada zdrojů")
    require({key for key in old_hashes if old_hashes[key] != new_hashes[key]} == {SOURCE},
            "Srovnání nemění právě jediný povolený zdroj")
    require(all(key in old_hashes for key in (
        "tests/profile_p8.py", "tests/benchmark_p8.py", "tests/benchmark_p8_gui.py", SOURCE)),
        "Chybí otisky měřičů nebo zdroje")
    metrics = {}
    for name in FACTS:
        previous = old["control"][1][name]["median_s"]
        current = new["control"][1][name]["median_s"]
        metrics[name] = {"before_control_median_s": previous,
                         "after_control_median_s": current,
                         "saved_s": previous-current, "after_over_before": current/previous}
    tree_times = [statistics.mean(t["spans"]["tree_visibility"]["self_s"]
                  for t in modes["spans"][1]["open-build-tree-render"]["traces"])
                  for modes in (old, new)]
    return {"schema": "skodacad-p8.3-v1", "status": "ok",
            "before_commit": before["commit"], "after_commit": after["commit"],
            "environment": after["environment"], "input_sha256": new["control"][0],
            "source": {"path": SOURCE, "before_sha256": old_hashes[SOURCE],
                       "after_sha256": new_hashes[SOURCE]}, "metrics": metrics,
            "tree_visibility_mean_self_s": {"before": tree_times[0], "after": tree_times[1]},
            "limits": ["Pevné pořadí před/potom, tři vzorky nejsou statistická studie.",
                       "Control je bez sond; self zahrnuje nativní práci a čekání.",
                       "Žádný předepsaný rychlostní práh; shoda výsledku je povinná."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.before.read_text(encoding="utf-8")),
                     json.loads(args.after.read_text(encoding="utf-8")))
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print("P83_RESULT " + json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
