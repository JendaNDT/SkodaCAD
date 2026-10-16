"""NDT studie v ModelSession (etapa 01): úpravy, Zpět/Znovu, ověření, řez, pozadí, CLI."""

import datetime
import json

import pytest

from conftest import EXAMPLES, face_at
from skodacad import DocumentError
from skodacad.cli import main
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder

NDT = EXAMPLES / "ndt"


def opened(name="deska"):
    session = ModelSession()
    session.open(NDT / f"{name}.json")
    return session


def state(session, study_id="s1"):
    return next(r for r in session.ndt_studies if r.id == study_id)


@pytest.mark.parametrize("path", sorted(NDT.glob("*.json")), ids=lambda p: p.stem)
def test_every_reference_part_has_a_valid_sample_study(path):
    session = ModelSession()
    session.open(path)
    [result] = session.ndt_studies
    assert result.state == "ok", result.messages
    assert result.faces >= 1


def test_parameter_change_makes_study_stale_and_undo_makes_it_valid():
    session = opened()
    session.set_parameter("t", "30")
    assert state(session).state == "stale"
    assert any("posunula o 10.00 mm" in m for m in state(session).messages)
    session.undo()
    assert state(session).state == "ok"
    session.redo()
    assert state(session).state == "stale"
    session.confirm_ndt_study("s1")
    assert state(session).state == "ok" and state(session).messages == ()
    assert session.ndt_study("s1")["target"]["faces"][0]["face"]["at"] == [0, 0, 30]
    session.undo()  # potvrzení je taky krok Zpět
    assert state(session).state == "stale"


def test_study_whose_face_disappeared_cannot_be_confirmed():
    session = opened("otvor")  # studie na stěně otvoru
    sketch = session.feature("obrys")
    sketch["elements"] = sketch["elements"][:1]  # otvor zmizí
    session.update_feature("obrys", sketch)
    assert state(session).state == "broken"
    assert "už na dílu není" in state(session).messages[0]
    with pytest.raises(DocumentError, match="Studii nejde potvrdit – Plocha u bodu"):
        session.confirm_ndt_study("s1")
    assert session.ndt_highlight("s1") == []


def test_rename_does_not_confirm_a_stale_study():
    session = opened()
    session.set_parameter("t", "25")
    session.rename_ndt_study("s1", "  Deska shora  ")
    assert state(session).name == "Deska shora"
    assert state(session).state == "stale"
    with pytest.raises(DocumentError, match="nesmí být prázdný"):
        session.rename_ndt_study("s1", " ")


def test_new_study_from_selected_faces_and_target_change():
    session = opened("kapsa")
    part = session.result.part
    floor = face_at(part, 0, 0, 15)
    wall = face_at(part, 20, 0, 30)
    sid = session.add_ndt_study("PT", [floor.wrapped, wall.wrapped], (0, 0, 15), "PT kapsy")
    assert sid == "s2"
    study = session.ndt_study(sid)
    assert study["method"] == "PT" and study["name"] == "PT kapsy"
    assert len(study["target"]["faces"]) == 2
    assert state(session, sid).state == "ok" and state(session, sid).faces == 2
    assert len(session.ndt_highlight(sid)) == 2
    floor = face_at(session.result.part, 0, 0, 15)  # po přepočtu je díl nový – klik znovu
    session.set_ndt_target(sid, [floor.wrapped])
    assert len(session.ndt_study(sid)["target"]["faces"]) == 1
    session.set_ndt_method(sid, "MT")
    assert state(session, sid).method == "MT"
    session.set_ndt_note(sid, " jen dno ")
    assert session.ndt_study(sid)["note"] == "jen dno"
    with pytest.raises(DocumentError, match="hrany ne"):
        session.set_ndt_target(sid, [session.result.part.edges()[0].wrapped])
    with pytest.raises(DocumentError, match="Metoda musí být"):
        session.set_ndt_method(sid, "ET")
    with pytest.raises(DocumentError, match="„x“ v modelu není"):
        session.rename_ndt_study("x", "nic")


