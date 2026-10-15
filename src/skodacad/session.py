"""Otevřený model v aplikaci: dokument, poslední přepočet, neuložené změny.

Tahle vrstva je mezi grafickým rozhraním a jádrem. Okno nikdy nemodeluje
samo – jen volá metody ``ModelSession`` (otevři, změň parametr, přidej
prvek, ulož, exportuj …) a zobrazuje výsledek. Díky tomu jde celá logika
aplikace testovat bez okna.

Každá úprava jde přes ``_change``: zkusí ji na kopii dokumentu, zkontroluje
ji a teprve pak ji přijme a uloží předchozí stav pro „Zpět“. Neplatná
úprava vyvolá ``DocumentError`` a model zůstane beze změny.

Okno předá ``runner`` (``worker.BackgroundRebuilder``) – pak se model přepočítává na
pozadí v pomocném procesu: úprava se přijme hned, ``result`` zůstane do dokončení starý
(``computing`` je True) a nový výsledek převezme ``poll``. Bez něj (testy, příkazová
řádka) se přepočítává hned a synchronně.
"""

from __future__ import annotations

import copy
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from skodacad.document import Document, DocumentError
from skodacad.export import export
from skodacad.expressions import (
    ExpressionError,
    evaluate,
    referenced_names,
    resolve_parameters,
)
from skodacad.features import describe, profile_problem
from skodacad.inspection import describe_shape
from skodacad.materials import density_g_cm3
from skodacad.picking import (
    edge_selector,
    face_direction,
    face_reference,
    map_edges,
    open_face_name,
    split_shapes,
)
from skodacad.properties import PartProperties, compute
from skodacad.rebuild import BuildResult, rebuild
from skodacad.schema import FEATURE_SCHEMAS, new_feature
from skodacad.selectors import SelectionError, describe_edges, select_edges, select_faces
from skodacad.solver import SolveError, loops, solve

if TYPE_CHECKING:
    from skodacad.worker import BackgroundRebuilder

_NUMBER = re.compile(r"[+-]?\d+(?:[.,]\d+)?")
_UNDO_LIMIT = 100
# Klíče, jejichž hodnoty nejsou výrazy (názvy, volby, odkazy) – při hledání použití parametru
# se přeskočí, aby se např. parametr „top“ nespletl s plochou „top“.
_NOT_EXPRESSION_KEYS = {"id", "type", "name", "sketch", "plane", "operation", "direction", "axis",
                        "shape", "mode", "face", "between", "parallel", "open_faces",
                        "through_all", "kind", "size", "fit", "modeled_thread", "features",
                        "direction2"}
