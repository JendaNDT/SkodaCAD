"""Sestava: soubor, který skládá díly a podsestavy do poloh – formát 29.

Příklad::

    {
      "format": "skodacad", "kind": "assembly", "version": 29,
      "name": "Krabička s víčkem", "units": "mm", "parameters": {"H": 30},
      "components": [
        {"id": "krabicka", "source": {"path": "../krabicka.json"},
         "placement": {"position": [0, 0, 0], "rotation": [0, 0, 0]}, "fixed": true},
        {"id": "vicko", "source": {"path": "dily/vicko.json"},
         "placement": {"position": [0, 0, "H + 2"], "rotation": [180, 0, 0]}}
      ]
    }

Komponenty na soubory dílů jen odkazují – cestou vůči složce souboru sestavy – a sestava
je nikdy nepřepisuje. Poloha je posun v mm a úhly ve stupních kolem pevných os sestavy:
nejdřív X, pak Y, pak Z. Rozhodnutí S1–S12: ``docs/p5-1-navrh-formatu-sestav.md``.

Vazby (formát 30, rozhodnutí M1–M12 v ``docs/p5-3-navrh-vazeb.md``) spojují plochy dvou
komponent: dotyk (``mate``), zarovnání (``flush``), vzdálenost (``distance``, hodnota v mm)
a souosost (``coaxial``). Odkaz je plocha významem v souřadnicích dílu komponenty
(``{"component": "vicko", "face": {"at": [...], "normal": [...], "type": "plane"}}``) nebo
základní rovina či osa dílu (``{"component": "noha", "plane": "XY"}``, ``"axis": "Z"``).
Sestava bez vazeb se ukládá ve verzi 29, s vazbami ve verzi 30.

Kontroly (formát 31, rozhodnutí K1–K12 v ``docs/p5-4-navrh-kontrol.md``): nepovinné
``checks`` s mezí vůle (``clearance``, mm) a přijatými kolizemi (``accepted``: dvojice
komponent jako cesty id, objem průniku při přijetí a poznámka). Výsledky kontrol se
neukládají – jsou pohled.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skodacad.document import ASSEMBLY_KIND, FORMAT, DocumentError, write_json

FIRST_VERSION = 29  # první verze formátu, která zná sestavy
VERSION = 31  # kontroly (checks); vazby (constraints) od verze 30
CONSTRAINTS_VERSION = 30
DEFAULT_CLEARANCE = 0.5  # mm, výchozí mez vůle (K2, zvoleno)
MAX_DEPTH = 8  # úrovní podsestav (S10, zvoleno)
MAX_COMPONENTS = 1000  # komponent po rozbalení podsestav (S10, zvoleno)

_TOP_KEYS = {"format", "kind", "version", "name", "description", "units", "parameters",
             "components", "constraints", "checks"}
_CHECK_KEYS = {"clearance", "accepted"}
_ACCEPTED_KEYS = {"a", "b", "volume", "note"}
_COMPONENT_KEYS = {"id", "name", "source", "placement", "fixed"}
_SOURCE_KEYS = {"path", "fingerprint"}
_PLACEMENT_KEYS = {"position", "rotation"}
_FINGERPRINT = re.compile(r"[0-9a-f]{16}")

CONSTRAINT_TYPES = {"mate": "dotyk", "flush": "zarovnání", "distance": "vzdálenost",
                    "coaxial": "souosost"}
PLANAR_TYPES = ("mate", "flush", "distance")  # vážou dvě roviny
BASE_PLANES = {"XY": ((0, 0, 0), (0, 0, 1)), "XZ": ((0, 0, 0), (0, -1, 0)),
               "YZ": ((0, 0, 0), (1, 0, 0))}  # normály jako u skic (XZ míří do −Y)
BASE_AXES = {"X": ((0, 0, 0), (1, 0, 0)), "Y": ((0, 0, 0), (0, 1, 0)),
             "Z": ((0, 0, 0), (0, 0, 1))}
_CONSTRAINT_KEYS = {"id", "type", "name", "a", "b", "value"}
_REFERENCE_KEYS = {"component", "face", "plane", "axis"}
_FACE_KEYS = {"at", "normal", "type"}


class AssemblyError(DocumentError):
    """Sestava má chybnou strukturu nebo úpravu nejde provést (zpráva je česky)."""


def check_path(text: Any) -> str:
    """Cesta ke zdroji (S4): relativní vůči složce sestavy, oddělovač „/“, „..“ jen na
    začátku. Každý soubor má tak jediný zápis a složka jde přenést na jiný disk i systém."""
    if not isinstance(text, str) or not text:
        raise AssemblyError("Cesta k souboru komponenty chybí.")
    if "\\" in text:
        raise AssemblyError(f"Cesta „{text}“ obsahuje „\\“ – v sestavě se píše „/“.")
    if text.startswith("/") or ":" in text:
        raise AssemblyError(f"Cesta „{text}“ musí být vůči složce sestavy, ne celá cesta "
                            "na disku (bez „/“ na začátku a bez písmene disku).")
    parts = text.split("/")
    if any(part in ("", ".") for part in parts):
        raise AssemblyError(f"Cesta „{text}“ má prázdnou část nebo „.“ – zapiš ji bez nich.")
    leading = 0
    while leading < len(parts) and parts[leading] == "..":
        leading += 1
    if leading == len(parts) or ".." in parts[leading:]:
        raise AssemblyError(f"Cesta „{text}“ smí mít „..“ jen na začátku a musí končit "
                            "názvem souboru.")
    return text


def _value(value: Any, where: str) -> Any:
    """Číslo nebo výraz s parametry sestavy (výraz se vyhodnotí až při sestavení)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise AssemblyError(f"{where}: hodnota musí být číslo nebo výraz.")
    if isinstance(value, float) and not math.isfinite(value):
        raise AssemblyError(f"{where}: hodnota musí být konečné číslo.")
    if isinstance(value, str) and not value.strip():
        raise AssemblyError(f"{where}: výraz je prázdný.")
    return value


