# PyInstaller: sestavení ŠkodaCAD jako samostatné aplikace (složka s SkodaCAD.exe).
# Spuštění z kořene repozitáře:  pyinstaller packaging/skodacad.spec --noconfirm
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_delvewheel_libs_directory

ROOT = Path(SPECPATH).parent  # noqa: F821 – SPECPATH dodává PyInstaller

datas = [(str(path), "examples") for path in sorted((ROOT / "examples").glob("*.json"))]
binaries = []
hiddenimports = []

# Open CASCADE (OCP) je jeden obří modul + stovky knihoven; build123d a spol. mají data.
for package in ("OCP", "build123d", "ocpsvg", "ocp_gordon", "lib3mf", "cadquery_ocp_proxy"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

# Knihovny OCCT přibalené v kole cadquery-ocp (složka cadquery_ocp_novtk.libs vedle OCP).
datas, binaries = collect_delvewheel_libs_directory(
    "OCP", libdir_name="cadquery_ocp_novtk.libs", datas=datas, binaries=binaries
)

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "skodacad-gui.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "PyInstaller"],  # IPython potřebuje build123d
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SkodaCAD",
    console=False,  # okno bez černé konzole
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SkodaCAD", upx=False)  # noqa: F821
