"""P6: spustitelný průzkum řízených přechodů, mimo produkční formát a aplikaci.

python docs/p6-6-pruzkum-voditek.py --output out/p6-guided-loft-study
Každý případ běží v samostatném procesu s limitem; důkazy obsahují vstupy,
G0 odchylky, analytické reference, P1, STEP a SVG. Žádná síť jako zdroj měření.
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
from build123d import Edge, Face, Plane, Shell, Solid, Vector, Wire, loft, section
from numpy.polynomial import Polynomial
from OCP.BRep import BRep_Tool

from skodacad.export import export
from skodacad.geometry_validation import inspect_volume
from skodacad.ndt.geometry import PartGeometry

CASES = ("rovny", "vybouleny", "ohnuty", "vice_profilu", "obracene_krivky",
         "kruhy_dva_profily", "kruhy_tri_profily", "mezera", "krizeni")
TOL = 1e-5  # mm: číselná mez průzkumu, nikoli výrobní tolerance
AREA_TOL = 1e-5  # mm²: číselná mez orientovaného součinu stran
GORDON_TOL = 1e-6
STEPS = tuple(i / 40 for i in range(41))
H = 60.0


def point(poles: list, t: float) -> tuple[float, float, float]:
    """Nezávislá Bernsteinova rovnice kubické vodicí křivky, bez jádra."""
    return tuple(math.fsum(math.comb(3, k) * t**k * (1 - t)**(3 - k) * poles[k][j]
                           for k in range(4)) for j in range(3))


def polynomial(poles: list, axis: int) -> Polynomial:
    a, b, c, d = [p[axis] for p in poles]
    return Polynomial([a, 3 * (b - a), 3 * (c - 2 * b + a), d - 3*c + 3*b - a])


def minimum(poly: Polynomial) -> float:
    candidates = [0.0, 1.0, *(float(r.real) for r in poly.deriv().roots()
                             if abs(r.imag) < 1e-8 and 0 < r.real < 1)]
    return min(float(poly(t)) for t in candidates)


def analytic(controls: list) -> tuple[float, float]:
    """Objem: integrál plošného obsahu čtyřúhelníku v z=H*t, shoelace vzorec.

    Minimum orientovaných součinů stran včetně stacionárních bodů hlídá
    konvexní nekolabující průřezy, nikoli jen několik řezů na obrázku.
    """
    xy = [(polynomial(p, 0), polynomial(p, 1)) for p in controls]
    area = Polynomial([0.0])
    crosses = []
    for i in range(4):
        x, y = xy[i]
        xx, yy = xy[(i + 1) % 4]
        xxx, yyy = xy[(i + 2) % 4]
        area += (x * yy - y * xx) / 2
        crosses.append((xx - x) * (yyy - yy) - (yy - y) * (xxx - xx))
    integral = area.integ()
    return H * float(integral(1) - integral(0)), min(minimum(p) for p in crosses)


def inputs(case: str) -> dict:
    circular = case.startswith("kruhy")
    bend = case in ("ohnuty", "vice_profilu", "obracene_krivky")
    bulge = case != "rovny"
    controls = []
    corners = ([(20 * math.cos(i * math.pi / 2), 20 * math.sin(i * math.pi / 2))
                for i in range(4)] if circular else [(20, 15), (-20, 15), (-20, -15), (20, -15)])
    for x, y in corners:
        x_end, y_end = (x, y) if circular else (x * .6, y * .6)
        bx, by = ((x / 4, y / 4) if circular else
                  (math.copysign(7, x), math.copysign(5, y))) if bulge else (0, 0)
        controls.append([(x, y, 0),
            (x + (x_end - x) / 3 + 4*bx/3 + (10 if bend else 0),
             y + (y_end - y) / 3 + 4*by/3 + (8 if bend else 0), H/3),
            (x + 2*(x_end - x) / 3 + 4*bx/3 - (8 if bend else 0),
             y + 2*(y_end - y) / 3 + 4*by/3 - (5 if bend else 0), 2*H/3),
            (x_end, y_end, H)])
    profile_controls = [[list(p) for p in rail] for rail in controls]
    if case == "mezera":
        controls[0][0] = (21, 15, 0)
    if case == "krizeni":
        for i, sign in ((0, -1), (1, 1)):
            controls[i][1] = (sign * 40, controls[i][1][1], H / 3)
            controls[i][2] = (sign * 40, controls[i][2][1], 2 * H / 3)
    return {"format": "skodacad-guided-loft-study", "schema_version": 1, "case": case,
            "circular": circular, "height_mm": H, "guides_cubic_poles_mm": controls,
            "profile_corner_poles_mm": profile_controls,
            "profile_parameters": ([0, .17, .63, 1] if case == "vice_profilu" else
                                   [0, .5, 1] if case == "kruhy_tri_profily" else [0, 1]),
            "reverse_curve_geometry": case == "obracene_krivky"}


def profiles_for(data: dict) -> list[list[Edge]]:
    controls = data["profile_corner_poles_mm"]
    profiles = []
    for t in data["profile_parameters"]:
        if data["circular"]:
            radius = 20 + 20 * t * (1 - t)
            edges = [Edge.make_circle(radius, Plane(origin=(0, 0, H * t)),
                                     start_angle=i * 90, end_angle=(i + 1) * 90)
                     for i in range(4)]
        else:
            vertices = [point(p, t) for p in controls]
            edges = [Edge.make_line(vertices[i], vertices[(i + 1) % 4]) for i in range(4)]
            if data["reverse_curve_geometry"]:
                edges = [Edge.make_line(vertices[(i + 1) % 4], vertices[i]) for i in range(4)]
        profiles.append(edges)
    return profiles


def curve_samples(profiles: list, guides: list) -> list[dict]:
    """Snímek původních vstupů před voláním jádra; pozdější změna jej nezmění."""
    results = []
    for i in range(4):
        curves = [(f"profil_{j}", p[i]) for j, p in enumerate(profiles)]
        curves += [(f"voditko_{j}", guides[j]) for j in (i, (i + 1) % 4)]
        for label, curve in curves:
            for t in STEPS:
                results.append({"patch": i, "curve": label, "parameter": t,
                                "point_mm": tuple(curve.position_at(t))})
    return results


def boundary_measurements(sides: list, sources: list) -> list[dict]:
    return [{**s, "distance_mm": sides[s["patch"]].distance_to(Vector(s["point_mm"]))}
            for s in sources]


def export_evidence(solid: Solid, controls: list, folder: Path, name: str) -> None:
    export(solid, folder / f"{name}.step")
    export(solid, folder / f"{name}.svg")
    vertices, triangles = solid.tessellate(.15, .1)
    (folder / f"{name}-mesh.json").write_text(json.dumps({
        "visualization_only": True, "deflection_mm": .15,
        "vertices": [tuple(v) for v in vertices], "triangles": triangles,
        "guides": [[point(rail, t) for t in STEPS] for rail in controls]}), encoding="utf-8")


def run_case(case: str, folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    data = inputs(case)
    (folder / "inputs.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    controls = data["guides_cubic_poles_mm"]
    original_controls = data["profile_corner_poles_mm"]
    profiles = profiles_for(data)
    caps = [Face(Wire(p)) for p in (profiles[0], profiles[-1])]
    plain = loft(caps)
    inspect_volume(plain)
    guides = [Edge.make_bezier(*(list(reversed(p)) if data["reverse_curve_geometry"] else p))
              for p in controls]
    gap = max(math.dist(rail[end], original[end]) for rail, original in
              zip(controls, original_controls, strict=True) for end in (0, -1))
    expected, convexity = analytic(controls)
    negative = case in ("mezera", "krizeni")
    input_problem = ("Vodítko nedosahuje koncového profilu." if gap > TOL else
                     "Vodítka kolabují nebo kříží průřez." if convexity <= AREA_TOL else "")
    result = {"case": case, "input_problem": input_problem, "endpoint_gap_mm": gap,
              "minimum_convexity_mm2": convexity, "plain_volume_mm3": plain.volume,
              "kernel_status": "attempted", "p1_valid": False, "meets_reference": False}
    sources = curve_samples(profiles, guides)
    start = time.monotonic()
    try:
        sides = []
        for i in range(4):
            ps = [p[i] for p in profiles]
            gs = [guides[i], guides[(i + 1) % 4]]
            if data["reverse_curve_geometry"]:
                ps.reverse()
                gs.reverse()
            sides.append(Face.make_gordon_surface(ps, gs, tolerance=GORDON_TOL))
        result["kernel_status"] = "surfaces_built"
        samples = boundary_measurements(sides, sources)
        after = curve_samples(profiles, guides)
        input_change = max(math.dist(a["point_mm"], b["point_mm"])
                           for a, b in zip(sources, after, strict=True))
        result["maximum_sampled_input_change_mm"] = input_change
        boundary_error = max(s["distance_mm"] for s in samples)
        (folder / "boundary-samples.json").write_text(json.dumps(samples), encoding="utf-8")
        result["maximum_boundary_error_mm"] = boundary_error
        candidate = Solid(Shell([*sides, *caps]))
        facts = inspect_volume(candidate)
        assert facts.solids == 1
        result.update(kernel_status="solid_built", p1_valid=True, volume_mm3=facts.volume,
                      max_topology_tolerance_mm=max(BRep_Tool.Tolerance_s(e.wrapped)
                                                   for e in candidate.edges()))
        if data["circular"]:
            reference_volume = 32800 * math.pi  # ∫ π[20+20t(1−t)]² · 60 dt
            ray = PartGeometry(candidate).cast((0, 0, H/2), (1, 1, 0))
            assert len(ray.segments) == 1 and ray.segments[0].certain
            diagonal_radius = ray.segments[0].length
            radii = []
            geometry = PartGeometry(candidate)
            for t in (.05, .125, .25, .375, .5, .625, .75, .875, .95):
                for quadrant in range(4):
                    for degrees in (15, 30, 45, 60, 75):
                        angle = math.radians(quadrant * 90 + degrees)
                        trace = geometry.cast((0, 0, H*t), (math.cos(angle), math.sin(angle), 0))
                        assert len(trace.segments) == 1 and trace.segments[0].certain
                        length = trace.segments[0].length
                        radii.append({"z_mm": H*t, "angle_deg": quadrant*90+degrees,
                                      "radius_mm": length,
                                      "reference_radius_mm": 20+20*t*(1-t),
                                      "error_mm": abs(length-(20+20*t*(1-t)))})
            (folder / "radial-samples.json").write_text(json.dumps(radii), encoding="utf-8")
            radial_error = max(r["error_mm"] for r in radii)
            seam_angles = []
            for i in range(4):
                for t in (.2, .5, .8):
                    p = point(controls[i], t)
                    n1, n2 = sides[i - 1].normal_at(p), sides[i].normal_at(p)
                    seam_angles.append(math.degrees(math.acos(min(1, abs(n1.dot(n2))))))
            result.update(analytic_revolution_volume_mm3=reference_volume,
                          revolution_volume_difference_mm3=candidate.volume-reference_volume,
                          middle_diagonal_radius_mm=diagonal_radius,
                          maximum_sampled_radial_error_mm=radial_error,
                          expected_middle_radius_mm=25,
                          maximum_sampled_seam_angle_deg=max(seam_angles),
                          middle_section_area_mm2=section(
                              candidate, section_by=Plane(origin=(0, 0, H/2))).area)
            result["meets_reference"] = (radial_error < TOL and
                abs(candidate.volume-reference_volume) < .01 and max(seam_angles) < .01)
        elif not input_problem:
            reference_faces = [Face.make_bezier_surface(
                [controls[i], controls[(i + 1) % 4]]) for i in range(4)]
            reference = Solid(Shell([*reference_faces, *caps]))
            inspect_volume(reference)
            reference_boundary = max(s["distance_mm"] for s in boundary_measurements(
                reference_faces, sources))
            interior = []
            for i, face in enumerate(sides):
                for t in (.11, .27, .5, .71, .89):
                    a, b = point(controls[i], t), point(controls[(i + 1) % 4], t)
                    for u in (.19, .37, .63, .81):
                        p = tuple((1-u)*x+u*y for x, y in zip(a, b, strict=True))
                        interior.append(face.distance_to(Vector(p)))
            result.update(analytic_volume_mm3=expected,
                          volume_error_mm3=abs(candidate.volume-expected),
                          bezier_reference_volume_mm3=reference.volume,
                          bezier_boundary_error_mm=reference_boundary,
                          maximum_analytic_surface_error_mm=max(interior))
            tolerance = max(2e-5, abs(expected)*1e-9)
            assert abs(reference.volume-expected) < tolerance and reference_boundary < TOL
            result["meets_reference"] = (abs(candidate.volume-expected) < tolerance
                                          and max(interior) < TOL)
        if not negative:
            export_evidence(candidate, controls, folder, "guided")
            export_evidence(plain, controls, folder, "plain")
        if not negative:
            assert boundary_error < TOL and input_change < TOL, result
            assert result["max_topology_tolerance_mm"] <= TOL, result
    except Exception as exc:  # noqa: BLE001 -- důkaz odmítnutí i chyba jádra jsou data průzkumu
        result["kernel_error"] = f"{type(exc).__name__}: {exc}"
        if not negative:
            (folder / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            raise
    result["seconds"] = time.monotonic() - start
    if negative:
        assert input_problem, result
        result["reference_accepted"] = False
    else:
        result["reference_accepted"] = result["meets_reference"]
        assert result["p1_valid"], result
        if case != "kruhy_dva_profily":
            assert result["meets_reference"], result
        else:
            # Záměrný protidůkaz: čtyři vodítka + dvě kružnice nedokazují kruhový meziřez/G1.
            assert not result["meets_reference"] and max(seam_angles) > 10, result
            assert abs(diagonal_radius - (20 + 5/math.sqrt(2))) < TOL, result
    (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("out/p6-guided-loft-study"))
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.case:
        print(json.dumps(run_case(args.case, args.output / args.case), ensure_ascii=False))
        return
    results = []
    summary = {"complete": False, "platform": platform.platform(),
               "python": platform.python_version(), "build123d": version("build123d"),
               "ocp": OCP.__version__, "ocp_gordon": version("ocp_gordon"),
               "numpy": version("numpy"), "scipy": version("scipy"),
               "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "numeric_tolerance_mm": TOL, "convexity_tolerance_mm2": AREA_TOL,
               "gordon_tolerance_mm": GORDON_TOL,
               "boundary_points_per_curve": len(STEPS), "cases": results}
    summary_path = args.output / "results.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for case in CASES:
        try:
            child = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                    "--output", str(args.output.resolve()), "--case", case],
                                   text=True, capture_output=True, encoding="utf-8", timeout=60)
        except subprocess.TimeoutExpired as exc:
            raise SystemExit(f"Případ {case} překročil limit 60 sekund.") from exc
        (args.output / f"{case}.log").write_text(child.stdout + child.stderr, encoding="utf-8")
        if child.returncode:
            raise SystemExit(f"Případ {case} selhal: {child.stderr[-4000:]}")
        result = json.loads((args.output / case / "result.json").read_text(encoding="utf-8"))
        results.append(result)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)
    summary["complete"] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {len(results)} případů; {args.output / 'results.json'}")


if __name__ == "__main__":
    main()
