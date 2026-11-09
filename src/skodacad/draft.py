"""Úkos stěn (P6.11, návrh ``docs/p6-11-ukos-steny.md``).

Jádro OCCT (``BRepOffsetAPI_DraftAngle``) zkosí zadané rovinné a válcové plochy kolem
neutrální roviny a šíří úkos po tečně navazujících plochách. Služba před voláním odmítne
vstupy, které jádro neumí, a **po něm změří sklon každé zadané plochy ve výsledku**: žádné
tiché přijetí a žádná náhradní aproximace.

Znaménko: kladný úhel nakloní vnější normálu plochy ke směru tažení (vnější stěna se ve
směru tažení zúží, stěna kapsy se rozšíří). Úhel je **absolutní**: výsledný sklon plochy vůči
směru tažení je právě zadaný (i když už byla nakloněná). Neutrální rovina je kolmá na osu
tažení; v ní se rozměr nemění.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from build123d import Compound, Face, GeomType, Part, Shape, Vector
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepOffsetAPI import BRepOffsetAPI_DraftAngle
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

MAX_ANGLE = 30.0  # stupně, horní mez úhlu v prvním vydání
TOL = 1e-6
PULLS = {
    "+X": (1.0, 0.0, 0.0), "-X": (-1.0, 0.0, 0.0),
    "+Y": (0.0, 1.0, 0.0), "-Y": (0.0, -1.0, 0.0),
    "+Z": (0.0, 0.0, 1.0), "-Z": (0.0, 0.0, -1.0),
}
FACE_KINDS = ("plane", "cylinder")
FEATURE_KEYS = {"id", "type", "name", "faces", "pull", "angle", "neutral"}
FACE_KEYS = {"at", "normal", "type", "origin"}


class DraftError(ValueError):
    """Český důvod odmítnutí úkosu."""


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _vector3(value: object) -> bool:
    return (isinstance(value, list) and len(value) == 3
            and all(_number(v) and math.isfinite(v) for v in value))


def _face_spec(spec: object, kinds: Sequence[str], label: str) -> None:
    if not isinstance(spec, dict):
        raise DraftError(f"{label} musí být odkaz na plochu {{\"at\", \"normal\", \"type\", "
                         "\"origin\"}} – vyber ji ve 3D.")
    unknown = set(spec) - FACE_KEYS
    if unknown:
        raise DraftError(f"{label}: neznámý klíč " + ", ".join(sorted(map(str, unknown))) + ".")
    if not _vector3(spec.get("at")) or not _vector3(spec.get("normal")):
        raise DraftError(f"{label} potřebuje „at“ a „normal“ jako trojici čísel.")
    if spec.get("type") not in kinds:
        raise DraftError(f"{label}: druh plochy musí být " + " nebo ".join(kinds) + ".")
    origin = spec.get("origin")
    if not isinstance(origin, str) or not origin:
        raise DraftError(f"{label}: chybí původ plochy („origin“) – vyber plochu znovu ve 3D.")


def validate(feature: dict[str, Any]) -> None:
    """Kontrola struktury zapsaného prvku (bez vyhodnocení výrazů a bez dílu)."""
    unknown = set(feature) - FEATURE_KEYS
    if unknown:
        raise DraftError("Úkos stěn: neznámý klíč " + ", ".join(sorted(map(str, unknown))) + ".")
    faces = feature.get("faces")
    if not isinstance(faces, list) or not faces:
        raise DraftError("Úkos stěn potřebuje aspoň jednu plochu („faces“) – vyber ji ve 3D.")
    for spec in faces:
        _face_spec(spec, FACE_KINDS, "Plocha úkosu")
    if feature.get("pull") not in PULLS:
        raise DraftError("Směr tažení („pull“) musí být " + ", ".join(PULLS) + ".")
    angle = feature.get("angle")
    if isinstance(angle, bool) or not isinstance(angle, (int, float, str)):
        raise DraftError("Úhel úkosu („angle“) musí být číslo nebo výraz.")
    neutral = feature.get("neutral")
    if isinstance(neutral, dict):
        _face_spec(neutral, ("plane",), "Neutrální rovina")
    elif isinstance(neutral, bool) or not isinstance(neutral, (int, float, str)):
        raise DraftError("Neutrální rovina („neutral“) musí být souřadnice (číslo nebo výraz) "
                         "nebo rovinná plocha dílu.")


def axis(pull: object) -> Vector:
    if pull not in PULLS:
        raise DraftError("Směr tažení musí být " + ", ".join(PULLS) + ".")
    return Vector(*PULLS[str(pull)])


def coordinate(point: Vector, pull: object) -> float:
    """Souřadnice bodu na ose tažení (v osách dílu, znaménko směru se nepoužije)."""
    a = axis(pull)
    return abs(a.X) * point.X + abs(a.Y) * point.Y + abs(a.Z) * point.Z


def neutral_from_face(face: Face, pull: object) -> float:
    """Poloha neutrální roviny z rovinné plochy dílu; plocha musí být kolmá na tažení."""
    if face.geom_type != GeomType.PLANE:
        raise DraftError("Neutrální rovina musí být rovinná plocha dílu.")
    if abs(face.normal_at().dot(axis(pull))) < 1 - 1e-9:
        raise DraftError("Neutrální plocha musí být kolmá na směr tažení – vyber vodorovnou "
                         "plochu při tažení ve svislém směru, nebo zadej souřadnici číslem.")
    return coordinate(face.center(), pull)


def _cylinder_axis(face: Face) -> Vector:
    direction = BRepAdaptor_Surface(face.wrapped).Cylinder().Axis().Direction()
    return Vector(direction.X(), direction.Y(), direction.Z())


def _normal(face: Face) -> Vector:
    return face.normal_at(face.center())


def apply(part: Part, faces: Sequence[Face], pull: object, angle: float,
          neutral: float) -> Part:
    """Zkosí zadané plochy dílu o ``angle`` stupňů kolem neutrální roviny a výsledek ověří."""
    vector = axis(pull)
    if not _number(angle) or not math.isfinite(angle) or abs(angle) < 1e-9 \
            or abs(angle) > MAX_ANGLE:
        raise DraftError(f"Úhel úkosu musí být nenulový a nejvýš ±{MAX_ANGLE:g}°.")
    if not _number(neutral) or not math.isfinite(neutral):
        raise DraftError("Poloha neutrální roviny musí být konečné číslo.")
    if not faces:
        raise DraftError("Vyber aspoň jednu plochu úkosu.")
    for index, face in enumerate(faces):
        if any(face.is_same(other) for other in faces[:index]):
            raise DraftError(f"Plocha č. {index + 1} je v seznamu dvakrát.")
        if not any(face.is_same(own) for own in part.faces()):
            raise DraftError(f"Plocha č. {index + 1} už k dílu nepatří – vyber ji znovu ve 3D.")

    # tvrdé předpoklady jádra: jen rovina a válec; válec s osou rovnoběžnou s tažením
    for index, face in enumerate(faces, start=1):
        if face.geom_type == GeomType.PLANE:
            if abs(_normal(face).dot(vector)) > 1 - TOL:
                raise DraftError(
                    f"Plocha č. {index} je kolmá na směr tažení – úkos se dělá na stěnách "
                    "rovnoběžných se směrem tažení (třeba svislých při tažení nahoru).")
        elif face.geom_type == GeomType.CYLINDER:
            if abs(_cylinder_axis(face).dot(vector)) < 1 - 1e-9:
                raise DraftError(
                    f"Válcová plocha č. {index} má osu mimo směr tažení – úkos jde na válec "
                    "s osou rovnoběžnou se směrem tažení.")
        else:
            raise DraftError(f"Plocha č. {index} není rovina ani válec – úkos ji neumí.")

    base = Vector(abs(vector.X), abs(vector.Y), abs(vector.Z)) * neutral
    plane = gp_Pln(gp_Pnt(base.X, base.Y, base.Z), gp_Dir(vector.X, vector.Y, vector.Z))
    direction = gp_Dir(vector.X, vector.Y, vector.Z)
    radians = math.radians(angle)
    builder = BRepOffsetAPI_DraftAngle(part.wrapped)
    for index, face in enumerate(faces, start=1):
        try:
            builder.Add(face.wrapped, direction, radians, plane)
            done = builder.AddDone()
        except Exception:  # noqa: BLE001 – jádro hlásí různé výjimky stejným významem
            done = False
        if not done:
            raise DraftError(
                f"Plochu č. {index} nejde zkosit kolem této roviny a směru tažení. Častá "
                "příčina: tečně na ni navazuje zaoblení nebo jiná plocha, kterou se zkosit "
                "nedá (třeba zaoblení dna kapsy). Udělej úkos před zaoblením, nebo vyber "
                "jen stěny bez takto navazujících ploch.")
    try:
        builder.Build()
        done = builder.IsDone()
    except Exception:  # noqa: BLE001
        done = False
    if not done:
        raise DraftError(f"Úkos {angle:g}° se nepodařil – stěny by se při tak velkém úhlu "
                         "srazily nebo překročily okolní geometrii. Zmenši úhel.")
    solids = Shape.cast(builder.Shape()).solids()
    if not solids:
        raise DraftError("Úkos nevytvořil žádné těleso – změň úhel nebo neutrální rovinu.")
    result = Part(Compound(list(solids)).wrapped)

    # Ověření výsledku: sklon každé zadané plochy se změří na výsledném tělese. Jádro
    # nastavuje sklon jako absolutní hodnotu vůči směru tažení (i nakloněná stěna skončí
    # přesně na zadaném úhlu), proto je očekávání jen sin(úhel).
    expected = math.sin(radians)
    for index, face in enumerate(faces, start=1):
        changed = Shape.cast(builder.ModifiedShape(face.wrapped))
        found = [g for g in result.faces() if g.is_same(changed)]
        if len(found) != 1:
            raise DraftError(f"Sklon plochy č. {index} se nepodařilo ověřit – úkos se "
                             "nepřijímá. Zkus jinou neutrální rovinu nebo úhel.")
        actual = _normal(found[0]).dot(vector)
        if abs(actual - expected) > 1e-6:
            raise DraftError(f"Plocha č. {index} po úkosu nemá očekávaný sklon "
                             f"(změřeno {math.degrees(math.asin(max(-1, min(1, actual)))):.4f}°"
                             f", očekáváno {angle:.4f}°) – úkos "
                             "se nepřijímá.")
    return result
