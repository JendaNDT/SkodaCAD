"""AI asistent: úpravy modelu podle popisu přes Claude API (Anthropic).

Claude dostane popis formátu modelu (část README a schéma prvků), aktuální model a
nástroje, které model mění **stejnými kroky jako okno** (``ModelSession`` – kontrola,
Zpět). Po každé změně vidí výsledek přepočtu (chyby prvků, objem, rozměry), takže si
úpravu sám ověří a opraví. Celá jedna odpověď je jeden krok Zpět (``begin_group``).

Modul nesahá na Qt – okno ho volá z pomocného vlákna a nástroje provádí v hlavním vlákně
(``ToolRunner``), příkazová řádka přímo. Síť jde jen přes oficiální knihovnu ``anthropic``
(načte se až při prvním dotazu).
"""

from __future__ import annotations

import base64
import copy
import json
import os
import sys
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from skodacad.document import DocumentError
from skodacad.features import describe
from skodacad.materials import DENSITIES_G_CM3
from skodacad.schema import FEATURE_SCHEMAS, SHAPE_SCHEMAS

MODELS = {
    "claude-opus-5-5": "Claude Opus 5.5 – nejschopnější",
    "claude-sonnet-5-5": "Claude Sonnet 5.5 – poloviční cena",
}
DEFAULT_MODEL = "claude-opus-5-5"
EFFORTS = {"low": "rychle a levně", "medium": "vyváženě", "high": "důkladně"}
DEFAULT_EFFORT = "high"
# Ceny v USD za milion tokenů: vstup, výstup, čtení z mezipaměti, zápis do mezipaměti (5 min).
PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20, 5.0), "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.5)}
USD_CZK = 23.0  # orientační kurz – cena v aplikaci je jen odhad
MAX_TOKENS = 64000
MAX_ROUNDS = 40  # pojistka proti nekonečné smyčce (a útratě)
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # odmítnutý dotaz zkusí záložní model
SETTINGS_FILE = "nastaveni.json"
KEY_URL = "https://console.anthropic.com/settings/keys"


class AssistantError(Exception):
    """Asistent nemohl odpovědět (zpráva je česky pro uživatele)."""


class Cancelled(AssistantError):
    def __init__(self) -> None:
        super().__init__("Zastaveno – úpravy, které AI do té doby udělala, zůstaly (vrátíš je "
                         "jedním Zpět).")


# --- nastavení ----------------------------------------------------------------------------


@dataclass
class AssistantSettings:
    """API klíč, model a důkladnost. Ukládá se do ``nastaveni.json`` v profilu uživatele."""

    api_key: str = ""
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT

    @classmethod
    def load(cls, path: Path) -> AssistantSettings:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8")).get("ai", {})
        except (OSError, ValueError, AttributeError):
            return cls()
        settings = cls(api_key=str(data.get("api_key", "")).strip())
        if data.get("model") in MODELS:
            settings.model = data["model"]
        if data.get("effort") in EFFORTS:
            settings.effort = data["effort"]
        return settings

    def save(self, path: Path) -> None:
        """Uloží nastavení AI (ostatní položky souboru nechá být)."""
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data["ai"] = asdict(self)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if sys.platform != "win32":
            path.chmod(0o600)  # klíč smí číst jen uživatel (ve Windows je profil soukromý)

    def key(self) -> str:
        """API klíč z nastavení, jinak z proměnné prostředí ANTHROPIC_API_KEY."""
        return self.api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()


def user_dir() -> Path:
    """Složka SkodaCAD v profilu uživatele (jako okno; SKODACAD_HOME ji přepíše)."""
    base = os.environ.get("SKODACAD_HOME")
    return Path(base) if base else Path.home() / "SkodaCAD"


def settings_path(folder: Path) -> Path:
    return Path(folder) / SETTINGS_FILE


def make_client(settings: AssistantSettings, **options: Any) -> Any:
    """Klient Claude API (knihovna anthropic). Bez klíče česká chyba s návodem."""
    key = settings.key()
    if not key:
        raise AssistantError(
            "Chybí API klíč Claude. Vytvoř ho na console.anthropic.com (Settings → API keys, "
            "účet s kreditem – předplatné Claude.ai API nezahrnuje) a vlož ho v Nastavení AI.")
    import anthropic

    return anthropic.Anthropic(api_key=key, max_retries=3, **options)


# --- spotřeba a cena -------------------------------------------------------------------


