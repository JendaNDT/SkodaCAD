# PyInstaller: sestavení ŠkodaCAD jako samostatné aplikace (Windows: složka s SkodaCAD.exe,
# macOS: SkodaCAD.app). Spuštění z kořene repozitáře:
#   pyinstaller packaging/skodacad.spec --noconfirm
# -*- mode: python ; coding: utf-8 -*-
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_delvewheel_libs_directory,
    collect_submodules,
)

ROOT = Path(SPECPATH).parent  # noqa: F821 – SPECPATH dodává PyInstaller

datas = [(str(path), "examples") for path in sorted((ROOT / "examples").glob("*.json"))]
datas += [(str(path), path.parent.relative_to(ROOT).as_posix())  # i pomocné cílové objemy
          for path in sorted((ROOT / "examples" / "ndt").rglob("*.json"))]
datas.append((str(ROOT / "README.md"), "."))  # popis formátu modelu pro AI asistenta
binaries = []
# AI asistent: knihovna anthropic načítá části API až při použití – přibalit všechny.
hiddenimports = collect_submodules("anthropic") + collect_submodules("httpx2")
# Commit a datum sestavení (zapíše GitHub Actions; zpráva NDT auditu, O aplikaci).
if (ROOT / "src" / "skodacad" / "_build.py").exists():
    hiddenimports.append("skodacad._build")

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

# macOS (Apple Silicon): SkodaCAD.app; podpis „ad-hoc“ (bez certifikátu) dělá PyInstaller.
if sys.platform == "darwin":
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"]
    app = BUNDLE(  # noqa: F821
        coll,
        name="SkodaCAD.app",
        bundle_identifier="io.github.jendandt.skodacad",
        info_plist={
            "CFBundleDisplayName": "ŠkodaCAD",
            "CFBundleShortVersionString": version,
            "LSMinimumSystemVersion": "13.0",  # PySide6 6.11 potřebuje macOS 13+
            "NSHighResolutionCapable": True,  # ostré písmo na Retina displeji
        },
    )
