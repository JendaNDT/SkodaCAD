"""Poloha ortogonálních pohledů na výkresovém listu v milimetrech.

Jde o výpočet rozvržení, nikoli úplný výkres, PDF či DXF. Výsledné souřadnice
mají počátek v levém dolním rohu listu; měřítko se nemění podle místa na listu.
"""
from __future__ import annotations

from dataclasses import dataclass

from build123d import Compound

from skodacad.document import Document, DocumentError
from skodacad.drawing_data import SCALES
from skodacad.drawing_geometry import DrawingView, project_view
from skodacad.rebuild import BuildResult, model_signature, require_complete_part

PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0)}
MARGIN = 10.0
TITLE_HEIGHT = 35.0
PADDING = 10.0  # volné místo od rámečku a budoucího popisového pole
GAP = 20.0


@dataclass(frozen=True)
class PlacedView:
    name: str
    geometry: DrawingView
    offset: tuple[float, float]
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class Sheet:
    paper: str
    width: float
    height: float
    scale: float
    views: tuple[PlacedView, ...]
    model_signature: str


def _bounds(view: DrawingView) -> tuple[float, float, float, float]:
    edges = (*view.visible, *view.hidden)
    if not edges:
        raise DocumentError("Pohled neobsahuje žádné hrany.")
    box = Compound(children=list(edges)).bounding_box()
    return box.min.X, box.min.Y, box.max.X, box.max.Y


def layout(document: Document, result: BuildResult, *, paper: str = "A4", scale: float = 1,
           views: tuple[str, ...] = ("front", "top", "right")) -> Sheet:
    """Rozmístí pohled shora pod čelní a pravý vlevo; při nevejití odmítne.

    Pohledy se nepřizpůsobují stránce a mají vůči sobě správné zarovnání os.
    Zatím se rezervuje spodní pruh pro budoucí popisové pole.
    """
    if not isinstance(paper, str) or paper not in PAPER:
        raise DocumentError("Zvol list A4 nebo A3.")
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or scale not in SCALES:
        raise DocumentError("Zvol podporované měřítko výkresu.")
    if (not isinstance(views, (tuple, list)) or not views
            or any(not isinstance(view, str) or view not in ("front", "top", "right")
                   for view in views) or len(set(views)) != len(views)):
        raise DocumentError("Vyber alespoň jeden známý pohled bez opakování.")
    part = require_complete_part(result)
    if result.model_signature != model_signature(document):
        raise DocumentError("Přepočet neodpovídá modelu – nejprve model přepočítej.")
    geometry = {name: project_view(part, name, scale) for name in views}
    boxes = {name: _bounds(view) for name, view in geometry.items()}
    # Ortogonální pohledy sdílejí souřadnice: X pro čelní/horní, Z pro čelní/pravý.
    left_width = boxes["right"][2] - boxes["right"][0] if "right" in boxes else 0.0
    top_height = boxes["top"][3] - boxes["top"][1] if "top" in boxes else 0.0
    right_gap = GAP if "right" in boxes and ("front" in boxes or "top" in boxes) else 0.0
    top_gap = GAP if "top" in boxes and ("front" in boxes or "right" in boxes) else 0.0
    x_main = MARGIN + PADDING + left_width + right_gap
    y_upper = MARGIN + TITLE_HEIGHT + PADDING + top_height + top_gap
    placements: dict[str, tuple[float, float]] = {}
    if "front" in boxes:
        b = boxes["front"]
        placements["front"] = (x_main - b[0], y_upper - b[1])
    if "top" in boxes:
        b = boxes["top"]
        # Sdílená osa X v projekcích; zarovnává skutečné souřadnice, ne středy obálek.
        x = placements["front"][0] if "front" in placements else x_main - b[0]
        placements["top"] = (x, MARGIN + TITLE_HEIGHT + PADDING - b[1])
    if "right" in boxes:
        b = boxes["right"]
        y = placements["front"][1] if "front" in placements else y_upper - b[1]
        placements["right"] = (MARGIN + PADDING - b[0], y)
    width, height = PAPER[paper]
    placed = []
    for name in views:
        b, offset = boxes[name], placements[name]
        translated = (b[0] + offset[0], b[1] + offset[1],
                      b[2] + offset[0], b[3] + offset[1])
        if (translated[0] < MARGIN + PADDING - 1e-6
                or translated[1] < MARGIN + TITLE_HEIGHT + PADDING - 1e-6
                or translated[2] > width - MARGIN - PADDING + 1e-6
                or translated[3] > height - MARGIN - PADDING + 1e-6):
            raise DocumentError("Pohledy se na list nevejdou – zvol větší list nebo menší měřítko.")
        placed.append(PlacedView(name, geometry[name], offset, translated))
    return Sheet(paper, width, height, float(scale), tuple(placed), result.model_signature)