@dataclass
class Usage:
    """Spotřebované tokeny (za konverzaci) a odhad ceny."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def add(self, usage: Any) -> None:
        self.input += getattr(usage, "input_tokens", 0) or 0
        self.output += getattr(usage, "output_tokens", 0) or 0
        self.cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0

    @property
    def tokens(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write

    def cost_usd(self, model: str) -> float:
        price_in, price_out, price_read, price_write = PRICES.get(model, PRICES[DEFAULT_MODEL])
        return (self.input * price_in + self.output * price_out + self.cache_read * price_read
                + self.cache_write * price_write) / 1e6

    def describe(self, model: str) -> str:
        czk = self.cost_usd(model) * USD_CZK
        tokens = f"{self.tokens:,}".replace(",", " ")
        return f"{tokens} tokenů, orientačně {czk:.2f} Kč".replace(".", ",")


# --- nástroje (co smí Claude s modelem dělat) ----------------------------------------


def _tool(name: str, description: str, properties: dict[str, Any],
          required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"name": name, "description": description, "eager_input_streaming": True,
            "input_schema": {"type": "object", "properties": properties,
                             "required": list(required)}}


_ANY_VALUE = {"description": "Číslo v mm/stupních nebo výraz s parametry (text).",
              "type": ["number", "string"]}

MODEL_TOOLS = [
    _tool("get_model", "Vrátí aktuální model (JSON) a výsledek přepočtu. Použij, když si "
          "nejsi jistý, jak model teď vypadá.", {}),
    _tool("set_parameters", "Nastaví hodnoty parametrů (nové přidá). Hodnota je číslo nebo "
          "výraz s jinými parametry, např. \"D - 40\".",
          {"values": {"type": "object", "additionalProperties": _ANY_VALUE,
                      "description": "Název parametru → hodnota, např. {\"D\": 200}."}},
          ("values",)),
    _tool("delete_parameter", "Smaže nepoužívaný parametr.",
          {"name": {"type": "string"}}, ("name",)),
    _tool("add_feature", "Přidá prvek do stromu (za prvek „after“, jinak na konec). "
          "„feature“ je objekt prvku podle formátu (type povinný, id volitelné – čitelné "
          "a jedinečné, např. „zakladni_deska“). Chybějící hodnoty doplní výchozí.",
          {"feature": {"type": "object", "description": "Prvek, např. {\"type\": \"hole\", "
                                                        "\"kind\": \"tapped\", …}."},
           "after": {"type": ["string", "null"], "description": "Id prvku, za který vložit."}},
          ("feature",)),
    _tool("update_feature", "Změní hodnoty prvku: klíče v „changes“ se přepíšou, hodnota "
          "null klíč smaže. Id ani typ prvku změnit nejde.",
          {"id": {"type": "string"}, "changes": {"type": "object"}}, ("id", "changes")),
    _tool("delete_feature", "Smaže prvek (nejde, když ho používá jiný prvek).",
          {"id": {"type": "string"}}, ("id",)),
    _tool("move_feature", "Přesune prvek ve stromu za prvek „after“ (null = na začátek).",
          {"id": {"type": "string"}, "after": {"type": ["string", "null"]}}, ("id", "after")),
    _tool("set_part_info", "Změní název, materiál nebo popis dílu.",
          {"name": {"type": "string"}, "material": {"type": "string"},
           "description": {"type": "string"}}),
    _tool("replace_model", "Nahradí celý model novým (nový díl z popisu nebo velká "
          "přestavba). „model“ je celý JSON modelu (name, material, parameters, features …; "
          "format a version se doplní). NDT studie (ndt) uživatele zůstanou, když je v modelu "
          "výslovně neuvedeš.",
          {"model": {"type": "object"}}, ("model",)),
]
VIEW_TOOL = _tool(
    "view_part", "Pořídí obrázek dílu ve 3D (stínovaný, jak ho vidí uživatel) – na kontrolu "
    "vzhledu, např. po větší úpravě. Stojí víc tokenů, používej s rozmyslem.",
    {"view": {"type": "string", "enum": ["current", "iso", "front", "top", "right"],
              "description": "current = pohled uživatele, jinak standardní pohled."}},
    ("view",))
VIEW_NAMES = {"current": "aktuální pohled", "iso": "izometrie", "front": "zepředu",
              "top": "shora", "right": "zprava"}


@dataclass
class ToolOutput:
    """Výsledek nástroje pro Claude: text (nebo seznam bloků s obrázkem) a zda šlo o chybu."""

    content: str | list[dict[str, Any]]
    is_error: bool = False
    changed: bool = False  # změnil model → po přepočtu se přidá souhrn

    def block(self, tool_use_id: str) -> dict[str, Any]:
        block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": self.content}
        if self.is_error:
            block["is_error"] = True
        return block


class ToolInputError(ValueError):
    pass


def _text(data: dict[str, Any], key: str, required: bool = True) -> str | None:
    value = data.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError(f"Chybí „{key}“ (text).")
    return value


def _object(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ToolInputError(f"Chybí „{key}“ (objekt).")
    return value


class ModelTools:
    """Nástroje nad otevřeným modelem (``ModelSession``). ``look(view)`` vrátí PNG dílu
    (jen v okně – příkazová řádka obrázky nemá)."""

    def __init__(self, session: Any, look: Callable[[str], bytes | None] | None = None):
        self.session = session
        self.look = look

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return [*MODEL_TOOLS, VIEW_TOOL] if self.look else list(MODEL_TOOLS)

    # --- popis kroku pro uživatele --------------------------------------------------

    @staticmethod
    def explain(name: str, data: Any) -> str:
        """Co asistent právě dělá, česky (do panelu a příkazové řádky)."""
        data = data if isinstance(data, dict) else {}
        if name == "set_parameters" and isinstance(data.get("values"), dict):
            values = ", ".join(f"{k} = {v}" for k, v in data["values"].items())
            return f"Nastavuji parametry: {values}"
        if name == "add_feature" and isinstance(data.get("feature"), dict):
            feature = data["feature"]
            schema = FEATURE_SCHEMAS.get(feature.get("type"))
            label = schema.label if schema else str(feature.get("type"))
            title = feature.get("name") or feature.get("id") or ""
            return f"Přidávám prvek: {label} {title}".rstrip()
        if name == "update_feature":
            keys = ", ".join(data.get("changes", {}) or {}) if isinstance(
                data.get("changes"), dict) else ""
            return f"Upravuji prvek {data.get('id', '?')}: {keys}"
        if name == "replace_model" and isinstance(data.get("model"), dict):
            count = len(data["model"].get("features") or [])
            return f"Skládám celý model znovu ({count} prvků)"
        if name == "view_part":
            return f"Dívám se na díl ({VIEW_NAMES.get(data.get('view'), 'pohled')})"
        texts = {"get_model": "Čtu model", "delete_parameter": "Mažu parametr {name}",
                 "delete_feature": "Mažu prvek {id}", "move_feature": "Přesouvám prvek {id}",
                 "set_part_info": "Měním údaje dílu"}
        return texts.get(name, name).format(name=data.get("name", "?"),
                                             id=data.get("id", "?"))

    # --- provedení ------------------------------------------------------------------

    def apply(self, name: str, data: Any) -> ToolOutput:
        """Provede nástroj. Chyby (špatný vstup, odmítnutá změna) vrátí Claudovi česky."""
        if not isinstance(data, dict):
            return ToolOutput("Vstup nástroje musí být JSON objekt.", is_error=True)
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return ToolOutput(f"Neznámý nástroj „{name}“.", is_error=True)
        try:
            return handler(data)
        except ToolInputError as exc:
            return ToolOutput(f"Chybný vstup nástroje {name}: {exc}", is_error=True)
        except DocumentError as exc:
            return ToolOutput(f"Změna se nepřijala, model je beze změny: {exc}", is_error=True)

    def run(self, name: str, data: Any) -> ToolOutput:
        """Provede nástroj, počká na přepočet a přidá jeho souhrn (bez okna, synchronně)."""
        output = self.apply(name, data)
        if output.changed:
            self.session.wait()
            output.content = f"{output.content}\n\n{self.report()}"
        return output

    def report(self) -> str:
        return build_report(self.session)

    def _tool_get_model(self, data: dict[str, Any]) -> ToolOutput:
        return ToolOutput(f"{model_json(self.session)}\n\n{self.report()}")

    def _tool_set_parameters(self, data: dict[str, Any]) -> ToolOutput:
        values = _object(data, "values")
        if not values:
            raise ToolInputError("„values“ je prázdné.")
        for name, value in values.items():
            if not isinstance(value, (int, float, str)) or isinstance(value, bool):
                raise ToolInputError(f"Hodnota parametru „{name}“ musí být číslo nebo výraz.")
        for name, value in values.items():
            if name in self.session.document.parameters:
                self.session.set_parameter(name, str(value))
            else:
                self.session.add_parameter(name, str(value))
        return ToolOutput("Parametry nastaveny.", changed=True)

    def _tool_delete_parameter(self, data: dict[str, Any]) -> ToolOutput:
        self.session.delete_parameter(_text(data, "name"))
        return ToolOutput("Parametr smazán.", changed=True)

    def _tool_add_feature(self, data: dict[str, Any]) -> ToolOutput:
        feature = _object(data, "feature")
        kind = _text(feature, "type")
        after = data.get("after")
        if after is not None and not isinstance(after, str):
            raise ToolInputError("„after“ musí být id prvku nebo null.")
        wanted = feature.get("id")
        if wanted is not None and not isinstance(wanted, str):
            raise ToolInputError("„id“ prvku musí být text.")
        new_id = self.session.add_feature(kind, after or None, feature, feature_id=wanted)
        return ToolOutput(f"Prvek přidán s id „{new_id}“.", changed=True)

    def _tool_update_feature(self, data: dict[str, Any]) -> ToolOutput:
        feature_id = _text(data, "id")
        changes = _object(data, "changes")
        feature = self.session.feature(feature_id)
        for key, value in changes.items():
            if key in ("id", "type") and value != feature.get(key):
                raise ToolInputError("U prvku nejde změnit id ani typ – přidej nový prvek.")
            if value is None:
                feature.pop(key, None)
            else:
                feature[key] = copy.deepcopy(value)
        self.session.update_feature(feature_id, feature)
        return ToolOutput("Prvek upraven.", changed=True)

    def _tool_delete_feature(self, data: dict[str, Any]) -> ToolOutput:
        self.session.delete_feature(_text(data, "id"))
        return ToolOutput("Prvek smazán.", changed=True)

    def _tool_move_feature(self, data: dict[str, Any]) -> ToolOutput:
        feature_id = _text(data, "id")
        after = data.get("after")
        index = self.session.feature_index(feature_id)
        if after is None:
            target = 0
        else:
            target = self.session.feature_index(_text(data, "after"))
            target += 0 if target > index else 1
        self.session.move_feature(feature_id, target - index)
        return ToolOutput("Prvek přesunut.", changed=True)

    def _tool_set_part_info(self, data: dict[str, Any]) -> ToolOutput:
        values = {key: data.get(key) for key in ("name", "material", "description")}
        if all(value is None for value in values.values()):
            raise ToolInputError("Zadej aspoň jedno z name, material, description.")
        for key, value in values.items():
            if value is not None and not isinstance(value, str):
                raise ToolInputError(f"„{key}“ musí být text.")
        self.session.set_info(**values)
        return ToolOutput("Údaje dílu změněny.", changed=True)

    def _tool_replace_model(self, data: dict[str, Any]) -> ToolOutput:
        model = copy.deepcopy(_object(data, "model"))
        current = self.session.document
        kept = "ndt" not in model and current is not None and bool(current.ndt)
        if kept:  # studie jsou práce uživatele – přestavba dílu je jen označí jako zastaralé
            model["ndt"] = copy.deepcopy(current.ndt)
        self.session.replace_document(model)
        return ToolOutput("Model nahrazen." + (" NDT studie uživatele zůstaly." if kept else ""),
                          changed=True)

    def _tool_view_part(self, data: dict[str, Any]) -> ToolOutput:
        view = data.get("view", "current")
        if view not in VIEW_NAMES:
            raise ToolInputError(f"Neznámý pohled „{view}“.")
        image = self.look(view) if self.look else None
        if not image:
            return ToolOutput("Obrázek dílu teď nejde pořídit (žádný díl nebo okno bez 3D).",
                              is_error=True)
        return ToolOutput([
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.standard_b64encode(image).decode()}},
            {"type": "text", "text": f"Díl – {VIEW_NAMES[view]}."},
        ])


def model_json(session: Any) -> str:
    return json.dumps(session.document.to_dict(), ensure_ascii=False, indent=1)


def build_report(session: Any) -> str:
    """Souhrn přepočtu pro Claude: stav prvků, objem, hmotnost, rozměry, měření."""
    result = session.result
    if session.failure:
        return f"Přepočet se nepovedl: {session.failure}"
    if result is None:
        return "Model zatím není spočítaný."
    params = result.parameters
    lines = ["Přepočet: " + ("v pořádku" if result.ok else "NĚKTERÉ PRVKY MAJÍ CHYBU"), "Prvky:"]
    by_id = {feature["id"]: feature for feature in session.document.features}
    for status in result.statuses:
        mark = {"ok": "✓", "error": "✕", "skipped": "–"}.get(status.status, "?")
        feature = by_id.get(status.id)
        text = describe(feature, params) if feature else status.label
        line = f"  {mark} [{status.id}] {text}"
        if status.status == "error":
            line += f" – CHYBA: {status.message}"
        elif status.status == "skipped":
            line += " – přeskočeno (kvůli chybě výš)"
        lines.append(line)
    if params:
        lines.append("Parametry (vyčíslené): " + ", ".join(f"{k} = {v:g}"
                                                          for k, v in params.items()))
    props = session.properties
    if props is not None and result.part is not None:
        box = result.part.bounding_box()
        mass = (f"{props.mass_kg:.4f} kg" if props.mass_kg is not None
                else "neznámá (materiál bez hustoty)")
        lines.append(
            f"Díl: objem {props.volume_mm3:.1f} mm³, hmotnost {mass} "
            f"({session.document.material}), povrch {props.area_mm2:.1f} mm², "
            f"těles {props.solids}")
        lines.append(f"Obalový kvádr: X {box.min.X:.2f}…{box.max.X:.2f}, "
                     f"Y {box.min.Y:.2f}…{box.max.Y:.2f}, Z {box.min.Z:.2f}…{box.max.Z:.2f} mm")
    else:
        lines.append("Díl zatím nemá žádné těleso.")
    for measurement in result.measurements:
        lines.append(f"Měření „{measurement.name}“: {measurement.text}")
    for study in result.ndt:
        details = "; ".join(study.messages)
        lines.append(f"NDT studie [{study.id}] „{study.name}“ ({study.method}): {study.label}"
                     + (f" – {details}" if details else ""))
    return "\n".join(lines)


# --- systémový pokyn ------------------------------------------------------------------


RULES = """Jsi asistent v ŠkodaCAD – osobním parametrickém 3D CAD (strojní díly, NDT, 3D tisk,
krabičky na elektroniku). Model je čitelný JSON „recept“: parametry a strom prvků (skica,
vysunutí, díra, zaoblení …), z něhož jádro (build123d / OCCT) postaví díl. Uživatel
neprogramuje; mluví česky a ty odpovídáš česky, stručně a lidsky, bez žargonu.

