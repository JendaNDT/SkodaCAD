"""Export dílu do souborů a náhledový obrázek.

* STEP – přesná CAD geometrie pro jiné CAD programy (Inventor, Solid Edge …)
* STL / 3MF – trojúhelníková síť pro 3D tisk (3MF je modernější, s jednotkami)
* GLB – síť pro prohlížeče a Blender
* SVG – izometrický náhled s viditelnými a skrytými hranami
"""

from __future__ import annotations

import re
from pathlib import Path

from build123d import (
    Compound,
    ExportSVG,
    LineType,
    Mesher,
    Part,
    Vector,
    export_gltf,
    export_step,
    export_stl,
)

FORMATS = ("step", "stl", "3mf", "glb", "svg")

# Pohled zepředu-zprava-shora, jak bývá zvykem u izometrie.
_VIEW_FROM = (1.0, -1.0, 0.8)


def export(part: Part, path: str | Path) -> Path:
    """Uloží díl do souboru; formát se pozná podle přípony."""
    path = Path(path)
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "step":
        ok = export_step(part, str(path))
    elif suffix == "stl":
        ok = export_stl(part, str(path), tolerance=0.01, angular_tolerance=0.1)
    elif suffix == "3mf":
        mesher = Mesher()
        mesher.add_shape(part, linear_deflection=0.01, angular_deflection=0.1)
        mesher.write(str(path))
        ok = path.exists()
    elif suffix == "glb":
        ok = export_gltf(part, str(path), binary=True)
    elif suffix == "svg":
        write_preview_svg(part, path)
        ok = path.exists()
    else:
        raise ValueError(f"Neznámý formát „{suffix}“, umím: {', '.join(FORMATS)}.")
    if not ok:
        raise RuntimeError(f"Export do {path} se nepodařil.")
    return path


def write_preview_svg(part: Part, path: str | Path, width_mm: float = 160) -> None:
    """Izometrický náhled: viditelné hrany plně, skryté čárkovaně, bílé pozadí."""
    bbox = part.bounding_box()
    center = bbox.center()
    origin = center + Vector(*_VIEW_FROM).normalized() * bbox.diagonal * 3
    visible, hidden = part.project_to_viewport(origin, viewport_up=(0, 0, 1), look_at=center)
    largest = max(*Compound(children=visible + hidden).bounding_box().size)
    svg = ExportSVG(scale=width_mm / largest, margin=5, line_weight=0.35)
    svg.add_layer("Viditelné", line_weight=0.35)
    svg.add_layer("Skryté", line_color=(140, 140, 140), line_type=LineType.DASHED,
                  line_weight=0.18)
    svg.add_shape(visible, layer="Viditelné")
    svg.add_shape(hidden, layer="Skryté")
    svg.write(str(path))
    _add_white_background(Path(path))


def _add_white_background(path: Path) -> None:
    """Bez pozadí by byl náhled v tmavém režimu nečitelný (černé čáry na černé)."""
    text = path.read_text(encoding="utf-8")
    match = re.search(r'viewBox="([-\d.e]+) ([-\d.e]+) ([-\d.e]+) ([-\d.e]+)"', text)
    if not match:
        return
    x, y, w, h = match.groups()
    rect = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="white" />'
    text = re.sub(r"(<svg[^>]*>)", r"\1" + rect, text, count=1)
    path.write_text(text, encoding="utf-8")
