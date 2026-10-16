"""Dokument dílu: parametry + seznam prvků, uložený jako čitelný JSON.

Příklad souboru::

    {
      "format": "skodacad",
      "version": 11,
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
# a „loft“ (přechod mezi skicami). Starší verze jsou podmnožinou – načtou se beze změny.
VERSION = 11
SUPPORTED_VERSIONS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)


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

    @classmethod
    def from_dict(cls, data: Any) -> Document:
        if not isinstance(data, dict):
            raise DocumentError("Model musí být JSON objekt.")
        if data.get("format") != FORMAT:
            raise DocumentError(f"Soubor není model ŠkodaCAD (chybí \"format\": \"{FORMAT}\").")
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

        thickness_map = data.get("thickness_map")
        if thickness_map is not None:
            from skodacad.thickness_map import MapError, MapSettings

            try:
                MapSettings.from_dict(thickness_map)
            except MapError as exc:
                raise DocumentError(str(exc)) from None

        return cls(
            name=str(data.get("name", "Bez názvu")),
            description=str(data.get("description", "")),
            units=units,
            material=str(data.get("material", "ocel")),
            parameters=copy.deepcopy(parameters),
            features=copy.deepcopy(features),
            measurements=copy.deepcopy(measurements),
            thickness_map=copy.deepcopy(thickness_map),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "format": FORMAT,
            "version": VERSION,
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
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        Path(path).write_text(text + "\n", encoding="utf-8")

    def with_parameters(self, overrides: dict[str, Any]) -> Document:
        """Kopie dokumentu se změněnými hodnotami parametrů."""
        unknown = sorted(set(overrides) - set(self.parameters))
        if unknown:
            raise DocumentError(f"Model nemá parametr(y): {', '.join(unknown)}.")
        changed = copy.deepcopy(self)
        changed.parameters.update(overrides)
        return changed
