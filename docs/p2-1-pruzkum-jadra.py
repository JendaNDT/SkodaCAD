"""Průzkum P2.1 – posun rovinné plochy a změna průměru válcové plochy v jádře OCCT.

Jednorázový průzkum k návrhu `p2-1-navrh-rozsahu-primeho-modelovani.md`, NE test
projektu a NE produkční kód. Spuštění z kořene repozitáře:

    .venv/bin/python docs/p2-1-pruzkum-jadra.py

Každý případ má očekávání spočítané ručně ze vzorce; „odmítnout“ znamená, že správná
implementace nesmí výsledek přijmout. Sloupec „pravidla“ ukazuje, co by zachytila
navržená doplňková pravidla G5 (tečný soused, nulová plocha, změna počtu ploch).
"""

from __future__ import annotations

import math
import time
from pathlib import Path

from build123d import (
    Axis,
    Box,
    BuildPart,
    BuildSketch,
    Compound,
    Cylinder,
    Face,
    GeomType,
    Locations,
    Mode,
    Part,
    Plane,
    Polygon,
    Solid,
    chamfer,
    extrude,
    fillet,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepOffset import BRepOffset_MakeOffset, BRepOffset_Skin
from OCP.GeomAbs import GeomAbs_Intersection

from skodacad.document import Document
from skodacad.geometry_validation import check_modification, inspect_volume
from skodacad.rebuild import rebuild

REJECT = None  # očekávání „odmítnout“


def offset_faces(part: Part, moves: list[tuple[Face, float]]) -> Part:
    """Posune vybrané plochy po jejich vnější normále; ostatní plochy se jen prodlouží."""
    solids = part.solids()
    if len(solids) != 1:
        raise RuntimeError("průzkum počítá s jedním tělesem")
    maker = BRepOffset_MakeOffset()
    # Vstupem musí být TopoDS_Solid: se složeninou (Compound) vrátí jádro jen skořápku.
    maker.Initialize(solids[0].wrapped, 0.0, 1e-7, BRepOffset_Skin, False, False,
                     GeomAbs_Intersection, False, False)
    for face, distance in moves:
        maker.SetOffsetOnFace(face.wrapped, distance)
    maker.MakeOffsetShape()
    if not maker.IsDone():
        raise RuntimeError(f"jádro hlásí {maker.Error()}")
    shape = maker.Shape()
    if shape.IsNull() or not BRepCheck_Analyzer(shape).IsValid():
        raise RuntimeError("jádro vrátilo prázdný nebo neplatný tvar")
    # Part(TopoDS_Solid) hlásí objem 0 – obalit složeninou jako jinde v build123d.
    return Part(Compound([Solid(shape)]).wrapped)


def tangent_edges(part: Part, face: Face) -> int:
    """Počet hran plochy, kde soused navazuje tečně (normály se liší o méně než 1°)."""
    count = 0
    for edge in face.edges():
        middle = edge.position_at(0.5)
        for other in part.faces():
            if other.is_same(face) or not any(e.is_same(edge) for e in other.edges()):
                continue
            if math.degrees(face.normal_at(middle).get_angle(other.normal_at(middle))) < 1.0:
                count += 1
    return count


def top(part: Part) -> Face:
    return max((f for f in part.faces() if f.geom_type == GeomType.PLANE),
               key=lambda f: f.center().Z)


def cylinder(part: Part, radius: float) -> Face:
    return next(f for f in part.faces()
                if f.geom_type == GeomType.CYLINDER and abs(f.radius - radius) < 1e-6)


def plane_up(part: Part, z: float) -> Face:
    return next(f for f in part.faces() if f.geom_type == GeomType.PLANE
                and f.normal_at().Z > 0.99 and abs(f.center().Z - z) < 1e-6)


ROWS: list[tuple[str, str, str, str]] = []


def case(code: str, name: str, part: Part, moves: list[tuple[Face, float]],
         expected: float | None) -> None:
    tangent = sum(tangent_edges(part, face) for face, _ in moves)
    before = inspect_volume(part)
    start = time.perf_counter()
    rules = []
    if tangent:
        rules.append(f"tečný soused ({tangent} hran)")
    try:
        result = offset_faces(part, moves)
        facts = inspect_volume(result)
        check_modification(before, facts)
        smallest = min(f.area for f in result.faces())
        if smallest <= 1e-6:
            rules.append(f"nulová plocha ({smallest:.3g} mm²)")
        if len(result.faces()) != len(part.faces()):
            rules.append(f"ploch {len(part.faces())}→{len(result.faces())}")
        ms = (time.perf_counter() - start) * 1000
        if expected is REJECT:
            outcome = f"jádro vrátilo V = {facts.volume:.4f} mm³ ({ms:.0f} ms)"
            verdict = "zachytí pravidla" if rules else "**NEZACHYCENO**"
        else:
            diff = facts.volume - expected
            outcome = f"V = {facts.volume:.4f} mm³, rozdíl {diff:.1e} ({ms:.0f} ms)"
            verdict = "shoda" if abs(diff) < 1e-6 * max(1, expected) and not rules \
                else "**odchylka**"
    except Exception as exc:  # noqa: BLE001 – průzkum zaznamenává každé selhání jádra
        ms = (time.perf_counter() - start) * 1000
        outcome = f"jádro odmítlo: {type(exc).__name__} ({ms:.0f} ms)"
        verdict = "správně odmítnuto" if expected is REJECT else "**selhalo**"
    expectation = "odmítnout" if expected is REJECT else f"{expected:.4f}"
    ROWS.append((f"{code} {name}", expectation, outcome,
                 verdict + (f"; pravidla: {', '.join(rules)}" if rules else "")))


BASE = 40 * 30 * 20
box = Box(40, 30, 20)  # z −10…10
case("K1", "kvádr, horní plocha +5", box, [(top(box), 5)], 40 * 30 * 25)
case("K2", "kvádr, horní plocha −5", box, [(top(box), -5)], 40 * 30 * 15)
case("K3", "kvádr, horní plocha −20 (nulová tloušťka)", box, [(top(box), -20)], REJECT)
case("K4", "kvádr, horní plocha −25 (za protější)", box, [(top(box), -25)], REJECT)
side = next(f for f in box.faces() if f.normal_at().X > 0.99)
case("K5", "kvádr, horní +5 a pravá +2 najednou", box, [(top(box), 5), (side, 2)],
     42 * 30 * 25)

holed = box - Cylinder(5, 20)
case("D1", "průchozí díra Ø10 → Ø8", holed, [(cylinder(holed, 5), 1)],
     BASE - math.pi * 4**2 * 20)
case("D2", "průchozí díra Ø10 → Ø12", holed, [(cylinder(holed, 5), -1)],
     BASE - math.pi * 6**2 * 20)
case("D3", "díra Ø10 → Ø32 (prorazí stěnu)", holed, [(cylinder(holed, 5), -11)], REJECT)

with BuildPart() as b:
    Box(40, 30, 20)
    with Locations((0, 0, 6)):
        Cylinder(5, 8, mode=Mode.SUBTRACT)
case("D4", "slepá díra Ø10 hl. 8 → Ø12", b.part, [(cylinder(b.part, 5), -1)],
     BASE - math.pi * 6**2 * 8)

with BuildPart() as b:
    Box(40, 30, 20)
    with Locations((14, 0, 0)):
        Cylinder(5, 20, mode=Mode.SUBTRACT)
case("D5", "díra u kraje Ø10 → Ø14 (zmizí stěna 1 mm)", b.part,
     [(cylinder(b.part, 5), -2)], REJECT)

with BuildPart() as b:
    Box(40, 30, 20)
    with Locations((0, 0, 15)):
        Cylinder(5, 10)
boss = b.part
case("D6", "čep Ø10 → Ø12", boss, [(cylinder(boss, 5), 1)], BASE + math.pi * 6**2 * 10)
case("S1", "plocha s čepem +5 (čep zůstane, zkrátí se)", boss, [(plane_up(boss, 10), 5)],
     40 * 30 * 25 + math.pi * 5**2 * 5)

with BuildPart() as b:
    Box(40, 30, 20)
    Cylinder(5, 20, mode=Mode.SUBTRACT)
    Cylinder(4, 40, rotation=(90, 0, 0), mode=Mode.SUBTRACT)
case("D7", "křížené díry, svislá Ø10 → Ø8", b.part, [(cylinder(b.part, 5), 1)], REJECT)

with BuildPart() as b:
    Box(40, 30, 20)
    Cylinder(5, 20, mode=Mode.SUBTRACT)
    chamfer(b.edges().filter_by(GeomType.CIRCLE).group_by(Axis.Z)[-1], 1)
chamfered = b.part
case("D8", "díra se sražením 1 mm, Ø10 → Ø11", chamfered,
     [(cylinder(chamfered, 5), -0.5)],
     BASE - math.pi * 5.5**2 * 19.5 - math.pi * 0.5 / 3 * (5.5**2 + 5.5 * 6 + 6**2))
case("D9", "díra se sražením, Ø10 → Ø12 (sražení zanikne)", chamfered,
     [(cylinder(chamfered, 5), -1)], REJECT)

with BuildPart() as b:
    Box(40, 30, 20)
    Cylinder(5, 20, mode=Mode.SUBTRACT)
    fillet(b.edges().filter_by(GeomType.CIRCLE).group_by(Axis.Z)[-1], 1)
case("D10", "díra se zaoblenou hranou R1, Ø10 → Ø11", b.part,
     [(cylinder(b.part, 5), -0.5)], REJECT)

with BuildPart() as b:
    with BuildSketch(Plane.XZ):
        Polygon((-20, 0), (20, 0), (10, 20), (-10, 20), align=None)
    extrude(amount=15, both=True)
trapezoid = b.part
case("R1", "lichoběžník, horní +5 (šikmé boky se prodlouží)", trapezoid,
     [(top(trapezoid), 5)], (40 + 15) / 2 * 25 * 30)
case("R2", "lichoběžník, šikmý bok +3 po normále", trapezoid,
     [(next(f for f in trapezoid.faces() if f.normal_at().X > 0.5), 3)],
     18000 + 3 * math.sqrt(500) * 30)

with BuildPart() as b:
    Box(40, 30, 20)
    fillet(b.edges().filter_by(Axis.Z), 3)
rounded = b.part
case("R3", "svislé hrany R3, horní +5 (sousedé ostře)", rounded, [(top(rounded), 5)],
     inspect_volume(rounded).volume * 25 / 20)

with BuildPart() as b:
    Box(40, 30, 20)
    fillet(b.edges().group_by(Axis.Z)[-1], 3)
case("R4", "horní hrany R3, horní +5 (tečný soused)", b.part, [(top(b.part), 5)], REJECT)

with BuildPart() as b:
    Box(40, 30, 20)
    with Locations((10, 0, 5)):
        Box(20, 30, 10, mode=Mode.SUBTRACT)
step = b.part
low = plane_up(step, 0)
case("R5", "schod, nižší plocha +3", step, [(low, 3)], BASE - 20 * 30 * 7)
case("R6", "schod, nižší plocha +10 (splyne s horní)", step, [(low, 10)], REJECT)
case("R7", "schod, nižší plocha +15 (nad horní)", step, [(low, 15)], REJECT)

with BuildPart() as b:
    Box(40, 30, 20)
    with Locations((0, 0, 7.5)):
        Box(20, 10, 5, mode=Mode.SUBTRACT)
pocket = b.part
case("R8", "dno kapsy +2 (mělčí)", pocket, [(plane_up(pocket, 5), 2)], BASE - 200 * 3)
case("R9", "dno kapsy −3 (hlubší)", pocket, [(plane_up(pocket, 5), -3)], BASE - 200 * 8)

with BuildPart() as b:
    Box(40, 30, 10)
    with Locations((-15, 0, 10), (15, 0, 10)):
        Box(10, 30, 20)
fork = b.part
inner = next(f for f in fork.faces() if f.geom_type == GeomType.PLANE
             and f.normal_at().X > 0.99 and abs(f.center().X + 10) < 1e-6)
case("R10", "U tvar, vnitřní stěna +10 (mezera zůstane)", fork, [(inner, 10)],
     inspect_volume(fork).volume + 10 * 30 * 15)
case("R11", "U tvar, vnitřní stěna +22 (vnikne do druhého zubu)", fork, [(inner, 22)], REJECT)

flange = rebuild(Document.load(Path(__file__).parents[1] / "examples" / "priruba.json")).part
v0 = inspect_volume(flange).volume
bottom = next(f for f in flange.faces() if f.geom_type == GeomType.PLANE
              and f.normal_at().Z < -0.99)
case("P1", "příruba, jedna díra Ø18 → Ø20", flange, [(cylinder(flange, 9), -1)],
     v0 - math.pi * (10**2 - 9**2) * 18)
case("P2", "příruba, spodní plocha −3", flange, [(bottom, -3)], v0 - 3 * bottom.area)
case("P3", "příruba, horní plocha +3 (kuželová sražení se zvětší)", flange,
     [(top(flange), 3)],
     v0 + math.pi * (80.5**2 + 80.5 * 77.5 + 77.5**2) - math.pi * (32**2 + 32 * 35 + 35**2)
     - 4 * math.pi * 9**2 * 3)
case("P4", "příruba, horní plocha −3 (sražení by zaniklo)", flange, [(top(flange), -3)],
     REJECT)

# Tichý nezdar jádra: plocha z JINÉHO tělesa se bez chyby přeskočí.
other = Box(40, 30, 20)
maker = BRepOffset_MakeOffset()
maker.Initialize(box.solids()[0].wrapped, 0.0, 1e-7, BRepOffset_Skin, False, False,
                 GeomAbs_Intersection, False, False)
maker.SetOffsetOnFace(top(other).wrapped, 5.0)
maker.MakeOffsetShape()
foreign = Part(Compound([Solid(maker.Shape())]).wrapped).volume
ROWS.append(("X1 plocha z jiného tělesa, +5", "odmítnout",
             f"jádro: hotovo bez chyby, V = {foreign:.4f} mm³ (beze změny)",
             "**tichý nezdar** – implementace musí ověřit příslušnost a účinek"))

# Navazující prvky na upraveném dílu (kvádr po posunu horní plochy o +5).
moved = offset_faces(box, [(top(box), 5)])
rounded_after = fillet(moved.edges().group_by(Axis.Z)[-1], 2)
ROWS.append(("N1 zaoblení horních hran R2 po posunu", "platné, výška 25",
             f"platné {rounded_after.is_valid}, výška "
             f"{rounded_after.bounding_box().size.Z:.4f}, V = "
             f"{inspect_volume(rounded_after).volume:.4f} mm³",
             "objem zaoblení se vzorcem neověřuje"))
drilled = moved - Cylinder(3, 60)
expected = 40 * 30 * 25 - math.pi * 3**2 * 25
actual = inspect_volume(drilled).volume
ROWS.append(("N2 průchozí díra Ø6 po posunu", f"{expected:.4f}",
             f"V = {actual:.4f} mm³, rozdíl {actual - expected:.1e}",
             "shoda" if abs(actual - expected) < 1e-6 * expected else "**odchylka**"))

print("| Případ | Očekávání [mm³] | Výsledek jádra | Závěr |")
print("|---|---|---|---|")
for row in ROWS:
    print("| " + " | ".join(row) + " |")