Jak pracuješ:
- Model měníš jen nástroji. Každá změna se hned přepočítá a dostaneš souhrn (stav prvků,
  objem, rozměry). Po úpravě ho zkontroluj: když má prvek chybu nebo rozměry nesedí s
  požadavkem, oprav to. Nevzdávej se po první chybě, ale nedělej zbytečné kroky.
- Malé změny dělej nástroji set_parameters / add_feature / update_feature; nový díl od nuly
  nebo velkou přestavbu jedním replace_model.
- Klíčové rozměry dávej do parametrů (krátké názvy: D, L, t, roztec …) a ve prvcích používej
  výrazy – uživatel pak díl snadno mění. Prvky pojmenuj česky („name“) a dej jim čitelná id.
- Jednotky jsou vždy mm, úhly ve stupních. Plochy a hrany vybírej jen významem (top,
  bottom, front …, výběry hran podle formátu), nikdy pořadovým číslem.
- Díry dělej prvkem hole (strojnické tabulky), šrouby, matice, ložiska a ocelové profily
  prvkem standard – ne ručně kreslenými kružnicemi.
- Když něco nejde nebo zadání není jasné, řekni to a navrhni možnost. Neodhaduj rozměry,
  které uživatel nezadal, aniž bys to řekl.
- NDT studie (sekce ndt) měň jen na výslovné přání. Výsledky NDT (pokrytí, detekovatelnost
  vad, shodu s normou) nikdy neodhaduj ani nevymýšlej – počítá je program, zatím jen
  geometricky. Když po tvé změně dílu studie zastará, řekni to; potvrdit ji musí uživatel.
