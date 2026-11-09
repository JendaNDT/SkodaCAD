"""P6.11: průzkum úkosu stěn v jádru OCCT (BRepOffsetAPI_DraftAngle) – jen měření.

Spuštění z kořene repozitáře:

    .venv/bin/python docs/p6-11-pruzkum-ukosu.py

Výsledky se vypíšou a uloží do ``out/p6-11-pruzkum-ukosu.json``. Skript nic v projektu
nemění. Každý případ má nezávislý analytický objem (jehlan / kužel komolý) a kontroluje se
platnost, počet těles a rozměr horní hrany. Cílem je zjistit, co jádro opravdu umí:
směr a znaménko úhlu, neutrální rovinu, kapsy, zaoblené rohy (tečné stěny), válec a selhání.
"""

import json
import math
import sys
from pathlib import Path

from build123d import Box, Cylinder, Part, Pos, Shape, Solid, fillet
from OCP.BRepOffsetAPI import BRepOffsetAPI_DraftAngle
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

OUT = Path("out")


def side_faces(part, normal_z=0.0, tol=1e-6):
    """Plochy, jejichž normála je kolmá na Z (svislé stěny) – jen pro pokus, ne pro produkci."""
    found = []
    for face in part.faces():
        n = face.normal_at(face.center())
        if abs(n.Z) <= tol:
            found.append(face)
    return found


def draft(part, faces, direction, angle_deg, neutral_z, reverse=False):
    """Zavolá DraftAngle; vrátí (těleso | None, text chyby)."""
    d = BRepOffsetAPI_DraftAngle(part.wrapped)
    vec = (0.0, 0.0, -1.0 if reverse else 1.0) if direction == "z" else direction
    plane = gp_Pln(gp_Pnt(0, 0, neutral_z), gp_Dir(0, 0, 1))
    for face in faces:
        try:
            d.Add(face.wrapped, gp_Dir(*vec), math.radians(angle_deg), plane)
        except Exception as exc:  # noqa: BLE001
            return None, f"Add: {type(exc).__name__}: {str(exc)[:80]}"
        if not d.AddDone():
            return None, "AddDone = False"
    d.Build()
    if not d.IsDone():
        return None, "IsDone = False"
    shape = Shape.cast(d.Shape())
    return shape, ""


def stats(shape):
    solids = shape.solids()
    return {
        "valid": bool(shape.is_valid),
        "solids": len(solids),
        "volume": float(sum(s.volume for s in solids)),
        "zmin": float(shape.bounding_box().min.Z),
        "zmax": float(shape.bounding_box().max.Z),
        "xspan": float(shape.bounding_box().size.X),
        "yspan": float(shape.bounding_box().size.Y),
    }


def frustum_box(a, b, h, t, z0, z1, neutral):
    """Objem kvádru a × b se svislými stěnami skloněnými o tg = t od neutrální roviny:
    rozměr v rovině z je (a − 2 t s)(b − 2 t s) kde s = z − neutral (kladné směrem k odebrání)."""
    def area(z):
        s = z - neutral
        return (a - 2 * t * s) * (b - 2 * t * s)
    n = 4000  # Simpson by stačil; kvadratika → přesné i s lichoběžníky při jemném dělení
    step = (z1 - z0) / n
    return sum((area(z0 + (i + 0.5) * step)) * step for i in range(n))


