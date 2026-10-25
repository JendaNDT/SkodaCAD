"""Popis polí každého prvku a tvaru skici – podle něj okno staví formuláře.

Schéma je jediný seznam toho, co který prvek umí. Když přibude nový prvek
v ``features.py``, musí přibýt i sem (hlídá to test), jinak by ho okno
neumělo upravit.

Druhy polí (``Field.kind``):

* ``number`` – číslo nebo výraz s parametry („D/2 + 5“)
* ``choice`` – výběr z možností (``choices``)
* ``sketch`` – odkaz na dřívější skicu
* ``bool`` – ano/ne
* ``faces`` – seznam pojmenovaných ploch dílu (horní, spodní …)
* ``edges`` – sémantický výběr hran (viz ``selectors.select_edges``)
* ``point`` – bod [x, y]
* ``point3`` – bod v prostoru [x, y, z]
* ``features`` – seznam dřívějších prvků, které přidávají či ubírají materiál (pole, zrcadlení)
* ``points`` – seznam bodů [[x, y], …]
* ``points3`` – seznam bodů v prostoru [[x, y, z], …] (trasa tažení)
* ``sketches`` – seznam dřívějších skic v pořadí stromu (přechod)
* ``shapes`` – seznam tvarů skici
* ``profile`` – obrys z úseček a oblouků s vazbami (upravuje se ve skicáři)
* ``text`` – obyčejný text
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from skodacad.features import REPEATABLE_FEATURES
from skodacad.holes import FITS, KINDS, SIZES
from skodacad.selectors import FACE_NAMES_CZ
from skodacad.standards import KINDS as STANDARD_KINDS
from skodacad.standards import SECTIONS

PLANE_CHOICES = (
    ("XY", "XY – vodorovná rovina"),
    ("XZ", "XZ – svislá rovina (zepředu)"),
    ("YZ", "YZ – svislá rovina (zboku)"),
    ("top", "horní plocha dílu"),
    ("bottom", "spodní plocha dílu"),
    ("front", "přední plocha dílu"),
    ("back", "zadní plocha dílu"),
    ("right", "pravá plocha dílu"),
    ("left", "levá plocha dílu"),
)
OPERATION_CHOICES = (
    ("new", "nové těleso"),
    ("add", "přidat materiál"),
    ("cut", "odebrat materiál (řez)"),
)
DIRECTION_CHOICES = (
    ("normal", "ven z roviny"),
    ("reverse", "opačně"),
    ("both", "symetricky na obě strany"),
)
AXIS_CHOICES = (("X", "osa X"), ("Y", "osa Y"), ("Z", "osa Z"))
MODE_CHOICES = (("add", "přidat"), ("subtract", "odečíst (otvor)"))
FACE_CHOICES = tuple((key, f"{label} plocha") for key, label in FACE_NAMES_CZ.items())
HOLE_KIND_CHOICES = tuple(KINDS.items())
HOLE_SIZE_CHOICES = tuple((size, size) for size in SIZES)
HOLE_FIT_CHOICES = tuple(zip(FITS, ("jemná", "střední", "hrubá"), strict=True))
PATTERN_KIND_CHOICES = (("circular", "kruhové – dokola kolem osy"),
                        ("linear", "lineární – v řadě nebo mřížka"))
SWEEP_PROFILE_CHOICES = (("circle", "kruh / trubka"), ("rectangle", "obdélník / jekl"),
                         ("steel", "ocelový profil podle tabulek"),
                         ("sketch", "tvar ze skici"))
SECTION_CHOICES = tuple(SECTIONS.items())
STANDARD_KIND_CHOICES = tuple((key, kind.label) for key, kind in STANDARD_KINDS.items())
STANDARD_DIRECTION_CHOICES = (("normal", "jak sedí na ploše"),
                              ("reverse", "otočit do materiálu (kapsa)"))
_LENGTH_KINDS = tuple(key for key, kind in STANDARD_KINDS.items() if kind.length)


def _standard_sizes(*kinds: str) -> Field:
    """Seznam velikostí pro jeden či více druhů normalizovaného dílu (se stejnou tabulkou)."""
    return Field("size", "Velikost", "choice",
                 choices=tuple(STANDARD_KINDS[kinds[0]].sizes.items()),
                 when=("kind", kinds if len(kinds) > 1 else kinds[0]))


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str
    required: bool = True
    choices: tuple[tuple[str, str], ...] = ()
    help: str = ""
    default: Any = None  # co jádro použije, když hodnota chybí (ukáže se ve formuláři)
    min_count: int = 1  # u „points“, „points3“, „sketches“: nejmenší počet
    # pole se ukáže, jen když má jiné pole tuto hodnotu (nebo jednu z n-tice hodnot)
    when: tuple[str, Any] = ()


def field_shown(field: Field, data: dict[str, Any], defaults: dict[str, Any]) -> bool:
    """Patří pole k aktuální volbě? (``when`` – např. průměr jen u kruhového profilu.)"""
    if not field.when:
        return True
    key, wanted = field.when
    value = data.get(key, defaults.get(key))
    return value in wanted if isinstance(wanted, tuple) else value == wanted


@dataclass(frozen=True)
class Schema:
    type: str
    label: str
    fields: tuple[Field, ...]
    help: str = ""
    # Nabídka „Přidat prvek“: přímé úpravy ploch vznikají jen výběrem plochy ve 3D (P2.4).
    menu: bool = True


_NAME = Field("name", "Název", "text", required=False)

FEATURE_SCHEMAS: dict[str, Schema] = {
    schema.type: schema
    for schema in (
        Schema("sketch", "Skica", (
            _NAME,
            Field("plane", "Rovina", "choice", choices=PLANE_CHOICES),
            Field("offset", "Posun roviny [mm]", "number", required=False),
            Field("elements", "Tvary", "shapes"),
        ), "2D tvary na rovině nebo na ploše dílu."),
        Schema("extrude", "Vysunutí", (
            _NAME,
            Field("sketch", "Skica", "sketch"),
            Field("operation", "Operace", "choice", required=False, choices=OPERATION_CHOICES,
                  help="Bez volby: první těleso nové, další přidávají materiál."),
            Field("distance", "Vzdálenost [mm]", "number", required=False,
                  help="Nepovinné jen při řezu skrz celý díl."),
            Field("direction", "Směr", "choice", required=False, choices=DIRECTION_CHOICES,
                  help="Bez volby: ven, u řezu do materiálu."),
            Field("through_all", "Řez skrz celý díl", "bool", required=False),
        ), "Vytáhne skicu do prostoru."),
        Schema("revolve", "Rotace", (
            _NAME,
            Field("sketch", "Skica", "sketch"),
            Field("axis", "Osa rotace", "choice", choices=AXIS_CHOICES, default="Z"),
            Field("angle", "Úhel [°]", "number", required=False),
            Field("operation", "Operace", "choice", required=False, choices=OPERATION_CHOICES),
        ), "Orotuje skicu kolem osy (skica musí ležet v rovině s osou)."),
        Schema("sweep", "Tažení", (
            _NAME,
            Field("path", "Trasa – body [x; y; z]", "points3", min_count=2,
                  help="Jeden bod na řádek ve tvaru  x; y; z  (i s parametry). Profil se "
                       "táhne od prvního bodu k poslednímu."),
            Field("bend_radius", "Poloměr ohybu [mm]", "number", required=False,
                  help="Zaoblení v rozích trasy jako u ohýbané trubky. Prázdné nebo 0 = "
                       "ostrý roh, spoj na pokos (rám z jeklu)."),
            Field("profile", "Profil", "choice", choices=SWEEP_PROFILE_CHOICES,
                  default="circle"),
            Field("diameter", "Průměr [mm]", "number", required=False,
                  when=("profile", "circle")),
            Field("width", "Šířka [mm]", "number", required=False,
                  help="Vodorovně (u svislého začátku trasy podél osy X).",
                  when=("profile", "rectangle")),
            Field("height", "Výška [mm]", "number", required=False,
                  when=("profile", "rectangle")),
            Field("wall", "Tloušťka stěny [mm]", "number", required=False,
                  help="Dutá trubka nebo jekl. Prázdné = plný profil.",
                  when=("profile", ("circle", "rectangle"))),
            Field("section", "Profil podle tabulek", "choice", required=False,
                  choices=SECTION_CHOICES, default="IPE 100",
                  help="Ocelový profil (IPE, U, L, jekl, trubka) – stojí na výšku, střed "
                       "obalového obdélníku v prvním bodě trasy.", when=("profile", "steel")),
            Field("sketch", "Skica profilu", "sketch", required=False,
                  help="Tvar skici se postaví kolmo na začátek trasy, počátek skici do "
                       "prvního bodu.", when=("profile", "sketch")),
            Field("operation", "Operace", "choice", required=False, choices=OPERATION_CHOICES),
        ), "Profil tažený po trase z bodů s ohyby – trubky, kolena, madla, rámy."),
        Schema("loft", "Přechod", (
            _NAME,
            Field("sketches", "Skici v pořadí", "sketches", min_count=2,
                  help="Zaškrtni aspoň dvě skici – přechod jde v pořadí stromu."),
            Field("ruled", "Rovné stěny (bez zaoblení mezi skicami)", "bool", required=False),
            Field("wall", "Tloušťka stěny [mm]", "number", required=False,
                  help="Dutý přechod s otevřenými konci (plech). Stěna je kolmá k povrchu; "
                       "u přechodu kruh ↔ hranatý tvar se měří v rovinách skic."),
            Field("operation", "Operace", "choice", required=False, choices=OPERATION_CHOICES),
        ), "Plynulý přechod mezi skicami – výsypka, redukce, násypka."),
        Schema("standard", "Normalizovaný díl", (
            _NAME,
            Field("kind", "Druh", "choice", choices=STANDARD_KIND_CHOICES,
                  default="socket_screw"),
            _standard_sizes("socket_screw", "hex_screw", "nut", "washer"),
            _standard_sizes("countersunk_screw"),
            _standard_sizes("bearing"),
            _standard_sizes("pin"),
            _standard_sizes("key"),
            _standard_sizes("profile"),
            Field("length", "Délka [mm]", "number", when=("kind", _LENGTH_KINDS),
                  help="Šroub s válcovou či šestihrannou hlavou: dřík pod hlavou; zápustný "
                       "šroub: celková délka i s hlavou; kolík, pero, tyč: celá délka."),
            Field("plane", "Rovina", "choice", choices=PLANE_CHOICES),
            Field("offset", "Posun roviny [mm]", "number", required=False),
            Field("positions", "Polohy [x; y]", "points",
                  help="Jedna poloha na řádek ve tvaru  x; y  (souřadnice jako ve skice)."),
            Field("angle", "Natočení kolem osy [°]", "number", required=False,
                  help="Natočí šestihran, pero (délka jde podél osy X skici) nebo profil."),
            Field("direction", "Směr", "choice", required=False,
                  choices=STANDARD_DIRECTION_CHOICES, default="normal",
                  help="Šroub má hlavu nad plochou a dřík v materiálu, matice, podložka, "
                       "ložisko, kolík a tyč leží na ploše. Pro kapsu je otoč do materiálu."),
            Field("operation", "Operace", "choice", required=False, choices=OPERATION_CHOICES),
            Field("clearance", "Vůle kapsy [mm]", "number", required=False,
                  help="O kolik je kapsa větší na každou stranu (3D tisk: 0,1–0,2 mm).",
                  when=("operation", "cut")),
        ), "Šroub, matice, podložka, ložisko, kolík, pero nebo tyč z ocelového profilu podle "
           "tabulek. Odebráním vznikne kapsa (třeba na matici pro 3D tisk)."),
        Schema("fillet", "Zaoblení", (
            _NAME,
            Field("edges", "Hrany", "edges"),
            Field("radius", "Poloměr [mm]", "number"),
        ), "Zaoblí vybrané hrany."),
        Schema("chamfer", "Sražení", (
            _NAME,
            Field("edges", "Hrany", "edges"),
            Field("distance", "Velikost [mm]", "number"),
        ), "Srazí vybrané hrany."),
        Schema("hole", "Díra", (
            _NAME,
            Field("kind", "Druh", "choice", choices=HOLE_KIND_CHOICES, default="tapped"),
            Field("size", "Velikost", "choice", choices=HOLE_SIZE_CHOICES),
            Field("fit", "Řada průchozí díry", "choice", required=False,
                  choices=HOLE_FIT_CHOICES, default="medium",
                  help="ISO 273 – pro průchozí díry a zahloubení."),
            Field("plane", "Rovina", "choice", choices=PLANE_CHOICES),
            Field("offset", "Posun roviny [mm]", "number", required=False),
            Field("positions", "Středy děr [x; y]", "points",
                  help="Jeden střed na řádek ve tvaru  x; y  (souřadnice jako ve skice)."),
            Field("depth", "Hloubka [mm]", "number", required=False,
                  help="Bez hodnoty: 2× průměr závitu (zálisná matice 2× průměr + 1)."),
            Field("through_all", "Skrz celý díl", "bool", required=False),
            Field("thread_depth", "Hloubka závitu [mm]", "number", required=False,
                  help="Jen závitová díra. Bez hodnoty: 1,5× průměr závitu "
                       "(vymodelovaný závit po celé hloubce díry)."),
            Field("modeled_thread", "Vymodelovat závit (3D tisk)", "bool", required=False,
                  help="Skutečná šroubovice podle ISO 68-1 místo vyznačeného závitu – pro "
                       "tisk doporučeno od M6. Přepočet trvá déle."),
            Field("print_clearance", "Vůle závitu pro tisk [mm]", "number", required=False,
                  help="Jen vymodelovaný závit: o kolik je závit větší než šroub "
                       "(na průměru). Bez hodnoty 0,2 mm."),
            Field("diameter", "Vlastní průměr [mm]", "number", required=False,
                  help="Přepíše průměr z tabulky (např. podle zkušebního tisku)."),
        ), "Díra podle strojnických tabulek – závit vyznačený, pro 3D tisk i vymodelovaný."),
        Schema("shell", "Skořepina", (
            _NAME,
            Field("thickness", "Tloušťka stěny [mm]", "number"),
            Field("open_faces", "Otevřené plochy", "faces", required=False),
        ), "Vydlabe díl na danou tloušťku stěny."),
        Schema("move_face", "Posunutí plochy", (
            _NAME,
            Field("face", "Plocha", "face",
                  help="Rovinná plocha vybraná ve 3D (bod a směr)."),
            Field("origin", "Původ plochy", "origin",
                  help="Prvek, kterým plocha vznikla – pojistka proti záměně plochy."),
            Field("distance", "Posun [mm]", "number",
                  help="+ ven z materiálu (přidá), − dovnitř (ubere). Sousední plochy se "
                       "jen prodlouží nebo zkrátí."),
        ), "Posune rovinnou plochu kolmo k ní – bez hledání prvku, který ji vytvořil.",
            menu=False),
        Schema("face_diameter", "Průměr plochy", (
            _NAME,
            Field("face", "Plocha", "face",
                  help="Válcová plocha (díra nebo čep) vybraná ve 3D."),
            Field("origin", "Původ plochy", "origin",
                  help="Prvek, kterým plocha vznikla – pojistka proti záměně plochy."),
            Field("diameter", "Nový průměr [mm]", "number", help="Osa zůstane na místě."),
        ), "Změní průměr díry nebo čepu.", menu=False),
        Schema("pattern", "Pole", (
            _NAME,
            Field("features", "Opakované prvky", "features",
                  help="Prvky, které se zopakují (díra, výřez, výstupek …)."),
            Field("kind", "Druh pole", "choice", choices=PATTERN_KIND_CHOICES,
                  default="circular"),
            Field("count", "Počet kusů", "number",
                  help="Včetně původního prvku (6 = původní + 5 kopií)."),
            Field("axis", "Osa", "choice", required=False, choices=AXIS_CHOICES, default="Z",
                  when=("kind", "circular")),
            Field("center", "Bod na ose", "point3", required=False,
                  help="Kterým bodem [x, y, z] osa prochází. Bez hodnoty počátek.",
                  when=("kind", "circular")),
            Field("angle", "Celkový úhel [°]", "number", required=False,
                  help="Bez hodnoty 360° = rovnoměrně dokola. Menší úhel: první a poslední "
                       "kus leží na krajích úhlu.", when=("kind", "circular")),
            Field("direction", "Směr", "choice", required=False, choices=AXIS_CHOICES,
                  default="X", when=("kind", "linear")),
            Field("spacing", "Rozteč [mm]", "number", required=False,
                  help="Vzdálenost sousedních kusů. Záporná = opačným směrem.",
                  when=("kind", "linear")),
            Field("direction2", "Druhý směr (mřížka)", "choice", required=False,
                  choices=AXIS_CHOICES, help="Bez volby jen jedna řada.",
                  when=("kind", "linear")),
            Field("count2", "Počet ve druhém směru", "number", required=False,
                  when=("kind", "linear")),
            Field("spacing2", "Rozteč ve druhém směru [mm]", "number", required=False,
                  when=("kind", "linear")),
        ), "Zopakuje vybrané prvky dokola, v řadě nebo v mřížce. Kopie se přepočítají "
           "s původním prvkem."),
        Schema("mirror", "Zrcadlení", (
            _NAME,
            Field("features", "Zrcadlené prvky", "features", required=False,
                  help="Nic nezaškrtnuto = zrcadlí se celý díl."),
            Field("plane", "Rovina zrcadlení", "choice", choices=PLANE_CHOICES),
            Field("offset", "Posun roviny [mm]", "number", required=False),
        ), "Zrcadlí vybrané prvky podle roviny. Bez vybraných prvků zrcadlí celý díl "
           "(namodeluješ polovinu, druhou dopočítá)."),
    )
}

_COMMON_SHAPE_FIELDS = (
    Field("mode", "Režim", "choice", choices=MODE_CHOICES, default="add"),
    Field("center", "Střed [x, y]", "point", required=False),
    Field("angle", "Natočení [°]", "number", required=False),
)

SHAPE_SCHEMAS: dict[str, Schema] = {
    schema.type: schema
    for schema in (
        Schema("rectangle", "Obdélník", (
            Field("width", "Šířka [mm]", "number"),
            Field("height", "Výška [mm]", "number"),
            Field("corner_radius", "Zaoblení rohů [mm]", "number", required=False),
            *_COMMON_SHAPE_FIELDS,
        )),
        Schema("circle", "Kružnice", (
            Field("diameter", "Průměr [mm]", "number"),
            *_COMMON_SHAPE_FIELDS,
        )),
        Schema("circle_pattern", "Díry na roztečné kružnici", (
            Field("count", "Počet", "number"),
            Field("pitch_diameter", "Roztečný průměr [mm]", "number"),
            Field("diameter", "Průměr děr [mm]", "number"),
            Field("start_angle", "Počáteční úhel [°]", "number", required=False),
            *_COMMON_SHAPE_FIELDS,
        )),
        Schema("regular_polygon", "Pravidelný mnohoúhelník", (
            Field("sides", "Počet stran", "number"),
            Field("diameter", "Opsaný průměr [mm]", "number"),
            *_COMMON_SHAPE_FIELDS,
        )),
        Schema("slot", "Drážka", (
            Field("length", "Rozteč středů [mm]", "number"),
            Field("width", "Šířka [mm]", "number"),
            *_COMMON_SHAPE_FIELDS,
        )),
        Schema("polygon", "Mnohoúhelník z bodů", (
            Field("points", "Body", "points", min_count=3),
            *_COMMON_SHAPE_FIELDS,
        )),
        Schema("steel", "Ocelový profil", (
            Field("section", "Profil", "choice", choices=SECTION_CHOICES),
            *_COMMON_SHAPE_FIELDS,
        ), "Průřez podle tabulek (IPE, U, L, jekl, trubka), střed obalového obdélníku "
           "v bodě středu."),
        Schema("profile", "Obrys z čar (s vazbami)", (
            Field("segments", "Obrys", "profile"),
            *_COMMON_SHAPE_FIELDS,
        ), "Úsečky a oblouky, vazby a kóty – upravuje se ve skicáři."),
    )
}


def _rectangle_profile(width: float, height: float) -> dict[str, Any]:
    """Obdélníkový obrys s rohem v počátku, plně určený vazbami – výchozí bod pro skicář."""
    points = {"A": [0, 0], "B": [width, 0], "C": [width, height], "D": [0, height]}
    names = list(points)
    segments = {f"s{i + 1}": {"type": "line", "start": names[i], "end": names[(i + 1) % 4]}
                for i in range(4)}
    constraints = [
        {"type": "coincident", "point": "A", "on": "origin"},
        {"type": "horizontal", "segment": "s1"},
        {"type": "vertical", "segment": "s2"},
        {"type": "horizontal", "segment": "s3"},
        {"type": "vertical", "segment": "s4"},
        {"type": "length", "segment": "s1", "value": width},
        {"type": "length", "segment": "s2", "value": height},
    ]
    return {"shape": "profile", "points": points, "segments": segments,
            "constraints": constraints}

# Výchozí tvary pro nové skici a nově přidané tvary.
SHAPE_DEFAULTS: dict[str, dict[str, Any]] = {
    "rectangle": {"shape": "rectangle", "width": 40, "height": 30},
    "circle": {"shape": "circle", "diameter": 20},
    "circle_pattern": {"shape": "circle_pattern", "count": 4, "pitch_diameter": 40,
                       "diameter": 6},
    "regular_polygon": {"shape": "regular_polygon", "sides": 6, "diameter": 20},
    "slot": {"shape": "slot", "length": 20, "width": 6},
    "polygon": {"shape": "polygon", "points": [[0, 0], [30, 0], [0, 20]]},
    "steel": {"shape": "steel", "section": "IPE 100"},
    "profile": _rectangle_profile(40, 30),
}


def new_shape(shape_type: str) -> dict[str, Any]:
    return copy.deepcopy(SHAPE_DEFAULTS[shape_type])


def new_feature(feature_type: str, existing: list[dict[str, Any]],
                index: int | None = None) -> dict[str, Any]:
    """Nový prvek s rozumnými výchozími hodnotami a jedinečným id.

    ``existing`` je seznam prvků modelu, ``index`` místo, kam se prvek vloží
    (výchozí: na konec). Podle prvků před ním se volí třeba skica pro vysunutí.
    """
    schema = FEATURE_SCHEMAS[feature_type]
    before = existing if index is None else existing[:index]
    has_solid = any(f.get("type") in ("extrude", "revolve", "sweep", "loft", "standard")
                    for f in before)
    sketches = [f["id"] for f in before if f.get("type") == "sketch"]

    ids = {f.get("id") for f in existing}
    number = 1 + sum(1 for f in existing if f.get("type") == feature_type)
    while f"{feature_type}{number}" in ids:
        number += 1
    feature: dict[str, Any] = {
        "id": f"{feature_type}{number}",
        "name": f"{schema.label} {number}",
        "type": feature_type,
    }

    if feature_type == "sketch":
        # Na ploše hotového dílu spíš otvor/výstupek než obdélník přes celý díl.
        shape = new_shape("circle") if has_solid else new_shape("rectangle")
        if has_solid:
            shape["diameter"] = 10
        feature.update(plane="top" if has_solid else "XY", elements=[shape])
    elif feature_type == "extrude":
        if sketches:
            feature["sketch"] = sketches[-1]
        feature["distance"] = 10
    elif feature_type == "revolve":
        if sketches:
            feature["sketch"] = sketches[-1]
        feature["axis"] = "Z"
    elif feature_type == "sweep":  # trubkové koleno 90°
        # šířka a výška jsou skryté, dokud se nepřepne na jekl – pak hned něco ukáže
        feature.update(path=[[0, 0, 0], [0, 0, 100], [100, 0, 100]], bend_radius=40,
                       profile="circle", diameter=30, width=40, height=20, wall=2)
    elif feature_type == "loft":
        feature["sketches"] = sketches[-2:]  # dvě poslední skici (třeba dole a nahoře)
    elif feature_type == "standard":  # imbus M6 × 20 na ploše dílu (bez dílu samostatně)
        feature.update(kind="socket_screw", size="M6", length=20,
                       plane="top" if has_solid else "XY", positions=[[0, 0]])
    elif feature_type == "fillet":
        feature.update(edges={"face": "top"}, radius=2)
    elif feature_type == "chamfer":
        feature.update(edges={"face": "top"}, distance=1)
    elif feature_type == "shell":
        feature.update(thickness=2, open_faces=["top"])
    elif feature_type == "move_face":  # plochu a původ doplní až výběr ve 3D
        feature["distance"] = 1
    elif feature_type == "face_diameter":
        feature["diameter"] = 10
    elif feature_type == "hole":
        feature.update(kind="tapped", size="M6", plane="top" if has_solid else "XY",
                       positions=[[0, 0]])
    elif feature_type in ("pattern", "mirror"):
        # Opakuje se prvek těsně před novým (ten vybraný ve stromu), ne ale základní těleso.
        repeatable = [f["id"] for f in before if f.get("type") in REPEATABLE_FEATURES]
        source = repeatable[1:][-1:]
        if feature_type == "pattern":
            feature.update(features=source, kind="linear", count=3, direction="X", spacing=10)
        elif source:
            feature.update(features=source, plane="YZ")
        else:
            feature["plane"] = "right"  # celý díl k sobě – funguje na každém dílu
    return feature