- UT v ŠkodaCAD posuzuje jen přístupnost sondy a geometrické pokrytí. Netvrď nic
  o prozvučitelnosti materiálu (útlum, struktura, akustická vazba) ani o tom, že by se vada
  našla – geometricky pokryté místo není důkaz detekce. Rady k poloze sondy nebo změně dílu
  dávej jen kvůli přístupnosti a pokrytí.
- PT (kapilární zkouška) v ŠkodaCAD posuzuje jen geometrickou přístupnost povrchu (nástřik,
  otření nástrojem, prohlídka). Výsledky PT nevymýšlej a netvrď nic o smáčivosti, vzlínání,
  citlivosti zkoušky ani o tom, že by se na přístupném místě vada našla.
- MT (magnetická prášková zkouška) v ŠkodaCAD posuzuje jen geometrii zkoušky jhem (kam se jho
  vejde, orientační směr pole mezi póly, dva směry magnetizace, nanesení a prohlídka).
  Výsledky MT nevymýšlej, „pokryto“ nevydávej za dostatečnou intenzitu pole ani za nalezení
  vady a feromagnetičnost materiálu nepotvrzuj za uživatele.
- RT (radiografická zkouška) v ŠkodaCAD posuzuje jen geometrii projekce (zdroj a detektor,
  přímé paprsky a prozařovaná tloušťka, promítnutí oblasti, zvětšení a neostrost, poměr
  tloušťky a nejmenší vzdálenost zdroje). Výsledky RT nevymýšlej, „promítne se“ nevydávej
  za viditelnost vady a nikdy neraď k dávce, radiační ochraně ani expozici.
