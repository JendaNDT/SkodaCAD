"""Příkazová řádka: ``skodacad build model.json`` a ``skodacad ai model.json "úprava"``.

``build`` postaví díl z modelu, vypíše strom prvků (✓ / ✕ / ·), vlastnosti dílu, uložená
měření, mapu tloušťky stěny (je-li v modelu nastavená, nebo s ``--mapa``) a uloží exporty
do složky ``out/``. ``ai`` upraví model podle popisu přes AI asistenta (Claude API);
když soubor modelu neexistuje, vytvoří nový díl.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skodacad import assistant as ai_assistant
from skodacad.assistant import EFFORTS, AssistantError, AssistantSettings
from skodacad.assistant import MODELS as AI_MODELS
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
    build.add_argument("--mapa", action="store_true",
                       help="spočítej mapu tloušťky stěny i bez nastavení v modelu "
                            "(souhrn + body do CSV)")
    ai = commands.add_parser("ai", help="uprav model podle popisu (AI asistent Claude)")
    ai.add_argument("model", type=Path,
                    help="soubor modelu (.json); když neexistuje, vznikne nový díl")
    ai.add_argument("request", help="co udělat, česky (např. \"zvětši D na 200\")")
    ai.add_argument("-o", "--out", type=Path,
                    help="kam uložit výsledek (výchozí: <model>-ai.json vedle původního)")
    ai.add_argument("--prepsat", action="store_true", help="ulož výsledek do původního souboru")
    ai.add_argument("--claude", choices=sorted(AI_MODELS), help="model Claude (výchozí z "
                    "nastavení, jinak claude-opus-5-5)")
    ai.add_argument("--dukladnost", choices=list(EFFORTS),
                    help="low = rychle a levně, medium, high = důkladně (výchozí)")
    args = parser.parse_args(argv)

    try:
        return _ai(args) if args.command == "ai" else _build(args)
    except (DocumentError, ExpressionError, ValueError, RuntimeError, AssistantError) as exc:
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
    with_map = args.mapa or document.thickness_map is not None
    result = rebuild(document, _parse_overrides(args.overrides), with_map=with_map)

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
    if with_map:
        print("Mapa tloušťky stěny:")
        if result.thickness_map is None:
            print(f"  ✕ {result.map_error}")
        else:
            for line in result.thickness_map.summary():
                print(f"  {line}")
            written.append(result.thickness_map.write_csv(
                args.out / f"{args.model.stem}-tloustka.csv"))
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


def _ai(args: argparse.Namespace) -> int:
    from skodacad.session import ModelSession

    session = ModelSession()
    new_part = not args.model.exists()
    if new_part:
        session.new_document()
        target = args.out or args.model
    else:
        session.open(args.model)
        target = args.out or (args.model if args.prepsat else
                              args.model.with_name(f"{args.model.stem}-ai.json"))
    settings = AssistantSettings.load(ai_assistant.settings_path(ai_assistant.user_dir()))
    if args.claude:
        settings.model = args.claude
    if args.dukladnost:
        settings.effort = args.dukladnost
    tools = ai_assistant.ModelTools(session)
    helper = ai_assistant.new_assistant(settings, tools, _examples_dir())
    print(f"AI asistent ({AI_MODELS[settings.model]}, {EFFORTS[settings.effort]}): "
          f"{'nový díl' if new_part else args.model}")

    def show(kind: str, text: str) -> None:
        if kind == "text":
            print(text, end="", flush=True)
        elif kind == "tool":
            print(f"\n  → {text}", flush=True)
        else:
            print(f"    {text}", flush=True)

    session.begin_group()
    try:
        helper.ask(args.request, session.document.to_dict(), tools.report(), tools.run, show,
                   lambda: session.document.to_dict())
    finally:
        session.end_group()
        print(f"\nSpotřeba: {helper.usage.describe(settings.model)}")
    if session.can_undo:
        session.save(target)
        print(f"Uloženo: {target}")
    else:
        print("Model se nezměnil – nic se neukládá.")
    print(tools.report())
    return 0


def _examples_dir() -> Path | None:
    folder = Path(__file__).resolve().parents[2] / "examples"
    return folder if folder.is_dir() else None
