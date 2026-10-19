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


def coverage_session(runner=None):
    from skodacad.ndt.devices import Probe

    session = ModelSession(runner)
    session.open(NDT / "deska.json")
    assert session.wait(30)
    part = session.result.part
    session.set_ndt_target("s1", [face_at(part, 0, 0, 0).wrapped], (0, 0, 0))
    assert session.wait(30)
    session.set_ndt_device("s1", Probe.straight(10))
    assert session.wait(30)
    session.place_ndt_probe("s1", [face_at(session.result.part, 0, 0, 20).wrapped], (0, 0, 20))
    return session


def test_coverage_is_a_view_invalidated_by_part_and_probe_changes(tmp_path):
    session = coverage_session()
    before = session.document.to_dict()
    result = session.compute_ndt_coverage(mode="line", step_mm=10, length_mm=10)
    assert session.ndt_coverage is result
    assert session.document.to_dict() == before
    assert result.area("covered") > 0
    csv = session.export_ndt_coverage(tmp_path / "coverage.csv")
    assert csv.exists()
    session.set_section_axis("X", 0)
    nodes, _, _ = session.visible_ndt_coverage()
    assert nodes and len(nodes) <= 3 * len(result.triangles) * 2
    session.shift_ndt_probe(5)
    assert session.ndt_coverage is None
    session.compute_ndt_coverage(mode="line", step_mm=10, length_mm=0)
    session.set_parameter("t", "30")
    assert session.ndt_coverage is None
    with pytest.raises(DocumentError, match="platnou UT studii"):
        session.compute_ndt_coverage()


def test_face_coverage_step_comparison_and_failed_comparison(monkeypatch):
    import skodacad.session as module
    from skodacad.ndt.coverage import CONVERGENCE_RULE, CoverageError

    session = coverage_session()
    plain = session.compute_ndt_coverage(mode="line", step_mm=10, length_mm=10)
    assert "convergence" not in plain.assumptions
    result = session.compute_ndt_coverage(mode="line", step_mm=10, length_mm=10,
                                          convergence=True)
    found = result.assumptions["convergence"]
    assert found["rule"] == CONVERGENCE_RULE and found["coarse_steps_mm"] == (20, 20)
    assert result.percent("covered") == plain.percent("covered")  # jemný běh se nemění
    assert result.assumptions["convergence_text"] in result.summary()

    def broken(*args, **kwargs):
        raise CoverageError("hrubší běh selhal")

    monkeypatch.setattr(module, "check_convergence", broken)
    result = session.compute_ndt_coverage(mode="line", step_mm=10, length_mm=10,
                                          convergence=True)
    assert "convergence" not in result.assumptions
    assert "Citlivost na krok se nepodařilo ověřit: hrubší běh selhal" in result.summary()


def test_coverage_background_result_and_cancel_do_not_change_model():
    runner = BackgroundRebuilder()
    try:
        session = coverage_session(runner)
        before = session.document.to_dict()
        old_part = session.result.part
        assert session.start_ndt_coverage(mode="line", step_mm=10, length_mm=0,
                                          convergence=True) is None
        assert session.computing and session.ndt_coverage is None
        assert session.wait(40), session.failure
        assert not session.failure
        assert session.ndt_coverage is not None
        assert "convergence" in session.ndt_coverage.assumptions  # i v pomocném procesu
        assert session.result.part is old_part
        session.start_ndt_coverage(step_mm=0.5)
        assert session.cancel()
        assert session.document.to_dict() == before and session.ndt_coverage is None
    finally:
        runner.close()


def test_coverage_cli_csv_and_negative_point_coordinates(tmp_path, capsys):
    from skodacad.ndt import UT_DISCLAIMER

    csv = tmp_path / "coverage.csv"
    assert main(["pokryti", str(NDT / "deska.json"), "--plocha", "-5,0,20", "--prima", "10",
                 "--cil", "-5,0,0", "--rezim", "line", "--delka", "0", "--krok", "5",
                 "--konvergence", "--csv", str(csv)]) == 0
    text = capsys.readouterr().out
    assert UT_DISCLAIMER in text and "Geometricky pokryto: 100.00 %" in text
    assert "Citlivost na krok" in text and csv.exists()
    assert main(["pokryti", str(NDT / "deska.json"), "--plocha", "0,0,20",
                 "--cil", "0,0,0", "--krok", "0"]) == 2


