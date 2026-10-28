"""Kontrola uložených dat výkresu; neprovádí výpočet ani export."""
from __future__ import annotations

import math
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
    section = drawing.get("section")
    if section is not None:
        if not isinstance(section, dict) or section.get("axis") not in ("X", "Y", "Z"):
            raise DocumentError("Řez výkresu musí mít osu X, Y nebo Z.")
        position = section.get("position")
        if (isinstance(position, bool) or not isinstance(position, (int, float))
                or not math.isfinite(position)):
            raise DocumentError("Poloha řezu musí být konečné číslo v mm.")
        if not isinstance(section.get("flipped", False), bool):
            raise DocumentError("Otočení řezu musí být ano nebo ne.")
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
        placement = item.get("placement")
        if placement is not None:
            if not isinstance(placement, dict):
                raise DocumentError(f"Umístění kóty „{did}“ musí být objekt.")
            if placement.get("view") not in ("front", "top", "right"):
                raise DocumentError(f"Kóta „{did}“ má neplatný pohled.")
            if placement.get("side") not in ("low", "high"):
                raise DocumentError(f"Kóta „{did}“ má neplatnou stranu.")
            offset = placement.get("offset")
            if (isinstance(offset, bool) or not isinstance(offset, (int, float))
                    or not math.isfinite(offset) or not 1 <= offset <= 60):
                raise DocumentError(f"Odstup kóty „{did}“ musí být 1 až 60 mm.")
        kind = item.get("kind")
        if kind == "overall":
            if item.get("axis") not in ("x", "y", "z"):
                raise DocumentError(f"Kóta „{did}“ má neplatnou osu.")
        elif kind == "distance":
            for key in ("a", "b"):
                ref = item.get(key)
                if (not isinstance(ref, dict) or not isinstance(ref.get("origin"), str)
                        or not ref["origin"] or ref.get("normal") not in
                        ("+x", "-x", "+y", "-y", "+z", "-z")):
                    raise DocumentError(f"Kóta „{did}“ nemá platný odkaz na plochu.")
            if item["a"]["normal"][1] != item["b"]["normal"][1]:
                raise DocumentError(f"Kóta „{did}“ nemá rovnoběžné plochy.")
            recipe = item.get("recipe")
            if not isinstance(recipe, str) or not re.fullmatch(r"[0-9a-f]{64}", recipe):
                raise DocumentError(f"Kóta „{did}“ nemá platnou pojistku historie.")
        elif kind in ("diameter", "radius"):
            origin, recipe = item.get("origin"), item.get("recipe")
            if not isinstance(origin, str) or not origin:
                raise DocumentError(f"Kóta „{did}“ nemá původ plochy.")
            if not isinstance(recipe, str) or not re.fullmatch(r"[0-9a-f]{64}", recipe):
                raise DocumentError(f"Kóta „{did}“ nemá platnou pojistku historie.")
        else:
            raise DocumentError(f"Kóta „{did}“ má nepodporovaný druh.")