def _triple(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list) or len(value) != 3:
        raise AssemblyError(f"{where} musí být trojice [x, y, z].")
    return [_value(item, where) for item in value]


def _unknown(data: dict[str, Any], allowed: set[str], where: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise AssemblyError(f"{where}: neznámý klíč {', '.join(f'„{k}“' for k in extra)} "
                            "(překlep, nebo soubor z novější verze ŠkodaCAD).")


def _vector(value: Any, where: str) -> list[float]:
    if (not isinstance(value, list) or len(value) != 3
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value)
            or not all(math.isfinite(v) for v in value)):
        raise AssemblyError(f"{where} musí být trojice čísel [x, y, z].")
    return list(value)


def check_reference(data: Any, where: str) -> dict[str, Any]:
    """Odkaz vazby (M2): komponenta a právě jedno z plocha / rovina dílu / osa dílu."""
    if not isinstance(data, dict):
        raise AssemblyError(f"{where} musí být objekt s „component“ a plochou, rovinou "
                            "nebo osou.")
    _unknown(data, _REFERENCE_KEYS, where)
    component = data.get("component")
    if not isinstance(component, str) or not component:
        raise AssemblyError(f"{where}: chybí textové „component“ (id komponenty).")
    kinds = [key for key in ("face", "plane", "axis") if key in data]
    if len(kinds) != 1:
        raise AssemblyError(f"{where}: uveď právě jedno z „face“, „plane“ nebo „axis“.")
    if "face" in data:
        face = data["face"]
        if not isinstance(face, dict):
            raise AssemblyError(f"{where}: „face“ musí být objekt s „at“, „normal“ a „type“.")
        _unknown(face, _FACE_KEYS, f"{where}, plocha")
        for key in _FACE_KEYS:
            if key not in face:
                raise AssemblyError(f"{where}: plocha potřebuje „at“, „normal“ i „type“.")
        _vector(face["at"], f"{where}: „at“")
        if not any(_vector(face["normal"], f"{where}: „normal“")):
            raise AssemblyError(f"{where}: „normal“ nesmí být nulový směr.")
        if face["type"] not in ("plane", "cylinder"):
            raise AssemblyError(f"{where}: vazby umí jen plochy „plane“ (rovinné) a "
                                "„cylinder“ (válcové).")
    elif "plane" in data:
        if data["plane"] not in tuple(BASE_PLANES):
            raise AssemblyError(f"{where}: rovina dílu musí být jedna z "
                                f"{', '.join(BASE_PLANES)}.")
    elif data["axis"] not in tuple(BASE_AXES):
        raise AssemblyError(f"{where}: osa dílu musí být jedna z {', '.join(BASE_AXES)}.")
    return copy.deepcopy(data)


