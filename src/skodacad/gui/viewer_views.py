"""Názvy a klávesové zkratky standardních pohledů (bez závislosti na OCCT).

Zkratky odpovídají numerické klávesnici jako v Blenderu: 1 zepředu, 3 zprava,
7 shora, 0 izometrie; s Ctrl opačná strana.
"""

VIEW_LABELS: dict[str, tuple[str, str | None]] = {
    "iso": ("Izometrie", "0"),
    "front": ("Zepředu", "1"),
    "right": ("Zprava", "3"),
    "top": ("Shora", "7"),
    "back": ("Zezadu", "Ctrl+1"),
    "bottom": ("Zespodu", "Ctrl+7"),
    "iso_back": ("Izometrie zezadu", "Ctrl+0"),
}
