"""Vzorkovaný CAD přehled stěny loftu v aktuálním hotovém dílu.

Měří první souvislý úsek materiálu kolmo od původního vnějšího povrchu.
Není to globální minimum ani UT vyhodnocení; nepoužívá filtr koncového echa.
Výstup obsahuje pouze přenosná data, žádné tvary OCCT.
"""

from __future__ import annotations

from dataclasses import dataclass

from build123d import GeomType, loft

from skodacad.document import Document, DocumentError
from skodacad.features import BuildContext, _coplanar, _loft_sections
from skodacad.ndt.geometry import PartGeometry
from skodacad.rebuild import BuildResult, model_signature, part_problem

Point = tuple[float, float, float]
GRID = (0.15, 0.325, 0.5, 0.675, 0.85)
MAX_SAMPLES = 2000
MODE_LABELS = {"normal": "Kolmo ke stěně", "sections": "V rovinách skic",
               "legacy": "Automaticky (starší model)"}
STATUS_LABELS = {"below": "Pod zadáním", "nominal": "U zadání", "longer": "Delší průchod",
                 "unknown": "Nejisté"}
LIMITATION = ("Vzorky původního pláště v aktuálním dílu; nejde o globální minimum. "
              "Delší průchod může vzniknout v rohu nebo přidaným materiálem. "
              "Porovnání používá jen číselnou toleranci, nikoli výrobní přejímku ani UT.")


@dataclass(frozen=True)
class WallSample:
    point: Point
    direction: Point
    length: float | None
    end: Point | None
    status: str
    reason: str = ""


@dataclass(frozen=True)
class WallReport:
    signature: str
    feature_id: str
    mode: str
    requested: float
    samples: tuple[WallSample, ...]
    skipped: int = 0
    truncated: bool = False

    @property
    def lengths(self) -> tuple[float, ...]:
        return tuple(s.length for s in self.samples if s.length is not None)

    @property
    def counts(self) -> dict[str, int]:
        return {key: sum(s.status == key for s in self.samples) for key in STATUS_LABELS}


def wall_feature(document: Document, result: BuildResult | None, feature_id: str
                 ) -> tuple[dict, float]:
    """Ověří hotový aktuální díl a kladnou stěnu bez výpočtu nové geometrie."""
    if problem := part_problem(result):
        raise DocumentError(problem)
    if result.model_signature != model_signature(document):
        raise DocumentError("Měření nemá aktuální těleso – přepočítej model.")
    feature = next((f for f in document.features if f["id"] == feature_id), None)
    if feature is None or feature["type"] != "loft":
        raise DocumentError("Vyber dutý přechod ve stromu prvků.")
    context = BuildContext(result.parameters)
    wall = context.num(feature.get("wall") or 0)
    if wall <= 0:
        raise DocumentError("Přechod nemá zadanou kladnou tloušťku stěny.")
    return feature, wall


def _sample(geometry: PartGeometry, point: Point, direction: Point, wall: float) -> WallSample:
    """Nejistota patří k bodu; chybějící průchod nikdy není nulová tloušťka."""
    def unknown(reason: str) -> WallSample:
        return WallSample(point, direction, None, None, "unknown", reason)

    step = min(1e-3, wall / 100)
    inside = tuple(p + d * step for p, d in zip(point, direction, strict=True))
    outside = tuple(p - d * step for p, d in zip(point, direction, strict=True))
    if (geometry.classify(point) != "surface" or geometry.classify(inside) != "inside"
            or geometry.classify(outside) != "outside"):
        return unknown("Původní povrch byl odstraněn, zakryt nebo jej nelze ověřit.")
    ray = geometry.cast(point, direction)
    segment = next((s for s in ray.segments if s.start < 1e-5), None)
    if segment is None or segment.entry is None or segment.exit is None:
        return unknown("Chybí ověřený vstup nebo výstup souvislého úseku materiálu.")
    if not segment.certain:
        return unknown("; ".join(segment.reasons))
    tolerance = max(2e-5, wall * 1e-6)
    length = segment.length
    status = ("below" if length < wall - tolerance else
              "longer" if length > wall + tolerance else "nominal")
    return WallSample(point, direction, length, segment.exit.point, status)


def inspect_loft(document: Document, result: BuildResult, feature_id: str) -> WallReport:
    """5 × 5 bodů na každé boční ploše původního loftu, nejvýš MAX_SAMPLES.

    Rozložení je v parametrech plochy, ne rovnoměrně v mm. Oříznuté části
    a okolí hran se vynechávají a jejich počet je ve zprávě. Celá plocha bez
    použitelného bodu dostane výslovný nejistý záznam.
    """
    feature, wall = wall_feature(document, result, feature_id)
    try:
        context = BuildContext(result.parameters, sketches=result.sketches)
        sections = _loft_sections(context, feature)
        original = loft(sections, ruled=bool(feature.get("ruled", False)))
        sides = [f for f in original.faces() if not (f.geom_type == GeomType.PLANE and any(
            _coplanar(f, end) for end in (sections[0], sections[-1])))]
        geometry = PartGeometry(result.part)
        samples: list[WallSample] = []
        skipped = 0
        truncated = False
        for face in sides:
            before = len(samples)
            for u in GRID:
                for v in GRID:
                    if len(samples) >= MAX_SAMPLES:
                        truncated = True
                        break
                    point = face.position_at(u, v)
                    if (not face.is_inside(point)
                            or min(e.distance_to(point) for e in face.edges()) < 1e-4):
                        skipped += 1
                        continue
                    direction = -face.normal_at(point)
                    try:
                        sample = _sample(geometry, tuple(point), tuple(direction), wall)
                    except Exception:  # noqa: BLE001 -- nejistota jednoho bodu
                        sample = WallSample(tuple(point), tuple(direction), None, None, "unknown",
                                            "Jádro nedokázalo tento paprsek spolehlivě vyhodnotit.")
                    samples.append(sample)
                if truncated:
                    break
            if truncated:
                break
            if len(samples) == before:
                samples.append(WallSample(tuple(face.center()), (0., 0., 0.), None, None,
                                          "unknown", "Plocha nemá použitelný kontrolní bod."))
        if not samples:
            raise ValueError("přechod nemá boční plochu")
        return WallReport(result.model_signature, feature_id, feature.get("wall_mode", "legacy"),
                          wall, tuple(samples), skipped, truncated)
    except DocumentError:
        raise
    except Exception as exc:  # noqa: BLE001 -- chyba jádra nesmí shodit okno
        raise DocumentError("Stěnu přechodu se nepodařilo změřit. Zkus model přepočítat "
                            "a měření zopakovat.") from exc