def reference_shape(data: dict[str, Any]) -> str:
    """Co odkaz určuje: „plane“ (rovina) nebo „axis“ (osa)."""
    if "face" in data:
        return "plane" if data["face"]["type"] == "plane" else "axis"
    return "plane" if "plane" in data else "axis"


@dataclass
class Constraint:
    """Vazba mezi plochami dvou komponent (M1, M10)."""

    id: str
    type: str
    a: dict[str, Any]
    b: dict[str, Any]
    value: Any = None  # jen u vzdálenosti: mm, číslo nebo výraz s parametry sestavy
    name: str = ""

    @property
    def label(self) -> str:
        return self.name or f"{self.id} ({CONSTRAINT_TYPES[self.type]})"

    @property
    def components(self) -> tuple[str, str]:
        return self.a["component"], self.b["component"]

    @classmethod
    def from_dict(cls, data: Any, index: int) -> Constraint:
        if not isinstance(data, dict):
            raise AssemblyError(f"Vazba č. {index} musí být objekt.")
        constraint_id = data.get("id")
        if not isinstance(constraint_id, str) or not constraint_id:
            raise AssemblyError(f"Vazba č. {index} nemá textové „id“.")
        where = f"Vazba „{constraint_id}“"
        _unknown(data, _CONSTRAINT_KEYS, where)
        kind = data.get("type")
        if kind not in tuple(CONSTRAINT_TYPES):
            raise AssemblyError(f"{where}: neznámý druh „{kind}“, povolené: "
                                + ", ".join(f"{k} ({v})" for k, v in CONSTRAINT_TYPES.items())
                                + ".")
        name = data.get("name", "")
        if not isinstance(name, str):
            raise AssemblyError(f"{where}: „name“ musí být text.")
        a = check_reference(data.get("a"), f"{where}, „a“")
        b = check_reference(data.get("b"), f"{where}, „b“")
        if a["component"] == b["component"]:
            raise AssemblyError(f"{where}: vazba musí spojovat dvě různé komponenty.")
        wanted = "plane" if kind in PLANAR_TYPES else "axis"
        for side in (a, b):
            if reference_shape(side) != wanted:
                raise AssemblyError(
                    f"{where} ({CONSTRAINT_TYPES[kind]}) potřebuje "
                    + ("dvě rovinné plochy nebo roviny dílu." if wanted == "plane"
                       else "dvě válcové plochy nebo osy dílu."))
        value = None
        if kind == "distance":
            if "value" not in data:
                raise AssemblyError(f"{where}: vzdálenost potřebuje hodnotu „value“ v mm.")
            value = _value(data["value"], f"{where}, hodnota")
        elif "value" in data:
            raise AssemblyError(f"{where}: hodnotu „value“ má jen vzdálenost.")
        return cls(id=constraint_id, type=kind, a=a, b=b, value=value, name=name)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "type": self.type}
        if self.name:
            data["name"] = self.name
        if self.type == "distance":
            data["value"] = copy.deepcopy(self.value)
        data["a"] = copy.deepcopy(self.a)
        data["b"] = copy.deepcopy(self.b)
        return data


