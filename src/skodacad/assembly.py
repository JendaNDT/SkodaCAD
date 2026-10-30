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
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skodacad.document import ASSEMBLY_KIND, FORMAT, DocumentError, write_json

VERSION = 29  # první verze formátu, která zná sestavy
MAX_DEPTH = 8  # úrovní podsestav (S10, zvoleno)
MAX_COMPONENTS = 1000  # komponent po rozbalení podsestav (S10, zvoleno)

_TOP_KEYS = {"format", "kind", "version", "name", "description", "units", "parameters",
             "components"}
_COMPONENT_KEYS = {"id", "name", "source", "placement", "fixed"}
_SOURCE_KEYS = {"path", "fingerprint"}
_PLACEMENT_KEYS = {"position", "rotation"}
_FINGERPRINT = re.compile(r"[0-9a-f]{16}")


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


@dataclass
class Assembly:
    """Soubor sestavy: název, popis, parametry pro polohy a seznam komponent."""

    name: str = "Nová sestava"
    description: str = ""
    units: str = "mm"
    parameters: dict[str, Any] = field(default_factory=dict)
    components: list[Component] = field(default_factory=list)

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
        if version < VERSION:
            raise AssemblyError(f"Sestavy existují až od formátu verze {VERSION}, soubor "
                                f"uvádí verzi {version}.")
        _unknown(data, _TOP_KEYS, "Sestava")
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
        for key in ("name", "description"):
            if not isinstance(data.get(key, ""), str):
                raise AssemblyError(f"„{key}“ sestavy musí být text.")
        return cls(name=data.get("name", "Nová sestava"),
                   description=data.get("description", ""),
                   parameters=copy.deepcopy(parameters), components=components)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "kind": ASSEMBLY_KIND,
            "version": VERSION,
            "name": self.name,
            "description": self.description,
            "units": self.units,
            "parameters": copy.deepcopy(self.parameters),
            "components": [component.to_dict() for component in self.components],
        }

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
    text = json.dumps(recipe, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
