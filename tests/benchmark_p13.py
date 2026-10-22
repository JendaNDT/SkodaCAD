"""P1.3 fixed semantic queries; run at the repository root, outside pytest.

One warm-up and three batches of 100 queries. Times are evidence, not thresholds.
Ambiguity outcomes intentionally change; physical inputs must remain identical.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path

import OCP
from build123d import Box, Part, Pos

from skodacad import Document, rebuild
from skodacad.selectors import SelectionError, find_face, select_edges


def signature(part):
    assert part.is_valid
    return {"volume": round(part.volume, 6), "solids": len(part.solids()),
            "bounds": [round(v, 6) for v in part.bounding_box().size]}


def edge_result(part, spec):
    try:
        edges = select_edges(part, spec, float)
    except SelectionError as exc:
        return {"error": str(exc)}
    return {"edges": sorted([*[round(v, 6) for v in e.center()], round(e.length, 6)]
                            for e in edges)}


def face_result(part, spec):
    try:
        face, point = find_face(part, spec)
    except SelectionError as exc:
        return {"error": str(exc)}
    return {"center": [round(v, 6) for v in face.center()],
            "point": [round(v, 6) for v in point], "area": round(face.area, 6)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be a new file")
    root = Path.cwd()
    models = {}
    inputs = {}
    for name in ["priruba", "krabicka", "ram"]:
        path = root / "examples" / (name + ".json")
        inputs[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        result = rebuild(Document.load(path))
        assert result.ok
        models[name] = result.part
    box = Box(20, 30, 40)
    pair = Part((Pos(-20, 0, 0) * Box(20, 20, 10)).solids()
                + (Pos(20, 0, 0) * Box(20, 20, 10)).solids())
    models.update(box=box, pair=pair)
    assert abs(pair.volume - 8000) < 1e-6 and len(pair.solids()) == 2
    queries = [
        ("priruba:top-circles", models["priruba"], edge_result,
         {"face": "top", "radius": 9}),
        ("krabicka:bottom", models["krabicka"], face_result,
         {"at": [0, 0, 0], "normal": [0, 0, -1], "type": "plane"}),
        ("ram:vertical", models["ram"], edge_result, {"parallel": "Z"}),
        ("box:ambiguous-edges", box, edge_result, {"parallel": "Z", "near": [0, -15, 0]}),
        ("pair:ambiguous-faces", pair, face_result,
         {"at": [0, 0, 5], "normal": [0, 0, 1], "type": "plane"}),
    ]
    results = []
    for name, part, query, spec in queries:
        physical = signature(part)
        expected = query(part, spec)
        samples = []
        for _ in range(3):
            started = time.perf_counter()
            outcomes = [query(part, spec) for _ in range(100)]
            samples.append(time.perf_counter() - started)
            assert all(outcome == expected for outcome in outcomes)
            assert signature(part) == physical
        results.append({"name": name, "spec": spec, "warmups": 1, "queries_per_batch": 100,
                        "samples_s": samples, "median_s": statistics.median(samples),
                        "result": expected, "physical": physical})
    sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted((root / "src").rglob("*.py")) if p.name != "_build.py"}
    report = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                text=True).strip(),
              "source_sha256": hashlib.sha256(json.dumps(sources, sort_keys=True).encode()
                                               ).hexdigest(),
              "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "inputs_sha256": inputs,
              "environment": {"python": platform.python_version(), "machine": platform.machine(),
                              "system": platform.system(), "packages": {
                                  name: importlib.metadata.version(name)
                                  for name in ["build123d", "PySide6", "slvs"]},
                              "ocp": OCP.__version__},
              "models": {name: signature(part) for name, part in models.items()},
              "results": results,
              "limits": ["Warm in-process queries; imports, GUI and spawn excluded.",
                         "Three batches are not a statistical or causal performance claim.",
                         "Two ambiguity outcomes change intentionally; physical inputs do not."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(args.output)


if __name__ == "__main__":
    main()
