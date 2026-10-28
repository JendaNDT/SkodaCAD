"""Bezpečné vazby prvních výkresových kót na přepočítaný model.

Rozměr obálky je záměrně celkový rozměr dílu. Válcová kóta je vázaná na
jedinou válcovou plochu nepřetržitě pocházející z konkrétního prvku.
Jakákoliv změna receptu (na rozdíl od hodnot parametrů) vyžaduje nové určení.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from build123d import Face, GeomType

from skodacad.direct_edit import face_origin
from skodacad.document import Document, DocumentError
from skodacad.rebuild import BuildResult, model_signature, require_complete_part


@dataclass(frozen=True)
class DimensionResult:
    id: str
    value: float | None = None
    error: str = ""


def _recipe(document: Document) -> str:
    raw = json.dumps(document.features, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _current(document: Document, result: BuildResult) -> Any:
    part = require_complete_part(result)
    if result.model_signature != model_signature(document):
        raise DocumentError("Přepočet neodpovídá aktuálnímu modelu – nejdřív model přepočítej.")
    return part


def _history(document: Document, result: BuildResult) -> list[tuple[str, Any]]:
    # Díl po prvku je díl před následujícím prvkem; po posledním je výsledný díl.
    ids = [feature["id"] for feature in document.features]
    return [(fid, result.parts_before[ids[i + 1]] if i + 1 < len(ids) else result.part)
            for i, fid in enumerate(ids)]


def _supported_origin(document: Document, origin: str) -> bool:
    """Jen jeden kruhový výřez má jednoznačný význam při změně parametrů."""
    feature = next((f for f in document.features if f.get("id") == origin), None)
    if not feature or feature.get("type") != "extrude" or feature.get("operation") != "cut":
        return False
    sketch = next((f for f in document.features if f.get("id") == feature.get("sketch")), None)
    if not sketch or sketch.get("type") != "sketch" or sketch.get("plane", "XY") not in (
            "XY", "XZ", "YZ"):
        return False
    elements = sketch.get("elements")
    return (isinstance(elements, list) and len(elements) == 1
            and isinstance(elements[0], dict) and elements[0].get("shape") == "circle")


def _cylinders(document: Document, result: BuildResult, origin: str) -> list[Face]:
    part = _current(document, result)
    history = _history(document, result)
    faces = []
    for face in part.faces():
        if face.geom_type != GeomType.CYLINDER:
            continue
        point = face.position_at(0.5, 0.5)
        if face_origin(history, face, point) == origin:
            faces.append(face)
    return faces


def new_overall(document: Document, result: BuildResult, dimension_id: str,
                axis: str) -> dict[str, Any]:
    _current(document, result)
    if axis not in ("x", "y", "z"):
        raise DocumentError("Celkový rozměr musí mít osu x, y nebo z.")
    return {"id": dimension_id, "kind": "overall", "axis": axis}


def new_cylinder(document: Document, result: BuildResult, dimension_id: str,
                 face: Face, kind: str) -> dict[str, Any]:
    part = _current(document, result)
    if kind not in ("diameter", "radius"):
        raise DocumentError("Válcová kóta musí být průměr nebo poloměr.")
    if (not isinstance(face, Face) or face.geom_type != GeomType.CYLINDER
            or not any(face.is_same(f) for f in part.faces())):
        raise DocumentError("Vyber válcovou plochu aktuálního dílu.")
    origin = face_origin(_history(document, result), face, face.position_at(0.5, 0.5))
    if not origin:
        raise DocumentError("Původ válcové plochy nelze určit – kótu nelze bezpečně uložit.")
    if not _supported_origin(document, origin):
        raise DocumentError("Zatím lze navázat jen otvor z výřezu jedné kruhové skici.")
    matches = _cylinders(document, result, origin)
    if len(matches) != 1 or not matches[0].is_same(face):
        raise DocumentError("Prvek vytváří více válcových ploch – kótu nelze jednoznačně navázat.")
    return {"id": dimension_id, "kind": kind, "origin": origin,
            "recipe": _recipe(document)}


def evaluate(document: Document, result: BuildResult, dimension: dict[str, Any]) -> DimensionResult:
    did = str(dimension.get("id", "?"))
    try:
        part = _current(document, result)
        kind = dimension.get("kind")
        if kind == "overall":
            axis = dimension.get("axis")
            if axis not in ("x", "y", "z"):
                raise DocumentError("Neplatná osa celkového rozměru.")
            value = getattr(part.bounding_box().size, axis.upper())
        elif kind in ("diameter", "radius"):
            if dimension.get("recipe") != _recipe(document):
                raise DocumentError("Historie modelu se změnila – vyber plochu kóty znovu.")
            origin = dimension.get("origin")
            if not isinstance(origin, str) or not origin:
                raise DocumentError("Kóta nemá platný původ plochy.")
            if not _supported_origin(document, origin):
                raise DocumentError("Původ kóty není podporovaný – vyber plochu znovu.")
            matches = _cylinders(document, result, origin)
            if len(matches) != 1:
                raise DocumentError("Plocha kóty zanikla nebo není jednoznačná – vyber ji znovu.")
            value = matches[0].radius * (2 if kind == "diameter" else 1)
        else:
            raise DocumentError("Neznámý druh kóty.")
        return DimensionResult(did, float(value))
    except Exception as exc:  # noqa: BLE001 – neplatná kóta nesmí způsobit chybný výstup
        return DimensionResult(did, error=str(exc) or type(exc).__name__)
