"""Rozříznutí dílu rovinou (P6.17, návrh ``docs/p6-17-rozriznuti.md``).

Z jednoho návrhu krabičky vzniknou základna a víčko: rovina rozdělí díl a ponechá se strana nad
rovinou (po normále), pod ní, nebo obě části, které se odsunou o zadanou mezeru. Řez je přesný
(jádro ``split`` z build123d), objem se vždy ověří – součet částí musí dát původní objem.

Rovina, která díl neprotíná (celý díl by zůstal, nebo by nezbylo nic), se **odmítne** s českou
radou; nic se potichu neodřízne ani nezahodí.
"""

from __future__ import annotations

import math
from typing import Any

from build123d import Compound, Keep, Location, Part, Plane, split

KEEP = ("above", "below", "both")
FEATURE_KEYS = {"id", "type", "name", "plane", "offset", "keep", "gap"}
SIDE_NAMES = {"above": "nad rovinou", "below": "pod rovinou"}
MAX_GAP = 10000.0  # mm


class SplitError(ValueError):
    """Český důvod odmítnutí rozříznutí."""


def validate(feature: dict[str, Any]) -> None:
    """Kontrola struktury zapsaného prvku (bez vyhodnocení výrazů a bez dílu)."""
    unknown = set(feature) - FEATURE_KEYS
    if unknown:
        raise SplitError("Rozříznutí: neznámý klíč " + ", ".join(sorted(map(str, unknown))) + ".")
    keep = feature.get("keep", "below")
    if keep not in KEEP:
        raise SplitError("Ponechaná část („keep“) musí být „above“ (nad rovinou), „below“ "
                         "(pod rovinou) nebo „both“ (obě).")
    gap = feature.get("gap")
    if gap not in (None, ""):
        if keep != "both":
            raise SplitError("Mezeru („gap“) jde zadat jen při ponechání obou částí („both“).")
        if isinstance(gap, bool) or not isinstance(gap, (int, float, str)):
            raise SplitError("„gap“ musí být číslo nebo výraz.")


def _volume(part: Part | None) -> float:
    return 0.0 if part is None else float(sum(solid.volume for solid in part.solids()))


def _tolerance(volume: float) -> float:
    return 1e-9 * max(1.0, abs(volume))


def _side(part: Part, plane: Plane, keep: Keep) -> Part | None:
    """Jedna strana od roviny; ``None``, když na ní nic nezůstane."""
    try:
        result = split(part, bisect_by=plane, keep=keep)
    except Exception as exc:  # noqa: BLE001 – chyby jádra převádíme na lidskou zprávu
        raise SplitError(f"Rozříznutí se nepodařilo ({exc}). Zkus jinou polohu roviny.") from None
    if result is None or not result.solids():
        return None
    return result


def apply(part: Part, plane: Plane, keep: str = "below", gap: float = 0.0) -> Part:
    """Díl rozříznutý rovinou ``plane``: ``above`` ponechá stranu po normále, ``below`` opačnou,
    ``both`` obě (horní se odsune po normále o ``gap``)."""
    if keep not in KEEP:
        raise SplitError("Ponechaná část musí být „above“, „below“ nebo „both“.")
    if not isinstance(gap, (int, float)) or not math.isfinite(gap) or gap < 0 or gap > MAX_GAP:
        raise SplitError(f"Mezera mezi částmi musí být od 0 do {MAX_GAP:g} mm (je {gap!r}).")
    if keep != "both" and gap:
        raise SplitError("Mezeru jde zadat jen při ponechání obou částí.")

    before = _volume(part)
    tolerance = _tolerance(before)
    upper = _side(part, plane, Keep.TOP)
    lower = _side(part, plane, Keep.BOTTOM)
    upper_volume, lower_volume = _volume(upper), _volume(lower)

    if upper_volume <= tolerance or lower_volume <= tolerance:
        empty = "nad rovinou" if upper_volume <= tolerance else "pod rovinou"
        raise SplitError(
            f"Rovina díl neprotíná – {empty} není žádný materiál. Posuň rovinu do dílu "
            "(změň „Posun roviny“ nebo rovinu).")
    if abs(upper_volume + lower_volume - before) > 1e-6 * max(1.0, before):
        raise SplitError("Součet částí po řezu nesedí s původním objemem – řez je nespolehlivý, "
                         "zkus rovinu posunout o setinu milimetru.")

    if keep == "above":
        return Part(Compound(list(upper.solids())).wrapped)
    if keep == "below":
        return Part(Compound(list(lower.solids())).wrapped)
    moved = upper.moved(Location(plane.z_dir * gap)) if gap else upper
    return Part(Compound([*lower.solids(), *moved.solids()]).wrapped)
