"""Konstrukční návrh pro NDT – srovnání variant dílu (etapa 15).

Návrh a schválené hranice jsou v ``docs/ndt/26-navrh-etapa-15.md``. Varianty jsou kombinace
hodnot povolených **číselných parametrů** modelu (nejvýš ``MAX_VARIANTS``, pevné pořadí). Každá
varianta se přepočítá na **kopii** modelu:

1. kontrola zamčených rozměrů a podmínek – uložená měření a parametry (rychlé, před NDT),
2. oblast studie se znovu ukotví významem (jen v kopii),
3. cílová studie (volitelně i ostatní) se spočítá stávajícím výpočtem se stejným nastavením
   a s **kroky sítě zamčenými podle původního dílu**; UT jen s uloženým plánem dráhy.

Model ani soubor se nikdy nemění – výsledek je pohled. Program posuzuje jen geometrickou
přístupnost a pokrytí (závazné vymezení UT, bod 3); pevnost, únavu, technologii ani funkci
dílu neposuzuje (``DESIGN_NOTE``). Pořadí variant je bez jednoho skóre a nejlepší varianty se
ověří polovičním krokem – krok výpočtu umí pořadí otočit (kapsa 100 × 40: MT 0 % se středy
jha po 12 mm, 53,1 % po 6 mm).
"""

from __future__ import annotations

import copy
import csv
import html
import itertools
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skodacad.ndt import (
    DISCLAIMER,
    MT_DISCLAIMER,
    PT_DISCLAIMER,
    RT_DISCLAIMER,
    UT_DISCLAIMER,
)

ALGORITHM = "ndt-navrh 1"
TITLE = "Konstrukční návrh pro NDT – srovnání variant"
BANNER = "Návrh ke konstruktérskému posouzení"
DESIGN_NOTE = ("Návrh ke konstruktérskému posouzení. Program posuzuje jen geometrickou "
               "přístupnost a pokrytí pro NDT. Pevnost, únavu, technologii výroby a funkci dílu "
               "neposuzuje – hlídá jen zamčené rozměry a podmínky zadané uživatelem. Změnu "
               "dílu musí schválit odpovědný konstruktér.")
INFORMATIVE = "informativní – bez zadaných podmínek"
BEFORE = "Než změníš díl: zkus návrh poloh, plán dráhy nebo jiné nastavení metody."
PERCENT_NOTE = ("Procenta vyjadřují jen geometrický podíl plochy nebo objemu oblasti studie, "
                "nikoli pravděpodobnost nalezení vady. Když se oblast studie s variantou "
                "změní, porovnávej i mm² / mm³.")
NOT_INCLUDED = ("Zpráva neobsahuje posouzení pevnosti, únavy, technologie výroby ani funkce "
                "dílu, výběr metody, normativní postup ani schválení změny. Popisuje jen "
                "výpočet nad modelem dílu a jeho variantami.")

MAX_PARAMETERS = 3
MAX_VALUES = 12  # hodnot jednoho parametru
MAX_VARIANTS = 24  # kombinací bez původního dílu
LOCK_TOLERANCE = 0.01  # mm, ° (i mm² u obsahu plochy)
REGION_CHANGE = 5.0  # % – změna oblasti studie, od které tabulka upozorní
UNSURE_GAP = 2.0  # procentní body – menší zlepšení po ověření krokem je „nejisté“
VERIFY_TOP = 3  # kolik nejlepších prošlých variant se ověří polovičním krokem
STATUSES = {"passed": "prošla", "rejected": "neprošla", "failed": "nelze vyhodnotit",
            "stopped": "neprovedeno – zastaveno"}
METHOD_DISCLAIMERS = {"UT": UT_DISCLAIMER, "PT": PT_DISCLAIMER, "MT": MT_DISCLAIMER,
                      "RT": RT_DISCLAIMER}
UT_MODES = ("rebuild", "check")
STALE = "Díl se od nastavení studie změnil"  # obecná hláška – ve variantě je to samozřejmost


class DesignError(ValueError):
    """Chybné zadání návrhu (zpráva je česky)."""


def _dec(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}"
    if text.startswith("-") and float(text) == 0:
        text = text[1:]
    return text.replace(".", ",")