@dataclass
class Component:
    """Jedno vložení dílu nebo podsestavy do sestavy."""

    id: str
    path: str
    position: list[Any] = field(default_factory=lambda: [0, 0, 0])
    rotation: list[Any] = field(default_factory=lambda: [0, 0, 0])
    name: str = ""
    fingerprint: str = ""  # otisk receptu zdroje při posledním uložení (jen informace, S5)
    fixed: bool = False

    @property
    def label(self) -> str:
        return self.name or self.id

    @classmethod
    def from_dict(cls, data: Any, index: int) -> Component:
        if not isinstance(data, dict):
            raise AssemblyError(f"Komponenta č. {index} musí být objekt.")
        component_id = data.get("id")
        if not isinstance(component_id, str) or not component_id:
            raise AssemblyError(f"Komponenta č. {index} nemá textové „id“.")
        where = f"Komponenta „{component_id}“"
        _unknown(data, _COMPONENT_KEYS, where)
        name = data.get("name", "")
        if not isinstance(name, str):
            raise AssemblyError(f"{where}: „name“ musí být text.")
        source = data.get("source")
        if not isinstance(source, dict):
            raise AssemblyError(f"{where}: chybí „source“ s cestou k souboru dílu.")
        _unknown(source, _SOURCE_KEYS, f"{where}, zdroj")
        try:
            path = check_path(source.get("path"))
        except AssemblyError as exc:
            raise AssemblyError(f"{where}: {exc}") from None
        fingerprint = source.get("fingerprint", "")
        if fingerprint and (not isinstance(fingerprint, str)
                            or not _FINGERPRINT.fullmatch(fingerprint)):
            raise AssemblyError(f"{where}: otisk zdroje musí být 16 znaků 0–9 a a–f.")
        placement = data.get("placement", {})
        if not isinstance(placement, dict):
            raise AssemblyError(f"{where}: „placement“ musí být objekt.")
        _unknown(placement, _PLACEMENT_KEYS, f"{where}, poloha")
        fixed = data.get("fixed", False)
        if not isinstance(fixed, bool):
            raise AssemblyError(f"{where}: „fixed“ musí být true nebo false.")
        return cls(
            id=component_id,
            path=path,
            position=_triple(placement.get("position", [0, 0, 0]), f"{where}, posun"),
            rotation=_triple(placement.get("rotation", [0, 0, 0]), f"{where}, otočení"),
            name=name,
            fingerprint=fingerprint,
            fixed=fixed,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id}
        if self.name:
            data["name"] = self.name
        source: dict[str, Any] = {"path": self.path}
        if self.fingerprint:
            source["fingerprint"] = self.fingerprint
        data["source"] = source
        data["placement"] = {"position": copy.deepcopy(self.position),
                             "rotation": copy.deepcopy(self.rotation)}
        if self.fixed:
            data["fixed"] = True
        return data


def _ids(value: Any, where: str) -> list[str]:
    if (not isinstance(value, list) or not value
            or any(not isinstance(item, str) or not item for item in value)):
        raise AssemblyError(f"{where} musí být cesta id komponent, např. [\"sroub_1\"].")
    return list(value)


@dataclass
class Accepted:
    """Přijatá kolize (K3): dvojice komponent, objem průniku při přijetí a poznámka."""

    a: list[str]
    b: list[str]
    volume: float
    note: str = ""

    @property
    def key(self) -> frozenset[tuple[str, ...]]:
        return frozenset((tuple(self.a), tuple(self.b)))

    @classmethod
    def from_dict(cls, data: Any, index: int) -> Accepted:
        where = f"Přijatá kolize č. {index}"
        if not isinstance(data, dict):
            raise AssemblyError(f"{where} musí být objekt.")
        _unknown(data, _ACCEPTED_KEYS, where)
        a = _ids(data.get("a"), f"{where}, „a“")
        b = _ids(data.get("b"), f"{where}, „b“")
        if a == b:
            raise AssemblyError(f"{where}: kolize musí být mezi dvěma různými komponentami.")
        volume = data.get("volume")
        if (isinstance(volume, bool) or not isinstance(volume, (int, float))
                or not math.isfinite(volume) or volume < 0):
            raise AssemblyError(f"{where}: „volume“ musí být nezáporný objem v mm³.")
        note = data.get("note", "")
        if not isinstance(note, str):
            raise AssemblyError(f"{where}: „note“ musí být text.")
        return cls(a=a, b=b, volume=volume, note=note)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"a": list(self.a), "b": list(self.b), "volume": self.volume}
        if self.note:
            data["note"] = self.note
        return data


