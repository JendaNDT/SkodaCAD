"""Volitelná baseline P0; není součást pytest kolekce ani produkční aplikace.

Spuštění z kořene repa: python tests/benchmark_p0.py --output out/p0-baseline.json
Časy jsou evidence pro porovnání na stejném stroji, nikoli podmínka průchodu CI.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import pickle
import platform
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from skodacad import Document, rebuild
from skodacad.document import VERSION
from skodacad.ndt.geometry import ALGORITHM, PartGeometry
from skodacad.worker import decode_result, encode_result

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("priruba.json", "krabicka.json", "ram.json",
          "ndt/cilove_objemy/tupy_svar_objem.json")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peak_rss():
    """Maximum celého procesu včetně importů; není to přírůstek ani paměť workerů."""
    try:
        import resource
    except ImportError:
        return None  # Windows: standardní knihovna tuto metriku neposkytuje.
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(raw if sys.platform == "darwin" else raw * 1024)


def signature(result):
    if not result.ok or result.part is None or not result.part.is_valid:
        raise RuntimeError(f"Neplatný přepočet: {result.statuses}")
    part = result.part
    if len(part.solids()) != 1 or part.volume <= 0:
        raise RuntimeError("Referenční model musí být jedno těleso s kladným objemem.")
    return {"volume_mm3": round(part.volume, 6), "area_mm2": round(part.area, 6),
            "bounds_mm": [round(value, 6) for value in part.bounding_box().size],
            "solids": len(part.solids()), "faces": len(part.faces()),
            "features": len(result.statuses),
            "ndt_states": [[s.id, s.state] for s in result.ndt]}


def measure(name, operation, inspect, repeats):
    expected = inspect(operation())  # jeden nezapočítaný zahřívací běh
    durations = []
    for _ in range(repeats):
        started = time.perf_counter()
        outcome = operation()
        durations.append(time.perf_counter() - started)
        if inspect(outcome) != expected:
            raise RuntimeError(f"Nestálý výsledek měření {name}.")
    return {"name": name, "warmups": 1, "samples_s": durations,
            "median_s": statistics.median(durations), "min_s": min(durations),
            "max_s": max(durations), "result": expected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error("--repeats musí být 1 až 20")
    # Měřič nesmí přepsat model ani existující evidence.
    if args.output.exists():
        parser.error("Výstup již existuje; zvol nový soubor.")

    paths = [ROOT / "examples" / name for name in (*MODELS, "ndt/deska.json")]
    inputs = {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}
    sources = sorted((ROOT / "src").rglob("*.py"))
    sources = [path for path in sources if path.name != "_build.py"]
    source_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in sources}
    results = []
    for name in MODELS:
        document = Document.load(ROOT / "examples" / name)
        before = document.to_dict()
        results.append(measure(f"rebuild:{name}", lambda doc=document: rebuild(doc),
                               signature, args.repeats))
        if document.to_dict() != before:
            raise RuntimeError(f"Měření změnilo recept {name}.")

    reference = rebuild(Document.load(ROOT / "examples/priruba.json"))
    expected = signature(reference)

    def transfer():
        payload = pickle.dumps(encode_result(reference))
        return len(payload), decode_result(pickle.loads(payload))

    def inspect_transfer(outcome):
        size, restored = outcome
        if signature(restored) != expected or restored.statuses != reference.statuses:
            raise RuntimeError("Přenos výsledku změnil geometrii nebo stavy prvků.")
        return {"payload_bytes": size, **signature(restored)}

    results.append(measure("encode-pickle-decode:priruba", transfer, inspect_transfer,
                           args.repeats))
    plate = PartGeometry(rebuild(Document.load(ROOT / "examples/ndt/deska.json")).part)

    def rays():
        # 1000 kolmých paprsků dovnitř desky 200 × 100 × 20, žádný po hraně.
        return [plate.cast((-49.5 + i / 10, 10, 50), (0, 0, -1)) for i in range(1000)]

    def inspect_rays(outcome):
        if not all(ray.certain and math.isclose(ray.material_length, 20, abs_tol=1e-6)
                   for ray in outcome):
            raise RuntimeError("Paprsek desky neodpovídá tloušťce 20 mm.")
        return {"rays": len(outcome), "material_length_each_mm": 20,
                "algorithm": ALGORITHM}

    results.append(measure("ndt:1000-rays-plate", rays, inspect_rays, args.repeats))
    if any(digest(ROOT / name) != sha for name, sha in inputs.items()):
        raise RuntimeError("Vstupní soubor se během měření změnil.")
    report = {
        "purpose": "P0 performance evidence; not a model file or acceptance threshold",
        "created_utc": datetime.now(UTC).isoformat(),
        "commit": git("rev-parse", "HEAD"),
        "tracked_changes": git("diff", "HEAD", "--name-only").splitlines(),
        "source_sha256": hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()
                                       ).hexdigest(),
        "benchmark_sha256": digest(Path(__file__)),
        "model_format_version": VERSION,
        "environment": {"python": platform.python_version(), "system": platform.system(),
                        "release": platform.release(), "machine": platform.machine(),
                        "processor": platform.processor(), "logical_cpus": os.cpu_count(),
                        "packages": {d.metadata["Name"]: d.version for d in sorted(
                            importlib.metadata.distributions(), key=lambda d: d.metadata["Name"])}},
        "inputs_sha256": inputs,
        "results": results,
        "process_peak_rss_bytes": peak_rss(),
        "limits": ["Warm in-process operations; imports, GUI, spawn and exports excluded.",
                   "RSS is process lifetime high-water mark, not a per-case allocation.",
                   "RSS unavailable on Windows; no estimate substituted.",
                   "Compare timings only on equivalent hardware, dependencies and load."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
    for result in results:
        print(f"{result['name']}: median {result['median_s']:.4f} s")
    print(f"Evidence: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
