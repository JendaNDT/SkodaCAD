"""Průzkum P2.2 – pojistka „původ plochy“ proti záměně plochy po změně historie.

Jednorázový průzkum k návrhu `p2-2-navrh-zapisu-prime-upravy.md`, NE test projektu
a NE produkční kód. Spuštění z kořene repozitáře:

    .venv/bin/python docs/p2-2-pruzkum-puvodu.py

Původ plochy = id prvku, po kterém plocha se stejnou nosnou geometrií v daném bodě
na díle nepřetržitě existuje až do místa úpravy. Při přepočtu se plocha najde dnešním
`find_face` a její původ se porovná s uloženým. Průzkum ukazuje, které záměny tím jdou
zachytit (R04) a že běžné změny parametrů falešnou chybu nevyvolají.
"""

from __future__ import annotations

import copy
import time

from build123d import Face, Part, Vector, Vertex

from skodacad.document import Document
from skodacad.picking import _same_surface
from skodacad.rebuild import rebuild
from skodacad.selectors import SelectionError, find_face

ON_FACE = 1e-6  # mm, stávající mez přenosu plochy (picking._ON_FACE)


def states(document: Document) -> list[tuple[str, Part | None]]:
    """Díl po každém prvku v pořadí receptu: [(id prvku, díl po něm), …]."""
    result = rebuild(document)
    ids = [f["id"] for f in document.features]
    after = []
    for index, feature_id in enumerate(ids):
        if index + 1 < len(ids):
            part = result.parts_before.get(ids[index + 1])
        else:
            part = result.part
        after.append((feature_id, part))
    return after


def present(part: Part | None, face: Face, point: Vector) -> bool:
    """Má díl v bodě plochu se stejnou nosnou geometrií a stejnou orientací?"""
    if part is None:
        return False
    normal = face.normal_at(point)
    for other in part.faces():
        if not _same_surface(other, face):
            continue
        distance, on_other, _ = other.distance_to_with_closest_points(Vertex(point))
        if distance <= ON_FACE and other.normal_at(on_other).dot(normal) > 1 - 1e-6:
            return True
    return False


def origin(history: list[tuple[str, Part | None]], face: Face, point: Vector) -> str | None:
    """Prvek, od kterého plocha v bodě nepřetržitě existuje (hledá se odzadu)."""
    found = None
    for feature_id, part in reversed(history):
        if not present(part, face, point):
            break
        found = feature_id
    return found


def pick(document: Document, spec: dict) -> tuple[str, str | None, float]:
    """Najde plochu odkazem `spec` v hotovém díle → (popis, původ, čas v ms)."""
    history = states(document)
    part = history[-1][1]
    start = time.perf_counter()
    face, on_face = find_face(part, spec)
    source = origin(history, face, on_face)
    ms = (time.perf_counter() - start) * 1000
    kind = str(face.geom_type).split(".")[-1].lower()
    where = f"z = {on_face.Z:.1f}" if kind == "plane" else f"R = {face.radius:g}"
    return f"{kind} {where}", source, ms


BASE = {
    "format": "skodacad", "version": 22, "name": "Průzkum původu", "units": "mm",
    "parameters": {"H": 20, "d": 6},
    "features": [
        {"id": "obrys", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "rectangle", "width": 60, "height": 40}]},
        {"id": "deska", "type": "extrude", "sketch": "obrys", "distance": "H"},
        {"id": "cep_skica", "type": "sketch", "plane": "top",
         "elements": [{"shape": "circle", "diameter": 12, "center": [-15, 0]}]},
        {"id": "cep", "type": "extrude", "sketch": "cep_skica", "distance": 10,
         "operation": "add"},
        {"id": "dira_skica", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "circle", "diameter": "d", "center": [15, 0]}]},
        {"id": "dira", "type": "extrude", "sketch": "dira_skica", "operation": "cut",
         "through_all": True},
        {"id": "pole", "type": "pattern", "features": ["dira"], "kind": "linear",
         "count": 2, "direction": "Y", "spacing": 12},
        {"id": "srazeni", "type": "chamfer", "distance": 2,
         "edges": [{"between": ["front", "right"]}, {"between": ["right", "back"]},
                   {"between": ["back", "left"]}, {"between": ["left", "front"]}]},
    ],
}


