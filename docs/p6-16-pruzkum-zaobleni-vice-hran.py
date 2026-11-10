"""P6.16: průzkum proměnného zaoblení více hran (jen měření, nic v projektu nemění).

Spuštění z kořene repozitáře:

    .venv/bin/python docs/p6-16-pruzkum-zaobleni-vice-hran.py

Zkouší, co udělá stávající jednohranová operace `variable_fillet.apply` při opakování na víc
hranách téhož dílu, a jak se chová bezprostředně navazující konstantní zaoblení OCCT.
Každý případ má nezávislý analytický objem odebraného materiálu:

    V = (1 − π/4) · délka / 3 · (R1² + R1·R2 + R2²)   (jedna hrana)

Výsledek se ukládá do `out/p6-16-pruzkum-zaobleni-vice-hran.json`.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from build123d import Box, GeomType, Pos, fillet

from skodacad import variable_fillet as vf

OUT = Path("out")


def volume(part) -> float:
    return float(sum(s.volume for s in part.solids()))


def cut_volume(length: float, r1: float, r2: float) -> float:
    return (1 - math.pi / 4) * length / 3 * (r1 * r1 + r1 * r2 + r2 * r2)


def vertical_edge(part, x: float, y: float):
    """Svislá přímá hrana (rovnoběžná se Z) na souřadnicích x, y – jen pro pokus."""
    found = [e for e in part.edges()
             if e.geom_type == GeomType.LINE
             and abs(e.tangent_at(0.5).Z) > 1 - 1e-9
             and abs(e.center().X - x) < 1e-6 and abs(e.center().Y - y) < 1e-6]
    return found[0] if len(found) == 1 else None


def apply_edge(part, history, x, y, r1, r2):
    edge = vertical_edge(part, x, y)
    if edge is None:
        raise vf.VariableFilletError(f"hrana ({x}, {y}) nenalezena")
    reference = vf.reference(part, edge, history)
    return vf.apply(part, edge, r1, r2, reference["direction"], False, reference["normals"])


def main() -> int:
    OUT.mkdir(exist_ok=True)
    results = []

    def record(case, expected, part, note="", error=""):
        row = {"case": case, "expected_removed": expected, "note": note, "error": error}
        if part is not None:
            row["volume"] = volume(part)
            row["solids"] = len(part.solids())
            row["valid"] = bool(part.is_valid)
            row["faces"] = len(part.faces())
        results.append(row)
        flag = "OK" if part is not None and row.get("valid") else "--"
        print(f"{flag} {case:<62} {note} {error}")
        return row

    block = Pos(0, 0, 10) * Box(60, 40, 20)  # svislé hrany v (±30, ±20), z od 0 do 20
    base = volume(block)
    corners = [(30, 20), (-30, 20), (30, -20), (-30, -20)]
    r1, r2 = 2.0, 6.0
    one = cut_volume(20, r1, r2)

    # V1: jedna hrana (kontrola, že stávající operace dá vzorec)
    history = [("telo", block)]
    part = apply_edge(block, history, *corners[0], r1, r2)
    row = record("V1 jedna svislá hrana R2→R6", one, part)
    row["removed"] = base - volume(part)
    row["removed_error"] = row["removed"] - one

    # V2: čtyři nezávislé svislé hrany po sobě
    part, history = block, [("telo", block)]
    try:
        for index, (x, y) in enumerate(corners, start=1):
            part = apply_edge(part, history, x, y, r1, r2)
            history.append((f"vf{index}", part))
        row = record("V2 čtyři svislé hrany po sobě, každá R2→R6", 4 * one, part)
        row["removed"] = base - volume(part)
        row["removed_error"] = row["removed"] - 4 * one
        row["faces_expected"] = len(block.faces()) + 4
    except vf.VariableFilletError as exc:
        record("V2 čtyři svislé hrany po sobě", 4 * one, None, error=str(exc))
    four = part

    # V3: stejné s opačným směrem poloměrů u části hran (R6→R2 na dvou hranách)
    part, history = block, [("telo", block)]
    try:
        for index, (x, y) in enumerate(corners, start=1):
            a, b = (r1, r2) if index % 2 else (r2, r1)
            part = apply_edge(part, history, x, y, a, b)
            history.append((f"vf{index}", part))
        row = record("V3 čtyři hrany, střídavě R2→R6 a R6→R2", 4 * one, part)
        row["removed"] = base - volume(part)
        row["removed_error"] = row["removed"] - 4 * one
    except vf.VariableFilletError as exc:
        record("V3 čtyři hrany střídavě", 4 * one, None, error=str(exc))

    # V4: dvě hrany téže strany, které se dotýkají jen svými zaobleními (tenká deska 12 mm)
    for width, label in ((12.0, "R6 u hrany desky 12 mm – zaoblení se dotknou"),
                         (11.0, "R6 u desky 11 mm – zaoblení by se překrývala")):
        plate = Pos(0, 0, 10) * Box(width, 40, 20)
        history = [("telo", plate)]
        part = plate
        try:
            for index, (x, y) in enumerate([(width / 2, 20), (-width / 2, 20)], start=1):
                part = apply_edge(part, history, x, y, r2, r2)
                history.append((f"vf{index}", part))
            record(f"V4 {label}", 2 * cut_volume(20, r2, r2), part,
                   note="PŘIJATO – musí se odmítnout, pokud se zaoblení překrývají")
        except vf.VariableFilletError as exc:
            record(f"V4 {label}", None, None, error="odmítnuto: " + str(exc)[:70])

    # V5: jedna vodorovná hrana u rohu – samostatná hrana je platný případ P6.2
    top_edges = [e for e in block.edges()
                 if e.geom_type == GeomType.LINE and abs(e.center().Z - 20) < 1e-6
                 and abs(e.tangent_at(0.5).X) > 1 - 1e-9 and abs(e.center().Y - 20) < 1e-6]
    try:
        reference = vf.reference(block, top_edges[0], [("telo", block)])
        part = vf.apply(block, top_edges[0], r1, r2, reference["direction"], False,
                        reference["normals"])
        row = record("V5 jedna vodorovná hrana (délka 60)", cut_volume(60, r1, r2), part)
        row["removed"] = base - volume(part)
        row["removed_error"] = row["removed"] - cut_volume(60, r1, r2)
    except vf.VariableFilletError as exc:
        record("V5 jedna vodorovná hrana", None, None, error=str(exc)[:70])

    # V5b: dvě VYBRANÉ hrany se společným rohem (vodorovná + svislá u téhož vrcholu)
    try:
        first = vf.apply(block, top_edges[0], r1, r2, reference["direction"], False,
                         reference["normals"])
        history = [("telo", block), ("vf1", first)]
        second = apply_edge(first, history, 30, 20, r1, r2)
        record("V5b vodorovná a pak svislá hrana u téhož vrcholu", None, second,
               note="PŘIJATO – očekáváno odmítnutí (společný roh)")
    except vf.VariableFilletError as exc:
        record("V5b vodorovná a pak svislá hrana u téhož vrcholu", None, None,
               error="odmítnuto: " + str(exc)[:80])

    # V6: navazující konstantní zaoblení OCCT na horní hrany po čtyřech svislých zaobleních
    try:
        top = four.edges().filter_by(lambda e: abs(e.center().Z - 20) < 1e-6)
        rounded = fillet(top, 1.0)
        record("V6 konstantní R1 na obvodu horní plochy po čtyřech svislých", None, rounded,
               note=f"odebráno navíc {volume(four) - volume(rounded):.3f} mm³ "
                    f"({len(top)} hran)")
    except Exception as exc:  # noqa: BLE001
        record("V6 konstantní R1 na obvodu horní plochy", None, None,
               error=f"{type(exc).__name__}: {str(exc)[:70]}")

    # V7: totéž na dně (konec s menším poloměrem, R2)
    try:
        bottom = four.edges().filter_by(lambda e: abs(e.center().Z) < 1e-6)
        rounded = fillet(bottom, 1.0)
        record("V7 konstantní R1 na obvodu spodní plochy", None, rounded,
               note=f"odebráno navíc {volume(four) - volume(rounded):.3f} mm³ "
                    f"({len(bottom)} hran)")
    except Exception as exc:  # noqa: BLE001
        record("V7 konstantní R1 na obvodu spodní plochy", None, None,
               error=f"{type(exc).__name__}: {str(exc)[:70]}")


    # V8: skořepina (jako prvek shell: offset dovnitř, otevřená horní plocha) PO zaoblení
    from build123d import offset
    for label, source in (("po čtyřech svislých zaobleních R2→R6", four),
                          ("na kvádru bez zaoblení (kontrola postupu)", block)):
        try:
            top_face = max(source.faces(), key=lambda f: f.center().Z)
            shell = offset(source, amount=-2.0, openings=[top_face])
            ok = bool(shell.is_valid) and volume(shell) < volume(source)
            record(f"V8 skořepina 2 mm {label}", None, shell,
                   note=f"objem {volume(shell):.3f} mm³, stěna kužele se odsadila: {ok}")
        except Exception as exc:  # noqa: BLE001
            record(f"V8 skořepina 2 mm {label}", None, None,
                   error=f"{type(exc).__name__}: {str(exc)[:70]}")

    # V9: zaoblení vnějších hran skořepiny (kryt) – řezací těleso zasáhne dutinu
    try:
        top_face = max(block.faces(), key=lambda f: f.center().Z)
        hollow = offset(block, amount=-2.0, openings=[top_face])
        part = apply_edge(hollow, [("telo", hollow)], 30, 20, r1, r2)
        record("V9 svislá hrana na hotové skořepině R2→R6", None, part,
               note="PŘIJATO – očekáváno odmítnutí (stěna 2 mm < poloměr)")
    except vf.VariableFilletError as exc:
        record("V9 svislá hrana na hotové skořepině R2→R6", None, None,
               error="odmítnuto: " + str(exc)[:80])
    except Exception as exc:  # noqa: BLE001
        record("V9 svislá hrana na hotové skořepině", None, None,
               error=f"{type(exc).__name__}: {str(exc)[:70]}")

    # V10: čas čtyř hran po sobě
    import time
    started = time.perf_counter()
    part, history = block, [("telo", block)]
    for index, (x, y) in enumerate(corners, start=1):
        part = apply_edge(part, history, x, y, r1, r2)
        history.append((f"vf{index}", part))
    record("V10 čas čtyř hran po sobě", None, part, note=f"{time.perf_counter() - started:.2f} s")

    Path(OUT / "p6-16-pruzkum-zaobleni-vice-hran.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
