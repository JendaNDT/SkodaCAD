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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skodacad.document import Document, DocumentError
from skodacad.export import export
from skodacad.expressions import (
    ExpressionError,
    evaluate,
    referenced_names,
    resolve_parameters,
)
from skodacad.features import describe
from skodacad.inspection import describe_shape
from skodacad.materials import density_g_cm3
from skodacad.picking import (
    edge_selector,
    face_reference,
    map_edges,
    open_face_name,
    split_shapes,
)
from skodacad.properties import PartProperties, compute
from skodacad.rebuild import BuildResult, rebuild
from skodacad.schema import FEATURE_SCHEMAS, new_feature
from skodacad.selectors import SelectionError, describe_edges, select_edges, select_faces

_NUMBER = re.compile(r"[+-]?\d+(?:[.,]\d+)?")
_UNDO_LIMIT = 100
# Klíče, jejichž hodnoty nejsou výrazy (názvy, volby, odkazy) – při hledání použití parametru
# se přeskočí, aby se např. parametr „top“ nespletl s plochou „top“.
_NOT_EXPRESSION_KEYS = {"id", "type", "name", "sketch", "plane", "operation", "direction", "axis",
                        "shape", "mode", "face", "between", "parallel", "open_faces",
                        "through_all"}
# Prvky, které jde vytvořit z výběru ve 3D (a do kterých jde výběr převzít).
SELECTION_FEATURES = ("fillet", "chamfer", "sketch", "shell")


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

    # --- výběr ve 3D ---------------------------------------------------------------

    def selection_info(self, shapes: list[Any]) -> SelectionInfo:
        """Co je vybrané kliknutím ve 3D (počty a český popis pro stavový řádek)."""
        faces, edges = split_shapes(shapes)
        if len(faces) + len(edges) == 1:
            try:
                text = describe_shape((faces or edges)[0].wrapped)
            except Exception:  # noqa: BLE001 – popis je jen informace navíc
                text = "Vybraný prvek"
        else:
            counts = [_count(len(faces), "plocha", "plochy", "ploch"),
                      _count(len(edges), "hrana", "hrany", "hran")]
            text = "Vybráno: " + ", ".join(c for c in counts if c) if faces or edges else ""
        return SelectionInfo(len(faces), len(edges), text)

    def add_from_selection(self, feature_type: str, shapes: list[Any],
                           point: Any = None) -> str:
        """Nový prvek z výběru ve 3D: zaoblení/sražení hran, skica na ploše, skořepina.

        Prvek se přidá na konec stromu – tam, kde je díl zobrazený. ``point`` je místo
        kliknutí [x, y, z] (skica tam dostane kružnici). Vrátí id nového prvku.
        """
        document = self._require()
        part = self._final_part()
        feature = new_feature(feature_type, document.features)
        self._fill_from_selection(feature, part, shapes, point, replace=True, new=True)
        self._change(lambda doc: doc.features.append(feature))
        return feature["id"]

    def apply_selection(self, feature_id: str, shapes: list[Any],
                        replace: bool = False) -> BuildResult:
        """Převezme výběr ve 3D do existujícího prvku.

        Zaoblení/sražení vybrané hrany přidá ke svým (``replace`` = místo svých),
        skica se přesune na vybranou plochu, skořepina vybrané plochy otevře.
        """
        feature = self.feature(feature_id)
        if feature["type"] not in SELECTION_FEATURES:
            raise DocumentError(f"{describe(feature)} výběr z 3D nepoužívá.")
        part = self.result.parts_before.get(feature_id) if self.result else None
        if part is None:
            raise DocumentError(f"{describe(feature)} se zatím nepočítá (je za chybou "
                                "nebo před ním není těleso) – výběr nejde převzít.")
        self._fill_from_selection(feature, part, shapes, None, replace=replace, new=False)
        return self.update_feature(feature_id, feature)

    def feature_highlight(self, feature_id: str) -> list[Any]:
        """Tvary (OCCT), které má okno zvýraznit u vybraného prvku: hrany zaoblení,
        otevřené plochy skořepiny, plochy skici. Při jakékoli potíži prázdný seznam."""
        if self.result is None or self.document is None:
            return []
        try:
            feature = self.document.features[self.feature_index(feature_id)]
            kind = feature["type"]
            part = self.result.parts_before.get(feature_id)
            if kind in ("fillet", "chamfer") and part is not None:
                edges = select_edges(part, feature.get("edges", "all"), self._evaluate)
                return [edge.wrapped for edge in edges]
            if kind == "shell" and part is not None:
                return [face.wrapped for name in feature.get("open_faces", [])
                        for face in select_faces(part, name)]
            sketch_id = feature["id"] if kind == "sketch" else feature.get("sketch")
            if sketch_id in self.result.sketches:
                plane, sketch = self.result.sketches[sketch_id]
                return [face.wrapped for face in (plane * sketch).faces()]
        except Exception:  # noqa: BLE001 – zvýraznění je jen pomůcka, nesmí nic shodit
            return []
        return []

    def _final_part(self) -> Any:
        result = self.result
        if result is None or result.part is None:
            raise DocumentError("Model zatím nemá těleso, není z čeho vybírat.")
        if result.first_error is not None:
            raise DocumentError(f"Model má chybu v prvku {result.first_error.label} – nejdřív "
                                "ji oprav, pak přidávej prvky z výběru.")
        return result.part

    def _evaluate(self, value: Any) -> float:
        return evaluate(value, self.result.parameters if self.result else {})

    def _fill_from_selection(self, feature: dict[str, Any], part: Any, shapes: list[Any],
                             point: Any, replace: bool, new: bool) -> None:
        """Doplní do prvku výběr z 3D. ``part`` je díl, na kterém prvek vybírá.

        Nový prvek (``new``) leží na konci stromu, kde je zobrazený díl – kliknuté hrany
        patří přímo jemu. U existujícího se hledají v dílu před prvkem (``map_edges``).
        """
        faces, edges = split_shapes(shapes)
        kind = feature["type"]
        try:
            if kind in ("fillet", "chamfer"):
                if not edges:
                    raise DocumentError("Vyber ve 3D aspoň jednu hranu (Ctrl+klik přidá další).")
                if new:
                    feature["edges"] = edge_selector(part, edges)
                elif replace:
                    feature["edges"] = edge_selector(part, map_edges(edges, part))
                else:
                    feature["edges"] = self._added_edges(feature["edges"], part, edges)
            elif kind == "sketch":
                if len(faces) != 1:
                    raise DocumentError("Vyber ve 3D právě jednu rovinnou plochu.")
                reference = face_reference(part, faces[0], point if new else None)
                feature["plane"] = reference.plane
                feature.pop("offset", None)
                if reference.offset:
                    feature["offset"] = reference.offset
                if new:
                    feature["elements"][0]["center"] = list(reference.point)
            elif kind == "shell":
                if not faces:
                    raise DocumentError("Vyber ve 3D plochy, které má skořepina otevřít.")
                names = [] if replace else list(feature.get("open_faces", []))
                for face in faces:
                    name = open_face_name(part, face)
                    if name not in names:
                        names.append(name)
                feature["open_faces"] = names
            else:
                raise DocumentError(f"{describe(feature)} výběr z 3D nepoužívá.")
        except SelectionError as exc:
            raise DocumentError(str(exc)) from None

    def _added_edges(self, current: Any, part: Any, picked: list[Any]) -> Any:
        """Stávající výběr hran + nově vybrané (kliknuté ve zobrazeném dílu)."""
        mapped = map_edges(picked, part)
        try:
            existing = select_edges(part, current, self._evaluate)
        except (SelectionError, ExpressionError):
            existing = []
        new = [edge for edge in mapped if edge not in existing]
        if not new:
            raise DocumentError(f"Vybrané hrany už prvek obsahuje ({describe_edges(current)}).")
        if not existing:
            return edge_selector(part, mapped)
        added = edge_selector(part, new)
        current_items = current if isinstance(current, list) else [current]
        added_items = added if isinstance(added, list) else [added]
        return [*current_items, *added_items]

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


@dataclass(frozen=True)
class SelectionInfo:
    faces: int
    edges: int
    text: str  # český popis, "" = nic nevybráno


def _count(n: int, one: str, few: str, many: str) -> str:
    if n == 0:
        return ""
    return f"{n} {one if n == 1 else few if n < 5 else many}"


def _uses_name(value: Any, name: str) -> bool:
    """Používá prvek (nebo jeho část) parametr ``name`` v nějakém výrazu?"""
    if isinstance(value, dict):
        return any(_uses_name(v, name) for k, v in value.items() if k not in _NOT_EXPRESSION_KEYS)
    if isinstance(value, list):
        return any(_uses_name(item, name) for item in value)
    return name in referenced_names(value)
