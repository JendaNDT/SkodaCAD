"""P0: ochrana rozpracovaných dat a chybových stavů bez změny chování aplikace."""

import copy
import pickle

import pytest

from conftest import EXAMPLES, box_features, make_doc
from skodacad import Document, DocumentError, rebuild
from skodacad.session import ModelSession
from skodacad.worker import decode_result, encode_result

# Rekurzivně: i cílové objemy v podsložce a zadání konstrukčních variant verze 22.
# Soubory sestav (formát 29) díly nejsou – mají vlastní testy v test_assembly.py.
EXAMPLE_PATHS = sorted(path for path in EXAMPLES.rglob("*.json")
                       if '"kind": "assembly"' not in path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", EXAMPLE_PATHS,
                         ids=lambda path: path.relative_to(EXAMPLES).as_posix())
def test_all_example_recipes_round_trip_without_aliasing_or_source_write(path, tmp_path):
    original_bytes = path.read_bytes()
    document = Document.load(path)
    expected = copy.deepcopy(document)
    data = document.to_dict()
    loaded = Document.from_dict(data)
    # Vnořené struktury ze vstupu ani z to_dict nesmějí změnit otevřený dokument.
    data["features"][0]["name"] = "Jméno změněné mimo dokument"
    data["parameters"].clear()
    if data.get("ndt"):
        data["ndt"]["studies"].clear()
    assert loaded == document == expected
    destination = tmp_path / "kopie.json"
    loaded.save(destination)
    restored = Document.load(destination)
    assert restored == expected
    assert restored.to_dict()["version"] == 24
    assert path.read_bytes() == original_bytes


@pytest.fixture
def edited_session(tmp_path):
    path = tmp_path / "deska.json"
    make_doc(box_features(20, 30, "t"), {"t": 10}).save(path)
    session = ModelSession()
    session.open(path)
    session.set_parameter("t", "12")
    session.set_parameter("t", "14")
    session.undo()  # rozpracovaná změna + dostupné Zpět i Znovu
    assert session.dirty and session.can_undo and session.can_redo
    return session


@pytest.mark.parametrize("bad_text", ["{", '{"format":"cizi","version":1}'])
def test_failed_open_preserves_unsaved_model_path_result_and_history(
        edited_session, tmp_path, bad_text):
    session = edited_session
    before = copy.deepcopy(session.document)
    result, original_path = session.result, session.path
    original_bytes = original_path.read_bytes()
    broken = tmp_path / "vadny.json"
    broken.write_text(bad_text, encoding="utf-8")
    with pytest.raises(DocumentError):
        session.open(broken)
    assert session.document == before and session.result is result
    assert session.path == original_path and session.dirty
    assert original_path.read_bytes() == original_bytes
    session.redo()
    assert session.properties.volume_mm3 == pytest.approx(20 * 30 * 14)
    session.undo()
    session.undo()
    assert session.properties.volume_mm3 == pytest.approx(20 * 30 * 10)


def test_rejected_edit_keeps_redo_branch_and_geometry(edited_session):
    session = edited_session
    before = copy.deepcopy(session.document)
    result = session.result
    with pytest.raises(DocumentError, match="neznámý parametr"):
        session.set_parameter("t", "chybejici + 1")
    assert session.document == before and session.result is result
    assert session.dirty and session.can_redo
    session.redo()
    assert session.properties.volume_mm3 == pytest.approx(20 * 30 * 14)
    assert session.result.part.is_valid


def test_failed_save_as_keeps_current_file_dirty_state_and_history(edited_session, tmp_path):
    session = edited_session
    original_path = session.path
    original_bytes = original_path.read_bytes()
    before = copy.deepcopy(session.document)
    # Skutečné selhání zápisu na všech OS: cíl je existující adresář.
    with pytest.raises(OSError):
        session.save(tmp_path)
    assert session.path == original_path and session.dirty
    assert session.document == before and session.can_redo and session.can_undo
    assert original_path.read_bytes() == original_bytes
    session.redo()
    saved = session.save()
    assert not session.dirty
    assert Document.load(saved).parameters["t"] == 14


def test_failed_feature_round_trip_retains_last_solid_error_and_skipped_tail():
    document = make_doc(box_features(20, 30, 40) + [
        {"id": "fail", "type": "fillet", "edges": "all", "radius": 50},
        {"id": "tail", "type": "chamfer", "edges": "all", "distance": 1},
    ])
    result = rebuild(document)
    restored = decode_result(pickle.loads(pickle.dumps(encode_result(result))))
    assert not restored.ok and restored.first_error.id == "fail"
    assert "Zaoblení R50 se nepodařilo" in restored.first_error.message
    assert [(status.id, status.status) for status in restored.statuses] == [
        ("s", "ok"), ("e", "ok"), ("fail", "error"), ("tail", "skipped")]
    assert restored.part.is_valid and len(restored.part.solids()) == 1
    assert restored.part.volume == pytest.approx(20 * 30 * 40)
    assert tuple(restored.part.bounding_box().size) == pytest.approx((20, 30, 40))
    assert restored.parts_before["fail"].volume == pytest.approx(20 * 30 * 40)
    assert "tail" not in restored.parts_before


def test_geometry_error_can_be_undone_redone_and_repaired(edited_session):
    session = edited_session
    session.add_feature("fillet", values={"edges": "all", "radius": 50})
    assert not session.result.ok
    assert session.properties.volume_mm3 == pytest.approx(20 * 30 * 12)
    session.undo()
    assert session.result.ok and session.result.part.is_valid
    session.redo()
    assert not session.result.ok
    session.undo()
    session.set_parameter("t", "16")
    assert session.result.ok and not session.can_redo
    assert session.properties.volume_mm3 == pytest.approx(20 * 30 * 16)
