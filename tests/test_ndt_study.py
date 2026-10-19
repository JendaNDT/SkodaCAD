"""NDT studie v modelu (etapa 01): formát v13, otisk dílu, stavy po přepočtu."""

import copy
import datetime
import json
import pickle

import pytest

from conftest import EXAMPLES, face_at
from skodacad import Document, rebuild
from skodacad.document import VERSION, DocumentError
from skodacad.ndt.study import (
    StudyError,
    duplicate,
    evaluate,
    new_study,
    part_fingerprint,
    target_for,
)
from skodacad.worker import decode_result, encode_result

NDT = EXAMPLES / "ndt"
TODAY = datetime.date(2026, 10, 16)


def plate(**overrides):
    document = Document.load(NDT / "deska.json")
    if overrides:
        document = document.with_parameters(overrides)
    return document


def top_study(document, **extra):
    """Studie UT na horní ploše desky (jako výběr kliknutím)."""
    part = rebuild(document).part
    target = target_for(part, [face_at(part, 30, 10, 20)], (30, 10, 20))
    study = new_study("UT", [], part_fingerprint(document), target, "UT desky shora", TODAY)
    study.update(extra)
    return study


def with_studies(document, *studies):
    changed = copy.deepcopy(document)
    changed.ndt = {"studies": list(studies)}
    return changed


# --- formát --------------------------------------------------------------------------------


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.stem)
def test_old_models_load_without_ndt_and_save_as_current_version(path, tmp_path):
    document = Document.load(path)
    assert document.ndt is None
    data = document.to_dict()
    assert "ndt" not in data and data["version"] == VERSION == 21


