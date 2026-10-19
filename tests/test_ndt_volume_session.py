"""Objemové cíle: formát 16, změny modelu, historie a bezpečné chování aplikace 07A."""

import copy
import json
import pickle

import pytest

from conftest import EXAMPLES
from skodacad import Document, DocumentError, rebuild
from skodacad.cli import main
from skodacad.ndt.study import new_study, part_fingerprint
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder, decode_result, encode_result
from test_ndt_session import coverage_session
from test_ndt_welds import fillet_target, v_target, volume_target


def target():
    return volume_target(profile_mm=[[0, 0], [10, 0], [10, 10], [0, 10]])


def opened(name="deska"):
    session = ModelSession()
    session.open(EXAMPLES / "ndt" / f"{name}.json")
    return session


@pytest.mark.parametrize("version", range(1, 16))
def test_older_versions_keep_face_studies_and_original_file_until_explicit_save(version, tmp_path):
    data = Document.load(EXAMPLES / "ndt/deska.json").to_dict() | {"version": version}
    old = tmp_path / "original.json"
    old.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    before = old.read_bytes()
    session = ModelSession()
    session.open(old)
    assert session.ndt_study("s1")["target"] == data["ndt"]["studies"][0]["target"]
    session.save(tmp_path / "kopie.json")
    assert old.read_bytes() == before
    assert json.loads((tmp_path / "kopie.json").read_text(encoding="utf-8"))["version"] == 21


def test_loading_volume_normalizes_frame_without_mutation_and_round_trips(tmp_path):
    document = Document.load(EXAMPLES / "ndt/deska.json")
    saved = target()
    saved["frame"]["axis"] = [0, 4, 0]
    saved["frame"]["across"] = [2, 0, 0]
    record = new_study("UT", [], part_fingerprint(document), saved)
    data = document.to_dict() | {"ndt": {"studies": [record]}}
    before = copy.deepcopy(data)
    loaded = Document.from_dict(data)
    assert data == before
    assert loaded.ndt["studies"][0]["target"]["frame"]["axis"] == [0, 1, 0]
    path = tmp_path / "objem.json"
    loaded.save(path)
    assert Document.load(path) == loaded
    [state] = rebuild(loaded).ndt
    assert state.state == "ok" and state.volume_mm3 == pytest.approx(2000)
    assert "2000 mm³" in state.text


def test_volume_target_changes_only_study_invalidates_map_and_verification_and_has_history():
    session = coverage_session()
    session.verify_ndt_study("s1", "Ověřovatel")
    old_record = session.ndt_study("s1")
    session.compute_ndt_coverage(mode="line", length_mm=0, step_mm=10)
    assert session.ndt_coverage is not None
    before_part = session.properties.volume_mm3
    before_features = copy.deepcopy(session.document.features)
    session.set_ndt_volume_target("s1", target())
    assert session.ndt_coverage is None
    assert "verified" not in session.ndt_study("s1")
    assert session.ndt_studies[0].target_kind == "volume"
    assert session.ndt_studies[0].faces == 0
    assert session.ndt_target_volume("s1").volume_mm3 == pytest.approx(2000)
    assert session.properties.volume_mm3 == before_part
    assert session.document.features == before_features
    session.undo()
    assert session.ndt_study("s1") == old_record
    session.redo()
    assert session.ndt_target_volume("s1").volume_mm3 == pytest.approx(2000)
    result = session.compute_ndt_coverage(step_mm=25, target_step_mm=10)
    assert result.total_volume == pytest.approx(2000)
    from skodacad.ndt.volume_drawing import mesh_areas

    # 07C: kresba = povrch cíle 10 × 10 × 20 mm obarvený podle buněk
    assert sum(mesh_areas(session.visible_ndt_coverage()).values()) == pytest.approx(1000)


def test_invalid_target_rolls_back_without_touching_document_or_history():
    session = opened()
    before, history = session.document.to_dict(), len(session._undo)
    for bad in (target() | {"length_mm": -1}, v_target()):
        with pytest.raises(DocumentError):
            session.set_ndt_volume_target("s1", bad)
        assert session.document.to_dict() == before and len(session._undo) == history


