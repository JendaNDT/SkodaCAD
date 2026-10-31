"""P6: tři referenční skořepiny a dvě kontroly mezí, bez změny aplikace.

Spuštění: python docs/p6-3-pruzkum-skorepin.py --output out/p6-3-skorepiny
Každý případ běží v samostatném procesu s časovým limitem. JSON recepty, přesné
STEP a SVG jsou v cílové složce; measurements obsahují všechny vzorky, ne jen minimum.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

import OCP
from build123d import Vector, offset
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

from skodacad import Document, rebuild
from skodacad.export import export as export_model
from skodacad.geometry_validation import check_modification, inspect_volume
from skodacad.measure import RayCaster
from skodacad.selectors import select_faces

ROOT = Path(__file__).resolve().parents[1]
CASES = ("kvadr", "sikme_steny", "zaobleny_kryt", "zanik_polomeru", "prilis_tlusta",
         "vysypka")
TOL = 2e-5  # mm, vzorkované geometrické měření; není mez výrobní tolerance


def sketch(key: str, width: float, height: float, z: float = 0, radius: float = 0) -> dict:
    return {"id": key, "type": "sketch", "plane": "XY", "offset": z, "elements": [
        {"shape": "rectangle", "width": width, "height": height, "corner_radius": radius}]}


def recipe(case: str) -> Document:
    if case == "vysypka":
        return Document.load(ROOT / "examples/vysypka.json")
    wall = 2 if case == "zaobleny_kryt" else 4 if case == "zanik_polomeru" else 3
    if case == "prilis_tlusta":
        wall = 26
    rounded = case in ("zaobleny_kryt", "zanik_polomeru")
    features = [sketch("obrys", 80, 50, radius=6 if rounded else 0)]
    if case == "sikme_steny":
        features += [sketch("vrsek", 40, 30, z=40),
                     {"id": "teleso", "type": "loft", "sketches": ["obrys", "vrsek"],
                      "ruled": True}]
    else:
        features.append({"id": "teleso", "type": "extrude", "sketch": "obrys", "distance": 30})
    if rounded:
        features.append({"id": "zaobleni_dna", "type": "fillet",
                         "edges": {"face": "bottom"}, "radius": 3})
    features.append({"id": "skorepina", "type": "shell", "thickness": "stena",
                     "open_faces": ["top"]})
    return Document.from_dict({"format": "skodacad", "version": 11, "name": case,
        "material": "PETG", "parameters": {"stena": wall}, "features": features})


def rounded_volume(length: float, width: float, height: float,
                   radius: float, fillet: float) -> float:
    """Integrál zaobleného obdélníku s dolním zaoblením; odvození v průvodním návrhu."""
    area = length * width - (4 - math.pi) * radius**2
    perimeter = 2 * (length + width) - 2 * (4 - math.pi) * radius
    return (area * height - perimeter * fillet**2 * (1 - math.pi / 4)
            + math.pi * fillet**3 * (5 / 3 - math.pi / 2))


def inclined_volume(wall: float) -> float:
    # Čtyři roviny x = ±(40 − z/2), y = ±(25 − z/4), dno z = 0.
    def integral(a: float, b: float, z: float) -> float:
        return 4 * (a * b * z - (a / 4 + b / 2) * z**2 / 2 + z**3 / 24)
    a, b = 40 - wall * math.sqrt(1.25), 25 - wall * math.sqrt(1.0625)
    return integral(40, 25, 40) - (integral(a, b, 40) - integral(a, b, wall))


def measurements(original, candidate, openings) -> list[dict]:
    """5 × 5 bodů každého ponechaného vnějšího povrchu; bez hran a čel otvorů.

    Parametrická síť není plošně rovnoměrná. Vzorky neprokazují globální minimum,
    výrobní přesnost ani tloušťku v místech, která síť nezasáhla.
    """
    ray = RayCaster(candidate)
    geometric_ray = IntCurvesFace_ShapeIntersector()
    geometric_ray.Load(candidate.wrapped, 1e-7)
    solids = candidate.solids()
    found = []
    for face in original.faces():
        if any(face.is_same(opening) for opening in openings):
            continue
        for u in (0.15, 0.325, 0.5, 0.675, 0.85):
            for v in (0.15, 0.325, 0.5, 0.675, 0.85):
                point = face.position_at(u, v)
                if not face.is_inside(point):
                    continue
                edge_distance = min(edge.distance_to(point) for edge in face.edges())
                if edge_distance < 1e-4:
                    continue
                normal = face.normal_at(point)
                assert any(s.is_inside(point - normal * 1e-5) for s in solids), point
                assert not any(s.is_inside(point + normal * 1e-5) for s in solids), point
                depth, oblique = ray.thickness(tuple(point), tuple(-normal))
                # Nezávisle zaznamenat geometrickou délku materiálem. Na rozdíl od
                # stávajícího měřidla zde není filtr protější stěny podle úhlu 60°.
                geometric_ray.Perform(gp_Lin(gp_Pnt(*point), gp_Dir(*(-normal))), 1e-6, 1e9)
                distances = [geometric_ray.WParameter(i)
                             for i in range(1, geometric_ray.NbPnt() + 1)
                             if geometric_ray.WParameter(i) > 1e-4]
                material_length = min(distances, default=None)
                found.append({"point_mm": list(point), "outward_normal": list(normal),
                    "surface": face.geom_type.name, "distance_to_edge_mm": edge_distance,
                    "thickness_mm": depth, "oblique": oblique,
                    "normal_material_length_mm": material_length})
    return found


def run_case(case: str, folder: Path) -> dict:
    started = time.monotonic()
    doc = recipe(case)
    doc.save(folder / f"{case}.json")
    outer = recipe(case)
    if case == "vysypka":
        outer.features[-1].pop("wall")
    else:
        outer.features.pop()
    original_result = rebuild(outer)
    assert original_result.ok, original_result.first_error
    original = original_result.part
    before = inspect_volume(original)
    result = rebuild(doc)
    record = {"case": case, "accepted": result.ok, "original_volume_mm3": before.volume}
    if case == "prilis_tlusta":
        assert not result.ok and result.first_error.id == "skorepina"
        assert result.part is result.parts_before["skorepina"]
        assert math.isclose(result.part.volume, original.volume, abs_tol=1e-6)
        record.update(error=result.first_error.message, previous_geometry_retained=True)
    else:
        assert result.ok, result.first_error
        candidate = result.part
        after = inspect_volume(candidate)
        check_modification(before, after, shell=True)
        assert after.solids == 1
        openings = select_faces(original, "top")
        if case == "vysypka":
            openings += select_faces(original, "bottom")
        samples = measurements(original, candidate, openings)
        values = [s["thickness_mm"] for s in samples if s["thickness_mm"] is not None]
        lengths = [s["normal_material_length_mm"] for s in samples
                   if s["normal_material_length_mm"] is not None]
        assert len(values) >= 100
        assert len(lengths) == len(samples)
        record.update(valid=True, solids=after.solids, volume_mm3=after.volume,
                      samples=len(samples), measured=len(values),
                      unknown=len(samples) - len(values), minimum_sampled_mm=min(values),
                      maximum_sampled_mm=max(values), normal_material_min_mm=min(lengths),
                      normal_material_max_mm=max(lengths), measurements=samples)
        wall = {"kvadr": 3, "sikme_steny": 3, "zaobleny_kryt": 2,
                "zanik_polomeru": 4, "vysypka": 3}[case]
        record["requested_wall_mm"] = wall
        if case in ("kvadr", "sikme_steny", "zaobleny_kryt"):
            uncertain = [s for s in samples if s["thickness_mm"] is None]
            # U šikmých boků část dna leží pod zesíleným klínem, nikoli pod dutinou.
            # Paprsek tam trefí šikmý bok; platný výsledek NDT měření je „nejisté“.
            if uncertain:
                assert case == "sikme_steny"
                assert all(s["oblique"] and s["distance_to_edge_mm"] < 2 * wall
                           for s in uncertain)
            assert max(abs(value - wall) for value in values) < TOL
            assert min(lengths) >= wall - TOL
            if case == "kvadr":
                expected = 80 * 50 * 30 - (80 - 6) * (50 - 6) * (30 - 3)
            elif case == "sikme_steny":
                expected = inclined_volume(wall)
            else:
                expected = rounded_volume(80, 50, 30, 6, 3) - rounded_volume(76, 46, 28, 4, 1)
            assert math.isclose(after.volume, expected, rel_tol=1e-8, abs_tol=1e-5)
            record["analytic_volume_mm3"] = expected
        elif case == "zanik_polomeru":
            assert min(lengths) >= wall - TOL
            point = Vector(-37 - 3 / math.sqrt(2), 0, 3 - 3 / math.sqrt(2))
            normal = Vector(-1, 0, -1).normalized()
            depth, oblique = RayCaster(candidate).thickness(tuple(point), tuple(-normal))
            expected = 3 + math.sqrt(2)  # průchod až do vnitřního rohu x = −36, z = 4
            assert not oblique and depth is not None and abs(depth - expected) < TOL
            record.update(corner_thickness_mm=depth, analytic_corner_thickness_mm=expected,
                          interpretation="Zesílení rohu po zániku vnitřního zaoblení.")
        else:
            # Kontrola známého náhradního postupu; neslibuje opravený normálový offset.
            raw = offset(original, amount=-wall, openings=openings)
            record.update(raw_offset_valid=raw.is_valid, raw_offset_volume_mm3=raw.volume,
                          raw_offset_unchanged=math.isclose(raw.volume, original.volume,
                                                          rel_tol=1e-9))
            assert min(values) < wall - 0.1, "Nález se změnil, aktualizuj závěr průzkumu."
        if case in ("kvadr", "sikme_steny", "zaobleny_kryt", "vysypka"):
            export_model(candidate, folder / f"{case}.step")
            export_model(candidate, folder / f"{case}.svg")
        # Typ BSPLINE sám neříká, zda je geometrie rovinná.
        record["surface_types"] = sorted({f.geom_type.name for f in original.faces()})
    record["seconds"] = time.monotonic() - started
    return record


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("out/p6-3-skorepiny"))
    parser.add_argument("--case", choices=CASES, help=argparse.SUPPRESS)
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if args.case:
        record = run_case(args.case, folder)
        (folder / f"{args.case}-result.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in record.items() if k != "measurements"},
                         ensure_ascii=False))
        return
    records = []
    for case in CASES:
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--case",
            case, "--output", str(folder)], cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", timeout=120, check=False)
        (folder / f"{case}-process.log").write_text(completed.stdout + completed.stderr,
                                                   encoding="utf-8")
        assert completed.returncode == 0, f"{case}: viz {folder / (case + '-process.log')}"
        record = json.loads((folder / f"{case}-result.json").read_text(encoding="utf-8"))
        records.append(record)
        print(completed.stdout.strip(), flush=True)
    report = {"source_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python": platform.python_version(), "platform": platform.platform(),
        "build123d": version("build123d"), "ocp": OCP.__version__,
        "study_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sample_tolerance_mm": TOL, "cases": records}
    (folder / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)
                                         + "\n", encoding="utf-8")
    print(f"OK: {len(records)} případů; {folder / 'results.json'}")


if __name__ == "__main__":
    main()