def state(session, study_id="s1"):
    return next(r for r in session.ndt_studies if r.id == study_id)


@pytest.mark.parametrize("path", sorted(NDT.glob("*.json")), ids=lambda p: p.stem)
def test_every_reference_part_has_a_valid_sample_study(path):
    session = ModelSession()
    session.open(path)
    assert session.ndt_studies  # kapsa má i PT studii, díl 9 tři PT studie
    for result in session.ndt_studies:
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
    assert sid == "s4"  # ukázka kapsy má studie s1 (UT), s2 (PT) a s3 (MT)
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
    assert session.ndt_study(sid)["name"] == "RT studie 3"  # deska má UT a MT studii
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
    assert [r.id for r in session.ndt_studies] == ["s1", copy_id, "s2"]  # kopie hned za
    assert state(session, copy_id).name == "UT desky shora (kopie)"
    for sid in ("s1", copy_id, "s2"):
        session.remove_ndt_study(sid)
    assert session.ndt_studies == [] and session.document.ndt is None
    path = session.save(tmp_path / "bez_studii.json")
    assert "ndt" not in json.loads(path.read_text(encoding="utf-8"))
    for _ in range(3):
        session.undo()
    assert [r.id for r in session.ndt_studies] == ["s1", copy_id, "s2"]


def test_study_survives_save_and_reopen(tmp_path):
    session = opened()
    session.add_ndt_study("UT", [face_at(session.result.part, 0, 0, 0).wrapped], (0, 0, 0),
                          "UT zespodu")
    path = session.save(tmp_path / "deska.json")
    reopened = ModelSession()
    reopened.open(path)
    assert [(r.name, r.state) for r in reopened.ndt_studies] == [
        ("UT desky shora", "ok"), ("MT horní plochy", "ok"), ("UT zespodu", "ok")]


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


# --- sonda (etapa 03) -----------------------------------------------------------------------


def test_probe_is_stored_in_study_with_undo(tmp_path):
    from skodacad.ndt.devices import Probe

    session = opened("zebro")
    assert session.ndt_probe("s1") == Probe.angle()  # bez sondy ve studii = výchozí
    session.verify_ndt_study("s1", "J. N.")
    session.set_ndt_device("s1", {"kind": "straight", "diameter": 12})
    assert session.ndt_study("s1")["device"] == {"kind": "straight", "diameter": 12,
                                                 "height": 25, "bounces": 0,
                                                 "max_gap": 0.5, "reserve": 0}
    assert "verified" not in session.ndt_study("s1")  # sonda je zadání studie
    assert session.ndt_probe("s1") == Probe.straight(12)
    path = session.save(tmp_path / "zebro.json")
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 20
    session.undo()
    assert "device" not in session.ndt_study("s1")
    with pytest.raises(DocumentError, match="Průměr sondy musí být číslo"):
        session.set_ndt_device("s1", {"kind": "straight", "diameter": 0})


def test_probe_placement_is_a_view_that_follows_the_part():
    session = opened("zebro")
    top = face_at(session.result.part, 60, 0, 20)
    placed = session.place_ndt_probe("s1", [top.wrapped], (22, 0, 20), angle=180)
    assert placed.ok and placed.clearance == pytest.approx(5)  # paprsek k žebru (−X)
    assert session.ndt_placement is placed  # podruhé z paměti
    assert session.ndt_beam is not None and session.ndt_beam.ok
    assert session.ndt_beam.half_skip == pytest.approx(20.0)
    document_before = session.document.to_dict()
    session.set_parameter("s", "14")  # tlustší žebro (bok x = 7) → volno 3 mm
    assert session.ndt_placement.clearance == pytest.approx(3)
    session.set_ndt_device("s1", {"kind": "angle", "reserve": 5})
    assert session.ndt_placement.state == "tight"
    session.turn_ndt_probe(0)  # paprsek od žebra: sonda se k němu otočí zadním koncem
    assert session.ndt_placement.state == "collision"  # zadní konec (28 mm) v žebru
    session.undo()
    session.undo()
    assert session.document.to_dict() == document_before  # přiložení se do modelu nepíše
    session.clear_ndt_placement()
    assert session.ndt_placement is None and session.ndt_beam is None