def test_duplicate_target_is_independent_and_drops_verification(tmp_path):
    session = opened()
    session.set_ndt_volume_target("s1", target())
    session.verify_ndt_study("s1", "Ověřovatel")
    sid = session.duplicate_ndt_study("s1")
    assert "verified" not in session.ndt_study(sid)
    changed = target()
    changed["frame"]["origin"][0] = 30
    session.set_ndt_volume_target(sid, changed)
    assert session.ndt_study("s1")["target"]["frame"]["origin"] == [0, 0, 0]
    assert session.ndt_study(sid)["target"]["frame"]["origin"] == [30, 0, 0]
    path = session.save(tmp_path / "studie.json")
    loaded = ModelSession()
    loaded.open(path)
    assert loaded.document == session.document
    volumes = [s.volume_mm3 for s in loaded.ndt_studies if s.target_kind == "volume"]
    assert volumes == pytest.approx([2000, 2000])


def test_changed_part_requires_confirmation_and_does_not_move_target():
    session = opened()
    session.set_ndt_volume_target("s1", target())
    saved = session.ndt_study("s1")["target"]
    session.verify_ndt_study("s1", "Ověřovatel")
    session.set_parameter("A", "220")
    assert session.ndt_studies[0].state == "stale"
    with pytest.raises(DocumentError, match="platnou studii"):
        session.ndt_target_volume("s1")
    session.confirm_ndt_study("s1")
    assert session.ndt_studies[0].state == "ok"
    assert session.ndt_study("s1")["target"] == saved
    assert "verified" not in session.ndt_study("s1")
    session.undo()
    assert session.ndt_studies[0].state == "stale"
    session.undo()
    assert session.ndt_studies[0].state == "ok"


def test_missing_weld_material_breaks_link_and_cannot_be_confirmed():
    session = opened("koutovy_svar")
    session.set_ndt_volume_target("s1", fillet_target())
    session.set_parameter("z", "3")
    assert session.ndt_studies[0].state == "broken"
    assert "není celý v materiálu" in session.ndt_studies[0].messages[0]
    with pytest.raises(DocumentError, match="Studii nejde potvrdit"):
        session.confirm_ndt_study("s1")
    session.undo()
    assert session.ndt_target_volume("s1").volume_mm3 == pytest.approx(2450)


def test_imported_empty_volume_is_broken_not_incomplete_or_zero_coverage():
    document = Document.load(EXAMPLES / "ndt/deska.json")
    outside = target()
    outside["frame"]["origin"] = [0, 0, 50]
    document.ndt["studies"][0]["target"] = outside
    result = rebuild(document).ndt[0]
    assert result.state == "broken" and result.target_kind == "volume"
    assert result.volume_mm3 == 0
    assert "žádný společný objem" in result.messages[0]


def test_volume_study_is_transferred_as_numbers_without_occt_shapes():
    session = opened()
    session.set_ndt_volume_target("s1", target())
    copied = decode_result(pickle.loads(pickle.dumps(encode_result(session.result))))
    assert copied.ndt == session.ndt_studies
    assert copied.ndt[0].volume_mm3 == pytest.approx(2000)


@pytest.mark.parametrize("filename,volumes,base", [
    ("tupy_svar_objem.json", [14613.84387633061] * 2, "tupy_svar.json"),  # UT a RT studie
    ("koutovy_svar_objem.json", [2450, 2450], "koutovy_svar.json"),
])
def test_volume_examples_preserve_original_manufacturing_geometry(filename, volumes, base):
    document = Document.load(EXAMPLES / "ndt/cilove_objemy" / filename)
    original = Document.load(EXAMPLES / "ndt" / base)
    assert document.features == original.features and document.parameters == original.parameters
    result = rebuild(document)
    assert result.ok and all(s.state == "ok" for s in result.ndt)
    assert [s.volume_mm3 for s in result.ndt] == pytest.approx(volumes)
    assert result.part.volume == pytest.approx(rebuild(original).part.volume)


def test_volume_target_background_rebuild_and_save(tmp_path):
    runner = BackgroundRebuilder()
    try:
        session = ModelSession(runner)
        session.open(EXAMPLES / "ndt/tupy_svar.json")
        assert session.wait(30)
        session.set_ndt_volume_target("s1", v_target())
        assert session.wait(30) and not session.failure
        assert session.ndt_studies[0].volume_mm3 == pytest.approx(14613.84387633061)
        session.save(tmp_path / "svar.json")
        session.undo()
        assert session.wait(30)
        assert session.ndt_studies[0].target_kind == "faces"
    finally:
        runner.close()


