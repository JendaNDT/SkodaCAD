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
from skodacad.features import FEATURE_TYPES, BuildContext, FeatureError, describe
from skodacad.selectors import SelectionError

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

    @property
    def ok(self) -> bool:
        return all(status.status == "ok" for status in self.statuses)

    @property
    def first_error(self) -> FeatureStatus | None:
        return next((s for s in self.statuses if s.status == "error"), None)


def rebuild(document: Document, overrides: dict[str, Any] | None = None) -> BuildResult:
    """Postaví díl z dokumentu. ``overrides`` dočasně mění hodnoty parametrů."""
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
            result.statuses.append(FeatureStatus(feature["id"], feature["type"], label, "ok"))
        else:
            failed = True
            result.statuses.append(
                FeatureStatus(feature["id"], feature["type"], label, "error", message)
            )

    result.part = ctx.part
    result.sketches = ctx.sketches
    return result


def _run_feature(ctx: BuildContext, feature: dict[str, Any]) -> str | None:
    """Spočítá jeden prvek; vrátí None, nebo českou chybovou zprávu."""
    feature_type = FEATURE_TYPES.get(feature["type"])
    if feature_type is None:
        known = ", ".join(FEATURE_TYPES)
        return f"Neznámý typ prvku „{feature['type']}“, umím: {known}."

    part_before = ctx.part
    ctx.recording = []  # co prvek s dílem udělá – pro pole a zrcadlení
    try:
        feature_type.build(ctx, feature)
        if ctx.part is not None and ctx.part is not part_before and not ctx.part.is_valid:
            raise FeatureError("Výsledek není platné těleso (jádro vrátilo poškozenou geometrii).")
    except (FeatureError, ExpressionError, SelectionError) as exc:
        ctx.part = part_before
        return str(exc)
    except Exception as exc:  # noqa: BLE001 – neočekávaná chyba jádra nesmí shodit program
        ctx.part = part_before
        return f"Neočekávaná chyba jádra ({type(exc).__name__}: {exc})."
    finally:
        recorded, ctx.recording = ctx.recording, None
    ctx.operations[feature["id"]] = recorded
    return None
