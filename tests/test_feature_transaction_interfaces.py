"""P1.2B: přenos, historie a shodné stavy skutečných pozdních chyb."""

import math
import pickle

import pytest

from skodacad import rebuild
from skodacad.assistant import build_report
from skodacad.cli import main
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder, decode_result, encode_result
from transaction_cases import late_failure_document


def assert_case(result, kind, repaired):
    volume = 80000 - (80 if repaired else 40) * math.pi
    assert result.ok == repaired
    assert result.part.is_valid and len(result.part.solids()) == 1
    assert result.part.volume == pytest.approx(volume)
    assert set(result.sketches) == {"s", "s0", "s1"} | ({"tail"} if repaired else set())
    assert not result.part.is_inside((-20, 0, 7.5))
    assert not result.part.is_inside((45, 0, 7.5))
    new_x = (0, 25) if kind == "pattern" else (-45, 20)
    if repaired:
        for x in ((-40, 25) if kind == "pattern" else new_x):
            assert not result.part.is_inside((x, 0, 7.5))
        assert result.statuses[-2].message == "Počet těles: 1 → 1."
    else:
        assert result.first_error.id == "bad" and result.statuses[-1].status == "skipped"
        assert "Počet těles" not in result.first_error.message
        assert result.part.is_inside((0 if kind == "pattern" else -5, 0, 7.5))
        assert result.parts_before["bad"].volume == pytest.approx(volume)


@pytest.fixture(scope="module")
def runner():
    worker = BackgroundRebuilder()
    yield worker
    worker.close()


@pytest.mark.parametrize("kind", ["pattern", "mirror"])
@pytest.mark.parametrize("repaired", [False, True])
def test_partial_or_complete_result_survives_existing_bin_tools_protocol(kind, repaired):
    result = rebuild(late_failure_document(kind, repaired))
    encoded = encode_result(result)
    assert set(encoded) == {"part", "parameters", "statuses", "parts_before", "sketches",
                            "measurements", "thickness_map", "map_error", "ndt"}
    restored = decode_result(pickle.loads(pickle.dumps(encoded)))
    assert restored.statuses == result.statuses
    assert restored.parameters == result.parameters
    assert_case(restored, kind, repaired)
    for key, (plane, sketch) in result.sketches.items():
        other_plane, other_sketch = restored.sketches[key]
        assert tuple(other_plane.origin) == pytest.approx(tuple(plane.origin))
        assert tuple(other_plane.z_dir) == pytest.approx(tuple(plane.z_dir))
        assert other_sketch.area == pytest.approx(sketch.area)


@pytest.mark.parametrize("kind", ["pattern", "mirror"])
def test_real_spawn_preserves_failure_repair_and_accepted_sketches(runner, kind):
    for repaired in [False, True, False]:
        document = late_failure_document(kind, repaired)
        direct = rebuild(document)
        job = runner.submit(document.to_dict())
        completed = runner.wait(timeout=60)
        assert completed is not None and completed.job == job and not completed.error
        assert completed.result.statuses == direct.statuses
        assert_case(completed.result, kind, repaired)


@pytest.mark.parametrize("kind", ["pattern", "mirror"])
def test_repair_undo_redo_round_trip_and_interface_messages(kind, tmp_path, capsys):
    source = tmp_path / "original.json"
    late_failure_document(kind).save(source)
    original_bytes = source.read_bytes()
    session = ModelSession()
    session.open(source)
    assert_case(session.result, kind, False)
    report = build_report(session)
    assert main(["build", str(source), "--format", "step", "-o", str(tmp_path / "bad")]) == 1
    cli = capsys.readouterr().out
    assert session.result.first_error.message in cli
    assert session.result.first_error.message in report
    assert "přeskočeno" in report and "Počet těles: 1" in cli
    feature = session.feature("bad")
    feature["spacing" if kind == "pattern" else "offset"] = -20 if kind == "pattern" else 0
    session.update_feature("bad", feature)
    assert_case(session.result, kind, True)
    session.undo()
    assert_case(session.result, kind, False)
    session.redo()
    assert_case(session.result, kind, True)
    copy = tmp_path / "copy.json"
    session.save(copy)
    restored = ModelSession()
    restored.open(copy)
    assert_case(restored.result, kind, True)
    assert main(["build", str(copy), "--format", "step", "-o", str(tmp_path / "good")]) == 0
    cli = capsys.readouterr().out
    message = "Počet těles: 1 → 1."
    assert message in cli and message in build_report(restored)
    assert source.read_bytes() == original_bytes
