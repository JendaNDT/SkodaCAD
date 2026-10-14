"""Dokument dílu: parametry + seznam prvků, uložený jako čitelný JSON.

Příklad souboru::

    {
      "format": "skodacad",
      "version": 1,
      "name": "Příruba",
      "units": "mm",
      "material": "ocel",
      "parameters": {"D": 165, "t": 18},
      "features": [
        {"id": "obrys", "type": "sketch", "plane": "XY",
         "elements": [{"shape": "circle", "diameter": "D"}]},
        {"id": "deska", "type": "extrude", "sketch": "obrys", "distance": "t"}
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
VERSION = 1


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

    @classmethod
    def from_dict(cls, data: Any) -> Document:
        if not isinstance(data, dict):
            raise DocumentError("Model musí být JSON objekt.")
        if data.get("format") != FORMAT:
            raise DocumentError(f"Soubor není model ŠkodaCAD (chybí \"format\": \"{FORMAT}\").")
        version = data.get("version")
        if version != VERSION:
            raise DocumentError(f"Nepodporovaná verze formátu {version!r}, umím verzi {VERSION}.")
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

        return cls(
            name=str(data.get("name", "Bez názvu")),
            description=str(data.get("description", "")),
            units=units,
            material=str(data.get("material", "ocel")),
            parameters=copy.deepcopy(parameters),
            features=copy.deepcopy(features),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "version": VERSION,
            "name": self.name,
            "description": self.description,
            "units": self.units,
            "material": self.material,
            "parameters": copy.deepcopy(self.parameters),
            "features": copy.deepcopy(self.features),
        }

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