def _num(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _value(value: float, unit: str) -> str:
    """Naměřená hodnota česky: „10,00 mm“, „90,00°“."""
    return f"{_dec(value)}°" if unit == "°" else f"{_dec(value)} {unit}"


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DesignError(f"{what} musí být číslo (je {value!r}).")
    return float(value)


# --- zadání návrhu ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ParameterRange:
    """Hodnoty jednoho měněného parametru – výčtem, nebo rozsahem s krokem."""

    name: str
    values: tuple[float, ...]
    spec: tuple[tuple[str, Any], ...]  # jak je zapsané v souboru (výčet / rozsah)

    @classmethod
    def from_dict(cls, data: Any, number: int) -> ParameterRange:
        where = f"Měněný parametr {number}"
        if not isinstance(data, dict) or not isinstance(data.get("name"), str) \
                or not data["name"].strip():
            raise DesignError(f"{where} musí mít jméno parametru (\"name\").")
        name = data["name"].strip()
        unknown = set(data) - {"name", "values", "from", "to", "step"}
        if unknown:
            raise DesignError(f"{where} „{name}“: neznámé položky {', '.join(sorted(unknown))}.")
        if "values" in data:
            if any(key in data for key in ("from", "to", "step")):
                raise DesignError(f"{where} „{name}“: zadej buď výčet hodnot, nebo rozsah – ne "
                                  "obojí.")
            raw = data["values"]
            if not isinstance(raw, list) or not raw:
                raise DesignError(f"{where} „{name}“: „values“ musí být neprázdný seznam čísel.")
            values = [round(_number(v, f"Hodnota parametru „{name}“"), 9) for v in raw]
            spec: dict[str, Any] = {"name": name, "values": raw}
        elif all(key in data for key in ("from", "to", "step")):
            start = _number(data["from"], f"Začátek rozsahu „{name}“")
            stop = _number(data["to"], f"Konec rozsahu „{name}“")
            step = _number(data["step"], f"Krok rozsahu „{name}“")
            if step <= 0 or stop < start:
                raise DesignError(f"{where} „{name}“: rozsah musí jít od menší hodnoty k větší "
                                  "s kladným krokem.")
            count = math.floor((stop - start) / step + 1e-9) + 1
            if count > MAX_VALUES:
                raise DesignError(f"{where} „{name}“ má {count} hodnot, nejvýš {MAX_VALUES} – "
                                  "zvětši krok.")
            values = [round(start + i * step, 9) for i in range(count)]
            spec = {"name": name, "from": data["from"], "to": data["to"], "step": data["step"]}
        else:
            raise DesignError(f"{where} „{name}“: zadej hodnoty (\"values\") nebo rozsah "
                              "(\"from\", \"to\", \"step\").")
        if len(values) > MAX_VALUES:
            raise DesignError(f"{where} „{name}“ má {len(values)} hodnot, nejvýš {MAX_VALUES}.")
        if len(set(values)) != len(values):
            raise DesignError(f"{where} „{name}“: hodnoty se opakují.")
        return cls(name, tuple(values), tuple(spec.items()))

    def to_dict(self) -> dict[str, Any]:
        return dict(self.spec)

    def text(self) -> str:
        spec = dict(self.spec)
        if "values" in spec:
            return f"{self.name} = " + ", ".join(_num(v) for v in self.values)
        return (f"{self.name} = {_num(spec['from'])} až {_num(spec['to'])} po "
                f"{_num(spec['step'])}")


@dataclass(frozen=True)
class Condition:
    """Podmínka: uložené měření musí ležet v mezích (důvod zadal uživatel)."""

    measurement: str
    min: float | None = None
    max: float | None = None
    reason: str = ""

    @classmethod
    def from_dict(cls, data: Any, number: int) -> Condition:
        where = f"Podmínka {number}"
        if not isinstance(data, dict) or not isinstance(data.get("measurement"), str):
            raise DesignError(f"{where} musí mít uložené měření (\"measurement\": \"m1\").")
        unknown = set(data) - {"measurement", "min", "max", "reason"}
        if unknown:
            raise DesignError(f"{where}: neznámé položky {', '.join(sorted(unknown))}.")
        low = None if data.get("min") is None else _number(data["min"], f"{where}: „min“")
        high = None if data.get("max") is None else _number(data["max"], f"{where}: „max“")
        if low is None and high is None:
            raise DesignError(f"{where}: zadej mez „min“, „max“ nebo obě.")
        if low is not None and high is not None and low > high:
            raise DesignError(f"{where}: „min“ je větší než „max“.")
        reason = data.get("reason", "")
        if not isinstance(reason, str):
            raise DesignError(f"{where}: důvod („reason“) musí být text.")
        return cls(data["measurement"], low, high, reason.strip())

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"measurement": self.measurement}
        if self.min is not None:
            data["min"] = self.min
        if self.max is not None:
            data["max"] = self.max
        if self.reason:
            data["reason"] = self.reason
        return data

    def required(self, unit: str = "") -> str:
        unit = f" {unit}" if unit else ""
        if self.min is not None and self.max is not None:
            return f"{_num(self.min)} až {_num(self.max)}{unit}"
        return (f"≥ {_num(self.min)}{unit}" if self.min is not None
                else f"≤ {_num(self.max)}{unit}")

    def holds(self, value: float) -> bool:
        return ((self.min is None or value >= self.min - 1e-9)
                and (self.max is None or value <= self.max + 1e-9))


