"""P1.2B: fixed short/long histories, late rejection and repeated rebuilds.

Run from the repository root. No timing threshold; output must be a new file.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import OCP

from skodacad import Document, rebuild

try:
    import resource
except ImportError:  # Windows nemá modul resource
    resource = None


def history(count: int, failing: bool = False) -> Document:
    features = []
    for index in range(count):
        features.extend([
            {"id": f"s{index}", "type": "sketch", "plane": "XY", "elements": [
                {"shape": "rectangle", "width": 1, "height": 2,
                 "center": [10 * index, 0]}]},
            {"id": f"e{index}", "type": "extrude", "sketch": f"s{index}",
             "distance": 3, "operation": "add"},
        ])
    if failing:
        features.extend([
            {"id": "inside", "type": "sketch", "plane": "XY", "elements": [
                {"shape": "rectangle", "width": 0.5, "height": 1}]},
            {"id": "bad", "type": "extrude", "sketch": "inside", "distance": 1,
             "operation": "add"},
            {"id": "tail", "type": "sketch", "plane": "XY", "elements": [
                {"shape": "circle", "diameter": 1}]},
        ])
    return Document.from_dict({"format": "skodacad", "version": 22, "name": "P1.2B history",
                               "units": "mm", "material": "ocel", "parameters": {},
                               "features": features})


def encoded(document: Document) -> bytes:
    return json.dumps(document.to_dict(), sort_keys=True, ensure_ascii=False).encode()


def check(result, count: int, failing: bool) -> dict:
    assert result.ok != failing
    if failing:
        assert result.first_error.id == "bad" and result.statuses[-1].status == "skipped"
    assert result.part.is_valid and len(result.part.solids()) == count
    assert math.isclose(result.part.volume, 6 * count, rel_tol=1e-10)
    box = result.part.bounding_box()
    bounds = [box.min.X, box.min.Y, box.min.Z, box.max.X, box.max.Y, box.max.Z]
    expected = [-0.5, -1, 0, 10 * (count - 1) + 0.5, 1, 3]
    assert all(math.isclose(a, b, abs_tol=1e-6)
               for a, b in zip(bounds, expected, strict=True))
    assert result.part.is_inside((0, 0, 0.5))
    return {"solids": count, "volume_mm3": result.part.volume, "bounds": bounds,
            "statuses": [(s.id, s.status, s.message) for s in result.statuses]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-commit", help="SHA archivovaného zdrojového stromu bez .git")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists")
    source = hashlib.sha256()
    for path in sorted(Path("src").rglob("*.py")):
        source.update(str(path).encode() + b"\0" + path.read_bytes())
    cases = []
    for count, failing in [(3, False), (30, False), (30, True)]:
        document = history(count, failing)
        original = encoded(document)
        check(rebuild(document), count, failing)  # warm-up
        samples = []
        signature = None
        for _ in range(3):
            started = time.perf_counter()
            result = rebuild(document)
            samples.append(time.perf_counter() - started)
            current = check(result, count, failing)
            if signature is not None:
                assert current == signature
            signature = current
            assert encoded(document) == original
        cases.append({"name": f"history-{count}" + ("-late-error" if failing else ""),
                      "input_sha256": hashlib.sha256(original).hexdigest(),
                      "samples_seconds": samples, "median_seconds": statistics.median(samples),
                      "signature": signature, "input_unchanged": True})
        print(cases[-1]["name"], round(cases[-1]["median_seconds"], 6), flush=True)
    document = history(30, True)
    original = encoded(document)
    started = time.perf_counter()
    for _ in range(10):
        check(rebuild(document), 30, True)
        assert encoded(document) == original
    repeated_seconds = time.perf_counter() - started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else None
    report = {"date_utc": datetime.now(UTC).isoformat(),
              "commit": args.reference_commit or subprocess.check_output(
                  ["git", "rev-parse", "HEAD"], text=True).strip(),
              "source_sha256": source.hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "platform": platform.platform(), "python": platform.python_version(),
              "libraries": {p: importlib.metadata.version(p)
                            for p in ["build123d", "PySide6", "slvs"]} | {
                                "OCP": str(OCP.__version__)},
              "warmup": 1, "repeats": 3, "cases": cases,
              "ten_rebuilds_seconds": repeated_seconds,
              "process_peak_rss_bytes": (peak if sys.platform == "darwin" else peak * 1024)
              if peak is not None else None,
              "memory_scope": "Process lifetime maximum, not per-feature allocation or leak proof"}
    with args.output.open("x") as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
