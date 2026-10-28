"""Kontrola uložených dat výkresu; neprovádí výpočet ani export."""
from __future__ import annotations

import re
from typing import Any

from skodacad.document import DocumentError

SCALES = (0.1, 0.2, 0.5, 1, 2, 5)


def check_drawing(drawing: Any) -> None:
    if not isinstance(drawing, dict):
        raise DocumentError("Výkres musí být objekt.")
    if drawing.get("paper", "A4") not in ("A4", "A3"):
        raise DocumentError("Výkres podporuje list A4 nebo A3.")
    scale = drawing.get("scale", 1)
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or scale not in SCALES:
        raise DocumentError("Výkres má nepodporované měřítko.")
    dimensions = drawing.get("dimensions", [])
    if not isinstance(dimensions, list):
        raise DocumentError("Kóty výkresu musí být seznam.")
    seen: set[str] = set()
    for item in dimensions:
        if not isinstance(item, dict):
            raise DocumentError("Kóta musí být objekt.")
        did = item.get("id")
        if not isinstance(did, str) or not did.strip() or did in seen:
            raise DocumentError("Kóta musí mít jedinečné neprázdné textové id.")
        seen.add(did)
        kind = item.get("kind")
        if kind == "overall":
            if item.get("axis") not in ("x", "y", "z"):
                raise DocumentError(f"Kóta „{did}“ má neplatnou osu.")
        elif kind in ("diameter", "radius"):
            origin, recipe = item.get("origin"), item.get("recipe")
            if not isinstance(origin, str) or not origin:
                raise DocumentError(f"Kóta „{did}“ nemá původ plochy.")
            if not isinstance(recipe, str) or not re.fullmatch(r"[0-9a-f]{64}", recipe):
                raise DocumentError(f"Kóta „{did}“ nemá platnou pojistku historie.")
        else:
            raise DocumentError(f"Kóta „{did}“ má nepodporovaný druh.")
