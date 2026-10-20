"""Předběžný NDT audit v ModelSession (etapa 14, krok 14A.2): co se spočítá, výpočet jako
pohled, nedostupné studie, mapa tloušťky, výsledek UT ze sezení, pozadí se zastavením, CLI
(``docs/ndt/25-navrh-etapa-14.md``)."""

import dataclasses
import math

import pytest

from conftest import EXAMPLES, face_at
from skodacad import DocumentError
from skodacad.cli import main
from skodacad.ndt.audit import SKIPPED_BY_USER, STOPPED, STUDY_PROBLEMS, TITLE
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder

NDT = EXAMPLES / "ndt"
PLATE = 200 * 100 - math.pi * 10**2  # horní plocha desky s otvorem Ø 20 [mm²]


def quick_plate(runner=None):
    """Deska s otvorem, RT studie s hrubou sítí (pár sekund)."""
    session = ModelSession(runner)
    session.open(NDT / "otvor.json")
    assert session.wait(60)
    settings = session.ndt_rt_settings("s2")
    session.set_ndt_rt_settings("s2", dataclasses.replace(settings, step_mm=10,
                                                          image_step_mm=20))
    assert session.wait(60)
    return session


@pytest.fixture(scope="module")
def plate():
    return quick_plate()


def test_items_say_what_runs_and_why_not(plate):
    ut, rt = plate.ndt_audit_items()
    assert (ut.study_id, ut.status) == ("s1", "skipped") and "nemá plán dráhy" in ut.reason
    assert (rt.status, rt.action) == ("ready", "rt") and rt.seconds > 0
    assert "2, asi" in rt.source and "– asi" in rt.text()
    ut, rt = plate.ndt_audit_items(include=["s1"])
    assert (rt.status, rt.reason) == ("skipped", SKIPPED_BY_USER)
    with pytest.raises(DocumentError, match="s9 v modelu není"):
        plate.ndt_audit_items(include=["s9"])
    with pytest.raises(DocumentError, match="jen u UT studie"):
        plate.ndt_audit_items(access=["s2"])


def test_audit_is_a_view_and_adopts_the_map(plate, tmp_path):
    before, undo = plate.document.to_dict(), len(plate._undo)
    progress = []
    audit = plate.compute_ndt_audit(operator="J. N.",
                                    progress=lambda *step: progress.append(step))
    assert plate.document.to_dict() == before and len(plate._undo) == undo
    assert plate.ndt_audit is audit and audit.complete and audit.operator == "J. N."
    assert [e.status for e in audit.entries] == ["skipped", "done"]
    entry = audit.entry("s2")
    assert [round(p.center[1]) for p in entry.places] == [-49, 49]  # okraje mimo film
    assert entry.target == "1 plocha" and entry.study_state == "platná"
    assert entry.record == plate.ndt_study("s2")
    assert [step[:2] for step in progress if step[3] is None] == [(0, 2), (1, 2)]
    assert any(step[3] is not None for step in progress)  # průběh uvnitř studie
    assert plate.adopt_ndt_audit_map("s2") and plate.ndt_rt_map is entry.result
    assert not plate.adopt_ndt_audit_map("s1")  # neprovedená studie mapu nemá
    names = sorted(p.name for p in plate.export_ndt_audit(tmp_path / "audit"))
    assert names == ["mista.csv", "studie-s2-rt.csv", "zprava.html"]
    assert TITLE in (tmp_path / "audit" / "zprava.html").read_text(encoding="utf-8")


def test_changed_part_drops_audit_and_stale_study_is_unavailable():
    session = quick_plate()
    session.compute_ndt_audit(include=["s2"])
    session.set_parameter("t", "25")
    assert session.ndt_audit is None
    with pytest.raises(DocumentError, match="spusť předběžný NDT audit"):
        session.export_ndt_audit("nikam")
    ut, rt = session.ndt_audit_items()
    assert rt.status == "unavailable" and rt.reason == STUDY_PROBLEMS["stale"]
    assert "sám nepotvrzuje" in rt.reason
    session.confirm_ndt_study("s2")
    settings = session.ndt_rt_settings("s2")
    session.set_ndt_rt_settings("s2", dataclasses.replace(settings, projections=()))
    rt = session.ndt_audit_items()[1]
    assert rt.status == "unavailable" and "nemá projekci" in rt.reason
    entry = session.compute_ndt_audit().entry("s2")
    assert (entry.status, entry.places) == ("unavailable", [])


