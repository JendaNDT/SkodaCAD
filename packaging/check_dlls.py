"""Kontrola sestavené aplikace pro Windows: chybějící knihovny DLL.

Každá DLL, kterou něco v balíčku potřebuje, musí být buď v balíčku, nebo
součástí samotných Windows. Knihovny „Visual C++ Redistributable“ (msvcp140,
vcruntime140, vcomp140 …) mají jen počítače, kam je něco doinstalovalo
(např. sestavovací počítač GitHubu) – na čistém Windows chybí, proto musí
být přibalené.

Použití:  python packaging/check_dlls.py dist/SkodaCAD
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pefile

VC_RUNTIME = re.compile(r"^(msvcp|vcruntime|vcomp|concrt|vccorlib|mfc)\d+.*\.dll$|^libomp.*\.dll$")


def imported_dlls(path: Path) -> list[str]:
    try:
        pe = pefile.PE(str(path), fast_load=True)
    except pefile.PEFormatError:
        return []
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
    )
    entries = getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])
    return [entry.dll.decode(errors="replace") for entry in entries]


def main(root: str) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # česká diakritika i ve Windows konzoli
    bundle = Path(root)
    files = [p for p in bundle.rglob("*") if p.suffix.lower() in (".dll", ".pyd", ".exe")]
    if not files:
        print(f"V {bundle} nejsou žádné DLL – špatná cesta?")
        return 1
    present = {p.name.lower() for p in files}
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"

    missing_runtime: list[str] = []
    not_found: list[str] = []
    for path in files:
        for name in imported_dlls(path):
            low = name.lower()
            if low in present or low.startswith(("api-ms-win-", "ext-ms-")):
                continue
            where = f"{path.relative_to(bundle)} → {name}"
            if VC_RUNTIME.match(low):
                missing_runtime.append(where)
            elif not (system32 / name).exists():
                not_found.append(where)

    print(f"Zkontrolováno {len(files)} souborů DLL/PYD/EXE.")
    unique_not_found = sorted(set(not_found))
    for line in unique_not_found[:30]:
        print(f"  (info) není v balíčku ani ve Windows: {line}")
    if len(unique_not_found) > 30:
        print(f"  (info) … a dalších {len(unique_not_found) - 30}")
    if missing_runtime:
        print("CHYBA – v balíčku chybí knihovny Visual C++, na čistém Windows by aplikace spadla:")
        for line in sorted(set(missing_runtime)):
            print(f"  {line}")
        return 1
    print("OK – všechny knihovny Visual C++ jsou v balíčku.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "dist/SkodaCAD"))