def main() -> int:
    OUT.mkdir(exist_ok=True)
    results = []

    def record(name, expected, shape, note="", error=""):
        row = {"case": name, "expected_volume": expected, "note": note, "error": error}
        if shape is not None:
            row.update(stats(shape))
            if expected is not None:
                row["volume_error"] = row["volume"] - expected
        results.append(row)
        flag = "OK" if shape is not None and row.get("valid") else "--"
        vol = f'{row["volume"]:.6f}' if shape is not None else "—"
        exp = f"{expected:.6f}" if expected is not None else "—"
        print(f"{flag} {name:<46} V={vol}  očekáváno={exp}  {error}{note}")

    box = Box(40, 30, 20)  # z od −10 do 10
    box = Pos(0, 0, 10) * box  # z od 0 do 20
    walls = side_faces(box)
    t5 = math.tan(math.radians(5))

    # K1: úkos 5°, neutrální rovina = dno (z = 0); směr tažení +Z
    for reverse in (False, True):
        shape, err = draft(box, walls, "z", 5.0, 0.0, reverse=reverse)
        name = f"K1 kvádr 5°, neutrální z=0, tažení {'−Z' if reverse else '+Z'}"
        if shape is not None:
            st = stats(shape)
            note = f"  (horní hrana rozměr {st['xspan']:.3f})"
        else:
            note = ""
        record(name, frustum_box(40, 30, 20, -t5 if reverse else t5, 0, 20, 0), shape, note, err)

    # K2: neutrální rovina uprostřed (z = 10): v rovině řezu se rozměr nemění
    shape, err = draft(box, walls, "z", 5.0, 10.0)
    record("K2 kvádr 5°, neutrální z=10 (uprostřed)", frustum_box(40, 30, 20, t5, 0, 20, 10),
           shape, "", err)

    # K3: záporný úhel (opačný směr)
    shape, err = draft(box, walls, "z", -5.0, 0.0)
    record("K3 kvádr −5°, neutrální z=0", frustum_box(40, 30, 20, -t5, 0, 20, 0), shape, "", err)

    # K4: jen dvě protilehlé stěny (typické pro odlitek) – jen stěny kolmé na X
    x_walls = [f for f in walls if abs(f.normal_at(f.center()).X) > 0.5]
    shape, err = draft(box, x_walls, "z", 5.0, 0.0)
    exp = 30 * (40 * 20 - 2 * t5 * 20 * 20 / 2 * 1)  # jen rozměr v X se zužuje
    record("K4 dvě stěny kolmé na X, 5°, z=0", exp, shape, "", err)

    # K5: válec Ø20 × 30 → komolý kužel
    cyl = Pos(0, 0, 15) * Cylinder(10, 30)
    cyl_walls = [f for f in cyl.faces() if abs(f.normal_at(f.center()).Z) < 1e-6
                 or f.geom_type.name == "CYLINDER"]
    cyl_walls = [f for f in cyl.faces() if f.geom_type.name == "CYLINDER"]
    shape, err = draft(cyl, cyl_walls, "z", 3.0, 0.0)
    t3 = math.tan(math.radians(3))
    exp = sum(math.pi * (10 - t3 * (0 + (i + 0.5) * 30 / 4000)) ** 2 * (30 / 4000)
              for i in range(4000))
    record("K5 válec Ø20×30, 3°, z=0", exp, shape, "", err)

    # K6: kvádr se zaoblenými svislými hranami R4 (tečné stěny – úkos se šíří řetězcem)
    rounded = fillet(box.edges().filter_by(lambda e: abs(e.center().Z - 10) < 1e-6 and
                                           e.length > 19), 4)
    rounded_walls = side_faces(rounded)
    shape, err = draft(rounded, rounded_walls[:1], "z", 4.0, 0.0)
    t4 = math.tan(math.radians(4))
    exp6 = sum(((40 - 2 * t4 * z) * (30 - 2 * t4 * z) - (4 - math.pi) * (4 - t4 * z) ** 2)
               * (20 / 4000) for z in ((i + 0.5) * 20 / 4000 for i in range(4000)))
    record("K6 zaoblené svislé hrany R4, úkos 4° na jedné stěně (řetěz)", exp6, shape,
           f"  (stěn celkem {len(rounded_walls)})", err)

    # K7: kapsa v bloku (vnitřní stěny, odebraný materiál) – úkos zužuje kapsu směrem ke dnu
    block = Pos(0, 0, 10) * Box(60, 50, 20)
    pocket = Pos(0, 0, 15) * Box(30, 20, 10)  # dutina od z = 10 do 20 (otevřená nahoře)
    cut = Part(Solid(block.wrapped).cut(Solid(pocket.wrapped).wrapped)) if False else block - pocket
    pocket_walls = [f for f in cut.faces() if abs(f.normal_at(f.center()).Z) < 1e-6
                    and abs(f.center().X) < 20 and abs(f.center().Y) < 20]
    shape, err = draft(cut, pocket_walls, "z", 5.0, 20.0, reverse=False)
    exp7 = 60000 - sum((30 - 2 * t5 * s) * (20 - 2 * t5 * s) * (10 / 4000)
                       for s in ((i + 0.5) * 10 / 4000 for i in range(4000)))
    record("K7 kapsa 30×20×10 v bloku, 5°, neutrální = horní plocha", exp7, shape,
           f"  (stěn kapsy {len(pocket_walls)})", err)

    # K8: díl s vodorovným stupněm – stěny nad stupněm sousedí s vodorovnou plochou
    step_block = box + Pos(0, 0, 25) * Box(20, 15, 10)  # nahoře menší hranol (z 20 až 30)
    upper = [f for f in step_block.faces() if abs(f.normal_at(f.center()).Z) < 1e-6
             and f.center().Z > 20]
    shape, err = draft(step_block, upper, "z", 3.0, 20.0)
    t3b = math.tan(math.radians(3))
    exp8 = 40 * 30 * 20 + sum((20 - 2 * t3b * s) * (15 - 2 * t3b * s) * (10 / 4000)
                              for s in ((i + 0.5) * 10 / 4000 for i in range(4000)))
    record("K8 stupňovitý díl, úkos jen horního hranolu, neutrální z=20", exp8, shape,
           f"  (horních stěn {len(upper)})", err)

    # G1: směr tažení +X, neutrální rovina x = 0 (stěna kolmá na Y a Z se zužuje s rostoucím x)
    box_x = Pos(20, 0, 0) * Box(40, 30, 20)  # x od 0 do 40
    sides_x = [f for f in box_x.faces() if abs(f.normal_at(f.center()).X) < 1e-6]
    d = BRepOffsetAPI_DraftAngle(box_x.wrapped)
    plane_x = gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0))
    ok = True
    for face in sides_x:
        d.Add(face.wrapped, gp_Dir(1, 0, 0), math.radians(5.0), plane_x)
        ok = ok and d.AddDone()
    d.Build()
    shape = Shape.cast(d.Shape()) if ok and d.IsDone() else None
    exp_g1 = sum((30 - 2 * t5 * s) * (20 - 2 * t5 * s) * (40 / 4000)
                 for s in ((i + 0.5) * 40 / 4000 for i in range(4000)))
    record("G1 vodorovný směr tažení +X, 5°, neutrální x=0", exp_g1, shape, "",
           "" if ok else "AddDone = False")

    # F1: příliš velký úhel
    shape, err = draft(box, walls, "z", 80.0, 0.0)
    record("F1 kvádr 80° (příliš strmý)", None, shape, "", err)

    # F2: úkos vodorovné plochy vůči svislému tažení (stěna kolmá na směr tažení)
    top = [f for f in box.faces() if abs(f.normal_at(f.center()).Z - 1) < 1e-6]
    shape, err = draft(box, top, "z", 5.0, 0.0)
    record("F2 vodorovná plocha vůči tažení +Z", None, shape, "", err)

    # F3: neutrální rovina mimo díl (z = 100)
    shape, err = draft(box, walls, "z", 5.0, 100.0)
    record("F3 neutrální rovina daleko mimo díl (z=100)", frustum_box(40, 30, 20, t5, 0, 20, 100),
           shape, "", err)

    Path(OUT / "p6-11-pruzkum-ukosu.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
