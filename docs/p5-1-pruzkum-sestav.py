"""Průzkum P5.1 – podklady k návrhu datového formátu sestav.

Jednorázový průzkum k návrhu `p5-1-navrh-formatu-sestav.md`, NE test projektu
a NE produkční kód. Spuštění z kořene repozitáře:

    .venv/bin/python docs/p5-1-pruzkum-sestav.py

Ověřuje na skutečném jádře (build123d 0.13, OCCT 8) to, na čem stojí rozhodnutí
návrhu: pořadí otáčení, přesnost násobků 90°, sdílení tvaru mezi kopiemi téhož dílu,
průnik dvou kopií, cenu sestavení dílu proti posunutí kopie a pravidla cest a cyklů.
"""

from __future__ import annotations

import json
import ntpath
import tempfile
import time
from itertools import dropwhile
from pathlib import Path, PurePosixPath

from build123d import Box, Extrinsic, Intrinsic, Location, Vector

from skodacad.document import Document
from skodacad.ndt.geometry import _common
from skodacad.properties import compute
from skodacad.rebuild import rebuild


def bounds(shape) -> tuple:
    box = shape.bounding_box()
    return tuple(round(v, 9) + 0.0 for v in (*box.min, *box.max))


def p1_poradi_otaceni() -> None:
    print("P1 Pořadí otáčení – nesouměrný kvádr 30 × 20 × 10 v rohu u počátku")
    block = Box(30, 20, 10).moved(Location((15, 10, 5)))
    print("   výchozí obálka          ", bounds(block))
    fixed = block.moved(Location((0, 0, 0), (90, 0, 90), Extrinsic.XYZ))
    print("   pevné osy X→Y→Z (90,0,90)", bounds(fixed), "– čekám (0,0,0)–(10,30,20)")
    default = block.moved(Location((0, 0, 0), (90, 0, 90)))
    print("   výchozí build123d       ", bounds(default), "– jiné pořadí (Intrinsic.XYZ)")
    same = block.moved(Location((0, 0, 0), (90, 0, 90), Intrinsic.ZYX))
    print("   Intrinsic.ZYX           ", bounds(same), "= pevné osy X→Y→Z")


