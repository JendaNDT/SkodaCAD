"""Příkazová řádka: ``skodacad build model.json``, ``skodacad ai model.json "úprava"`` a
``skodacad paprsek model.json --z x,y,z --smer dx,dy,dz``, ``skodacad sonda model.json --bod
x,y,z`` a ``skodacad audit model.json`` (předběžný NDT audit všech studií).

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
from skodacad.ndt import DISCLAIMER, MT_DISCLAIMER, PT_DISCLAIMER, RT_DISCLAIMER, UT_DISCLAIMER
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
    probe.add_argument("--uhel", dest="beam_angle", type=float, metavar="STUPNĚ",
                       help="úhel lomu paprsku v materiálu [°] (výchozí 45 u úhlové, 0 u přímé)")
    probe.add_argument("--snell", metavar="ALFA,C1,C2",
                       help="spočti úhel lomu ze Snellova zákona: úhel v předsádce [°], "
                            "rychlost v předsádce a v materiálu [m/s]")
    probe.add_argument("--vlna", default="shear", choices=("shear", "longitudinal"),
                       help="druh vlny v materiálu pro --snell (shear = příčná, longitudinal)")
    probe.add_argument("--odrazy", dest="bounces", type=int, metavar="POČET",
                       help="maximální počet odrazů paprsku (výchozí 1 u úhlové, 0 u přímé)")
    probe.add_argument("--dosah", dest="max_length", type=float, metavar="MM",
                       help="maximální délka dráhy paprsku v materiálu [mm]")
    probe.add_argument("--mezera", type=float, help="dovolená mezera pod sondou [mm] (0.5)")
    probe.add_argument("--rezerva", type=float, help="manipulační rezerva [mm] (0)")
    _library_arguments(probe)
    probe.add_argument("--posun", dest="move", metavar="DX,DY,DZ",
                       help="posouvej sondu tímto směrem a vypiš, kde volně jede")
    probe.add_argument("--delka", type=float, default=50.0, help="délka posunu [mm] (50)")
    probe.add_argument("--krok", type=float, default=1.0, help="krok posunu [mm] (1)")
    probe.add_argument("--set", dest="overrides", action="append", default=[],
                       metavar="NÁZEV=HODNOTA", help="dočasně změň parametr")
    coverage = commands.add_parser("pokryti", help="mapa geometrického pokrytí UT")
    coverage.add_argument("model", type=Path)
    coverage.add_argument("--plocha", required=True, metavar="X,Y,Z",
                          help="výchozí bod sondy na pojezdové ploše [mm]")
    coverage.add_argument("--studie", help="UT studie se sondou a cílovými plochami/objemem")
    coverage.add_argument("--cil", action="append", metavar="X,Y,Z",
                          help="kontrolovaný bod (lze opakovat)")
    coverage.add_argument("--cil-plocha", action="append", metavar="X,Y,Z",
                          help="bod určující cílovou plochu (lze opakovat)")
    coverage.add_argument("--rezim", choices=("line", "face"), default="face")
    coverage.add_argument("--krok", type=float, default=5.0, help="krok pojezdu [mm]")
    coverage.add_argument("--krok-cile", type=float,
                          help="krok sítě cíle [mm]; jinak u objemu šestina menšího rozměru "
                               "průřezu, u ploch --krok")
    coverage.add_argument("--delka", type=float, default=50.0, help="délka přímé dráhy [mm]")
    coverage.add_argument("--smer", type=float, default=0.0, help="natočení sondy [°]")
    coverage.add_argument("--sklon", "--uhel", dest="beam_angle", type=float)
    coverage.add_argument("--prima", type=float, metavar="PRŮMĚR")
    coverage.add_argument("--uhlova", metavar="DxŠxV")
    coverage.add_argument("--celo", type=float)
    coverage.add_argument("--mezera", type=float)
    coverage.add_argument("--rezerva", type=float)
    coverage.add_argument("--odrazy", dest="bounces", type=int)
    coverage.add_argument("--dosah", dest="max_length", type=float)
    coverage.add_argument("--snell", metavar="ALFA,C1,C2")
    coverage.add_argument("--vlna", choices=("shear", "longitudinal"), default="shear")
    _library_arguments(coverage)
    coverage.add_argument("--tolerance", type=float, help="numerický poloměr zachycení [mm]")
    coverage.add_argument("--rozevreni", type=float, default=0.0, help="poloviční úhel [°]")
    coverage.add_argument("--konvergence", action="store_true", help="porovnej krok a 2× krok")
    coverage.add_argument("--csv", type=Path)
    coverage.add_argument("--set", dest="overrides", action="append", default=[])
    access = commands.add_parser("polohy", help="návrh poloh UT sondy: přístupnost "
                                 "a geometrické pokrytí variant")
    access.add_argument("model", type=Path)
    access.add_argument("--studie", required=True, help="UT studie se sondou a cílem")
    access.add_argument("--krok", type=float, default=10.0, help="krok analýzy [mm]")
    access.add_argument("--smery", type=float, choices=(30, 45, 90), default=45,
                        help="směry paprsku po … stupních (+ k cíli, od cíle, kolmo na svar)")
    access.add_argument("--uhly", metavar="B1,B2,…",
                        help="zkus i další úhly β [°], např. 45,60,70 (stejné rozměry sondy)")
    access.add_argument("--odrazy", default="0,1", metavar="0,1",
                        help="počty odrazů k vyzkoušení (0–2)")
    access.add_argument("--krok-cile", type=float,
                        help="krok sítě cíle [mm]; jinak u objemu doporučený, u ploch --krok")
    access.add_argument("--tolerance", type=float, help="numerický poloměr zachycení [mm]")
    access.add_argument("--rozevreni", type=float, default=0.0, help="poloviční úhel [°]")
    access.add_argument("--csv", type=Path)
    plan = commands.add_parser("draha", help="plán dráhy UT sondy: řádky cik-cak, přestavení, "
                               "nájezd, zakázané zóny a geometrické pokrytí")
    plan.add_argument("model", type=Path)
    plan.add_argument("--studie", required=True, help="UT studie se sondou a cílem")
    plan.add_argument("--plocha", metavar="X,Y,Z",
                      help="plánuj z přiložené sondy: bod na rovinné kontaktní ploše [mm]")
    plan.add_argument("--smer", type=float, default=0.0, help="směr paprsku [°] k --plocha")
    plan.add_argument("--varianta", type=int, metavar="N",
                      help="plánuj N-tou variantu návrhu poloh (spustí návrh poloh)")
    plan.add_argument("--kombinace", action="store_true",
                      help="plánuj kombinaci návrhu poloh (spustí návrh poloh)")
    plan.add_argument("--prepocet", action="store_true",
                      help="ověř a spočítej plán uložený ve studii")
    plan.add_argument("--vzor", default="auto", help="auto, k-cili nebo podel")
    plan.add_argument("--roztec", type=float, default=5.0, help="rozteč řádků [mm]")
    plan.add_argument("--najezd", type=float, default=20.0,
                      help="výška nájezdu [mm], 0 = nekontrolovat")
    plan.add_argument("--kontrola", type=float, default=1.0, help="kontrolní krok [mm]")
    plan.add_argument("--zona", action="append", metavar="X1,Y1,Z1:X2,Y2,Z2",
                      help="přidej zakázanou zónu – kvádr dvěma rohy (lze opakovat)")
    plan.add_argument("--krok-cile", type=float,
                      help="krok sítě cíle [mm]; jinak u objemu doporučený, u ploch rozteč")
    plan.add_argument("--tolerance", type=float, help="numerický poloměr zachycení [mm]")
    plan.add_argument("--rozevreni", type=float, default=0.0, help="poloviční úhel [°]")
    plan.add_argument("--srovnani", action="store_true",
                      help="spočítej i pojezd po celých plochách průchodů")
    plan.add_argument("--odolnost", action="store_true",
                      help="spočítej i pokrytí po posunu řádků o ± půl rozteče")
    plan.add_argument("--ulozit", action="store_true", help="ulož model s plánem a zónami")
    plan.add_argument("--csv", type=Path)

    pt = commands.add_parser("kapilarni", help="PT: geometrická přístupnost povrchu pro "
                             "kapilární zkoušku (nástřik, otření, prohlídka)")
    pt.add_argument("model", type=Path)
    pt.add_argument("--studie", required=True, help="PT studie s vybranými plochami")
    pt.add_argument("--krok", type=float, help="krok sítě [mm]; jinak automaticky")
    pt.add_argument("--nastroj", type=float, help="průměr hlavního nástroje [mm] (výchozí 10)")
    pt.add_argument("--jemny", type=float, help="průměr jemného nástroje [mm], 0 = bez něj")
    pt.add_argument("--delka", type=float, help="délka dříku nástroje [mm] (výchozí 100)")
    pt.add_argument("--oplach", action="store_true",
                    help="čištění a odstranění přebytku oplachem (ne otřením)")
    pt.add_argument("--ulozit", action="store_true", help="ulož nastavení PT do modelu")
    pt.add_argument("--csv", type=Path)

    mag = commands.add_parser("magneticka", help="MT: přiložení jha a směry magnetizace "
                              "(geometrie zkoušky jhem)")
    mag.add_argument("model", type=Path)
    mag.add_argument("--studie", required=True, help="MT studie s vybranými plochami")
    mag.add_argument("--roztec", type=float, help="rozteč pólů [mm] (výchozí 100)")
    mag.add_argument("--nejmensi", type=float,
                     help="nejmenší rozteč, zkusí se, když hlavní nejde [mm] (výchozí 75)")
    mag.add_argument("--krok", type=float, help="krok sítě míst [mm]; jinak automaticky")
    mag.add_argument("--krok-stredu", type=float, dest="krok_stredu",
                     help="krok mřížky středů jha [mm]; jinak automaticky")
    mag.add_argument("--feromagneticky", action="store_true",
                     help="potvrď, že je materiál feromagnetický (nerez, neuvedený)")
    mag.add_argument("--bez-naneseni", action="store_true", dest="bez_naneseni",
                     help="nepočítej nanesení detekčního prostředku")
    mag.add_argument("--bez-prohlidky", action="store_true", dest="bez_prohlidky",
                     help="nepočítej prohlídku")
    mag.add_argument("--ulozit", action="store_true", help="ulož nastavení MT do modelu")
    mag.add_argument("--csv", type=Path)

    rad = commands.add_parser("radiografie", help="RT: geometrie projekce (zdroj, detektor, "
                              "prozařovaná tloušťka, promítnutí oblasti)")
    rad.add_argument("model", type=Path)
    rad.add_argument("--studie", required=True, help="RT studie s oblastí a projekcemi")
    rad.add_argument("--projekce", action="append",
                     help="počítej jen tuto projekci (jde opakovat); jinak všechny")
    rad.add_argument("--trida", choices=("A", "B"), help="třída zkoušky (výchozí B)")
    rad.add_argument("--ohnisko", type=float, help="rozměr ohniska d [mm] (výchozí 3)")
    rad.add_argument("--vzdalenost", type=float,
                     help="vzdálenost zdroje od zaměřeného bodu [mm] u počítaných projekcí "
                          "(volný detektor zůstane na místě)")
    rad.add_argument("--krok", type=float, help="krok sítě míst [mm]; jinak automaticky")
    rad.add_argument("--krok-nahledu", type=float, dest="krok_nahledu",
                     help="krok náhledu prozařované tloušťky na detektoru [mm] (výchozí 2)")
    rad.add_argument("--ulozit", action="store_true", help="ulož nastavení a projekce do modelu")
    rad.add_argument("--csv", type=Path)

    aud = commands.add_parser("audit", help="předběžný NDT audit – zpráva o geometrickém "
                              "posouzení všech studií modelu (jen pohled, model se nemění)")
    aud.add_argument("model", type=Path)
    aud.add_argument("--studie", action="append",
                     help="jen tato studie (jde opakovat; tl = mapa tloušťky); jinak všechny")
    aud.add_argument("--navrh-poloh", action="append", dest="navrh_poloh",
                     help="u této UT studie bez plánu spusť návrh poloh (pomalé – minuty až "
                          "desítky minut; jde opakovat)")
    aud.add_argument("--slozka", type=Path,
                     help="ulož zprávu do složky (zprava.html, mista.csv, CSV studií)")
    aud.add_argument("--zpracovatel", default="", help="kdo audit zpracoval (do zprávy)")
    args = parser.parse_args(_glue_negative(sys.argv[1:] if argv is None else argv))

    try:
        if args.command == "paprsek":
            return _ray(args)
        if args.command == "sonda":
            return _probe(args)
        if args.command == "pokryti":
            return _coverage(args)
        if args.command == "polohy":
            return _access(args)
        if args.command == "draha":
            return _plan(args)
        if args.command == "kapilarni":
            return _pt(args)
        if args.command == "magneticka":
            return _mt(args)
        if args.command == "radiografie":
            return _rt(args)
        if args.command == "audit":
            return _audit(args)
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
    from skodacad.ndt.devices import DeviceError, place, scan_line
    from skodacad.ndt.geometry import GeometryError, PartGeometry
    from skodacad.ndt.ut import BeamError, refract, trace_beam

    if args.beam_angle is not None and args.snell is not None:
        raise ValueError("Zadej buď --uhel, nebo --snell, ne obojí.")
    point = _vector(args.point, "--bod")
    direction = _vector(args.direction, "--smer") if args.direction else None
    refraction = None
    if args.snell:
        alpha, c1, c2 = _vector(args.snell, "--snell")
        refraction = refract(alpha, c1, c2, args.vlna)
    document = Document.load(args.model)
    result = rebuild(document, _parse_overrides(args.overrides) or None)
    if result.part is None:
        raise ValueError("Model nemá těleso – není kam sondu přiložit.")
    try:
        probe, device_lines, _material = _cli_device(args, document)
        geo = PartGeometry(result.part)
        placed = place(geo, probe, point, direction)
        beam = trace_beam(geo, placed, beta=args.beam_angle, bounces=args.bounces,
                          max_length=args.max_length, refraction=refraction)
    except (DeviceError, GeometryError, BeamError) as exc:
        raise ValueError(str(exc)) from None
    print(f"{probe.label} (mezera nejvýš {probe.max_gap:.2f} mm, rezerva "
          f"{probe.reserve:.2f} mm)")
    for line in device_lines:
        print(f"  {line}")
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
    print(beam.text)
    print(f"  ({UT_DISCLAIMER})")
    return 0


def _library_arguments(parser: argparse.ArgumentParser) -> None:
    """Knihovna NDT (etapa 08) – společné pro „sonda“ a „pokryti“."""
    parser.add_argument("--profil", metavar="KLÍČ",
                        help="profil sondy z knihovny (např. uhlova-standardni-70, prima-10) "
                             "nebo název z Mých sond")
    parser.add_argument("--material-ut", metavar="NÁZEV",
                        help="materiál pro UT (ocel, nerez, hliník, měď, mosaz nebo z Mých "
                             "sond); jinak ze studie")
    parser.add_argument("--prepocet-uhlu", action="store_true",
                        help="přepočti úhel sondy do materiálu pro UT (Snellův zákon)")
    parser.add_argument("--knihovna", type=Path, metavar="SOUBOR",
                        help="soubor Mých sond (výchozí ~/SkodaCAD/ndt-knihovna.json)")


def _cli_device(args: argparse.Namespace, document: Document) -> tuple[Any, list[str], Any]:
    """Sonda, řádky o profilu/materiálu/úhlu a materiál pro UT z příkazové řádky.
    Úhel se do jiného materiálu přepočítá jen s --prepocet-uhlu."""
    from skodacad.ndt.library import (
        check_angle,
        describe,
        find_material,
        load_user_library,
        transferred,
        user_library_path,
    )
    from skodacad.ndt.study import study_material
    from skodacad.ndt.ut import BeamError

    library = load_user_library(args.knihovna or user_library_path())
    probe = _cli_probe(args, document, library.probes)
    study = _cli_study(args, document)
    material = study_material(study) if study is not None else None
    if args.material_ut:
        material = find_material(args.material_ut, library.materials)
        if material is None:
            raise ValueError(f"Materiál pro UT „{args.material_ut}“ v knihovně není (vestavěné: "
                             "ocel, nerez, hliník, měď, mosaz; vlastní přidej do Mých sond).")
    check = check_angle(probe, material, document.material)
    if args.prepocet_uhlu:
        if args.beam_angle is not None or args.snell:
            raise ValueError("--prepocet-uhlu nejde spojit s --uhel ani --snell.")
        try:
            probe = transferred(probe, check)
        except BeamError as exc:
            raise ValueError(str(exc)) from None
        check = check_angle(probe, material, document.material)
    used = args.profil or args.material_ut
    return probe, [*(library.problems if used else []), *describe(probe, material, check)], \
        material


def _cli_study(args: argparse.Namespace, document: Document) -> dict[str, Any] | None:
    if not args.studie:
        return None
    studies = (document.ndt or {}).get("studies", [])
    study = next((s for s in studies if s.get("id") == args.studie), None)
    if study is None:
        raise ValueError(f"NDT studie „{args.studie}“ v modelu není.")
    return study


def _cli_probe(args: argparse.Namespace, document: Document, mine: dict[str, Any]) -> Any:
    """Sonda z příkazové řádky: profil z knihovny, ze studie, přímá, úhlová, nebo výchozí."""
    from skodacad.ndt.devices import Probe
    from skodacad.ndt.library import PROBES
    from skodacad.ndt.study import study_probe

    if args.profil:
        found = PROBES.get(args.profil) or next(
            (p for p in PROBES.values() if p.name == args.profil), None)
        base = found.probe if found is not None else mine.get(args.profil)
        if base is None:
            raise ValueError(f"Profil sondy „{args.profil}“ neznám. Vestavěné: "
                             f"{', '.join(PROBES)}" + (f"; Moje sondy: {', '.join(mine)}"
                                                      if mine else "") + ".")
    elif args.studie:
        base = study_probe(_cli_study(args, document))
    elif args.prima is not None:
        base = Probe.straight(args.prima)
    elif args.uhlova:
        try:
            length, width, height = (float(v.replace(",", "."))
                                     for v in args.uhlova.lower().split("x"))
        except ValueError:
            raise ValueError(f"--uhlova „{args.uhlova}“ musí být délka x šířka x výška, např. "
                             "40x20x25.") from None
        base = Probe.angle(length, width, height)
    else:
        base = Probe.angle()
    changes = {key: value for key, value in (("front", args.celo), ("max_gap", args.mezera),
                                             ("reserve", args.rezerva)) if value is not None}
    if not changes:
        return base
    data = {**base.to_dict(), **changes}
    if "front" in changes and base.origins:  # výstupní bod z profilu přepsán ručně
        data["origins"] = {**dict(base.origins), "front": "entered"}
    return Probe.from_dict(data)


def _coverage(args: argparse.Namespace) -> int:
    from skodacad.ndt.coverage import check_convergence
    from skodacad.ndt.coverage import compute as coverage_compute
    from skodacad.ndt.devices import place
    from skodacad.ndt.geometry import PartGeometry
    from skodacad.ndt.study import part_fingerprint
    from skodacad.ndt.ut import refract
    from skodacad.ndt.volume_coverage import check_volume_convergence, compute_volume

    if args.beam_angle is not None and args.snell is not None:
        raise ValueError("Zadej buď --sklon, nebo --snell, ne obojí.")
    if args.cil and args.cil_plocha:
        raise ValueError("Zadej buď --cil, nebo --cil-plocha, ne obojí.")
    document = Document.load(args.model)
    result = rebuild(document, _parse_overrides(args.overrides) or None)
    geo = PartGeometry(result.part)
    probe, device_lines, ut_material = _cli_device(args, document)
    placed = place(geo, probe, _vector(args.plocha, "--plocha"), angle=args.smer)
    faces, points, target = [], None, None
    if args.cil:
        points = [_vector(text, "--cil") for text in args.cil]
    elif args.cil_plocha:
        for text in args.cil_plocha:
            surface = geo.surface_at(_vector(text, "--cil-plocha"))
            if surface.distance > 1e-4 or not surface.certain:
                raise ValueError("Cílovou plochu urči bodem uvnitř plochy, mimo její hrany.")
            if not any(surface.face.wrapped.IsSame(f.wrapped) for f in faces):
                faces.append(surface.face)
    elif args.studie:
        record = next(s for s in (document.ndt or {}).get("studies", [])
                      if s["id"] == args.studie)
        study_result = next(s for s in result.ndt if s.id == args.studie)
        if record["method"] != "UT" or study_result.state != "ok":
            raise ValueError("Vyber platnou UT studii.")
        if (record.get("target") or {}).get("kind") in ("volume", "weld"):
            target = record["target"]
        else:
            faces, problems = geo.faces_of(record.get("target"))
            if problems:
                raise ValueError(" ".join(problems))
    else:
        raise ValueError("Zadej --cil, --cil-plocha nebo --studie s kontrolovanou oblastí.")
    refraction = refract(*_vector(args.snell, "--snell"), args.vlna) if args.snell else None
    inputs = ({"target": target} if target is not None else
              {"faces": faces or None, "points": points})
    options = dict(**inputs, mode=args.rezim,
                   scan_step=args.krok,
                   target_step=(args.krok_cile if args.krok_cile is not None
                                else None if target is not None else args.krok),
                   length_mm=args.delka, angle_deg=args.smer, tolerance_mm=args.tolerance,
                   spread_deg=args.rozevreni, beta=args.beam_angle, bounces=args.bounces,
                   max_length=args.max_length, refraction=refraction)
    compute = compute_volume if target is not None else coverage_compute
    covered = compute(geo, placed, **options)
    covered.assumptions.update(model=args.model.name, parameters=dict(result.parameters),
                               study_id=args.studie,
                               part_fingerprint=part_fingerprint(document),
                               evaluated_target=(target["kind"] if target else
                                                 "points" if points else "faces"),
                               device_lines=device_lines,
                               **({"ut_material": ut_material.to_dict()} if ut_material else {}))
    if args.konvergence:  # text porovnání je pak i v souhrnu
        (check_volume_convergence if target is not None else check_convergence)(
            geo, placed, fine=covered, **options)
    print("\n".join(covered.summary()))
    print("Předpoklady:", covered.assumptions)
    if args.csv:
        try:
            print("CSV:", covered.write_csv(args.csv))
        except OSError as exc:
            raise ValueError(f"CSV nejde uložit: {exc}") from None
    return 0


def _access(args: argparse.Namespace) -> int:
    from skodacad.session import ModelSession

    def numbers(text: str, option: str, kind: type) -> tuple:
        try:
            return tuple(kind(v) for v in text.split(",") if v.strip())
        except ValueError:
            raise ValueError(f"{option} čeká čísla oddělená čárkou.") from None

    options = {"step_mm": args.krok, "direction_step_deg": args.smery,
               "angles": numbers(args.uhly, "--uhly", float) if args.uhly else (),
               "bounces": numbers(args.odrazy, "--odrazy", int),
               "target_step_mm": args.krok_cile, "tolerance_mm": args.tolerance,
               "spread_deg": args.rozevreni}
    session = ModelSession()
    session.open(args.model)
    print(session.ndt_access_estimate(args.studie, options).text, file=sys.stderr)

    def progress(stage: str, done: int, total: int) -> None:
        print(f"{stage}: {min(done + 1, total)} z {total}", file=sys.stderr, flush=True)

    result = session.compute_ndt_access(args.studie, options, progress=progress)
    print("\n".join(result.summary()))
    if args.csv:
        print("CSV:", session.export_ndt_access(args.csv))
    return 0


def _plan(args: argparse.Namespace) -> int:
    from build123d import Vector

    from skodacad.ndt.plan import PATTERN_CHOICES, Zone
    from skodacad.session import ModelSession

    session = ModelSession()
    session.open(args.model)
    study = args.studie

    def progress(stage: str, done: int, total: int) -> None:
        text = f"{stage}: {min(done + 1, total)} z {total}" if total > 1 else stage
        print(text, file=sys.stderr, flush=True)

    zones = list(session.ndt_zones(study))
    for text in args.zona or []:
        low_text, separator, high_text = text.partition(":")
        if not separator:
            raise ValueError(f"--zona „{text}“ musí být X1,Y1,Z1:X2,Y2,Z2 (dva rohy kvádru).")
        low, high = _vector(low_text, "--zona"), _vector(high_text, "--zona")
        corners = [tuple(min(a, b) for a, b in zip(low, high, strict=True)),
                   tuple(max(a, b) for a, b in zip(low, high, strict=True))]
        zones.append(Zone(f"zóna {len(zones) + 1}", *corners))
    if args.zona:
        session.set_ndt_zones(study, zones)
    options = {"pattern": {"k-cili": "toward", "podel": "along"}.get(args.vzor, args.vzor),
               "row_step_mm": args.roztec, "approach_mm": args.najezd,
               "check_step_mm": args.kontrola, "target_step_mm": args.krok_cile,
               "tolerance_mm": args.tolerance, "spread_deg": args.rozevreni,
               "compare": args.srovnani, "robustness": args.odolnost}
    if options["pattern"] not in PATTERN_CHOICES:
        raise ValueError("--vzor musí být auto, k-cili nebo podel.")
    if args.prepocet:
        result = session.check_ndt_plan(study, options, progress=progress)
    else:
        if args.plocha is not None:
            point = _vector(args.plocha, "--plocha")
            face = min(session.result.part.faces(),
                       key=lambda f: f.distance_to(Vector(*point)))
            session.place_ndt_probe(study, [face.wrapped], point, args.smer)
            passes = session.ndt_plan_passes(study)
        elif args.varianta is not None or args.kombinace:
            print("Návrh poloh sondy (výchozí nastavení etapy 09) …", file=sys.stderr)
            session.compute_ndt_access(study, progress=progress)
            passes = (session.ndt_plan_passes(study, "combination") if args.kombinace
                      else session.ndt_plan_passes(study, "variant", args.varianta - 1))
        else:
            raise ValueError("Zadej, odkud plánovat: --plocha X,Y,Z (a --smer), "
                             "--varianta N, --kombinace, nebo --prepocet uloženého plánu.")
        print(session.ndt_plan_estimate(study, passes, options).text, file=sys.stderr)
        result = session.compute_ndt_plan(study, passes, options, progress=progress)
    print("\n".join(result.summary()))
    if args.csv:
        try:
            print("CSV:", result.write_csv(args.csv))
        except OSError as exc:
            raise ValueError(f"CSV nejde uložit: {exc}") from None
    if args.ulozit:
        print("Model uložen:", session.save())
    return 0


def _pt(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from skodacad.session import ModelSession

    session = ModelSession()
    session.open(args.model)
    study = args.studie
    settings = session.ndt_pt_settings(study)
    changes = {key: value for key, value in (("step_mm", args.krok), ("tool_mm", args.nastroj),
                                             ("fine_tool_mm", args.jemny),
                                             ("tool_length_mm", args.delka)) if value is not None}
    if args.oplach:
        changes["cleaning"] = "rinse"
    if changes:
        settings = replace(settings, **changes)
        session.set_ndt_pt_settings(study, settings)
    count, step, seconds = session.ndt_pt_estimate(study)
    print(f"Odhad: {count} vzorků při kroku {step:g} mm, asi {seconds:.0f} s.", file=sys.stderr)

    def progress(done: int, total: int) -> None:
        if done == total or done % 200 == 0:
            print(f"Vzorky: {done} z {total}", file=sys.stderr, flush=True)

    result = session.compute_ndt_pt(study, progress=progress)
    print("\n".join(result.summary()))
    if args.csv:
        try:
            print("CSV:", result.write_csv(args.csv))
        except OSError as exc:
            raise ValueError(f"CSV nejde uložit: {exc}") from None
    if args.ulozit:
        print("Model uložen:", session.save())
    return 0


def _mt(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from skodacad.session import ModelSession

    session = ModelSession()
    session.open(args.model)
    study = args.studie
    settings = session.ndt_mt_settings(study)
    changes: dict[str, object] = {
        key: value for key, value in (("spacing_mm", args.roztec),
                                      ("min_spacing_mm", args.nejmensi),
                                      ("step_mm", args.krok),
                                      ("center_step_mm", args.krok_stredu)) if value is not None}
    if args.nejmensi is None and args.roztec is not None:
        changes["min_spacing_mm"] = min(settings.min_spacing_mm, args.roztec)
    if args.feromagneticky:
        changes["ferromagnetic"] = True
    if args.bez_naneseni:
        changes["apply"] = False
    if args.bez_prohlidky:
        changes["inspect"] = False
    if changes:
        try:
            settings = replace(settings, **changes)
        except ValueError as exc:
            raise ValueError(str(exc)) from None
        session.set_ndt_mt_settings(study, settings)
    samples, step, centers, center_step, seconds = session.ndt_mt_estimate(study)
    print(f"Odhad: {samples} míst při kroku {step:g} mm, {centers} středů jha po "
          f"{center_step:g} mm, asi {seconds:.0f} s.", file=sys.stderr)

    def progress(done: int, total: int) -> None:
        if done == total or done % 200 == 0:
            print(f"Výpočet: {done} z {total}", file=sys.stderr, flush=True)

    result = session.compute_ndt_mt(study, progress=progress)
    print("\n".join(result.summary()))
    if args.csv:
        try:
            print("CSV:", result.write_csv(args.csv))
        except OSError as exc:
            raise ValueError(f"CSV nejde uložit: {exc}") from None
    if args.ulozit:
        print("Model uložen:", session.save())
    return 0


def _rt(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from skodacad.session import ModelSession

    session = ModelSession()
    session.open(args.model)
    study = args.studie
    settings = session.ndt_rt_settings(study)
    chosen = args.projekce or [p.name for p in settings.projections]
    for name in chosen:
        settings.projection(name)  # neznámá projekce = česká chyba
    changes: dict[str, object] = {
        key: value for key, value in (("test_class", args.trida), ("focal_mm", args.ohnisko),
                                      ("step_mm", args.krok),
                                      ("image_step_mm", args.krok_nahledu)) if value is not None}
    if args.vzdalenost is not None:

        def moved(p: Any) -> Any:
            if p.name not in chosen:
                return p
            if p.detector_distance_mm is None:
                return replace(p, distance_mm=args.vzdalenost)
            return replace(p, distance_mm=args.vzdalenost, detector_distance_mm=(
                p.detector_distance_mm - p.distance_mm + args.vzdalenost))

        changes["projections"] = tuple(moved(p) for p in settings.projections)
    if changes:
        session.set_ndt_rt_settings(study, replace(settings, **changes))
    samples, step, projections, seconds = session.ndt_rt_estimate(study, args.projekce)
    print(f"Odhad: asi {samples} míst při kroku {step:g} mm, {projections} projekcí, asi "
          f"{seconds:.0f} s.", file=sys.stderr)

    def progress(done: int, total: int) -> None:
        if done == total:
            print(f"Výpočet: {done} z {total}", file=sys.stderr, flush=True)

    result = session.compute_ndt_rt(study, progress=progress, projections=args.projekce)
    print("\n".join(result.summary()))
    if args.csv:
        try:
            print("CSV:", result.write_csv(args.csv))
        except OSError as exc:
            raise ValueError(f"CSV nejde uložit: {exc}") from None
    if args.ulozit:
        print("Model uložen:", session.save())
    return 0


def _audit(args: argparse.Namespace) -> int:
    from skodacad.ndt.audit import duration_text, estimate_seconds
    from skodacad.session import ModelSession

    session = ModelSession()
    session.open(args.model)
    items = session.ndt_audit_items(args.studie, args.navrh_poloh)
    print("Co audit spočítá:", file=sys.stderr)
    for item in items:
        print(f"  {item.text()}", file=sys.stderr)
    print(f"Odhad celkem: {duration_text(estimate_seconds(items))}.", file=sys.stderr,
          flush=True)

    def progress(index: int, total: int, label: str, inner: Any) -> None:
        if inner is None:
            print(f"[{index + 1}/{total}] {label}", file=sys.stderr, flush=True)

    result = session.compute_ndt_audit(args.studie, args.navrh_poloh, args.zpracovatel,
                                       progress=progress)
    print("\n".join(result.summary()))
    if args.slozka:
        for path in session.export_ndt_audit(args.slozka):
            print("Uloženo:", path)
    return 0


def _glue_negative(argv: list[str]) -> list[str]:
    """„--z -150,0,20“ → „--z=-150,0,20“: argparse by zápornou trojici vzal jako volbu."""
    glued: list[str] = []
    items = iter(argv)
    for item in items:
        if item in ("--z", "--smer", "--bod", "--posun", "--plocha", "--cil", "--cil-plocha",
                    "--zona"):
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
        if any(study.method == "UT" for study in result.ndt):
            print(f"  ({UT_DISCLAIMER})")
        if any(study.method == "PT" for study in result.ndt):
            print(f"  ({PT_DISCLAIMER})")
        if any(study.method == "MT" for study in result.ndt):
            print(f"  ({MT_DISCLAIMER})")
        if any(study.method == "RT" for study in result.ndt):
            print(f"  ({RT_DISCLAIMER})")

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
