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
import datetime
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

from build123d import GeomType, Vector

from skodacad.document import FORMAT, VERSION, Document, DocumentError
from skodacad.export import export
from skodacad.expressions import (
    ExpressionError,
    evaluate,
    referenced_names,
    resolve_parameters,
)
from skodacad.features import describe, profile_problem, sketch_plane
from skodacad.inspection import describe_shape
from skodacad.materials import density_g_cm3
from skodacad.measure import MeasureError, SavedResult, Value, measure, new_measurement
from skodacad.measure import face_reference as surface_reference
from skodacad.ndt.coverage import (
    MAX_COMPARISONS,
    MAX_POSITIONS,
    CoverageError,
    CoverageMap,
    _scan_positions,
)
from skodacad.ndt.coverage import compute as compute_coverage
from skodacad.ndt.devices import SNAP, DeviceError, Placement, Probe, ScanResult, place, scan_line
from skodacad.ndt.geometry import GeometryError, PartGeometry
from skodacad.ndt.study import METHODS as NDT_METHODS
from skodacad.ndt.study import (
    StudyError,
    StudyResult,
    new_study,
    part_fingerprint,
    refresh_target,
    study_probe,
    target_fingerprint,
    target_for,
)
from skodacad.ndt.study import duplicate as duplicate_study
from skodacad.ndt.ut import BeamError, BeamPath, trace_beam
from skodacad.ndt.volume_coverage import (
    MAX_CELLS,
    VolumeCoverageMap,
    check_volume_convergence,
    compute_volume,
    grid_extent,
)
from skodacad.ndt.welds import (
    TargetError,
    TargetVolume,
    nominal_volume,
    normalize_target,
    resolve_target,
    target_profiles,
)
from skodacad.picking import (
    edge_selector,
    face_direction,
    face_reference,
    map_edges,
    open_face_name,
    split_shapes,
)
from skodacad.projection import Projected, ProjectionError, candidates, reference_for
from skodacad.projection import refresh as refresh_references
from skodacad.properties import PartProperties, compute
from skodacad.rebuild import BuildResult, rebuild
from skodacad.schema import FEATURE_SCHEMAS, new_feature
from skodacad.section import (
    Section,
    SectionError,
    SectionPlane,
    axis_plane,
    axis_range,
    base_depth_range,
    clip_mesh,
    face_base,
    offset_plane,
)
from skodacad.section import cut as cut_section
from skodacad.section import export_2d as export_section_2d
from skodacad.selectors import (
    SelectionError,
    describe_edges,
    find_face,
    select_edges,
    select_faces,
)
from skodacad.solver import SolveError, loops, solve
from skodacad.thickness_map import MapError, MapSettings, ThicknessMap

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
        self._group: int | None = None  # skupina změn = jeden krok Zpět (AI asistent)
        self._runner = runner
        self._job: int | None = None  # běžící přepočet na pozadí
        self._computed: Document | None = None  # model, ke kterému patří ``result``
        self.map_visible = False  # počítat i mapu tloušťky stěny (zapíná okno)
        self.section_settings: SectionSettings | None = None  # řez modelem (jen pohled)
        self._section_cache: tuple[Any, ...] | None = None
        # přiložená NDT sonda (jen pohled): (id studie, odkaz na plochu, úhel paprsku [°])
        self.ndt_placement_request: tuple[str, dict[str, Any], float] | None = None
        self.ndt_placement_error = ""
        self._line_scan: tuple[Any, str, Probe, ScanResult] | None = None
        self.ndt_scan_index = 0
        self._placement_cache: tuple[Any, ...] | None = None
        self._geometry_cache: tuple[Any, Any] | None = None
        self._coverage_cache: tuple[Any, CoverageMap | VolumeCoverageMap] | None = None
        self._coverage_pending: tuple[Any, ...] | None = None
        self._target_preview_cache: tuple[Any, Any] | None = None

    # --- otevření a přepočet ---------------------------------------------------

    def open(self, path: str | Path) -> BuildResult | None:
        document = Document.load(path)
        self.path = Path(path)
        self.document = document
        self.result = self._computed = None  # výsledek starého modelu už neplatí
        self.dirty = False
        self._undo.clear()
        self._redo.clear()
        self.clear_ndt_placement()
        return self.rebuild()

    def new_document(self, name: str = "Nový díl") -> BuildResult:
        """Prázdný model bez prvků (zatím bez souboru)."""
        self.document = Document(name=name)
        self.result = self._computed = None
        self.path = None
        self.dirty = False
        self._undo.clear()
        self._redo.clear()
        self.clear_ndt_placement()
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
        self.clear_ndt_coverage()
        self._coverage_pending = None
        if self._runner is None:
            self.result = rebuild(self.document, with_map=self.map_visible)
            self._computed = self.document
            return self.result
        self._job = self._runner.submit(self.document.to_dict(), with_map=self.map_visible)
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
        if self._coverage_pending is not None:
            if finished.coverage is not None:
                self._coverage_cache = (self._coverage_pending, finished.coverage)
            else:
                self.failure = finished.error
            self._coverage_pending = None
        elif finished.result is not None:
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
        self._coverage_pending = None
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
        overflow = max(0, len(self._undo) - _UNDO_LIMIT)
        del self._undo[:overflow]
        if self._group is not None:
            self._group = max(0, self._group - overflow)
        self._redo.clear()
        self.document = candidate
        self.dirty = True
        return self.rebuild()

    def begin_group(self) -> None:
        """Další změny (až do ``end_group``) půjdou vrátit jedním krokem Zpět."""
        self._group = len(self._undo)

    def end_group(self) -> None:
        mark, self._group = self._group, None
        if mark is not None and len(self._undo) > mark + 1:
            del self._undo[mark + 1:]  # zůstane jen stav před první změnou skupiny

    def replace_document(self, data: dict[str, Any]) -> BuildResult:
        """Nahradí celý model (nový díl z popisu) – jako jeden krok pro Zpět."""
        if not isinstance(data, dict):
            raise DocumentError("Model musí být JSON objekt.")
        data = {"format": FORMAT, "version": VERSION, **data}
        new = Document.from_dict(data)

        def mutate(doc: Document) -> None:
            for item in fields(Document):
                setattr(doc, item.name, copy.deepcopy(getattr(new, item.name)))

        return self._change(mutate)

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
                    values: dict[str, Any] | None = None,
                    feature_id: str | None = None) -> str:
        """Přidá nový prvek s výchozími hodnotami (za ``after_id``, jinak na konec).

        ``values`` přepíše výchozí hodnoty (např. skica rovnou s nakresleným obrysem) –
        pořád jde o jeden krok pro Zpět. Id z ``values`` se nepřebírá; vlastní id jde
        zadat ``feature_id`` (jinak se vytvoří, např. „sketch2“)."""
        if feature_type not in FEATURE_SCHEMAS:
            raise DocumentError(f"Neznámý typ prvku „{feature_type}“.")
        features = self._require().features
        index = self.feature_index(after_id) + 1 if after_id else len(features)
        feature = new_feature(feature_type, features, index)
        if feature_id is not None:  # vlastní čitelné id (AI asistent, např. „zaklad“)
            if not isinstance(feature_id, str) or not feature_id.strip():
                raise DocumentError("Id prvku musí být neprázdný text.")
            if any(f.get("id") == feature_id for f in features):
                raise DocumentError(f"Prvek s id „{feature_id}“ už v modelu je – zvol jiné id.")
            feature["id"] = feature_id
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

    def sketch_projection(self, element: dict[str, Any], feature_id: str | None = None,
                          after_id: str | None = None) -> SketchProjection | None:
        """Díl pod skicou pro skicář (promítnutí hran). ``feature_id`` = upravovaná skica,
        bez něj nová skica vložená za ``after_id`` (s výchozí rovinou nové skici).
        None = pod skicou není spočítaný díl."""
        document = self.document
        if document is None or self.result is None or self.computing:
            return None
        params = self._params()
        try:
            if feature_id is not None:
                feature = document.features[self.feature_index(feature_id)]
                part = self.result.parts_before.get(feature_id)
            else:
                index = self.feature_index(after_id) + 1 if after_id else len(document.features)
                feature = new_feature("sketch", document.features, index)
                part = (self.result.part if index >= len(document.features)
                        else self.result.parts_before.get(document.features[index]["id"]))
            if part is None:
                return None
            plane = sketch_plane(part, feature, params)
            x, y = (evaluate(v, params) for v in element.get("center", [0, 0]))
            place = (x, y, evaluate(element.get("angle", 0), params))
            found = candidates(part, plane, place)
        except Exception:  # noqa: BLE001 – bez promítnutí jde skicář použít dál
            return None
        return SketchProjection(part, plane, place, params, [p for _, p in found],
                                [e for e, _ in found])

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
        shapes = self._model_shapes(shapes)
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
        shapes = self._model_shapes(shapes)
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

    # --- měření --------------------------------------------------------------------

    def measure_selection(self, shapes: list[Any], point: Any = None) -> list[Value]:
        """Co se dá změřit na výběru ve 3D (okno to ukáže hned po kliknutí); jinak []."""
        if self.result is None or self.result.part is None or self.computing:
            return []
        faces, edges = split_shapes(shapes)
        try:
            return measure(faces, edges, point, self.result.part)
        except Exception:  # noqa: BLE001 – měření je jen informace, nesmí shodit okno
            return []

    @property
    def measurements(self) -> list[SavedResult]:
        """Uložená měření spočítaná na posledním dílu."""
        return list(self.result.measurements) if self.result is not None else []

    def add_measurement(self, shapes: list[Any], kind: str, point: Any = None) -> str:
        """Uloží měření výběru do modelu (přepočítá se při každé změně). Vrátí jeho id."""
        document = self._require()
        self._require_computed("uložení měření")
        if self.result is None or self.result.part is None:
            raise DocumentError("Model zatím nemá těleso, není co měřit.")
        faces, edges = split_shapes(self._model_shapes(shapes))
        try:
            record = new_measurement(self.result.part, faces, edges, kind, point,
                                     document.measurements)
        except (MeasureError, SelectionError) as exc:
            raise DocumentError(str(exc)) from None
        self._change(lambda doc: doc.measurements.append(record))
        return record["id"]

    def remove_measurement(self, measurement_id: str) -> BuildResult:
        self._measurement_index(measurement_id)

        def mutate(doc: Document) -> None:
            doc.measurements = [m for m in doc.measurements if m.get("id") != measurement_id]

        return self._change(mutate)

    def rename_measurement(self, measurement_id: str, name: str) -> BuildResult:
        index = self._measurement_index(measurement_id)
        name = name.strip()
        if not name:
            raise DocumentError("Název měření nesmí být prázdný.")
        return self._change(lambda doc: doc.measurements[index].update(name=name))

    def _measurement_index(self, measurement_id: str) -> int:
        for index, measurement in enumerate(self._require().measurements):
            if measurement.get("id") == measurement_id:
                return index
        raise DocumentError(f"Měření „{measurement_id}“ v modelu není.")

    # --- řez modelem (jen pohled, model se nemění) -----------------------------------------

    def set_section_axis(self, axis: str, position: float | None = None,
                         flipped: bool = False) -> Section | None:
        """Řez kolmo na osu X/Y/Z; bez ``position`` uprostřed dílu."""
        if axis not in ("X", "Y", "Z"):
            raise DocumentError(f"Neznámá osa řezu „{axis}“ – umím X, Y nebo Z.")
        part = self._section_source()
        if position is None:
            low, high = axis_range(part, axis)
            position = (low + high) / 2
        self.section_settings = SectionSettings(axis, float(position), flipped)
        return self.section

    def set_section_face(self, shapes: list[Any], point: Any = None) -> Section | None:
        """Řez rovnoběžně s vybranou rovinnou plochou, napoprvé v polovině hloubky dílu."""
        faces, _ = split_shapes(shapes)
        if len(faces) != 1:
            raise DocumentError("Pro řez rovnoběžně s plochou vyber ve 3D právě jednu rovinnou "
                                "plochu.")
        try:
            base = face_base(faces[0], point)
        except SectionError as exc:
            raise DocumentError(str(exc)) from None
        low, high = base_depth_range(self._section_source(), base)
        self.section_settings = SectionSettings(None, (low + high) / 2, False, base)
        return self.section

    def set_section_position(self, position: float) -> Section | None:
        settings = self._require_section()
        self.section_settings = SectionSettings(settings.axis, float(position),
                                                settings.flipped, settings.base)
        return self.section

    def flip_section(self) -> Section | None:
        settings = self._require_section()
        self.section_settings = SectionSettings(settings.axis, settings.position,
                                                not settings.flipped, settings.base)
        return self.section

    def clear_section(self) -> None:
        self.section_settings = None

    @property
    def section_plane(self) -> SectionPlane | None:
        settings = self.section_settings
        if settings is None:
            return None
        if settings.axis is not None:
            return axis_plane(settings.axis, settings.position, settings.flipped)
        return offset_plane(settings.base, settings.position, settings.flipped)

    def section_range(self) -> tuple[float, float]:
        """Rozsah posuvníku řezu (souřadnice v ose, nebo hloubka pod plochou) [mm]."""
        settings = self._require_section()
        part = self._section_source()
        if settings.axis is not None:
            return axis_range(part, settings.axis)
        return base_depth_range(part, settings.base)

    @property
    def section(self) -> Section | None:
        """Rozříznutý díl podle nastavení (spočítá se jednou pro každý díl a polohu)."""
        return self._cut()[0]

    @property
    def section_error(self) -> str:
        """Proč se řez nepovedl ("" = v pořádku nebo řez vypnutý)."""
        return self._cut()[1]

    @property
    def display_part(self) -> Any:
        """Díl, který okno ukáže: rozříznutý při zapnutém řezu, jinak celý."""
        section = self.section
        if section is not None:
            return section.part
        return self.result.part if self.result is not None else None

    def export_section(self, path: str | Path) -> Path:
        """Obrys řezu jako 2D výkres (.dxf pro CAD, .svg jako obrázek)."""
        section = self.section
        if section is None:
            raise DocumentError(self.section_error or "Řez není zapnutý.")
        try:
            return export_section_2d(section, path)
        except SectionError as exc:
            raise DocumentError(str(exc)) from None

    def _cut(self) -> tuple[Section | None, str]:
        plane = self.section_plane
        part = self.result.part if self.result is not None else None
        if plane is None or part is None:
            return None, ""
        key = (id(part), plane)
        if self._section_cache is None or self._section_cache[0] != key:
            try:
                found: tuple[Section | None, str] = (cut_section(part, plane), "")
            except SectionError as exc:
                found = (None, str(exc))
            self._section_cache = (key, found)
        return self._section_cache[1]

    def _section_source(self) -> Any:
        if self.result is None or self.result.part is None:
            raise DocumentError("Řez potřebuje díl – model zatím nemá těleso.")
        return self.result.part

    def _require_section(self) -> SectionSettings:
        if self.section_settings is None:
            raise DocumentError("Řez není zapnutý.")
        return self.section_settings

    def _model_shapes(self, shapes: list[Any]) -> list[Any]:
        """Plochy a hrany rozříznutého dílu (řez zapnutý) → tytéž na celém dílu."""
        if self.section_settings is None or self.result is None or self.result.part is None:
            return shapes
        from build123d import Vertex

        from skodacad.measure import inner_point

        part = self.result.part
        faces, edges = split_shapes(shapes)
        mapped: list[Any] = []
        for face in faces:
            point = inner_point(face)
            normal = face.normal_at(point)
            here = Vertex(point)
            same = [f for f in part.faces() if f.geom_type == face.geom_type]
            best = min(same, key=lambda f: f.distance_to(here), default=None)
            if (best is None or best.distance_to(here) > 1e-6
                    or best.normal_at(point).dot(normal) < 1 - 1e-6):
                raise DocumentError("Vybraná plocha vznikla jen řezem – na díl ji použít ani "
                                    "uložit nejde. Vyber jinou plochu, nebo řez vypni.")
            mapped.append(best.wrapped)
        if edges:
            try:
                mapped += [edge.wrapped for edge in map_edges(edges, part)]
            except SelectionError:
                raise DocumentError("Vybraná hrana vznikla jen řezem – na díl ji použít ani "
                                    "uložit nejde. Vyber jinou hranu, nebo řez vypni.") from None
        return mapped

    # --- mapa tloušťky stěny ----------------------------------------------------------

    @property
    def map_settings(self) -> MapSettings:
        try:
            return MapSettings.from_dict(self._require().thickness_map)
        except MapError:
            return MapSettings()

    @property
    def thickness_map(self) -> ThicknessMap | None:
        return self.result.thickness_map if self.result is not None else None

    def show_thickness_map(self, visible: bool) -> BuildResult | None:
        """Zapne/vypne mapu tloušťky. Zapnutá mapa se spočítá (na pozadí) a pak se počítá
        s každou změnou modelu."""
        self.map_visible = visible
        if visible and self.document is not None and (
                self.result is None or (self.result.thickness_map is None
                                        and not self.result.map_error)):
            return self.rebuild()
        return self.result

    def set_map_setting(self, key: str, text: str) -> BuildResult:
        """Nastavení mapy z políčka okna (``limit``, ``step``, ``scale_max``); prázdné =
        bez hranice / automaticky. Uloží se do modelu (Zpět/Znovu)."""
        document = self._require()
        current = dict(document.thickness_map or {})
        text = text.strip()
        if not text:
            current.pop(key, None)
        else:
            try:
                current[key] = float(text.replace(",", "."))
            except ValueError:
                raise DocumentError(f"„{text}“ není číslo – napiš tloušťku v mm, "
                                    "např. 4 nebo 2,5.") from None
            if current[key].is_integer():
                current[key] = int(current[key])
        try:
            settings = MapSettings.from_dict(current)
        except MapError as exc:
            raise DocumentError(str(exc)) from None
        saved = settings.to_dict()

        def mutate(doc: Document) -> None:
            doc.thickness_map = saved

        return self._change(mutate)

    def visible_map(self) -> tuple[list, list, list]:
        """Mapa tloušťky k zobrazení (uzly, trojúhelníky, barvy uzlů) – při zapnutém řezu
        oříznutá rovinou řezu."""
        found = self.thickness_map
        if found is None:
            return [], [], []
        colors = found.node_colors()
        if self.section is None:
            return found.nodes, found.triangles, colors
        return clip_mesh(found.nodes, found.triangles, colors, self.section_plane)

    def export_thickness_map(self, path: str | Path) -> Path:
        """Body mapy tloušťky do CSV (x, y, z, tloušťka) pro Excel."""
        self._require_computed("export mapy")
        found = self.thickness_map
        if found is None:
            raise DocumentError("Mapa tloušťky ještě není spočítaná – zapni ji a počkej na "
                                "výsledek.")
        return found.write_csv(path)

    # --- NDT studie (nemění těleso) ------------------------------------------------------

    @property
    def ndt_studies(self) -> list[StudyResult]:
        """Stavy NDT studií na posledním dílu (spočítá je přepočet)."""
        return list(self.result.ndt) if self.result is not None else []

    def ndt_study(self, study_id: str) -> dict[str, Any]:
        """Záznam studie v modelu (kopie)."""
        return copy.deepcopy(_studies(self._require())[self._study_index(study_id)])

    def add_ndt_study(self, method: str, shapes: list[Any] | None = None, point: Any = None,
                      name: str | None = None) -> str:
        """Nová studie; vybrané plochy (``shapes``) budou kontrolovaná oblast. Vrátí id."""
        document = self._require()
        target = self._ndt_target(shapes, point) if shapes else None
        try:
            record = new_study(method, _studies(document), part_fingerprint(document), target,
                               name)
        except StudyError as exc:
            raise DocumentError(str(exc)) from None
        self._change(lambda doc: _studies(doc, create=True).append(record))
        return record["id"]

    def rename_ndt_study(self, study_id: str, name: str) -> BuildResult:
        name = name.strip()
        if not name:
            raise DocumentError("Název NDT studie nesmí být prázdný.")
        return self._edit_study(study_id, lambda study: study.update(name=name))

    def set_ndt_note(self, study_id: str, note: str) -> BuildResult:
        return self._edit_study(study_id, lambda study: study.update(note=note.strip()))

    def set_ndt_method(self, study_id: str, method: str) -> BuildResult:
        if method not in NDT_METHODS:
            raise DocumentError(f"Metoda musí být jedna z {', '.join(NDT_METHODS)}.")
        return self._edit_study(study_id, lambda study: study.update(method=method),
                                setup=True)

    def set_ndt_target(self, study_id: str, shapes: list[Any], point: Any = None) -> BuildResult:
        """Kontrolovaná oblast studie z ploch vybraných ve 3D."""
        index = self._study_index(study_id)
        target = self._ndt_target(shapes, point)
        return self._edit_study(_studies(self._require())[index]["id"],
                                lambda study: study.update(target=target), setup=True)

    def confirm_ndt_study(self, study_id: str) -> BuildResult:
        """Potvrdí studii pro aktuální díl (po kontrole zastaralé studie): nový otisk dílu a
        plochy oblasti ukotvené tam, kde teď jsou. Ověření pro starší díl tím zanikne."""
        document = self._require()
        self._require_computed("potvrzení studie")
        study = _studies(document)[self._study_index(study_id)]
        fingerprint = part_fingerprint(document)
        target = study.get("target")
        if target and (target.get("faces") or target.get("kind") in ("volume", "weld")):
            if self.result is None or self.result.part is None or self._computed != document:
                raise DocumentError("Model nemá spočítané těleso – studii teď nejde potvrdit.")
            try:
                target = refresh_target(self.result.part, target)
            except (SelectionError, StudyError) as exc:
                raise DocumentError(f"Studii nejde potvrdit – {exc} Vyber kontrolovanou oblast "
                                    "znovu.") from None

        def confirm(study: dict[str, Any]) -> None:
            study["part"] = fingerprint
            if target:
                study["target"] = target
            if (study.get("verified") or {}).get("part") != fingerprint:
                study.pop("verified", None)
            elif (target and target.get("kind") in ("volume", "weld")
                  and (study.get("verified") or {}).get("target") != target_fingerprint(target)):
                study.pop("verified", None)

        return self._edit_study(study_id, confirm)

    def set_ndt_volume_target(self, study_id: str, target: dict[str, Any]) -> BuildResult:
        """Zadaný pomocný objem/svar; změní jen studii, s kontrolou geometrie a Zpět/Znovu."""
        self._study_index(study_id)
        saved = self.ndt_target_outline(target)[0]
        self.check_ndt_volume_target(saved)
        return self._edit_study(study_id, lambda study: study.update(target=saved), setup=True)

    def check_ndt_volume_target(self, target: dict[str, Any]) -> TargetVolume:
        """Cíl ověřený na aktuálním dílu **bez změny modelu** (editor: Zkontrolovat v dílu)."""
        self._require_computed("kontrola cílového objemu")
        if self._computed != self.document:
            raise DocumentError("Model nemá aktuálně spočítané těleso – nejdřív jej přepočítej.")
        try:
            return resolve_target(self._final_part(), normalize_target(target))
        except TargetError as exc:
            raise DocumentError(str(exc)) from None

    @staticmethod
    def ndt_target_outline(target: dict[str, Any]) -> tuple[dict[str, Any], list, float]:
        """Ověřené zadání cíle, polygony průřezu (napříč, výška) a zadaný objem ze vzorce
        (průřez × délka) – bez geometrie dílu, pro nákres v editoru."""
        try:
            saved = normalize_target(target)
            return saved, target_profiles(saved), nominal_volume(saved)
        except TargetError as exc:
            raise DocumentError(str(exc)) from None

    def ndt_frame_from_edge(self, shapes: list[Any]) -> dict[str, Any]:
        """Rovná hrana vybraná ve 3D → počátek (začátek hrany), směr podél a délka [mm].
        Směr se otočí ke kladným souřadnicím, aby nezávisel na orientaci hrany v OCCT."""
        if self.result is None or self.result.part is None:
            raise DocumentError("Model zatím nemá těleso, není z čeho vybírat.")
        faces, edges = split_shapes(self._model_shapes(shapes))
        if faces or len(edges) != 1 or edges[0].geom_type != GeomType.LINE:
            raise DocumentError("Vyber ve 3D právě jednu rovnou hranu (podél svaru).")
        start, end = edges[0].position_at(0), edges[0].position_at(1)
        direction = end - start
        length = direction.length
        if length <= 1e-9:
            raise DocumentError("Vybraná hrana má nulovou délku.")
        components = (direction.X, direction.Y, direction.Z)
        if components[max(range(3), key=lambda i: abs(components[i]))] < 0:
            start, direction = end, -direction
        axis = [_clean(v / length) for v in (direction.X, direction.Y, direction.Z)]
        return {"origin": [_clean(v) for v in (start.X, start.Y, start.Z)], "axis": axis,
                "length_mm": _clean(length)}

    def ndt_target_preview(self, study_id: str | None) -> tuple[Any, Any] | None:
        """Pomocné těleso objemového cíle studie pro náhled ve 3D: (účinný objem v materiálu,
        zadaný tvar – jen když z dílu vyčnívá). Při řezu rozříznuté. None = není co ukázat."""
        if study_id is None or self.document is None or self.result is None \
                or self.result.part is None:
            return None
        try:
            target = (self.ndt_study(study_id).get("target") or {})
        except DocumentError:
            return None
        if target.get("kind") not in ("volume", "weld"):
            return None
        plane = self.section_plane
        key = (id(self.result.part), repr(target), plane)
        if self._target_preview_cache is not None and self._target_preview_cache[0] == key:
            return self._target_preview_cache[1]
        try:
            resolved = resolve_target(self.result.part, target)
        except TargetError:
            preview = None
        else:
            outside = resolved.outside_volume_mm3 > max(1e-6, resolved.volume_mm3 * 1e-8)
            shapes = [_cut_preview(shape, plane)
                      for shape in (resolved.shape, resolved.requested if outside else None)]
            preview = None if shapes[0] is None else (shapes[0], shapes[1])
        self._target_preview_cache = (key, preview)
        return preview

    def ndt_target_volume(self, study_id: str) -> TargetVolume:
        """Účinné pomocné těleso platné studie (není to výsledek pokrytí ani výrobní díl)."""
        self._require_computed("ověření cílového objemu")
        if self._computed != self.document:
            raise DocumentError("Model nemá aktuálně spočítané těleso – nejdřív jej přepočítej.")
        record = self.ndt_study(study_id)
        state = next((r.state for r in self.ndt_studies if r.id == study_id), None)
        if state != "ok":
            raise DocumentError("Cílový objem vyžaduje platnou studii – nejdřív ji zkontroluj "
                                "a potvrď pro aktuální díl.")
        try:
            return resolve_target(self._final_part(), record.get("target"))
        except TargetError as exc:
            raise DocumentError(str(exc)) from None

    def verify_ndt_study(self, study_id: str, by: str) -> BuildResult:
        """Zapíše odborné ověření studie (kdo, dnes, pro aktuální díl)."""
        by = by.strip()
        if not by:
            raise DocumentError("Napiš, kdo studii ověřil.")
        self._require_computed("ověření studie")
        index = self._study_index(study_id)
        state = next((r.state for r in self.ndt_studies if r.id == study_id), None)
        if state != "ok":
            reasons = {"stale": "je zastaralá – nejdřív ji zkontroluj a potvrď pro aktuální díl",
                       "incomplete": "je neúplná – nejdřív vyber kontrolovanou oblast",
                       "broken": "má neplatnou vazbu na díl – nejdřív ji oprav"}
            raise DocumentError(f"Studie {reasons.get(state, 'ještě není vyhodnocená')}.")
        verified = {"by": by, "date": datetime.date.today().isoformat(),
                    "part": _studies(self._require())[index]["part"]}
        target = _studies(self._require())[index].get("target") or {}
        if target.get("kind") in ("volume", "weld"):
            self.ndt_target_volume(study_id)
            verified["target"] = target_fingerprint(target)
        return self._edit_study(study_id, lambda study: study.update(verified=verified))

    def unverify_ndt_study(self, study_id: str) -> BuildResult:
        return self._edit_study(study_id, lambda study: study.pop("verified", None))

    def duplicate_ndt_study(self, study_id: str) -> str:
        """Kopie studie hned za originálem (bez ověření). Vrátí id kopie."""
        index = self._study_index(study_id)
        record = duplicate_study(_studies(self._require())[index], _studies(self._require()))
        self._change(lambda doc: _studies(doc).insert(index + 1, record))
        return record["id"]

    def remove_ndt_study(self, study_id: str) -> BuildResult:
        index = self._study_index(study_id)

        def remove(doc: Document) -> None:
            del _studies(doc)[index]
            if not _studies(doc):
                doc.ndt = None  # bez studií se sekce do souboru nepíše

        return self._change(remove)

    # --- NDT sonda ---------------------------------------------------------------------

    def ndt_probe(self, study_id: str) -> Probe:
        """Sonda studie (uložená, jinak výchozí úhlová 40 × 20 × 25 mm)."""
        return study_probe(_studies(self._require())[self._study_index(study_id)])

    def set_ndt_device(self, study_id: str, device: dict[str, Any] | Probe) -> BuildResult:
        """Uloží sondu do studie (změna zadání – ověření studie zanikne)."""
        try:
            probe = device if isinstance(device, Probe) else Probe.from_dict(device)
        except DeviceError as exc:
            raise DocumentError(str(exc)) from None
        record = probe.to_dict()
        return self._edit_study(study_id, lambda study: study.update(device=record), setup=True)

    def place_ndt_probe(self, study_id: str, shapes: list[Any], point: Any = None,
                        angle: float = 0.0) -> Placement:
        """Přiloží sondu studie na plochu vybranou ve 3D (jen pohled, do modelu se neukládá;
        po změně dílu se přiloží znovu na stejné místo). ``angle`` = směr paprsku ve stupních."""
        self._require_computed("přiložení sondy")
        self._study_index(study_id)
        if self.result is None or self.result.part is None:
            raise DocumentError("Model zatím nemá těleso, není kam sondu přiložit.")
        faces, edges = split_shapes(self._model_shapes(shapes))
        if len(faces) != 1 or edges:
            raise DocumentError("Sondu přikládáš na jednu plochu – vyber ve 3D právě jednu "
                                "plochu (klikni na ni v místě přiložení).")
        previous = self.ndt_placement_request
        reference = surface_reference(faces[0], point)
        self.ndt_placement_request = (study_id, reference, float(angle))
        placement = self.ndt_placement
        if placement is None:
            error = self.ndt_placement_error
            self.ndt_placement_request = previous
            raise DocumentError(error)
        self._line_scan = None
        self.ndt_scan_index = 0
        return placement

    def move_ndt_probe(self, study_id: str | None, shapes: list[Any], point: Any,
                       angle: float | None = None) -> Placement:
        """Posune sondu na novou polohu ve 3D (zachová studii i natočení, když nejsou zadané)."""
        if study_id is None:
            if self.ndt_placement_request is None:
                raise DocumentError("Sonda není přiložená.")
            study_id = self.ndt_placement_request[0]
        if angle is None:
            angle = self.ndt_placement_request[2] if self.ndt_placement_request is not None else 0.0
        return self.place_ndt_probe(study_id, shapes, point, angle=angle)

    def turn_ndt_probe(self, angle: float) -> Placement | None:
        """Natočí přiloženou sondu (směr paprsku ve stupních)."""
        if self.ndt_placement_request is None:
            return None
        study_id, reference, _ = self.ndt_placement_request
        self.ndt_placement_request = (study_id, reference, float(angle))
        self._line_scan = None
        self.ndt_scan_index = 0
        return self.ndt_placement

    def shift_ndt_probe(self, step_mm: float) -> Placement:
        """Posune přiloženou sondu po ploše přiložení o ``step_mm`` (+ dopředu ve směru paprsku,
        − dozadu)."""
        placement = self.ndt_placement
        if placement is None or self.ndt_placement_request is None or self.result is None:
            raise DocumentError("Sonda není přiložená.")
        study_id, reference, angle = self.ndt_placement_request
        face, _ = find_face(self.result.part, reference["face"])
        geo = self._ndt_geometry()
        step = float(step_mm)
        target = tuple(o + d * step for o, d in zip(placement.origin, placement.x_dir, strict=True))
        surface = geo.surface_at(target, face)
        if (step != 0 and math.dist(target, surface.point) > max(0.25, abs(step) * 0.5)
                or surface.distance > SNAP):
            raise DocumentError("Posun vede mimo plochu přiložení.")
        previous = self.ndt_placement_request
        self.ndt_placement_request = (study_id, surface_reference(face, surface.point), angle)
        moved = self.ndt_placement
        if moved is None:
            error = self.ndt_placement_error
            self.ndt_placement_request = previous
            raise DocumentError(error)
        self._line_scan = None
        self.ndt_scan_index = 0
        return moved

    def scan_ndt_line(self, length: float = 50.0, step: float = 1.0) -> ScanResult:
        """Projede přiloženou sondou přímku z aktuálního místa ve směru paprsku."""
        placement = self.ndt_placement
        if placement is None or self.ndt_placement_request is None or self.result is None:
            raise DocumentError("Sonda není přiložená.")
        study_id, reference, angle = self.ndt_placement_request
        face, _ = find_face(self.result.part, reference["face"])
        try:
            scan = scan_line(self._ndt_geometry(), placement.probe, placement.origin,
                             angle=angle, face=face, length=float(length), step=float(step))
        except (DeviceError, GeometryError) as exc:
            raise DocumentError(str(exc)) from None
        self._line_scan = (self.result, study_id, placement.probe, scan)
        self.ndt_scan_index = 0
        return scan

    def select_ndt_scan_index(self, index: int) -> Placement:
        """Přesune sondu na ``index``-tou polohu posledního projetí čáry."""
        scan = self.ndt_line_scan
        if scan is None or self.ndt_placement_request is None or self.result is None:
            raise DocumentError("Čára posuvu není spočítaná.")
        if not (0 <= index < len(scan.positions)):
            raise DocumentError("Poloha na čáře je mimo rozsah.")
        study_id, reference, angle = self.ndt_placement_request
        face, _ = find_face(self.result.part, reference["face"])
        point = scan.positions[index][1].origin
        self.ndt_placement_request = (study_id, surface_reference(face, point), angle)
        self.ndt_scan_index = int(index)
        placement = self.ndt_placement
        if placement is None:
            raise DocumentError(self.ndt_placement_error)
        return placement

    def clear_ndt_placement(self) -> None:
        self.clear_ndt_coverage()
        self.ndt_placement_request = None
        self.ndt_placement_error = ""
        self._line_scan = None
        self.ndt_scan_index = 0

    @property
    def ndt_line_scan(self) -> ScanResult | None:
        """Poslední projetí čáry přiloženou sondou (jen pohled); zanikne po změně dílu či sondy."""
        if (self._line_scan is None or self.ndt_placement is None
                or self.ndt_placement_request is None):
            return None
        result, study_id, probe, scan = self._line_scan
        if (self.result is not result or self.ndt_placement_request[0] != study_id
                or self.ndt_probe(study_id) != probe):
            self._line_scan = None
            self.ndt_scan_index = 0
            return None
        return scan

    @property
    def ndt_placement(self) -> Placement | None:
        """Přiložená sonda na aktuálním dílu (přepočítá se po změně dílu i sondy); None =
        žádná, nebo nejde přiložit (důvod v ``ndt_placement_error``)."""
        request = self.ndt_placement_request
        result = self.result
        if request is None or result is None or result.part is None or self.computing:
            return None
        study_id, reference, angle = request
        try:
            probe = self.ndt_probe(study_id)
        except DocumentError:
            self.ndt_placement_error = "Studie se sondou už v modelu není."
            return None
        key = (study_id, repr(reference), angle, probe)
        cache = self._placement_cache
        if cache is not None and cache[0] is result and cache[1] == key:
            return cache[2]
        placement = None
        beam = None
        try:
            face, at = find_face(result.part, reference["face"])
            geo = self._ndt_geometry()
            placement = place(geo, probe, (at.X, at.Y, at.Z), angle=angle, face=face)
            beam = trace_beam(geo, placement)
            self.ndt_placement_error = ""
        except (SelectionError, DeviceError, GeometryError, BeamError) as exc:
            self.ndt_placement_error = f"Sondu nejde přiložit: {exc}"
        except Exception as exc:  # noqa: BLE001 – pohled nesmí shodit okno
            self.ndt_placement_error = (f"Sondu nejde přiložit (neočekávaná chyba jádra "
                                        f"{type(exc).__name__}: {exc}).")
        self._placement_cache = (result, key, placement, beam)
        return placement

    @property
    def ndt_beam(self) -> BeamPath | None:
        """Geometrická dráha osy UT paprsku přiložené sondy v dílu; None = žádná sonda."""
        if self.ndt_placement is None or self._placement_cache is None:
            return None
        return self._placement_cache[3]

    def _ndt_geometry(self) -> PartGeometry:
        part = self.result.part
        if self._geometry_cache is None or self._geometry_cache[0] is not part:
            self._geometry_cache = (part, PartGeometry(part))
        return self._geometry_cache[1]

    def _coverage_context(self) -> tuple[Any, ...]:
        request = self.ndt_placement_request
        record = self.ndt_study(request[0]) if request else None
        return (self.result, repr(request), repr(record))

    @property
    def ndt_coverage(self) -> CoverageMap | VolumeCoverageMap | None:
        """Mapa platí pouze pro původní díl, zadání studie a přiložení sondy."""
        if self.computing or self._coverage_cache is None:
            return None
        key, result = self._coverage_cache
        try:
            current = self._coverage_context()
        except DocumentError:
            self._coverage_cache = None
            return None
        if key[0] is not current[0] or key[1:] != current[1:]:
            self._coverage_cache = None
            return None
        return result

    def clear_ndt_coverage(self) -> None:
        self._coverage_cache = None

    def _coverage_inputs(self) -> tuple[PartGeometry, Placement, list[Any] | dict, float]:
        self._require_computed("výpočet pokrytí")
        placed = self.ndt_placement
        if placed is None or self.ndt_placement_request is None:
            raise DocumentError("Nejdřív přilož sondu UT studie na pojezdovou plochu.")
        study_id, _, angle = self.ndt_placement_request
        record = self.ndt_study(study_id)
        state = next(r.state for r in self.ndt_studies if r.id == study_id)
        if record["method"] != "UT" or state != "ok":
            raise DocumentError("Pokrytí potřebuje platnou UT studii s kontrolovanou oblastí.")
        geo = self._ndt_geometry()
        if (record.get("target") or {}).get("kind") in ("volume", "weld"):
            return geo, placed, record["target"], angle
        faces, problems = geo.faces_of(record.get("target"))
        if problems or not faces:
            raise DocumentError("Kontrolovanou oblast nejde určit: " + " ".join(problems))
        return geo, placed, faces, angle

    def compute_ndt_coverage(self, mode: str = "face", step_mm: float = 5.0,
                             bounces: int | None = None, spread_deg: float = 0.0,
                             length_mm: float = 50.0, *, target_step_mm: float | None = None,
                             tolerance_mm: float | None = None,
                             convergence: bool = False) -> CoverageMap | VolumeCoverageMap:
        """Spočítá mapu bez změny dokumentu a jeho verze (CLI a synchronní testy).
        ``convergence`` u objemu navíc porovná s hrubším během (dvojnásobné kroky)."""
        geo, placed, target, angle = self._coverage_inputs()
        key = self._coverage_context()
        self.clear_ndt_coverage()
        volume = isinstance(target, dict)
        options = dict({"target": target} if volume else {"faces": target}, mode=mode,
                       scan_step=step_mm,
                       target_step=step_mm if target_step_mm is None else target_step_mm,
                       tolerance_mm=tolerance_mm, angle_deg=angle, bounces=bounces,
                       spread_deg=spread_deg, length_mm=length_mm)
        try:
            result = (compute_volume if volume else compute_coverage)(geo, placed, **options)
        except Exception as exc:  # noqa: BLE001 – chyby jádra nesmí shodit okno
            raise DocumentError(f"Pokrytí nejde spočítat: {exc}") from None
        if volume and convergence:
            try:
                check_volume_convergence(geo, placed, fine=result, **options)
            except Exception as exc:  # noqa: BLE001 – jemný výsledek platí, stabilita ne
                result.assumptions["convergence_text"] = (
                    f"Citlivost na krok se nepodařilo ověřit: {exc}")
        result.assumptions.update(study_id=self.ndt_placement_request[0],
                                  part_fingerprint=part_fingerprint(self._require()),
                                  parameters=dict(self.result.parameters))
        self._coverage_cache = (key, result)
        return result

    def ndt_coverage_estimate(self, mode: str = "face", step_mm: float = 5.0,
                              spread_deg: float = 0.0, length_mm: float = 50.0, *,
                              target_step_mm: float | None = None,
                              convergence: bool = False) -> CoverageEstimate:
        """Velikost objemového výpočtu ještě před spuštěním (bez geometrických průniků):
        buňky cíle, polohy sondy a stejné ochrany jako výpočet 07B."""
        _geo, placed, target, _angle = self._coverage_inputs()
        if not isinstance(target, dict):
            raise DocumentError("Odhad je jen pro objemový cíl.")
        if mode == "line" and spread_deg == 0:
            return CoverageEstimate(0, 0, 0, False, (
                "Pojezd po čáře bez rozevření svazku nevymezuje pokrytý objem. Pro objem zvol "
                "pojezd po ploše; pro čáru lze samostatně vyhodnotit body nebo plochy."))
        step = step_mm if target_step_mm is None else target_step_mm
        try:
            cells = math.prod(grid_extent(target, step)[2])
            positions = len(_scan_positions(placed, mode, step_mm, length_mm))
        except (CoverageError, TargetError) as exc:
            return CoverageEstimate(0, 0, 0, False, str(exc))
        beam = self.ndt_beam
        legs = beam.bounces + 1 if beam is not None else 1
        ok = (cells <= MAX_CELLS and positions <= MAX_POSITIONS
              and cells * positions * legs <= MAX_COMPARISONS)
        text = (f"Odhad: {_count(cells, 'buňka', 'buňky', 'buněk')} cíle, "
                f"{_count(positions, 'poloha', 'polohy', 'poloh')} sondy")
        if convergence:
            text += "; s citlivostí navíc hrubší běh (dvojnásobné kroky)"
        text += "." if ok else (" – výpočet je příliš jemný (nejvýš 20 000 buněk a 80 milionů "
                                "porovnání). Zvětši krok cíle nebo pojezdu.")
        return CoverageEstimate(cells, positions, legs, ok, text)

    @property
    def coverage_pending(self) -> bool:
        """Počítá se zrovna mapa pokrytí v pomocném procesu?"""
        return self._coverage_pending is not None

    def start_ndt_coverage(self, **options: Any) -> CoverageMap | VolumeCoverageMap | None:
        """Okno použije existující pomocný proces: zůstává živé a výpočet jde zastavit."""
        self._coverage_inputs()
        if self._runner is None:
            return self.compute_ndt_coverage(**options)
        key = self._coverage_context()
        self.clear_ndt_coverage()
        self.failure = ""
        self._job = self._runner.submit_coverage(self._require().to_dict(),
                                                self.ndt_placement_request, options)
        self._coverage_pending = key
        return None

    def visible_ndt_coverage(self) -> tuple[list, list, list]:
        result = self.ndt_coverage
        if result is None or isinstance(result, VolumeCoverageMap):
            return [], [], []
        nodes, triangles, colors = result.mesh()
        plane = self.section_plane
        return clip_mesh(nodes, triangles, colors, plane) if plane else (nodes, triangles, colors)

    def export_ndt_coverage(self, path: str | Path) -> Path:
        result = self.ndt_coverage
        if result is None:
            raise DocumentError("Nejdřív spočítej mapu geometrického pokrytí UT.")
        try:
            return result.write_csv(path)
        except OSError as exc:
            raise DocumentError(f"CSV nejde uložit: {exc}") from None

    def ndt_highlight(self, study_id: str) -> list[Any]:
        """Plochy kontrolované oblasti na dílu (OCCT) pro zvýraznění; co chybí, vynechá."""
        if self.result is None or self.result.part is None or self.document is None:
            return []
        try:
            study = _studies(self.document)[self._study_index(study_id)]
        except DocumentError:
            return []
        shapes = []
        for reference in (study.get("target") or {}).get("faces", []):
            try:
                face, _ = find_face(self.result.part, reference["face"])
            except SelectionError:
                continue
            shapes.append(face.wrapped)
        return shapes

    def _study_index(self, study_id: str) -> int:
        for index, study in enumerate(_studies(self._require())):
            if study.get("id") == study_id:
                return index
        raise DocumentError(f"NDT studie „{study_id}“ v modelu není.")

    def _edit_study(self, study_id: str, update: Callable[[dict[str, Any]], Any],
                    setup: bool = False) -> BuildResult:
        """Úprava studie; ``setup`` = mění zadání (metoda, oblast) → ověření zanikne.
        Otisk dílu mění jen založení a potvrzení – přejmenování zastaralou studii neopraví."""
        index = self._study_index(study_id)

        def mutate(doc: Document) -> None:
            study = _studies(doc)[index]
            update(study)
            if setup:
                study.pop("verified", None)

        return self._change(mutate)

    def _ndt_target(self, shapes: list[Any], point: Any) -> dict[str, Any]:
        self._require_computed("výběr kontrolované oblasti")
        if self.result is None or self.result.part is None:
            raise DocumentError("Model zatím nemá těleso, není z čeho vybírat.")
        faces, edges = split_shapes(self._model_shapes(shapes))
        if edges or not faces:
            raise DocumentError("Kontrolovaná oblast jsou plochy dílu – vyber ve 3D jednu nebo "
                                "víc ploch (hrany ne).")
        try:
            return target_for(self.result.part, faces, point)
        except StudyError as exc:
            raise DocumentError(str(exc)) from None

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
                    raise DocumentError("Vyber ve 3D právě jednu plochu (rovinnou, šikmou i "
                                        "zakřivenou – u té bude skica na tečné rovině).")
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
            raise DocumentError("Vyber ve 3D právě jednu plochu – díra bude v místě kliknutí.")
        reference = face_reference(part, faces[0], point)
        if new:
            feature["plane"] = reference.plane
            feature.pop("offset", None)
            if reference.offset:
                feature["offset"] = reference.offset
            feature["positions"] = [list(reference.point)]
            return
        if point is None:
            raise DocumentError("Klikni na plochu přesně tam, kde má další díra být.")
        if isinstance(reference.plane, str) and isinstance(feature.get("plane"), str):
            same_plane = (feature.get("plane") == reference.plane and abs(
                self._evaluate(feature.get("offset", 0)) - reference.offset) < 1e-6)
            position = list(reference.point)
        else:  # šikmá plocha: kliknutý bod musí ležet v rovině díry
            plane = sketch_plane(part, feature, self._params())
            local = plane.to_local_coords(Vector(*point))
            normal = faces[0].normal_at(Vector(*point))
            same_plane = abs(local.Z) < 1e-3 and normal.dot(plane.z_dir) > 1 - 1e-6
            position = [round(local.X, 1) + 0.0, round(local.Y, 1) + 0.0]
        if not same_plane:
            raise DocumentError("Díra leží na jiné ploše, než kam jsi klikl. Pro díru na téhle "
                                "ploše přidej novou: pravé tlačítko → Díra na vybrané ploše.")
        feature["positions"] = [*feature.get("positions", []), position]

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
class SketchProjection:
    """Hrany dílu pod skicou: co jde promítnout (``candidates`` – tvary v souřadnicích
    obrysu pro kreslení) a jak z toho udělat odkaz do obrysu."""

    part: Any
    plane: Any
    place: tuple[float, float, float]
    params: dict[str, float]
    candidates: list[Projected]
    _edges: list[Any]

    def reference(self, index: int) -> dict[str, Any]:
        """Odkaz na ``index``-tou hranu (popis hrany významem + promítnutý tvar)."""
        return reference_for(self.part, self._edges[index], self.plane, self.place)

    def refresh(self, profile: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Promítnuté hrany obrysu spočítané znovu z dílu; při potíži původní obrys a
        česká zpráva."""
        try:
            return refresh_references(profile, self.part, self.plane, self.place,
                                      lambda value: evaluate(value, self.params)), ""
        except ProjectionError as exc:
            return profile, str(exc)


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
class SectionSettings:
    """Nastavení řezu: osa (X/Y/Z), nebo rovina vybrané plochy ``base``; poloha je souřadnice
    v ose, nebo hloubka pod plochou [mm]."""

    axis: str | None
    position: float
    flipped: bool = False
    base: SectionPlane | None = None


@dataclass(frozen=True)
class CoverageEstimate:
    """Odhad objemového výpočtu pokrytí (``ModelSession.ndt_coverage_estimate``)."""

    cells: int
    positions: int
    legs: int
    ok: bool  # False = výpočet by překročil ochrany 07B nebo nemá smysl
    text: str


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


def _clean(value: float) -> float:
    """Číslo z geometrie bez šumu (−0,0 a 1e-15) – ať se v editoru neukazuje 4.999999999."""
    value = round(value, 9)
    return 0.0 if value == 0 else value


def _cut_preview(shape: Any, plane: SectionPlane | None) -> Any:
    """Náhled cíle při zapnutém řezu: rozříznutý; mimo řez celý, odříznutý = None."""
    if shape is None or plane is None:
        return shape
    try:
        return cut_section(shape, plane).part
    except SectionError:
        center = shape.center()
        return shape if plane.side((center.X, center.Y, center.Z)) < 0 else None


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


def _studies(document: Document, create: bool = False) -> list[dict[str, Any]]:
    """Seznam NDT studií modelu (``create`` založí sekci „ndt“, když chybí)."""
    if document.ndt is None:
        if not create:
            return []
        document.ndt = {"studies": []}
    return document.ndt.setdefault("studies", [])