def snapped(angles: tuple[float, float, float]) -> Location:
    """Otočení kolem pevných os X→Y→Z s přesnými hodnotami pro násobky 90°."""
    import math

    from OCP.gp import gp_Trsf

    def cos_sin(degrees: float) -> tuple[float, float]:
        if degrees % 90 == 0:
            return ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))[int(degrees // 90) % 4]
        return math.cos(math.radians(degrees)), math.sin(math.radians(degrees))

    (cx, sx), (cy, sy), (cz, sz) = (cos_sin(a) for a in angles)
    rx = ((1, 0, 0), (0, cx, -sx), (0, sx, cx))
    ry = ((cy, 0, sy), (0, 1, 0), (-sy, 0, cy))
    rz = ((cz, -sz, 0), (sz, cz, 0), (0, 0, 1))

    def mul(a, b):
        return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
                     for i in range(3))

    m = mul(rz, mul(ry, rx))
    trsf = gp_Trsf()
    trsf.SetValues(*m[0], 0.0, *m[1], 0.0, *m[2], 0.0)
    return Location(trsf)


def p2_presnost_90() -> None:
    print("P2 Násobky 90° a zpětný převod na úhly")
    turned = Box(30, 20, 10).moved(Location((15, 10, 5))).moved(
        Location((0, 0, 0), (90, 0, 0), Extrinsic.XYZ))
    raw = turned.bounding_box()
    print(f"   obálka po 90° kolem X: min z = {raw.min.Z!r}, max y = {raw.max.Y!r}")
    # Dvě otočení „tlačítkem“ za sebou a zpět na trojici úhlů.
    step = Location((0, 0, 0), (90, 0, 0), Extrinsic.XYZ)
    step_z = Location((0, 0, 0), (0, 0, 90), Extrinsic.XYZ)
    combined = step_z * step
    angles = combined.wrapped.Transformation().GetRotation()
    from OCP.gp import gp_EulerSequence

    values = angles.GetEulerAngles(gp_EulerSequence.gp_Extrinsic_XYZ)
    print("   90° kolem X, pak 90° kolem Z → úhly", [f"{v * 57.29577951308232:.17g}"
                                                    for v in values])
    exact = Box(30, 20, 10).moved(Location((15, 10, 5))).moved(snapped((90, 0, 0)))
    box = exact.bounding_box()
    print(f"   se zaokrouhlenou maticí: min z = {box.min.Z!r}, max y = {box.max.Y!r}")
    print("   otočený vektor X dílu:", tuple(round(c, 12) + 0.0 for c in
                                         (combined * Location(Vector(1, 0, 0))).position))


def p3_sdileni_tvaru() -> None:
    print("P3 Kopie téhož dílu sdílí tvar (krabicka.json)")
    document = Document.load("examples/krabicka.json")
    start = time.perf_counter()
    part = rebuild(document).part
    built = time.perf_counter() - start
    before = bounds(part)
    start = time.perf_counter()
    copies = [part.moved(Location((100 * i, 0, 0), (0, 0, 90 * i), Extrinsic.XYZ))
              for i in range(100)]
    moved = time.perf_counter() - start
    shared = all(c.wrapped.TShape() == part.wrapped.TShape() for c in copies)
    print(f"   sestavení dílu {built * 1000:.0f} ms, 100 posunutých kopií {moved * 1000:.1f} ms")
    print(f"   všechny kopie sdílí tvar: {shared}; zdroj beze změny: {bounds(part) == before}")
    volumes = {round(c.volume, 6) for c in copies[:5]}
    props = compute(part, document.material)
    print(f"   objem kopií {volumes} mm³, hmotnost kusu {props.mass_kg * 1000:.2f} g")


def p4_prunik_kopii() -> None:
    print("P4 Průnik dvou kopií téhož kvádru 20 × 20 × 20 posunutých o 15 mm")

    def records(shape) -> int:
        return sum(edge.wrapped.TShape().Curves().Size() for edge in shape.edges())

    for label, destructive in (("výchozí build123d &", True), ("nedestruktivní _common", False)):
        block = Box(20, 20, 20)
        a = block.moved(Location((0, 0, 0)))
        b = block.moved(Location((15, 0, 0)))
        start = records(block)
        if destructive:
            volume = (a & b).volume
        else:
            common = _common(a, b)
            from build123d import Shape

            volume = Shape.cast(common.Shape()).volume
        print(f"   {label}: průnik {volume:.3f} mm³ (vzorec 5·20·20 = 2000), "
              f"záznamy hran zdroje {start} → {records(block)}")


def check_path(text: str) -> str:
    """Navrhované pravidlo S4: jen relativní cesta s „/“ a bez prázdných částí."""
    if not text or "\\" in text or text.startswith("/") or ntpath.splitdrive(text)[0]:
        return "odmítnout"
    parts = text.split("/")
    if any(part in ("", ".") for part in parts) or ":" in text:
        return "odmítnout"
    leading = len(parts) - len(list(dropwhile(lambda part: part == "..", parts)))
    if ".." in parts[leading:] or leading == len(parts):
        return "odmítnout"  # „..“ jen na začátku, jinak by stejný soubor měl víc zápisů
    return "ok → " + str(PurePosixPath(text))


def p5_cesty() -> None:
    print("P5 Pravidla cest (S4)")
    for text in ("dily/deska.json", "../dily/deska.json", "C:/dily/deska.json",
                 "/home/jan/deska.json", "dily\\deska.json", "\\\\server\\deska.json",
                 "dily//deska.json", "./deska.json", "dily/../deska.json", "..", ""):
        print(f"   {text!r:28} {check_path(text)}")
    try:
        ntpath.relpath("D:\\dily\\deska.json", "C:\\sestavy")
    except ValueError as exc:
        print(f"   díl na jiném disku Windows: relativní cesta nejde ({exc})")


def p6_cyklus() -> None:
    print("P6 Cyklus podsestav (S10)")
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / "a.json").write_text(json.dumps({"components": [{"path": "b.json"}]}))
        (root / "b.json").write_text(json.dumps({"components": [{"path": "./sub/../a.json"}]}))
        (root / "sub").mkdir()

        def walk(path: Path, chain: list[Path]) -> str:
            real = path.resolve()
            if real in chain:
                names = " → ".join(p.name for p in [*chain, real])
                return f"cyklus: {names}"
            data = json.loads(real.read_text())
            for item in data.get("components", []):
                found = walk(real.parent / item["path"], [*chain, real])
                if found:
                    return found
            return ""

        print("  ", walk(root / "a.json", []))


if __name__ == "__main__":
    for probe in (p1_poradi_otaceni, p2_presnost_90, p3_sdileni_tvaru, p4_prunik_kopii,
                  p5_cesty, p6_cyklus):
        probe()
