"""Vytvoření syntetických STEP vzorků P3.1, nikoli importní služba aplikace.

Spouštět z kořene projektu: .venv/bin/python tests/fixtures/step/vytvorit_vzorky.py
Výstupy se přepíší. Verze jádra může ovlivnit zápis STEP i kontrolní součty.
"""
from pathlib import Path

from build123d import Align, Box, Compound, Face, Pos, export_step
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

HERE = Path(__file__).resolve().parent
ALIGN = (Align.MIN,) * 3
STAMP = "2026-01-01T00:00:00"


def write_separate(name, shapes, unit="MM"):
    """Samostatné kořeny s výstupní jednotkou; souřadnice jsou zadány v mm."""
    writer = STEPControl_Writer()
    if not Interface_Static.SetCVal_s("write.step.unit", unit):
        raise RuntimeError(f"Jednotku {unit} nelze nastavit")
    try:
        for shape in shapes:
            if writer.Transfer(shape.wrapped, STEPControl_AsIs) != IFSelect_RetDone:
                raise RuntimeError(f"Přenos geometrie pro {name} selhal")
        if writer.Write(str(HERE / name)) != IFSelect_RetDone:
            raise RuntimeError(f"Zápis {name} selhal")
    finally:
        Interface_Static.SetCVal_s("write.step.unit", "MM")


def main():
    one = Box(40, 30, 20, align=ALIGN)
    export_step(one, HERE / "01-jedno-teleso.step", timestamp=STAMP)
    first = Box(10, 20, 30, align=ALIGN)
    second = Pos(30, 0, 0) * Box(5, 10, 15, align=ALIGN)
    write_separate("02-dve-telesa.step", [first, second])
    first.label = "Deska"
    second.label = "Kostka"
    export_step(Compound(children=[first, second], label="Sestava"),
                HERE / "03-sestava.step", timestamp=STAMP)
    write_separate("04-palce.step", [Box(50.8, 25.4, 12.7, align=ALIGN)], "INCH")
    write_separate("07-metry.step", [Box(10, 13, 17, align=ALIGN)], "M")
    export_step(Face.make_rect(40, 20), HERE / "05-otevrena-plocha.step", timestamp=STAMP)
    # Záměrně uříznutý soubor; nejde o další platný STEP ani o automatickou opravu.
    source = (HERE / "01-jedno-teleso.step").read_bytes()
    (HERE / "06-poskozeny.step").write_bytes(source[:len(source) // 2])


if __name__ == "__main__":
    main()
