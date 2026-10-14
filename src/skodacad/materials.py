"""Tabulka materiálů pro výpočet hmotnosti (hustoty v g/cm³)."""

from __future__ import annotations

import unicodedata

DENSITIES_G_CM3 = {
    "ocel": 7.85,
    "nerez": 7.90,
    "litina": 7.20,
    "hlinik": 2.70,
    "mosaz": 8.50,
    "med": 8.96,
    "titan": 4.51,
    "pla": 1.24,
    "petg": 1.27,
    "abs": 1.04,
}


def _key(name: str) -> str:
    without_accents = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return without_accents.strip().lower()


def density_g_cm3(material: str) -> float | None:
    """Hustota materiálu; diakritika a velikost písmen nevadí („Hliník“ = „hlinik“)."""
    return DENSITIES_G_CM3.get(_key(material))