# Prvky, které jde vytvořit z výběru ve 3D (a do kterých jde výběr převzít).
SELECTION_FEATURES = ("fillet", "chamfer", "sketch", "shell", "hole")


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
    def __init__(self, runner: BackgroundRebuilder | None = None) -> None:
        self.path: Path | None = None
        self.document: Document | None = None
        self.result: BuildResult | None = None
        self.dirty = False
        self.failure = ""  # proč se poslední přepočet na pozadí nepovedl ("" = v pořádku)
        self._undo: list[Document] = []
        self._redo: list[Document] = []
        self._runner = runner
        self._job: int | None = None  # běžící přepočet na pozadí
        self._computed: Document | None = None  # model, ke kterému patří ``result``

    # --- otevření a přepočet ---------------------------------------------------

    def open(self, path: str | Path) -> BuildResult | None:
        document = Document.load(path)
        self.path = Path(path)
        self.document = document
        self.result = self._computed = None  # výsledek starého modelu už neplatí
        self.dirty = False
        self._undo.clear()
        self._redo.clear()
        return self.rebuild()

    def new_document(self, name: str = "Nový díl") -> BuildResult:
        """Prázdný model bez prvků (zatím bez souboru)."""
        self.document = Document(name=name)
        self.result = self._computed = None
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

    def rebuild(self) -> BuildResult | None:
        """Přepočítá model. S pomocným procesem jen spustí přepočet na pozadí a vrátí
        dosavadní výsledek (nový převezme ``poll``)."""
        if self.document is None:
            raise DocumentError("Není otevřený žádný model.")
        self.failure = ""
        if self._runner is None:
            self.result = rebuild(self.document)
            self._computed = self.document
            return self.result
        self._job = self._runner.submit(self.document.to_dict())
        return self.result

    # --- přepočet na pozadí ----------------------------------------------------------

    @property
    def computing(self) -> bool:
        """Běží přepočet na pozadí (``result`` je zatím ten předchozí)?"""
        return self._job is not None

    @property
    def computing_seconds(self) -> float:
        return time.monotonic() - self._runner.started if self.computing else 0.0

    def poll(self) -> bool:
        """Převezme hotový přepočet z pozadí. True = výsledek (nebo chyba) se změnil."""
        if self._runner is None or self._job is None:
            return False
        finished = self._runner.poll()
        if finished is None or finished.job != self._job:
            return False
        self._job = None
        if finished.result is not None:
            self.result = finished.result
            self._computed = self.document
        else:
            self.failure = finished.error
        return True

    def wait(self, timeout: float = 120.0) -> bool:
        """Počká na dokončení přepočtu na pozadí. False = nestihl se do ``timeout`` s."""
        end = time.monotonic() + timeout
        while self.computing and time.monotonic() < end:
            if not self.poll():
                time.sleep(0.02)
        return not self.computing

    def cancel(self) -> bool:
        """Zastaví přepočet na pozadí a vrátí model do posledního spočítaného stavu.
        Zrušenou změnu vrátí „Znovu“. False = nic se nepočítalo."""
        if self._runner is None or self._job is None:
            return False
        self._runner.cancel()
        self._job = None
        document, computed = self._require(), self._computed
        if computed is None:
            self.failure = ("Přepočet zastaven – model zatím není spočítaný. Uprav ho "
                            "(třeba menší počet kusů) nebo přepočítej znovu.")
            return True
        if document != computed:
            same = [i for i, old in enumerate(self._undo) if old == computed]
            if same:
                del self._undo[same[-1]:]
            self._redo.append(document)
            self.document = computed
            self.dirty = True
        return True

    def _require_computed(self, what: str) -> None:
        if self.computing:
            raise DocumentError(f"Model se ještě přepočítává – {what} půjde, až bude hotovo "
                                "(nebo přepočet zastav).")

    def _params(self) -> dict[str, float]:
        """Hodnoty parametrů aktuálního modelu (i když se zrovna přepočítává)."""
        try:
            return resolve_parameters(self._require().parameters)
        except (ExpressionError, DocumentError):
            return self.result.parameters if self.result else {}

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

    def add_feature(self, feature_type: str, after_id: str | None = None,
                    values: dict[str, Any] | None = None) -> str:
        """Přidá nový prvek s výchozími hodnotami (za ``after_id``, jinak na konec).

        ``values`` přepíše výchozí hodnoty (např. skica rovnou s nakresleným obrysem) –
        pořád jde o jeden krok pro Zpět."""
        if feature_type not in FEATURE_SCHEMAS:
            raise DocumentError(f"Neznámý typ prvku „{feature_type}“.")
        features = self._require().features
        index = self.feature_index(after_id) + 1 if after_id else len(features)
        feature = new_feature(feature_type, features, index)
        feature.update(copy.deepcopy({k: v for k, v in (values or {}).items()
                                      if k not in ("id", "type")}))
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
        users = [describe(f) for f in document.features
                 if f.get("sketch") == feature_id or feature_id in (f.get("features") or [])]
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

    # --- skicář ----------------------------------------------------------------------

    def solve_profile(self, profile: dict[str, Any]) -> ProfileSolution:
        """Vyřeší obrys skicáře s aktuálními parametry. Nikdy nevyhodí výjimku – chybu
        vrátí česky v ``message`` (a čísla vadných vazeb ve ``failed``)."""
        params = self._params()
        try:
            solved = solve(profile, lambda value: evaluate(value, params))
        except SolveError as exc:
            return ProfileSolution({}, -1, str(exc), exc.failed)
        except ExpressionError as exc:
            return ProfileSolution({}, -1, f"Hodnota kóty: {exc}", [])
        try:
            loops(profile, solved.points, solved.radii)
        except SolveError:  # neuzavřený obrys hlásí skicář sám
            warning = ""
        else:
            warning = profile_problem(profile, params)
        return ProfileSolution(solved.points, solved.dof, radii=solved.radii, warning=warning)

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
        return SelectionInfo(len(faces), len(edges), text, sum(map(_is_flat, faces)))

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
                        replace: bool = False, point: Any = None) -> BuildResult:
        """Převezme výběr ve 3D do existujícího prvku.

        Zaoblení/sražení vybrané hrany přidá ke svým (``replace`` = místo svých),
        skica se přesune na vybranou plochu, skořepina vybrané plochy otevře,
        díra dostane další polohu v místě kliknutí ``point``.
        """
        feature = self.feature(feature_id)
        if feature["type"] not in SELECTION_FEATURES:
            raise DocumentError(f"{describe(feature)} výběr z 3D nepoužívá.")
        self._require_computed("převzetí výběru")
        part = self.result.parts_before.get(feature_id) if self.result else None
        if part is None:
            raise DocumentError(f"{describe(feature)} se zatím nepočítá (je za chybou "
                                "nebo před ním není těleso) – výběr nejde převzít.")
        self._fill_from_selection(feature, part, shapes, point, replace=replace, new=False)
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
        self._require_computed("přidání prvku z výběru")
        result = self.result
        if result is None or result.part is None:
            raise DocumentError("Model zatím nemá těleso, není z čeho vybírat.")
        if result.first_error is not None:
            raise DocumentError(f"Model má chybu v prvku {result.first_error.label} – nejdřív "
                                "ji oprav, pak přidávej prvky z výběru.")
        return result.part

    def _evaluate(self, value: Any) -> float:
        return evaluate(value, self._params())

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
            elif kind == "hole":
                self._hole_from_selection(feature, part, faces, point, new)
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

    def _hole_from_selection(self, feature: dict[str, Any], part: Any, faces: list[Any],
                             point: Any, new: bool) -> None:
        """Díra v místě kliknutí: nová díra na kliknuté ploše, nebo další poloha díry."""
        if len(faces) != 1:
            raise DocumentError("Vyber ve 3D právě jednu rovinnou plochu – díra bude v místě "
                                "kliknutí.")
        reference = face_reference(part, faces[0], point)
        if new:
            feature["plane"] = reference.plane
            feature.pop("offset", None)
            if reference.offset:
                feature["offset"] = reference.offset
            feature["positions"] = [list(reference.point)]
            return
        same_plane = (feature.get("plane") == reference.plane
                      and abs(self._evaluate(feature.get("offset", 0)) - reference.offset) < 1e-6)
        if not same_plane:
            raise DocumentError("Díra leží na jiné ploše, než kam jsi klikl. Pro díru na téhle "
                                "ploše přidej novou: pravé tlačítko → Díra na vybrané ploše.")
        if point is None:
            raise DocumentError("Klikni na plochu přesně tam, kde má další díra být.")
        feature["positions"] = [*feature.get("positions", []), list(reference.point)]

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
        self._require_computed("export")
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


