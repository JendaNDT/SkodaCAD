"""První průchod uloženého STEP v modelu a přepočtu."""
from pathlib import Path

import pytest

from skodacad.document import Document
from skodacad.rebuild import rebuild
from skodacad.step_source import source_record
from skodacad.worker import BackgroundRebuilder

STEP = Path(__file__).parent / "fixtures" / "step" / "01-jedno-teleso.step"


def model():
    return Document(features=[{"id": "step1", "type": "step_import", "name": "Kvádr",
                               **source_record(STEP.read_bytes(), "kvadr.step")}])


def test_embedded_step_survives_save_and_open(tmp_path):
    document = model()
    path = tmp_path / "model.json"
    document.save(path)
    loaded = Document.load(path)
    assert loaded.to_dict()["version"] == 24
    result = rebuild(loaded)
    assert result.ok
    assert result.part.volume == pytest.approx(24000, abs=1e-5)


def test_background_rebuild_of_embedded_step():
    runner = BackgroundRebuilder()
    try:
        runner.submit(model().to_dict())
        outcome = runner.wait(timeout=30)
        assert outcome is not None and not outcome.error
        assert outcome.result.ok
        assert outcome.result.part.volume == pytest.approx(24000, abs=1e-5)
    finally:
        runner.close()


def test_damage_is_stopped_without_geometry():
    document = model()
    document.features[0]["sha256"] = "0" * 64
    result = rebuild(document)
    assert not result.ok
    assert result.part is None
    assert "otisk" in result.first_error.message


def test_failed_save_preserves_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "model.json"
    path.write_bytes(b"puvodni soubor")

    def failure(_source, _target):
        raise OSError("selhal zapis")

    monkeypatch.setattr("skodacad.document.os.replace", failure)
    with pytest.raises(OSError, match="selhal zapis"):
        model().save(path)
    assert path.read_bytes() == b"puvodni soubor"
    assert list(tmp_path.iterdir()) == [path]


def test_session_import_undo_redo_and_direct_edit(tmp_path):
    from skodacad.session import ModelSession

    session = ModelSession()
    session.new_document()
    session.add_step_import(STEP.read_bytes(), "kvadr.step")
    assert session.result.ok
    assert session.result.part.volume == pytest.approx(24000, abs=1e-5)
    assert session.undo()
    assert not session.document.features
    assert session.redo()
    assert session.result.part.volume == pytest.approx(24000, abs=1e-5)
    session.add_feature("move_face", values={"face": {"at": [20, 15, 20],
                        "normal": [0, 0, 1], "type": "plane"},
                        "origin": "step_import1", "distance": 5})
    assert session.result.ok, session.result.first_error
    assert session.result.part.volume == pytest.approx(30000, abs=1e-5)
    path = tmp_path / "prenos.json"
    session.save(path)
    reopened = ModelSession()
    reopened.open(path)
    assert reopened.result.ok
    assert reopened.result.part.volume == pytest.approx(30000, abs=1e-5)


def test_ai_view_omits_step_bytes_without_changing_model():
    from skodacad.assistant import _ai_document

    original = model().to_dict()
    encoded = original["features"][0]["data"]
    visible = _ai_document(original)
    assert "data" not in visible["features"][0]
    assert visible["features"][0]["sha256"] == original["features"][0]["sha256"]
    assert original["features"][0]["data"] == encoded


def test_restore_only_identical_source_and_undo(tmp_path):
    from skodacad.document import DocumentError
    from skodacad.session import ModelSession

    document = model()
    del document.features[0]["data"]
    path = tmp_path / "poskozeny.json"
    document.save(path)
    session = ModelSession()
    session.open(path)
    assert not session.result.ok
    before = session.document.to_dict()
    with pytest.raises(DocumentError, match="neodpovídá"):
        session.restore_step_source("step1", b"jiny soubor")
    assert session.document.to_dict() == before
    session.restore_step_source("step1", STEP.read_bytes())
    assert session.result.ok
    assert session.result.part.volume == pytest.approx(24000)
    session.undo()
    assert session.document.to_dict() == before
    assert not session.result.ok


def test_source_cannot_be_silently_replaced():
    from skodacad.document import DocumentError
    from skodacad.session import ModelSession

    session = ModelSession()
    session.new_document()
    with pytest.raises(DocumentError, match="Importovat STEP"):
        session.add_feature("step_import")
    session.add_step_import(STEP.read_bytes(), "kvadr.step")
    before = session.document.to_dict()
    changed = session.feature("step_import1")
    changed["sha256"] = "0" * 64
    with pytest.raises(DocumentError, match="totožného"):
        session.update_feature("step_import1", changed)
    assert session.document.to_dict() == before
