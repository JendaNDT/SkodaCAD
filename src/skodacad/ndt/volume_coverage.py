"""Objemové pokrytí UT (07B): skutečné průniky buněk, mm³ a ověřené vnitřní body.

Jeden bod zastupuje celý objemový kus; nejde o důkaz zásahu každého jeho místa.
Výsledek obsahuje pouze přenosná data, nikoli geometrii OCCT nebo povrchovou mapu.
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skodacad.ndt import UT_COVERAGE, UT_DISCLAIMER
from skodacad.ndt.coverage import (
    ALGORITHM as HIT_ALGORITHM,
)
from skodacad.ndt.coverage import (
    MAX_COMPARISONS,
    PERCENT_NOTE,
    STATES,
    CoverageError,
    CoverageHit,
    _evaluate_samples,
    _number,
    _scan_positions,
)
from skodacad.ndt.devices import Placement
from skodacad.ndt.geometry import PartGeometry, Point
from skodacad.ndt.study import target_fingerprint
from skodacad.ndt.ut import Refraction, trace_beam
from skodacad.ndt.welds import _weld_profiles, normalize_target, resolve_target

ALGORITHM = "ndt-ut-objemove-pokryti 1"
MAX_CELLS = 20_000
MAX_PIECES = 20_000
MAX_CLASSIFICATIONS = 1_000_000
APPROXIMATION = ("Stav vnitřního bodu zastupuje objem jeho kusu buňky; "
                 "není důkazem zásahu každého místa.")


@dataclass(frozen=True)
class VolumeSample:
    cell: tuple[int, int, int]
    piece: int
    bounds: tuple[Point, Point]  # místní souřadnice napříč, výška, podélně
    point: Point | None
    volume_mm3: float
    reason: str = ""


@dataclass(frozen=True)
class VolumeCoverageMap:
    samples: list[VolumeSample]
    states: list[str]
    hits: list[CoverageHit | None]
    reasons: list[str]
    requested_volume_mm3: float
    total_volume: float
    positions: int
    valid_positions: int
    uncertain_positions: int
    assumptions: dict[str, Any]
    seconds: float

    @property
    def sampled_volume(self) -> float:
        return math.fsum(s.volume_mm3 for s in self.samples)

    def volume(self, state: str) -> float:
        return math.fsum(s.volume_mm3 for s, status in zip(self.samples, self.states, strict=True)
                         if status == state)

    def percent(self, state: str) -> float:
        return 100 * self.volume(state) / self.total_volume

    def summary(self) -> list[str]:
        lines = [UT_COVERAGE, UT_DISCLAIMER, PERCENT_NOTE,
                 f"Cíl: objem; účinný objem {self.total_volume:.9g} mm³, "
                 f"zadaný {self.requested_volume_mm3:.9g} mm³.",
                 f"Součet vah {self.sampled_volume:.12g} mm³; "
                 f"odchylka {self.sampled_volume - self.total_volume:.6g} mm³.",
                 f"Polohy sondy: {self.positions}, platné {self.valid_positions}, "
                 f"nejisté {self.uncertain_positions}."]
        lines += [f"{label}: {self.percent(state):.2f} % ({self.volume(state):.9g} mm³)."
                  for state, label in STATES.items()]
        a = self.assumptions
        lines += [f"Krok pojezdu {a['scan_step_mm']:g} mm, cíle {a['target_step_mm']:g} mm, "
                  f"tolerance {a['tolerance_mm']:g} mm, rozevření {a['spread_deg']:g}°.",
                  APPROXIMATION,
                  a.get("convergence_text", "Citlivost na krok neověřena."),
                  f"Výpočet {self.seconds:.1f} s; algoritmus {ALGORITHM}."]
        lines.extend(dict.fromkeys(r for r in self.reasons if r))
        return lines

    def write_csv(self, path: str | Path) -> Path:
        path = Path(path)
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            for text in (UT_COVERAGE, UT_DISCLAIMER, PERCENT_NOTE,
                         *self.summary()[3:],
                         json.dumps(self.assumptions, ensure_ascii=False, sort_keys=True)):
                writer.writerow([text])
            writer.writerow(["buňka", "kus", "x [mm]", "y [mm]", "z [mm]", "objem [mm³]",
                             "stav", "důvod", "rameno", "dráha [mm]", "sonda x [mm]",
                             "sonda y [mm]", "sonda z [mm]"])

            def cz(value: float) -> str:
                return format(value, ".17g").replace(".", ",")

            for sample, state, hit, reason in zip(self.samples, self.states, self.hits,
                                                 self.reasons, strict=True):
                coords = [cz(v) for v in sample.point] if sample.point is not None else [""] * 3
                extra = ([hit.leg, cz(hit.distance), *(cz(v) for v in hit.origin)]
                         if hit else [""] * 5)
                writer.writerow(["/".join(map(str, sample.cell)), sample.piece, *coords,
                                 cz(sample.volume_mm3), STATES[state], reason, *extra])
        return path


class _InteriorSearch:
    def __init__(self) -> None:
        self.classifications = 0

    def point(self, solid: Any, plane: Any, geo: PartGeometry) -> Point | None:
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_IN

        classifier = BRepClass3d_SolidClassifier(solid.wrapped)
        box = solid.bounding_box()

        def candidates():
            yield tuple(solid.center())
            for depth in range(1, 5):
                n = 2**depth
                for indices in itertools.product(range(n), repeat=3):
                    yield tuple(a + (i + 0.5) * (b - a) / n for a, b, i in
                                zip(box.min, box.max, indices, strict=True))

        for local in candidates():
            if self.classifications + 2 > MAX_CLASSIFICATIONS:
                return None
            self.classifications += 1
            classifier.Perform(gp_Pnt(*local), 1e-7)
            if classifier.State() != TopAbs_IN:
                continue
            world = tuple(plane.from_local_coords(local))
            self.classifications += 1
            if geo.classify(world) == "inside":
                return world
        return None


def _intersection(cell: Any, target: Any) -> Any:
    """Samostatné místo pro geometrický průnik a regresní zkoušku chyby jádra."""
    return cell & target


def _check_volume(samples: list[VolumeSample], expected: float) -> float:
    total = math.fsum(s.volume_mm3 for s in samples)
    error = total - expected
    if not samples or not math.isfinite(total) or abs(error) > max(1e-6, expected * 1e-6):
        raise CoverageError("Rozdělení cíle nezachovalo objem – výsledek nelze spolehlivě "
                            "spočítat. Zkus jiný krok nebo zkontroluj geometrii cíle.")
    return error


def grid_extent(target: dict, step: float) -> tuple[Point, Point, tuple[int, int, int]]:
    """Místní rozsah mřížky cíle (napříč, výška, podélně) a počty buněk v osách – bez
    geometrie, takže jde spočítat i jako odhad před výpočtem."""
    target = normalize_target(target)
    profiles = [target["profile_mm"]] if target["kind"] == "volume" else _weld_profiles(target)
    vertices = [v for profile in profiles for v in profile]
    low = (min(v[0] for v in vertices), min(v[1] for v in vertices), 0.0)
    high = (max(v[0] for v in vertices), max(v[1] for v in vertices), target["length_mm"])
    counts = tuple(max(1, math.ceil((b - a) / step - 1e-12))
                   for a, b in zip(low, high, strict=True))
    return low, high, counts


def _sample_volume(geo: PartGeometry, target: dict, step: float, positions: int,
                   legs: int) -> tuple[list[VolumeSample], Any, dict]:
    from build123d import Align, Box, Location, Plane

    f = target["frame"]
    # Pravotočivá rovina: její Y = -výška, Z = axis. V uložených mezích je výška kladná.
    plane = Plane(origin=f["origin"], x_dir=f["across"], z_dir=f["axis"])
    low, high, counts = grid_extent(target, step)
    count = math.prod(counts)
    if count > MAX_CELLS or count * positions * legs > MAX_COMPARISONS:
        raise CoverageError("Objemová mřížka je příliš jemná – zvětši krok cíle nebo pojezdu.")
    resolved = resolve_target(geo.part, target)
    local_target = plane.to_local_coords(resolved.shape)
    samples = []
    search = _InteriorSearch()
    for indices in itertools.product(*(range(n) for n in counts)):
        lo = tuple(a + i * step for a, i in zip(low, indices, strict=True))
        hi = tuple(min(a + (i + 1) * step, b)
                   for a, b, i in zip(low, high, indices, strict=True))
        cell = Box(*(b - a for a, b in zip(lo, hi, strict=True)),
                   align=(Align.MIN, Align.MIN, Align.MIN))
        cell = cell.located(Location((lo[0], -hi[1], lo[2])))
        try:
            clipped = _intersection(cell, local_target)
            if clipped is None:
                continue
            if not clipped.is_valid:
                raise CoverageError("Průnik objemové buňky není platné těleso.")
            for i, solid in enumerate(clipped.solids()):
                volume = solid.volume
                if not solid.is_valid or not math.isfinite(volume) or volume < 0:
                    raise CoverageError("Objem kusu buňky nelze spolehlivě určit.")
                if volume == 0:
                    continue
                if (len(samples) >= MAX_PIECES
                        or (len(samples) + 1) * positions * legs > MAX_COMPARISONS):
                    raise CoverageError("Cíl má příliš mnoho objemových kusů – zvětši krok.")
                try:
                    point = search.point(solid, plane, geo)
                except Exception:  # noqa: BLE001 – váha je známá, selhalo jen určení bodu
                    point = None
                reason = ("" if point is not None else
                          "Objem je známý, ale spolehlivý vnitřní bod nebyl nalezen "
                          "nebo byl dosažen limit jeho hledání.")
                samples.append(VolumeSample(indices, i, (lo, hi), point, volume, reason))
        except CoverageError:
            raise
        except Exception as exc:  # noqa: BLE001 – neznámou váhu nesmíme nahradit nulou
            raise CoverageError(f"Průnik objemové buňky nelze ověřit: {exc}") from None
    error = _check_volume(samples, resolved.volume_mm3)
    metadata = {"grid_frame": f, "grid_min": low, "grid_max": high,
                "candidate_cells": count, "samples": len(samples),
                "interior_classifications": search.classifications,
                "requested_volume_mm3": resolved.requested_volume_mm3,
                "effective_volume_mm3": resolved.volume_mm3,
                "sampled_volume_mm3": math.fsum(s.volume_mm3 for s in samples),
                "volume_error_mm3": error,
                "volume_tolerance_mm3": max(1e-6, resolved.volume_mm3 * 1e-6)}
    return samples, resolved, metadata


def compute_volume(geo: PartGeometry, placement: Placement, *, target: dict,
                   mode: str = "face", scan_step: float = 5.0, target_step: float = 4.0,
                   length_mm: float = 50.0, angle_deg: float = 0.0,
                   tolerance_mm: float | None = None, spread_deg: float = 0.0,
                   beta: float | None = None, bounces: int | None = None,
                   max_length: float | None = None,
                   refraction: Refraction | None = None) -> VolumeCoverageMap:
    started = time.monotonic()
    scan_step = _number(scan_step, "Krok pojezdu [mm]", 0.1, 1000)
    target_step = _number(target_step, "Krok cíle [mm]", 0.1, 1000)
    length_mm = _number(length_mm, "Délka pojezdu [mm]", 0, 100000)
    angle_deg = _number(angle_deg, "Směr sondy [°]", -36000, 36000)
    spread_deg = _number(spread_deg, "Rozevření [°]", 0, 45)
    if mode not in ("line", "face"):
        raise CoverageError("Zvol pojezd po ploše (face) nebo po přímce (line).")
    if mode == "line" and spread_deg == 0:
        raise CoverageError("Pojezd po čáře bez rozevření svazku nevymezuje pokrytý objem. "
                            "Pro objem zvol pojezd po ploše; pro čáru lze samostatně "
                            "vyhodnotit body nebo plochy.")
    tolerance = (scan_step * (math.sqrt(0.5) if mode == "face" else 0.6)
                 if tolerance_mm is None else _number(
                     tolerance_mm, "Tolerance zachycení [mm]", 0, 1000))
    target = normalize_target(target)
    beam = trace_beam(geo, placement, beta, bounces, max_length, refraction)
    candidates = _scan_positions(placement, mode, scan_step, length_mm)
    try:
        samples, resolved, metadata = _sample_volume(geo, target, target_step,
                                                    len(candidates), beam.bounces + 1)
    except CoverageError:
        raise
    except Exception as exc:  # noqa: BLE001 – i příprava geometrie musí mít českou chybu
        raise CoverageError(f"Cílový objem nelze rozdělit: {exc}") from None
    states, hits, reasons, positions, valid, uncertain, assumptions = _evaluate_samples(
        geo, placement, [s.point for s in samples], [s.reason for s in samples],
        candidates, beam, mode=mode, scan_step=scan_step, target_step=target_step,
        length_mm=length_mm, angle_deg=angle_deg, tolerance=tolerance, spread_deg=spread_deg,
        beta=beta, bounces=bounces, max_length=max_length, refraction=refraction)
    assumptions.update(metadata, target=target, target_kind=target["kind"],
                       quantity="volume", unit="mm³",
                       target_fingerprint=target_fingerprint(target),
                       volume_algorithm=ALGORITHM, hit_algorithm=HIT_ALGORITHM,
                       approximation=APPROXIMATION)
    return VolumeCoverageMap(samples, states, hits, reasons, resolved.requested_volume_mm3,
                             resolved.volume_mm3, positions, valid, uncertain, assumptions,
                             time.monotonic() - started)


@dataclass(frozen=True)
class VolumeConvergence:
    fine: dict[str, float]
    coarse: dict[str, float]
    delta_pct: float
    fine_steps: tuple[float, float]
    coarse_steps: tuple[float, float]

    @property
    def stable(self) -> bool:
        return self.delta_pct <= 1

    @property
    def text(self) -> str:
        values = "; ".join(f"{label} {self.fine[s]:.2f} / {self.coarse[s]:.2f} %"
                           for s, label in STATES.items())
        return (f"Citlivost na krok: největší rozdíl tří stavů {self.delta_pct:.2f} "
                f"procentního bodu; kroky pojezdu/cíle {self.fine_steps} / "
                f"{self.coarse_steps} mm. {values}. "
                + ("Nízká pozorovaná citlivost do 1 p. b.; není zárukou přesnosti."
                   if self.stable else "Zjemni krok výpočtu."))


def check_volume_convergence(geo: PartGeometry, placement: Placement, *,
                             fine: VolumeCoverageMap | None = None,
                             **kwargs: Any) -> VolumeConvergence:
    """CLI předá již spočítaný jemný běh; tolerance se pro hrubý běh nezvětší."""
    if fine is None:
        fine = compute_volume(geo, placement, **kwargs)
    a = fine.assumptions
    fine_steps = (a["scan_step_mm"], a["target_step_mm"])
    coarse_steps = tuple(v * 2 for v in fine_steps)
    coarse = compute_volume(geo, placement, **(kwargs | {
        "scan_step": coarse_steps[0], "target_step": coarse_steps[1],
        "tolerance_mm": a["tolerance_mm"]}))
    if not math.isclose(fine.total_volume, coarse.total_volume, rel_tol=1e-8, abs_tol=1e-6):
        raise CoverageError("Porovnání kroků nemá shodný cílový objem.")
    f, c = ({s: result.percent(s) for s in STATES} for result in (fine, coarse))
    result = VolumeConvergence(f, c, max(abs(f[s] - c[s]) for s in STATES),
                               fine_steps, coarse_steps)
    fine.assumptions.update(convergence={"fine_pct": f, "coarse_pct": c,
                                         "delta_pp": result.delta_pct,
                                         "fine_steps_mm": fine_steps,
                                         "coarse_steps_mm": coarse_steps,
                                         "tolerance_mm": a["tolerance_mm"]},
                            convergence_text=result.text)
    return result
