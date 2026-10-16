"""NDT studie: záznam v modelu (sekce ``ndt``), otisk dílu a stav studie po přepočtu.

Studie nemění těleso. Její výsledek se neukládá – stav se spočítá při každém přepočtu
z aktuálního dílu (jako uložená měření). Kontrolovaná oblast drží plochy **významem**
(bod, směr, druh – ``measure.face_reference``), nikdy indexem.

Otisk dílu je kontrolní součet receptu (parametry, prvky bez názvů, materiál). Volí se
schválně recept, ne tvar: posunutá díra nemění objem ani rozměry, otisk ano. Raději
zbytečné „zastaralá“ než tiché „platná“.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from build123d import Face, Part, Vector

from skodacad.materials import material_key
from skodacad.measure import MeasureError, format_value, reference_for
from skodacad.selectors import SelectionError, find_face

METHODS = {  # zkratka → český název metody
    "UT": "ultrazvuková",
    "PT": "kapilární",
    "MT": "magnetická prášková",
    "RT": "radiografická",
}
TARGET_KINDS = ("faces",)  # objem a svar přidá etapa 07
STUDY_KEYS = ("id", "name", "method", "target", "device", "note", "created", "part",
              "verified")

STATE_LABELS = {"ok": "platná", "stale": "zastaralá", "incomplete": "neúplná",
                "broken": "neplatná vazba"}
STATE_MARKS = {"ok": "✓", "stale": "⚠", "incomplete": "⚠", "broken": "✕"}
MOVED = 1e-3  # o kolik mm se smí uložený bod lišit od nalezené plochy (zaokrouhlení v JSON)


class StudyError(ValueError):
    """Chybný záznam NDT studie (zpráva je česky pro uživatele)."""


# --- kontrola struktury ------------------------------------------------------------------


def check(data: Any) -> None:
    """Zkontroluje sekci ``ndt`` modelu; chyba = ``StudyError`` s českou zprávou."""
    if not isinstance(data, dict):
        raise StudyError('„ndt“ musí být objekt {"studies": [...]}.')
    unknown = sorted(set(data) - {"studies"})
    if unknown:
        raise StudyError(f"Neznámá položka „{unknown[0]}“ v „ndt“ (umím jen „studies“).")
    studies = data.get("studies", [])
    if not isinstance(studies, list):
        raise StudyError("„ndt.studies“ musí být seznam NDT studií.")
    seen: set[str] = set()
    for index, study in enumerate(studies, start=1):
        check_study(study, index)
        if study["id"] in seen:
            raise StudyError(f"Id NDT studie „{study['id']}“ je v modelu dvakrát.")
        seen.add(study["id"])


def check_study(study: Any, index: int = 1) -> None:
    if not isinstance(study, dict):
        raise StudyError(f"NDT studie č. {index} musí být objekt.")
    sid = study.get("id")
    if not isinstance(sid, str) or not sid:
        raise StudyError(f"NDT studie č. {index} nemá textové „id“.")
    where = f"NDT studie „{sid}“"
    unknown = sorted(set(study) - set(STUDY_KEYS))
    if unknown:
        raise StudyError(f"{where}: neznámá položka „{unknown[0]}“ "
                         f"(umím: {', '.join(STUDY_KEYS)}).")
    if study.get("method") not in METHODS:
        raise StudyError(f"{where}: metoda musí být jedna z {', '.join(METHODS)} "
                         f"(je {study.get('method')!r}).")
    for key in ("name", "note", "created", "part"):
        if key in study and not isinstance(study[key], str):
            raise StudyError(f"{where}: „{key}“ musí být text.")
    if "target" in study:
        _check_target(study["target"], where)
    if "device" in study:
        from skodacad.ndt.devices import DeviceError, Probe

        try:
            Probe.from_dict(study["device"])
        except DeviceError as exc:
            raise StudyError(f"{where}: {exc}") from None
    verified = study.get("verified")
    if verified is not None:
        if (not isinstance(verified, dict) or set(verified) - {"by", "date", "part"}
                or not isinstance(verified.get("by"), str) or not verified["by"].strip()
                or not all(isinstance(verified.get(key, ""), str) for key in ("date", "part"))):
            raise StudyError(f'{where}: „verified“ musí být {{"by": "kdo", "date": "RRRR-MM-DD", '
                             '"part": "otisk dílu"}.')


def _check_target(target: Any, where: str) -> None:
    if not isinstance(target, dict) or target.get("kind") not in TARGET_KINDS:
        raise StudyError(f'{where}: kontrolovaná oblast „target“ musí být {{"kind": "faces", '
                         '"faces": [...]}.')
    faces = target.get("faces", [])
    if not isinstance(faces, list):
        raise StudyError(f"{where}: „target.faces“ musí být seznam ploch.")
    for number, reference in enumerate(faces, start=1):
        spec = reference.get("face") if isinstance(reference, dict) else None
        at = spec.get("at") if isinstance(spec, dict) else None
        if (not isinstance(at, list) or len(at) != 3
                or not all(isinstance(v, int | float) and not isinstance(v, bool) for v in at)):
            raise StudyError(f'{where}: plocha č. {number} musí být {{"face": {{"at": [x, y, z], '
                             '"normal": [nx, ny, nz]}}.')


# --- otisk dílu ----------------------------------------------------------------------------


def part_fingerprint(document: Any) -> str:
    """Otisk dílu (16 znaků) z parametrů, prvků a materiálu – bez názvů prvků."""
    recipe = {
        "parameters": _canonical(document.parameters),
        "features": [_canonical({k: v for k, v in feature.items() if k != "name"})
                     for feature in document.features],
        "material": material_key(document.material),
    }
    text = json.dumps(recipe, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _canonical(value: Any) -> Any:
    """20.0 a 20 jsou totéž číslo – otisk se nesmí změnit jen zápisem."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