@dataclass
class Checks:
    """Nastavení kontrol sestavy (K4): mez vůle a přijaté kolize."""

    clearance: float = DEFAULT_CLEARANCE
    accepted: list[Accepted] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return self.clearance == DEFAULT_CLEARANCE and not self.accepted

    @classmethod
    def from_dict(cls, data: Any) -> Checks:
        if not isinstance(data, dict):
            raise AssemblyError("„checks“ musí být objekt s „clearance“ a „accepted“.")
        _unknown(data, _CHECK_KEYS, "Kontroly sestavy")
        clearance = data.get("clearance", DEFAULT_CLEARANCE)
        if (isinstance(clearance, bool) or not isinstance(clearance, (int, float))
                or not math.isfinite(clearance) or clearance <= 0):
            raise AssemblyError("Mez vůle „clearance“ musí být kladné číslo v mm.")
        raw = data.get("accepted", [])
        if not isinstance(raw, list):
            raise AssemblyError("„accepted“ musí být seznam přijatých kolizí.")
        accepted = [Accepted.from_dict(item, index) for index, item in enumerate(raw, 1)]
        if len({item.key for item in accepted}) != len(accepted):
            raise AssemblyError("Stejná dvojice komponent je mezi přijatými kolizemi dvakrát.")
        return cls(clearance=clearance, accepted=accepted)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.clearance != DEFAULT_CLEARANCE:
            data["clearance"] = self.clearance
        if self.accepted:
            data["accepted"] = [item.to_dict() for item in self.accepted]
        return data

    def find(self, a: Sequence[str], b: Sequence[str]) -> Accepted | None:
        key = frozenset((tuple(a), tuple(b)))
        return next((item for item in self.accepted if item.key == key), None)


