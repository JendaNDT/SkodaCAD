"""P1.2A: shodné zprávy, skutečný worker, opravitelné chyby a nezměněný formát."""

import pickle

import pytest

from body_count_cases import COUNT_CASE_NAMES, body_count_case
from conftest import box_features, make_doc
from skodacad import Document, rebuild
from skodacad.assistant import build_report
from skodacad.cli import main
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder, decode_result, encode_result


@pytest.fixture(params=COUNT_CASE_NAMES)
def body_case(request, tmp_path):
    document, volume, count, transitions = body_count_case(request.param)
    path = tmp_path / (request.param + ".json")
    document.save(path)
    return document, volume, count, transitions, path


def assert_transitions(result, transitions):
    actual = {s.id: s.message for s in result.statuses if s.type != "sketch"}
    assert actual == {key: f"Počet těles: {before} → {after}."
                      for key, (before, after) in transitions.items()}
    assert all(s.message == "" for s in result.statuses if s.type == "sketch")
    assert result.ok


def test_core_cli_and_ai_report_the_same_actual_body_counts(body_case, tmp_path, capsys):
    document, volume, count, transitions, path = body_case
    original = path.read_bytes()
    result = rebuild(document)
    assert_transitions(result, transitions)
    assert result.part.volume == pytest.approx(volume, rel=1e-9)
    assert len(result.part.solids()) == count
    code = main(["build", str(path), "--format", "step", "-o", str(tmp_path / "out")])
    output = capsys.readouterr().out
    assert code == 0 and f"Počet těles: {count}\n" in output
    session = ModelSession()
    session.open(path)
    report = build_report(session)  # čistě místní souhrn, žádné API volání
    assert "Přepočet: v pořádku" in report and f"těles {count}" in report
    for before, after in transitions.values():
        message = f"Počet těles: {before} → {after}."
        assert message in output and message in report
    assert path.read_bytes() == original


def test_body_messages_survive_existing_transfer_without_new_protocol_fields(body_case):
    document, volume, count, transitions, _path = body_case
    encoded = encode_result(rebuild(document))
    assert set(encoded) == {"part", "parameters", "statuses", "parts_before", "sketches",
                            "measurements", "thickness_map", "map_error", "ndt"}
    restored = decode_result(pickle.loads(pickle.dumps(encoded)))
    assert_transitions(restored, transitions)
    assert restored.part.volume == pytest.approx(volume, rel=1e-9)
    assert len(restored.part.solids()) == count


@pytest.fixture(scope="module")
def count_runner():
    runner = BackgroundRebuilder()
    yield runner
    runner.close()


def test_body_messages_survive_a_real_spawned_rebuild(body_case, count_runner):
    document, volume, count, transitions, _path = body_case
    job = count_runner.submit(document.to_dict())
    completed = count_runner.wait(timeout=60)
    assert completed is not None and completed.job == job and not completed.error
    assert_transitions(completed.result, transitions)
    assert completed.result.part.volume == pytest.approx(volume, rel=1e-9)
    assert len(completed.result.part.solids()) == count


@pytest.mark.parametrize("kind", ["add", "shell"])
def test_new_rejections_can_be_undone_redone_repaired_and_saved(kind, tmp_path):
    is_shell = kind == "shell"
    document = make_doc(box_features(50, 30, 20) if is_shell else box_features())
    path = tmp_path / "original.json"
    document.save(path)
    original = path.read_bytes()
    session = ModelSession()
    session.open(path)
    previous_volume = session.properties.volume_mm3
    feature_id = session.add_feature("shell" if is_shell else "extrude", values=(
        {"thickness": 2, "open_faces": []} if is_shell else
        {"sketch": "s", "distance": 20, "direction": "normal", "operation": "add"}
    ))
    assert not session.result.ok and session.result.first_error.id == feature_id
    assert "Počet těles:" not in session.result.first_error.message
    assert session.properties.volume_mm3 == pytest.approx(previous_volume)
    assert "NĚKTERÉ PRVKY MAJÍ CHYBU" in build_report(session)
    session.undo()
    assert session.result.ok
    session.redo()
    assert not session.result.ok
    repaired = session.feature(feature_id)
    repaired.update({"open_faces": ["top"]} if is_shell else {"distance": 60})
    session.update_feature(feature_id, repaired)
    assert session.result.ok
    assert session.properties.volume_mm3 == pytest.approx(8472 if is_shell else 36000)
    assert session.result.statuses[-1].message == "Počet těles: 1 → 1."
    session.undo()
    assert not session.result.ok
    session.redo()
    assert session.result.ok
    saved = tmp_path / "copy.json"
    session.save(saved)
    data = Document.load(saved).to_dict()
    assert data["version"] == 24 and path.read_bytes() == original
    assert all("message" not in feature for feature in data["features"])


def test_failed_and_skipped_features_are_not_reported_as_successful_counts(tmp_path, capsys):
    document = make_doc(box_features() + [
        {"id": "bad", "type": "shell", "thickness": 2, "open_faces": []},
        {"id": "tail", "type": "chamfer", "distance": 1, "edges": "all"},
    ])
    path = tmp_path / "error.json"
    document.save(path)
    session = ModelSession()
    session.open(path)
    report = build_report(session)
    for marker in ("[bad]", "[tail]"):
        assert "Počet těles:" not in next(line for line in report.splitlines() if marker in line)
    assert not session.result.ok and session.result.statuses[-1].status == "skipped"
    assert main(["build", str(path), "--format", "step", "-o", str(tmp_path / "out")]) == 1
    output = capsys.readouterr().out
    assert "Počet těles:" not in next(line for line in output.splitlines() if "Skořepina" in line)