def test_thickness_map_only_with_limit():
    session = ModelSession()
    session.open(NDT / "otvor.json")
    session.set_map_setting("step", "10")
    item = session.ndt_audit_items()[-1]
    assert (item.study_id, item.status) == ("tl", "skipped")
    assert "nemá nastavenou mez" in item.reason
    session.set_map_setting("limit", "21")
    item = session.ndt_audit_items(include=["tl"])[-1]
    assert (item.status, item.action) == ("ready", "thickness")
    entry = session.compute_ndt_audit(include=["tl"]).entry("tl")
    below = [p for p in entry.places if p.group == "blocked"]
    assert len(below) == 2 and sum(p.amount for p in below) == pytest.approx(2 * PLATE, rel=1e-3)


def test_ut_result_from_this_session_is_used():
    from skodacad.ndt.devices import Probe

    session = ModelSession()
    session.open(NDT / "deska.json")
    session.set_ndt_target("s1", [face_at(session.result.part, 0, 0, 0).wrapped], (0, 0, 0))
    session.set_ndt_device("s1", Probe.straight(10))
    session.place_ndt_probe("s1", [face_at(session.result.part, 0, 0, 20).wrapped], (0, 0, 20))
    coverage = session.compute_ndt_coverage(mode="line", step_mm=10, length_mm=10)
    item = session.ndt_audit_items(include=["s1"])[0]
    assert (item.status, item.action) == ("ready", "session") and item.seconds == 0
    assert "mapa pokrytí spočítaná v tomto sezení z polohy sondy (0; 0; 20) mm" in item.source
    entry = session.compute_ndt_audit(include=["s1"]).entry("s1")
    assert entry.status == "done" and entry.result is coverage
    assert entry.layer.percent("covered") == pytest.approx(coverage.percent("covered"))
    assert session.adopt_ndt_audit_map("s1")


def test_audit_in_background_streams_studies_and_stops():
    runner = BackgroundRebuilder()
    try:
        session = quick_plate(runner)
        assert session.start_ndt_audit(operator="J. N.") is None
        assert session.audit_pending and session.ndt_audit is None
        assert session.wait(120)
        audit = session.ndt_audit
        assert audit.complete and [e.status for e in audit.entries] == ["skipped", "done"]
        assert len(audit.entry("s2").places) == 2 and audit.operator == "J. N."
        assert session.ndt_rt_map is None  # mapa vznikla v pomocném procesu
        assert session.adopt_ndt_audit_map("s2")
        assert session.ndt_rt_map is audit.entry("s2").result
        session.start_ndt_audit()
        assert session.cancel()
        stopped = session.ndt_audit
        assert not stopped.complete and not session.audit_pending
        assert [(e.status, e.reason) for e in stopped.entries][1] == ("skipped", STOPPED)
        assert "nemá plán dráhy" in stopped.entries[0].reason  # zapsané hned zůstane
    finally:
        runner.close()


def test_cli_audit_folder_and_errors(tmp_path, capsys):
    session = quick_plate()
    model = tmp_path / "deska.json"
    session.save(model)
    folder = tmp_path / "zprava"
    assert main(["audit", str(model), "--slozka", str(folder), "--zpracovatel", "J. N."]) == 0
    out, err = capsys.readouterr()
    assert TITLE in out and "S2-01 Nepromítne se" in out and "Zpracoval(a): J. N." in out
    assert "Co audit spočítá:" in err and "Odhad celkem: asi" in err
    assert sorted(p.name for p in folder.iterdir()) == ["mista.csv", "studie-s2-rt.csv",
                                                       "zprava.html"]
    assert main(["audit", str(model), "--studie", "s7"]) == 2
    assert "s7 v modelu není" in capsys.readouterr().err