def variant(change) -> Document:
    data = copy.deepcopy(BASE)
    change(data)
    return Document.from_dict(data)


def drop(*ids):
    def change(data):
        data["features"] = [f for f in data["features"] if f["id"] not in ids]
    return change


def param(name, value):
    def change(data):
        data["parameters"][name] = value
    return change


def feature(fid, key, value):
    def change(data):
        next(f for f in data["features"] if f["id"] == fid)[key] = value
    return change


TOP_OF_PIN = {"at": [-15, 0, 30], "normal": [0, 0, 1], "type": "plane"}
TOP_OF_PLATE = {"at": [10, 15, 20], "normal": [0, 0, 1], "type": "plane"}
COPY_HOLE = {"at": [18, 12, 10], "normal": [-1, 0, 0], "type": "cylinder", "radius": 3}
COPY_HOLE_FREE = {"at": [18, 12, 10], "normal": [-1, 0, 0], "type": "cylinder"}

CASES = [
    ("O1", "horní plocha čepu", TOP_OF_PIN, None),
    ("O2", "horní plocha desky", TOP_OF_PLATE, None),
    ("O3", "kopie díry z pole (R3)", COPY_HOLE, None),
    ("Z1", "čep smazán → horní plocha čepu", TOP_OF_PIN, drop("cep_skica", "cep")),
    ("Z2", "pole smazáno → kopie díry (R3)", COPY_HOLE, drop("pole")),
    ("Z3", "pole smazáno → kopie díry bez R", COPY_HOLE_FREE, drop("pole")),
    ("Z4", "deska H = 35 (čep vyjede výš) → horní plocha čepu", TOP_OF_PIN, param("H", 35)),
    ("F1", "deska H = 25 → horní plocha desky", TOP_OF_PLATE, param("H", 25)),
    ("F2", "deska H = 25 → horní plocha čepu", TOP_OF_PIN, param("H", 25)),
    ("F3", "díra d = 8 → kopie díry bez R", COPY_HOLE_FREE, param("d", 8)),
    ("F4", "díra d = 8 → kopie díry s R3", COPY_HOLE, param("d", 8)),
    ("F5", "sražení smazáno → horní plocha desky", TOP_OF_PLATE, drop("srazeni")),
    ("F6", "rozteč pole 14 → kopie díry bez R", COPY_HOLE_FREE,
     feature("pole", "spacing", 14)),
]

base = Document.from_dict(BASE)
stored = {}
print("| Případ | Plocha nalezená odkazem | Původ | Závěr |")
print("|---|---|---|---|")
for code, name, spec, change in CASES:
    document = base if change is None else variant(change)
    key = (spec["type"], tuple(spec["at"]))
    try:
        found, source, ms = pick(document, spec)
    except SelectionError as exc:
        print(f"| {code} {name} | odkaz selhal: {exc} | – | chyba už dnes (P1.3) |")
        continue
    if change is None:
        stored[key] = source
        verdict = f"uložit původ ({ms:.0f} ms)"
    elif source == stored.get(key):
        verdict = "původ sedí → úprava proběhne"
    else:
        verdict = f"**původ nesedí** (uloženo {stored.get(key)}) → česká chyba"
    print(f"| {code} {name} | {found} | {source} | {verdict} |")

# Mez pojistky: záměna mezi kusy TÉHOŽ prvku (kopie téhož pole) se nepozná.
THIRD_HOLE = {"at": [18, 24, 10], "normal": [-1, 0, 0], "type": "cylinder"}
three = variant(feature("pole", "count", 3))
_, kept, _ = pick(three, THIRD_HOLE)
found, source, _ = pick(base, THIRD_HOLE)  # pole zpět na 2 kusy: třetí díra zmizela
verdict = ("**nezachyceno** – jiná kopie téhož pole má stejný původ" if source == kept
           else "původ nesedí → česká chyba")
print(f"| M1 pole 3 → 2 kusy → třetí díra (bez R) | {found} | {source} | {verdict} |")
