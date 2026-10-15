"""Díry podle strojnických tabulek: závitové, průchozí, zahloubení, díry pro 3D tisk.

Závit je jen **vyznačený** (jako v běžných CAD): díra má průměr vrtáku pod závit
a prvek nese údaj „M6, hloubka závitu 9“. Skutečná šroubovice se nemodeluje.

Zdroje tabulek (ověřeno 15. 10. 2026 porovnáním více zdrojů; normy samotné jsou placené):

* stoupání hrubého závitu – ISO 261; vrták pod závit – ISO 2306 (běžné tabulky:
  Optimas, Fractory, AmesWeb; hodnota ≈ d − P),
* průchozí díry jemná/střední/hrubá řada – ISO 273 (reprodukce YJT Fastener Database,
  Optimas; u M16 uvádí Optimas střední 18 – držíme ISO 273: 17,5),
* válcové zahloubení pro šrouby s válcovou hlavou ISO 4762 – DIN 974-1 (tabulka
  neue-physik.de; hlavy ISO 4762 ověřeny u Würth),
* kuželové zahloubení 90° pro zápustné šrouby ISO 10642 – DIN 74 tvar F (tabulka Würth),
* zálisné (zatavovací) matice pro 3D tisk – doporučení výrobců (ruthex, Accu,
  Albany County Fasteners; zdroje se liší o desetiny mm → vždy vyzkoušej tiskem),
* šroub přímo do plastu – norma neexistuje; výchozí je vrták pod závit (vyzkoušej tiskem).

Všechny rozměry v mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Stoupání hrubého metrického závitu (ISO 261) a vrták pod závit (ISO 2306).
PITCH = {"M2": 0.4, "M2.5": 0.45, "M3": 0.5, "M4": 0.7, "M5": 0.8, "M6": 1.0, "M8": 1.25,
         "M10": 1.5, "M12": 1.75, "M16": 2.0, "M20": 2.5, "M24": 3.0, "M30": 3.5}
TAP_DRILL = {"M2": 1.6, "M2.5": 2.05, "M3": 2.5, "M4": 3.3, "M5": 4.2, "M6": 5.0, "M8": 6.8,
             "M10": 8.5, "M12": 10.2, "M16": 14.0, "M20": 17.5, "M24": 21.0, "M30": 26.5}

# Průchozí díry ISO 273: (jemná, střední, hrubá).
CLEARANCE = {
    "M2": (2.2, 2.4, 2.6), "M2.5": (2.7, 2.9, 3.1), "M3": (3.2, 3.4, 3.6),
    "M4": (4.3, 4.5, 4.8), "M5": (5.3, 5.5, 5.8), "M6": (6.4, 6.6, 7.0),
    "M8": (8.4, 9.0, 10.0), "M10": (10.5, 11.0, 12.0), "M12": (13.0, 13.5, 14.5),
    "M16": (17.0, 17.5, 18.5), "M20": (21.0, 22.0, 24.0), "M24": (25.0, 26.0, 28.0),
    "M30": (31.0, 33.0, 35.0),
}
FITS = ("fine", "medium", "coarse")

# Válcové zahloubení DIN 974-1 pro ISO 4762: (průměr, hloubka).
COUNTERBORE = {
    "M3": (6.5, 3.4), "M4": (8.0, 4.4), "M5": (10.0, 5.4), "M6": (11.0, 6.4),
    "M8": (15.0, 8.6), "M10": (18.0, 10.6), "M12": (20.0, 12.6), "M16": (26.0, 16.6),
    "M20": (33.0, 20.6), "M24": (40.0, 24.8),
}

# Kuželové zahloubení 90° pro ISO 10642 (DIN 74 tvar F): průměr na povrchu.
COUNTERSINK = {"M3": 7.0, "M4": 9.2, "M5": 11.5, "M6": 13.7, "M8": 18.3, "M10": 22.7,
               "M12": 27.2}

# Díra pro zálisnou matici do 3D tisku (průměr).
INSERT = {"M2": 3.2, "M2.5": 3.7, "M3": 4.0, "M4": 5.6, "M5": 6.4, "M6": 8.0}

SIZES = tuple(PITCH)  # pořadí pro výběr v okně

KINDS = {
    "tapped": "závitová (vrták pod závit)",
    "clearance": "průchozí pro šroub",
    "counterbore": "válcové zahloubení pro imbus (ISO 4762)",
    "countersink": "kuželové zahloubení 90° (zápustná hlava ISO 10642)",
    "insert": "3D tisk – zálisná matice",
    "plastic": "3D tisk – šroub přímo do plastu",
}
DRILL_POINT_ANGLE = 118.0  # špička vrtáku u slepé vrtané díry


class HoleError(ValueError):
    """Díru nejde vytvořit (zpráva česky)."""


@dataclass(frozen=True)
class HoleShape:
    """Tvar díry v řezu (osa díry = osa Z, povrch v z = 0, díra jde do −Z)."""

    diameter: float  # hlavní průměr díry
    depth: float | None  # hloubka válcové části (None = skrz celý díl)
    point: bool  # slepá vrtaná díra končí kuželem vrtáku 118°
    counterbore: tuple[float, float] | None = None  # (průměr, hloubka)
    countersink: float | None = None  # průměr kuželového zahloubení 90° na povrchu
    thread: str | None = None  # vyznačený závit, např. „M6“
    thread_depth: float | None = None


def nominal(size: str) -> float:
    """„M6“ → 6.0."""
    return float(size[1:])


def _check_size(size: str, table: dict, what: str) -> None:
    if size not in table:
        available = ", ".join(table)
        raise HoleError(f"{what} pro {size} v tabulce není – k dispozici: {available}.")


def hole_shape(kind: str, size: str, fit: str = "medium", depth: float | None = None,
               through_all: bool = False, thread_depth: float | None = None,
               diameter: float | None = None) -> HoleShape:
    """Rozměry díry podle tabulek. ``diameter`` přepíše hlavní průměr z tabulky."""
    if kind not in KINDS:
        raise HoleError(f"Neznámý druh díry „{kind}“, povolené: {', '.join(KINDS)}.")
    if size not in PITCH:
        raise HoleError(f"Neznámá velikost „{size}“, povolené: {', '.join(SIZES)}.")
    if fit not in FITS:
        raise HoleError("Řada průchozí díry musí být fine (jemná), medium (střední) "
                        "nebo coarse (hrubá).")
    d = nominal(size)
    clearance = CLEARANCE[size][FITS.index(fit)]
    if depth is not None and depth <= 0:
        raise HoleError(f"Hloubka díry musí být kladná (je {depth:g} mm).")
    blind_depth = None if through_all else (depth if depth is not None else 2 * d)

    if kind == "tapped":
        main = diameter or TAP_DRILL[size]
        default_thread = 1.5 * d if blind_depth is None else min(1.5 * d, blind_depth)
        thread = thread_depth if thread_depth is not None else default_thread
        if blind_depth is not None and thread > blind_depth:
            raise HoleError(f"Závit hloubky {thread:g} mm se nevejde do díry hloubky "
                            f"{blind_depth:g} mm – prohlub díru nebo zkrať závit.")
        return HoleShape(main, blind_depth, blind_depth is not None, thread=size,
                         thread_depth=thread)
    if kind == "clearance":
        return HoleShape(diameter or clearance, blind_depth, blind_depth is not None)
    if kind == "counterbore":
        _check_size(size, COUNTERBORE, "Válcové zahloubení")
        bore = COUNTERBORE[size]
        if blind_depth is not None and blind_depth <= bore[1]:
            raise HoleError(f"Díra hloubky {blind_depth:g} mm je mělčí než zahloubení "
                            f"{bore[1]:g} mm – nastav větší hloubku nebo skrz celý díl.")
        return HoleShape(diameter or clearance, blind_depth, blind_depth is not None,
                         counterbore=bore)
    if kind == "countersink":
        _check_size(size, COUNTERSINK, "Kuželové zahloubení")
        sink = COUNTERSINK[size]
        main = diameter or clearance
        if blind_depth is not None and blind_depth <= (sink - main) / 2:
            raise HoleError(f"Díra hloubky {blind_depth:g} mm je mělčí než kuželové "
                            "zahloubení – nastav větší hloubku nebo skrz celý díl.")
        return HoleShape(main, blind_depth, blind_depth is not None, countersink=sink)
    if kind == "insert":
        _check_size(size, INSERT, "Díra pro zálisnou matici")
        # Ploché dno (tisk), výchozí hloubka 2·d + 1, aby se vešla běžná matice.
        insert_depth = None if through_all else (depth if depth is not None else 2 * d + 1)
        return HoleShape(diameter or INSERT[size], insert_depth, False)
    # „plastic“: šroub přímo do plastu – vrták pod závit, ploché dno (tisk).
    return HoleShape(diameter or TAP_DRILL[size], blind_depth, False)


def point_height(diameter: float) -> float:
    """Výška kuželové špičky vrtáku 118°."""
    return (diameter / 2) / math.tan(math.radians(DRILL_POINT_ANGLE / 2))


def removed_volume(shape: HoleShape, through_length: float | None = None) -> float:
    """Objem jedné díry (pro testy a kontrolu); u díry skrz se zadá délka ``through_length``."""
    length = shape.depth if shape.depth is not None else through_length
    r = shape.diameter / 2
    volume = math.pi * r * r * length
    if shape.point:
        volume += math.pi * r * r * point_height(shape.diameter) / 3
    if shape.counterbore:
        big, deep = shape.counterbore
        volume += math.pi * ((big / 2) ** 2 - r * r) * deep
    if shape.countersink:
        big = shape.countersink / 2
        h = big - r  # 90° → výška = rozdíl poloměrů
        volume += math.pi * h / 3 * (big * big + big * r + r * r) - math.pi * r * r * h
    return volume


def summary(kind: str, size: str, count: int, shape: HoleShape | None = None) -> str:
    """Krátký český popis pro strom prvků: „M6 závit hl. 9, 4×“."""
    text = {"tapped": f"{size} závit", "clearance": f"průchozí pro {size}",
            "counterbore": f"{size} imbus zahloubení", "countersink": f"{size} zápustné",
            "insert": f"{size} zálisná matice", "plastic": f"{size} do plastu"}.get(kind, size)
    if shape is not None and shape.thread_depth is not None:
        text += f" hl. {shape.thread_depth:g}"
    return f"{text}, {count}×" if count > 1 else text
