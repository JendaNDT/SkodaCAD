"""Dokument dílu: parametry + seznam prvků, uložený jako čitelný JSON.

Příklad souboru::

    {
      "format": "skodacad",
      "version": 12,
      "name": "Příruba",
      "units": "mm",
      "material": "ocel",
      "parameters": {"D": 165, "t": 18},
      "features": [
        {"id": "obrys", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "circle", "diameter": "D"}]},
        {"id": "deska", "type": "extrude", "sketch": "obrys", "distance": "t"}
      ],
      "measurements": [
        {"id": "m1", "name": "Tloušťka desky", "kind": "thickness",
         "a": {"face": {"at": [60, 0, 18], "normal": [0, 0, 1], "type": "plane"}}}
      ]
    }
"""

from __future__ import annotations

import copy
import json
import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FORMAT = "skodacad"
# Verze 2 přidala do výběru hran klíče „between“, „near“ a seznam výběrů (výběr kliknutím),
# verze 3 tvar skici „profile“ (obrys z úseček a oblouků s vazbami), verze 4 prvek „hole“
# (díry podle strojnických tabulek), verze 5 prvky „pattern“ (pole) a „mirror“ (zrcadlení),
# verze 6 kružnice, víc smyček (díry) a nové vazby v obrysu „profile“, verze 7 promítnuté
# hrany dílu v obrysu („references“), verze 8 rovina skici/díry na šikmé či zakřivené ploše
# („plane“: {"at": …, "normal": …}), verze 9 uložená měření („measurements“), verze 10
# nastavení mapy tloušťky stěny („thickness_map“), verze 11 prvky „sweep“ (tažení po trase)
# a „loft“ (přechod mezi skicami), verze 12 normalizované díly („standard“), ocelový profil
# ve skice („steel“) a v tažení, verze 13 NDT studie („ndt“), verze 14 sonda ve studii
# („device“), verze 15 úhel lomu a počet odrazů sondy („beam_angle“, „bounces“). Starší verze
# jsou podmnožinou – načtou se beze změny. Verze 16 přidává cílové objemy a svary NDT,
# verze 17 knihovnu NDT: původ hodnot sondy („profile“, „origins“, „angle_material“ …)
# a materiál pro UT ve studii („material“), verze 18 plán dráhy sondy („plan“) a zakázané
# zóny („zones“) ve studii, verze 19 nastavení PT studie („pt“: nástroje, úhly, postup),
# verze 20 nastavení MT studie („mt“: jho, rozteče, meze, nanesení a prohlídka),
# verze 21 nastavení a projekce RT studie („rt“: zdroj, detektor, třída, projekce),
# verze 22 zadání konstrukčního návrhu (ndt.design), výsledky zůstávají jen v paměti,
# verze 23 přímé úpravy ploch: prvky „move_face“ a „face_diameter“ s odkazem na plochu
# a pojistkou původu („origin“) – návrh docs/p2-2-navrh-zapisu-prime-upravy.md.
# Verze 24: vložený zdroj STEP – prvek step_import.
# Verze 25: uložené nastavení výkresu a kóty.
# Verze 26: výslovné tolerance kót; starší aplikace je nesmí přehlédnout.
# Verze 27: údaje popisového pole, které starší export nesmí vynechat.
# Verze 28: skryté pohledy výkresu („views“), které by starší aplikace tiše ukázala.
# Verze 29: sestavy – samostatný soubor s „kind“: „assembly“ (assembly.py, návrh
# docs/p5-1-navrh-formatu-sestav.md). Díly se dál ukládají v nejnižší potřebné verzi.
VERSION = 29
SUPPORTED_VERSIONS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
                      20, 21, 22, 23, 24, 25, 26, 27, 28, 29)