# --- stav studie po přepočtu ---------------------------------------------------------------


@dataclass(frozen=True)
class StudyResult:
    """Stav NDT studie na posledním dílu (jen čísla a texty – přenese se z pomocného procesu)."""

    id: str
    name: str
    method: str
    state: str  # ok / stale / incomplete / broken
    messages: tuple[str, ...] = ()
    faces: int = 0  # kolik ploch kontrolované oblasti se na dílu našlo
    verified: str = "neověřeno"
    part: str = ""  # otisk aktuálního dílu

    @property
    def label(self) -> str:
        return STATE_LABELS[self.state]

    @property
    def mark(self) -> str:
        return STATE_MARKS[self.state]

    @property
    def text(self) -> str:
        line = f"{self.mark} {self.name} ({self.method}) – {self.label}"
        details = [*self.messages, self.verified]
        return line + "".join(f"\n    {detail}" for detail in details)


def study_name(study: dict[str, Any]) -> str:
    name = study.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else str(study.get("id", "?"))


def evaluate(part: Part | None, study: dict[str, Any], fingerprint: str) -> StudyResult:
    """Stav studie: platná, zastaralá (díl se změnil), neúplná, nebo neplatná vazba."""
    sid, name, method = str(study.get("id", "?")), study_name(study), str(study.get("method"))
    broken: list[str] = []
    warnings: list[str] = []
    references = (study.get("target") or {}).get("faces", [])
    found = 0
    if part is None:
        broken.append("Model nemá těleso (některý prvek se nepostavil) – studii nejde "
                      "vyhodnotit.")
    else:
        for number, reference in enumerate(references, start=1):
            single = len(references) == 1
            which = "Kontrolovaná plocha" if single else f"Plocha č. {number}"
            try:
                _, on_face = find_face(part, reference["face"])
            except SelectionError as exc:
                where = "" if single else f", plocha č. {number}"
                broken.append(f"Kontrolovaná oblast{where}: {exc}")
                continue
            found += 1
            moved = (on_face - Vector(*reference["face"]["at"])).length
            if moved > MOVED:
                warnings.append(f"{which} se posunula o {format_value(moved, 'mm')} – "
                                "zkontroluj, že je to pořád ta správná.")
    changed = study.get("part") != fingerprint
    if broken:
        state = "broken"
    elif changed:
        state = "stale"
        warnings.insert(0, "Díl se od nastavení studie změnil – zkontroluj ji a potvrď pro "
                           "aktuální díl.")
    elif not references:
        state = "incomplete"
    else:
        state = "ok"
    if not references:
        warnings.append("Chybí kontrolovaná oblast – vyber plochy dílu.")
    return StudyResult(sid, name, method, state, tuple(broken + warnings), found,
                       _verification(study, fingerprint), fingerprint)