def test_volume_verification_tracks_target_even_if_file_is_edited_outside_session(tmp_path):
    session = opened()
    session.set_ndt_volume_target("s1", target())
    session.verify_ndt_study("s1", "Ověřovatel")
    before = session.save(tmp_path / "overeny.json")
    loaded = opened()
    loaded.open(before)
    assert "Ověřil(a) Ověřovatel" in loaded.ndt_studies[0].verified
    data = session.document.to_dict()
    data["ndt"]["studies"][0]["target"]["length_mm"] = 10
    session.replace_document(data)
    assert session.ndt_studies[0].state == "ok"
    assert "neplatí" in session.ndt_studies[0].verified
    session.confirm_ndt_study("s1")
    assert "verified" not in session.ndt_study("s1")


def test_failed_rebuild_cannot_use_old_part_for_volume_or_its_verification():
    session = opened()
    session.set_ndt_volume_target("s1", target())
    session._computed = None  # jako po chybě pomocného procesu, result je dosavadní starý díl
    for action in (lambda: session.ndt_target_volume("s1"),
                   lambda: session.set_ndt_volume_target("s1", target()),
                   lambda: session.verify_ndt_study("s1", "Ověřovatel")):
        with pytest.raises(DocumentError, match="aktuálně spočítané"):
            action()


def test_cli_reports_volume_and_computes_weighted_coverage(tmp_path, capsys):
    session = opened()
    session.set_ndt_volume_target("s1", target())
    path = session.save(tmp_path / "objem.json")
    assert main(["build", str(path), "--out", str(tmp_path / "export")]) == 0
    from skodacad.ndt import UT_DISCLAIMER

    summary = capsys.readouterr().out
    assert "2000 mm³" in summary and UT_DISCLAIMER in summary
    csv_path = tmp_path / "coverage.csv"
    assert main(["pokryti", str(path), "--studie", "s1", "--plocha", "0,0,20",
                 "--prima", "10", "--krok", "25", "--krok-cile", "10", "--konvergence",
                 "--csv", str(csv_path)]) == 0
    captured = capsys.readouterr().out
    assert "2000 mm³" in captured and "Cíl: objem" in captured
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "objem [mm³]" in text and "convergence" in text and UT_DISCLAIMER in text
    assert "mm²" not in text


def test_volume_background_result_cancel_and_target_change_invalidate_cache(tmp_path):
    from skodacad.ndt.volume_coverage import VolumeCoverageMap

    runner = BackgroundRebuilder()
    try:
        session = coverage_session(runner)
        session.set_ndt_volume_target("s1", target())
        assert session.wait(30)
        before = session.document.to_dict()
        session.start_ndt_coverage(step_mm=25, target_step_mm=10)
        assert session.computing and session.ndt_coverage is None
        assert session.wait(40), session.failure
        result = session.ndt_coverage
        assert isinstance(result, VolumeCoverageMap)
        assert result.total_volume == pytest.approx(2000)
        assert result.volume("covered") == pytest.approx(2000)
        assert session.document.to_dict() == before
        assert "objem [mm³]" in session.export_ndt_coverage(
            tmp_path / "volume.csv").read_text(encoding="utf-8-sig")
        session.set_section_axis("X", 2)
        assert session.ndt_coverage is result and result.total_volume == pytest.approx(2000)
        from skodacad.ndt.volume_drawing import mesh_areas

        # řez X = 2 nechá z cíle 2 × 20 × 10 mm; kresba je jen pohled, čísla stejná
        drawing = mesh_areas(session.visible_ndt_coverage())
        assert sum(drawing.values()) == pytest.approx(2 * (2 * 20 + 2 * 10 + 20 * 10))
        session.start_ndt_coverage(step_mm=1, target_step_mm=0.1)
        assert session.cancel()
        assert session.document.to_dict() == before and session.ndt_coverage is None
        session.start_ndt_coverage(step_mm=25, target_step_mm=10)
        with pytest.raises(DocumentError, match="ještě přepočítává"):
            session.set_ndt_volume_target("s1", target() | {"length_mm": 10})
        assert session.cancel()
        session.set_ndt_volume_target("s1", target() | {"length_mm": 10})
        assert session.wait(40)
        assert session.ndt_coverage is None
    finally:
        runner.close()


def test_explicit_cli_points_do_not_masquerade_as_volume_of_study(tmp_path, capsys):
    session = coverage_session()
    session.set_ndt_volume_target("s1", target())
    path = session.save(tmp_path / "model.json")
    assert main(["pokryti", str(path), "--studie", "s1", "--plocha", "0,0,20",
                 "--cil", "0,0,0", "--rezim", "line", "--delka", "0"]) == 0
    text = capsys.readouterr().out
    assert "1 bodů" in text and "'evaluated_target': 'points'" in text and "mm³" not in text