def test_study_without_selection_is_incomplete_and_cannot_be_verified():
    session = opened()
    sid = session.add_ndt_study("RT")
    assert session.ndt_study(sid)["name"] == "RT studie 2"
    assert state(session, sid).state == "incomplete"
    with pytest.raises(DocumentError, match="neúplná"):
        session.verify_ndt_study(sid, "J. N.")


def test_verification_lifecycle():
    session = opened()
    with pytest.raises(DocumentError, match="kdo studii ověřil"):
        session.verify_ndt_study("s1", "  ")
    session.verify_ndt_study("s1", "J. N.")
    today = datetime.date.today()
    assert state(session).verified == f"Ověřil(a) J. N. {today.day}. {today.month}. {today.year}."
    session.set_parameter("t", "30")
    assert "neplatí" in state(session).verified
    with pytest.raises(DocumentError, match="zastaralá"):
        session.verify_ndt_study("s1", "J. N.")
    session.confirm_ndt_study("s1")  # potvrzení pro nový díl staré ověření smaže
    assert "verified" not in session.ndt_study("s1")
    assert state(session).verified == "Neověřeno."
    session.verify_ndt_study("s1", "J. N.")
    session.set_ndt_method("s1", "PT")  # změna zadání ověření smaže
    assert "verified" not in session.ndt_study("s1")
    session.verify_ndt_study("s1", "J. N.")
    session.unverify_ndt_study("s1")
    assert "verified" not in session.ndt_study("s1")


def test_duplicate_and_remove_with_undo(tmp_path):
    session = opened()
    copy_id = session.duplicate_ndt_study("s1")
    assert [r.id for r in session.ndt_studies] == ["s1", copy_id]
    assert state(session, copy_id).name == "UT desky shora (kopie)"
    session.remove_ndt_study("s1")
    session.remove_ndt_study(copy_id)
    assert session.ndt_studies == [] and session.document.ndt is None
    path = session.save(tmp_path / "bez_studii.json")
    assert "ndt" not in json.loads(path.read_text(encoding="utf-8"))
    session.undo()
    session.undo()
    assert [r.id for r in session.ndt_studies] == ["s1", copy_id]


def test_study_survives_save_and_reopen(tmp_path):
    session = opened()
    session.add_ndt_study("UT", [face_at(session.result.part, 0, 0, 0).wrapped], (0, 0, 0),
                          "UT zespodu")
    path = session.save(tmp_path / "deska.json")
    reopened = ModelSession()
    reopened.open(path)
    assert [(r.name, r.state) for r in reopened.ndt_studies] == [
        ("UT desky shora", "ok"), ("UT zespodu", "ok")]


def test_target_picked_on_cut_part_is_stored_for_whole_part():
    session = opened()
    session.set_section_axis("Y", 0)
    top = face_at(session.display_part, 30, -10, 20)
    sid = session.add_ndt_study("UT", [top.wrapped], (30, -10, 20))
    assert state(session, sid).state == "ok"
    on_cut = face_at(session.display_part, 30, 0, 10)  # plocha řezu
    with pytest.raises(DocumentError, match="vznikla jen řezem"):
        session.add_ndt_study("UT", [on_cut.wrapped], (30, 0, 10))


def test_studies_are_evaluated_in_background_process():
    runner = BackgroundRebuilder()
    try:
        session = ModelSession(runner)
        session.open(NDT / "deska.json")
        assert session.wait()
        assert state(session).state == "ok"
        session.set_parameter("t", "30")
        with pytest.raises(DocumentError, match="přepočítává"):
            session.verify_ndt_study("s1", "J. N.")
        assert session.wait()
        assert state(session).state == "stale"
    finally:
        runner.close()


def test_cli_prints_study_states(capsys, tmp_path):
    code = main(["build", str(NDT / "deska.json"), "-o", str(tmp_path), "--format", "step"])
    out = capsys.readouterr().out
    assert code == 0
    assert "NDT studie:\n  ✓ UT desky shora (UT) – platná\n      Neověřeno." in out
    assert "Nenahrazuje kvalifikovaný postup" in out
    main(["build", str(NDT / "deska.json"), "-o", str(tmp_path), "--format", "step",
          "--set", "t=30"])
    out = capsys.readouterr().out
    assert "⚠ UT desky shora (UT) – zastaralá" in out
    assert "Kontrolovaná plocha se posunula o 10.00 mm" in out