@dataclass(frozen=True)
class Design:
    """Zadání návrhu uložené v modelu (``ndt.design``, formát 22)."""

    study: str
    parameters: tuple[ParameterRange, ...]
    locked_measurements: tuple[str, ...] = ()
    locked_parameters: tuple[str, ...] = ()
    conditions: tuple[Condition, ...] = ()
    mass_change_pct: float | None = None
    thickness: bool = False  # mapa tloušťky nikde pod mezí modelu
    others: bool = False  # spočítat i ostatní studie
    rejected: bool = True  # neprošlé varianty spočítat informativně
    verify: bool = True  # ověřit pořadí polovičním krokem
    ut: str = "rebuild"  # UT: plán sestavit znovu / jen ověřit uložený

    @classmethod
    def from_dict(cls, data: Any) -> Design:
        if not isinstance(data, dict):
            raise DesignError("Zadání návrhu („design“) musí být objekt.")
        unknown = set(data) - {"study", "parameters", "locked", "conditions", "mass_change_pct",
                               "options"}
        if unknown:
            raise DesignError(f"Zadání návrhu: neznámé položky {', '.join(sorted(unknown))}.")
        study = data.get("study")
        if not isinstance(study, str) or not study:
            raise DesignError("Zadání návrhu musí mít cílovou studii (\"study\": \"s1\").")
        raw = data.get("parameters")
        if not isinstance(raw, list) or not raw:
            raise DesignError("Zadání návrhu musí mít aspoň jeden měněný parametr.")
        if len(raw) > MAX_PARAMETERS:
            raise DesignError(f"Měnit jde nejvýš {MAX_PARAMETERS} parametry najednou.")
        parameters = tuple(ParameterRange.from_dict(p, i) for i, p in enumerate(raw, start=1))
        names = [p.name for p in parameters]
        if len(set(names)) != len(names):
            raise DesignError("Měněný parametr je v zadání dvakrát.")
        locked = data.get("locked", {})
        if not isinstance(locked, dict) or set(locked) - {"measurements", "parameters"}:
            raise DesignError("Zamčené rozměry („locked“) musí být objekt s „measurements“ "
                              "a „parameters“.")
        lists = {}
        for key in ("measurements", "parameters"):
            items = locked.get(key, [])
            if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
                raise DesignError(f"„locked.{key}“ musí být seznam jmen.")
            lists[key] = tuple(dict.fromkeys(items))
        clash = set(lists["parameters"]) & set(names)
        if clash:
            raise DesignError(f"Parametr {', '.join(sorted(clash))} nejde měnit a zároveň "
                              "zamknout.")
        raw_conditions = data.get("conditions", [])
        if not isinstance(raw_conditions, list):
            raise DesignError("Podmínky („conditions“) musí být seznam.")
        conditions = tuple(Condition.from_dict(c, i)
                           for i, c in enumerate(raw_conditions, start=1))
        mass = data.get("mass_change_pct")
        if mass is not None:
            mass = _number(mass, "Limit změny hmotnosti")
            if mass <= 0:
                raise DesignError("Limit změny hmotnosti musí být kladný (v %).")
        options = data.get("options", {})
        if not isinstance(options, dict) or set(options) - {"others", "rejected", "verify",
                                                            "ut", "thickness"}:
            raise DesignError("Volby návrhu („options“) znají jen others, rejected, verify, ut "
                              "a thickness.")
        flags = {}
        for key, default in (("others", False), ("rejected", True), ("verify", True),
                             ("thickness", False)):
            value = options.get(key, default)
            if not isinstance(value, bool):
                raise DesignError(f"Volba „{key}“ musí být true nebo false.")
            flags[key] = value
        ut = options.get("ut", "rebuild")
        if ut not in UT_MODES:
            raise DesignError("Volba „ut“ je „rebuild“ (plán sestavit znovu) nebo „check“ (jen "
                              "ověřit uložený plán).")
        return cls(study, parameters, lists["measurements"], lists["parameters"], conditions,
                   mass, ut=ut, **flags)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"study": self.study,
                                "parameters": [p.to_dict() for p in self.parameters]}
        if self.locked_measurements or self.locked_parameters:
            data["locked"] = {key: list(value) for key, value in
                              (("measurements", self.locked_measurements),
                               ("parameters", self.locked_parameters)) if value}
        if self.conditions:
            data["conditions"] = [c.to_dict() for c in self.conditions]
        if self.mass_change_pct is not None:
            data["mass_change_pct"] = self.mass_change_pct
        options = {key: value for key, value, default in
                   (("others", self.others, False), ("rejected", self.rejected, True),
                    ("verify", self.verify, True), ("ut", self.ut, "rebuild"),
                    ("thickness", self.thickness, False)) if value != default}
        if options:
            data["options"] = options
        return data

    @property
    def informative(self) -> bool:
        """Bez zamčených rozměrů a podmínek je každý výsledek jen informativní."""
        return not (self.locked_measurements or self.locked_parameters or self.conditions
                    or self.mass_change_pct is not None or self.thickness)

    def check(self, document: Any) -> None:
        """Odkazy zadání na model (studie, parametry, měření). Česká chyba při neshodě."""
        studies = {s.get("id"): s for s in (document.ndt or {}).get("studies", [])}
        record = studies.get(self.study)
        if record is None:
            raise DesignError(f"Cílová studie „{self.study}“ v modelu není.")
        if record.get("method") == "UT" and not record.get("plan"):
            raise DesignError("UT studie potřebuje uložený plán dráhy (etapa 10) – sestav ho "
                              "v panelu NDT; varianty pak použijí stejné průchody.")
        for p in self.parameters:
            if p.name not in document.parameters:
                raise DesignError(f"Parametr „{p.name}“ v modelu není.")
            value = document.parameters[p.name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise DesignError(f"Parametr „{p.name}“ je zadaný výrazem ({value}) – měnit jde "
                                  "jen číselné parametry; výraz se změní sám s ostatními.")
        for name in self.locked_parameters:
            if name not in document.parameters:
                raise DesignError(f"Zamčený parametr „{name}“ v modelu není.")
        measured = {m.get("id") for m in document.measurements}
        for mid in (*self.locked_measurements, *(c.measurement for c in self.conditions)):
            if mid not in measured:
                raise DesignError(f"Uložené měření „{mid}“ v modelu není – ulož ho v panelu "
                                  "Měření.")
        if self.thickness and (document.thickness_map or {}).get("limit") is None:
            raise DesignError("Podmínka mapy tloušťky chce mez mapy (minimální tloušťku) "
                              "v modelu.")

    def combinations(self, original: dict[str, float]) -> list[dict[str, float]]:
        """Všechny kombinace hodnot bez té, která je stejná jako původní díl."""
        names = [p.name for p in self.parameters]
        out = []
        for combo in itertools.product(*(p.values for p in self.parameters)):
            values = dict(zip(names, combo, strict=True))
            if all(abs(values[n] - float(original[n])) <= 1e-9 for n in names):
                continue
            out.append(values)
        if len(out) > MAX_VARIANTS:
            raise DesignError(f"Kombinací je {len(out)}, nejvýš {MAX_VARIANTS} – zúži hodnoty "
                              "nebo ubírej parametry.")
        if not out:
            raise DesignError("Zadané hodnoty dávají jen původní díl – přidej jiné hodnoty.")
        return out

    def text(self) -> list[str]:
        """Zadání česky (zpráva, CLI, panel)."""
        lines = [f"Cílová studie: {self.study}",
                 "Měněné parametry: " + "; ".join(p.text() for p in self.parameters)]
        if self.locked_measurements:
            lines.append("Zamčená měření: " + ", ".join(self.locked_measurements))
        if self.locked_parameters:
            lines.append("Zamčené parametry: " + ", ".join(self.locked_parameters))
        for c in self.conditions:
            lines.append(f"Podmínka: {c.measurement} {c.required()}"
                         + (f" – {c.reason}" if c.reason else ""))
        if self.mass_change_pct is not None:
            lines.append(f"Změna hmotnosti nejvýš ± {_num(self.mass_change_pct)} %")
        if self.thickness:
            lines.append("Tloušťka stěny nikde pod mezí mapy tloušťky")
        lines.append("Volby: " + ", ".join((
            "i ostatní studie" if self.others else "jen cílová studie",
            "neprošlé informativně" if self.rejected else "neprošlé bez NDT",
            "pořadí ověřit polovičním krokem" if self.verify else "bez ověření pořadí",
            "UT: plán sestavit znovu" if self.ut == "rebuild" else "UT: jen ověřit plán")))
        if self.informative:
            lines.append(f"Bez zamčených rozměrů a podmínek – výsledky jsou {INFORMATIVE}.")
        return lines


# --- výsledek ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    """Výsledek jednoho zámku nebo podmínky u varianty."""

    kind: str  # lock / parameter / condition / mass / thickness
    label: str
    required: str
    value: str
    ok: bool

    def text(self) -> str:
        return f"{self.label}: {self.value} (požadováno {self.required})"


@dataclass
class StudyOutcome:
    """Výsledek jedné studie u varianty (souhrn vrstvy auditu, bez geometrie)."""

    study_id: str
    name: str
    method: str
    status: str = "done"  # done / unavailable
    reason: str = ""
    states: tuple[tuple[str, str, str, float, float], ...] = ()  # stav, název, skupina, %, mm
    unit: str = "mm²"
    total: float = 0.0
    places: int = 0
    steps: str = ""
    notes: tuple[str, ...] = ()
    seconds: float = 0.0
    result: Any = None  # mapa metody (náhled v okně); do CSV ani zprávy nejde

    def group_pct(self, group: str) -> float:
        return sum(pct for _s, _l, g, pct, _a in self.states if g == group)

    def group_amount(self, group: str) -> float:
        return sum(amount for _s, _l, g, _p, amount in self.states if g == group)

    @property
    def good_pct(self) -> float:
        return self.group_pct("ok")

    @property
    def good_label(self) -> str:
        return next((label for _s, label, g, _p, _a in self.states if g == "ok"), "dobrý stav")

    def text(self) -> str:
        if self.status != "done":
            return f"{self.study_id} {self.name}: nelze vyhodnotit – {self.reason}"
        shares = ", ".join(f"{label} {_dec(pct)} % ({_dec(amount, 0)} {self.unit})"
                           for _s, label, _g, pct, amount in self.states)
        return f"{self.study_id} {self.name}: {shares}; problémových míst {self.places}"


@dataclass
class Variant:
    """Jedna varianta (index 0 = původní díl) a její výsledek."""

    index: int
    values: dict[str, float]
    status: str = "passed"
    reasons: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    volume: float | None = None
    mass: float | None = None
    target: StudyOutcome | None = None
    others: list[StudyOutcome] = field(default_factory=list)
    verify: StudyOutcome | None = None
    notes: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def label(self) -> str:
        return "Původní" if self.index == 0 else f"V{self.index}"

    def values_text(self, original: dict[str, float]) -> str:
        if self.index == 0:
            return "; ".join(f"{n} = {_num(v)}" for n, v in original.items())
        return "; ".join(f"{n}: {_num(original[n])} → {_num(v)}" if abs(v - original[n]) > 1e-9
                         else f"{n} = {_num(v)}" for n, v in self.values.items())

    def change_size(self, original: dict[str, float]) -> float:
        """Součet relativních změn parametrů (pořadí: menší změna dřív)."""
        return sum(abs(v - original[n]) / abs(original[n]) if original[n] else abs(v)
                   for n, v in self.values.items())


@dataclass
class DesignResult:
    """Celý návrh: zadání, původní díl a varianty v pořadí výpočtu."""

    design: Design
    model: str
    path: str
    fingerprint: str
    material: str
    created: str
    build: str
    libraries: str
    original: dict[str, float]  # původní hodnoty měněných parametrů
    steps: dict[str, str]  # studie → zamčené kroky (text)
    variants: list[Variant]
    complete: bool = True
    seconds: float = 0.0
    verify_note: str = ""
    operator: str = ""

    # --- pořadí a závěr -------------------------------------------------------------------

    @property
    def base(self) -> Variant | None:
        return next((v for v in self.variants if v.index == 0), None)

    def ranked(self) -> list[Variant]:
        """Původní díl první, pak varianty podle pravidel (bez skóre)."""
        base = self.base
        rest = sorted((v for v in self.variants if v.index != 0), key=self._key)
        return ([base] if base is not None else []) + rest

    def _key(self, variant: Variant) -> tuple:
        status = {"passed": 0, "rejected": 1}.get(variant.status, 2)
        target = variant.target if variant.target is not None and \
            variant.target.status == "done" else None
        if target is None:
            return (status, 1, 0.0, 0.0, 0.0, 0.0, 0.0, variant.index)
        volume = abs((variant.volume or 0) - (self.base.volume or 0)) if self.base else 0.0
        return (status, 0, -target.good_pct, -target.group_pct("limited"),
                target.group_pct("uncertain"), variant.change_size(self.original), volume,
                variant.index)

    def improvement(self, variant: Variant) -> float | None:
        """O kolik procentních bodů je dobrý stav cílové studie lepší než u původního dílu."""
        base = self.base
        if base is None or base.target is None or variant.target is None \
                or base.target.status != "done" or variant.target.status != "done":
            return None
        return variant.target.good_pct - base.target.good_pct

    def better(self, variant: Variant) -> bool:
        """Lepší než původní díl: víc dobrého stavu, při shodě víc „omezeně“ (pořadí etapy 15)."""
        good = self.improvement(variant)
        if good is None:
            return False
        if abs(good) > 1e-9:
            return good > 0
        return (variant.target.group_pct("limited")
                - self.base.target.group_pct("limited")) > 1e-9

    @staticmethod
    def shares(variant: Variant | StudyOutcome | None) -> str:
        """Dobrý a omezený stav cílové studie česky („přístupné 53,86 %, omezené 34,31 %“)."""
        target = variant.target if isinstance(variant, Variant) else variant
        if target is None or target.status != "done":
            return "nelze vyhodnotit"
        return ", ".join(f"{label[:1].lower()}{label[1:]} {_dec(pct)} %"
                         for _s, label, group, pct, _a in target.states
                         if group in ("ok", "limited"))

    def region_change(self, variant: Variant) -> float | None:
        """Změna velikosti oblasti cílové studie proti původnímu dílu [%]."""
        base = self.base
        if base is None or base.target is None or variant.target is None \
                or base.target.status != "done" or variant.target.status != "done" \
                or not base.target.total:
            return None
        return 100 * (variant.target.total - base.target.total) / base.target.total

    def conclusion(self) -> str:
        base = self.base
        if base is None or base.target is None or base.target.status != "done":
            return "Původní díl se nepodařilo vyhodnotit – srovnání nejde udělat."
        passed = [v for v in self.ranked()[1:] if v.status == "passed" and self.better(v)]
        if passed:
            best = passed[0]
            text = (f"Nejlepší prošlá varianta {best.label} ({best.values_text(self.original)}): "
                    f"{self.shares(best)} proti {self.shares(base)} u původního dílu.")
        else:
            text = "V povolených mezích se výsledek cílové studie nezlepšil."
            rejected = [v for v in self.ranked()[1:] if v.status == "rejected" and self.better(v)]
            if rejected:
                best = rejected[0]
                text += (f" Nejlepší neprošlá varianta {best.label} "
                         f"({best.values_text(self.original)}): {self.shares(best)}, neprošla: "
                         f"{'; '.join(best.reasons)}.")
        if self.verify_note:
            text += f" {self.verify_note}"
        return text

    # --- texty a výstupy --------------------------------------------------------------------

    def methods(self) -> list[str]:
        present = {o.method for v in self.variants for o in
                   ([v.target] if v.target else []) + v.others}
        return [m for m in ("UT", "PT", "MT", "RT") if m in present]

    def disclaimers(self) -> list[str]:
        return [DISCLAIMER, *(METHOD_DISCLAIMERS[m] for m in self.methods())]

    def header(self) -> list[str]:
        lines = [f"Model: {self.model}" + (f" ({self.path})" if self.path else ""),
                 f"Otisk dílu: {self.fingerprint}; materiál: {self.material or 'neuvedený'}.",
                 f"Vytvořeno: {self.created}; {self.build}; {self.libraries}.",
                 f"Algoritmus návrhu: {ALGORITHM}."]
        if self.operator:
            lines.append(f"Zpracoval(a): {self.operator}.")
        if not self.complete:
            lines.append("Návrh byl zastaven – nespočítané varianty jsou „neprovedeno“.")
        return lines

    def row(self, variant: Variant) -> dict[str, str]:
        """Jeden řádek tabulky variant (texty pro panel, CSV i zprávu)."""
        target = variant.target
        done = target is not None and target.status == "done"
        change = self.region_change(variant)
        better = self.improvement(variant)
        base = self.base
        mass = ""
        if variant.volume is not None and base is not None and base.volume:
            mass = f"{_dec(100 * (variant.volume - base.volume) / base.volume, 1)} %"
        status = STATUSES[variant.status]
        if variant.status in ("rejected", "failed") and variant.reasons:
            status += " – " + "; ".join(variant.reasons)
        if self.design.informative and variant.index:
            status += f" ({INFORMATIVE})"
        return {
            "variant": variant.label,
            "values": variant.values_text(self.original),
            "status": status,
            "good": f"{_dec(target.good_pct)} %" if done else "–",
            "good_amount": f"{_dec(target.group_amount('ok'), 0)} {target.unit}" if done else "",
            "limited": f"{_dec(target.group_pct('limited'))} %" if done else "",
            "blocked": f"{_dec(target.group_pct('blocked'))} %" if done else "",
            "uncertain": f"{_dec(target.group_pct('uncertain'))} %" if done else "",
            "region": (f"{_dec(target.total, 0)} {target.unit}" if done else "")
            + (f" ({'+' if change > 0 else ''}{_dec(change, 1)} %)"
               if change is not None and abs(change) > REGION_CHANGE else ""),
            "better": (f"{'+' if better > 0 else ''}{_dec(better)} p. b."
                       + (" (lepší v „omezeně“)" if abs(better) <= 1e-9 and self.better(variant)
                          else "")
                       if better is not None and variant.index else ""),
            "verify": self.shares(variant.verify) if variant.verify is not None else "",
            "volume": f"{_dec(variant.volume, 0)} mm³" if variant.volume is not None else "",
            "mass": mass,
            "checks": "; ".join(("✓ " if c.ok else "✕ ") + c.text() for c in variant.checks),
            "others": "; ".join(o.text() for o in variant.others),
            "seconds": f"{_dec(variant.seconds, 1)} s",
        }

    def region_warning(self) -> str:
        changed = [v.label for v in self.variants
                   if (c := self.region_change(v)) is not None and abs(c) > REGION_CHANGE]
        return (f"Oblast cílové studie se změnila o víc než {_num(REGION_CHANGE)} % u variant "
                f"{', '.join(changed)} – porovnávej i mm² / mm³." if changed else "")

    def summary(self) -> list[str]:
        """Text pro příkazovou řádku: povinné texty, hlavička, zadání, varianty, závěr."""
        lines = [TITLE, BANNER, DESIGN_NOTE, *self.disclaimers(), PERCENT_NOTE, *self.header(),
                 "Zadání:", *(f"  {line}" for line in self.design.text())]
        lines += [f"Zamčené kroky: {sid}: {text}" for sid, text in self.steps.items()]
        lines.append("Varianty:")
        for variant in self.ranked():
            row = self.row(variant)
            lines.append(f"  {row['variant']} ({row['values']}): {row['status']}; "
                         f"dobrý stav {row['good']} {row['good_amount']}".rstrip()
                         + (f", omezeně {row['limited']}" if row["limited"] else "")
                         + (f", proti původnímu {row['better']}" if row["better"] else "")
                         + (f", oblast {row['region']}" if row["region"] else "")
                         + (f", ověřeno polovičním krokem {row['verify']}" if row["verify"]
                            else "")
                         + (f", objem {row['volume']} ({row['mass']})" if row["mass"] else ""))
            for note in variant.notes:
                lines.append(f"      {note}")
        warning = self.region_warning()
        if warning:
            lines.append(warning)
        lines += [f"Závěr: {self.conclusion()}", NOT_INCLUDED]
        return lines

    def write_csv(self, path: str | Path) -> Path:
        """CSV variant (středník, desetinná čárka, nahoře povinné texty)."""
        path = Path(path)
        columns = (("variant", "varianta"), ("values", "parametry"), ("status", "stav"),
                   ("good", "dobrý stav [%]"), ("good_amount", "dobrý stav"),
                   ("limited", "omezeně [%]"), ("blocked", "nepokryto / nepřístupné [%]"),
                   ("uncertain", "nelze spolehlivě vyhodnotit [%]"), ("region", "oblast"),
                   ("better", "proti původnímu"), ("verify", "ověřeno polovičním krokem"),
                   ("volume", "objem"), ("mass", "změna hmotnosti"),
                   ("checks", "zámky a podmínky"), ("others", "ostatní studie"),
                   ("seconds", "doba"))
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            for text in (TITLE, BANNER, DESIGN_NOTE, *self.disclaimers(), PERCENT_NOTE,
                         *self.header(), *self.design.text(), f"Závěr: {self.conclusion()}"):
                writer.writerow([text])
            writer.writerow([])
            writer.writerow([label for _key, label in columns])
            for variant in self.ranked():
                row = self.row(variant)
                writer.writerow([row[key] for key, _label in columns])
        return path

    def html(self, images: dict[str, list[tuple[str, bytes]]] | None = None) -> str:
        """Zpráva jako jeden soubor HTML (styl i obrázky uvnitř, tiskne se na A4)."""
        import base64

        from skodacad.ndt.audit import _CSS

        e = html.escape
        out = ["<!doctype html>", '<html lang="cs"><head><meta charset="utf-8">',
               f"<title>{e(TITLE)} – {e(self.model)}</title>", f"<style>{_CSS}"
               ".banner{border:2px solid #b45309;color:#b45309;font-weight:bold;padding:6pt 10pt;"
               "font-size:12pt}tr.passed td:first-child{color:#166534}"
               "tr.rejected td,tr.failed td,tr.stopped td{color:#777}</style>",
               "</head><body>", f"<h1>{e(TITLE)}</h1>", f"<p class=banner>{e(BANNER)}</p>",
               "<p class=meta>" + "<br>".join(e(line) for line in self.header()) + "</p>",
               '<section class=warn><h2>Povinné texty</h2>']
        out += [f"<p>{e(text)}</p>" for text in (DESIGN_NOTE, *self.disclaimers(),
                                                  PERCENT_NOTE)]
        out += ["</section>", "<h2>Zadání</h2>", "<ul>"]
        out += [f"<li>{e(line)}</li>" for line in self.design.text()]
        out += [f"<li>Zamčené kroky – {e(sid)}: {e(text)}</li>" for sid, text in
                self.steps.items()]
        out += ["</ul>", "<h2>Závěr</h2>", f"<p><b>{e(self.conclusion())}</b></p>"]
        warning = self.region_warning()
        if warning:
            out.append(f"<p>{e(warning)}</p>")
        out += ["<h2>Varianty</h2>", "<table><tr><th>Varianta</th><th>Parametry</th>"
                "<th>Stav</th><th>Dobrý stav</th><th>Proti původnímu</th><th>Omezeně</th>"
                "<th>Nelze spolehlivě vyhodnotit</th><th>Oblast</th><th>Ověřeno polovičním "
                "krokem</th><th>Objem (změna)</th><th>Doba</th></tr>"]
        for variant in self.ranked():
            row = self.row(variant)
            out.append(f"<tr class={variant.status}><td>{e(row['variant'])}</td>"
                       f"<td>{e(row['values'])}</td><td>{e(row['status'])}</td>"
                       f"<td>{e(row['good'])}<br><small>{e(row['good_amount'])}</small></td>"
                       f"<td>{e(row['better'])}</td><td>{e(row['limited'])}</td>"
                       f"<td>{e(row['uncertain'])}</td><td>{e(row['region'])}</td>"
                       f"<td>{e(row['verify'])}</td><td>{e(row['volume'])}"
                       f"{' (' + e(row['mass']) + ')' if row['mass'] else ''}</td>"
                       f"<td>{e(row['seconds'])}</td></tr>")
        out.append("</table>")
        out.append("<h2>Varianty podrobně</h2>")
        for variant in self.ranked():
            target = variant.target
            out.append(f"<section class=study><h3>{e(variant.label)} – "
                       f"{e(variant.values_text(self.original))}</h3>")
            out.append(f"<p><b>Stav:</b> {e(self.row(variant)['status'])}</p>")
            if variant.checks:
                out.append("<p><b>Zámky a podmínky:</b></p><ul>" + "".join(
                    f"<li>{'✓' if c.ok else '✕'} {e(c.text())}</li>" for c in variant.checks)
                    + "</ul>")
            if target is not None:
                out.append(f"<p><b>Cílová studie:</b> {e(target.text())}</p>")
                if target.steps:
                    out.append(f"<p><small>Kroky: {e(target.steps)}</small></p>")
            for note in variant.notes:
                out.append(f"<p><small>{e(note)}</small></p>")
            for other in variant.others:
                out.append(f"<p><b>Ostatní studie:</b> {e(other.text())}</p>")
            if variant.verify is not None:
                out.append(f"<p><b>Ověřeno polovičním krokem:</b> {e(variant.verify.text())}"
                           "</p>")
            for caption, png in (images or {}).get(variant.label, []):
                data = base64.b64encode(png).decode("ascii")
                out.append(f'<figure><img alt="{e(caption)}" src="data:image/png;base64,'
                           f'{data}"><figcaption>{e(caption)}</figcaption></figure>')
            out.append("</section>")
        out += ["<h2>Co zpráva neobsahuje</h2>", f"<p>{e(NOT_INCLUDED)}</p>",
                f"<p class=meta>{e(self.build)} · {e(ALGORITHM)}</p>", "</body></html>"]
        return "\n".join(out)

    def write_folder(self, folder: str | Path,
                     images: dict[str, list[tuple[str, bytes]]] | None = None) -> list[Path]:
        """Složka se zprávou: ``navrh.html`` a ``varianty.csv``."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        report = folder / "navrh.html"
        report.write_text(self.html(images), encoding="utf-8")
        return [report, self.write_csv(folder / "varianty.csv")]


# --- výpočet variant ------------------------------------------------------------------------


@dataclass
class Baseline:
    """Co je potřeba z původního dílu: hodnoty parametrů, měření, objem, studie a kroky."""

    document: dict[str, Any]
    original: dict[str, float]
    parameters: dict[str, float]  # vyčíslené hodnoty všech parametrů
    measurements: dict[str, Any]  # id → SavedResult
    volume: float
    density: float | None
    studies: list[str]  # cílová + případně ostatní
    steps: dict[str, dict[str, Any]]  # studie → zamčené kroky (doplní se do záznamu studie)
    steps_text: dict[str, str]
    seconds: dict[str, float]  # studie → odhad doby jednoho výpočtu [s]
    limit: float | None = None  # mez mapy tloušťky


def _session(data: dict[str, Any]) -> Any:
    from skodacad.document import Document
    from skodacad.session import ModelSession

    session = ModelSession()
    session.document = Document.from_dict(data)
    session.rebuild()
    return session


def baseline(document: dict[str, Any], design: Design) -> Baseline:
    """Přepočítá původní díl, ověří zadání a zamkne kroky sítě studií."""
    from skodacad.document import DocumentError
    from skodacad.ndt.audit import STUDY_PROBLEMS
    from skodacad.properties import compute as properties

    session = _session(copy.deepcopy(document))
    result = session.result
    if result is None or not result.ok or result.part is None:
        raise DesignError("Původní díl se nepřepočítal bez chyby – oprav nejdřív model.")
    design.check(session.document)
    states = {r.id: r for r in session.ndt_studies}
    target = states.get(design.study)
    if target is None or target.state != "ok":
        problem = STUDY_PROBLEMS.get(target.state if target else "broken", "")
        raise DesignError(f"Cílová studie není platná: {problem}".strip())
    studies = [design.study]
    if design.others:
        for record in (session.document.ndt or {}).get("studies", []):
            sid = record["id"]
            if sid != design.study and states.get(sid) is not None \
                    and states[sid].state == "ok" \
                    and (record.get("method") != "UT" or record.get("plan")):
                studies.append(sid)
    steps, texts, seconds = {}, {}, {}
    for sid in studies:
        record = session.ndt_study(sid)
        try:
            steps[sid], texts[sid], seconds[sid] = _locked_steps(session, sid, record)
        except DocumentError as exc:
            raise DesignError(f"Studie {sid}: {exc}") from None
    props = properties(result.part, session.document.material)
    return Baseline(
        document=copy.deepcopy(document),
        original={p.name: float(session.document.parameters[p.name]) for p in design.parameters},
        parameters=dict(result.parameters),
        measurements={m.id: m for m in result.measurements},
        volume=props.volume_mm3, density=props.density_g_cm3, studies=studies, steps=steps,
        steps_text=texts, seconds=seconds,
        limit=(session.document.thickness_map or {}).get("limit"))


def _locked_steps(session: Any, sid: str, record: dict[str, Any]
                  ) -> tuple[dict[str, Any], str, float]:
    """Kroky sítě, které ukáže odhad původního dílu – ve variantách se použijí napevno
    (automatický krok by se jinak řídil velikostí oblasti varianty). Vrátí i odhad doby."""
    method = record.get("method")
    if method == "PT":
        _count, step, seconds = session.ndt_pt_estimate(sid)
        return {"pt": {"step_mm": step}}, f"síť {_num(round(step, 4))} mm", seconds
    if method == "MT":
        _samples, step, _centers, center, seconds = session.ndt_mt_estimate(sid)
        return ({"mt": {"step_mm": step, "center_step_mm": center}},
                f"síť {_num(round(step, 4))} mm, středy jha {_num(round(center, 4))} mm",
                seconds)
    if method == "RT":
        _samples, step, _count, seconds = session.ndt_rt_estimate(sid)
        return {"rt": {"step_mm": step}}, f"síť {_num(round(step, 4))} mm", seconds
    if method == "UT":
        plan = session.ndt_plan(sid)
        passes = [{"face": p.face, "angle_deg": p.angle_deg, "beta": p.beta,
                   "bounces": p.bounces} for p in plan.passes]
        seconds = session.ndt_plan_estimate(sid, passes).seconds[1]
        return ({}, f"plán dráhy: rozteč řádků {_num(plan.row_step_mm)} mm (uložená)",
                seconds)
    raise DesignError(f"Metoda {method} v návrhu není.")


def _with_steps(record: dict[str, Any], steps: dict[str, Any], half: bool) -> None:
    """Doplní zamčené kroky do záznamu studie v kopii modelu (``half`` = poloviční krok)."""
    for key, values in steps.items():
        settings = dict(record.get(key) or {})
        for name, value in values.items():
            settings[name] = value / 2 if half and (key != "mt" or name == "center_step_mm") \
                else value
        record[key] = settings


def evaluate(base: Baseline, design: Design, index: int, values: dict[str, float], *,
             half: bool = False, studies: list[str] | None = None,
             progress: Callable[[int, int], None] | None = None) -> Variant:
    """Jedna varianta na kopii modelu: přepočet, zámky a podmínky, studie se zamčenými kroky."""
    started = time.monotonic()
    variant = Variant(index, dict(values))
    data = copy.deepcopy(base.document)
    data["parameters"].update(values)
    for record in (data.get("ndt") or {}).get("studies", []):
        if record.get("id") in base.steps:
            _with_steps(record, base.steps[record["id"]], half)
    try:
        session = _session(data)
    except Exception as exc:  # noqa: BLE001 – neplatná varianta nesmí shodit návrh
        variant.status, variant.reasons = "failed", [f"model varianty nejde načíst: {exc}"]
        return variant
    result = session.result
    errors = [s for s in result.statuses if s.status == "error"] if result else []
    if result is None or errors or result.part is None:
        variant.status = "failed"
        variant.reasons = ([f"prvek {errors[0].label}: {errors[0].message}"] if errors
                           else ["díl varianty nemá těleso"])
        variant.seconds = time.monotonic() - started
        return variant
    variant.volume = result.part.volume
    if base.density is not None:
        variant.mass = variant.volume / 1e6 * base.density
    variant.checks = _checks(base, design, session, result)
    failed = [c for c in variant.checks if not c.ok]
    if failed:
        variant.status = "rejected"
        variant.reasons = [c.text() for c in failed]
    if failed and not design.rejected:
        variant.seconds = time.monotonic() - started
        return variant
    for sid in studies or base.studies:
        outcome = _study(session, sid, design, base, half, progress)
        if sid == design.study:
            variant.target = outcome
            variant.notes += [f"{sid}: {note}" for note in outcome.notes]
        else:
            variant.others.append(outcome)
    if variant.target is None or variant.target.status != "done":
        if variant.status == "passed":
            variant.status = "failed"
        reason = variant.target.reason if variant.target else "cílová studie chybí"
        variant.reasons.append(f"cílová studie: {reason}")
    variant.seconds = time.monotonic() - started
    return variant


def _checks(base: Baseline, design: Design, session: Any, result: Any) -> list[Check]:
    measured = {m.id: m for m in result.measurements}
    checks = []
    for name in design.locked_parameters:
        before, after = base.parameters.get(name), result.parameters.get(name)
        ok = before is not None and after is not None \
            and abs(after - before) <= 1e-9 * max(1.0, abs(before))
        checks.append(Check("parameter", f"zamčený parametr {name}",
                            f"= {_num(before) if before is not None else '?'}",
                            _num(after) if after is not None else "nejde vyčíslit", ok))
    for mid in design.locked_measurements:
        before, after = base.measurements.get(mid), measured.get(mid)
        name = before.name if before is not None else mid
        if before is None or before.value is None:
            checks.append(Check("lock", f"zamčená kóta {name}", "původní hodnota",
                                "u původního dílu nejde spočítat", False))
            continue
        unit = before.value.unit
        required = _value(before.value.value, unit)
        if after is None or after.value is None:
            error = after.error if after is not None else "měření chybí"
            checks.append(Check("lock", f"zamčená kóta {name}", f"= {required}",
                                f"nejde spočítat ({error})", False))
            continue
        ok = abs(after.value.value - before.value.value) <= LOCK_TOLERANCE
        checks.append(Check("lock", f"zamčená kóta {name}", f"= {required}",
                            _value(after.value.value, unit), ok))
    for condition in design.conditions:
        after = measured.get(condition.measurement)
        name = after.name if after is not None else condition.measurement
        label = f"podmínka {name}" + (f" ({condition.reason})" if condition.reason else "")
        if after is None or after.value is None:
            error = after.error if after is not None else "měření chybí"
            checks.append(Check("condition", label, condition.required(),
                                f"nejde spočítat ({error})", False))
            continue
        checks.append(Check("condition", label, condition.required(after.value.unit),
                            _value(after.value.value, after.value.unit),
                            condition.holds(after.value.value)))
    if design.mass_change_pct is not None and base.volume:
        change = 100 * (result.part.volume - base.volume) / base.volume
        checks.append(Check("mass", "změna hmotnosti",
                            f"nejvýš ± {_num(design.mass_change_pct)} %",
                            f"{'+' if change > 0 else ''}{_dec(change, 1)} %",
                            abs(change) <= design.mass_change_pct + 1e-9))
    if design.thickness and base.limit is not None:
        from skodacad.thickness_map import compute as thickness

        found = thickness(result.part, session.map_settings)
        minimum = found.minimum
        checks.append(Check("thickness", "tloušťka stěny (mapa)",
                            f"≥ {_num(base.limit)} mm",
                            "nejde změřit" if minimum is None else f"nejmenší {_dec(minimum)} mm",
                            minimum is not None and minimum >= base.limit - 1e-9))
    return checks


def _study(session: Any, sid: str, design: Design, base: Baseline, half: bool,
           progress: Callable[[int, int], None] | None) -> StudyOutcome:
    """Studie v kopii modelu: znovu ukotvit (jen v kopii) a spočítat stávajícím výpočtem."""
    from skodacad.document import DocumentError
    from skodacad.ndt.audit import STUDY_PROBLEMS, AuditError, find_places, layer_of

    record = session.ndt_study(sid)
    method, name = record.get("method", ""), record.get("name") or sid
    outcome = StudyOutcome(sid, name, method)
    state = next((r for r in session.ndt_studies if r.id == sid), None)
    notes = tuple(m for m in (state.messages if state else ()) if m and not m.startswith(STALE))
    started = time.monotonic()
    try:
        if state is not None and state.state == "stale":
            session.confirm_ndt_study(sid)  # jen v kopii – originál zůstává nepotvrzený
        elif state is None or state.state != "ok":
            problem = STUDY_PROBLEMS.get(state.state if state else "broken", "")
            raise DocumentError(" ".join([problem, *notes]).strip())
        result = _compute(session, sid, method, design, half, progress)
        layer = layer_of(result)
    except (DocumentError, AuditError, DesignError) as exc:
        outcome.status, outcome.reason = "unavailable", str(exc)
        outcome.notes, outcome.seconds = notes, time.monotonic() - started
        return outcome
    except Exception as exc:  # noqa: BLE001 – chyba jedné varianty nesmí shodit návrh
        outcome.status = "unavailable"
        outcome.reason = f"výpočet skončil chybou ({type(exc).__name__}: {exc})"
        outcome.seconds = time.monotonic() - started
        return outcome
    outcome.states = tuple((state_, label, layer.groups.get(state_, "ok"), layer.percent(state_),
                            layer.amount(state_)) for state_, label in layer.states.items())
    outcome.unit, outcome.total = layer.unit, layer.total
    outcome.places = len(find_places(layer, sid, name, method))
    text = base.steps_text.get(sid, "")
    outcome.steps = f"{text} – poloviční krok" if half and text else text
    outcome.notes, outcome.result = notes, result
    outcome.seconds = time.monotonic() - started
    return outcome


def _compute(session: Any, sid: str, method: str, design: Design, half: bool,
             progress: Callable[[int, int], None] | None) -> Any:
    if method == "PT":
        return session.compute_ndt_pt(sid, progress=progress)
    if method == "MT":
        return session.compute_ndt_mt(sid, progress=progress)
    if method == "RT":
        return session.compute_ndt_rt(sid, progress=progress)
    if method != "UT":
        raise DesignError(f"Metoda {method} v návrhu není.")
    from skodacad.ndt.plan import PlanOptions

    plan = session.ndt_plan(sid)
    if plan is None:
        raise DesignError("UT studie nemá uložený plán dráhy.")

    def staged(_stage: str, done: int, total: int) -> None:
        if progress is not None:
            progress(done, total)

    if design.ut == "check" and not half:
        return session.check_ndt_plan(sid, coverage=True, progress=staged)
    options = PlanOptions.for_plan(plan, **({"row_step_mm": plan.row_step_mm / 2} if half
                                            else {}))
    passes = [{"face": p.face, "angle_deg": p.angle_deg, "beta": p.beta, "bounces": p.bounces}
              for p in plan.passes]
    return session._run_plan(sid, passes, options, staged)


def rank_and_verify(base: Baseline, design: Design, variants: list[Variant],
                    progress: Callable[[int, int, str, Any], None] | None = None,
                    on_verify: Callable[[Variant], None] | None = None) -> str:
    """Ověří původní díl a nejlepší prošlé varianty polovičním krokem; vrátí poznámku
    o pořadí („potvrzeno“ / „nejisté“). Bez ověření prázdná."""
    if not design.verify:
        return ""
    holder = DesignResult(design, "", "", "", "", "", "", "", base.original, {}, variants)
    ranked = [v for v in holder.ranked() if v.target is not None
              and v.target.status == "done"]
    chosen = [v for v in ranked if v.index == 0]
    chosen += [v for v in ranked if v.index != 0 and v.status == "passed"][:VERIFY_TOP]
    if len(chosen) < 2:
        return ""
    for number, variant in enumerate(chosen):
        if progress is not None:
            progress(number, len(chosen), f"ověření {variant.label} polovičním krokem", None)
        fine = evaluate(base, design, variant.index, variant.values, half=True,
                        studies=[design.study])
        variant.verify = fine.target
        if on_verify is not None:
            on_verify(variant)
    coarse = [_level(v.target) for v in chosen]
    finer = [_level(v.verify) if v.verify is not None and v.verify.status == "done" else None
             for v in chosen]
    if any(f is None for f in finer):
        return "Pořadí se nepodařilo ověřit polovičním krokem."
    coarse_order = sorted(range(len(chosen)), key=lambda i: (-coarse[i][0], -coarse[i][1], i))
    fine_order = sorted(range(len(chosen)), key=lambda i: (-finer[i][0], -finer[i][1], i))
    best = fine_order[0] if fine_order[0] != 0 else fine_order[1]
    if coarse_order != fine_order or (_gain(coarse[best], coarse[0]) >= UNSURE_GAP
                                      > _gain(finer[best], finer[0])):
        return "Pořadí nejisté – rozhoduje krok výpočtu (ověřeno polovičním krokem)."
    return "Pořadí potvrzeno polovičním krokem."


def _level(outcome: StudyOutcome) -> tuple[float, float]:
    """Dobrý stav a „omezeně“ v % – pořadí etapy 15 (při shodě dobrého rozhoduje omezeně)."""
    return round(outcome.good_pct, 6), round(outcome.group_pct("limited"), 6)


def _gain(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Zlepšení a proti b v procentních bodech (dobrý stav, při shodě omezeně)."""
    return a[0] - b[0] if abs(a[0] - b[0]) > 1e-9 else a[1] - b[1]


def run(document: dict[str, Any], design: Design, *, model: str = "", path: str = "",
        fingerprint: str = "", created: str = "", operator: str = "",
        progress: Callable[[int, int, str, Any], None] | None = None,
        on_variant: Callable[[Variant], None] | None = None,
        on_prepared: Callable[[Baseline], None] | None = None) -> DesignResult:
    """Celý návrh synchronně (CLI, testy, pomocný proces). Model se nemění."""
    from skodacad.buildinfo import build_text, libraries_text

    started = time.monotonic()
    base = baseline(document, design)
    if on_prepared is not None:
        on_prepared(base)
    combos = design.combinations(base.original)
    todo = [{}, *combos]
    variants: list[Variant] = []
    for index, values in enumerate(todo):
        label = "původní díl" if index == 0 else f"varianta V{index}"

        def inner(done: int, total: int, index: int = index, label: str = label) -> None:
            if progress is not None:
                progress(index, len(todo), label, (done, total))

        if progress is not None:
            progress(index, len(todo), label, None)
        variant = evaluate(base, design, index, values, progress=inner)
        variants.append(variant)
        if on_variant is not None:
            on_variant(variant)
    note = rank_and_verify(base, design, variants, progress, on_variant)
    return DesignResult(design, model or document.get("name", ""), path, fingerprint,
                        document.get("material", ""), created, build_text(), libraries_text(),
                        base.original, base.steps_text, variants, complete=True,
                        seconds=time.monotonic() - started, verify_note=note,
                        operator=operator.strip())


def estimate(base: Baseline, design: Design) -> tuple[int, float]:
    """Počet variant (bez původního dílu) a odhad doby celého návrhu [s] z odhadů studií
    původního dílu; ověření polovičním krokem asi 4× dražší."""
    per_variant = sum(base.seconds.get(sid, 0.0) for sid in base.studies) + 0.2
    count = len(design.combinations(base.original))
    verify = 0.0
    if design.verify:
        verify = 4 * base.seconds.get(design.study, 0.0) * min(1 + VERIFY_TOP, count + 1)
    return count, (count + 1) * per_variant + verify


def json_record(design: Design) -> str:
    return json.dumps(design.to_dict(), ensure_ascii=False, sort_keys=True)
