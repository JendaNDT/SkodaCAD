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
import dataclasses
import datetime
import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from build123d import GeomType, Vector, Vertex

from skodacad.buildinfo import build_text, libraries_text
from skodacad.direct_edit import face_origin
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
from skodacad.materials import density_g_cm3, material_key
from skodacad.measure import MeasureError, SavedResult, Value, measure, new_measurement
from skodacad.measure import face_reference as surface_reference
from skodacad.ndt.access import (
    CONTACT_COLORS,
    AccessError,
    AccessEstimate,
    AccessOptions,
    AccessResult,
    Analysis,
    Preparation,
    VariantResult,
)
from skodacad.ndt.access import finish as finish_access
from skodacad.ndt.audit import (
    SKIPPED_BY_USER,
    STOPPED,
    STUDY_PROBLEMS,
    THICKNESS_ID,
    AuditEntry,
    AuditError,
    AuditItem,
    AuditResult,
)
from skodacad.ndt.coverage import (
    MAX_COMPARISONS,
    MAX_POSITIONS,
    CoverageError,
    CoverageMap,
    _scan_positions,
    check_convergence,
)
from skodacad.ndt.coverage import compute as compute_coverage
from skodacad.ndt.design import (
    Design,
    DesignError,
    DesignResult,
)
from skodacad.ndt.design import Variant as DesignVariant
from skodacad.ndt.design import baseline as design_baseline
from skodacad.ndt.design import estimate as estimate_design
from skodacad.ndt.design import run as run_design
from skodacad.ndt.devices import SNAP, DeviceError, Placement, Probe, ScanResult, place, scan_line
from skodacad.ndt.geometry import GeometryError, PartGeometry
from skodacad.ndt.library import (
    MATERIALS,
    AngleCheck,
    LibraryError,
    Material,
    check_angle,
    transferred,
)
from skodacad.ndt.library import describe as describe_device
from skodacad.ndt.mt import (
    MtError,
    MtMap,
    MtSettings,
    YokePlacement,
    find_yoke,
    place_yoke,
    yoke_compound,
)
from skodacad.ndt.mt import compute as compute_mt
from skodacad.ndt.mt import estimate as estimate_mt
from skodacad.ndt.mt import study_faces as mt_study_faces
from skodacad.ndt.plan import (
    STEP_COLORS,
    PassSpec,
    Plan,
    PlanError,
    PlanEstimate,
    Planner,
    PlanOptions,
    PlanResult,
    Zone,
    probe_fingerprint,
    zone_hit,
    zones_from,
)
from skodacad.ndt.pt import PtError, PtMap, PtSettings
from skodacad.ndt.pt import compute as compute_pt
from skodacad.ndt.pt import estimate as estimate_pt
from skodacad.ndt.pt import study_faces as pt_study_faces
from skodacad.ndt.rt import COLORS as RT_COLORS
from skodacad.ndt.rt import (
    SETUP_FAILURES,
    Projection,
    RtError,
    RtImage,
    RtMap,
    RtSettings,
    along_angle,
    angles_of,
    next_projection_name,
    preview_rgb,
    setup_shapes,
    write_png,
)
from skodacad.ndt.rt import compute as compute_rt
from skodacad.ndt.rt import estimate as estimate_rt
from skodacad.ndt.rt import prepare as prepare_rt
from skodacad.ndt.study import METHODS as NDT_METHODS
from skodacad.ndt.study import (
    STATE_LABELS,
    StudyError,
    StudyResult,
    new_study,
    part_fingerprint,
    refresh_target,
    study_material,
    study_probe,
    target_fingerprint,
    target_for,
)
from skodacad.ndt.study import duplicate as duplicate_study
from skodacad.ndt.study import evaluate_all as evaluate_studies
from skodacad.ndt.ut import BeamError, BeamPath, trace_beam
from skodacad.ndt.volume_coverage import (
    MAX_CELLS,
    VolumeCoverageMap,
    check_volume_convergence,
    compute_volume,
    grid_extent,
    recommended_target_step,
)
from skodacad.ndt.volume_drawing import volume_mesh
from skodacad.ndt.welds import (
    WELD_TYPES,
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
from skodacad.rebuild import BuildResult, part_problem, rebuild
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
from skodacad.thickness_map import compute as compute_thickness

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
SELECTION_FEATURES = ("fillet", "chamfer", "sketch", "shell", "hole", "move_face",
                      "face_diameter")


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


ON_SURFACE_MM = 0.01  # RT dialog: zaměřený bod leží na ploše, je-li k ní blíž
# RT náhled: buňka patří k oblasti do tolika kroků sítě od místa (× zvětšení); těžiště
# trojúhelníků ploch jsou hustší než krok, buňky objemu leží po celém kroku
PREVIEW_REACH = {"faces": 0.45, "volume": 0.75}


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
        # návrh poloh sondy (etapa 09, jen pohled): (klíč platnosti, výsledek) a běžící analýza
        self._access_cache: tuple[tuple[Any, ...], AccessResult] | None = None
        self._access_pending: dict[str, Any] | None = None
        # ukázka varianty: (id studie, sonda s úhlem/odrazy varianty) – model se nemění
        self._probe_override: tuple[str, Probe] | None = None
        # plán dráhy (etapa 10): (klíč platnosti, ověřený plán) a běžící sestavení/ověření
        self._plan_cache: tuple[tuple[Any, ...], PlanResult] | None = None
        self._plan_pending: dict[str, Any] | None = None
        self._plan_drawing_cache: tuple[Any, Any] | None = None
        self._plan_view_cache: tuple[Any, Any] | None = None
        self._target_preview_cache: tuple[Any, Any] | None = None
        self._volume_drawing_cache: tuple[Any, Any] | None = None
        # mapa PT (etapa 11, jen pohled): (klíč platnosti, mapa) a běžící výpočet
        self._pt_cache: tuple[tuple[Any, ...], PtMap] | None = None
        self._pt_pending: dict[str, Any] | None = None
        # mapa MT a přiložené jho (etapa 12, jen pohled): (klíč platnosti, výsledek)
        self._mt_cache: tuple[tuple[Any, ...], MtMap] | None = None
        self._mt_pending: dict[str, Any] | None = None
        self._yoke_view: tuple[tuple[Any, ...], YokePlacement] | None = None
        # mapa RT (etapa 13, jen pohled): (klíč platnosti, mapa) a běžící výpočet
        self._rt_cache: tuple[tuple[Any, ...], RtMap] | None = None
        self._rt_pending: dict[str, Any] | None = None
        self._rt_drawing_cache: tuple[tuple[Any, ...], Any] | None = None
        self._rt_volume_cache: tuple[tuple[Any, ...], Any] | None = None
        # předběžný NDT audit (etapa 14, jen pohled): (klíč platnosti, výsledek) a běžící výpočet
        self._audit_cache: tuple[tuple[Any, ...], AuditResult] | None = None
        self._audit_pending: dict[str, Any] | None = None
        self._design_cache: tuple[tuple[Any, ...], DesignResult] | None = None
        self._design_pending: dict[str, Any] | None = None

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
        self._access_cache = None
        self._plan_cache = None
        self._pt_cache = None
        self._mt_cache = None
        self._yoke_view = None
        self._rt_cache = None
        self._audit_cache = None
        self._design_cache = None
        self._design_pending = None
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
        self._access_cache = None
        self._plan_cache = None
        self._pt_cache = None
        self._mt_cache = None
        self._yoke_view = None
        self._rt_cache = None
        self._audit_cache = None
        self._design_cache = None
        self._design_pending = None
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
        self._access_pending = None
        self._plan_pending = None
        self._pt_pending = None
        self._mt_pending = None
        self._rt_pending = None
        self._audit_pending = None
        self._design_pending = None
        self._design_cache = None
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
        changed = False
        while True:
            finished = self._runner.poll()
            if finished is None or finished.job != self._job:
                return changed
            if finished.update is None:
                break
            changed = True
            kind, payload = finished.update
            if self._plan_pending is not None and kind == "progress":
                self._plan_pending["progress"] = payload
            if self._pt_pending is not None and kind == "progress":
                self._pt_pending["progress"] = payload
            if self._mt_pending is not None and kind == "progress":
                self._mt_pending["progress"] = payload
            if self._rt_pending is not None and kind == "progress":
                self._rt_pending["progress"] = payload
            if self._design_pending is not None:
                if kind == "design_progress":
                    self._design_pending["progress"] = payload
                elif kind == "design_prepared":
                    self._design_pending["prepared"] = payload
                elif kind == "design_variant":
                    self._design_pending["variants"].append(payload)
            if self._audit_pending is not None:
                if kind == "progress":
                    self._audit_pending["progress"] = payload
                elif kind == "entry":
                    self._audit_pending["remote"][payload.study_id] = payload
            pending = self._access_pending
            if pending is not None:
                if kind == "progress":
                    pending["progress"] = payload
                elif kind == "prepared":
                    pending["preparation"] = payload
                elif kind == "variant":
                    pending["results"].append(payload[1])
        self._job = None
        if self._design_pending is not None:
            self._finish_design(finished.design, finished.error)
        elif self._audit_pending is not None:
            if finished.audit is None:  # chyba: hotové studie zůstanou, zbylé neprovedeno
                self.failure = finished.error
            self._finish_audit(complete=finished.audit is not None)
        elif self._rt_pending is not None:
            if finished.rt is not None:
                self._rt_cache = (self._rt_pending["key"], finished.rt)
            else:
                self.failure = finished.error
            self._rt_pending = None
        elif self._mt_pending is not None:
            if finished.mt is not None:
                self._mt_cache = (self._mt_pending["key"], finished.mt)
            else:
                self.failure = finished.error
            self._mt_pending = None
        elif self._pt_pending is not None:
            if finished.pt is not None:
                self._pt_cache = (self._pt_pending["key"], finished.pt)
            else:
                self.failure = finished.error
            self._pt_pending = None
        elif self._plan_pending is not None:
            self._plan_finished(finished)
        elif self._access_pending is not None:
            if finished.access is not None:
                self._access_cache = (self._access_pending["key"], finished.access)
            else:
                self.failure = finished.error
            self._access_pending = None
        elif self._coverage_pending is not None:
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
        self._plan_pending = None
        self._pt_pending = None
        self._mt_pending = None
        self._rt_pending = None
        if self._design_pending is not None:
            self._finish_design(None, "Výpočet konstrukčních návrhů byl zastaven.")
            return True
        if self._audit_pending is not None:  # hotové studie zůstanou, zbylé neprovedeno
            self._finish_audit(complete=False)
            return True
        pending, self._access_pending = self._access_pending, None
        if pending is not None:
            if pending["preparation"] is not None:
                self._access_cache = (pending["key"], finish_access(
                    pending["preparation"], pending["results"], complete=False))
            return True
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

    @property
    def model_problem(self) -> str:
        """Důvod nedostupnosti hotového dílu; také trvalé označení náhledu v okně."""
        if self.document is None:
            return "Není otevřený žádný model."
        if self.computing:
            if self._computed == self.document:
                return "Probíhá výpočet – počkej na dokončení nebo jej zastav."
            return ("Model se ještě přepočítává. Zobrazená geometrie patří předchozímu "
                    "stavu – počkej na dokončení nebo přepočet zastav.")
        if self.result is None:
            return part_problem(None)
        if self._computed != self.document:
            return ("Model nemá aktuálně spočítané těleso. Náhled patří předchozímu stavu. "
                    "Přepočítej model znovu nebo vrať změnu pomocí Zpět.")
        return part_problem(self.result)

    def _require_complete_part(self, what: str) -> Any:
        self._require_computed(what)
        if problem := self.model_problem:
            raise DocumentError(problem)
        return self.result.part

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

    def add_step_import(self, data: bytes, source_name: str) -> str:
        """Vloží původní zdroj STEP do prázdného modelu jako jediný vratný krok."""
        from skodacad.step_probe import StepProbeError
        from skodacad.step_source import source_record

        if self._require().features:
            raise DocumentError("Import STEP zatím vyžaduje prázdný model – založ nový díl.")
        try:
            source = source_record(data, source_name)
        except StepProbeError as exc:
            raise DocumentError(str(exc)) from exc
        feature = {"id": "step_import1", "type": "step_import", "name": "Importovaný díl",
                   **source}
        self._change(lambda document: document.features.append(feature))
        return feature["id"]

    def restore_step_source(self, feature_id: str, data: bytes) -> BuildResult:
        """Nahradí chybějící obsah pouze totožným zdrojem podle uloženého otisku."""
        from skodacad.step_probe import StepProbeError
        from skodacad.step_source import restore_source

        index = self.feature_index(feature_id)
        feature = self._require().features[index]
        if feature.get("type") != "step_import":
            raise DocumentError("Vybraný prvek není import STEP.")
        try:
            restored = restore_source(feature, data)
        except StepProbeError as exc:
            raise DocumentError(str(exc)) from exc
        return self._change(lambda document: document.features.__setitem__(index, restored))

    def add_feature(self, feature_type: str, after_id: str | None = None,
                    values: dict[str, Any] | None = None,
                    feature_id: str | None = None) -> str:
        """Přidá nový prvek s výchozími hodnotami (za ``after_id``, jinak na konec).

        ``values`` přepíše výchozí hodnoty (např. skica rovnou s nakresleným obrysem) –
        pořád jde o jeden krok pro Zpět. Id z ``values`` se nepřebírá; vlastní id jde
        zadat ``feature_id`` (jinak se vytvoří, např. „sketch2“)."""
        if feature_type not in FEATURE_SCHEMAS:
            raise DocumentError(f"Neznámý typ prvku „{feature_type}“.")
        if feature_type == "step_import":
            raise DocumentError("STEP vlož pomocí příkazu Importovat STEP.")
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
        if original["type"] == "step_import":
            keys = ("data", "sha256", "size_bytes", "encoding", "source_name")
            if any(feature.get(key) != original.get(key) for key in keys):
                raise DocumentError("Zdroj STEP lze obnovit jen z totožného souboru.")
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

    def preview_direct_edit(self, kind: str, shapes: list[Any], point: Any, value: float | str,
                            feature_id: str | None = None) -> DirectEditPreview:
        """Spočítá návrh na kopii; dokument ani historie Zpět se tím nemění."""
        if kind not in ("move_face", "face_diameter"):
            raise DocumentError("Neznámý druh přímé úpravy.")
        document = self._require()
        if feature_id:
            self._require_computed("převzetí výběru")
            if self.result is None or self.result.part is None or self._computed != document:
                raise DocumentError("Model nemá aktuální vypočtený díl – přepočítej jej.")
            final = self.result.part
        else:
            final = self._final_part()
        faces, edges = split_shapes(self._model_shapes(shapes))
        if len(faces) != 1 or edges:
            raise DocumentError("Vyber právě jednu plochu, bez dalších hran.")
        index = self.feature_index(feature_id) if feature_id else len(document.features)
        if feature_id:
            feature = self.feature(feature_id)
            if feature["type"] != kind:
                raise DocumentError("Vybraný prvek není tato přímá úprava.")
            from skodacad.picking import map_faces

            part = self.result.parts_before.get(feature_id)
            if part is None:
                raise DocumentError("Před úpravou není dostupné těleso.")
            try:
                faces = map_faces(faces, part)
            except SelectionError as exc:
                raise DocumentError(str(exc)) from None
        else:
            feature = new_feature(kind, document.features)
            part = final
        face = faces[0]
        expected = GeomType.PLANE if kind == "move_face" else GeomType.CYLINDER
        if face.geom_type != expected:
            raise DocumentError("Vyber rovinnou plochu pro posun nebo válcovou pro průměr.")
        if not any(face.is_same(known) for known in part.faces()):
            raise DocumentError("Plocha nepatří k dílu – vyber ji znovu.")
        try:
            where = Vector(*point) if point is not None else face.position_at(0.5, 0.5)
            distance, on_face, _ = face.distance_to_with_closest_points(Vertex(where))
            if distance > 1e-3:
                raise DocumentError("Bod výběru neleží na ploše – klikni na ni znovu.")
            normal = face.normal_at(on_face)
            spec = {"at": list(on_face), "normal": list(normal),
                    "type": "plane" if kind == "move_face" else "cylinder"}
            found, actual = find_face(part, spec)
            if not found.is_same(face):
                raise DocumentError("Plochu nelze jednoznačně určit – klikni dál od hrany.")
            history = [(f["id"], (self.result.parts_before.get(document.features[i + 1]["id"])
                                   if i + 1 < len(document.features) else final))
                       for i, f in enumerate(document.features[:index])]
            origin = face_origin(history, found, actual)
        except SelectionError as exc:
            raise DocumentError(str(exc)) from None
        if not origin:
            raise DocumentError("Původ plochy nelze bezpečně určit – vyber jinou plochu.")
        feature.update(face=spec, origin=origin)
        feature["distance" if kind == "move_face" else "diameter"] = value
        candidate = copy.deepcopy(document)
        if feature_id:
            candidate.features[index] = feature
        else:
            candidate.features.append(feature)
        result = rebuild(candidate)
        if problem := part_problem(result):
            error = result.first_error
            detail = f"{error.label}: {error.message}" if error else problem
            raise DocumentError(f"Náhled nelze použít: {detail} Původní model se nezměnil.")
        return DirectEditPreview(copy.deepcopy(document), feature, feature_id, result)

    def apply_direct_edit(self, preview: DirectEditPreview) -> str:
        """Přijme jen stále aktuální návrh jako jediný krok historie."""
        if self._require() != preview.document or self.computing:
            raise DocumentError("Model se od náhledu změnil – vytvoř náhled znovu.")
        feature = copy.deepcopy(preview.feature)
        if preview.feature_id:
            index = self.feature_index(preview.feature_id)
            self._change(lambda doc: doc.features.__setitem__(index, feature))
        else:
            self._change(lambda doc: doc.features.append(feature))
        return feature["id"]

    def preview_direct_feature(self, feature: dict[str, Any]) -> DirectEditPreview:
        """Náhled změny hodnot existující úpravy bez změny jejího původu."""
        document = self._require()
        self._require_computed("náhled úpravy")
        if self._computed != document:
            raise DocumentError("Model není aktuálně přepočítaný – přepočítej jej.")
        feature_id = feature.get("id")
        index = self.feature_index(feature_id)
        original = document.features[index]
        if original["type"] not in ("move_face", "face_diameter") \
                or feature.get("type") != original["type"] \
                or feature.get("face") != original.get("face") \
                or feature.get("origin") != original.get("origin"):
            raise DocumentError("Výběr plochy změň příkazem Převzít výběr.")
        candidate = copy.deepcopy(document)
        candidate.features[index] = copy.deepcopy(feature)
        result = rebuild(candidate)
        if problem := part_problem(result):
            error = result.first_error
            detail = f"{error.label}: {error.message}" if error else problem
            raise DocumentError(f"Náhled nelze použít: {detail} Původní model se nezměnil.")
        return DirectEditPreview(copy.deepcopy(document), copy.deepcopy(feature), feature_id,
                                 result)

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
        if feature["type"] in ("move_face", "face_diameter"):
            key = "distance" if feature["type"] == "move_face" else "diameter"
            preview = self.preview_direct_edit(feature["type"], shapes, point,
                                               self._evaluate(feature[key]), feature_id)
            self.apply_direct_edit(preview)
            return self.result
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

    # --- vazby výkresových kót --------------------------------------------------------------

    def drawing_dimensions(self) -> list[Any]:
        from skodacad.drawing_dimensions import evaluate

        document = self._require()
        self._require_computed("vyhodnocení kót")
        return [evaluate(document, self.result, item)
                for item in (document.drawing or {}).get("dimensions", [])]

    def add_drawing_dimension(self, kind: str, *, axis: str = "", face: Any = None,
                              faces: list[Any] | None = None) -> str:
        from skodacad.drawing_dimensions import new_cylinder, new_distance, new_overall

        document = self._require()
        self._require_computed("uložení kóty")
        dimensions = (document.drawing or {}).get("dimensions", [])
        used = {item["id"] for item in dimensions}
        number = 1
        while f"d{number}" in used:
            number += 1
        did = f"d{number}"
        if kind == "overall":
            record = new_overall(document, self.result, did, axis)
        elif kind == "distance":
            selected, edges = split_shapes(self._model_shapes(faces or []))
            if len(selected) != 2 or edges:
                raise DocumentError("Vyber právě dvě rovinné plochy.")
            record = new_distance(document, self.result, did, selected)
        else:
            shapes = self._model_shapes([face]) if face is not None else []
            faces, edges = split_shapes(shapes)
            if len(faces) != 1 or edges:
                raise DocumentError("Vyber právě jednu válcovou plochu otvoru.")
            record = new_cylinder(document, self.result, did, faces[0], kind)

        def mutate(doc: Document) -> None:
            if doc.drawing is None:
                doc.drawing = {"paper": "A4", "scale": 1, "dimensions": []}
            doc.drawing.setdefault("dimensions", []).append(record)

        self._change(mutate)
        return did

    def set_drawing_section(self, axis: str | None, position: float = 0,
                            flipped: bool = False) -> BuildResult:
        def mutate(doc: Document) -> None:
            if axis is None:
                if doc.drawing is not None:
                    doc.drawing.pop("section", None)
                return
            if doc.drawing is None:
                doc.drawing = {"paper": "A4", "scale": 1, "dimensions": []}
            doc.drawing["section"] = {"axis": axis, "position": position, "flipped": flipped}
        return self._change(mutate)

    def set_drawing_dimension_placement(self, dimension_id: str, view: str, side: str,
                                        offset: float) -> BuildResult:
        dimensions = (self._require().drawing or {}).get("dimensions", [])
        index = next((i for i, item in enumerate(dimensions) if item["id"] == dimension_id), None)
        if index is None:
            raise DocumentError(f"Kóta „{dimension_id}“ ve výkresu není.")
        placement = {"view": view, "side": side, "offset": offset}
        return self._change(lambda doc: doc.drawing["dimensions"][index].update(
            placement=placement))

    def set_drawing_dimension_tolerance(self, dimension_id: str,
                                        upper: float | None, lower: float | None) -> BuildResult:
        dimensions = (self._require().drawing or {}).get("dimensions", [])
        index = next((i for i, item in enumerate(dimensions)
                        if item["id"] == dimension_id), None)
        if index is None:
            raise DocumentError(f"Kóta „{dimension_id}“ ve výkresu není.")
        if (upper is None) != (lower is None):
            raise DocumentError("Zadej obě odchylky nebo toleranci odeber.")
        def mutate(doc: Document) -> None:
            item = doc.drawing["dimensions"][index]
            if upper is None:
                item.pop("tolerance", None)
            else:
                item["tolerance"] = {"upper": upper, "lower": lower}
        return self._change(mutate)

    def remove_drawing_dimension(self, dimension_id: str) -> BuildResult:
        dimensions = (self._require().drawing or {}).get("dimensions", [])
        if not any(item["id"] == dimension_id for item in dimensions):
            raise DocumentError(f"Kóta „{dimension_id}“ ve výkresu není.")

        def mutate(doc: Document) -> None:
            doc.drawing["dimensions"] = [item for item in doc.drawing["dimensions"]
                                         if item["id"] != dimension_id]

        return self._change(mutate)

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

    def set_section_target(self, target: dict[str, Any]) -> Section | None:
        """Průřez svarem: řez kolmo na osu cíle, napoprvé uprostřed jeho délky. Poloha je
        vzdálenost od začátku cíle (0 … délka); řez míří k pozorovateli v izometrii."""
        saved = self.ndt_target_outline(target)[0]
        self._section_source()
        frame = saved["frame"]
        axis = tuple(frame["axis"])
        sign = 1.0 if sum(a * v for a, v in zip(axis, (1.0, -1.0, 1.0), strict=True)) >= 0 \
            else -1.0
        along = TargetSection(tuple(frame["origin"]), axis, saved["length_mm"],
                              tuple(sign * a + 0.0 for a in axis))  # bez −0.0
        self.section_settings = SectionSettings(None, saved["length_mm"] / 2, False,
                                                target=along)
        return self.section

    def set_section_position(self, position: float) -> Section | None:
        settings = self._require_section()
        self.section_settings = dataclasses.replace(settings, position=float(position))
        return self.section

    def flip_section(self) -> Section | None:
        settings = self._require_section()
        self.section_settings = dataclasses.replace(settings, flipped=not settings.flipped)
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
        if settings.target is not None:
            along = settings.target
            origin = tuple(o + a * settings.position
                           for o, a in zip(along.origin, along.axis, strict=True))
            normal = tuple(-n for n in along.normal) if settings.flipped else along.normal
            return SectionPlane(origin, normal)
        return offset_plane(settings.base, settings.position, settings.flipped)

    def section_range(self) -> tuple[float, float]:
        """Rozsah posuvníku řezu (souřadnice v ose, nebo hloubka pod plochou) [mm]."""
        settings = self._require_section()
        part = self._section_source()
        if settings.target is not None:
            return 0.0, settings.target.length
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
        self._require_complete_part("export řezu")
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
        from skodacad.picking import map_faces

        part = self.result.part
        faces, edges = split_shapes(shapes)
        mapped: list[Any] = []
        try:
            mapped += [face.wrapped for face in map_faces(faces, part)]
        except SelectionError as exc:
            raise DocumentError("Vybraná plocha vznikla jen řezem, nebo nemá jednoznačný "
                                f"protějšek v původním dílu. {exc}") from None
        if edges:
            try:
                mapped += [edge.wrapped for edge in map_edges(edges, part)]
            except SelectionError as exc:
                raise DocumentError("Vybraná hrana vznikla jen řezem, nebo nemá jednoznačný "
                                    f"protějšek v původním dílu. {exc}") from None
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
        return self.result.thickness_map if not self.model_problem else None

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
        self._require_complete_part("export mapy")
        found = self.thickness_map
        if found is None:
            raise DocumentError("Mapa tloušťky ještě není spočítaná – zapni ji a počkej na "
                                "výsledek.")
        return found.write_csv(path)

    # --- NDT studie (nemění těleso) ------------------------------------------------------

    @property
    def ndt_studies(self) -> list[StudyResult]:
        """Stavy NDT studií na posledním dílu (spočítá je přepočet)."""
        if self.document is not None and self._computed != self.document:
            return evaluate_studies(None, self.document, model_problem=self.model_problem)
        return list(self.result.ndt) if self.result is not None else []

    def ndt_preview_note(self, study_id: str | None) -> str:
        """Pracovní náhled neplatné studie není výpočtem její kontrolované oblasti."""
        state = next((s for s in self.ndt_studies if s.id == study_id), None)
        reasons = {"stale": "studie je zastaralá", "incomplete": "studie je neúplná",
                   "broken": "studie má neplatnou vazbu"}
        return f"Pracovní náhled – {reasons[state.state]}." if state is not None \
            and state.state in reasons else ""

    def _ndt_study_is_ok(self, study_id: str) -> bool:
        return any(study.id == study_id and study.state == "ok" for study in self.ndt_studies)

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

        def update(study: dict[str, Any]) -> None:
            study.update(method=method)
            if method != "PT":
                study.pop("pt", None)  # nastavení PT má jen PT studie
            if method != "MT":
                study.pop("mt", None)  # nastavení MT má jen MT studie
            if method != "RT":
                study.pop("rt", None)  # nastavení a projekce RT má jen RT studie

        return self._edit_study(study_id, update, setup=True)

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
        self._require_complete_part("potvrzení studie")
        study = _studies(document)[self._study_index(study_id)]
        fingerprint = part_fingerprint(document)
        target = study.get("target")
        if not target or (target.get("kind", "faces") == "faces" and not target.get("faces")):
            raise DocumentError("Studie je neúplná – nejdřív vyber kontrolovanou oblast.")
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
        self._require_complete_part("kontrola cílového objemu")
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
        self._require_complete_part("práce s NDT geometrií")
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
        if self.model_problem:
            return None
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
        self._require_complete_part("ověření cílového objemu")
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
        self._require_complete_part("ověření studie")
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
        if self._probe_override is not None and self._probe_override[0] == study_id:
            self._probe_override = None
        return self._edit_study(study_id, lambda study: study.update(device=record), setup=True)

    # --- NDT knihovna: materiál pro UT a úhel sondy (etapa 08) --------------------------

    def ndt_ut_material(self, study_id: str) -> Material | None:
        """Materiál pro UT ve studii (rychlosti zvuku), None = nezvolený."""
        return study_material(_studies(self._require())[self._study_index(study_id)])

    def set_ndt_ut_material(self, study_id: str,
                            material: str | dict[str, Any] | Material | None) -> BuildResult:
        """Materiál pro UT: název vestavěného profilu („hliník“), vlastní záznam, None = žádný.
        Mění zadání – ověření studie zanikne a mapa pokrytí se spočítá znovu."""
        if isinstance(material, str):
            found = MATERIALS.get(material_key(material))
            if found is None:
                raise DocumentError(f"Materiál „{material}“ ve vestavěné knihovně není (je tam "
                                    f"{', '.join(m.name for m in MATERIALS.values())}). Vlastní "
                                    "materiál zadej rychlostmi zvuku a zdrojem.")
            material = found
        try:
            record = None if material is None else (
                material if isinstance(material, Material) else Material.from_dict(material)
            ).to_dict()
        except LibraryError as exc:
            raise DocumentError(str(exc)) from None

        def update(study: dict[str, Any]) -> None:
            if record is None:
                study.pop("material", None)
            else:
                study["material"] = record

        return self._edit_study(study_id, update, setup=True)

    def ndt_angle_check(self, study_id: str) -> AngleCheck:
        """Platí úhel sondy v materiálu pro UT? Nic nemění – přepočet jen přes
        ``apply_ndt_angle_transfer``."""
        return check_angle(self.ndt_probe(study_id), self.ndt_ut_material(study_id),
                           self._require().material)

    def apply_ndt_angle_transfer(self, study_id: str) -> BuildResult:
        """Přepočte úhel sondy do materiálu pro UT (Snellův zákon) – jeden krok Zpět."""
        found = self.ndt_angle_check(study_id)
        if found.state != "differs":
            raise DocumentError(found.text or "Úhel sondy není co přepočítat – platí přímo "
                                              "v materiálu dílu.")
        return self.set_ndt_device(study_id, transferred(self.ndt_probe(study_id), found))

    def ndt_device_lines(self, study_id: str) -> list[str]:
        """Profil sondy, původ hodnot, materiál pro UT a kontrola úhlu pro výstupy
        (prázdné, když nic z toho není zadané)."""
        return describe_device(self.ndt_probe(study_id), self.ndt_ut_material(study_id),
                               self.ndt_angle_check(study_id))

    def place_ndt_probe(self, study_id: str, shapes: list[Any], point: Any = None,
                        angle: float = 0.0, keep_preview: bool = False) -> Placement:
        """Přiloží sondu studie na plochu vybranou ve 3D (jen pohled, do modelu se neukládá;
        po změně dílu se přiloží znovu na stejné místo). ``angle`` = směr paprsku ve stupních.
        Ruční přiložení zruší ukázku varianty návrhu poloh (``keep_preview`` ji při posunu
        zachová)."""
        self._require_complete_part("přiložení sondy")
        self._study_index(study_id)
        if self.result is None or self.result.part is None:
            raise DocumentError("Model zatím nemá těleso, není kam sondu přiložit.")
        faces, edges = split_shapes(self._model_shapes(shapes))
        if len(faces) != 1 or edges:
            raise DocumentError("Sondu přikládáš na jednu plochu – vyber ve 3D právě jednu "
                                "plochu (klikni na ni v místě přiložení).")
        previous, override = self.ndt_placement_request, self._probe_override
        if not keep_preview or (override is not None and override[0] != study_id):
            self._probe_override = None
        reference = surface_reference(faces[0], point)
        self.ndt_placement_request = (study_id, reference, float(angle))
        placement = self.ndt_placement
        if placement is None:
            error = self.ndt_placement_error
            self.ndt_placement_request, self._probe_override = previous, override
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
        return self.place_ndt_probe(study_id, shapes, point, angle=angle, keep_preview=True)

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
        self._require_complete_part("práce s NDT geometrií")
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
        self._require_complete_part("práce s NDT geometrií")
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
        self._require_complete_part("práce s NDT geometrií")
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
        self._probe_override = None
        self.ndt_placement_request = None
        self.ndt_placement_error = ""
        self._line_scan = None
        self.ndt_scan_index = 0

    @property
    def ndt_line_scan(self) -> ScanResult | None:
        """Poslední projetí čáry přiloženou sondou (jen pohled); zanikne po změně dílu či sondy."""
        if self.model_problem:
            return None
        if (self._line_scan is None or self.ndt_placement is None
                or self.ndt_placement_request is None):
            return None
        result, study_id, probe, scan = self._line_scan
        if (self.result is not result or self.ndt_placement_request[0] != study_id
                or self._placed_probe(study_id) != probe):
            self._line_scan = None
            self.ndt_scan_index = 0
            return None
        return scan

    @property
    def ndt_placement(self) -> Placement | None:
        """Přiložená sonda na aktuálním dílu (přepočítá se po změně dílu i sondy); None =
        žádná, nebo nejde přiložit (důvod v ``ndt_placement_error``)."""
        if self.model_problem:
            return None
        request = self.ndt_placement_request
        result = self.result
        if request is None or result is None or result.part is None or self.computing:
            return None
        study_id, reference, angle = request
        try:
            probe = self._placed_probe(study_id)
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
        part = self._require_complete_part("NDT výpočet")
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
        if self.model_problem:
            return None
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
        self._require_complete_part("výpočet pokrytí")
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
        ``convergence`` navíc porovná s hrubším během (dvojnásobné kroky) – u objemu
        i u ploch."""
        geo, placed, target, angle = self._coverage_inputs()
        key = self._coverage_context()
        self.clear_ndt_coverage()
        volume = isinstance(target, dict)
        # Bez kroku cíle: u objemu podle velikosti průřezu (compute_volume), u ploch krok.
        options = dict({"target": target} if volume else {"faces": target}, mode=mode,
                       scan_step=step_mm,
                       target_step=(None if volume else step_mm) if target_step_mm is None
                       else target_step_mm,
                       tolerance_mm=tolerance_mm, angle_deg=angle, bounces=bounces,
                       spread_deg=spread_deg, length_mm=length_mm)
        try:
            result = (compute_volume if volume else compute_coverage)(geo, placed, **options)
        except Exception as exc:  # noqa: BLE001 – chyby jádra nesmí shodit okno
            raise DocumentError(f"Pokrytí nejde spočítat: {exc}") from None
        if convergence:
            try:
                (check_volume_convergence if volume else check_convergence)(
                    geo, placed, fine=result, **options)
            except Exception as exc:  # noqa: BLE001 – jemný výsledek platí, stabilita ne
                result.assumptions["convergence_text"] = (
                    f"Citlivost na krok se nepodařilo ověřit: {exc}")
        study_id = self.ndt_placement_request[0]
        material = self.ndt_ut_material(study_id)
        result.assumptions.update(study_id=study_id,
                                  part_fingerprint=part_fingerprint(self._require()),
                                  parameters=dict(self.result.parameters),
                                  device_lines=self.ndt_device_lines(study_id),
                                  **({"ut_material": material.to_dict()} if material else {}))
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
        try:
            step = recommended_target_step(normalize_target(target)) \
                if target_step_mm is None else target_step_mm
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

    def ndt_recommended_target_step(self, study_id: str | None) -> float | None:
        """Výchozí krok cíle objemové studie (šestina menšího rozměru průřezu); None = studie
        nemá objemový cíl."""
        try:
            target = (self.ndt_study(study_id).get("target") or {}) if study_id else {}
            if target.get("kind") not in ("volume", "weld"):
                return None
            return recommended_target_step(normalize_target(target))
        except (DocumentError, TargetError):
            return None

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
        """Barevná síť mapy pro okno; u objemu povrch cíle (při řezu rozříznutého)."""
        return self.coverage_mesh(self.ndt_coverage)

    def coverage_mesh(self, result: CoverageMap | VolumeCoverageMap | None
                      ) -> tuple[list, list, list]:
        """Síť libovolné mapy pokrytí (i sjednocení kombinace návrhu poloh) pro okno."""
        if result is None:
            return [], [], []
        if isinstance(result, VolumeCoverageMap):
            return self._volume_drawing(result)
        nodes, triangles, colors = result.mesh()
        plane = self.section_plane
        return clip_mesh(nodes, triangles, colors, plane) if plane else (nodes, triangles, colors)

    def _volume_drawing(self, result: VolumeCoverageMap) -> tuple[list, list, list]:
        """Kresba objemového výsledku pro díl, ke kterému patří (pamatuje se pro řez)."""
        plane = self.section_plane
        key = (id(result), plane)
        if self._volume_drawing_cache is None or self._volume_drawing_cache[0] != key:
            try:
                shape = _cut_preview(resolve_target(self.result.part,
                                                    result.assumptions["target"]).shape, plane)
                drawing = volume_mesh(result, shape) if shape is not None else ([], [], [])
            except Exception:  # noqa: BLE001 – kresba je jen pohled, čísla zůstávají v panelu
                drawing = ([], [], [])
            self._volume_drawing_cache = (key, drawing)
        return self._volume_drawing_cache[1]

    def export_ndt_coverage(self, path: str | Path) -> Path:
        self._require_complete_part("výstup NDT")
        result = self.ndt_coverage
        if result is None:
            raise DocumentError("Nejdřív spočítej mapu geometrického pokrytí UT.")
        try:
            return result.write_csv(path)
        except OSError as exc:
            raise DocumentError(f"CSV nejde uložit: {exc}") from None

    # --- NDT PT – přístupnost povrchu (etapa 11, jen pohled) -----------------------------

    def ndt_pt_settings(self, study_id: str) -> PtSettings:
        """Nastavení mapy PT studie (výchozí, když ve studii žádné není)."""
        try:
            return PtSettings.from_dict(self.ndt_study(study_id).get("pt"))
        except PtError as exc:
            raise DocumentError(str(exc)) from None

    def set_ndt_pt_settings(self, study_id: str, settings: PtSettings | dict[str, Any]
                            ) -> BuildResult | None:
        """Uloží nastavení PT do studie (jeden krok Zpět); stejné nastavení = žádná změna."""
        record = self.ndt_study(study_id)
        if record.get("method") != "PT":
            raise DocumentError("Nastavení PT má jen PT (kapilární) studie.")
        try:
            settings = (settings if isinstance(settings, PtSettings)
                        else PtSettings.from_dict(settings))
        except PtError as exc:
            raise DocumentError(str(exc)) from None
        if "pt" in record and PtSettings.from_dict(record["pt"]) == settings:
            return None
        data = settings.to_dict()
        return self._edit_study(study_id, lambda study: study.update(pt=data))

    def _pt_inputs(self, study_id: str) -> tuple[Any, list[Any], PtSettings]:
        self._require_complete_part("mapa PT")
        record = self.ndt_study(study_id)
        if record.get("method") != "PT":
            raise DocumentError("Mapa PT jde spočítat jen pro PT (kapilární) studii.")
        if self.result is None or self.result.part is None:
            raise DocumentError("Model nemá těleso – mapa PT nemá na čem počítat.")
        state = next((r.state for r in self.ndt_studies if r.id == study_id), "broken")
        if state == "stale":
            raise DocumentError("Studie je zastaralá (díl se změnil) – nejdřív ji potvrď.")
        if state != "ok":
            raise DocumentError("Mapa PT potřebuje platnou PT studii s vybranými plochami.")
        try:
            faces = pt_study_faces(self._ndt_geometry(), record)
            settings = PtSettings.from_dict(record.get("pt"))
        except PtError as exc:
            raise DocumentError(str(exc)) from None
        return self.result.part, faces, settings

    def _pt_key(self, study_id: str) -> tuple[Any, ...]:
        return (self.result, study_id, repr(self.ndt_study(study_id)))

    @property
    def ndt_pt_map(self) -> PtMap | None:
        """Mapa PT platí jen pro díl, ze kterého vznikla, a nezměněnou studii."""
        if self.model_problem:
            return None
        if self.computing or self._pt_cache is None:
            return None
        key, result = self._pt_cache
        try:
            current = self._pt_key(key[1])
        except DocumentError:
            self._pt_cache = None
            return None
        if key[0] is not current[0] or key[1:] != current[1:]:
            self._pt_cache = None
            return None
        return result

    def ndt_pt_study(self) -> str | None:
        """Studie, ke které patří platná mapa PT."""
        return self._pt_cache[0][1] if self.ndt_pt_map is not None else None

    def clear_ndt_pt(self) -> None:
        self._pt_cache = None

    def ndt_pt_estimate(self, study_id: str) -> tuple[int, float, float]:
        """Odhad před spuštěním: (počet vzorků, krok sítě [mm], doba [s])."""
        part, faces, settings = self._pt_inputs(study_id)
        try:
            return estimate_pt(part, faces, settings)
        except PtError as exc:
            raise DocumentError(str(exc)) from None

    def compute_ndt_pt(self, study_id: str,
                       progress: Callable[[int, int], None] | None = None) -> PtMap:
        """Spočítá mapu PT bez změny modelu (CLI, testy, pomocný proces)."""
        part, faces, settings = self._pt_inputs(study_id)
        key = self._pt_key(study_id)
        self.clear_ndt_pt()
        try:
            result = compute_pt(part, faces, settings, progress=progress)
        except PtError as exc:
            raise DocumentError(str(exc)) from None
        except Exception as exc:  # noqa: BLE001 – chyby jádra nesmí shodit okno
            raise DocumentError(f"Mapu PT nejde spočítat: {exc}") from None
        self._pt_cache = (key, result)
        return result

    @property
    def pt_pending(self) -> bool:
        """Počítá se zrovna mapa PT v pomocném procesu?"""
        return self._pt_pending is not None

    @property
    def ndt_pt_progress(self) -> tuple[int, int] | None:
        """Průběh výpočtu mapy PT (hotovo, celkem)."""
        return self._pt_pending.get("progress") if self._pt_pending is not None else None

    def start_ndt_pt(self, study_id: str) -> PtMap | None:
        """Okno: mapa PT v pomocném procesu (jde zastavit); bez pomocného procesu hned."""
        self._pt_inputs(study_id)
        if self._runner is None:
            return self.compute_ndt_pt(study_id)
        key = self._pt_key(study_id)
        self.clear_ndt_pt()
        self.failure = ""
        self._job = self._runner.submit_pt(self._require().to_dict(), study_id)
        self._pt_pending = {"key": key, "progress": None}
        return None

    def ndt_pt_mesh(self, check: str | None = None) -> tuple[list, list, list]:
        """Barevná síť mapy PT pro okno (celkem nebo jedna kontrola), v řezu oříznutá."""
        result = self.ndt_pt_map
        if result is None:
            return [], [], []
        nodes, triangles, colors = result.mesh(check)
        plane = self.section_plane
        return clip_mesh(nodes, triangles, colors, plane) if plane else (nodes, triangles, colors)

    def ndt_pt_describe(self, point: Any) -> list[str]:
        """Stav a důvody vzorku mapy PT nejblíž bodu (klik do mapy); bez mapy prázdné."""
        result = self.ndt_pt_map
        if result is None or point is None:
            return []
        index = result.nearest(tuple(float(v) for v in point))
        return [] if index is None else result.describe(index)

    def export_ndt_pt(self, path: str | Path) -> Path:
        self._require_complete_part("výstup NDT")
        result = self.ndt_pt_map
        if result is None:
            raise DocumentError("Nejdřív spočítej mapu PT.")
        try:
            return result.write_csv(path)
        except OSError as exc:
            raise DocumentError(f"CSV nejde uložit: {exc}") from None

    # --- NDT MT – přiložení jha a směry magnetizace (etapa 12, jen pohled) ---------------

    def ndt_mt_settings(self, study_id: str) -> MtSettings:
        """Nastavení mapy MT studie (výchozí, když ve studii žádné není)."""
        try:
            return MtSettings.from_dict(self.ndt_study(study_id).get("mt"))
        except MtError as exc:
            raise DocumentError(str(exc)) from None

    def set_ndt_mt_settings(self, study_id: str, settings: MtSettings | dict[str, Any]
                            ) -> BuildResult | None:
        """Uloží nastavení MT do studie (jeden krok Zpět); stejné nastavení = žádná změna."""
        record = self.ndt_study(study_id)
        if record.get("method") != "MT":
            raise DocumentError("Nastavení MT má jen MT (magnetická prášková) studie.")
        try:
            settings = (settings if isinstance(settings, MtSettings)
                        else MtSettings.from_dict(settings))
        except MtError as exc:
            raise DocumentError(str(exc)) from None
        if "mt" in record and MtSettings.from_dict(record["mt"]) == settings:
            return None
        data = settings.to_dict()
        return self._edit_study(study_id, lambda study: study.update(mt=data))

    def _mt_record(self, study_id: str, what: str) -> dict[str, Any]:
        self._require_complete_part(what)
        record = self.ndt_study(study_id)
        if record.get("method") != "MT":
            raise DocumentError(f"{what.capitalize()} jde jen pro MT (magnetickou práškovou) "
                                "studii.")
        if self.result is None or self.result.part is None:
            raise DocumentError(f"Model nemá těleso – {what} nemá na čem počítat.")
        return record

    def _mt_inputs(self, study_id: str) -> tuple[Any, list[Any], MtSettings, str]:
        record = self._mt_record(study_id, "mapa MT")
        state = next((r.state for r in self.ndt_studies if r.id == study_id), "broken")
        if state == "stale":
            raise DocumentError("Studie je zastaralá (díl se změnil) – nejdřív ji potvrď.")
        if state != "ok":
            raise DocumentError("Mapa MT potřebuje platnou MT studii s vybranými plochami.")
        try:
            faces = mt_study_faces(self._ndt_geometry(), record)
            settings = MtSettings.from_dict(record.get("mt"))
        except MtError as exc:
            raise DocumentError(str(exc)) from None
        return self.result.part, faces, settings, self._require().material

    def _mt_key(self, study_id: str) -> tuple[Any, ...]:
        return (self.result, study_id, repr(self.ndt_study(study_id)),
                self._require().material)

    def _mt_valid(self, cache: tuple[tuple[Any, ...], Any] | None) -> bool:
        if self.computing or cache is None:
            return False
        key = cache[0]
        try:
            current = self._mt_key(key[1])
        except DocumentError:
            return False
        return key[0] is current[0] and key[1:] == current[1:]

    @property
    def ndt_mt_map(self) -> MtMap | None:
        """Mapa MT platí jen pro díl, ze kterého vznikla, a nezměněnou studii."""
        if self.model_problem:
            return None
        if not self._mt_valid(self._mt_cache):
            self._mt_cache = None
            return None
        return self._mt_cache[1]

    def ndt_mt_study(self) -> str | None:
        """Studie, ke které patří platná mapa MT."""
        return self._mt_cache[0][1] if self.ndt_mt_map is not None else None

    def clear_ndt_mt(self) -> None:
        self._mt_cache = None

    def ndt_mt_estimate(self, study_id: str) -> tuple[int, float, int, float, float]:
        """Odhad před spuštěním: (místa, krok sítě, středy jha, krok středů, doba [s])."""
        part, faces, settings, material = self._mt_inputs(study_id)
        try:
            return estimate_mt(part, faces, settings, material)
        except MtError as exc:
            raise DocumentError(str(exc)) from None

    def compute_ndt_mt(self, study_id: str,
                       progress: Callable[[int, int], None] | None = None) -> MtMap:
        """Spočítá mapu MT bez změny modelu (CLI, testy, pomocný proces)."""
        part, faces, settings, material = self._mt_inputs(study_id)
        key = self._mt_key(study_id)
        self.clear_ndt_mt()
        try:
            result = compute_mt(part, faces, settings, material, progress=progress)
        except MtError as exc:
            raise DocumentError(str(exc)) from None
        except Exception as exc:  # noqa: BLE001 – chyby jádra nesmí shodit okno
            raise DocumentError(f"Mapu MT nejde spočítat: {exc}") from None
        self._mt_cache = (key, result)
        return result

    @property
    def mt_pending(self) -> bool:
        """Počítá se zrovna mapa MT v pomocném procesu?"""
        return self._mt_pending is not None

    @property
    def ndt_mt_progress(self) -> tuple[int, int] | None:
        """Průběh výpočtu mapy MT (hotovo, celkem)."""
        return self._mt_pending.get("progress") if self._mt_pending is not None else None

    def start_ndt_mt(self, study_id: str) -> MtMap | None:
        """Okno: mapa MT v pomocném procesu (jde zastavit); bez pomocného procesu hned."""
        part, faces, settings, material = self._mt_inputs(study_id)
        try:
            estimate_mt(part, faces, settings, material)  # chyba materiálu hned, ne až v procesu
        except MtError as exc:
            raise DocumentError(str(exc)) from None
        if self._runner is None:
            return self.compute_ndt_mt(study_id)
        key = self._mt_key(study_id)
        self.clear_ndt_mt()
        self.failure = ""
        self._job = self._runner.submit_mt(self._require().to_dict(), study_id)
        self._mt_pending = {"key": key, "progress": None}
        return None

    def ndt_mt_mesh(self, view: str | None = None) -> tuple[list, list, list]:
        """Barevná síť mapy MT pro okno (celkem, jeden směr pole, nanesení, prohlídka),
        v řezu oříznutá."""
        result = self.ndt_mt_map
        if result is None:
            return [], [], []
        nodes, triangles, colors = result.mesh(view)
        plane = self.section_plane
        return clip_mesh(nodes, triangles, colors, plane) if plane else (nodes, triangles, colors)

    def ndt_mt_describe(self, point: Any) -> list[str]:
        """Stav, směry a důvody místa mapy MT nejblíž bodu (klik do mapy); bez mapy prázdné."""
        result = self.ndt_mt_map
        if result is None or point is None:
            return []
        index = result.nearest(tuple(float(v) for v in point))
        return [] if index is None else result.describe(index)

    def export_ndt_mt(self, path: str | Path) -> Path:
        self._require_complete_part("výstup NDT")
        result = self.ndt_mt_map
        if result is None:
            raise DocumentError("Nejdřív spočítej mapu MT.")
        try:
            return result.write_csv(path)
        except OSError as exc:
            raise DocumentError(f"CSV nejde uložit: {exc}") from None

    @property
    def ndt_yoke(self) -> YokePlacement | None:
        """Přiložené jho (jen pohled) – platí pro díl a studii, pro které vzniklo."""
        if self.model_problem:
            return None
        if not self._mt_valid(self._yoke_view):
            self._yoke_view = None
            return None
        return self._yoke_view[1]

    def ndt_yoke_study(self) -> str | None:
        """Studie aktuálně zobrazeného jha (bez odhalování mezipaměti oknu)."""
        return self._yoke_view[0][1] if self.ndt_yoke is not None else None

    def ndt_yoke_settings(self) -> MtSettings | None:
        """Nastavení studie, se kterým vzniklo přiložené jho (obrys účinné oblasti)."""
        if self.ndt_yoke is None:
            return None
        return self.ndt_mt_settings(self._yoke_view[0][1])

    def clear_ndt_yoke(self) -> None:
        self._yoke_view = None

    def place_ndt_yoke(self, study_id: str, point: Any, angle: float) -> YokePlacement:
        """Přiložit jho sem: jho se středem v bodě povrchu, natočené o ``angle`` [°] (0° =
        průmět osy +X do plochy); jen pohled."""
        record = self._mt_record(study_id, "přiložení jha")
        settings = self.ndt_mt_settings(study_id)
        geo = self._ndt_geometry()
        try:
            surface = geo.surface_at(tuple(float(v) for v in point))
            placed = place_yoke(self.result.part, surface.point, surface.normal, float(angle),
                                settings, geo=geo)
        except (GeometryError, MtError) as exc:
            raise DocumentError(str(exc)) from None
        self._yoke_view = (self._mt_key(record["id"]), placed)
        return placed

    def ndt_mt_yoke_at(self, point: Any, view: str | None) -> YokePlacement | None:
        """Ukázat jho: pro místo mapy nejblíž bodu najde jho, jehož účinná oblast místo
        pokryje ve směru ``view`` (u „celkem“ v prvním platném směru); když žádné, ukáže
        nevyhovující jho se středem v místě. Jen pohled."""
        result, study_id = self.ndt_mt_map, self.ndt_mt_study()
        if result is None or point is None:
            return None
        index = result.nearest(tuple(float(v) for v in point))
        if index is None:
            return None
        sample = result.samples[index]
        if view is not None and view.startswith("d"):
            angle = int(view[1:]) * 22.5
        else:
            angle = sample.angles[0] if sample.angles else 0.0
        try:
            placed = find_yoke(self.result.part, sample.point, sample.normal, angle,
                               result.settings, geo=self._ndt_geometry())
        except MtError as exc:
            raise DocumentError(str(exc)) from None
        self._yoke_view = (self._mt_key(study_id), placed)
        return placed

    def ndt_yoke_drawing(self) -> tuple[Any, str, Any, Any, str, list] | None:
        """Jho pro prohlížeč: (tvar, stav v barvách sondy, pól, pól, popis, obrys účinné
        oblasti); None = žádné jho nebo ještě nemá tvar (pól nemá kam dosednout)."""
        placed = self.ndt_yoke
        if placed is None or not placed.shapes:
            return None
        if placed.ok:
            state = "uncertain" if placed.uncertain else "ok"
        else:
            state = "collision" if placed.kind in ("shoe", "body") else "overhang"
        ends = (*placed.poles, placed.center, placed.center)[:2]
        text = (f"jho {placed.spacing:g} mm".replace(".", ",")
                + ("" if placed.ok else " – nevejde se"))
        text = (self.ndt_preview_note(self._yoke_view[0][1]) + " " + text).strip()
        outline = placed.outline(self.ndt_yoke_settings()) if placed.ok else []
        return yoke_compound(placed), state, ends[0], ends[1], text, outline

    # --- NDT RT – geometrie projekce (etapa 13; nastavení a projekce ve studii, mapa pohled) --

    def ndt_rt_settings(self, study_id: str) -> RtSettings:
        """Nastavení a projekce RT studie (výchozí bez projekcí, když ve studii žádné není)."""
        try:
            return RtSettings.from_dict(self.ndt_study(study_id).get("rt"))
        except RtError as exc:
            raise DocumentError(str(exc)) from None

    def set_ndt_rt_settings(self, study_id: str, settings: RtSettings | dict[str, Any]
                            ) -> BuildResult | None:
        """Uloží nastavení i projekce RT do studie (jeden krok Zpět); stejné = žádná změna."""
        record = self.ndt_study(study_id)
        if record.get("method") != "RT":
            raise DocumentError("Nastavení RT má jen RT (radiografická) studie.")
        try:
            settings = (settings if isinstance(settings, RtSettings)
                        else RtSettings.from_dict(settings))
        except RtError as exc:
            raise DocumentError(str(exc)) from None
        if "rt" in record and RtSettings.from_dict(record["rt"]) == settings:
            return None
        data = settings.to_dict()
        return self._edit_study(study_id, lambda study: study.update(rt=data))

    def _rt_projections(self, study_id: str, projections: list[Projection]
                        ) -> BuildResult | None:
        settings = self.ndt_rt_settings(study_id)
        try:
            changed = settings.with_projections(projections)
        except RtError as exc:
            raise DocumentError(str(exc)) from None
        return self.set_ndt_rt_settings(study_id, changed)

    def _rt_projection(self, study_id: str, name: str) -> Projection:
        try:
            return self.ndt_rt_settings(study_id).projection(name)
        except RtError as exc:
            raise DocumentError(str(exc)) from None

    def ndt_rt_projection_at(self, study_id: str, point: Any) -> Projection:
        """Zdroj nad vybrané místo: nová (zatím neuložená) projekce zaměřená na bod povrchu,
        zdroj po normále ve výchozí vzdálenosti, detektor na ploše. U svaru delší strana
        detektoru podél svaru."""
        record = self._rt_record(study_id, "projekce RT")
        settings = self.ndt_rt_settings(study_id)
        geo = self._ndt_geometry()
        try:
            surface = geo.surface_at(tuple(float(v) for v in point))
            aim = tuple(round(v, 6) + 0.0 for v in surface.point)
            direction = tuple(round(v, 9) + 0.0 for v in surface.normal)
            projection = Projection(next_projection_name(settings), aim, direction)
            along = (record.get("target") or {}).get("frame", {}).get("axis")
            if along is not None:
                setup = prepare_rt(geo, settings, projection)
                normal = setup.normal if setup.ok else setup.axis
                projection = dataclasses.replace(
                    projection, detector_angle_deg=along_angle(normal, along))
        except (GeometryError, RtError) as exc:
            raise DocumentError(str(exc)) from None
        return projection

    def add_ndt_rt_projection(self, study_id: str, projection: Projection | dict[str, Any]
                              ) -> BuildResult | None:
        """Přidá projekci na konec seznamu (jeden krok Zpět)."""
        try:
            projection = (projection if isinstance(projection, Projection)
                          else Projection.from_dict(projection))
        except RtError as exc:
            raise DocumentError(str(exc)) from None
        return self._rt_projections(
            study_id, [*self.ndt_rt_settings(study_id).projections, projection])

    def set_ndt_rt_projection(self, study_id: str, name: str,
                              projection: Projection | dict[str, Any]) -> BuildResult | None:
        """Nahradí projekci ``name`` (i přejmenováním); stejná = žádná změna."""
        self._rt_projection(study_id, name)
        try:
            projection = (projection if isinstance(projection, Projection)
                          else Projection.from_dict(projection))
        except RtError as exc:
            raise DocumentError(str(exc)) from None
        return self._rt_projections(study_id, [
            projection if p.name == name else p
            for p in self.ndt_rt_settings(study_id).projections])

    def copy_ndt_rt_projection(self, study_id: str, name: str, shift: Any) -> BuildResult | None:
        """Kopie projekce posunutá o vektor ``shift`` [mm] (třeba podél svaru), nový název."""
        source = self._rt_projection(study_id, name)
        try:
            dx, dy, dz = (float(v) for v in shift)
        except (TypeError, ValueError):
            raise DocumentError("Posun kopie projekce musí být tři čísla [mm].") from None
        if math.isclose(dx * dx + dy * dy + dz * dz, 0.0, abs_tol=1e-18):
            raise DocumentError("Kopie by ležela na stejném místě – zadej nenulový posun.")
        settings = self.ndt_rt_settings(study_id)
        aim = tuple(round(a + d, 6) + 0.0 for a, d in zip(source.aim, (dx, dy, dz),
                                                         strict=True))
        copied = dataclasses.replace(source, name=next_projection_name(settings), aim=aim)
        return self._rt_projections(study_id, [*settings.projections, copied])

    def remove_ndt_rt_projection(self, study_id: str, name: str) -> BuildResult | None:
        self._rt_projection(study_id, name)
        return self._rt_projections(study_id, [
            p for p in self.ndt_rt_settings(study_id).projections if p.name != name])

    def _rt_record(self, study_id: str, what: str) -> dict[str, Any]:
        self._require_complete_part(what)
        record = self.ndt_study(study_id)
        if record.get("method") != "RT":
            raise DocumentError(f"{what.capitalize()} jde jen pro RT (radiografickou) studii.")
        if self.result is None or self.result.part is None:
            raise DocumentError(f"Model nemá těleso – {what} nemá na čem počítat.")
        return record

    def _rt_inputs(self, study_id: str, projections: list[str] | None = None
                   ) -> tuple[Any, dict[str, Any], RtSettings, str]:
        record = self._rt_record(study_id, "mapa RT")
        state = next((r.state for r in self.ndt_studies if r.id == study_id), "broken")
        if state == "stale":
            raise DocumentError("Studie je zastaralá (díl se změnil) – nejdřív ji potvrď.")
        if state != "ok":
            raise DocumentError("Mapa RT potřebuje platnou RT studii s oblastí (plochy nebo "
                                "cílový objem svaru).")
        settings = self.ndt_rt_settings(study_id)
        if projections:
            try:
                settings = settings.with_projections(
                    [settings.projection(name) for name in projections])
            except RtError as exc:
                raise DocumentError(str(exc)) from None
        return self.result.part, record, settings, self._require().material

    def _rt_key(self, study_id: str, projections: list[str] | None = None
                ) -> tuple[Any, ...]:
        return (self.result, study_id, repr(self.ndt_study(study_id)),
                self._require().material, tuple(projections or ()))

    def _rt_valid(self, cache: tuple[tuple[Any, ...], Any] | None) -> bool:
        if self.computing or cache is None:
            return False
        key = cache[0]
        try:
            current = self._rt_key(key[1], list(key[4]))
        except DocumentError:
            return False
        return key[0] is current[0] and key[1:] == current[1:]

    @property
    def ndt_rt_map(self) -> RtMap | None:
        """Mapa RT platí jen pro díl, ze kterého vznikla, a nezměněnou studii."""
        if self.model_problem:
            return None
        if not self._rt_valid(self._rt_cache):
            self._rt_cache = None
            return None
        return self._rt_cache[1]

    def ndt_rt_study(self) -> str | None:
        """Studie, ke které patří platná mapa RT."""
        return self._rt_cache[0][1] if self.ndt_rt_map is not None else None

    def clear_ndt_rt(self) -> None:
        self._rt_cache = None

    def ndt_rt_estimate(self, study_id: str, projections: list[str] | None = None
                        ) -> tuple[int, float, int, float]:
        """Odhad před spuštěním: (míst oblasti, krok sítě, projekcí, doba [s])."""
        part, record, settings, _material = self._rt_inputs(study_id, projections)
        try:
            return estimate_rt(part, record, settings)
        except (RtError, GeometryError) as exc:
            raise DocumentError(str(exc)) from None

    def compute_ndt_rt(self, study_id: str,
                       progress: Callable[[int, int], None] | None = None,
                       projections: list[str] | None = None) -> RtMap:
        """Spočítá mapu RT bez změny modelu (CLI, testy, pomocný proces); ``projections`` =
        jen tyto projekce."""
        part, record, settings, material = self._rt_inputs(study_id, projections)
        key = self._rt_key(study_id, projections)
        self.clear_ndt_rt()
        try:
            result = compute_rt(part, record, settings, material, progress=progress)
        except (RtError, GeometryError) as exc:
            raise DocumentError(str(exc)) from None
        except Exception as exc:  # noqa: BLE001 – chyby jádra nesmí shodit okno
            raise DocumentError(f"Mapu RT nejde spočítat: {exc}") from None
        self._rt_cache = (key, result)
        return result

    @property
    def rt_pending(self) -> bool:
        """Počítá se zrovna mapa RT v pomocném procesu?"""
        return self._rt_pending is not None

    @property
    def ndt_rt_progress(self) -> tuple[int, int] | None:
        """Průběh výpočtu mapy RT (hotovo, celkem)."""
        return self._rt_pending.get("progress") if self._rt_pending is not None else None

    def start_ndt_rt(self, study_id: str) -> RtMap | None:
        """Okno: mapa RT v pomocném procesu (jde zastavit); bez pomocného procesu hned."""
        self.ndt_rt_estimate(study_id)  # chyba oblasti hned, ne až z pomocného procesu
        if not self.ndt_rt_settings(study_id).projections:
            raise DocumentError("RT studie nemá projekci – přidej ji (Zdroj nad vybrané "
                                "místo).")
        if self._runner is None:
            return self.compute_ndt_rt(study_id)
        key = self._rt_key(study_id)
        self.clear_ndt_rt()
        self.failure = ""
        self._job = self._runner.submit_rt(self._require().to_dict(), study_id)
        self._rt_pending = {"key": key, "progress": None}
        return None

    def ndt_rt_mesh(self, view: str | None = None) -> tuple[list, list, list]:
        """Barevná síť mapy RT pro okno (celkem nebo jedna projekce „p0“ …), v řezu oříznutá;
        objem svaru = povrch cíle obarvený podle buněk 07B."""
        result = self.ndt_rt_map
        if result is None:
            return [], [], []
        if result.kind == "volume":
            return self._rt_volume_drawing(result, view)
        nodes, triangles, colors = result.mesh(view)
        plane = self.section_plane
        return clip_mesh(nodes, triangles, colors, plane) if plane else (nodes, triangles, colors)

    def _rt_volume_drawing(self, result: RtMap, view: str | None) -> tuple[list, list, list]:
        """Kresba objemové mapy RT (pamatuje se pro pohled a řez)."""
        plane = self.section_plane
        key = (id(result), view, plane)
        if self._rt_volume_cache is None or self._rt_volume_cache[0] != key:
            grid = result.volume_grid
            try:
                shape = _cut_preview(resolve_target(self.result.part, grid["target"]).shape,
                                     plane)
                states = [s.grade(view) for s in result.samples]
                cells = SimpleNamespace(assumptions=grid, samples=result.volume_samples,
                                        states=states)
                drawing = (volume_mesh(cells, shape, RT_COLORS) if shape is not None
                           else ([], [], []))
            except Exception:  # noqa: BLE001 – kresba je jen pohled, čísla zůstávají v panelu
                drawing = ([], [], [])
            self._rt_volume_cache = (key, drawing)
        return self._rt_volume_cache[1]

    def ndt_rt_drawing(self, study_id: str | None, name: str | None
                       ) -> tuple[Any, str, Any, Any, str, list] | None:
        """Projekce pro prohlížeč (jen pohled): (tělo zdroje a deska detektoru, stav v barvách
        sondy, zdroj, zaměřený bod, popis, paprsky ze zdroje do rohů detektoru); None = nejde
        nakreslit (bez dílu, během přepočtu, neznámá projekce)."""
        if self.model_problem:
            return None
        if (self.computing or study_id is None or name is None or self.result is None
                or self.result.part is None):
            return None
        try:
            record = self.ndt_study(study_id)
            settings = RtSettings.from_dict(record.get("rt"))
            projection = settings.projection(name)
        except (DocumentError, RtError):
            return None
        if record.get("method") != "RT":
            return None
        key = (self.result, study_id, name, repr(record))
        cached = self._rt_drawing_cache
        if cached is not None and cached[0][0] is key[0] and cached[0][1:] == key[1:]:
            return cached[1]
        try:
            setup = prepare_rt(self._ndt_geometry(), settings, projection)
            shapes = [s for s in setup_shapes(setup, settings) if s is not None]
        except Exception:  # noqa: BLE001 – kresba je jen pohled
            return None
        from build123d import Compound

        state = ("ok" if setup.ok else "collision"
                 if setup.kind in ("housing", "detector", "source_inside") else "uncertain")
        corners = []
        if setup.plane > 0:
            half_l, half_w = settings.detector_length_mm / 2, settings.detector_width_mm / 2
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                corner = tuple(c + setup.long[i] * a * half_l + setup.short[i] * b * half_w
                               for i, c in enumerate(setup.center))
                corners += [setup.source, corner]
        text = (f"{name}: f {projection.distance_mm:g} mm".replace(".", ",")
                + ("" if setup.ok else " – " + SETUP_FAILURES.get(setup.kind, "nejde")))
        text = (self.ndt_preview_note(study_id) + " " + text).strip()
        drawing = (Compound(shapes), state, setup.source, projection.aim, text, corners)
        self._rt_drawing_cache = (key, drawing)
        return drawing

    def ndt_rt_setup_text(self, study_id: str | None, name: str | None) -> str:
        """Jednou větou, jak projekce stojí (zdroj, detektor, odsunutí nebo proč nejde)."""
        if self.ndt_rt_drawing(study_id, name) is None:
            return ""
        try:
            settings = self.ndt_rt_settings(study_id)
            setup = prepare_rt(self._ndt_geometry(), settings, settings.projection(name))
        except (DocumentError, RtError, GeometryError):
            return ""
        return setup.text

    def ndt_rt_angles(self, point: Any, direction: Any
                      ) -> tuple[tuple[float, ...], float, float, str]:
        """Pro dialog projekce: vztažná kolmice, (sklon, natočení) směru ke zdroji vůči ní [°]
        a její popis. Leží-li zaměřený bod na ploše dílu, je to kolmice k ploše; jinak (střed
        otvoru, bod mimo díl) osa souřadnic nejbližší směru ke zdroji."""
        direction = tuple(float(v) for v in direction)
        normal, label = None, ""
        try:
            surface = self._ndt_geometry().surface_at(tuple(float(v) for v in point))
            if (abs(surface.distance) <= ON_SURFACE_MM
                    and sum(a * b for a, b in zip(surface.normal, direction, strict=True)) > 0):
                normal, label = tuple(surface.normal), "kolmice k ploše"
        except (GeometryError, DocumentError):
            pass
        if normal is None:
            index = max(range(3), key=lambda i: abs(direction[i]))
            sign = 1.0 if direction[index] >= 0 else -1.0
            normal = tuple(sign if i == index else 0.0 for i in range(3))
            label = f"osa {'+' if sign > 0 else '−'}{'XYZ'[index]}"
        tilt, turn = angles_of(normal, direction)
        return normal, tilt, turn, label

    def ndt_rt_preview(self, name: str, scale: int = 1) -> tuple[int, int, bytes] | None:
        """Náhled prozařované tloušťky projekce ze spočítané mapy jako obrázek RGB (šířka,
        výška, bajty) s tečkami míst oblasti; None = projekce bez náhledu."""
        result = self.ndt_rt_map
        if result is None:
            return None
        found = [i for i, p in enumerate(result.projections) if p.setup.name == name]
        if not found or result.images[found[0]] is None:
            return None
        index = found[0]
        radius = (PREVIEW_REACH[result.kind] * result.step_mm
                  * (result.projections[index].magnification or 1))
        return preview_rgb(result.images[index], result.marks(index), scale, radius)

    def export_ndt_rt_png(self, name: str, path: str | Path) -> Path:
        self._require_complete_part("výstup NDT")
        image = self.ndt_rt_image(name)
        if image is None:
            raise DocumentError("Náhled projekce není – spočítej mapu RT (projekce musí jít "
                                "přiložit).")
        scale = max(1, 960 // max(image.columns, 1))
        try:
            return write_png(path, *self.ndt_rt_preview(name, scale))
        except OSError as exc:
            raise DocumentError(f"PNG nejde uložit: {exc}") from None

    def ndt_rt_describe(self, point: Any) -> list[str]:
        """Stav místa mapy RT nejblíž bodu v každé projekci (klik do mapy); bez mapy prázdné."""
        result = self.ndt_rt_map
        if result is None or point is None:
            return []
        index = result.nearest(tuple(float(v) for v in point))
        return [] if index is None else result.describe(index)

    def ndt_rt_image(self, name: str) -> RtImage | None:
        """Náhled prozařované tloušťky projekce ``name`` ze spočítané mapy (jinak None)."""
        result = self.ndt_rt_map
        if result is None:
            return None
        found = [i for i, p in enumerate(result.projections) if p.setup.name == name]
        return result.images[found[0]] if found else None

    def export_ndt_rt(self, path: str | Path) -> Path:
        self._require_complete_part("výstup NDT")
        result = self.ndt_rt_map
        if result is None:
            raise DocumentError("Nejdřív spočítej mapu RT.")
        try:
            return result.write_csv(path)
        except OSError as exc:
            raise DocumentError(f"CSV nejde uložit: {exc}") from None

    # --- NDT předběžný audit (etapa 14, jen pohled) ------------------------------------------

    def _audit_key(self) -> tuple[Any, ...]:
        document = self._require()
        return (self.result, json.dumps(document.ndt or {}, sort_keys=True),
                document.material, json.dumps(document.thickness_map, sort_keys=True))

    def ndt_audit_items(self, include: list[str] | None = None,
                        access: list[str] | None = None) -> list[AuditItem]:
        """Co audit spočítá u každé studie (a mapy tloušťky s mezí), s odhadem doby a důvodem,
        proč ne. ``include`` = jen tyto studie (jinak všechny), ``access`` = UT studie, u nichž
        se má spustit návrh poloh (pomalé). Model se nemění."""
        self._require_complete_part("předběžný NDT audit")
        records = (self._require().ndt or {}).get("studies", [])
        known = {record["id"]: record.get("method") for record in records}
        if self._require().thickness_map is not None:
            known[THICKNESS_ID] = "TL"
        unknown = [sid for sid in (include or []) if sid not in known]
        if unknown:
            raise DocumentError(f"Studie {', '.join(unknown)} v modelu není (jsou: "
                                f"{', '.join(known) or 'žádné'}).")
        wrong = [sid for sid in (access or []) if known.get(sid) != "UT"]
        if wrong:
            raise DocumentError(f"Návrh poloh jde jen u UT studie – {', '.join(wrong)} není "
                                "UT studie tohoto modelu.")
        states = {r.id: r for r in self.ndt_studies}
        items = []
        for record in records:
            sid, method = record["id"], record.get("method", "")
            name = record.get("name") or sid
            item = AuditItem(sid, name, method)
            items.append(item)
            if include is not None and sid not in include:
                item.skip(SKIPPED_BY_USER)
                continue
            state = states.get(sid)
            if state is None or state.state != "ok":
                problem = STUDY_PROBLEMS.get(state.state if state else "broken", "")
                if state is not None and state.state == "broken" and state.messages:
                    problem += " " + " ".join(state.messages[:2])
                item.unavailable(problem)
                continue
            try:
                self._plan_audit_item(item, record, access or [])
            except DocumentError as exc:
                item.unavailable(str(exc))
        map_data = self._require().thickness_map
        if map_data is not None:
            item = AuditItem(THICKNESS_ID, "Mapa tloušťky stěny", "TL")
            items.append(item)
            if include is not None and THICKNESS_ID not in include:
                item.skip(SKIPPED_BY_USER)
            elif self.map_settings.limit is None:
                item.skip("mapa tloušťky nemá nastavenou mez (minimální tloušťku)")
            else:
                item.ready("thickness", "mapa tloušťky stěny s nastavením modelu "
                           f"(mez {self.map_settings.limit:g} mm)".replace(".", ","), 5.0)
        return items

    def _plan_audit_item(self, item: AuditItem, record: dict[str, Any],
                         access: list[str]) -> None:
        sid, method = item.study_id, item.method
        if method == "PT":
            count, step, seconds = self.ndt_pt_estimate(sid)
            item.ready("pt", f"mapa PT s nastavením studie ({count} míst po {step:g} mm)"
                       .replace(".", ","), seconds)
        elif method == "MT":
            samples, step, centers, _center_step, seconds = self.ndt_mt_estimate(sid)
            item.ready("mt", f"mapa MT s nastavením studie ({samples} míst po {step:g} mm, "
                       f"{centers} středů jha)".replace(".", ","), seconds)
        elif method == "RT":
            settings = self.ndt_rt_settings(sid)
            if not settings.projections:
                item.unavailable("RT studie nemá projekci – přidej ji v panelu NDT (Zdroj nad "
                                 "vybrané místo).")
                return
            samples, step, projections, seconds = self.ndt_rt_estimate(sid)
            item.ready("rt", f"mapa RT se všemi projekcemi studie ({projections}, asi {samples} "
                       f"míst po {step:g} mm)".replace(".", ","), seconds)
        elif method == "UT":
            plan_state, plan_text = self.ndt_plan_state(sid)
            if plan_state != "none" and plan_state != "stale":
                estimate = self.ndt_plan_estimate(sid)
                item.ready("plan", "ověření uloženého plánu dráhy a jeho pokrytí (jako Ověřit "
                           "a spočítat)", estimate.seconds[1])
                return
            session_result = self._ut_session_result(sid)
            if session_result is not None:
                item.ready("session", session_result[0], 0.0)
                item.result = session_result[1]
                return
            if sid in access:
                estimate = self.ndt_access_estimate(sid)
                item.ready("access", "návrh poloh sondy s výchozím nastavením (zaškrtnuto "
                           "uživatelem) – pokrytí kombinace nejvýš 3 variant",
                           estimate.seconds[1])
                return
            why = ("plán dráhy je zastaralý (" + plan_text + ")" if plan_state == "stale"
                   else "UT studie nemá plán dráhy ani výsledek spočítaný v tomto sezení")
            item.skip(f"{why}. Založ nebo ověř plán dráhy, spočítej pokrytí z přiložené sondy, "
                      "nebo zaškrtni návrh poloh (pomalé – minuty až desítky minut).")
        else:
            item.unavailable(f"Metoda {method} v auditu není.")

    def _ut_session_result(self, study_id: str) -> tuple[str, Any] | None:
        """Výsledek UT spočítaný v tomto sezení pro studii (plán, mapa pokrytí, návrh poloh)."""
        if self.ndt_plan_study() == study_id and self.ndt_plan_result is not None \
                and self.ndt_plan_result.coverage is not None:
            return ("ověřený plán dráhy z tohoto sezení", self.ndt_plan_result)
        request = self.ndt_placement_request
        coverage = self.ndt_coverage
        if coverage is not None and request is not None and request[0] == study_id:
            face = request[1].get("face", request[1]) if isinstance(request[1], dict) else {}
            point = face.get("at") if isinstance(face, dict) else None
            where = (" z polohy sondy (" + "; ".join(f"{v:g}" for v in point) + ") mm"
                     if point else "")
            return (f"mapa pokrytí spočítaná v tomto sezení{where}, úhel {request[2]:g}°"
                    .replace(".", ","), coverage)
        access = self.ndt_access
        if access is not None and self._access_cache[0][1] == study_id and access.union:
            return (f"návrh poloh spočítaný v tomto sezení – {access.combination_text()}",
                    access)
        return None

    def _audit_entry(self, item: AuditItem,
                     progress: Callable[[int, int], None] | None = None) -> AuditEntry:
        """Spočítá jednu položku auditu stávajícím výpočtem metody (nebo ji jen zapíše)."""
        record = None if item.study_id == THICKNESS_ID else self.ndt_study(item.study_id)
        state = next((r for r in self.ndt_studies if r.id == item.study_id), None)
        base = {"study_id": item.study_id, "name": item.name, "method": item.method,
                "record": record,
                "study_state": STATE_LABELS.get(state.state, state.state) if state else "",
                "verified": state.verified if state else "",
                "target": _target_text(record, state)}
        if item.status != "ready":
            return AuditEntry(status=item.status, reason=item.reason, **base)
        sid = item.study_id

        def staged(stage: str, done: int, total: int) -> None:
            if progress is not None:
                progress(done, total)

        started = time.monotonic()
        try:
            if item.action == "pt":
                result = self.compute_ndt_pt(sid, progress=progress)
            elif item.action == "mt":
                result = self.compute_ndt_mt(sid, progress=progress)
            elif item.action == "rt":
                result = self.compute_ndt_rt(sid, progress=progress)
            elif item.action == "plan":
                result = self.check_ndt_plan(sid, coverage=True, progress=staged)
            elif item.action == "access":
                result = self.compute_ndt_access(sid, progress=staged)
            elif item.action == "session":
                result = item.result
            elif item.action == "thickness":
                result = self._thickness_now() or compute_thickness(self.result.part,
                                                                    self.map_settings)
            else:
                raise DocumentError(f"Neznámý výpočet auditu „{item.action}“.")
        except DocumentError as exc:
            return AuditEntry(status="unavailable", reason=f"výpočet skončil chybou: {exc}",
                              seconds=time.monotonic() - started, **base)
        except Exception as exc:  # noqa: BLE001 – chyba jedné studie nesmí shodit audit
            return AuditEntry(status="unavailable",
                              reason=f"výpočet skončil chybou ({type(exc).__name__}: {exc})",
                              seconds=time.monotonic() - started, **base)
        entry = AuditEntry(status="done", source=item.source, result=result,
                           seconds=time.monotonic() - started, **base)
        try:
            entry.places  # noqa: B018 – výsledek musí jít shrnout
        except AuditError as exc:
            return AuditEntry(status="unavailable", reason=str(exc), seconds=entry.seconds,
                              **base)
        return entry

    def _thickness_now(self) -> ThicknessMap | None:
        """Mapa tloušťky spočítaná s nastavením modelu (jinak ji audit spočítá znovu)."""
        current = self.thickness_map
        return current if current is not None and current.settings == self.map_settings \
            else None

    def _audit_result(self, entries: list[AuditEntry], operator: str, complete: bool,
                      seconds: float) -> AuditResult:
        document = self._require()
        return AuditResult(document.name, str(self.path) if self.path else "",
                           part_fingerprint(document), document.material,
                           datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), build_text(),
                           libraries_text(), entries, operator=operator.strip(),
                           complete=complete, seconds=seconds)

    def compute_ndt_audit(self, include: list[str] | None = None,
                          access: list[str] | None = None, operator: str = "", *,
                          progress: Callable[[int, int, str, Any], None] | None = None,
                          on_entry: Callable[[AuditEntry], None] | None = None) -> AuditResult:
        """Předběžný NDT audit synchronně (CLI, testy, pomocný proces). Model se nemění."""
        items = self.ndt_audit_items(include, access)
        key = self._audit_key()
        started = time.monotonic()
        entries = []
        for index, item in enumerate(items):
            label = f"{item.study_id} {item.name}"

            def inner(done: int, total: int, index: int = index, label: str = label) -> None:
                if progress is not None:
                    progress(index, len(items), label, (done, total))

            if progress is not None:
                progress(index, len(items), label, None)
            entry = self._audit_entry(item, inner)
            entries.append(entry)
            if on_entry is not None:
                on_entry(entry)
        result = self._audit_result(entries, operator, True, time.monotonic() - started)
        self._audit_cache = (key, result)
        return result

    def start_ndt_audit(self, include: list[str] | None = None,
                        access: list[str] | None = None, operator: str = ""
                        ) -> AuditResult | None:
        """Okno: audit v pomocném procesu (hotové studie chodí průběžně, Zastavit je ponechá);
        bez pomocného procesu hned."""
        items = self.ndt_audit_items(include, access)
        if self._runner is None:
            return self.compute_ndt_audit(include, access, operator)
        local = {}  # co se nepočítá (neprovedeno, nedostupné, výsledek ze sezení, hotová mapa)
        remote = []
        for item in items:
            if item.status == "ready" and item.action != "session" and not (
                    item.action == "thickness" and self._thickness_now() is not None):
                remote.append(item.study_id)
            else:
                local[item.study_id] = self._audit_entry(item)
        self.clear_ndt_audit()
        self.failure = ""
        self._audit_pending = {"key": self._audit_key(), "items": items, "local": local,
                               "remote": {}, "progress": None, "operator": operator,
                               "started": time.monotonic()}
        if not remote:
            self._finish_audit(complete=True)
            return self.ndt_audit
        self._job = self._runner.submit_audit(self._require().to_dict(), remote,
                                              [sid for sid in (access or []) if sid in remote],
                                              operator)
        return None

    def _finish_audit(self, complete: bool) -> None:
        pending, self._audit_pending = self._audit_pending, None
        if pending is None:
            return
        entries = []
        for item in pending["items"]:
            entry = pending["local"].get(item.study_id) or pending["remote"].get(item.study_id)
            if entry is None:
                item.skip(STOPPED)
                entry = self._audit_entry(item)
            entries.append(entry)
        result = self._audit_result(entries, pending["operator"], complete,
                                    time.monotonic() - pending["started"])
        self._audit_cache = (pending["key"], result)

    @property
    def audit_pending(self) -> bool:
        """Počítá se zrovna předběžný audit v pomocném procesu?"""
        return self._audit_pending is not None

    @property
    def ndt_audit_progress(self) -> str:
        """Průběh auditu česky („studie 2 z 3 – s2 RT desky, 312 z 1086“), bez auditu
        prázdné."""
        pending = self._audit_pending
        if pending is None or pending["progress"] is None:
            return ""
        index, total, label, inner = pending["progress"]
        text = f"studie {index + 1} z {total} – {label}"
        return text + (f", {inner[0]} z {inner[1]}" if inner else "")

    @property
    def ndt_audit(self) -> AuditResult | None:
        """Hotový (i zastavený) audit, pokud platí pro díl, studie, materiál a mapu tloušťky."""
        if self.model_problem:
            return None
        if self._audit_cache is None or self.computing:
            return None
        key, result = self._audit_cache
        try:
            current = self._audit_key()
        except DocumentError:
            self._audit_cache = None
            return None
        if key[0] is not current[0] or key[1:] != current[1:]:
            self._audit_cache = None
            return None
        return result

    def clear_ndt_audit(self) -> None:
        self._audit_cache = None

    def adopt_ndt_audit_map(self, study_id: str) -> bool:
        """Mapa studie z auditu se stane mapou její metody v panelu NDT (jen pohled), aby ji
        nebylo třeba počítat znovu. False = audit ji nemá. Platnou mapu téže studie (třeba
        spočítanou po auditu) nechá být."""
        audit = self.ndt_audit
        if audit is None:
            return False
        try:
            entry = audit.entry(study_id)
        except AuditError:
            return False
        result = entry.result
        if entry.status != "done" or result is None:
            return False
        if isinstance(result, PtMap):
            if self.ndt_pt_study() != study_id:
                self._pt_cache = (self._pt_key(study_id), result)
        elif isinstance(result, MtMap):
            if self.ndt_mt_study() != study_id:
                self._mt_cache = (self._mt_key(study_id), result)
        elif isinstance(result, RtMap):
            if self.ndt_rt_study() != study_id:
                self._rt_cache = (self._rt_key(study_id), result)
        elif isinstance(result, PlanResult):
            if self.ndt_plan_study() != study_id:
                self._plan_cache = (self._plan_key(study_id), result)
        elif isinstance(result, AccessResult):
            if self.ndt_access is None or self._access_cache[0][1] != study_id:
                self._access_cache = (self._access_key(study_id), result)
        else:
            return result is self.ndt_coverage  # mapa pokrytí ze sezení už je v panelu
        return True

    def ndt_audit_mesh(self, study_id: str) -> tuple[list, list, list, bool]:
        """Barevná síť mapy studie z auditu pro okno (v řezu oříznutá) a zda jde o objem
        svaru (kreslí se navrch). Studie bez výsledku = prázdná síť."""
        audit = self.ndt_audit
        try:
            entry = audit.entry(study_id) if audit is not None else None
        except AuditError:
            entry = None
        result = entry.result if entry is not None and entry.status == "done" else None
        if isinstance(result, AccessResult):
            result = result.union
        elif isinstance(result, PlanResult):
            result = result.coverage.coverage if result.coverage is not None else None
        if result is None:
            return [], [], [], False
        if isinstance(result, (CoverageMap, VolumeCoverageMap)):
            return (*self.coverage_mesh(result), isinstance(result, VolumeCoverageMap))
        if isinstance(result, RtMap) and result.kind == "volume":
            return (*self._rt_volume_drawing(result, None), True)
        if isinstance(result, ThicknessMap):
            nodes, triangles, colors = result.nodes, result.triangles, result.node_colors()
        else:  # PT, MT a RT na plochách
            nodes, triangles, colors = result.mesh(None)
        plane = self.section_plane
        if plane:
            nodes, triangles, colors = clip_mesh(nodes, triangles, colors, plane)
        return nodes, triangles, colors, False

    def export_ndt_audit(self, folder: str | Path,
                         images: dict[str, list[tuple[str, bytes]]] | None = None
                         ) -> list[Path]:
        """Složka se zprávou auditu (HTML, CSV míst, podrobná CSV studií)."""
        self._require_complete_part("výstup NDT")
        audit = self.ndt_audit
        if audit is None:
            raise DocumentError("Nejdřív spusť předběžný NDT audit.")
        try:
            return audit.write_folder(folder, images)
        except OSError as exc:
            raise DocumentError(f"Zprávu nejde uložit: {exc}") from None

    # --- konstrukční návrhy pro NDT (etapa 15) -----------------------------------------------

    def ndt_design_settings(self) -> Design | None:
        """Zadání z modelu; výsledky se do souboru nikdy nezapisují."""
        data = (self._require().ndt or {}).get("design")
        return Design.from_dict(data) if data is not None else None

    def set_ndt_design(self, settings: Design | dict[str, Any] | None) -> BuildResult:
        """Zadání do ndt.design (jeden krok Zpět), None odstraní zadání."""
        design = (settings if isinstance(settings, Design) else
                  Design.from_dict(settings) if settings is not None else None)
        if design is not None:
            design.check(self._require())

        def mutate(doc: Document) -> None:
            if design is None:
                if doc.ndt is not None:
                    doc.ndt.pop("design", None)
            else:
                if doc.ndt is None:
                    doc.ndt = {"studies": []}
                doc.ndt["design"] = design.to_dict()

        return self._change(mutate)

    def _get_ndt_design(self, settings: Design | dict[str, Any] | None) -> Design:
        design = (self.ndt_design_settings() if settings is None else
                  settings if isinstance(settings, Design) else Design.from_dict(settings))
        if design is None:
            raise DocumentError("Model nemá zadání konstrukčního návrhu. Nejdřív ho nastav.")
        design.check(self._require())
        return design

    def _design_key(self) -> tuple[Any, ...]:
        """Výsledek patří přesnému stavu modelu i zadání."""
        return (id(self.result), json.dumps(self._require().to_dict(), sort_keys=True))

    def ndt_design_estimate(self, settings: Design | dict[str, Any] | None = None
                            ) -> tuple[int, float]:
        self._require_complete_part("odhad konstrukčního návrhu")
        design = self._get_ndt_design(settings)
        try:
            return estimate_design(design_baseline(self._require().to_dict(), design), design)
        except DesignError as exc:
            raise DocumentError(str(exc)) from None

    def compute_ndt_design(self, settings: Design | dict[str, Any] | None = None,
                           operator: str = "", *,
                           progress: Callable[[int, int, str, Any], None] | None = None,
                           on_variant: Callable[[DesignVariant], None] | None = None
                           ) -> DesignResult:
        """Synchronní výpočet na kopiích dílu (CLI a testy)."""
        self._require_complete_part("konstrukční návrh")
        design = self._get_ndt_design(settings)
        key, doc = self._design_key(), self._require()
        try:
            outcome = run_design(
                doc.to_dict(), design, model=doc.name, path=str(self.path or ""),
                fingerprint=part_fingerprint(doc),
                created=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                operator=operator, progress=progress, on_variant=on_variant)
        except DesignError as exc:
            raise DocumentError(str(exc)) from None
        self._design_cache = (key, outcome)
        return outcome

    def start_ndt_design(self, settings: Design | dict[str, Any] | None = None,
                         operator: str = "") -> DesignResult | None:
        """Výpočet variant na pozadí, s průběžným předáváním hotových variant."""
        self._require_complete_part("konstrukční návrh")
        design = self._get_ndt_design(settings)
        if self._runner is None:
            return self.compute_ndt_design(design, operator)
        doc = self._require()
        self._design_cache = None
        self.failure = ""
        self._design_pending = {
            "key": self._design_key(), "settings": design, "progress": None,
            "prepared": None, "variants": [], "started": time.monotonic(),
            "operator": operator, "model": doc.name, "path": str(self.path or ""),
            "fingerprint": part_fingerprint(doc), "material": doc.material,
            "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
        self._job = self._runner.submit_design(doc.to_dict(), design.to_dict(),
                                                str(self.path or ""), operator)
        return None

    def _finish_design(self, finished: DesignResult | None, error: str = "") -> None:
        """Zastavený výpočet uchová varianty, které už stihl dokončit."""
        pending, self._design_pending = self._design_pending, None
        if pending is None:
            return
        if finished is None and pending["prepared"] is not None and pending["variants"]:
            original, steps = pending["prepared"]
            finished = DesignResult(
                pending["settings"], pending["model"], pending["path"],
                pending["fingerprint"], pending["material"], pending["created"],
                build_text(), libraries_text(), original, steps, pending["variants"],
                complete=False, seconds=time.monotonic() - pending["started"],
                operator=pending["operator"])
        if finished is not None:
            self._design_cache = (pending["key"], finished)
        if error:
            self.failure = error

    @property
    def design_pending(self) -> bool:
        return self._design_pending is not None

    @property
    def ndt_design_progress(self) -> str:
        pending = self._design_pending
        if pending is None or pending["progress"] is None:
            return ""
        index, total, label, inner = pending["progress"]
        return (f"varianta {index + 1} z {total} – {label}" +
                (f", {inner[0]} z {inner[1]}" if inner is not None else ""))

    @property
    def ndt_design(self) -> DesignResult | None:
        """Srovnání platné pro současnou podobu modelu."""
        if self.model_problem:
            return None
        if self._design_cache is None or self.computing:
            return None
        key, outcome = self._design_cache
        if key != self._design_key():
            self._design_cache = None
            return None
        return outcome

    def clear_ndt_design(self) -> None:
        self._design_cache = None

    def _design_variant(self, index: int) -> DesignVariant:
        self._require_complete_part("použití konstrukční varianty")
        outcome = self.ndt_design
        if outcome is None:
            raise DocumentError("Nejdřív spočítej konstrukční návrh pro tento model.")
        variant = next((v for v in outcome.variants if v.index == index), None)
        if variant is None or index == 0:
            raise DocumentError("Vyber vypočtenou variantu (ne původní díl).")
        if variant.status != "passed" or variant.target is None or \
                variant.target.status != "done":
            raise DocumentError("Použít lze jen variantu, která prošla všemi podmínkami "
                                "a má vypočtenou cílovou studii.")
        return variant

    def apply_ndt_design_variant(self, index: int) -> BuildResult:
        """Výslovně zvolená varianta = jeden krok Zpět (potvrzení řeší okno etapy 15B)."""
        variant = self._design_variant(index)
        return self._change(lambda doc: doc.parameters.update(variant.values))

    def save_ndt_design_variant(self, index: int, path: str | Path) -> Path:
        """Nový soubor, nepřepisuje otevřený model ani existující soubory."""
        variant = self._design_variant(index)
        target = Path(path).resolve()
        if target.exists() or (self.path is not None and target == self.path.resolve()):
            raise DocumentError("Cílový soubor už existuje. Vyber nový název.")
        try:
            self._require().with_parameters(variant.values).save(target)
        except OSError as exc:
            raise DocumentError(f"Variantní model nelze uložit: {exc}") from None
        return target

    def export_ndt_design(self, folder: str | Path,
                          images: dict[str, list[tuple[str, bytes]]] | None = None
                          ) -> list[Path]:
        self._require_complete_part("výstup NDT")
        outcome = self.ndt_design
        if outcome is None:
            raise DocumentError("Nejdřív spočítej konstrukční návrh.")
        try:
            return outcome.write_folder(folder, images)
        except OSError as exc:
            raise DocumentError(f"Zprávu návrhu nelze uložit: {exc}") from None

    # --- NDT návrh poloh sondy (etapa 09, jen pohled) ------------------------------------

    def _placed_probe(self, study_id: str) -> Probe:
        """Sonda, která se přikládá: ukázka varianty návrhu poloh, jinak sonda studie."""
        override = self._probe_override
        if override is not None and override[0] == study_id:
            return override[1]
        return self.ndt_probe(study_id)

    @property
    def ndt_probe_preview(self) -> Probe | None:
        """Sonda ukázky varianty (úhel a odrazy zatím neuložené ve studii), jinak None."""
        if self.model_problem:
            return None
        request = self.ndt_placement_request
        override = self._probe_override
        if request is None or override is None or override[0] != request[0]:
            return None
        return override[1]

    def ndt_access_contact(self, shapes: list[Any]) -> list[dict[str, Any]]:
        """Kontaktní plochy vybrané ve 3D jako odkazy významem (jdou i do pomocného procesu)."""
        self._require_complete_part("práce s NDT geometrií")
        faces, edges = split_shapes(self._model_shapes(shapes))
        if edges or not faces:
            raise DocumentError("Kontaktní plochy vyber ve 3D – jen plochy, ne hrany.")
        return [surface_reference(face) for face in faces]

    def _access_key(self, study_id: str) -> tuple[Any, ...]:
        """Analýza platí pro díl (recept), cíl studie a rozměry a meze sondy; úhel a odrazy
        studie ne – *Použít variantu* je mění a tabulka má zůstat."""
        probe = self.ndt_probe(study_id)
        record = self.ndt_study(study_id)
        return (part_fingerprint(self._require()), study_id, repr(record.get("target")),
                (probe.kind, probe.diameter, probe.length, probe.width, probe.height,
                 probe.front, probe.max_gap, probe.reserve))

    def ndt_access_analysis(self, study_id: str, options: AccessOptions | dict | None = None,
                            contact: list[dict[str, Any]] | None = None) -> Analysis:
        """Připravená analýza (bez výpočtu) – pro odhad i výpočet."""
        self._require_complete_part("návrh poloh sondy")
        record = self.ndt_study(study_id)
        state = next((r.state for r in self.ndt_studies if r.id == study_id), None)
        if record["method"] != "UT" or state != "ok":
            raise DocumentError("Návrh poloh potřebuje platnou UT studii s kontrolovanou "
                                "oblastí.")
        geo = self._ndt_geometry()
        target = record.get("target") or {}
        if target.get("kind") in ("volume", "weld"):
            inputs: dict[str, Any] = {"volume": target}
        else:
            faces, problems = geo.faces_of(target)
            if problems or not faces:
                raise DocumentError("Kontrolovanou oblast nejde určit: " + " ".join(problems))
            inputs = {"faces": faces}
        contact_faces = None
        if contact:
            contact_faces = []
            for reference in contact:
                try:
                    contact_faces.append(find_face(self.result.part, reference["face"])[0])
                except (SelectionError, KeyError, TypeError):
                    raise DocumentError("Vybraná kontaktní plocha v dílu už není – vyber "
                                        "plochy znovu.") from None
        if isinstance(options, dict):
            options = AccessOptions(**{k: tuple(v) if k in ("bounces", "angles") else v
                                       for k, v in options.items()})
        try:
            return Analysis(geo, self.ndt_probe(study_id), **inputs,
                            contact_faces=contact_faces, options=options,
                            device_lines=self.ndt_device_lines(study_id),
                            assumptions={"study_id": study_id,
                                         "part_fingerprint": part_fingerprint(self._require()),
                                         "parameters": dict(self.result.parameters),
                                         "contact": contact or []})
        except (AccessError, TargetError) as exc:
            raise DocumentError(str(exc)) from None

    def ndt_access_estimate(self, study_id: str, options: AccessOptions | dict | None = None,
                            contact: list[dict[str, Any]] | None = None) -> AccessEstimate:
        return self.ndt_access_analysis(study_id, options, contact).estimate()

    def compute_ndt_access(self, study_id: str, options: AccessOptions | dict | None = None,
                           contact: list[dict[str, Any]] | None = None, *,
                           progress: Callable[[str, int, int], None] | None = None,
                           on_prepared: Callable[[Preparation], None] | None = None,
                           on_variant: Callable[[int, Any], None] | None = None
                           ) -> AccessResult:
        """Návrh poloh synchronně (CLI, testy, pomocný proces). Model se nemění."""
        analysis = self.ndt_access_analysis(study_id, options, contact)
        key = self._access_key(study_id)
        try:
            result = analysis.run(progress, on_variant, on_prepared)
        except AccessError as exc:
            raise DocumentError(str(exc)) from None
        except Exception as exc:  # noqa: BLE001 – chyby jádra nesmí shodit okno
            raise DocumentError(f"Návrh poloh nejde spočítat: {exc}") from None
        self._access_cache = (key, result)
        return result

    def start_ndt_access(self, study_id: str, options: AccessOptions | dict | None = None,
                         contact: list[dict[str, Any]] | None = None) -> AccessResult | None:
        """Okno: analýza v pomocném procesu s průběhem; *Zastavit* nechá hotové varianty."""
        analysis = self.ndt_access_analysis(study_id, options, contact)  # chyby hned, česky
        if self._runner is None:
            return self.compute_ndt_access(study_id, options, contact)
        self.failure = ""
        self._access_cache = None
        self._access_pending = {"key": self._access_key(study_id), "preparation": None,
                                "results": [], "progress": ("Připravuji návrh poloh", 0, 0)}
        self._job = self._runner.submit_access(
            self._require().to_dict(), study_id,
            dataclasses.asdict(analysis.options), contact)
        return None

    @property
    def access_pending(self) -> bool:
        return self._access_pending is not None

    @property
    def ndt_access_progress(self) -> str:
        """Průběh běžící analýzy česky („3. kolo: pokrytí variant 7 z 24“), jinak prázdné."""
        if self._access_pending is None:
            return ""
        stage, done, total = self._access_pending["progress"]
        text = f"{stage} {done + 1 if done < total else done} z {total}" if total else stage
        results = [r for r in self._access_pending["results"] if isinstance(r, VariantResult)]
        prepared = self._access_pending["preparation"]
        if results and prepared is not None:
            left = len(prepared.candidates) - len(self._access_pending["results"])
            seconds = left * sum(r.seconds for r in results) / len(results)
            text += (f", zbývá asi {max(1, round(seconds / 60))} min" if seconds >= 90
                     else f", zbývá asi {max(1, round(seconds))} s")
        return text

    @property
    def ndt_access(self) -> AccessResult | None:
        """Hotová (i zastavená) analýza, pokud platí pro díl, cíl a rozměry sondy."""
        if self.model_problem:
            return None
        if self._access_cache is None or self.document is None:
            return None
        key, result = self._access_cache
        try:
            if not self._ndt_study_is_ok(key[1]) or self._access_key(key[1]) != key:
                self._access_cache = None
                return None
        except DocumentError:
            self._access_cache = None
            return None
        return result

    def clear_ndt_access(self) -> None:
        self._access_cache = None

    def _access_variant(self, rank: int) -> tuple[str, VariantResult]:
        self._require_complete_part("práce s NDT geometrií")
        result = self.ndt_access
        if result is None:
            raise DocumentError("Nejdřív spusť návrh poloh sondy.")
        if not 0 <= rank < len(result.variants):
            raise DocumentError("Taková varianta v návrhu není.")
        found = result.variants[rank]
        if found.best_reference is None:
            raise DocumentError("Tahle varianta z cíle nic nepokryje – není kam sondu přiložit.")
        return result.preparation.assumptions["study_id"], found

    def _variant_probe(self, study_id: str, found: VariantResult) -> Probe:
        """Sonda studie s úhlem a odrazy varianty; změněný úhel = „zadáno ručně“."""
        probe = self.ndt_probe(study_id)
        variant = found.variant
        if probe.kind == "straight":
            return dataclasses.replace(probe, bounces=variant.bounces)
        if abs(probe.beam_angle - variant.beta) <= 1e-9:
            return dataclasses.replace(probe, bounces=variant.bounces)
        origins = probe.origins
        if origins:
            origins = tuple({**dict(origins), "beam_angle": "entered"}.items())
        return dataclasses.replace(probe, beam_angle=variant.beta, bounces=variant.bounces,
                                   origins=origins, angle_note="")

    def show_ndt_access_variant(self, rank: int) -> Placement:
        """Přiloží sondu do nejlepší polohy varianty (jen pohled – úhel a odrazy varianty se
        ukážou, ale do studie se neuloží)."""
        study_id, found = self._access_variant(rank)
        probe = self._variant_probe(study_id, found)
        previous = (self.ndt_placement_request, self._probe_override)
        self._probe_override = None if probe == self.ndt_probe(study_id) else (study_id, probe)
        self.ndt_placement_request = (study_id, found.best_reference, found.variant.angle_deg)
        self._line_scan = None
        self.ndt_scan_index = 0
        placement = self.ndt_placement
        if placement is None:
            error = self.ndt_placement_error
            self.ndt_placement_request, self._probe_override = previous
            raise DocumentError(error)
        return placement

    def apply_ndt_access_variant(self, rank: int) -> BuildResult | None:
        """Uloží úhel a odrazy varianty do studie (jeden krok Zpět, jen když se liší) a přiloží
        sondu do nejlepší polohy varianty. Návrh poloh zůstane."""
        study_id, found = self._access_variant(rank)
        probe = self._variant_probe(study_id, found)
        result = None
        if probe != self.ndt_probe(study_id):
            result = self.set_ndt_device(study_id, probe)
        self._probe_override = None
        self.ndt_placement_request = (study_id, found.best_reference, found.variant.angle_deg)
        self._line_scan = None
        self.ndt_scan_index = 0
        return result

    def ndt_access_points(self) -> tuple[list, list, list[str]]:
        """Mapa kontaktních ploch návrhu poloh: body, barvy a stavy (all / some / none / away)."""
        result = self.ndt_access
        if result is None:
            return [], [], []
        contact = result.preparation.contact
        return ([c.point for c in contact], [CONTACT_COLORS[c.state] for c in contact],
                [c.state for c in contact])

    def export_ndt_access(self, path: str | Path) -> Path:
        self._require_complete_part("výstup NDT")
        result = self.ndt_access
        if result is None:
            raise DocumentError("Nejdřív spusť návrh poloh sondy.")
        try:
            return result.write_csv(path)
        except OSError as exc:
            raise DocumentError(f"CSV nejde uložit: {exc}") from None

    # --- NDT plán dráhy UT sondy (etapa 10) ----------------------------------------------

    def ndt_zones(self, study_id: str) -> tuple[Zone, ...]:
        """Zakázané zóny studie (kvádry, kam sonda nesmí)."""
        try:
            return zones_from(self.ndt_study(study_id).get("zones"))
        except PlanError as exc:
            raise DocumentError(str(exc)) from None

    def set_ndt_zones(self, study_id: str, zones: list[dict[str, Any] | Zone]) -> BuildResult:
        """Uloží zakázané zóny studie – jeden krok Zpět. Plán dráhy se tím jen znovu ověří
        (sám se neposune); zadání studie ani její ověření se nemění."""
        try:
            records = [zone.to_dict() if isinstance(zone, Zone)
                       else Zone.from_dict(zone, index).to_dict()
                       for index, zone in enumerate(zones, start=1)]
        except PlanError as exc:
            raise DocumentError(str(exc)) from None

        def update(study: dict[str, Any]) -> None:
            if records:
                study["zones"] = records
            else:
                study.pop("zones", None)

        return self._edit_study(study_id, update)

    @property
    def ndt_placement_zone(self) -> str:
        """Upozornění, když ručně přiložená sonda zasahuje do zakázané zóny studie (zóny
        platí pro plán dráhy – přiložení samo nezakazují); jinak prázdné."""
        placement, request = self.ndt_placement, self.ndt_placement_request
        if placement is None or request is None:
            return ""
        try:
            zones = self.ndt_zones(request[0])
        except DocumentError:
            return ""
        found = zone_hit(placement.body, zones)
        if found is None:
            return ""
        return (f"Sonda zasahuje do zakázané zóny {found.label(zones.index(found))} – plán "
                "dráhy sem nepojede.")

    def ndt_plan(self, study_id: str) -> Plan | None:
        """Plán dráhy uložený ve studii, None = žádný."""
        data = self.ndt_study(study_id).get("plan")
        if data is None:
            return None
        try:
            return Plan.from_dict(data)
        except PlanError as exc:
            raise DocumentError(str(exc)) from None

    def _plan_prints(self, study_id: str) -> dict[str, str]:
        """Otisky zadání, pro které plán vznikl: díl (recept), cíl a rozměry sondy."""
        record = self.ndt_study(study_id)
        return {"part": part_fingerprint(self._require()),
                "target": target_fingerprint(record.get("target") or {}),
                "probe": probe_fingerprint(self.ndt_probe(study_id))}

    def _plan_key(self, study_id: str) -> tuple[Any, ...]:
        """Výsledek ověření platí pro díl, cíl, sondu, zóny a přesně tento plán."""
        record = self.ndt_study(study_id)
        return (part_fingerprint(self._require()), study_id,
                json.dumps(record.get("plan"), sort_keys=True),
                json.dumps(record.get("zones"), sort_keys=True),
                json.dumps(record.get("target"), sort_keys=True),
                json.dumps(self.ndt_probe(study_id).to_dict(), sort_keys=True))

    @property
    def ndt_plan_result(self) -> PlanResult | None:
        """Ověřený (a případně spočítaný) plán, pokud platí pro současné zadání."""
        if self.model_problem:
            return None
        if self._plan_cache is None or self.document is None:
            return None
        key, result = self._plan_cache
        try:
            if not self._ndt_study_is_ok(key[1]) or self._plan_key(key[1]) != key:
                self._plan_cache = None
                return None
        except DocumentError:
            self._plan_cache = None
            return None
        return result

    def ndt_plan_study(self) -> str | None:
        """Studie, ke které patří ``ndt_plan_result``."""
        return self._plan_cache[0][1] if self.ndt_plan_result is not None else None

    def clear_ndt_plan_result(self) -> None:
        self._plan_cache = None

    def ndt_plan_state(self, study_id: str) -> tuple[str, str]:
        """Stav plánu: none / stale (jiný díl, cíl nebo sonda) / unchecked / invalid / ok
        a český text."""
        plan = self.ndt_plan(study_id)
        if plan is None:
            return "none", "Studie zatím nemá plán dráhy."
        prints = self._plan_prints(study_id)
        changed = [label for key, label in (("part", "díl"), ("target", "cíl"),
                                            ("probe", "sonda"))
                   if getattr(plan, key) and getattr(plan, key) != prints[key]]
        if changed:
            return "stale", (f"Plán je zastaralý – změnil se {', '.join(changed)}. Sám se "
                             "neposune: ověř ho znovu, nebo ho sestav znovu.")
        result = self.ndt_plan_result
        if result is None or self.ndt_plan_study() != study_id:
            return "unchecked", "Plán zatím není na tomto dílu ověřený."
        if not result.check.valid:
            return "invalid", "Plán neplatí: " + " ".join(result.check.problems[:3])
        return "ok", "Plán platí" + (" (ručně upravený)." if plan.edited else ".")

    def ndt_planner(self, study_id: str, options: PlanOptions | dict | None = None
                    ) -> Planner:
        """Plánovač pro studii (cíl, sonda, zóny) – bez výpočtu."""
        self._require_complete_part("plán dráhy")
        record = self.ndt_study(study_id)
        state = next((r.state for r in self.ndt_studies if r.id == study_id), None)
        if record["method"] != "UT" or state != "ok":
            raise DocumentError("Plán dráhy potřebuje platnou UT studii s kontrolovanou "
                                "oblastí.")
        geo = self._ndt_geometry()
        target = record.get("target") or {}
        if target.get("kind") in ("volume", "weld"):
            inputs: dict[str, Any] = {"volume": target}
        else:
            faces, problems = geo.faces_of(target)
            if problems or not faces:
                raise DocumentError("Kontrolovanou oblast nejde určit: " + " ".join(problems))
            inputs = {"faces": faces}
        if isinstance(options, dict):
            options = PlanOptions(**options)
        try:
            return Planner(geo, self.ndt_probe(study_id), **inputs,
                           zones=self.ndt_zones(study_id), options=options,
                           device_lines=self.ndt_device_lines(study_id),
                           assumptions={"study_id": study_id,
                                        "part_fingerprint": part_fingerprint(self._require()),
                                        "parameters": dict(self.result.parameters)})
        except (PlanError, TargetError) as exc:
            raise DocumentError(str(exc)) from None

    def ndt_plan_passes(self, study_id: str, source: str = "placement",
                        rank: int | None = None) -> list[dict[str, Any]]:
        """Co naplánovat, jako odkazy významem (jdou i do pomocného procesu): přiložená
        sonda (``placement``), varianta návrhu poloh (``variant`` + ``rank``) nebo jeho
        kombinace (``combination``)."""
        if source == "placement":
            request, placed = self.ndt_placement_request, self.ndt_placement
            if request is None or request[0] != study_id or placed is None:
                raise DocumentError("Nejdřív přilož sondu studie na kontaktní plochu, nebo "
                                    "vyber variantu návrhu poloh.")
            if placed.surface is None or placed.surface.kind != "plane":
                raise DocumentError("Plán dráhy umí jen rovinné kontaktní plochy – přilož "
                                    "sondu na rovinnou plochu.")
            probe = self._placed_probe(study_id)
            return [{"face": request[1]["face"], "point": list(placed.origin),
                     "angle_deg": request[2],
                     "beta": 0.0 if probe.kind == "straight" else probe.beam_angle,
                     "bounces": probe.bounces}]
        result = self.ndt_access
        if result is None or result.preparation.assumptions.get("study_id") != study_id:
            raise DocumentError("Nejdřív spusť návrh poloh sondy pro tuto studii.")
        if source == "variant":
            if rank is None or not 0 <= rank < len(result.variants):
                raise DocumentError("Taková varianta v návrhu není.")
            indices = [rank]
        elif source == "combination":
            indices = list(result.combination)
            if not indices:
                raise DocumentError("Návrh poloh nemá žádnou kombinaci – z cíle nic nepokryje.")
        else:
            raise DocumentError("Plán jde sestavit z přiložené sondy, varianty nebo kombinace.")
        passes = []
        for index in indices:
            found = result.variants[index]
            if found.best_reference is None:
                raise DocumentError(f"Varianta #{index + 1} z cíle nic nepokryje – není z čeho "
                                    "plánovat.")
            variant = found.variant
            passes.append({"face": found.best_reference["face"], "point": list(found.best),
                           "angle_deg": variant.angle_deg, "beta": variant.beta,
                           "bounces": variant.bounces})
        return passes

    def _plan_specs(self, passes: list[dict[str, Any]]) -> list[PassSpec]:
        from build123d import GeomType

        specs = []
        for number, request in enumerate(passes, start=1):
            try:
                face, at = find_face(self.result.part, request["face"])
            except (SelectionError, KeyError, TypeError):
                raise DocumentError(f"Plocha průchodu {number} v dílu už není – sestav plán "
                                    "znovu z přiložené sondy.") from None
            if face.geom_type != GeomType.PLANE:
                raise DocumentError(f"Plocha průchodu {number} není rovinná – plán dráhy umí "
                                    "jen rovinné kontaktní plochy.")
            point = request.get("point") or (at.X, at.Y, at.Z)
            specs.append(PassSpec(face, tuple(float(v) for v in point),
                                  float(request["angle_deg"]), float(request["beta"]),
                                  int(request["bounces"])))
        return specs

    def _plan_faces(self, plan: Plan) -> list[Any]:
        faces = []
        for number, plan_pass in enumerate(plan.passes, start=1):
            try:
                faces.append(find_face(self.result.part, plan_pass.face)[0])
            except (SelectionError, KeyError, TypeError):
                raise DocumentError(f"Plocha průchodu {number} v dílu už není – sestav plán "
                                    "znovu.") from None
        return faces

    def ndt_plan_estimate(self, study_id: str, passes: list[dict[str, Any]] | None = None,
                          options: PlanOptions | dict | None = None) -> PlanEstimate:
        planner = self.ndt_planner(study_id, options)
        passes = self.ndt_plan_passes(study_id) if passes is None else passes
        return planner.estimate(self._plan_specs(passes))

    def _run_plan(self, study_id: str, passes: list[dict[str, Any]] | None,
                  options: PlanOptions | dict | None,
                  progress: Callable[[str, int, int], None] | None) -> PlanResult:
        """Sestavení, ověření a pokrytí bez uložení (synchronně i v pomocném procesu)."""
        planner = self.ndt_planner(study_id, options)
        specs = self._plan_specs(self.ndt_plan_passes(study_id) if passes is None else passes)
        try:
            result = planner.run(specs, progress)
        except PlanError as exc:
            raise DocumentError(str(exc)) from None
        except Exception as exc:  # noqa: BLE001 – chyby jádra nesmí shodit okno
            raise DocumentError(f"Plán dráhy nejde spočítat: {exc}") from None
        plan = dataclasses.replace(result.plan, edited=False, **self._plan_prints(study_id))
        return dataclasses.replace(result, plan=plan)

    def _store_plan(self, study_id: str, result: PlanResult) -> PlanResult:
        """Uloží sestavený plán do studie (jeden krok Zpět); bez úseků nic neuloží."""
        if result.plan.passes:
            record = result.plan.to_dict()
            self._edit_study(study_id, lambda study: study.update(plan=record))
            self._plan_cache = (self._plan_key(study_id), result)
        return result

    def compute_ndt_plan(self, study_id: str, passes: list[dict[str, Any]] | None = None,
                         options: PlanOptions | dict | None = None, *,
                         progress: Callable[[str, int, int], None] | None = None
                         ) -> PlanResult:
        """Sestaví plán dráhy (z přiložené sondy, nebo z ``passes``), ověří ho, spočítá
        pokrytí a uloží do studie – jeden krok Zpět. Když nenajde žádný úsek, nic neuloží
        (důvody jsou v ``result.dropped``)."""
        return self._store_plan(study_id, self._run_plan(study_id, passes, options, progress))

    def _check_options(self, plan: Plan, options: PlanOptions | dict | None) -> PlanOptions:
        if isinstance(options, PlanOptions):
            options = dataclasses.asdict(options)
        keep = {key: value for key, value in (options or {}).items()
                if key in ("target_step_mm", "tolerance_mm", "spread_deg", "compare",
                           "robustness")}
        return PlanOptions.for_plan(plan, **keep)

    def check_ndt_plan(self, study_id: str, options: PlanOptions | dict | None = None, *,
                       coverage: bool = True, confirm: bool = False,
                       progress: Callable[[str, int, int], None] | None = None) -> PlanResult:
        """Ověří uložený plán na současném dílu (po kontrolním kroku, nájezd, zóny)
        a s ``coverage`` spočítá i pokrytí. Model se nemění – jen s ``confirm`` se platný
        zastaralý plán přihlásí k současnému dílu, cíli a sondě (jeden krok Zpět)."""
        self._require_complete_part("ověření plánu dráhy")
        plan = self.ndt_plan(study_id)
        if plan is None:
            raise DocumentError("Studie zatím nemá plán dráhy.")
        planner = self.ndt_planner(study_id, self._check_options(plan, options))
        faces = self._plan_faces(plan)
        key = self._plan_key(study_id)
        try:
            result = planner.evaluate(plan, faces, progress, coverage=coverage)
        except PlanError as exc:
            raise DocumentError(str(exc)) from None
        except Exception as exc:  # noqa: BLE001 – chyby jádra nesmí shodit okno
            raise DocumentError(f"Plán dráhy nejde ověřit: {exc}") from None
        self._plan_cache = (key, result)
        if confirm:
            self._confirm_plan(study_id, result)
        return result

    def _confirm_plan(self, study_id: str, result: PlanResult) -> None:
        """Platný plán převezme otisky současného zadání (už není zastaralý)."""
        prints = self._plan_prints(study_id)
        record = self.ndt_study(study_id).get("plan") or {}
        if not result.check.valid or all(record.get(k) == v for k, v in prints.items()):
            return
        self._edit_study(study_id, lambda study: study["plan"].update(prints))
        result = dataclasses.replace(result, plan=dataclasses.replace(result.plan, **prints))
        self._plan_cache = (self._plan_key(study_id), result)

    def start_ndt_plan(self, study_id: str, passes: list[dict[str, Any]] | None = None,
                       options: PlanOptions | dict | None = None) -> PlanResult | None:
        """Okno: sestavení plánu v pomocném procesu; hotový plán uloží ``poll``."""
        planner = self.ndt_planner(study_id, options)  # chyby hned, česky
        passes = self.ndt_plan_passes(study_id) if passes is None else passes
        self._plan_specs(passes)
        if self._runner is None:
            return self.compute_ndt_plan(study_id, passes, options)
        self.failure = ""
        self._plan_pending = {"mode": "build", "study_id": study_id,
                              "progress": ("Připravuji plán dráhy", 0, 0)}
        self._job = self._runner.submit_plan(self._require().to_dict(), study_id, "build",
                                             passes, dataclasses.asdict(planner.options), True)
        return None

    def start_ndt_plan_check(self, study_id: str, options: PlanOptions | dict | None = None,
                             coverage: bool = True, confirm: bool = False
                             ) -> PlanResult | None:
        """Okno: ověření (a pokrytí) uloženého plánu v pomocném procesu."""
        self._require_complete_part("ověření plánu dráhy")
        plan = self.ndt_plan(study_id)
        if plan is None:
            raise DocumentError("Studie zatím nemá plán dráhy.")
        checked = self._check_options(plan, options)
        self.ndt_planner(study_id, checked)
        self._plan_faces(plan)
        if self._runner is None:
            return self.check_ndt_plan(study_id, checked, coverage=coverage, confirm=confirm)
        self.failure = ""
        self._plan_pending = {"mode": "check", "study_id": study_id, "confirm": confirm,
                              "key": self._plan_key(study_id),
                              "progress": ("Ověřuji plán dráhy", 0, 0)}
        self._job = self._runner.submit_plan(self._require().to_dict(), study_id, "check",
                                             None, dataclasses.asdict(checked), coverage)
        return None

    @property
    def plan_pending(self) -> bool:
        return self._plan_pending is not None

    @property
    def ndt_plan_progress(self) -> str:
        if self._plan_pending is None:
            return ""
        stage, done, total = self._plan_pending["progress"]
        return f"{stage} {min(done + 1, total)} z {total}" if total > 1 else stage

    def _plan_finished(self, finished: Any) -> None:
        pending, self._plan_pending = self._plan_pending, None
        if finished.plan is None:
            self.failure = finished.error
            return
        if pending["mode"] == "build":
            try:
                self._store_plan(pending["study_id"], finished.plan)
            except DocumentError as exc:
                self.failure = str(exc)
            if not finished.plan.plan.passes:
                self.failure = ("Plán dráhy nenašel žádný úsek: "
                                + " ".join(finished.plan.dropped))
        elif pending["key"] == self._plan_key(pending["study_id"]):
            self._plan_cache = (pending["key"], finished.plan)
            if pending["confirm"]:
                try:
                    self._confirm_plan(pending["study_id"], finished.plan)
                except DocumentError as exc:
                    self.failure = str(exc)

    # úpravy plánu (každá jeden krok Zpět; plán je pak „ručně upravený“)

    def _edit_plan(self, study_id: str, change: Callable[[list[dict[str, Any]]], Any]
                   ) -> BuildResult:
        plan = self.ndt_plan(study_id)
        if plan is None:
            raise DocumentError("Studie zatím nemá plán dráhy.")
        data = plan.to_dict()
        change(data["passes"])
        data["passes"] = [p for p in data["passes"] if p["segments"]]
        data["edited"] = True
        try:
            Plan.from_dict(data)
        except PlanError as exc:
            raise DocumentError(str(exc)) from None
        return self._edit_study(study_id, lambda study: study.update(plan=data))

    @staticmethod
    def _segments_of(passes: list[dict[str, Any]], pass_index: int, segment: int
                     ) -> list[dict[str, Any]]:
        if not 0 <= pass_index < len(passes):
            raise DocumentError(f"Plán nemá průchod {pass_index + 1}.")
        segments = passes[pass_index]["segments"]
        if not 0 <= segment < len(segments):
            raise DocumentError(f"Průchod {pass_index + 1} nemá úsek {segment + 1}.")
        return segments

    def remove_ndt_plan_segment(self, study_id: str, pass_index: int, segment: int
                                ) -> BuildResult:
        return self._edit_plan(study_id, lambda passes: self._segments_of(
            passes, pass_index, segment).pop(segment))

    def reverse_ndt_plan_segment(self, study_id: str, pass_index: int, segment: int
                                 ) -> BuildResult:
        def change(passes: list[dict[str, Any]]) -> None:
            item = self._segments_of(passes, pass_index, segment)[segment]
            item["start"], item["end"] = item["end"], item["start"]

        return self._edit_plan(study_id, change)

    def move_ndt_plan_segment(self, study_id: str, pass_index: int, segment: int,
                              offset: int) -> BuildResult:
        """Přeřadí úsek v pořadí jízdy průchodu o ``offset`` (−1 nahoru, +1 dolů)."""
        def change(passes: list[dict[str, Any]]) -> None:
            segments = self._segments_of(passes, pass_index, segment)
            target = segment + offset
            if not 0 <= target < len(segments):
                raise DocumentError("Úsek už je na kraji průchodu – dál posunout nejde.")
            segments.insert(target, segments.pop(segment))

        return self._edit_plan(study_id, change)

    def set_ndt_plan_segment(self, study_id: str, pass_index: int, segment: int,
                             start: Any, end: Any) -> BuildResult:
        """Nové konce úseku (mm) – zkrácení, prodloužení či posun čísly."""
        try:
            points = [[float(v) for v in start], [float(v) for v in end]]
        except (TypeError, ValueError):
            raise DocumentError("Začátek a konec úseku musí být tři čísla [x, y, z].") from None
        if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
            raise DocumentError("Začátek a konec úseku musí být tři čísla [x, y, z].")

        def change(passes: list[dict[str, Any]]) -> None:
            item = self._segments_of(passes, pass_index, segment)[segment]
            item["start"], item["end"] = points

        return self._edit_plan(study_id, change)

    def add_ndt_plan_segment(self, study_id: str, length_mm: float = 50.0) -> BuildResult:
        """Přidá úsek z přiložené sondy: od výstupního bodu ``length_mm`` ve směru paprsku.
        Patří do průchodu se stejnou plochou, směrem, úhlem a odrazy, jinak vznikne nový."""
        if not (isinstance(length_mm, int | float) and 0 <= length_mm <= 10_000):
            raise DocumentError("Délka úseku musí být 0–10 000 mm.")
        request = self.ndt_plan_passes(study_id)[0]
        placed = self.ndt_placement
        start = [float(v) for v in placed.origin]
        end = [s + d * float(length_mm) for s, d in zip(start, placed.x_dir, strict=True)]
        segment = {"start": start, "end": end}
        face = find_face(self.result.part, request["face"])[0]
        plan = self.ndt_plan(study_id)
        if plan is None:
            data = Plan((), edited=True, **self._plan_prints(study_id)).to_dict()
        else:
            data = plan.to_dict()
        data["edited"] = True
        for plan_pass in data["passes"]:
            try:
                same = find_face(self.result.part, plan_pass["face"])[0].is_same(face)
            except (SelectionError, KeyError, TypeError):
                same = False
            if (same and abs(plan_pass["angle_deg"] - request["angle_deg"] % 360) < 1e-6
                    and abs(plan_pass["beta"] - request["beta"]) < 1e-9
                    and plan_pass["bounces"] == request["bounces"]):
                plan_pass["segments"].append(segment)
                break
        else:
            data["passes"].append({"face": dict(request["face"]),
                                   "angle_deg": request["angle_deg"] % 360,
                                   "beta": request["beta"], "bounces": request["bounces"],
                                   "pattern": "manual", "segments": [segment]})
        try:
            record = Plan.from_dict(data).to_dict()
        except PlanError as exc:
            raise DocumentError(str(exc)) from None
        return self._edit_study(study_id, lambda study: study.update(plan=record))

    def remove_ndt_useless_segments(self, study_id: str) -> BuildResult:
        """Smaže úseky, ze kterých paprsek žádný vzorek cíle nezasáhne jako první (podle
        spočítaného pokrytí plánu) – jeden krok Zpět. Pokrytí se tím nezmenší; ověří ho
        nový výpočet."""
        result = self.ndt_plan_result
        if result is None or self.ndt_plan_study() != study_id or result.coverage is None:
            raise DocumentError("Nejdřív plán ověř a spočítej jeho pokrytí.")
        useless = set(result.useless_segments())
        if not useless:
            raise DocumentError("Plán nemá úseky bez přínosu.")

        def change(passes: list[dict[str, Any]]) -> None:
            for p_index, plan_pass in enumerate(passes):
                plan_pass["segments"] = [s for s_index, s in enumerate(plan_pass["segments"])
                                         if (p_index, s_index) not in useless]

        return self._edit_plan(study_id, change)

    def remove_ndt_plan(self, study_id: str) -> BuildResult:
        return self._edit_study(study_id, lambda study: study.pop("plan", None))

    def show_ndt_plan_position(self, index: int) -> Placement:
        """Přehrávání: přiloží sondu do polohy plánu ``index`` (jen pohled)."""
        result = self.ndt_plan_result
        if result is None:
            raise DocumentError("Plán dráhy zatím není ověřený.")
        positions = result.check.positions
        if not 0 <= index < len(positions):
            raise DocumentError("Taková poloha v plánu není.")
        study_id = self.ndt_plan_study()
        position = positions[index]
        plan_pass = result.plan.passes[position.pass_index]
        probe = self.ndt_probe(study_id)
        if probe.kind == "straight":
            shown = dataclasses.replace(probe, bounces=plan_pass.bounces)
        else:
            shown = dataclasses.replace(probe, beam_angle=plan_pass.beta,
                                        bounces=plan_pass.bounces)
        previous = (self.ndt_placement_request, self._probe_override)
        self._probe_override = None if shown == probe else (study_id, shown)
        self.ndt_placement_request = (study_id, {"face": {**plan_pass.face,
                                                          "at": list(position.point)}},
                                      plan_pass.angle_deg)
        self._line_scan = None
        self.ndt_scan_index = 0
        placement = self.ndt_placement
        if placement is None:
            error = self.ndt_placement_error
            self.ndt_placement_request, self._probe_override = previous
            raise DocumentError(error)
        return placement

    def ndt_plan_drawing(self, study_id: str | None) -> tuple[Any, Any]:
        """Kresba plánu dráhy studie pro okno: (klíč, (čáry po barvách, začátek, zóny)), nebo
        (None, None). Ověřený plán ukáže celou jízdu (přesuny, přestavení obloukem nad dílem
        ve výšce nájezdu), neověřený jen úseky. Klíč se mění jen se změnou kresby."""
        if self.model_problem:
            return None, None
        if study_id is None or self.document is None or self.result is None \
                or self.result.part is None:
            return None, None
        try:
            record = self.ndt_study(study_id)
        except DocumentError:
            return None, None
        plan_data, zones_data = record.get("plan"), record.get("zones")
        if plan_data is None and not zones_data:
            return None, None
        result = self.ndt_plan_result if self.ndt_plan_study() == study_id else None
        key = (id(self.result), json.dumps(plan_data, sort_keys=True),
               json.dumps(zones_data, sort_keys=True), id(result))
        if self._plan_drawing_cache is not None and self._plan_drawing_cache[0] == key:
            return self._plan_drawing_cache
        lines: dict[tuple, list] = {color: [] for color in STEP_COLORS.values()}
        start = None
        try:
            if result is not None:
                height = max(result.plan.approach_mm, 10.0)
                for step in result.check.steps:
                    if step.kind == "air":
                        up = tuple(p + n * height for p, n in zip(step.start, step.normals[0],
                                                                 strict=True))
                        over = tuple(p + n * height for p, n in zip(step.end, step.normals[1],
                                                                   strict=True))
                        lines[STEP_COLORS["air"]] += [(step.start, up), (up, over),
                                                      (over, step.end)]
                    else:
                        lines[STEP_COLORS[step.kind]].append((step.start, step.end))
                start = result.check.steps[0].start if result.check.steps else None
            elif plan_data is not None:
                for plan_pass in Plan.from_dict(plan_data).passes:
                    for segment in plan_pass.segments:
                        lines[STEP_COLORS["scan"]].append((segment.start, segment.end))
                        start = start or segment.start
            zones = [zone.solid() for zone in zones_from(zones_data)]
        except PlanError:
            return None, None
        self._plan_drawing_cache = (key, ({c: v for c, v in lines.items() if v}, start, zones))
        return self._plan_drawing_cache

    def ndt_plan_view_map(self, index: int | None) -> CoverageMap | VolumeCoverageMap | None:
        """Mapa pokrytí plánu po polohu ``index`` (přehrávání): co ještě paprsek nezasáhl, je
        zatím nepokryté. None = celý plán."""
        result = self.ndt_plan_result
        if result is None or result.coverage is None:
            return None
        full = result.coverage.coverage
        if index is None or index >= len(result.check.positions) - 1:
            return full
        key = (id(result), index)
        if self._plan_view_cache is None or self._plan_view_cache[0] != key:
            self._plan_view_cache = (key, dataclasses.replace(
                full, states=result.coverage.until(index)))
        return self._plan_view_cache[1]

    def ndt_zone_from_selection(self, shapes: list[Any]) -> dict[str, Any]:
        """Zakázaná zóna kolem ploch či hran vybraných ve 3D (obalový kvádr + 1 mm)."""
        self._require_complete_part("práce s NDT geometrií")
        faces, edges = split_shapes(self._model_shapes(shapes))
        items = [*faces, *edges]
        if not items:
            raise DocumentError("Nejdřív ve 3D vyber plochu nebo hranu, kolem které má zóna "
                                "být.")
        boxes = [item.bounding_box() for item in items]
        low = [round(min(getattr(b.min, a) for b in boxes) - 1.0, 2) for a in "XYZ"]
        high = [round(max(getattr(b.max, a) for b in boxes) + 1.0, 2) for a in "XYZ"]
        center = "; ".join(f"{(lo + hi) / 2:g}".replace(".", ",") for lo, hi in
                           zip(low, high, strict=True))
        return {"name": f"zóna u ({center})", "min": low, "max": high}

    def export_ndt_plan(self, path: str | Path) -> Path:
        self._require_complete_part("výstup NDT")
        result = self.ndt_plan_result
        if result is None:
            raise DocumentError("Plán dráhy zatím není ověřený – není co uložit.")
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
        self._require_complete_part("výběr kontrolované oblasti")
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
        return self._require_complete_part("přidání prvku z výběru")

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
            if not new and faces and kind in ("sketch", "hole", "shell"):
                from skodacad.picking import map_faces

                faces = map_faces(faces, part)
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
        return export(self._require_complete_part("export"), path)

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
    target: TargetSection | None = None  # průřez svarem: poloha = vzdálenost od začátku cíle


@dataclass(frozen=True)
class TargetSection:
    """Řez kolmo na osu cílového objemu NDT (tlačítko Průřez svarem)."""

    origin: tuple[float, float, float]
    axis: tuple[float, float, float]
    length: float
    normal: tuple[float, float, float]  # ± osa, k pozorovateli v izometrii


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


@dataclass(frozen=True)
class DirectEditPreview:
    document: Document
    feature: dict[str, Any]
    feature_id: str | None
    result: BuildResult


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


def _target_text(record: dict[str, Any] | None, state: StudyResult | None) -> str:
    """Kontrolovaná oblast studie pro zprávu auditu (počet ploch, nebo druh a objem cíle)."""
    if record is None or state is None:
        return ""
    if state.target_kind == "faces":
        n = state.faces
        return f"{n} {'plocha' if n == 1 else 'plochy' if 2 <= n <= 4 else 'ploch'}"
    target = record.get("target") or {}
    kind = (WELD_TYPES.get(target.get("weld_type"), "svar") if target.get("kind") == "weld"
            else "obecný hranol")
    return f"{kind}, objem {state.volume_mm3:.6g} mm³".replace(".", ",")


def _studies(document: Document, create: bool = False) -> list[dict[str, Any]]:
    """Seznam NDT studií modelu (``create`` založí sekci „ndt“, když chybí)."""
    if document.ndt is None:
        if not create:
            return []
        document.ndt = {"studies": []}
    return document.ndt.setdefault("studies", [])