@dataclass
class ProfileSolution:
    points: dict[str, tuple[float, float]]  # vyřešené polohy ({} při chybě)
    dof: int  # kolik rozměrů chybí (0 = plně určeno, -1 = chyba)
    message: str = ""  # česká chyba, "" = v pořádku
    failed: list[int] = field(default_factory=list)  # čísla vazeb, které si odporují
    radii: dict[str, float] = field(default_factory=dict)  # vyřešené poloměry kružnic
    warning: str = ""  # obrys je vyřešený, ale plocha z něj nejde (smyčky se kříží …)

    @property
    def ok(self) -> bool:
        return not self.message


@dataclass(frozen=True)
class SelectionInfo:
    faces: int
    edges: int
    text: str  # český popis, "" = nic nevybráno
    flat_faces: int = 0  # rovinné plochy kolmé k ose X/Y/Z – jen na nich jde skica a skořepina


def _is_flat(face: Any) -> bool:
    try:
        face_direction(face)
    except SelectionError:
        return False
    return True


def _count(n: int, one: str, few: str, many: str) -> str:
    if n == 0:
        return ""
    return f"{n} {one if n == 1 else few if n < 5 else many}"


def _uses_name(value: Any, name: str) -> bool:
    """Používá prvek (nebo jeho část) parametr ``name`` v nějakém výrazu?"""
    if isinstance(value, dict) and value.get("shape") == "profile":
        # V obrysu jsou výrazy jen v souřadnicích bodů a hodnotách kót; jinde jsou jména
        # bodů a čar („A“, „s1“), která se nesmí splést s parametrem stejného jména.
        coordinates = list((value.get("points") or {}).values())
        dimensions = [c.get("value") for c in value.get("constraints") or []
                      if isinstance(c, dict)]
        rest = {k: v for k, v in value.items()
                if k not in ("shape", "points", "segments", "constraints")}
        return any(_uses_name(part, name) for part in (coordinates, dimensions, rest))
    if isinstance(value, dict):
        return any(_uses_name(v, name) for k, v in value.items() if k not in _NOT_EXPRESSION_KEYS)
    if isinstance(value, list):
        return any(_uses_name(item, name) for item in value)
    return name in referenced_names(value)