def _verification(study: dict[str, Any], fingerprint: str) -> str:
    verified = study.get("verified")
    if not verified:
        return "Neověřeno."
    if verified.get("part") != fingerprint:
        return f"Ověření ({verified['by']}) neplatí – díl se od ověření změnil."
    when = _date_cz(verified.get("date", ""))
    return f"Ověřil(a) {verified['by']}" + (f" {when}." if when else ".")


def _date_cz(text: str) -> str:
    try:
        day = datetime.date.fromisoformat(text)
    except ValueError:
        return text
    return f"{day.day}. {day.month}. {day.year}"


def evaluate_all(part: Part | None, document: Any) -> list[StudyResult]:
    """Stavy všech studií modelu; neočekávaná chyba jádra studii jen označí, nespadne."""
    studies = (document.ndt or {}).get("studies", [])
    if not studies:
        return []
    fingerprint = part_fingerprint(document)
    results = []
    for study in studies:
        try:
            results.append(evaluate(part, study, fingerprint))
        except Exception as exc:  # noqa: BLE001 – studie nesmí shodit přepočet
            results.append(StudyResult(
                str(study.get("id", "?")), study_name(study), str(study.get("method")),
                "broken", (f"Neočekávaná chyba ({type(exc).__name__}: {exc}).",),
                part=fingerprint))
    return results


# --- nová studie a úpravy ------------------------------------------------------------------


def target_for(part: Part, faces: list[Face], point: Any = None) -> dict[str, Any]:
    """Kontrolovaná oblast z vybraných ploch (odkazy významem, ověřené na dílu)."""
    unique: list[Face] = []
    for face in faces:
        if not any(face.is_same(other) for other in unique):
            unique.append(face)
    try:
        references = [reference_for(part, face, point) for face in unique]
    except MeasureError as exc:
        raise StudyError(str(exc).replace("uložené měření", "NDT studii")) from None
    return {"kind": "faces", "faces": references}


def refresh_target(part: Part, target: dict[str, Any]) -> dict[str, Any]:
    """Kontrolovaná oblast znovu ukotvená na aktuálním dílu (při potvrzení studie): body
    a směry ploch tam, kde plochy teď jsou. Plocha, která zmizela → ``SelectionError``."""
    references = []
    for reference in target.get("faces", []):
        face, on_face = find_face(part, reference["face"])
        try:
            references.append(reference_for(part, face, on_face))
        except MeasureError as exc:
            raise StudyError(str(exc).replace("uložené měření", "NDT studii")) from None
    return {**target, "faces": references}


def new_id(existing: list[dict[str, Any]]) -> str:
    used = {study.get("id") for study in existing}
    number = 1
    while f"s{number}" in used:
        number += 1
    return f"s{number}"


def new_study(method: str, existing: list[dict[str, Any]], fingerprint: str,
              target: dict[str, Any] | None = None, name: str | None = None,
              today: datetime.date | None = None) -> dict[str, Any]:
    """Záznam nové studie; ``target`` z ``target_for`` (bez něj je studie neúplná)."""
    if method not in METHODS:
        raise StudyError(f"Metoda musí být jedna z {', '.join(METHODS)} (je {method!r}).")
    sid = new_id(existing)
    study: dict[str, Any] = {"id": sid,
                             "name": (name or "").strip() or f"{method} studie {sid[1:]}",
                             "method": method}
    if target and target.get("faces"):
        study["target"] = copy.deepcopy(target)
    study.update(note="", created=(today or datetime.date.today()).isoformat(),
                 part=fingerprint)
    return study


def duplicate(study: dict[str, Any], existing: list[dict[str, Any]]) -> dict[str, Any]:
    """Kopie studie s novým id (ověření se nepřenáší – platí jen pro originál)."""
    copied = copy.deepcopy(study)
    copied.pop("verified", None)
    copied["id"] = new_id(existing)
    copied["name"] = f"{study_name(study)} (kopie)"
    return copied


def study_probe(study: dict[str, Any]) -> Any:
    """Sonda studie (``device``), bez ní výchozí úhlová sonda 40 × 20 × 25 mm."""
    from skodacad.ndt.devices import Probe

    device = study.get("device")
    return Probe.from_dict(device) if device is not None else Probe.angle()
