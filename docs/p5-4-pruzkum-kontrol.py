"""Průzkum P5.4 – kontroly sestavy: kolize, vůle, kusovník, export STEP.

Jednorázový průzkum k návrhu `p5-4-navrh-kontrol.md`, NE test projektu a NE produkční kód.
Spuštění z kořene repozitáře:

    .venv/bin/python docs/p5-4-pruzkum-kontrol.py

Díly: ukázka krabicka_s_vazbami (krabička, víčko, 4 nožičky) a zkušební kvádry, deska
s dírou pod závit M3 a „šroub“ Ø 3 mm. Kolize = objem průniku nedestruktivním průnikem
(`ndt.geometry.overlap`), vůle = nejmenší vzdálenost (`BRepExtrema_DistShapeShape`).
"""

from __future__ import annotations

import json
import math
import tempfile
import time
from collections import Counter
from itertools import combinations
from pathlib import Path

from skodacad.assembly import Assembly
from skodacad.assembly_build import Cache, build
from skodacad.ndt.geometry import overlap


def distance(a, b) -> float:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    tool = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    tool.Perform()
    return tool.Value() if tool.IsDone() else float("nan")


def boxes_touch(a, b, margin: float) -> bool:
    ba, bb = a.bounding_box(), b.bounding_box()
    amin, amax, bmin, bmax = tuple(ba.min), tuple(ba.max), tuple(bb.min), tuple(bb.max)
    return all(amin[i] - margin <= bmax[i] and bmin[i] - margin <= amax[i] for i in range(3))


def check(result, margin: float = 0.5) -> list[tuple]:
    rows = []
    for x, y in combinations(result.instances, 2):
        if not boxes_touch(x.part, y.part, margin):
            continue
        start = time.perf_counter()
        volume = overlap(x.part, y.part)
        t_common = time.perf_counter() - start
        start = time.perf_counter()
        gap = distance(x.part, y.part)
        t_dist = time.perf_counter() - start
        rows.append(("/".join(x.ids), "/".join(y.ids), volume, gap, t_common, t_dist))
    return rows


def part(width, depth, height, center=(0, 0), hole=None, name="Kvádr"):
    features = [{"id": "s", "type": "sketch", "plane": "XY",
                 "elements": [{"shape": "rectangle", "width": width, "height": depth,
                               "center": list(center)}]},
                {"id": "e", "type": "extrude", "sketch": "s", "distance": height}]
    if hole is not None:
        features += [{"id": "d", "type": "sketch", "plane": "top",
                      "elements": [{"shape": "circle", "diameter": hole, "center": [0, 0]}]},
                     {"id": "o", "type": "extrude", "sketch": "d", "operation": "cut",
                      "distance": height}]
    return {"format": "skodacad", "version": 24, "name": name, "material": "PETG",
            "parameters": {}, "features": features}


def pin(diameter, length):
    return {"format": "skodacad", "version": 24, "name": "Šroub (zjednodušený)",
            "material": "ocel", "parameters": {}, "features": [
                {"id": "s", "type": "sketch", "plane": "XY",
                 "elements": [{"shape": "circle", "diameter": diameter, "center": [0, 0]}]},
                {"id": "e", "type": "extrude", "sketch": "s", "distance": length}]}


def write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def assembly(folder: Path, components: list[dict]) -> Path:
    return write(folder / "s.json", {"format": "skodacad", "kind": "assembly", "version": 29,
                                     "name": "Zkouška", "units": "mm", "parameters": {},
                                     "components": components})


def comp(cid, path, position=(0, 0, 0), rotation=(0, 0, 0)):
    return {"id": cid, "source": {"path": path},
            "placement": {"position": list(position), "rotation": list(rotation)}}