def test_probe_placement_errors():
    session = opened("zebro")
    part = session.result.part
    with pytest.raises(DocumentError, match="právě jednu plochu"):
        session.place_ndt_probe("s1", [part.edges()[0].wrapped])
    with pytest.raises(DocumentError, match="„x“ v modelu není"):
        session.place_ndt_probe("x", [face_at(part, 60, 0, 20).wrapped])
    session.place_ndt_probe("s1", [face_at(part, 60, 0, 20).wrapped], (60, 0, 20))
    session.remove_ndt_study("s1")
    assert session.ndt_placement is None
    assert session.ndt_placement_error == "Studie se sondou už v modelu není."
    session.open(NDT / "deska.json")
    assert session.ndt_placement_request is None  # nový model = bez sondy


def test_cli_probe(capsys):
    assert main(["sonda", str(NDT / "zebro.json"), "--bod", "22,0,20", "--smer", "-1,0,0",
                 "--posun", "-1,0,0", "--delka", "10"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[:5] == [
        "Úhlová sonda 40 × 20 × 25 mm, výstupní bod 12 mm od čela (mezera nejvýš 0.50 mm, "
        "rezerva 0.00 mm)",
        "Přiložení v [22; 0; 20], paprsek [-1; 0; 0]:",
        "  Přiloženo. Mezera pod sondou 0.00 mm, volno k překážkám 5.00 mm.",
        "Posun směrem [-1; 0; 0] o 10 mm po 1 mm: volně 0–5 mm",
        "  první potíž po 6 mm: Koliduje. Průnik těla sondy s dílem 500 mm³.",
    ]
    assert main(["sonda", str(NDT / "trubka.json"), "--bod", "0,0,57.15", "--prima", "20"]) == 0
    out = capsys.readouterr().out
    assert "Přiložení v [0; 0; 57.15]" in out and "Nedosedá. Mezera pod sondou 0.88 mm" in out
    assert main(["sonda", str(NDT / "zebro.json"), "--bod", "22,0,20", "--smer", "-1,0,0",
                 "--studie", "s1", "--rezerva", "5", "--celo", "15"]) == 0
    assert "Málo místa. Volno jen 2.00 mm" in capsys.readouterr().out
    assert main(["sonda", str(NDT / "zebro.json"), "--bod", "22,0,20", "--uhlova", "40x20"]) == 2
    assert "délka x šířka x výška" in capsys.readouterr().err
    assert main(["sonda", str(NDT / "zebro.json"), "--bod", "22,0,40"]) == 2
    assert "od povrchu dílu" in capsys.readouterr().err


# --- ruční pohyb sondy (etapa 05) -----------------------------------------------------------


def test_probe_move_shift_and_line_scan_on_zebro():
    session = opened("zebro")
    top = face_at(session.result.part, 60, 0, 20)
    with pytest.raises(DocumentError, match="Sonda není přiložená"):
        session.shift_ndt_probe(1)
    with pytest.raises(DocumentError, match="Sonda není přiložená"):
        session.scan_ndt_line(10)
    with pytest.raises(DocumentError, match="Čára posuvu není spočítaná"):
        session.select_ndt_scan_index(0)

    session.place_ndt_probe("s1", [top.wrapped], (22, 0, 20), angle=180)
    moved = session.move_ndt_probe(None, [top.wrapped], (20, 0, 20))
    assert moved.origin == pytest.approx((20, 0, 20))
    assert moved.clearance == pytest.approx(3)  # zachovalo studii s1 i úhel 180°

    shifted = session.shift_ndt_probe(5)  # +5 mm ve směru paprsku (−X) → x = 15 → kolize s žebrem
    assert shifted.origin == pytest.approx((15, 0, 20))
    assert shifted.state == "collision"
    back = session.shift_ndt_probe(-7)  # −7 mm dozadu (+X) → x = 22
    assert back.origin == pytest.approx((22, 0, 20))
    assert back.ok
    with pytest.raises(DocumentError, match="mimo plochu"):
        session.shift_ndt_probe(-200)
    assert session.ndt_placement.origin == pytest.approx((22, 0, 20))  # neplatný posun nic nemění

    scan = session.scan_ndt_line(length=10, step=1)
    assert session.ndt_line_scan is scan
    assert scan.free_ranges == ((0, 5),)
    assert "Volně: 0–5 mm. První potíž po 6 mm: Koliduje." in scan.summary
    at_collision = session.select_ndt_scan_index(6)
    assert session.ndt_scan_index == 6
    assert at_collision.state == "collision"
    assert session.ndt_line_scan is scan  # posun po čáře čáru nesmaže
    with pytest.raises(DocumentError, match="mimo rozsah"):
        session.select_ndt_scan_index(99)
    session.turn_ndt_probe(90)
    assert session.ndt_line_scan is None  # natočení sondy čáru zruší


def test_probe_move_across_reference_parts():
    # tupý svar: posun úhlové sondy 60° s 1 odrazem ukáže přechod přímého a odraženého paprsku
    svar = opened("tupy_svar")
    svar.set_ndt_device("s1", {"kind": "angle", "beam_angle": 60, "bounces": 1})
    top = face_at(svar.result.part, -40, 0, 12)
    svar.place_ndt_probe("s1", [top.wrapped], (-45, 0, 12), angle=0)
    assert svar.ndt_beam.ok and len(svar.ndt_beam.legs) == 2
    svar.shift_ndt_probe(20)  # blíž ke svaru (x = -25)
    assert svar.ndt_placement.origin == pytest.approx((-25, 0, 12))
    assert svar.ndt_beam.ok and svar.ndt_beam.legs[0].end[2] == pytest.approx(0)

    # trubka: kolmá sonda Ø20 nedosedá, Ø6 dosedá i po posunu po plášti
    trubka = opened("trubka")
    outer = face_at(trubka.result.part, 0, 0, 57.15)
    trubka.set_ndt_device("s1", {"kind": "straight", "diameter": 20})
    placed = trubka.place_ndt_probe("s1", [outer.wrapped], (0, 0, 57.15))
    assert placed.state == "lift_off"
    trubka.set_ndt_device("s1", {"kind": "straight", "diameter": 6})
    assert trubka.ndt_placement.ok
    shifted = trubka.shift_ndt_probe(15)
    assert shifted.ok and trubka.ndt_beam.ok

    # kapsa: na dně kapsy Ø20 uprostřed sedí, po posunu narazí do stěny; zespodu dráha 15 → 40 mm
    kapsa = opened("kapsa")
    kapsa.set_ndt_device("s1", {"kind": "straight", "diameter": 20})
    floor = face_at(kapsa.result.part, 0, 0, 15)
    assert kapsa.place_ndt_probe("s1", [floor.wrapped], (0, 0, 15), angle=0).ok
    assert kapsa.shift_ndt_probe(14).state == "collision"
    bottom = face_at(kapsa.result.part, 0, 0, 0)
    kapsa.move_ndt_probe("s1", [bottom.wrapped], (0, 0, 0), angle=0)
    assert kapsa.ndt_beam.legs[0].length == pytest.approx(15)
    kapsa.move_ndt_probe("s1", [bottom.wrapped], (40, 0, 0), angle=0)
    assert kapsa.ndt_beam.legs[0].length == pytest.approx(40)

