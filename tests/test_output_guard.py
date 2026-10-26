"""P1.4 E.1: poslední dobrý mezistav není hotový exportovatelný recept."""

import copy
from types import SimpleNamespace

import pytest
from build123d import Part, import_step

from conftest import box_features, make_doc
from skodacad import Document, DocumentError
from skodacad.cli import main
from skodacad.export import FORMATS
from skodacad.rebuild import BuildResult, FeatureStatus, part_problem, require_complete_part
from skodacad.session import ModelSession


@pytest.fixture
def output_session(tmp_path):
    document = make_doc(box_features(20, 30, "h"), {"h": 40})
    source = tmp_path / "original.json"
    document.save(source)
    session = ModelSession()
    session.open(source)
    return session


def fail_history(session):
    session.add_feature("fillet", feature_id="bad", values={"edges": "all", "radius": 50})
    session.add_feature("chamfer", feature_id="tail", values={"edges": "all", "distance": 1})
    assert not session.result.ok
    assert session.result.first_error.id == "bad"
    assert session.result.statuses[-1].status == "skipped"
    assert session.result.part.is_valid and session.result.part.volume == pytest.approx(24000)


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("exists", [False, True])
def test_failed_history_cannot_create_or_overwrite_geometry(output_session, tmp_path, fmt, exists):
    session = output_session
    fail_history(session)
    target = tmp_path / f"output.{fmt}"
    if exists:
        target.write_bytes(b"Puvodni vystup zustava\x00\xff")
    before = copy.deepcopy((session.document, session.path, session.dirty,
                            session._undo, session._redo))
    result = session.result
    with pytest.raises(DocumentError, match=r"\[bad\].*R50"):
        session.export(target)
    assert (session.document, session.path, session.dirty, session._undo, session._redo) == before
    assert session.result is result
    if exists:
        assert target.read_bytes() == b"Puvodni vystup zustava\x00\xff"
    else:
        assert not target.exists()


@pytest.mark.parametrize("fmt", ["dxf", "svg"])
def test_section_remains_visible_but_partial_recipe_cannot_export_it(output_session, tmp_path, fmt):
    session = output_session
    fail_history(session)
    session.set_section_axis("X", 0)
    assert session.section is not None and session.display_part is session.section.part
    target = tmp_path / f"section.{fmt}"
    target.write_bytes(b"puvodni rez")
    with pytest.raises(DocumentError, match="Model není dokončený"):
        session.export_section(target)
    assert target.read_bytes() == b"puvodni rez"


@pytest.mark.parametrize("exists", [False, True])
def test_cli_refuses_all_outputs_before_mkdir_or_write(output_session, tmp_path, capsys, exists):
    session = output_session
    fail_history(session)
    source = session.save(tmp_path / "failed.json")
    folder = tmp_path / "exports"
    if exists:
        folder.mkdir()
        for fmt in FORMATS:
            (folder / f"failed.{fmt}").write_bytes(b"puvodni")
    assert main(["build", str(source), "--format", ",".join(FORMATS), "-o", str(folder)]) == 1
    output = capsys.readouterr()
    assert "[bad]" in output.err and "R50" in output.err
    assert "Diagnostika posledního dobrého mezistavu" in output.out
    assert "Počet těles: 1" in output.out and "Uloženo:" not in output.out
    assert all(p.read_bytes() == b"puvodni" for p in folder.iterdir()) if exists \
        else not folder.exists()


def test_valid_two_body_export_preserves_both_solids(output_session, tmp_path):
    session = output_session
    session.add_feature("sketch", feature_id="island", values={"plane": "XY", "elements": [
        {"shape": "rectangle", "width": 5, "height": 5, "center": [100, 0]}]})
    session.add_feature("extrude", values={"sketch": "island", "distance": 10,
                                           "operation": "add"})
    assert session.result.ok and not session.model_problem
    exported = import_step(session.export(tmp_path / "both.step"))
    assert exported.is_valid and len(exported.solids()) == 2
    assert exported.volume == pytest.approx(24250)
    assert tuple(exported.bounding_box().size) == pytest.approx((112.5, 30, 40))


@pytest.mark.parametrize("features", [[], box_features()[:1]])
def test_empty_or_sketch_only_model_has_no_exportable_body(tmp_path, features):
    session = ModelSession()
    source = tmp_path / "source.json"
    make_doc(features).save(source)
    session.open(source)
    assert session.result.ok
    with pytest.raises(DocumentError, match="těleso"):
        session.export(tmp_path / "empty.step")
    assert not (tmp_path / "empty.step").exists()


def test_shared_guard_rejects_empty_shape_and_skipped_without_first_error():
    with pytest.raises(DocumentError, match="těleso"):
        require_complete_part(BuildResult(Part(), {}))
    skipped = BuildResult(None, {}, [FeatureStatus("tail", "extrude", "Konec", "skipped")])
    assert "přeskočené" in part_problem(skipped)
    with pytest.raises(DocumentError, match="přeskočené"):
        require_complete_part(skipped)


def test_failed_worker_cannot_export_old_ok_result_and_retry_recovers(output_session, tmp_path):
    session = output_session
    old_result = session.result
    # Řízená chyba transportu; skutečný model i jeho změna používají stejnou session.
    runner = SimpleNamespace(submit=lambda *args, **kwargs: 7)
    session._runner = runner
    session.set_parameter("h", "50")
    assert session.computing and session.result is old_result and old_result.ok
    with pytest.raises(DocumentError, match="ještě přepočítává"):
        session.export(tmp_path / "during.step")
    runner.poll = lambda: SimpleNamespace(job=7, update=None, result=None, error="Worker spadl")
    assert session.poll() and not session.computing and session.failure == "Worker spadl"
    assert session.result is old_result
    with pytest.raises(DocumentError, match="předchozímu stavu"):
        session.export(tmp_path / "old.step")
    session._runner = None
    session.rebuild()
    assert session.result.ok and not session.model_problem
    exported = import_step(session.export(tmp_path / "retry.step"))
    assert exported.volume == pytest.approx(30000)
    assert not (tmp_path / "during.step").exists() and not (tmp_path / "old.step").exists()


def test_invalid_json_can_be_saved_reopened_and_repaired_with_history(output_session, tmp_path):
    session = output_session
    original = session.path.read_bytes()
    session.add_feature("fillet", feature_id="bad", values={"edges": "all", "radius": 50})
    saved = session.save(tmp_path / "work.json")
    restored = ModelSession()
    restored.open(saved)
    assert not restored.result.ok and Document.load(saved).to_dict()["version"] == 23
    fixed = restored.feature("bad")
    fixed["radius"] = 2
    restored.update_feature("bad", fixed)
    assert restored.result.ok and not restored.model_problem
    restored.export(tmp_path / "fixed.step")
    restored.undo()
    with pytest.raises(DocumentError, match="Model není dokončený"):
        restored.export(tmp_path / "again.step")
    restored.redo()
    assert restored.result.ok and not restored.model_problem
    assert output_session.path == saved
    assert (tmp_path / "original.json").read_bytes() == original
    assert not (tmp_path / "again.step").exists()