def main() -> None:
    sample = Path("examples/sestavy/krabicka_s_vazbami.json")
    result = build(Assembly.load(sample), sample, Cache())

    print("K1 Ukázka krabicka_s_vazbami: 6 komponent = 15 dvojic")
    start = time.perf_counter()
    rows = check(result)
    took = time.perf_counter() - start
    print(f"   kandidátů po obálkách (rezerva 0,5 mm): {len(rows)} z 15, celkem {took:.2f} s")
    for a, b, volume, gap, t1, t2 in rows:
        print(f"   {a:10} × {b:10} průnik {volume:.4f} mm³, vzdálenost {gap:.4f} mm "
              f"({t1 * 1000:.0f} + {t2 * 1000:.0f} ms)")

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        write(folder / "kvadr.json", part(20, 20, 20, center=(10, 10)))
        print("K2 Dva kvádry 20 mm: překryv o 5 mm, dotyk, mezera 0,3 mm")
        for name, dx in (("překryv", 15), ("dotyk", 20), ("mezera", 20.3)):
            path = assembly(folder, [comp("a", "kvadr.json"), comp("b", "kvadr.json", (dx, 0, 0))])
            res = build(Assembly.load(path), path, Cache())
            a, b = res.instances
            print(f"   {name:8} průnik {overlap(a.part, b.part):.4f} mm³ "
                  f"(vzorec {max(0, 20 - dx) * 400:.4f}), "
                  f"vzdálenost {distance(a.part, b.part):.4f}")

        write(folder / "deska.json", part(30, 30, 6, hole=2.5, name="Deska s dírou pod M3"))
        write(folder / "sroub.json", pin(3, 10))
        path = assembly(folder, [comp("deska", "deska.json"),
                                 comp("sroub", "sroub.json", (0, 0, -2))])
        res = build(Assembly.load(path), path, Cache())
        d, s = res.instances
        expected = math.pi * (1.5 ** 2 - 1.25 ** 2) * 6
        print(f"K3 Šroub Ø 3 v díře pod závit Ø 2,5 (deska 6 mm): průnik "
              f"{overlap(d.part, s.part):.4f} mm³, vzorec π(1,5² − 1,25²)·6 = {expected:.4f}")

        print("K4 40 víček na stejném místě (780 dvojic, všechny se překrývají)")
        lids = [comp(f"v{i}", "dily/vicko.json", (0, 0, 32), (180, 0, 0)) for i in range(40)]
        target = Path("examples/sestavy").resolve()
        path = write(target.parent / "sestavy" / "_pruzkum_p54.json", {
            "format": "skodacad", "kind": "assembly", "version": 29, "name": "Zkouška",
            "units": "mm", "parameters": {}, "components": lids})
        try:
            res = build(Assembly.load(path), path, Cache())
            pairs = list(combinations(res.instances[:12], 2))
            start = time.perf_counter()
            for x, y in pairs:
                overlap(x.part, y.part)
            per = (time.perf_counter() - start) / len(pairs)
            print(f"   přesný průnik víčko × víčko: {per * 1000:.0f} ms na dvojici → 780 dvojic "
                  f"≈ {780 * per:.0f} s")
        finally:
            path.unlink()

    print("K5 Kusovník ukázky: seskupení podle souboru a receptu")
    groups = Counter((str(i.file.name), i.material) for i in result.instances)
    for (name, material), count in groups.items():
        sample_instance = next(i for i in result.instances if i.file.name == name)
        print(f"   {name:16} {count} ks  {material:5} {sample_instance.mass_kg * 1000:.2f} g/ks")

    print("K6 Export STEP se strukturou: kopie s názvy, zpětné načtení (build123d import_step)")
    from build123d import Compound, export_step, import_step

    children = []
    for instance in result.instances:
        shape = instance.part
        shape.label = "/".join(instance.ids)
        children.append(shape)
    tree = Compound(children=children, label="Krabička s víčkem a vazbami")
    with tempfile.TemporaryDirectory() as tmp:
        file = Path(tmp) / "sestava.step"
        start = time.perf_counter()
        export_step(tree, str(file))
        took = time.perf_counter() - start
        back = import_step(str(file))
        leaves = [c for c in back.children] if back.children else []
        flat = []
        while leaves:
            node = leaves.pop(0)
            if node.children:
                leaves = list(node.children) + leaves
            else:
                flat.append(node)
        labels = sorted(n.label for n in flat)
        volume = sum(n.volume for n in flat)
        box = back.bounding_box()
        print(f"   zápis {took:.2f} s, {file.stat().st_size // 1024} kB; kořen „{back.label}“, "
              f"listů {len(flat)}: {labels}")
        print(f"   objem zpět {volume:.2f} mm³ (sestava {result.volume_mm3:.2f}), obálka "
              f"{tuple(round(v, 3) for v in box.min)} – {tuple(round(v, 3) for v in box.max)}")

    print("K7 Vlastní zápis XCAF (výrobek = soubor dílu, kopie = id komponenty)")
    xcaf_names(result)


def xcaf_names(result) -> None:
    """K7: vlastní zápis XCAF – výrobek = soubor dílu (jednou), kopie = id komponenty."""
    from OCP.collections import Sequence_TDF_Label
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    def name_of(label) -> str:
        attr = TDataStd_Name()
        found = label.FindAttribute(TDataStd_Name.GetID_s(), attr)
        return attr.Get().ToExtString() if found else "?"

    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    root = tool.NewShape()
    TDataStd_Name.Set_s(root, TCollection_ExtendedString("Víčko a krabička", True))
    products = {}
    for instance in result.instances:
        shape = instance.part.wrapped
        if instance.file not in products:
            products[instance.file] = tool.AddShape(shape.Located(TopLoc_Location()), False)
            TDataStd_Name.Set_s(products[instance.file],
                                TCollection_ExtendedString(instance.file.stem))
        component = tool.AddComponent(root, products[instance.file], shape.Location())
        TDataStd_Name.Set_s(component, TCollection_ExtendedString("/".join(instance.ids)))
    tool.UpdateAssemblies()
    with tempfile.TemporaryDirectory() as tmp:
        file = Path(tmp) / "sestava.step"
        writer = STEPCAFControl_Writer()
        writer.SetNameMode(True)
        start = time.perf_counter()
        writer.Transfer(doc, STEPControl_AsIs)
        writer.Write(str(file))
        took = time.perf_counter() - start
        raw = file.read_bytes()
        utf8 = "Víčko".encode() in raw
        back = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        ok = reader.ReadFile(str(file)) == IFSelect_RetDone and reader.Transfer(back)
        shapes = XCAFDoc_DocumentTool.ShapeTool_s(back.Main())
        free, parts = Sequence_TDF_Label(), Sequence_TDF_Label()
        shapes.GetFreeShapes(free)
        shapes.GetComponents_s(free.Value(1), parts)
        pairs = []
        for index in range(parts.Length()):
            component, product = parts.Value(index + 1), TDF_Label()
            shapes.GetReferredShape_s(component, product)
            pairs.append(f"{name_of(component)}→{name_of(product)}")
        root_name = name_of(free.Value(1))
        print(f"   zápis {took:.2f} s, {len(raw) // 1024} kB, zpět {ok}; kořen „{root_name}“"
              f" (UTF-8 bajty v souboru: {utf8})")
        print(f"   kopie → výrobek: {', '.join(pairs)}")


if __name__ == "__main__":
    main()