@dataclass
class Assembly:
    """Soubor sestavy: název, popis, parametry pro polohy a seznam komponent."""

    name: str = "Nová sestava"
    description: str = ""
    units: str = "mm"
    parameters: dict[str, Any] = field(default_factory=dict)
    components: list[Component] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    checks: Checks = field(default_factory=Checks)

    @classmethod
    def from_dict(cls, data: Any) -> Assembly:
        if not isinstance(data, dict):
            raise AssemblyError("Sestava musí být JSON objekt.")
        if data.get("format") != FORMAT:
            raise AssemblyError(f"Soubor není ŠkodaCAD (chybí \"format\": \"{FORMAT}\").")
        if data.get("kind") != ASSEMBLY_KIND:
            raise AssemblyError("Tento soubor je díl, ne sestava – otevři ho jako díl.")
        version = data.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version > VERSION:
            raise AssemblyError(f"Nepodporovaná verze sestavy {version!r} – soubor je nejspíš "
                                "z novější verze ŠkodaCAD, stáhni aktuální aplikaci.")
        if version < FIRST_VERSION:
            raise AssemblyError(f"Sestavy existují až od formátu verze {FIRST_VERSION}, soubor "
                                f"uvádí verzi {version}.")
        _unknown(data, _TOP_KEYS, "Sestava")
        if "constraints" in data and version < CONSTRAINTS_VERSION:
            raise AssemblyError(f"Vazby jsou až ve formátu verze {CONSTRAINTS_VERSION}, "
                                f"soubor uvádí verzi {version}.")
        if "checks" in data and version < VERSION:
            raise AssemblyError(f"Kontroly sestavy jsou až ve formátu verze {VERSION}, soubor "
                                f"uvádí verzi {version}.")
        checks = Checks.from_dict(data["checks"]) if "checks" in data else Checks()
        if data.get("units", "mm") != "mm":
            raise AssemblyError(f"Jednotky „{data.get('units')}“ nejsou podporované, "
                                "sestava musí být v mm.")
        parameters = data.get("parameters", {})
        if not isinstance(parameters, dict):
            raise AssemblyError("„parameters“ musí být objekt {název: hodnota}.")
        for name, value in parameters.items():
            _value(value, f"Parametr „{name}“")
        raw = data.get("components", [])
        if not isinstance(raw, list):
            raise AssemblyError("„components“ musí být seznam komponent.")
        components = [Component.from_dict(item, index) for index, item in enumerate(raw, 1)]
        seen: set[str] = set()
        for component in components:
            if component.id in seen:
                raise AssemblyError(f"Id komponenty „{component.id}“ je v sestavě dvakrát, "
                                    "musí být jedinečné.")
            seen.add(component.id)
        if len(components) > MAX_COMPONENTS:
            raise AssemblyError(f"Sestava má {len(components)} komponent, nejvýš "
                                f"{MAX_COMPONENTS}.")
        raw = data.get("constraints", [])
        if not isinstance(raw, list):
            raise AssemblyError("„constraints“ musí být seznam vazeb.")
        constraints = [Constraint.from_dict(item, index) for index, item in enumerate(raw, 1)]
        seen = set()
        for constraint in constraints:
            if constraint.id in seen:
                raise AssemblyError(f"Id vazby „{constraint.id}“ je v sestavě dvakrát, musí "
                                    "být jedinečné.")
            seen.add(constraint.id)
        for key in ("name", "description"):
            if not isinstance(data.get(key, ""), str):
                raise AssemblyError(f"„{key}“ sestavy musí být text.")
        return cls(name=data.get("name", "Nová sestava"),
                   description=data.get("description", ""),
                   parameters=copy.deepcopy(parameters), components=components,
                   constraints=constraints, checks=checks)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "format": FORMAT,
            "kind": ASSEMBLY_KIND,
            "version": (VERSION if not self.checks.empty
                        else CONSTRAINTS_VERSION if self.constraints else FIRST_VERSION),
            "name": self.name,
            "description": self.description,
            "units": self.units,
            "parameters": copy.deepcopy(self.parameters),
            "components": [component.to_dict() for component in self.components],
        }
        if self.constraints:
            data["constraints"] = [constraint.to_dict() for constraint in self.constraints]
        if not self.checks.empty:
            data["checks"] = self.checks.to_dict()
        return data

    def constraint(self, constraint_id: str) -> Constraint:
        for constraint in self.constraints:
            if constraint.id == constraint_id:
                return constraint
        raise AssemblyError(f"Sestava nemá vazbu „{constraint_id}“.")

    def component(self, component_id: str) -> Component:
        for component in self.components:
            if component.id == component_id:
                return component
        raise AssemblyError(f"Sestava nemá komponentu „{component_id}“.")

    @classmethod
    def load(cls, path: str | Path) -> Assembly:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise AssemblyError(f"Soubor {path} neexistuje.") from None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AssemblyError(f"Soubor {path} není platný JSON (řádek {exc.lineno}, "
                                f"sloupec {exc.colno}: {exc.msg}).") from None
        return cls.from_dict(data)

    def save(self, path: str | Path) -> None:
        write_json(path, self.to_dict())


def is_assembly(data: Any) -> bool:
    """Patří slovník ze souboru JSON sestavě (podle „kind“, ne přípony)?"""
    return isinstance(data, dict) and data.get("kind") == ASSEMBLY_KIND


def fingerprint(assembly: Assembly) -> str:
    """Otisk receptu podsestavy (16 znaků): parametry a komponenty bez názvů a otisků."""
    from skodacad.ndt.study import _canonical

    recipe = {
        "parameters": _canonical(assembly.parameters),
        "components": [_canonical({"id": c.id, "path": c.path, "position": c.position,
                                   "rotation": c.rotation})
                       for c in assembly.components],
    }
    if assembly.constraints:  # bez vazeb zůstane otisk jako ve verzi 29
        recipe["constraints"] = [_canonical({k: v for k, v in c.to_dict().items()
                                             if k != "name"})
                                 for c in assembly.constraints]
    text = json.dumps(recipe, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
