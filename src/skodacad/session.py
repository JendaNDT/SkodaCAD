"""Otevřený model v aplikaci: dokument, poslední přepočet, neuložené změny.

Tahle vrstva je mezi grafickým rozhraním a jádrem. Okno nikdy nemodeluje
samo – jen volá metody ``ModelSession`` (otevři, změň parametr, přidej
prvek, ulož, exportuj …) a zobrazuje výsledek. Díky tomu jde celá logika
aplikace testovat bez okna.

Každá úprava jde přes ``_change``: zkusí ji na kopii dokumentu, zkontroluje
ji a teprve pak ji přijme a uloží předchozí stav pro „Zpět“. Neplatná
úprava vyvolá ``DocumentError`` a model zůstane beze změny.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from skodacad.document import Document, DocumentError
from skodacad.export import export
from skodacad.expressions import ExpressionError, referenced_names, resolve_parameters
from skodacad.features import describe
from skodacad.materials import density_g_cm3
from skodacad.properties import PartProperties, compute
from skodacad.rebuild import BuildResult, rebuild
from skodacad.schema import FEATURE_SCHEMAS, new_feature

_NUMBER = re.compile(r"[+-]?\d+(?:[.,]\d+)?")
_UNDO_LIMIT = 100
# Klíče, jejichž hodnoty nejsou výrazy (názvy, volby, odkazy) – při hledání použití parametru
# se přeskočí, aby se např. parametr „top“ nespletl s plochou „top“.
_NOT_EXPRESSION_KEYS = {"id", "type", "name", "sketch", "plane", "operation", "direction", "axis",
                        "shape", "mode", "face", "parallel", "open_faces", "through_all"}


def parse_parameter_text(text: str) -> int | float | str:
    """Text z políčka parametru → číslo (i s desetinnou čárkou), jinak výraz."""
    text = text.strip()
    if not text:
        raise DocumentError("Hodnota parametru nesmí být prázdná.")
    if _NUMBER.fullmatch(text):
        value = float(text.replace(",", "."))
        return int(value) if value.is_integer() and "," not in text and "." not in text else value
    return text


def format_parameter_value(value: Any) -> str:
    """Hodnota parametru pro zobrazení v políčku."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class ModelSession:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.document: Document | None = None
        self.result: BuildResult | None = None
        self.dirty = False
        self._undo: list[Document] = []
        self._redo: list[Document] = []

    # --- otevření a přepočet ---------------------------------------------------

    def open(self, path: str | Path) -> BuildResult:
        document = Document.load(path)
        self.path = Path(path)
        self.document = document
        self.dirty = False
        self._undo.clear()
        self._redo.clear()
        return self.rebuild()

    def new_document(self, name: str = "Nový díl") -> BuildResult:
        """Prázdný model bez prvků (zatím bez souboru)."""
        self.document = Document(name=name)
        self.path = None
        self.dirty = False
        self._undo.clear()
        self._redo.clear()
        return self.rebuild()

    def open_template(self, path: str | Path) -> BuildResult:
        """Otevře model jako předlohu (ukázku): „Uložit“ se zeptá na nový soubor."""
        result = self.open(path)
        self.path = None
        return result

    def rebuild(self) -> BuildResult:
        if self.document is None:
            raise DocumentError("Není otevřený žádný model.")
        self.result = rebuild(self.document)
        return self.result

    # --- úpravy ------------------------------------------------------------------

    def _require(self) -> Document:
        if self.document is None:
            raise DocumentError("Není otevřený žádný model.")
        return self.document

    def _change(self, mutate: Callable[[Document], None]) -> BuildResult:
        """Provede úpravu na kopii, zkontroluje ji a přijme (s možností Zpět)."""
        current = self._require()
        candidate = copy.deepcopy(current)
        mutate(candidate)
        if candidate == current:
            return self.result if self.result is not None else self.rebuild()
        candidate = Document.from_dict(candidate.to_dict())  # kontrola struktury (jedinečná id …)
        try:
            resolve_parameters(candidate.parameters)
        except ExpressionError as exc:
            raise DocumentError(str(exc)) from None
        self._undo.append(current)
        del self._undo[:-_UNDO_LIMIT]
        self._redo.clear()
        self.document = candidate
        self.dirty = True
        return self.rebuild()

    # --- parametry -----------------------------------------------------------------

    def set_parameter(self, name: str, text: str) -> BuildResult:
        """Změní parametr a přepočítá model.

        Neplatná hodnota (neznámý parametr ve výrazu, kruhový odkaz …) vyvolá
        ``DocumentError`` a model zůstane beze změny.
        """
        if name not in self._require().parameters:
            raise DocumentError(f"Model nemá parametr „{name}“.")
        value = parse_parameter_text(text)
        return self._change(lambda doc: doc.parameters.__setitem__(name, value))

    def add_parameter(self, name: str, text: str) -> BuildResult:
        name = name.strip()
        if name in self._require().parameters:
            raise DocumentError(f"Parametr „{name}“ už existuje.")
        if not name.isidentifier():
            raise DocumentError(
                f"„{name}“ nejde použít jako název parametru – použij písmena, číslice a _, "
                "na začátku písmeno (např. D, tloustka, roztec_der)."
            )
        value = parse_parameter_text(text)
        return self._change(lambda doc: doc.parameters.__setitem__(name, value))

    def delete_parameter(self, name: str) -> BuildResult:
        document = self._require()
        if name not in document.parameters:
            raise DocumentError(f"Model nemá parametr „{name}“.")
        users = [f"parametr „{other}“" for other, value in document.parameters.items()
                 if other != name and name in referenced_names(value)]
        users += [describe(f) for f in document.features if _uses_name(f, name)]
        if users:
            raise DocumentError(f"Parametr „{name}“ se používá: {', '.join(users)}. "
                                "Nejdřív ho tam nahraď číslem.")
        return self._change(lambda doc: doc.parameters.pop(name))

    def set_info(self, name: str | None = None, material: str | None = None,
                 description: str | None = None) -> BuildResult:
        """Název, materiál a popis dílu."""
        if material is not None and density_g_cm3(material) is None:
            raise DocumentError(f"Materiál „{material}“ neznám.")

        def mutate(doc: Document) -> None:
            if name is not None:
                doc.name = name.strip() or "Bez názvu"
            if material is not None:
                doc.material = material
            if description is not None:
                doc.description = description

        return self._change(mutate)

    # --- prvky ---------------------------------------------------------------------

    def feature_index(self, feature_id: str) -> int:
        for index, feature in enumerate(self._require().features):
            if feature["id"] == feature_id:
                return index
        raise DocumentError(f"Prvek „{feature_id}“ v modelu není.")

    def feature(self, feature_id: str) -> dict[str, Any]:
        """Kopie prvku (úpravy jdou jen přes ``update_feature``)."""
        return copy.deepcopy(self._require().features[self.feature_index(feature_id)])

    def add_feature(self, feature_type: str, after_id: str | None = None) -> str:
        """Přidá nový prvek s výchozími hodnotami (za ``after_id``, jinak na konec)."""
        if feature_type not in FEATURE_SCHEMAS:
            raise DocumentError(f"Neznámý typ prvku „{feature_type}“.")
        features = self._require().features
        index = self.feature_index(after_id) + 1 if after_id else len(features)
        feature = new_feature(feature_type, features, index)
        self._change(lambda doc: doc.features.insert(index, feature))
        return feature["id"]

    def update_feature(self, feature_id: str, feature: dict[str, Any]) -> BuildResult:
        index = self.feature_index(feature_id)
        original = self._require().features[index]
        if feature.get("id") != feature_id or feature.get("type") != original["type"]:
            raise DocumentError("U prvku nejde změnit id ani typ.")
        updated = copy.deepcopy(feature)
        return self._change(lambda doc: doc.features.__setitem__(index, updated))

    def delete_feature(self, feature_id: str) -> BuildResult:
        index = self.feature_index(feature_id)
        document = self._require()
        users = [describe(f) for f in document.features if f.get("sketch") == feature_id]
        if users:
            raise DocumentError(f"{describe(document.features[index])} používá "
                                f"{', '.join(users)}. Smaž nebo uprav nejdřív ty prvky.")
        return self._change(lambda doc: doc.features.pop(index))

    def move_feature(self, feature_id: str, offset: int) -> BuildResult:
        """Posune prvek ve stromu o ``offset`` míst (−1 nahoru, +1 dolů)."""
        index = self.feature_index(feature_id)
        target = index + offset
        if not 0 <= target < len(self._require().features):
            return self.result if self.result is not None else self.rebuild()

        def mutate(doc: Document) -> None:
            doc.features.insert(target, doc.features.pop(index))

        return self._change(mutate)

    # --- Zpět / Znovu --------------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> BuildResult | None:
        if not self._undo:
            return None
        self._redo.append(self._require())
        self.document = self._undo.pop()
        self.dirty = True
        return self.rebuild()

    def redo(self) -> BuildResult | None:
        if not self._redo:
            return None
        self._undo.append(self._require())
        self.document = self._redo.pop()
        self.dirty = True
        return self.rebuild()

    # --- ukládání a export ---------------------------------------------------------

    def save(self, path: str | Path | None = None) -> Path:
        self._require()
        target = Path(path) if path is not None else self.path
        if target is None:
            raise DocumentError("Model zatím nemá soubor, zvol „Uložit jako“.")
        self.document.save(target)
        self.path = target
        self.dirty = False
        return target

    def export(self, path: str | Path) -> Path:
        if self.result is None or self.result.part is None:
            raise DocumentError("Model zatím nemá žádné těleso, není co exportovat.")
        return export(self.result.part, path)

    # --- informace pro zobrazení -------------------------------------------------

    @property
    def properties(self) -> PartProperties | None:
        if self.result is None or self.result.part is None or self.document is None:
            return None
        return compute(self.result.part, self.document.material)

    @property
    def title(self) -> str:
        if self.document is None:
            return "ŠkodaCAD"
        star = "*" if self.dirty else ""
        filename = self.path.name if self.path else "nový model"
        return f"{star}{self.document.name} ({filename}) – ŠkodaCAD"


def _uses_name(value: Any, name: str) -> bool:
    """Používá prvek (nebo jeho část) parametr ``name`` v nějakém výrazu?"""
    if isinstance(value, dict):
        return any(_uses_name(v, name) for k, v in value.items() if k not in _NOT_EXPRESSION_KEYS)
    if isinstance(value, list):
        return any(_uses_name(item, name) for item in value)
    return name in referenced_names(value)