ASSEMBLY_KIND = "assembly"


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    """Zapíše JSON přes dočasný soubor ve stejné složce a jedinou výměnou – při chybě
    zápisu zůstane původní soubor celý."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    target = Path(path).resolve()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class DocumentError(ValueError):
    """Soubor modelu má chybnou strukturu (zpráva je česky pro uživatele)."""


@dataclass
class Document:
    name: str = "Bez názvu"
    description: str = ""
    units: str = "mm"
    material: str = "ocel"
    parameters: dict[str, Any] = field(default_factory=dict)
    features: list[dict[str, Any]] = field(default_factory=list)
    measurements: list[dict[str, Any]] = field(default_factory=list)  # uložená měření
    thickness_map: dict[str, Any] | None = None  # nastavení mapy tloušťky stěny (NDT)
    ndt: dict[str, Any] | None = None  # NDT studie {"studies": [...]} (nemění těleso)
    drawing: dict[str, Any] | None = None  # výkres (nemění těleso)

    @classmethod
    def from_dict(cls, data: Any) -> Document:
        if not isinstance(data, dict):
            raise DocumentError("Model musí být JSON objekt.")
        if data.get("format") != FORMAT:
            raise DocumentError(f"Soubor není model ŠkodaCAD (chybí \"format\": \"{FORMAT}\").")
        kind = data.get("kind")
        if kind == ASSEMBLY_KIND:
            # Bez této kontroly by se sestava otevřela jako prázdný díl a uložením přepsala.
            raise DocumentError("Tento soubor je sestava, ne díl – otevři ho jako sestavu "
                                "(v okně Soubor → Otevřít, v příkazové řádce skodacad sestava).")
        if kind is not None:
            raise DocumentError(f"Neznámý druh souboru „{kind}“ – soubor je nejspíš z novější "
                                "verze ŠkodaCAD, stáhni aktuální aplikaci.")
        version = data.get("version")
        if version not in SUPPORTED_VERSIONS:
            raise DocumentError(
                f"Nepodporovaná verze formátu {version!r}, umím verze "
                f"{', '.join(map(str, SUPPORTED_VERSIONS))}. Soubor je nejspíš z novější "
                "verze ŠkodaCAD – stáhni aktuální aplikaci."
            )
        units = data.get("units", "mm")
        if units != "mm":
            raise DocumentError(f"Jednotky „{units}“ nejsou podporované, model musí být v mm.")

        parameters = data.get("parameters", {})
        if not isinstance(parameters, dict):
            raise DocumentError("„parameters“ musí být objekt {název: hodnota}.")

        features = data.get("features", [])
        if not isinstance(features, list):
            raise DocumentError("„features“ musí být seznam prvků.")
        seen: set[str] = set()
        for index, feature in enumerate(features, start=1):
            if not isinstance(feature, dict):
                raise DocumentError(f"Prvek č. {index} musí být objekt.")
            feature_id = feature.get("id")
            if not isinstance(feature_id, str) or not feature_id:
                raise DocumentError(f"Prvek č. {index} nemá textové „id“.")
            if feature_id in seen:
                raise DocumentError(f"Id „{feature_id}“ je v modelu dvakrát, musí být jedinečné.")
            seen.add(feature_id)
            if not isinstance(feature.get("type"), str):
                raise DocumentError(f"Prvek „{feature_id}“ nemá „type“.")
            if feature["type"] == "step_import" and version < 24:
                raise DocumentError("Import STEP vyžaduje formát modelu verze 24.")
        if sum(feature.get("type") == "step_import" for feature in features) > 1:
            raise DocumentError("Model zatím podporuje nejvýš jeden import STEP.")

        measurements = data.get("measurements", [])
        if not isinstance(measurements, list):
            raise DocumentError("„measurements“ musí být seznam měření.")
        seen.clear()
        for index, measurement in enumerate(measurements, start=1):
            if not isinstance(measurement, dict):
                raise DocumentError(f"Měření č. {index} musí být objekt.")
            measurement_id = measurement.get("id")
            if not isinstance(measurement_id, str) or not measurement_id:
                raise DocumentError(f"Měření č. {index} nemá textové „id“.")
            if measurement_id in seen:
                raise DocumentError(f"Id měření „{measurement_id}“ je v modelu dvakrát.")
            seen.add(measurement_id)
            if not isinstance(measurement.get("kind"), str):
                raise DocumentError(f"Měření „{measurement_id}“ nemá „kind“ (druh měření).")

        drawing = data.get("drawing")
        if drawing is not None:
            if version < 25:
                raise DocumentError("Uložený výkres vyžaduje formát modelu verze 25.")
            from skodacad.drawing_data import check_drawing

            check_drawing(drawing)
            if version < 28 and "views" in drawing:
                raise DocumentError("Skryté pohledy výkresu vyžadují formát modelu verze 28.")
            if version < 27 and "title_block" in drawing:
                raise DocumentError("Popisové pole vyžaduje formát modelu verze 27.")
            if version < 26 and any("tolerance" in d for d in drawing.get("dimensions", [])):
                raise DocumentError("Tolerance kót vyžadují formát modelu verze 26.")

        thickness_map = data.get("thickness_map")
        if thickness_map is not None:
            from skodacad.thickness_map import MapError, MapSettings

            try:
                MapSettings.from_dict(thickness_map)
            except MapError as exc:
                raise DocumentError(str(exc)) from None

        ndt = data.get("ndt")
        if ndt is not None:
            from skodacad.ndt.study import StudyError, check

            try:
                check(ndt)
            except StudyError as exc:
                raise DocumentError(str(exc)) from None
            # Kopie: načtení nesmí změnit vstupní slovník ani původní soubor.
            from skodacad.ndt.welds import normalize_target

            ndt = copy.deepcopy(ndt)
            for study in ndt.get("studies", []):
                target = study.get("target") or {}
                if target.get("kind") in ("volume", "weld"):
                    study["target"] = normalize_target(target)

        document = cls(
            name=str(data.get("name", "Bez názvu")),
            description=str(data.get("description", "")),
            units=units,
            material=str(data.get("material", "ocel")),
            parameters=copy.deepcopy(parameters),
            features=copy.deepcopy(features),
            measurements=copy.deepcopy(measurements),
            thickness_map=copy.deepcopy(thickness_map),
            ndt=copy.deepcopy(ndt),
            drawing=copy.deepcopy(drawing),
        )
        if ndt is not None and "design" in ndt:
            from skodacad.ndt.design import Design, DesignError

            try:
                Design.from_dict(ndt["design"]).check(document)
            except DesignError as exc:
                raise DocumentError(str(exc)) from None
        return document

    def to_dict(self) -> dict[str, Any]:
        data = {
            "format": FORMAT,
            "version": (28 if self.drawing is not None and "views" in self.drawing
                else 27 if self.drawing is not None and "title_block" in self.drawing
                else 26 if self.drawing is not None and any(
                "tolerance" in d for d in self.drawing.get("dimensions", []))
                else 25 if self.drawing is not None else 24),
            "name": self.name,
            "description": self.description,
            "units": self.units,
            "material": self.material,
            "parameters": copy.deepcopy(self.parameters),
            "features": copy.deepcopy(self.features),
            "measurements": copy.deepcopy(self.measurements),
        }
        if self.thickness_map is not None:
            data["thickness_map"] = copy.deepcopy(self.thickness_map)
        if self.ndt is not None:
            data["ndt"] = copy.deepcopy(self.ndt)
        if self.drawing is not None:
            data["drawing"] = copy.deepcopy(self.drawing)
        return data

    @classmethod
    def load(cls, path: str | Path) -> Document:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise DocumentError(f"Soubor {path} neexistuje.") from None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DocumentError(
                f"Soubor {path} není platný JSON "
                f"(řádek {exc.lineno}, sloupec {exc.colno}: {exc.msg})."
            ) from None
        return cls.from_dict(data)

    def save(self, path: str | Path) -> None:
        write_json(path, self.to_dict())

    def with_parameters(self, overrides: dict[str, Any]) -> Document:
        """Kopie dokumentu se změněnými hodnotami parametrů."""
        unknown = sorted(set(overrides) - set(self.parameters))
        if unknown:
            raise DocumentError(f"Model nemá parametr(y): {', '.join(unknown)}.")
        changed = copy.deepcopy(self)
        changed.parameters.update(overrides)
        return changed
