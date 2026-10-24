"""Přepočet modelu: projde prvky v pořadí a postaví z nich těleso.

Když prvek selže, díl zůstane ve stavu před ním, prvek dostane českou
chybovou zprávu a všechny další prvky se přeskočí – stejně jako strom
historie v běžném CADu (✓ / ✕ / přeskočeno).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from build123d import Part, Plane, Sketch

from skodacad.document import Document, DocumentError
from skodacad.expressions import ExpressionError, resolve_parameters
from skodacad.features import FEATURE_TYPES, VOLUME_FEATURES, BuildContext, FeatureError, describe
from skodacad.geometry_validation import GeometryValidationError, body_count_message, inspect_volume
from skodacad.measure import SavedResult, evaluate
from skodacad.ndt.study import StudyResult
from skodacad.ndt.study import evaluate_all as evaluate_studies
from skodacad.selectors import SelectionError
from skodacad.thickness_map import MapError, MapSettings, ThicknessMap
from skodacad.thickness_map import compute as compute_map

Status = Literal["ok", "error", "skipped"]


@dataclass
class FeatureStatus:
    id: str
    type: str
    label: str
    status: Status
    message: str = ""


@dataclass
class BuildResult:
    part: Part | None
    parameters: dict[str, float]
    statuses: list[FeatureStatus] = field(default_factory=list)
    # Díl těsně před každým spočítaným prvkem (id → Part nebo None) – na něm prvek vybíral
    # hrany a plochy. Okno podle toho zvýrazní, co prvek zasahuje.
    parts_before: dict[str, Part | None] = field(default_factory=dict)
    sketches: dict[str, tuple[Plane, Sketch]] = field(default_factory=dict)  # id → umístění
    measurements: list[SavedResult] = field(default_factory=list)  # uložená měření na dílu
    thickness_map: ThicknessMap | None = None  # mapa tloušťky stěny (jen když se chtěla)
    map_error: str = ""  # proč mapa nejde spočítat
    ndt: list[StudyResult] = field(default_factory=list)  # stavy NDT studií na dílu

    @property
    def ok(self) -> bool:
        return all(status.status == "ok" for status in self.statuses)

    @property
    def first_error(self) -> FeatureStatus | None:
        return next((s for s in self.statuses if s.status == "error"), None)


def part_problem(result: BuildResult | None) -> str:
    """Proč výsledek nelze použít jako hotový díl (náhled smí zůstat viditelný).

    Platnost objemové geometrie zajišťují kontroly při přijetí prvku. Zde se
    nepočítá nová geometrie; poslední dobrý solid není úspěchem celé historie.
    Aktuálnost vůči otevřenému dokumentu kontroluje navíc ModelSession.
    """
    if result is None:
        return "Model zatím není spočítaný – nejdřív jej přepočítej."
    if not result.ok:
        error = result.first_error
        cause = (f"prvek [{error.id}] {error.label} má chybu – {error.message}"
                 if error is not None else "některé prvky jsou přeskočené")
        return (f"Model není dokončený: {cause}. Zobrazené těleso je poslední dobrý "
                "mezistav. Oprav prvek nebo použij Zpět a potom operaci zopakuj.")
    if result.part is None or not result.part.solids():
        return "Model zatím nemá žádné těleso – nejdřív vytvoř objemový díl."
    return ""


def require_complete_part(result: BuildResult | None) -> Part:
    """Vrátí dokončený díl, nebo český důvod odmítnutí před výpočtem/zápisem."""
    problem = part_problem(result)
    if problem:
        raise DocumentError(problem)
    return result.part


def rebuild(document: Document, overrides: dict[str, Any] | None = None,
            with_map: bool = False) -> BuildResult:
    """Postaví díl z dokumentu. ``overrides`` dočasně mění hodnoty parametrů, ``with_map``
    spočítá i mapu tloušťky stěny (nastavení z ``document.thickness_map``)."""
    if overrides:
        document = document.with_parameters(overrides)
    try:
        params = resolve_parameters(document.parameters)
    except ExpressionError as exc:
        raise DocumentError(str(exc)) from None

    ctx = BuildContext(params=params)
    result = BuildResult(part=None, parameters=params)
    failed = False

    for feature in document.features:
        label = describe(feature, params)
        if failed:
            result.statuses.append(
                FeatureStatus(feature["id"], feature["type"], label, "skipped",
                              "přeskočeno kvůli chybě v předchozím prvku")
            )
            continue

        result.parts_before[feature["id"]] = ctx.part
        message = _run_feature(ctx, feature)
        if message is None:
            information = ""
            if feature["type"] in VOLUME_FEATURES:
                previous = result.parts_before[feature["id"]]
                information = body_count_message(len(previous.solids()) if previous else 0,
                                                 len(ctx.part.solids()))
            result.statuses.append(
                FeatureStatus(feature["id"], feature["type"], label, "ok", information)
            )
        else:
            failed = True
            result.statuses.append(
                FeatureStatus(feature["id"], feature["type"], label, "error", message)
            )

    result.part = ctx.part
    result.sketches = ctx.sketches
    result.measurements = [evaluate(ctx.part, m) for m in document.measurements]
    problem = part_problem(result)
    result.ndt = evaluate_studies(ctx.part, document, model_problem=problem)
    if with_map and problem:
        result.map_error = ("Mapa tloušťky potřebuje díl. " + problem
                            if result.part is None else problem)
    elif with_map:
        try:
            result.thickness_map = compute_map(ctx.part,
                                               MapSettings.from_dict(document.thickness_map))
        except MapError as exc:
            result.map_error = str(exc)
        except Exception as exc:  # noqa: BLE001 – mapa nesmí shodit přepočet
            result.map_error = f"Neočekávaná chyba mapy ({type(exc).__name__}: {exc})."
    return result


def _run_feature(ctx: BuildContext, feature: dict[str, Any]) -> str | None:
    """Spočítá jeden prvek; vrátí None, nebo českou chybovou zprávu."""
    feature_type = FEATURE_TYPES.get(feature["type"])
    if feature_type is None:
        known = ", ".join(FEATURE_TYPES)
        return f"Neznámý typ prvku „{feature['type']}“, umím: {known}."

    try:
        candidate, working_feature = ctx._fork_for_feature(feature)
        feature_type.build(candidate, working_feature)
        if feature["type"] in VOLUME_FEATURES:
            inspect_volume(candidate.part)
        ctx._accept_feature(candidate, feature, working_feature)
    except (FeatureError, ExpressionError, SelectionError, GeometryValidationError) as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 – neočekávaná chyba jádra nesmí shodit program
        return f"Neočekávaná chyba jádra ({type(exc).__name__}: {exc})."
    return None
