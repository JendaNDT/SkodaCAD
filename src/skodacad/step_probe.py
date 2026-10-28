"""Předběžná kontrola STEP pro P3.3; volat jen v izolovaném pomocném procesu.

Není to zatím uživatelský import ani záruka, že jádro vždy hlásí všechny změny.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

MAX_STEP_BYTES = 16 * 1024 * 1024


class StepProbeError(ValueError):
    """STEP nebyl jednoznačně rozpoznán jako bezpečný referenční díl."""


@dataclass(frozen=True)
class StepFacts:
    sha256: str
    size_bytes: int
    unit: str
    solids: int
    bounds_mm: tuple[float, ...]
    volume_mm3: float


def probe_step(data: bytes) -> StepFacts:
    """Přísná diagnostika jediného tělesa, určena pro pomocný proces."""
    return _inspect_step(data)[0]


def _inspect_step(data: bytes):
    """Kontrolované skutečnosti a tvar; nepředávat přímo mimo proces."""
    from skodacad.worker import _STEP_PHASE

    if _STEP_PHASE is not None:
        _STEP_PHASE.set()
    try:
        return _inspect_step_inner(data)
    finally:
        if _STEP_PHASE is not None:
            _STEP_PHASE.clear()


def _inspect_step_inner(data: bytes):
    if not isinstance(data, bytes) or not data:
        raise StepProbeError("STEP je prázdný nebo nejde přečíst.")
    if len(data) > MAX_STEP_BYTES:
        raise StepProbeError("STEP je větší než povolených 16 MiB.")

    from build123d import Shape
    from OCP.collections import Sequence_TCollection_AsciiString
    from OCP.IFSelect import IFSelect_ItemsByEntity, IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_Reader
    from OCP.StepRepr import StepRepr_NextAssemblyUsageOccurrence

    from skodacad.geometry_validation import GeometryValidationError, inspect_volume

    reader = STEPControl_Reader()
    previous = Interface_Static.CVal_s("FromSTEP.exec.op")
    if not Interface_Static.SetCVal_s("FromSTEP.exec.op", ""):
        raise StepProbeError("Nelze nastavit kontrolu STEP. Soubor nebyl přijat.")
    try:
        if reader.ReadStream("zdroj.step", io.BytesIO(data)) != IFSelect_RetDone:
            raise StepProbeError(
                "STEP se nepodařilo načíst; soubor je poškozený nebo nepodporovaný."
            )
        output = io.BytesIO()
        reader.PrintCheckLoad(output, False, IFSelect_ItemsByEntity)
        if output.getvalue().strip():
            raise StepProbeError("STEP obsahuje upozornění při čtení; soubor nebyl přijat.")

        model = reader.StepModel()
        if any(isinstance(model.Value(i), StepRepr_NextAssemblyUsageOccurrence)
               for i in range(1, model.NbEntities() + 1)):
            raise StepProbeError("STEP obsahuje sestavu; zatím lze zpracovat jen jeden díl.")
        if reader.NbRootsForTransfer() != 1:
            raise StepProbeError("STEP neobsahuje právě jeden hlavní díl; soubor nebyl přijat.")
        length, angle, solid_angle = (Sequence_TCollection_AsciiString() for _ in range(3))
        reader.FileUnits(length, angle, solid_angle)
        units = {length.Value(i).ToCString().strip().lower() for i in range(1, length.Length() + 1)}
        if len(units) != 1 or not units.issubset({"millimetre", "metre", "inch"}):
            raise StepProbeError("Jednotky STEP chybí, jsou nejednoznačné nebo nejsou podporované.")
        reader.SetSystemLengthUnit(1.0)
        if reader.TransferRoots() != 1 or reader.NbShapes() != 1:
            raise StepProbeError("STEP se nepodařilo převést úplně; soubor nebyl přijat.")
        output = io.BytesIO()
        reader.PrintCheckTransfer(output, False, IFSelect_ItemsByEntity)
        if output.getvalue().strip():
            raise StepProbeError(
                "Při převodu STEP vzniklo upozornění nebo oprava; soubor nebyl přijat."
            )
        try:
            shape = Shape.cast(reader.OneShape())
            facts = inspect_volume(shape)
        except (GeometryValidationError, ValueError, TypeError) as exc:
            raise StepProbeError(f"STEP netvoří platné uzavřené těleso: {exc}") from exc
        if facts.solids != 1:
            raise StepProbeError("STEP neobsahuje právě jedno těleso; soubor nebyl přijat.")
        box = shape.bounding_box()
        return (StepFacts(hashlib.sha256(data).hexdigest(), len(data), units.pop(), facts.solids,
                          (*box.min, *box.max), facts.volume), shape)
    finally:
        Interface_Static.SetCVal_s("FromSTEP.exec.op", previous)