def test_study_survives_save_and_load(tmp_path):
    document = with_studies(plate(), top_study(plate()))
    path = tmp_path / "deska.json"
    document.save(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["ndt"]["studies"][0]["method"] == "UT"
    assert saved["ndt"]["studies"][0]["target"]["faces"] == [
        {"face": {"at": [30, 10, 20], "normal": [0, 0, 1], "type": "plane"}}]
    assert Document.load(path) == document


@pytest.mark.parametrize("ndt, message", [
    ([], "musí být objekt"),
    ({"studie": []}, "Neznámá položka „studie“"),
    ({"studies": {}}, "musí být seznam"),
    ({"studies": [{"method": "UT"}]}, "nemá textové „id“"),
    ({"studies": [{"id": "s1", "method": "ET"}]}, "metoda musí být jedna z UT, PT, MT, RT"),
    ({"studies": [{"id": "s1", "method": "UT"}, {"id": "s1", "method": "PT"}]}, "dvakrát"),
    ({"studies": [{"id": "s1", "method": "UT", "probe": {}}]}, "neznámá položka „probe“"),
    ({"studies": [{"id": "s1", "method": "UT", "target": {"kind": "volume"}}]},
     'Souřadný systém cíle musí být objekt'),
    ({"studies": [{"id": "s1", "method": "UT",
                   "target": {"kind": "faces", "faces": [{"face": {"at": [1, 2]}}]}}]},
     "plocha č. 1 musí být"),
    ({"studies": [{"id": "s1", "method": "UT", "verified": {"date": "2026-10-16"}}]},
     "„verified“ musí být"),
    ({"studies": [{"id": "s1", "method": "UT", "name": 5}]}, "„name“ musí být text"),
    ({"studies": [{"id": "s1", "method": "UT", "device": {"kind": "angle", "front": 99}}]},
     "studie „s1“: Výstupní bod"),
])
def test_bad_ndt_section_is_czech_error(ndt, message):
    data = plate().to_dict() | {"ndt": ndt}
    with pytest.raises(DocumentError, match=message):
        Document.from_dict(data)


# --- otisk dílu ----------------------------------------------------------------------------


def test_fingerprint_ignores_names_and_number_notation():
    document = plate()
    renamed = copy.deepcopy(document)
    renamed.features[1]["name"] = "Jiný název"
    renamed.name = "Jiný díl"
    renamed.description = "jiný popis"
    floats = document.with_parameters({"t": 20.0})
    fingerprint = part_fingerprint(document)
    assert len(fingerprint) == 16
    assert part_fingerprint(renamed) == part_fingerprint(floats) == fingerprint


def test_fingerprint_changes_with_parameter_feature_and_material():
    document = plate()
    edited = copy.deepcopy(document)
    edited.features[1]["direction"] = "reverse"
    steel_to_aluminium = copy.deepcopy(document)
    steel_to_aluminium.material = "Hliník"
    prints = {part_fingerprint(d) for d in (document, plate(t=30), edited, steel_to_aluminium)}
    assert len(prints) == 4


def test_moved_hole_keeps_volume_but_changes_fingerprint():
    document = Document.load(NDT / "otvor.json")
    moved = copy.deepcopy(document)
    moved.features[0]["elements"][1]["center"] = [30, 0]
    assert rebuild(moved).part.volume == pytest.approx(rebuild(document).part.volume)
    assert part_fingerprint(moved) != part_fingerprint(document)


# --- stavy ---------------------------------------------------------------------------------


def test_study_on_unchanged_part_is_valid():
    document = with_studies(plate(), top_study(plate()))
    [result] = rebuild(document).ndt
    assert (result.id, result.name, result.method) == ("s1", "UT desky shora", "UT")
    assert result.state == "ok" and result.mark == "✓" and result.label == "platná"
    assert result.faces == 1 and result.messages == ()
    assert result.verified == "Neověřeno."


def test_parameter_change_makes_study_stale_and_reports_moved_face():
    study = top_study(plate())
    [result] = rebuild(with_studies(plate(), study), {"t": 30}).ndt
    assert result.state == "stale" and result.mark == "⚠"
    assert "Díl se od nastavení studie změnil" in result.messages[0]
    assert "Kontrolovaná plocha se posunula o 10.00 mm" in result.messages[1]
    assert result.faces == 1
    [back] = rebuild(with_studies(plate(), study), {"t": 20}).ndt
    assert back.state == "ok"  # stejný recept = zase platná (jako Zpět)


def test_study_without_target_is_incomplete():
    document = plate()
    study = new_study("PT", [], part_fingerprint(document), today=TODAY)
    assert study == {"id": "s1", "name": "PT studie 1", "method": "PT", "note": "",
                     "created": "2026-10-16", "part": part_fingerprint(document)}
    [result] = rebuild(with_studies(document, study)).ndt
    assert result.state == "incomplete"
    assert result.messages == ("Chybí kontrolovaná oblast – vyber plochy dílu.",)


def test_missing_face_or_part_breaks_the_link():
    holed = Document.load(NDT / "otvor.json")
    part = rebuild(holed).part
    hole_wall = face_at(part, 10, 0, 10)
    target = target_for(part, [hole_wall], (10, 0, 10))
    assert target["faces"][0]["face"]["type"] == "cylinder"
    study = new_study("UT", [], part_fingerprint(holed), target, today=TODAY)
    [result] = rebuild(with_studies(plate(), study)).ndt  # deska bez otvoru
    assert result.state == "broken" and result.mark == "✕" and result.faces == 0
    assert result.messages[0].startswith("Kontrolovaná oblast: Plocha u bodu [10; 0; 10] už")
    assert evaluate(None, study, "x").messages[0].startswith("Model nemá těleso")


def test_verification_is_valid_only_for_the_same_part():
    document = plate()
    study = top_study(document, verified={"by": "J. N.", "date": "2026-10-16",
                                           "part": part_fingerprint(document)})
    [result] = rebuild(with_studies(document, study)).ndt
    assert result.verified == "Ověřil(a) J. N. 16. 10. 2026."
    [changed] = rebuild(with_studies(document, study), {"t": 25}).ndt
    assert changed.verified == "Ověření (J. N.) neplatí – díl se od ověření změnil."


def test_target_from_selection_skips_duplicates_and_checks_uniqueness():
    document = plate()
    part = rebuild(document).part
    top = face_at(part, 0, 0, 20)
    target = target_for(part, [top, top, face_at(part, 0, 0, 0)])
    assert [ref["face"]["normal"] for ref in target["faces"]] == [[0, 0, 1], [0, 0, -1]]
    with pytest.raises(StudyError, match="metoda|Metoda"):
        new_study("XX", [], "x")


def test_duplicate_gets_new_id_and_drops_verification():
    study = top_study(plate(), verified={"by": "J. N.", "date": "2026-10-16", "part": "x"})
    copied = duplicate(study, [study])
    assert copied["id"] == "s2" and copied["name"] == "UT desky shora (kopie)"
    assert "verified" not in copied and copied["target"] == study["target"]


def test_study_states_cross_the_process_boundary():
    result = rebuild(with_studies(plate(), top_study(plate())), {"t": 30})
    copied = decode_result(pickle.loads(pickle.dumps(encode_result(result))))
    assert copied.ndt == result.ndt and copied.ndt[0].state == "stale"


def test_text_summary_for_command_line():
    study = top_study(plate())
    [result] = rebuild(with_studies(plate(), study), {"t": 30}).ndt
    assert result.text.splitlines() == [
        "⚠ UT desky shora (UT) – zastaralá",
        "    Díl se od nastavení studie změnil – zkontroluj ji a potvrď pro aktuální díl.",
        "    Kontrolovaná plocha se posunula o 10.00 mm – zkontroluj, že je to pořád ta správná.",
        "    Neověřeno.",
    ]
