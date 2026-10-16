"""Geometrický model UT paprsku (etapa 04): přímá a úhlová sonda, Snellův zákon a odrazy.

Střední paprsek svazku jako lomená čára z výstupního bodu přiložené sondy (``devices.Placement``)
přes geometrické jádro (``geometry.PartGeometry``). Počítá jen geometrickou dráhu v materiálu,
půlkrok, celý krok a úhly dopadu – nikdy fyzikální útlum, rozptyl ani záchyt vad
(viz ``docs/ndt/04-zavazne-vymezeni-ut.md``). Lom podle Snellova zákona vyžaduje výslovně
zadané rychlosti v předsádce a v materiálu.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from skodacad.ndt.devices import Placement
from skodacad.ndt.geometry import (
    ALONG_SURFACE,
    EDGE_TOL,
    LENGTH_TOL,
    UNDECIDED,
    Hit,
    PartGeometry,
    Point,
)

ALGORITHM = "ndt-ut-paprsek 1"  # verze algoritmu (do protokolu)
DEFAULT_ANGLE = 45.0  # ° – výchozí úhel lomu úhlové sondy v materiálu
DEFAULT_BOUNCES = 1  # výchozí počet odrazů úhlové sondy (1 odraz = 2 ramena = celý krok)
ANGLE_LIMITS = (1.0, 85.0)  # ° – povolený rozsah úhlu lomu úhlové sondy
BOUNCE_LIMITS = (0, 10)  # povolený počet odrazů
SPEED_LIMITS = (100.0, 20000.0)  # m/s – povolený rozsah rychlostí vln pro Snellův zákon
WAVES = {"shear": "příčná", "longitudinal": "podélná"}

NO_ENTRY = "Paprsek v místě přiložení nevstupuje do materiálu (okraj, otvor nebo povrch)."
STOPPED_UNCERTAIN = ("Další odraz se nepočítá – dopad není jednoznačný "
                     "(hrana, roh nebo tečný dotyk).")


class BeamError(ValueError):
    """Chybně zadaný úhel paprsku, lom nebo počet odrazů (zpráva česky)."""


# --- lom podle Snellova zákona -------------------------------------------------------------


@dataclass(frozen=True)
class Refraction:
    """Lom paprsku na rozhraní předsádka → díl podle Snellova zákona se zadanými rychlostmi."""

    alpha: float  # úhel v předsádce od kolmice [°]
    c_wedge: float  # rychlost vlny v předsádce [m/s]
    c_material: float  # rychlost vlny v materiálu [m/s]
    wave: str  # shear (příčná) / longitudinal (podélná)
    beta: float  # vypočtený úhel lomu v materiálu [°]
    critical_angle: float | None  # kritický úhel v předsádce [°] (None, když c_material <= c_wedge)

    @property
    def wave_label(self) -> str:
        return WAVES[self.wave]

    @property
    def label(self) -> str:
        crit = (f", kritický úhel {self.critical_angle:.1f}°"
                if self.critical_angle is not None else "")
        return (f"Snellův zákon: α = {self.alpha:g}°, c1 = {self.c_wedge:g} m/s, "
                f"c2 = {self.c_material:g} m/s ({self.wave_label} vlna) → "
                f"β = {self.beta:.2f}°{crit}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha_deg": self.alpha,
            "c_wedge_m_s": self.c_wedge,
            "c_material_m_s": self.c_material,
            "wave": self.wave,
            "beta_deg": round(self.beta, 4),
            "critical_angle_deg": (round(self.critical_angle, 4)
                                   if self.critical_angle is not None else None),
        }


def refract(alpha: float, c_wedge: float, c_material: float, wave: str = "shear") -> Refraction:
    """Spočítá úhel lomu ``beta`` v materiálu ze Snellova zákona: sin(beta)/c2 = sin(alpha)/c1.

    Rychlosti ``c_wedge`` a ``c_material`` [m/s] musí být výslovně zadané. Při nadkritickém
    úhlu (totální odraz) vyhodí ``BeamError`` s českým vysvětlením.
    """
    if wave not in WAVES:
        raise BeamError(f"Druh vlny musí být „shear“ (příčná) nebo „longitudinal“ (podélná), "
                        f"je {wave!r}.")
    alpha_val = _number(alpha, "Úhel v předsádce")
    if not (0.0 < alpha_val < 90.0):
        raise BeamError(f"Úhel v předsádce musí být mezi 0° a 90° (je {alpha_val:g}°).")
    c1 = _number(c_wedge, "Rychlost vlny v předsádce")
    c2 = _number(c_material, "Rychlost vlny v materiálu")
    low, high = SPEED_LIMITS
    if not (low <= c1 <= high):
        raise BeamError(f"Rychlost vlny v předsádce musí být {low:g}–{high:g} m/s (je {c1:g}).")
    if not (low <= c2 <= high):
        raise BeamError(f"Rychlost vlny v materiálu musí být {low:g}–{high:g} m/s (je {c2:g}).")

    critical = math.degrees(math.asin(c1 / c2)) if c2 > c1 else None
    sin_beta = (c2 / c1) * math.sin(math.radians(alpha_val))
    if sin_beta >= 1.0 - 1e-9:
        crit_text = f" (kritický úhel je {critical:.1f}°)" if critical is not None else ""
        raise BeamError(f"Nadkritický úhel: pro α = {alpha_val:g}° a rychlosti "
                        f"{c1:g} → {c2:g} m/s nastává totální odraz{crit_text} – "
                        "vlna do materiálu nevstoupí.")
    beta = math.degrees(math.asin(sin_beta))
    return Refraction(alpha_val, c1, c2, wave, beta, critical)


# --- dráha paprsku -------------------------------------------------------------------------


@dataclass(frozen=True)
class BeamLeg:
    """Jedno přímé rameno paprsku v materiálu (1 = přímý paprsek, 2 = po 1. odrazu …)."""

    index: int
    start: Point  # počátek ramene [mm]
    end: Point  # konec ramene [mm]
    direction: Point  # jednotkový směr ramene
    length: float  # délka tohoto ramene v materiálu [mm]
    cumulative_length: float  # celková dráha od výstupního bodu po konec ramene [mm]
    horizontal: float  # vodorovná vzdálenost konce od výstupního bodu v rovině přiložení [mm]
    along: float  # průmět posunu od výstupního bodu do směru paprsku sondy (+dopředu) [mm]
    depth: float  # hloubka konce pod rovinou přiložení (proti normále plochy) [mm]
    incidence: float | None  # úhel dopadu na konci ramene od normály [°] (None = konec v materiálu)
    hit: Hit | None  # průsečík s povrchem na konci ramene (None = omezeno max_length)
    reasons: tuple[str, ...] = ()

    @property
    def certain(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class BeamPath:
    """Geometrická dráha středního paprsku UT svazku ze sondy přiložené na díl."""

    placement: Placement
    beta: float  # úhel lomu v materiálu od kolmice [°] (u přímé sondy 0°)
    bounces: int  # povolený počet odrazů
    max_length: float | None  # omezení celkové dráhy v materiálu [mm]
    refraction: Refraction | None  # výpočet ze Snellova zákona, pokud byl použit
    legs: tuple[BeamLeg, ...]
    reasons: tuple[str, ...] = ()

    @property
    def certain(self) -> bool:
        return bool(self.legs) and not self.reasons and all(leg.certain for leg in self.legs)

    @property
    def ok(self) -> bool:
        return self.certain

    @property
    def total_length(self) -> float:
        """Celková délka dráhy v materiálu – jen jistá ramena [mm]."""
        return sum(leg.length for leg in self.legs if leg.certain)

    @property
    def actual_bounces(self) -> int:
        return max(0, len(self.legs) - 1)

    @property
    def points(self) -> tuple[Point, ...]:
        """Body lomené čáry paprsku (výstupní bod + konce ramen) pro vykreslení ve 3D."""
        return (self.placement.origin, *(leg.end for leg in self.legs)) if self.legs else ()

    @property
    def end_point(self) -> Point | None:
        return self.legs[-1].end if self.legs else None

    @property
    def half_skip(self) -> float | None:
        """Vodorovná vzdálenost 1. dopadu v rovině přiložení (půlkrok) [mm]."""
        if self.legs and self.legs[0].certain and self.legs[0].hit is not None:
            return self.legs[0].horizontal
        return None

    @property
    def full_skip(self) -> float | None:
        """Vodorovná vzdálenost 2. dopadu v rovině přiložení (celý krok) [mm]."""
        if (len(self.legs) >= 2 and self.legs[0].certain and self.legs[1].certain
                and self.legs[1].hit is not None):
            return self.legs[1].horizontal
        return None

    @property
    def assumptions(self) -> dict[str, Any]:
        """Explicitní záznam předpokladů výpočtu (pro protokol a ověřitelnost)."""
        data: dict[str, Any] = {
            "algorithm": ALGORITHM,
            "probe_kind": self.placement.probe.kind,
            "beta_deg": round(self.beta, 4),
            "bounces": self.bounces,
            "max_length_mm": self.max_length,
        }
        if self.refraction is not None:
            data["refraction"] = self.refraction.to_dict()
        return data

    @property
    def short(self) -> str:
        """Krátký popisek dráhy do 3D a stavového řádku."""
        if not self.legs:
            return "paprsek mimo materiál"
        if self.placement.probe.kind == "straight":
            return f"dráha {self.legs[0].length:.2f} mm"
        if self.half_skip is not None:
            return (f"β {self.beta:g}° · půlkrok {self.half_skip:.1f} mm · "
                    f"dráha {self.total_length:.1f} mm")
        return f"β {self.beta:g}° · dráha {self.total_length:.1f} mm"

    def summary_lines(self) -> list[str]:
        """Český víceřádkový souhrn dráhy pro panel NDT a příkazovou řádku."""
        bounces_word = ("bez odrazu" if self.bounces == 0
                        else f"nejvýš {self.bounces} {_bounce_word(self.bounces)}")
        header = (f"Dráha paprsku (úhel lomu {self.beta:.1f}°, {bounces_word}, "
                  f"algoritmus {ALGORITHM}):")
        lines = [header]
        if self.refraction is not None:
            lines.append(f"  {self.refraction.label}")
        if not self.legs:
            lines.append("  paprsek materiálem neprochází")
        for leg in self.legs:
            hit_text = (f"dopad {leg.incidence:.1f}°" if leg.incidence is not None
                        else "konec dosahu v materiálu")
            mark = "" if leg.certain else " – NEJISTÉ"
            lines.append(
                f"  rameno {leg.index}: [{_coords(leg.start)}] → [{_coords(leg.end)}], "
                f"délka {leg.length:.2f} mm, vodorovně {leg.horizontal:.2f} mm, "
                f"hloubka {leg.depth:.2f} mm ({hit_text}){mark}"
            )
        skips = []
        if self.placement.probe.kind == "angle":
            if self.half_skip is not None:
                skips.append(f"půlkrok {self.half_skip:.2f} mm")
            if self.full_skip is not None:
                skips.append(f"celý krok {self.full_skip:.2f} mm")
        skip_part = (", " + ", ".join(skips)) if skips else ""
        certainty = "ok" if self.certain else "NEJISTÉ"
        lines.append(f"  celkem v materiálu: {self.total_length:.2f} mm{skip_part}, "
                     f"jistota: {certainty}")
        for reason in self.reasons:
            lines.append(f"  ⚠ {reason}")
        return lines

    @property
    def text(self) -> str:
        return "\n".join(self.summary_lines())


def trace_beam(geo: PartGeometry, placement: Placement, beta: float | None = None,
               bounces: int | None = None, max_length: float | None = None,
               refraction: Refraction | None = None) -> BeamPath:
    """Vypočítá geometrickou dráhu středního paprsku ze sondy ``placement`` v dílu ``geo``.

    - U přímé sondy míří paprsek vždy kolmo do materiálu (``beta = 0°``), výchozí ``bounces = 0``.
    - U úhlové sondy se použije ``refraction.beta`` (je-li zadán ``refraction``), jinak ``beta``
      (výchozí ``placement.probe.beam_angle``; rozsah 1–85°), výchozí ``bounces`` ze sondy (1).
    """
    probe = placement.probe
    if probe.kind == "straight":
        if refraction is not None or (beta is not None and float(beta) != 0.0):
            raise BeamError("Přímá sonda vysílá paprsek kolmo do materiálu (0°) – "
                            "pro šikmý paprsek zvol úhlovou sondu.")
        beta_val = 0.0
        max_bounces = getattr(probe, "bounces", 0) if bounces is None else bounces
    else:
        if refraction is not None:
            beta_val = refraction.beta
        elif beta is not None:
            beta_val = _number(beta, "Úhel lomu v materiálu")
        else:
            beta_val = float(getattr(probe, "beam_angle", DEFAULT_ANGLE))
        low_a, high_a = ANGLE_LIMITS
        if not (low_a <= beta_val <= high_a):
            raise BeamError(f"Úhel lomu v materiálu musí být {low_a:g}–{high_a:g}° "
                            f"(je {beta_val:g}°).")
        max_bounces = getattr(probe, "bounces", DEFAULT_BOUNCES) if bounces is None else bounces

    if (not isinstance(max_bounces, int) or isinstance(max_bounces, bool)
            or not (BOUNCE_LIMITS[0] <= max_bounces <= BOUNCE_LIMITS[1])):
        raise BeamError(f"Počet odrazů musí být celé číslo {BOUNCE_LIMITS[0]}–{BOUNCE_LIMITS[1]} "
                        f"(je {max_bounces!r}).")

    limit = None if max_length is None else _number(max_length, "Maximální délka dráhy")
    if limit is not None and not limit > 0:
        raise BeamError("Maximální délka dráhy musí být kladná.")

    rad = math.radians(beta_val)
    sin_b, cos_b = math.sin(rad), math.cos(rad)
    x_dir, y_dir, z_dir = placement.x_dir, placement.y_dir, placement.z_dir
    direction: Point = tuple(
        sin_b * x - cos_b * z for x, z in zip(x_dir, z_dir, strict=True)
    )  # type: ignore[assignment]

    legs: list[BeamLeg] = []
    path_reasons: list[str] = []
    current_start = placement.origin
    cumulative = 0.0

    for leg_index in range(1, max_bounces + 2):
        remaining = None if limit is None else max(0.0, limit - cumulative)
        if remaining is not None and remaining <= LENGTH_TOL:
            break
        ray = geo.cast(current_start, direction, remaining)
        first = next((s for s in ray.segments if s.start <= EDGE_TOL), None)
        if first is None:
            if leg_index == 1:
                for r in ray.reasons:
                    if r in (ALONG_SURFACE, UNDECIDED):
                        path_reasons.append(r)
                if not path_reasons:
                    path_reasons.append(NO_ENTRY)
            else:
                path_reasons.append(STOPPED_UNCERTAIN)
            break

        end_dist = first.end
        hit = first.exit
        end_point = hit.point if hit is not None else ray.point_at(end_dist)
        leg_length = end_dist
        cumulative += leg_length
        dx = end_point[0] - placement.origin[0]
        dy = end_point[1] - placement.origin[1]
        dz = end_point[2] - placement.origin[2]
        along = dx * x_dir[0] + dy * x_dir[1] + dz * x_dir[2]
        across = dx * y_dir[0] + dy * y_dir[1] + dz * y_dir[2]
        horizontal = math.hypot(along, across)
        raw_depth = -(dx * z_dir[0] + dy * z_dir[1] + dz * z_dir[2])
        depth = 0.0 if abs(raw_depth) < 1e-9 else raw_depth
        incidence = hit.incidence if hit is not None else None

        leg_reasons = list(first.reasons)
        legs.append(BeamLeg(
            index=leg_index,
            start=current_start,
            end=end_point,
            direction=ray.direction,
            length=leg_length,
            cumulative_length=cumulative,
            horizontal=horizontal,
            along=along,
            depth=depth,
            incidence=incidence,
            hit=hit,
            reasons=tuple(leg_reasons),
        ))
        for r in leg_reasons:
            path_reasons.append(r)

        if hit is None:
            break  # dráha skončila v materiálu dosažením max_length
        if not first.certain or not hit.certain:
            if leg_index <= max_bounces:
                path_reasons.append(STOPPED_UNCERTAIN)
            break  # na hraně či při tečném dotyku nemá odraz jednoznačný směr
        if leg_index > max_bounces:
            break

        direction = _reflect(ray.direction, hit.normal)
        current_start = hit.point

    return BeamPath(
        placement=placement,
        beta=beta_val,
        bounces=max_bounces,
        max_length=limit,
        refraction=refraction,
        legs=tuple(legs),
        reasons=tuple(dict.fromkeys(path_reasons)),
    )


# --- pomocné výpočty -----------------------------------------------------------------------


def _reflect(direction: Point, normal: Point) -> Point:
    """Zrcadlový odraz jednotkového směru ``direction`` od plochy s normálou ``normal``."""
    dot = sum(d * n for d, n in zip(direction, normal, strict=True))
    rx, ry, rz = (d - 2.0 * dot * n for d, n in zip(direction, normal, strict=True))
    norm = math.sqrt(rx * rx + ry * ry + rz * rz)
    return (rx / norm, ry / norm, rz / norm)


def _number(value: Any, what: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        raise BeamError(f"{what} musí být konečné číslo (je {value!r}).")
    return float(value)


def _coords(values: Point) -> str:
    return "; ".join(f"{round(v, 4) + 0.0:g}" for v in values)


def _bounce_word(n: int) -> str:
    return "odraz" if n == 1 else "odrazy" if 2 <= n <= 4 else "odrazů"
