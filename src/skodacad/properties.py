"""Fyzikální vlastnosti dílu: objem, povrch, hmotnost, těžiště, rozměry."""

from __future__ import annotations

from dataclasses import dataclass

from build123d import CenterOf, Part

from skodacad.materials import density_g_cm3


@dataclass(frozen=True)
class PartProperties:
    volume_mm3: float
    area_mm2: float
    size_mm: tuple[float, float, float]
    center_of_mass_mm: tuple[float, float, float]
    material: str
    density_g_cm3: float | None
    solids: int

    @property
    def mass_kg(self) -> float | None:
        if self.density_g_cm3 is None:
            return None
        return self.volume_mm3 / 1000 * self.density_g_cm3 / 1000


def compute(part: Part, material: str) -> PartProperties:
    size = part.bounding_box().size
    center = part.center(CenterOf.MASS)
    return PartProperties(
        volume_mm3=part.volume,
        area_mm2=part.area,
        size_mm=(size.X, size.Y, size.Z),
        center_of_mass_mm=(center.X, center.Y, center.Z),
        material=material,
        density_g_cm3=density_g_cm3(material),
        solids=len(part.solids()),
    )
