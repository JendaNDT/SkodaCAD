"""P6.1/P6.2: omezený pokus s proměnným zaoblením v OCCT, nikoli funkce aplikace.

Spuštění z kořene: .venv/bin/python docs/p6-1-pruzkum-zaobleni.py
Výsledek: out/p6-1-pruzkum-zaobleni.json. Nemění zdrojové díly ani formát modelu.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
from importlib.metadata import version
from pathlib import Path

import OCP
from build123d import Axis, Box, Compound, Cylinder, Part, Shape, Vertex
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet

from skodacad.geometry_validation import check_modification, inspect_volume
from skodacad.selectors import select_edges


def constant_volume(radius: float) -> float:
    """Jeden vypouklý roh kvádru: odpad = (čtverec − čtvrtkruh) × výška."""
    return 40 * 30 * 20 - (1 - math.pi / 4) * radius**2 * 20


def setback(part: Part, z: float) -> float:
    """Dvě místa dotyku zaoblení s boky na konci hrany, měřená od původního rohu."""
    values = []
    for vertex in part.vertices():
        if abs(vertex.Z - z) > 1e-6:
            continue
        if abs(vertex.X - 20) < 1e-6 and vertex.Y > 0:
            values.append(15 - vertex.Y)
        elif abs(vertex.Y - 15) < 1e-6 and vertex.X > 0:
            values.append(20 - vertex.X)
    assert len(values) == 2, values
    assert math.isclose(*values, abs_tol=1e-6), values
    return sum(values) / 2


def attempt(part: Part, low: float, high: float) -> tuple[Part | None, dict]:
    """Jedna úsečka významem; poloměry od nižšího Z, nezávisle na orientaci OCCT."""
    before = inspect_volume(part)
    edge, = select_edges(part, {"parallel": "Z", "near": [20, 15, 0]}, float)
    maker = BRepFilletAPI_MakeFillet(part.wrapped)
    maker.Add(edge.wrapped)
    contour = maker.Contour(edge.wrapped)
    assert contour > 0 and maker.NbEdges(contour) == 1
    first, last = Vertex(maker.FirstVertex(contour)), Vertex(maker.LastVertex(contour))
    radii = (low, high) if first.Z < last.Z else (high, low)
    # 1 je interní pořadí jediné hrany již nalezené kontury, nikoli výběr z part.edges().
    maker.SetRadius(*radii, contour, 1)
    maker.Build()
    record = {"requested_radii_mm": [low, high], "kernel_first_z_mm": first.Z,
              "kernel_radii_mm": list(radii), "kernel_done": maker.IsDone()}
    assert math.isclose(part.volume, before.volume, abs_tol=1e-7)
    if not maker.IsDone():
        return None, record
    candidate = Part(Compound([Shape.cast(maker.Shape())]).wrapped)
    after = inspect_volume(candidate)
    check_modification(before, after)
    assert after.solids == 1 and after.volume < before.volume
    bounds = candidate.bounding_box()
    assert all(abs(a - b) < 2e-6 for a, b in zip(
        (*bounds.min, *bounds.max), (-20, -15, -10, 20, 15, 10), strict=True))
    contacts = [setback(candidate, -10), setback(candidate, 10)]
    assert all(abs(a - b) < 1e-6 for a, b in zip(contacts, (low, high), strict=True))
    record.update(valid=True, solids=after.solids, volume_mm3=after.volume,
                  endpoint_setbacks_mm=contacts, input_unchanged=True)
    return candidate, record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path("out/p6-1-pruzkum-zaobleni.json"))
    args = parser.parse_args()
    records = {}
    for name, low, high, rotated, hole in [
        ("K1 konstantni R3", 3, 3, False, False),
        ("K2 promenne R2-R6", 2, 6, False, False),
        ("K3 opacne R6-R2", 6, 2, False, False),
        ("K4 obracena topologicka orientace", 2, 6, True, False),
        ("D1 otvor mimo zaobleni", 2, 6, False, True),
        ("F1 prilis velke R80", 80, 80, False, False),
    ]:
        part = Box(40, 30, 20)
        if rotated:
            part = part.rotate(Axis.X, 180)
        if hole:
            part = part - Cylinder(3, 20)
        candidate, record = attempt(part, low, high)
        records[name] = record
        if name.startswith("F1"):
            assert candidate is None, "R80 nesmí na tomto kvádru projít."
        else:
            assert candidate is not None, name
            if low == high:
                expected = constant_volume(low)
                assert math.isclose(candidate.volume, expected, abs_tol=1e-6)
                record["analytic_volume_mm3"] = expected
            else:
                removed_hole = math.pi * 3**2 * 20 if hole else 0
                assert (constant_volume(6) - removed_hole < candidate.volume
                        < constant_volume(2) - removed_hole)
                reference = records["K2 promenne R2-R6"]["volume_mm3"] - removed_hole
                assert math.isclose(candidate.volume, reference, abs_tol=1e-6)
        print(name, "odmítnuto jádrem" if candidate is None
              else f"{candidate.volume:.9f} mm³; konce {record['endpoint_setbacks_mm']}")
    result = {"python": platform.python_version(), "platform": platform.platform(),
              "build123d": version("build123d"), "ocp": OCP.__version__,
              "cases": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