- Předběžný NDT audit (zpráva o geometrickém posouzení všech studií) spouští uživatel v okně
  nebo `skodacad audit`. Jeho čísla ani problémová místa nevymýšlej, nevybírej za uživatele
  metodu ani postup a nikdy netvrď, že díl „vyhovuje“ – zpráva je jen seznam podnětů
  k ověření kvalifikovanou osobou.
- Rychlosti zvuku, úhly a rozměry sond nevymýšlej – ber je jen z knihovny NDT programu
  (vestavěné profily, Moje sondy) nebo od uživatele a vždy řekni, odkud jsou. Úhel sondy do
  jiného materiálu přepočítej jen na výslovné přání.
- Na konci krátce shrň, co se změnilo (rozměry, objem/hmotnost), a co si uživatel může
  zkontrolovat. Celou tvou úpravu vrátí jedním Zpět (Ctrl+Z).
"""


def _readme_format() -> str:
    """Část README „Formát modelu“ (jediný zdroj popisu formátu)."""
    roots = [Path(__file__).resolve().parents[2], Path(getattr(sys, "_MEIPASS", "."))]
    for root in roots:
        readme = root / "README.md"
        try:
            text = readme.read_text(encoding="utf-8")
        except OSError:
            continue
        start = text.find("## Formát modelu")
        end = text.find("\n## ", start + 10)
        if start >= 0:
            return text[start:end if end > 0 else None].strip()
    return ""


def _schema_reference() -> str:
    """Pole všech prvků a tvarů skici přesně podle formulářů okna (vždy aktuální)."""
    def fields_text(schema: Any) -> str:
        parts = []
        for item in schema.fields:
            text = item.key
            if item.choices:
                keys = [key for key, _ in item.choices]
                shown = ", ".join(keys[:14]) + (" …" if len(keys) > 14 else "")
                text += f" ({shown})"
            if item.when:
                key, value = item.when
                values = "/".join(value) if isinstance(value, tuple) else value
                text += f" [jen když {key}={values}]"
            if not item.required:
                text += "?"
            parts.append(text)
        return "; ".join(parts)

    lines = ["Prvky (type – název – pole; ? = nepovinné):"]
    for key, schema in FEATURE_SCHEMAS.items():
        lines.append(f"- {key} – {schema.label}: {fields_text(schema)}")
    lines.append("Tvary skici (elements[].shape):")
    for key, schema in SHAPE_SCHEMAS.items():
        lines.append(f"- {key} – {schema.label}: {fields_text(schema)}")
    lines.append("Materiály: " + ", ".join(DENSITIES_G_CM3))
    return "\n".join(lines)


def _examples(examples_dir: Path | None) -> str:
    if examples_dir is None:
        return ""
    parts = []
    for name in ("priruba", "krabicka", "drzak_loziska"):
        path = Path(examples_dir) / f"{name}.json"
        try:
            parts.append(f"<priklad soubor=\"{name}.json\">\n{path.read_text(encoding='utf-8')}"
                         "\n</priklad>")
        except OSError:
            continue
    return "\n".join(parts)


def system_prompt(examples_dir: Path | None = None) -> str:
    sections = [RULES, "<format_modelu>", _readme_format(), _schema_reference(),
                "</format_modelu>"]
    examples = _examples(examples_dir)
    if examples:
        sections += ["Ukázky hotových modelů:", examples]
    return "\n\n".join(section for section in sections if section)


# --- rozhovor -----------------------------------------------------------------------------


class ToolRunner(Protocol):
    def __call__(self, name: str, data: Any) -> ToolOutput: ...


Events = Callable[[str, str], None]  # (druh, text): text / tool / result / info


@dataclass
class Assistant:
    """Rozhovor s Claudem nad jedním modelem. ``ask`` je blokující (síť) – okno ho volá
    z pomocného vlákna; ``run_tool`` provede nástroj (v okně v hlavním vlákně)."""

    client: Any
    settings: AssistantSettings
    tools: list[dict[str, Any]]
    system: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    seen: Any = None  # model, jak ho Claude naposledy viděl (dict)
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self.cancel_event.set()

    def reset(self) -> None:
        """Nová konverzace (Claude zapomene předchozí dotazy)."""
        self.messages.clear()
        self.seen = None

    def user_content(self, text: str, document: dict[str, Any], report: str) -> str:
        """Dotaz uživatele; aktuální model se přidá, jen když ho Claude ještě neviděl."""
        if document == self.seen:
            return text
        self.seen = copy.deepcopy(document)
        note = ("Aktuální model" if len(self.messages) == 0 else
                "Uživatel mezitím model změnil – aktuální stav")
        model = json.dumps(document, ensure_ascii=False, indent=1)
        return (f"{note}:\n<model>\n{model}\n</model>\n<prepocet>\n{report}\n</prepocet>\n\n"
                f"Požadavek uživatele: {text}")

    def ask(self, text: str, document: dict[str, Any], report: str, run_tool: ToolRunner,
            events: Events | None = None, document_now: Callable[[], dict] | None = None) -> str:
        """Pošle dotaz a nechá Claude pracovat, dokud neodpoví. Vrátí závěrečný text."""
        emit = events or (lambda kind, value: None)
        self.cancel_event.clear()
        self.messages.append({"role": "user",
                              "content": self.user_content(text, document, report)})
        answer = ""
        for _round in range(MAX_ROUNDS):
            response = self._request(emit)
            self.usage.add(response.usage)
            self.messages.append({"role": "assistant", "content": response.content})
            answer = "\n".join(b.text for b in response.content if b.type == "text").strip()
            if any(b.type == "fallback" for b in response.content):
                emit("info", "Odpověď dokončil záložní model Claude.")
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason == "refusal":
                self._close_tools(tool_uses, "Odpověď byla odmítnuta.")
                details = getattr(response, "stop_details", None)
                why = getattr(details, "explanation", None) or ""
                raise AssistantError(f"Claude odmítl odpovědět. {why}".strip())
            if response.stop_reason == "max_tokens":
                self._close_tools(tool_uses, "Odpověď byla useknutá – nástroj se nespustil.")
                raise AssistantError("Odpověď byla moc dlouhá a useknula se – zkus požadavek "
                                     "rozdělit na menší kroky.")
            if not tool_uses:
                return answer
            results = []
            for block in tool_uses:
                if self.cancel_event.is_set():
                    results.append(ToolOutput("Uživatel úpravu zastavil.", is_error=True)
                                   .block(block.id))
                    continue
                emit("tool", ModelTools.explain(block.name, block.input))
                output = run_tool(block.name, block.input)
                emit("result", _short(output))
                results.append(output.block(block.id))
            self.messages.append({"role": "user", "content": results})
            if document_now is not None:
                self.seen = copy.deepcopy(document_now())
            if self.cancel_event.is_set():
                raise Cancelled()
        raise AssistantError(f"Asistent udělal {MAX_ROUNDS} kroků a pořád nekončí – zastavil "
                             "jsem ho. Zkus požadavek zjednodušit.")

    def _close_tools(self, tool_uses: list[Any], why: str) -> None:
        """Rozdělané volání nástrojů uzavře chybou (historie musí zůstat platná)."""
        if tool_uses:
            self.messages.append({"role": "user", "content": [
                ToolOutput(why, is_error=True).block(block.id) for block in tool_uses]})

    def _request(self, emit: Events) -> Any:
        import anthropic

        try:
            with self.client.beta.messages.stream(
                model=self.settings.model,
                max_tokens=MAX_TOKENS,
                system=self.system,
                tools=self.tools,
                messages=self.messages,
                output_config={"effort": self.settings.effort},
                cache_control={"type": "ephemeral"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                for event in stream:
                    if self.cancel_event.is_set():
                        raise Cancelled()
                    if (event.type == "content_block_delta"
                            and getattr(event.delta, "type", "") == "text_delta"):
                        emit("text", event.delta.text)
                return stream.get_final_message()
        except anthropic.AuthenticationError:
            raise AssistantError("API klíč není platný – zkontroluj ho v Nastavení AI "
                                 f"({KEY_URL}).") from None
        except anthropic.PermissionDeniedError:
            raise AssistantError("API klíč nemá oprávnění k tomuto modelu – zkus v Nastavení "
                                 "AI jiný model.") from None
        except anthropic.RateLimitError:
            raise AssistantError("Překročen limit dotazů API – zkus to za chvíli.") from None
        except anthropic.BadRequestError as exc:
            message = str(getattr(exc, "message", exc))
            if "credit" in message.lower():
                raise AssistantError("Na účtu API došel kredit – dobij ho na "
                                     "console.anthropic.com (Billing).") from None
            raise AssistantError(f"Claude dotaz odmítl jako chybný: {message}") from None
        except anthropic.APIStatusError as exc:
            raise AssistantError(f"Služba Claude má potíže (kód {exc.status_code}) – zkus to "
                                 "za chvíli.") from None
        except anthropic.APIConnectionError:
            raise AssistantError("Nepodařilo se spojit se službou Claude – zkontroluj "
                                 "připojení k internetu.") from None
        except ValueError:  # poškozený vstup nástroje (proudové posílání) – zkusit znovu
            raise AssistantError("Claude poslal poškozenou odpověď – zkus to prosím znovu.") \
                from None


def _short(output: ToolOutput) -> str:
    """Výsledek nástroje na jeden řádek pro uživatele."""
    if isinstance(output.content, list):
        return "obrázek dílu"
    first = output.content.strip().splitlines()[0] if output.content.strip() else ""
    if output.is_error:
        return f"✕ {first}"
    return f"✓ {first}"


def offline_client(turns: list[tuple[list[dict[str, Any]], str]],
                   requests: list[dict[str, Any]] | None = None) -> Any:
    """Skutečný klient knihovny anthropic, který místo sítě přehraje připravené odpovědi
    (bloky ``text`` / ``tool_use`` a stop_reason). Pro testy a self-test sestavené aplikace
    – ověří knihovnu i proudové odpovědi bez internetu a bez útraty. ``requests`` sbírá
    odeslané dotazy (hlavičky a tělo)."""
    import anthropic
    import httpx2

    queue = list(turns)

    def handler(request: Any) -> Any:
        if requests is not None:
            requests.append({"headers": dict(request.headers),
                             "body": json.loads(request.content)})
        blocks, stop = queue.pop(0)
        events: list[dict[str, Any]] = [{"type": "message_start", "message": {
            "id": f"msg_{len(queue)}", "type": "message", "role": "assistant",
            "model": DEFAULT_MODEL, "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 1000, "output_tokens": 1,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}]
        for index, block in enumerate(blocks):
            if block["type"] == "text":
                start = {"type": "text", "text": ""}
                delta = {"type": "text_delta", "text": block["text"]}
            else:
                start = {"type": "tool_use", "id": block["id"], "name": block["name"],
                         "input": {}}
                delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
            events += [{"type": "content_block_start", "index": index, "content_block": start},
                       {"type": "content_block_delta", "index": index, "delta": delta},
                       {"type": "content_block_stop", "index": index}]
        events += [{"type": "message_delta", "delta": {"stop_reason": stop,
                                                       "stop_sequence": None},
                    "usage": {"output_tokens": 50}},
                   {"type": "message_stop"}]
        body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               content=body.encode())

    return anthropic.Anthropic(
        api_key="offline", max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))


def new_assistant(settings: AssistantSettings, tools: ModelTools,
                  examples_dir: Path | None = None, client: Any = None) -> Assistant:
    """Asistent pro otevřený model (``client`` jde podstrčit – testy)."""
    return Assistant(client=client if client is not None else make_client(settings),
                     settings=settings, tools=tools.definitions,
                     system=system_prompt(examples_dir))
