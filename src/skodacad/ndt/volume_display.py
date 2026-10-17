"""Přenosná kresba cíle a přesných průřezů. Volá se v pomocném procesu, bez Qt.

BinTools kusy se zachytí při vzorkování; jejich index je přímo index vzorku.
Číselná mapa ani dokument žádný tvar nenesou. Chyba kresby neznehodnotí mapu.
"""

from __future__ import annotations

import io
import itertools
import pickle
from dataclasses import dataclass, field, replace
from typing import Any

from skodacad.section import SectionPlane

MAX_TRIANGLES = 500_000
MAX_BYTES = 128 * 1024 * 1024
COLORS = {"covered": (0.15, 0.7, 0.25), "uncovered": (0.85, 0.2, 0.15),
          "uncertain": (0.9, 0.75, 0.15)}
BLUE = (0.2, 0.55, 0.95)


def encode(shape: Any) -> bytes:
    from OCP.BinTools import BinTools

    stream = io.BytesIO()
    BinTools.Write_s(shape.wrapped, stream)
    return stream.getvalue()


def decode(raw: bytes) -> Any:
    from build123d import Solid
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape

    shape = TopoDS_Shape()
    BinTools.Read_s(shape, io.BytesIO(raw))
    return Solid.cast(shape)


@dataclass(frozen=True)
class DisplayPiece:
    sample: int
    bounds: tuple[tuple[float, ...], tuple[float, ...]]  # světové souřadnice
    raw: bytes


@dataclass
class DisplaySource:
    pieces: list[DisplayPiece] = field(default_factory=list)
    error: str = ""
    size: int = 0
    samples: int = 0
    filtered: bool = False

    def capture(self, sample: int, solid: Any, plane: Any) -> None:
        self.samples = sample + 1
        if self.error:
            return
        try:
            world = plane.from_local_coords(solid)
            box = world.bounding_box()
            piece = DisplayPiece(sample, (tuple(box.min), tuple(box.max)), encode(world))
            self.size += len(pickle.dumps(piece, protocol=5))
            if self.size > MAX_BYTES:
                raise ValueError("Zdroj kresby překročil 128 MiB.")
            self.pieces.append(piece)
        except Exception as exc:  # noqa: BLE001 – výpočet vah pokračuje
            self.error = f"Barevný průřez není dostupný: {exc} Čísla a CSV zůstávají platné."
            self.pieces.clear()
            self.size = 0

    def finish(self) -> None:
        if not self.error:
            self.size = len(pickle.dumps(self, protocol=5)) + 1024
            if self.size > MAX_BYTES:
                self.error = "Zdroj kresby překročil 128 MiB. Čísla a CSV zůstávají platné."
                self.pieces.clear()
                self.size = 0

    def for_plane(self, plane: SectionPlane) -> DisplaySource:
        # Jen číselné meze: do procesu se neposílají tělesa daleko od řezu.
        pieces = []
        for piece in self.pieces:
            low, high = _range(piece.bounds, plane)
            if low < -1e-7 and high >= -1e-7:
                pieces.append(piece)
        return replace(self, pieces=pieces, filtered=True)


@dataclass
class DisplayMesh:
    nodes: list = field(default_factory=list)
    triangles: list = field(default_factory=list)
    colors: list = field(default_factory=list)
    samples: list[int] = field(default_factory=list)  # jeden index pro každý trojúhelník
    area_mm2: float = 0.0
    message: str = ""
    seconds: float = 0.0

    def append(self, shape: Any, color: tuple, sample: int, deflection: float) -> None:
        points, triangles = shape.tessellate(deflection, 0.1)
        offset = len(self.nodes)
        self.nodes.extend(tuple(p) for p in points)
        self.triangles.extend(tuple(offset + i for i in t) for t in triangles)
        self.colors.extend([color] * len(points))  # žádné sdílení uzlů různých stavů
        self.samples.extend([sample] * len(triangles))
        if len(self.triangles) > MAX_TRIANGLES:
            raise ValueError("Kresba překročila 500 000 trojúhelníků.")

    def mesh(self) -> tuple[list, list, list]:
        return self.nodes, self.triangles, self.colors


def _range(bounds: tuple, plane: SectionPlane) -> tuple[float, float]:
    sides = [plane.side(p) for p in itertools.product(*zip(*bounds, strict=True))]
    return min(sides), max(sides)


def _cap_faces(solid: Any, plane: SectionPlane) -> list:
    """Přesný poloprostor bez objemových prahů určených pro řez celého dílu.

    I velmi tenká ponechaná vrstva může mít velkou plochu řezu. Chybu booleovské
    operace nesmíme zaměnit za prázdnou buňku a potichu vynechat její barvu.
    """
    from build123d import Box, Pos, Vector

    box = solid.bounding_box()
    size = 2 * box.diagonal + 2 * (Vector(*plane.origin) - box.center()).length + 1
    cutter = plane.plane().location * Pos(0, 0, size / 2) * Box(size, size, size)
    kept = solid - cutter
    if kept is None:
        return []
    if not kept.is_valid:
        raise ValueError("Geometrie průřezu některého kusu není platná.")
    return list(kept.faces())


def cross_section(source: DisplaySource, states: list[str], plane: SectionPlane,
                  step: float) -> DisplayMesh:
    """Pouze skutečné plochy řezu; na společné hranici vlastní barvu ponechaná strana."""
    import time

    from build123d import GeomType, Vector

    started = time.monotonic()
    if source.error:
        return DisplayMesh(message=source.error)
    result = DisplayMesh()
    try:
        if (source.samples != len(states)
                or (not source.filtered and len(source.pieces) != len(states))):
            raise ValueError("Chybí některý kus zdroje kresby; přepočítej mapu.")
        normal = Vector(*plane.normal).normalized()
        for piece in source.pieces:
            low, high = _range(piece.bounds, plane)
            if low >= -1e-7 or high < -1e-7:
                continue
            solid = decode(piece.raw)
            faces = _cap_faces(solid, plane) if high > 1e-7 else solid.faces()
            for face in faces:
                if (face.geom_type != GeomType.PLANE
                        or face.normal_at().dot(normal) < 1 - 1e-7
                        or abs(plane.side(tuple(face.center()))) > 1e-6):
                    continue
                result.append(face, COLORS[states[piece.sample]], piece.sample, min(.1, step / 10))
                result.area_mm2 += face.area
        if source.size + len(pickle.dumps(result, protocol=5)) > MAX_BYTES:
            raise ValueError("Zdroj a kresba společně překročily 128 MiB.")
        if not result.triangles:
            result.message = "Řez cílový objem neprotíná."
    except Exception as exc:  # noqa: BLE001 – nikdy nevrátit neúplnou barevnou kresbu
        result = DisplayMesh(message=f"Barevný průřez není dostupný: {exc} "
                             "Čísla a CSV zůstávají platné.")
    result.seconds = time.monotonic() - started
    return result


def target_preview(part: Any, target: dict) -> tuple[dict, DisplayMesh, dict]:
    from skodacad.ndt.welds import normalize_target, resolve_target

    saved = normalize_target(target)
    resolved = resolve_target(part, saved)
    mesh = DisplayMesh()
    mesh.append(resolved.shape, BLUE, 0, .1)
    if len(pickle.dumps(mesh, protocol=5)) > MAX_BYTES:
        raise ValueError("Náhled překročil 128 MiB; zjednoduš průřez.")
    return saved, mesh, {"volume_mm3": resolved.volume_mm3,
                         "requested_volume_mm3": resolved.requested_volume_mm3,
                         "outside_volume_mm3": resolved.outside_volume_mm3}
