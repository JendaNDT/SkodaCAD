"""Příkazová řádka: ``skodacad build model.json``.

Postaví díl z modelu, vypíše strom prvků (✓ / ✕ / ·), vlastnosti dílu, uložená měření
a uloží exporty do složky ``out/``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skodacad.document import Document, DocumentError
from skodacad.export import FORMATS, export
from skodacad.expressions import ExpressionError, evaluate
from skodacad.properties import compute
from skodacad.rebuild import BuildResult, rebuild

_ICONS = {"ok": "✓", "error": "✕", "skipped": "·"}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # české znaky i ve Windows konzoli

    parser = argparse.ArgumentParser(prog="skodacad", description="ŠkodaCAD – parametrický 3D CAD")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="postav díl z modelu a ulož exporty")
    build.add_argument("model", type=Path, help="soubor modelu (.json)")
    build.add_argument("-o", "--out", type=Path, default=Path("out"),
                       help="složka pro exporty (výchozí: out)")
    build.add_argument("--set", dest="overrides", action="append", default=[],
                       metavar="NÁZEV=HODNOTA", help="dočasně změň parametr, např. --set D=200")
    build.add_argument("--format", default="step,stl,3mf,svg",
                       help=f"formáty exportu oddělené čárkou ({', '.join(FORMATS)})")
    args = parser.parse_args(argv)

    try:
        return _build(args)
    except (DocumentError, ExpressionError, ValueError, RuntimeError) as exc:
        print(f"Chyba: {exc}", file=sys.stderr)
        return 2


def _parse_overrides(items: list[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for item in items:
        name, separator, value = item.partition("=")
        if not separator or not name.strip():
            raise ValueError(f"--set „{item}“ musí mít tvar NÁZEV=HODNOTA.")
        overrides[name.strip()] = evaluate(value, {})
    return overrides


def _build(args: argparse.Namespace) -> int:
    formats = [f.strip().lower() for f in args.format.split(",") if f.strip()]
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"Neznámý formát: {', '.join(unknown)}; umím: {', '.join(FORMATS)}.")

    document = Document.load(args.model)
    result = rebuild(document, _parse_overrides(args.overrides))

    print(f"Model: {document.name} ({args.model})")
    print("Parametry: " + ", ".join(f"{k}={v:g}" for k, v in result.parameters.items()))
    print("Strom prvků:")
    for status in result.statuses:
        line = f"  {_ICONS[status.status]} {status.label}"
        if status.status == "error":
            line += f" – {status.message}"
        print(line)

    if result.part is None:
        print("Model zatím nemá žádné těleso.")
        return 1

    _print_properties(result, document.material)
    if result.measurements:
        print("Měření:")
        for measurement in result.measurements:
            print(f"  {measurement.text}")

    args.out.mkdir(parents=True, exist_ok=True)
    written = [export(result.part, args.out / f"{args.model.stem}.{fmt}") for fmt in formats]
    if written:
        print("Uloženo: " + ", ".join(str(path) for path in written))
    return 0 if result.ok else 1


def _print_properties(result: BuildResult, material: str) -> None:
    props = compute(result.part, material)
    sx, sy, sz = props.size_mm
    cx, cy, cz = props.center_of_mass_mm
    print("Vlastnosti dílu:")
    print(f"  Objem:     {props.volume_mm3:,.0f} mm³ ({props.volume_mm3 / 1000:,.2f} cm³)"
          .replace(",", " "))
    print(f"  Povrch:    {props.area_mm2:,.0f} mm²".replace(",", " "))
    if props.mass_kg is None:
        print(f"  Hmotnost:  neznámý materiál „{material}“")
    else:
        print(f"  Hmotnost:  {props.mass_kg:.3f} kg ({material}, {props.density_g_cm3} g/cm³)")
    print(f"  Rozměry:   {sx:.2f} × {sy:.2f} × {sz:.2f} mm")
    print(f"  Těžiště:   X {cx:.2f}  Y {cy:.2f}  Z {cz:.2f} mm")
    if props.solids != 1:
        print(f"  Pozor: díl se skládá z {props.solids} samostatných těles.")


if __name__ == "__main__":
    raise SystemExit(main())
