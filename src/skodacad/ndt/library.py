"""Knihovna NDT – etapa 08 (jen UT): obecné profily sond a materiálů, Moje sondy, přenos úhlu.

Vestavěné hodnoty jsou **orientační**: obecné profily bez značek výrobců, žádné katalogové
ani certifikované údaje. Úhel a výstupní bod skutečné sondy se ověřují na kalibračním bloku
(č. 1 podle EN ISO 2400, miniaturní sondy č. 2 podle EN ISO 7963), rychlost zvuku na vzorku.
Program sám nic neměří ani neověřuje; geometrii ani výpočet pokrytí knihovna nemění.

Rychlosti zvuku [m/s] (podélná c_L / příčná c_T), každá ze dvou zdrojů, ověřeno 18. 10. 2026:

- ocel uhlíková (mild, 1020): c_L 5 920 – materialwelding.com „Ultrasonic Velocity Chart“,
  Class Instrumentation „Ultrasonic Sound Velocity Chart“ (mild steel); c_T 3 240 –
  materialwelding.com, Dakota NDT „Ultrasonic Velocity Table“ (1020), NDT Systems „Common
  Material Velocities of Sound“ (1020: 3,24 mm/µs).
- nerez austenitická (302/304): c_L 5 660 – Cygnus „Velocity Table“ (302), materialwelding.com
  (304); c_T 3 120 – materialwelding.com, Dakota NDT, NDT Systems (302: 3,12 mm/µs).
- hliník (válcovaný): c_L 6 320, c_T 3 130 – Olympus/Evident „Ultrasonic Transducers
  Technical Notes“ (tabulka akustických vlastností), materialwelding.com; c_L i Evident
  „Material Sound Velocities“.
- měď: c_L 4 660, c_T 2 260 – Olympus/Evident Technical Notes, materialwelding.com; c_L i Evident
  „Material Sound Velocities“.
- mosaz (lodní): c_L 4 430, c_T 2 120 – Olympus/Evident Technical Notes (naval brass),
  materialwelding.com; c_L i Evident „Material Sound Velocities“.

Záměrně chybí litina (velký rozptyl podle struktury – nutno zadat) a titan (zdroje se u c_T
liší: 3 120 × 3 300 m/s).
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from skodacad.materials import material_key
from skodacad.ndt.devices import LABELS, ORIGINS, DeviceError, Probe
from skodacad.ndt.ut import SPEED_LIMITS, WAVES, BeamError

LIBRARY_VERSION = "ndt-knihovna 1"
BUILTIN = f"vestavěná knihovna {LIBRARY_VERSION}"
USER_LIBRARY = "Moje sondy"
USER_FILE = "ndt-knihovna.json"
USER_FORMAT = "skodacad-ndt-knihovna"
USER_VERSION = 1
ORIENTATIVE = ("Orientační hodnoty z literatury – skutečná rychlost závisí na slitině, "
               "zpracování a teplotě, přesně se měří na vzorku.")


class LibraryError(ValueError):
    """Chybný záznam knihovny nebo soubor Mých sond (zpráva česky)."""


# --- materiály -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Material:
    """Rychlosti zvuku v materiálu pro UT [m/s]; 0 = neuvedeno (aspoň jedna musí být)."""

    name: str
    c_l: float
    c_t: float
    source: str
    profile: str = ""  # klíč vestavěného profilu, "" = vlastní materiál
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 100:
            raise LibraryError("Materiál pro UT musí mít název (nejvýš 100 znaků).")
        for key in ("source", "profile", "note"):
            if not isinstance(getattr(self, key), str) or len(getattr(self, key)) > 500:
                raise LibraryError(f"Materiál „{self.name}“: „{key}“ musí být text.")
        low, high = SPEED_LIMITS
        for key, label in (("c_l", "podélná"), ("c_t", "příčná")):
            value = getattr(self, key)
            if (not isinstance(value, int | float) or isinstance(value, bool)
                    or not math.isfinite(value) or not (value == 0 or low <= value <= high)):
                raise LibraryError(f"Materiál „{self.name}“: {label} rychlost musí být 0 "
                                   f"(neuvedeno) nebo {low:g}–{high:g} m/s (je {value!r}).")
        if not self.c_l and not self.c_t:
            raise LibraryError(f"Materiál „{self.name}“ potřebuje aspoň jednu rychlost zvuku.")
        if self.c_l and self.c_t and self.c_t >= self.c_l:
            raise LibraryError(f"Materiál „{self.name}“: příčná rychlost bývá menší než podélná "
                               f"({self.c_t:g} ≥ {self.c_l:g} m/s) – zkontroluj zadání.")
        if not self.source.strip():
            raise LibraryError(f"Materiál „{self.name}“: uveď zdroj rychlostí (literatura, "
                               "měření na vzorku …).")

    @property
    def key(self) -> str:
        return self.profile or material_key(self.name)

    def velocity(self, wave: str) -> float:
        """Rychlost pro druh vlny (shear = příčná, longitudinal = podélná); 0 = neuvedeno."""
        return self.c_t if wave == "shear" else self.c_l

    def to_dict(self) -> dict[str, Any]:
        data = {"name": self.name, "c_l": _clean(self.c_l), "c_t": _clean(self.c_t),
                "source": self.source}
        for key in ("profile", "note"):
            if getattr(self, key):
                data[key] = getattr(self, key)
        return data

    @classmethod
    def from_dict(cls, data: Any) -> Material:
        if not isinstance(data, dict):
            raise LibraryError('Materiál pro UT musí být objekt {"name": …, "c_l": …, "c_t": …, '
                               '"source": …}.')
        unknown = sorted(set(data) - {"name", "c_l", "c_t", "source", "profile", "note"})
        if unknown:
            raise LibraryError(f"Materiál pro UT: neznámá položka „{unknown[0]}“.")
        return cls(data.get("name", ""), data.get("c_l", 0), data.get("c_t", 0),
                   data.get("source", ""), data.get("profile", ""), data.get("note", ""))

    @property
    def text(self) -> str:
        speeds = ", ".join(f"{label} {value:g} m/s" for label, value
                           in (("podélná", self.c_l), ("příčná", self.c_t)) if value)
        return f"{self.name} – {speeds}"


_SOURCES = {
    "ocel": "materialwelding.com, Class Instrumentation (c_L); materialwelding.com, Dakota NDT, "
            "NDT Systems (c_T)",
    "nerez": "Cygnus, materialwelding.com (c_L); materialwelding.com, Dakota NDT, NDT Systems "
             "(c_T)",
    "hlinik": "Olympus/Evident Technical Notes, materialwelding.com, Evident (c_L)",
    "med": "Olympus/Evident Technical Notes, materialwelding.com, Evident (c_L)",
    "mosaz": "Olympus/Evident Technical Notes, materialwelding.com, Evident (c_L)",
}
MATERIALS = {
    "ocel": Material("ocel", 5920, 3240, _SOURCES["ocel"], "ocel",
                     "uhlíková a nízkolegovaná ocel"),
    "nerez": Material("nerez", 5660, 3120, _SOURCES["nerez"], "nerez",
                      "austenitická (302/304); svary austenitu jsou anizotropní – skutečná "
                      "dráha svazku se ohýbá, geometrický výsledek je jen orientační"),
    "hlinik": Material("hliník", 6320, 3130, _SOURCES["hlinik"], "hlinik", "válcovaný"),
    "med": Material("měď", 4660, 2260, _SOURCES["med"], "med"),
    "mosaz": Material("mosaz", 4430, 2120, _SOURCES["mosaz"], "mosaz", "lodní mosaz"),
}


def find_material(name: str, user: dict[str, Material] | None = None) -> Material | None:
    """Vestavěný profil podle názvu („Hliník“ = „hlinik“), jinak vlastní materiál z Mých sond."""
    key = material_key(name)
    if key in MATERIALS:
        return MATERIALS[key]
    return next((m for m in (user or {}).values() if material_key(m.name) == key), None)


def same_material(a: str, b: str) -> bool:
    return bool(a) and material_key(a) == material_key(b)


# --- obecné profily sond ---------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeProfile:
    key: str
    name: str
    probe: Probe


def _generic_probes() -> dict[str, ProbeProfile]:
    """Typické řády velikosti, ne konkrétní výrobek; úhlové s úhlem v oceli 45/60/70°."""
    found: dict[str, ProbeProfile] = {}
    for diameter, height in ((10, 25), (20, 30)):
        name = f"Obecná přímá Ø {diameter} × {height} mm"
        found[f"prima-{diameter}"] = ProbeProfile(f"prima-{diameter}", name, Probe.straight(
            diameter, height, profile=name, library=BUILTIN,
            origins={"diameter": "profile", "height": "profile"}))
    sizes = (("mala", "malá (stísněná místa)", 25, 12, 20, 7),
             ("standardni", "standardní", 40, 20, 25, 12),
             ("velka", "velká", 50, 25, 30, 16))
    for size, label, length, width, height, front in sizes:
        for angle in (45, 60, 70):
            key = f"uhlova-{size}-{angle}"
            name = (f"Obecná úhlová {label} {length} × {width} × {height} mm, "
                    f"{angle}° v oceli")
            found[key] = ProbeProfile(key, name, Probe.angle(
                length, width, height, front, beam_angle=angle, profile=name, library=BUILTIN,
                angle_material="ocel",
                origins={k: "profile" for k in ("length", "width", "height", "front",
                                                "beam_angle")}))
    return found


PROBES = _generic_probes()


# --- přenos úhlu mezi materiály ---------------------------------------------------------------


def transfer_angle(beta: float, c_from: float, c_to: float) -> float:
    """Úhel v jiném materiálu se stejnou předsádkou: sin β / c je podle Snellova zákona stálé,
    takže β₂ = arcsin(c₂ / c₁ · sin β₁). Úhel ani rychlost v předsádce nejsou potřeba."""
    low, high = SPEED_LIMITS
    for value, label in ((c_from, "výchozím"), (c_to, "cílovém")):
        if not (low <= value <= high):
            raise BeamError(f"Rychlost zvuku v {label} materiálu musí být {low:g}–{high:g} m/s "
                            f"(je {value:g}).")
    if not 0 < beta < 90:
        raise BeamError(f"Úhel k přepočtu musí být mezi 0° a 90° (je {beta:g}°).")
    sine = c_to / c_from * math.sin(math.radians(beta))
    if sine >= 1 - 1e-9:
        raise BeamError(f"Úhel {beta:g}° při rychlostech {c_from:g} → {c_to:g} m/s nastává "
                        "totální odraz – vlna do materiálu dílu nevstoupí.")
    return math.degrees(math.asin(sine))


@dataclass(frozen=True)
class AngleCheck:
    """Platí úhel sondy v materiálu pro UT? ``state``: none (nic ke kontrole – úhel platí přímo
    v materiálu dílu), ok, differs (jde přepočítat), unknown (chybí údaje), error (nejde)."""

    state: str
    text: str = ""
    beta_from: float = 0.0
    beta_to: float | None = None
    material_from: str = ""
    material_to: str = ""
    wave: str = ""
    c_from: float = 0.0
    c_to: float = 0.0

    @property
    def note(self) -> str:
        """Záznam do sondy po přepočtu (původ úhlu)."""
        return (f"přepočteno z {self.beta_from:g}° v materiálu „{self.material_from}“ – "
                f"Snellův zákon, {WAVES[self.wave]} vlna {self.c_from:g} → {self.c_to:g} m/s")


def check_angle(probe: Probe, material: Material | None, part_material: str = "",
                user: dict[str, Material] | None = None) -> AngleCheck:
    """Porovná materiál, ve kterém platí úhel sondy, s materiálem pro UT (bez něj s dílem).
    Nic nepřepočítává – přepočet je jen na výslovný pokyn (``AngleCheck.beta_to``)."""
    if probe.kind != "angle" or not probe.angle_material:
        return AngleCheck("none")
    source = probe.angle_material
    beta = probe.beam_angle
    target = material.name if material is not None else part_material
    if same_material(source, target):
        return AngleCheck("ok", f"Úhel {beta:g}° platí v materiálu „{source}“ – shoduje se "
                                "s materiálem pro UT.", beta, beta, source, target)
    if material is None:
        part = f"díl je z materiálu „{part_material}“ a " if part_material else ""
        return AngleCheck("unknown", f"Úhel sondy {beta:g}° platí v materiálu „{source}“, "
                                     f"{part}materiál pro UT není zvolený – zvol ho, aby šel "
                                     "úhel přepočítat.", beta, None, source)
    reference = find_material(source, user)
    wave = probe.wave_mode
    c_from = reference.velocity(wave) if reference is not None else 0.0
    c_to = material.velocity(wave)
    if not c_from or not c_to:
        missing = source if not c_from else material.name
        return AngleCheck("unknown", f"Úhel sondy {beta:g}° platí v materiálu „{source}“, "
                                     f"ale {WAVES[wave]} rychlost zvuku v materiálu "
                                     f"„{missing}“ neznám – přepočet nejde. Zadej úhel přímo "
                                     "v materiálu dílu.", beta, None, source, material.name, wave)
    try:
        beta_to = transfer_angle(beta, c_from, c_to)
    except BeamError as exc:
        return AngleCheck("error", f"Úhel sondy nejde přepočítat: {exc}", beta, None, source,
                          material.name, wave, c_from, c_to)
    return AngleCheck("differs", f"Úhel sondy {beta:g}° platí v materiálu „{source}“, materiál "
                                 f"pro UT je „{material.name}“ – v něm je asi {beta_to:.1f}° "
                                 f"(Snellův zákon, {WAVES[wave]} vlna {c_from:g} → {c_to:g} "
                                 "m/s). Přepočítej úhel.",
                      beta, beta_to, source, material.name, wave, c_from, c_to)


def transferred(probe: Probe, check: AngleCheck) -> Probe:
    """Sonda s úhlem přepočteným do materiálu pro UT (jen pro ``check.state == "differs"``)."""
    if check.state != "differs" or check.beta_to is None:
        raise BeamError(check.text or "Úhel sondy není co přepočítat.")
    origins = {**dict(probe.origins), "beam_angle": "transferred"}
    return replace(probe, beam_angle=round(check.beta_to, 2), angle_material=check.material_to,
                   angle_note=check.note, origins=tuple(sorted(origins.items())))


# --- popis do souhrnu, CSV a příkazové řádky ----------------------------------------------------


def describe(probe: Probe, material: Material | None = None,
             check: AngleCheck | None = None) -> list[str]:
    """Řádky o sondě a materiálu pro výstupy. Bez profilu, původu a materiálu prázdné –
    výstupy starých modelů zůstanou beze změny."""
    lines: list[str] = []
    if probe.profile:
        lines.append(f"Profil sondy: {probe.profile} ({probe.library or 'bez knihovny'}).")
    if probe.origins:
        groups: dict[str, list[str]] = {}
        for key, origin in probe.origins:
            groups.setdefault(ORIGINS[origin], []).append(LABELS[key].lower())
        lines.append("Původ hodnot sondy: " + "; ".join(
            f"{origin} – {', '.join(keys)}" for origin, keys in groups.items()) + ".")
    if probe.kind == "angle" and probe.angle_material:
        lines.append(f"Úhel {probe.beam_angle:g}° platí v materiálu „{probe.angle_material}“"
                     + (f"; {probe.angle_note}" if probe.angle_note else "") + ".")
    if material is not None:
        orientative = f" {ORIENTATIVE}" if material.profile in MATERIALS else ""
        lines.append(f"Materiál pro UT: {material.text}; zdroj: {material.source}."
                     + orientative)
        if material.note:
            lines.append(f"Poznámka k materiálu: {material.note}.")
    if check is not None and check.state in ("differs", "unknown", "error"):
        lines.append(check.text)
    info = [text for value, text in ((probe.frequency_mhz, f"frekvence {probe.frequency_mhz:g} "
                                                           "MHz"),
                                     (probe.crystal_mm, f"měnič Ø {probe.crystal_mm:g} mm"))
            if value]
    if info:
        joined = ", ".join(info)
        lines.append(f"{joined[0].upper()}{joined[1:]} – jen informativně, výpočet je "
                     "nepoužívá.")
    if probe.source:
        lines.append(f"Zdroj údajů sondy: {probe.source}.")
    return lines


# --- Moje sondy (soubor v profilu uživatele) ----------------------------------------------------


def user_dir() -> Path:
    """Složka SkodaCAD v profilu uživatele (jako okno; SKODACAD_HOME ji přepíše)."""
    base = os.environ.get("SKODACAD_HOME")
    return Path(base) if base else Path.home() / "SkodaCAD"


def user_library_path(folder: Path | None = None) -> Path:
    return (folder or user_dir()) / USER_FILE


@dataclass
class UserLibrary:
    """Moje sondy a moje materiály; vadné záznamy se vynechají a popíšou v ``problems``."""

    path: Path
    probes: dict[str, Probe] = field(default_factory=dict)
    materials: dict[str, Material] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def load_user_library(path: Path) -> UserLibrary:
    """Načte Moje sondy. Chybějící soubor = prázdná knihovna, poškozený = česká hláška
    v ``problems`` (vestavěné profily fungují dál)."""
    library = UserLibrary(Path(path))
    if not library.path.exists():
        return library
    try:
        data = _read(library.path)
    except LibraryError as exc:
        library.problems.append(str(exc))
        return library
    for number, entry in enumerate(data.get("probes", []), start=1):
        try:
            if not isinstance(entry, dict) or set(entry) - {"name", "device"}:
                raise LibraryError('sonda musí být {"name": …, "device": {…}}')
            name = _name(entry.get("name"))
            library.probes[name] = replace(Probe.from_dict(entry.get("device")), profile=name,
                                           library=USER_LIBRARY)
        except (LibraryError, DeviceError) as exc:
            library.problems.append(f"Moje sondy: sonda č. {number} vynechána – {exc}")
    for number, entry in enumerate(data.get("materials", []), start=1):
        try:
            material = Material.from_dict(entry)
            library.materials[material.name] = replace(material, profile="")
        except LibraryError as exc:
            library.problems.append(f"Moje sondy: materiál č. {number} vynechán – {exc}")
    return library


def save_user_probe(path: Path, name: str, probe: Probe) -> Probe:
    """Uloží (nebo přepíše stejnojmennou) sondu do Mých sond a vrátí ji, jak bude ve studii."""
    stored = replace(probe, profile=_name(name), library=USER_LIBRARY)
    data = _read(Path(path)) if Path(path).exists() else _empty()
    record = stored.to_dict()
    for key in ("profile", "library"):
        record.pop(key, None)
    probes = [p for p in data["probes"]
              if not isinstance(p, dict) or p.get("name") != stored.profile]
    data["probes"] = [*probes, {"name": stored.profile, "device": record}]
    _write(Path(path), data)
    return stored


def save_user_material(path: Path, material: Material) -> Material:
    """Uloží (nebo přepíše stejnojmenný) vlastní materiál do Mých sond."""
    stored = replace(material, profile="")
    data = _read(Path(path)) if Path(path).exists() else _empty()
    materials = [m for m in data["materials"]
                 if not isinstance(m, dict) or m.get("name") != stored.name]
    data["materials"] = [*materials, stored.to_dict()]
    _write(Path(path), data)
    return stored


def _empty() -> dict[str, Any]:
    return {"format": USER_FORMAT, "version": USER_VERSION, "probes": [], "materials": []}


def _read(path: Path) -> dict[str, Any]:
    """Obsah souboru Mých sond; poškozený soubor se nikdy nepřepíše (LibraryError)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LibraryError(f"Soubor Mých sond {path} nejde přečíst ({exc}) – oprav ho nebo "
                           "smaž, vestavěné profily fungují dál.") from None
    if (not isinstance(data, dict) or data.get("format") != USER_FORMAT
            or not isinstance(data.get("probes", []), list)
            or not isinstance(data.get("materials", []), list)):
        raise LibraryError(f"Soubor {path} není soubor Mých sond ŠkodaCAD – nechávám ho beze "
                           "změny.")
    if data.get("version", 0) > USER_VERSION:
        raise LibraryError(f"Soubor Mých sond {path} je z novější verze programu – nechávám ho "
                           "beze změny.")
    return {**_empty(), **data}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise LibraryError("název musí být neprázdný text (nejvýš 100 znaků)")
    return value.strip()


def _clean(value: float) -> float | int:
    return int(value) if float(value).is_integer() else value
