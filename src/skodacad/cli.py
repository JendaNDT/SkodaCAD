"""Příkazová řádka: ``skodacad build model.json``, ``skodacad ai model.json "úprava"`` a
``skodacad paprsek model.json --z x,y,z --smer dx,dy,dz`` a ``skodacad sonda model.json --bod
x,y,z``.

``build`` postaví díl z modelu, vypíše strom prvků (✓ / ✕ / ·), vlastnosti dílu, uložená
měření, mapu tloušťky stěny (je-li v modelu nastavená, nebo s ``--mapa``) a uloží exporty
do složky ``out/``. ``ai`` upraví model podle popisu přes AI asistenta (Claude API);
když soubor modelu neexistuje, vytvoří nový díl. ``paprsek`` vypíše průchod přímky dílem
(úseky v materiálu, úhly dopadu, jistotu) a ``sonda`` přiložení virtuální sondy (mezera,
přesah, kolize, vůle; s ``--posun`` i posun po přímce) – geometrie NDT bez okna.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from skodacad import assistant as ai_assistant
from skodacad.assistant import EFFORTS, AssistantError, AssistantSettings
from skodacad.assistant import MODELS as AI_MODELS
from skodacad.document import Document, DocumentError
from skodacad.export import FORMATS, export
from skodacad.expressions import ExpressionError, evaluate
from skodacad.ndt import DISCLAIMER
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
    ray = commands.add_parser("paprsek", help="průchod přímky dílem: úseky v materiálu (NDT)")
    ray.add_argument("model", type=Path, help="soubor modelu (.json)")
    ray.add_argument("--z", dest="origin", required=True, metavar="X,Y,Z",
                     help="počátek paprsku v mm, např. 0,0,100 (nebo \"0;0;12,5\")")
    ray.add_argument("--smer", dest="direction", required=True, metavar="DX,DY,DZ",
                     help="směr paprsku, např. 0,0,-1")
    ray.add_argument("--delka", type=float, help="délka paprsku v mm (výchozí: přes celý díl)")
    ray.add_argument("--set", dest="overrides", action="append", default=[],
                     metavar="NÁZEV=HODNOTA", help="dočasně změň parametr, např. --set t=30")
    probe = commands.add_parser("sonda", help="přilož virtuální NDT sondu na díl")
    probe.add_argument("model", type=Path, help="soubor modelu (.json)")
    probe.add_argument("--bod", dest="point", required=True, metavar="X,Y,Z",
                       help="bod přiložení na povrchu (výstupní bod paprsku) v mm")
    probe.add_argument("--smer", dest="direction", metavar="DX,DY,DZ",
                       help="směr paprsku (sklopí se do plochy); výchozí osa X")
    probe.add_argument("--studie", help="vezmi sondu z NDT studie (id, např. s1)")
    probe.add_argument("--prima", type=float, metavar="PRŮMĚR",
                       help="přímá sonda daného průměru [mm]")
    probe.add_argument("--uhlova", metavar="DxŠxV", help="úhlová sonda, např. 40x20x25 [mm]")
    probe.add_argument("--celo", type=float, help="výstupní bod úhlové sondy od čela [mm]")
    probe.add_argument("--mezera", type=float, help="dovolená mezera pod sondou [mm] (0.5)")
    probe.add_argument("--rezerva", type=float, help="manipulační rezerva [mm] (0)")
    probe.add_argument("--posun", dest="move", metavar="DX,DY,DZ",
                       help="posouvej sondu tímto směrem a vypiš, kde volně jede")
    probe.add_argument("--delka", type=float, default=50.0, help="délka posunu [mm] (50)")
    probe.add_argument("--krok", type=float, default=1.0, help="krok posunu [mm] (1)")
    probe.add_argument("--set", dest="overrides", action="append", default=[],
                       metavar="NÁZEV=HODNOTA", help="dočasně změň parametr")
    args = parser.parse_args(_glue_negative(sys.argv[1:] if argv is None else argv))

    try:
        if args.command == "paprsek":
            return _ray(args)
        if args.command == "sonda":
            return _probe(args)
        return _ai(args) if args.command == "ai" else _build(args)
    except (DocumentError, ExpressionError, ValueError, RuntimeError, AssistantError) as exc:
        print(f"Chyba: {exc}", file=sys.stderr)
        return 2


def _ray(args: argparse.Namespace) -> int:
    from skodacad.ndt.geometry import ALGORITHM, GeometryError, PartGeometry

    origin, direction = _vector(args.origin, "--z"), _vector(args.direction, "--smer")
    document = Document.load(args.model)
    result = rebuild(document, _parse_overrides(args.overrides) or None)
    if result.part is None:
        raise ValueError("Model nemá těleso – paprsek nemá čím procházet.")
    try:
        ray = PartGeometry(result.part).cast(origin, direction, args.delka)
    except GeometryError as exc:
        raise ValueError(str(exc)) from None
    print(f"Paprsek z [{_coords(origin)}] směrem [{_coords(direction)}] "
          f"(algoritmus {ALGORITHM}):")
    if not ray.segments:
        print("  materiálem neprochází")
    for number, segment in enumerate(ray.segments, start=1):
        entry = (f"vstup {segment.entry.incidence:.1f}°" if segment.entry
                 else "začíná v materiálu")
        exit_ = (f"výstup {segment.exit.incidence:.1f}°" if segment.exit
                 else "pokračuje za konec paprsku")
        mark = "" if segment.certain else " – NEJISTÝ"
        print(f"  úsek {number}: {segment.start:.2f} → {segment.end:.2f} mm, v materiálu "
              f"{segment.length:.2f} mm ({entry}, {exit_}){mark}")
    print(f"  celkem v materiálu: {ray.material_length:.2f} mm (jen jisté úseky), jistota: "
          + ("ok" if ray.certain else "NEJISTÉ"))
    for reason in ray.reasons:
        print(f"  ⚠ {reason}")
    print("  (jen geometrie přímky – ne fyzikální model UT ani detekovatelnost vad)")
    return 0


def _probe(args: argparse.Namespace) -> int:
    from skodacad.ndt.devices import DeviceError, Probe, place, scan_line
    from skodacad.ndt.geometry import GeometryError, PartGeometry
    from skodacad.ndt.study import study_probe

    point = _vector(args.point, "--bod")
    direction = _vector(args.direction, "--smer") if args.direction else None
    document = Document.load(args.model)
    result = rebuild(document, _parse_overrides(args.overrides) or None)
    if result.part is None:
        raise ValueError("Model nemá těleso – není kam sondu přiložit.")
    try:
        probe = _cli_probe(args, document, Probe, study_probe)
        geo = PartGeometry(result.part)
        placed = place(geo, probe, point, direction)
    except (DeviceError, GeometryError) as exc:
        raise ValueError(str(exc)) from None
    print(f"{probe.label} (mezera nejvýš {probe.max_gap:.2f} mm, rezerva "
          f"{probe.reserve:.2f} mm)")
    print(f"Přiložení v [{_coords(placed.origin)}], paprsek "
          f"[{_coords(placed.x_dir)}]:")
    print(f"  {placed.text}")
    if args.move:
        move = _vector(args.move, "--posun")
        try:
            scan = scan_line(geo, probe, point, direction, move, args.delka, args.krok)
        except DeviceError as exc:
            raise ValueError(str(exc)) from None
        free = ", ".join(f"{a:g}–{b:g} mm" for a, b in scan.free_ranges) or "nikde"
        print(f"Posun směrem [{_coords(move)}] o {args.delka:g} mm po {args.krok:g} mm: "
              f"volně {free}")
        problem = next(((offset, p) for offset, p in scan.positions if not p.ok), None)
        if problem is not None:
            print(f"  první potíž po {problem[0]:g} mm: {problem[1].text}")
    print("  (jen geometrie přiložení – ne fyzikální model UT ani detekovatelnost vad)")
    return 0


def _cli_probe(args: argparse.Namespace, document: Document, probe_class: type,
               study_probe: Any) -> Any:
    """Sonda z příkazové řádky: ze studie, přímá, úhlová, nebo výchozí úhlová."""
    if args.studie:
        studies = (document.ndt or {}).get("studies", [])
        study = next((s for s in studies if s.get("id") == args.studie), None)
        if study is None:
            raise ValueError(f"NDT studie „{args.studie}“ v modelu není.")
        base = study_probe(study)
    elif args.prima is not None:
        base = probe_class.straight(args.prima)
    elif args.uhlova:
        try:
            length, width, height = (float(v.replace(",", "."))
                                     for v in args.uhlova.lower().split("x"))
        except ValueError:
            raise ValueError(f"--uhlova „{args.uhlova}“ musí být délka x šířka x výška, např. "
                             "40x20x25.") from None
        base = probe_class.angle(length, width, height)
    else:
        base = probe_class.angle()
    changes = {key: value for key, value in (("front", args.celo), ("max_gap", args.mezera),
                                             ("reserve", args.rezerva)) if value is not None}
    return probe_class.from_dict({**base.to_dict(), **changes}) if changes else base


def _glue_negative(argv: list[str]) -> list[str]:
    """„--z -150,0,20“ → „--z=-150,0,20“: argparse by zápornou trojici vzal jako volbu."""
    glued: list[str] = []
    items = iter(argv)
    for item in items:
        if item in ("--z", "--smer", "--bod", "--posun"):
            value = next(items, None)
            glued.append(item if value is None else f"{item}={value}")
        else:
            glued.append(item)
    return glued


def _vector(text: str, option: str) -> tuple[float, float, float]:
    """„0,0,100“ nebo „0;0;12,5“ (s desetinnou čárkou) → tři čísla."""
    parts = text.split(";") if ";" in text else text.split(",")
    try:
        x, y, z = (float(part.strip().replace(",", ".")) for part in parts)
    except ValueError:
        raise ValueError(f"{option} „{text}“ musí být tři čísla, např. 0,0,100 nebo "
                         "\"0;0;12,5\".") from None
    return (x, y, z)


def _coords(values: tuple[float, float, float]) -> str:
    return "; ".join(f"{round(v, 4) + 0.0:g}" for v in values)  # bez 3.5e-15 a −0


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
    if result.ndt:
        print("NDT studie:")
        for study in result.ndt:
            print("  " + study.text.replace("\n", "\n  "))
        print(f"  ({DISCLAIMER})")

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
