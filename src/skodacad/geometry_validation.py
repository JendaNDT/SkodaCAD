"""Společná smlouva objemové geometrie P1.1 (mm, mm³).

Pouze inspekce a rozhodnutí: tvar se neopravuje, nezjednodušuje ani nemění.
Číselné výsledky jsou místní; nepatří do receptu ani přenosového protokolu.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Part
from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_SOLID
from OCP.TopoDS import TopoDS_Iterator


class GeometryValidationError(ValueError):
    """Tvar nebo účinek nesplňuje schválenou smlouvu; text je pro uživatele."""


@dataclass(frozen=True)
class VolumeFacts:
    volume: float
    component_volumes: tuple[float, ...]
    bounds: tuple[float, ...]

    @property
    def solids(self) -> int:
        return len(self.component_volumes)


def volume_tolerance(before: float, after: float) -> float:
    """Rozlišitelnost objemu; objem řezacího nástroje sem nepatří."""
    return 1e-9 * max(1.0, abs(before), abs(after))


def body_count_message(before: int, after: int) -> str:
    """Společná informace k úspěchu celého 3D prvku; nejde o chybový stav."""
    return f"Počet těles: {before} → {after}."


def _only_volume_components(shape: Part) -> None:
    pending = [shape.wrapped]
    while pending:
        current = pending.pop()
        if current.IsNull():
            raise GeometryValidationError("tvar obsahuje prázdnou složku.")
        kind = current.ShapeType()
        if kind == TopAbs_SOLID:
            continue  # shelly/plochy uvnitř solidu patří k jeho hranici, i u dutiny
        if kind not in (TopAbs_COMPOUND, TopAbs_COMPSOLID):
            raise GeometryValidationError(
                "tvar obsahuje volnou neobjemovou složku – použij uzavřené objemové těleso."
            )
        iterator = TopoDS_Iterator(current)
        if not iterator.More():
            raise GeometryValidationError("tvar obsahuje prázdnou složku.")
        while iterator.More():
            pending.append(iterator.Value())
            iterator.Next()


def inspect_volume(shape: Part | None) -> VolumeFacts:
    """Ověří celý tvar i všechny solidy; nevybírá jen největší/použitelné části."""
    try:
        solids = list(shape.solids()) if shape is not None else []
        if not solids:
            raise GeometryValidationError(
                "těleso nemá žádný objem – zkontroluj uzavření a rozměry profilu."
            )
        _only_volume_components(shape)
        if not shape.is_valid:
            raise GeometryValidationError(
                "tvar není platné objemové těleso – uprav poslední prvek nebo použij Zpět."
            )
        volumes = []
        for solid in solids:
            shells = list(solid.shells())
            if not shells or not all(BRep_Tool.IsClosed_s(s.wrapped) for s in shells):
                raise GeometryValidationError(
                    "tvar obsahuje neuzavřenou objemovou složku – uprav profil nebo poslední prvek."
                )
            if not solid.is_valid:
                raise GeometryValidationError(
                    "tvar obsahuje neplatnou objemovou složku – uprav poslední prvek."
                )
            value = solid.volume
            if not math.isfinite(value) or value <= volume_tolerance(0, value):
                raise GeometryValidationError(
                    "objemová složka nemá konečný kladný rozlišitelný objem – zvětši rozměry "
                    "nebo uprav poslední prvek."
                )
            volumes.append(value)
        volume = shape.volume
        total = math.fsum(volumes)
        if (not math.isfinite(volume)
                or abs(volume - total) > volume_tolerance(total, volume)):
            raise GeometryValidationError(
                "objem celku neodpovídá všem jeho složkám – tvar nelze spolehlivě přijmout; "
                "uprav poslední prvek."
            )
        # Pro konečnost stačí konzervativní obálka; přesné hledání extrémů křivek
        # by při každé bezpečnostní kontrole zbytečně opakovalo drahou optimalizaci.
        box = shape.bounding_box(optimal=False)
        bounds = (*box.min, *box.max)
        coordinates = (v for vertex in shape.vertices() for v in (vertex.X, vertex.Y, vertex.Z))
        if (not math.isfinite(volume) or volume <= volume_tolerance(0, volume)
                or not all(math.isfinite(v) for v in (*bounds, *coordinates))):
            raise GeometryValidationError(
                "tvar nemá konečné souřadnice nebo rozlišitelný objem – zkontroluj rozměry."
            )
        return VolumeFacts(volume, tuple(volumes), bounds)
    except GeometryValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 – neověřitelný tvar nelze přijmout
        raise GeometryValidationError(
            "tvar se nepodařilo spolehlivě ověřit – uprav poslední prvek nebo použij Zpět."
        ) from exc


def check_cut_volume(before: float, after: float, empty_cut: str) -> None:
    """I prázdný výsledek řezu má dostat konkrétní radu o odebrání celého dílu."""
    if not math.isfinite(after):
        raise GeometryValidationError("výsledek řezu nemá konečný objem – uprav řez.")
    tolerance = volume_tolerance(before, after)
    if after <= tolerance:
        raise GeometryValidationError(
            "řez by odebral celý díl – zmenši skicu nebo hloubku řezu."
        )
    if before - after <= tolerance:
        raise GeometryValidationError(
            f"řez neodebral žádný materiál (v rozlišitelné míře) – {empty_cut}."
        )


def check_boolean(operation: str, before: VolumeFacts | None, tool: VolumeFacts,
                  result: VolumeFacts, *, empty_cut: str, empty_add: str) -> None:
    """Nutné objemové podmínky, nikoli důkaz prostorové správnosti jádra."""
    previous = before.volume if before is not None else 0.0
    tolerance = volume_tolerance(previous, result.volume)
    if result.volume <= tolerance:
        raise GeometryValidationError("výsledek nemá rozlišitelný objem – uprav rozměry.")
    if operation == "add" and before is not None:
        if result.volume - previous <= tolerance:
            raise GeometryValidationError(
                f"přidání nepřidalo rozlišitelný materiál – {empty_add}."
            )
        if result.volume > previous + tool.volume + tolerance:
            raise GeometryValidationError(
                "přidání vytvořilo větší objem, než dovolují vstupy – uprav poslední prvek."
            )
    elif operation == "cut":
        check_cut_volume(previous, result.volume, empty_cut)


def check_modification(before: VolumeFacts, result: VolumeFacts, *, shell: bool = False) -> None:
    """Úprava hran/stěn musí zachovat počet složek; skořepina také ubírá materiál."""
    if result.solids != before.solids:
        raise GeometryValidationError(
            f"počet těles se změnil z {before.solids} na {result.solids} – "
            "úprava hran nebo stěn musí zachovat všechny složky; uprav výběr nebo rozměr."
        )
    tolerance = volume_tolerance(before.volume, result.volume)
    if result.volume <= tolerance:
        raise GeometryValidationError("výsledek nemá rozlišitelný objem – uprav rozměry.")
    if shell and result.volume >= before.volume - tolerance:
        raise GeometryValidationError(
            "skořepina nevytvořila rozlišitelné stěny – vyber otevřenou plochu "
            "a zkontroluj tloušťku."
        )
