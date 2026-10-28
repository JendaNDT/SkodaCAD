"""P1.4 E.2: model, vazba studie a původ výsledku jsou oddělené podmínky."""

import copy
import pickle
from dataclasses import replace
from types import SimpleNamespace

import pytest

from conftest import EXAMPLES, box_features, face_at, make_doc
from skodacad import DocumentError, rebuild
from skodacad.cli import main
from skodacad.ndt import PT_DISCLAIMER
from skodacad.ndt.devices import Probe
from skodacad.ndt.pt import PtSettings
from skodacad.ndt.study import new_study, part_fingerprint
from skodacad.rebuild import part_problem
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder, decode_result, encode_result
from test_ndt_welds import volume_target


def ndt_document(*, failed=False, kind="faces"):
    doc = make_doc(box_features(20, 30, "h"), {"h": 40})
    if failed:
        doc.features += [
            {"id": "bad", "type": "fillet", "edges": "all", "radius": 50},
            {"id": "tail", "type": "chamfer", "edges": "all", "distance": 1}]
    target = {"kind": "faces", "faces": [
        {"face": {"at": [0, 0, 40], "normal": [0, 0, 1], "type": "plane"}}]}
    if kind == "volume":
        target = volume_target(profile_mm=[[0, 0], [5, 0], [5, 5], [0, 5]])
    studies = []
    for method in ("UT", "PT", "MT", "RT"):
        studies.append(new_study(method, studies, part_fingerprint(doc), target))
    doc.ndt = {"studies": studies}
    doc.ndt["studies"][1]["pt"] = replace(PtSettings(), step_mm=10).to_dict()
    return doc


def opened(tmp_path, *, failed=False, kind="faces"):
    source = tmp_path / "model.json"
    ndt_document(failed=failed, kind=kind).save(source)
    session = ModelSession()
    session.open(source)
    return session


@pytest.mark.parametrize("kind", ["faces", "volume"])
def test_failed_history_never_validates_targets_or_computes_thickness(tmp_path, monkeypatch, kind):
    import importlib

    module = importlib.import_module("skodacad.rebuild")

    def forbidden(*args, **kwargs):
        pytest.fail("Mapa tloušťky se na neúplném tělese nesmí ani spustit")

    monkeypatch.setattr(module, "compute_map", forbidden)
    doc = ndt_document(failed=True, kind=kind)
    result = rebuild(doc, with_map=True)
    assert result.part.is_valid and result.part.volume == pytest.approx(24000)
    assert result.map_error == part_problem(result) and result.thickness_map is None
    assert len(result.ndt) == 4
    for study in result.ndt:
        assert study.state == "broken" and "[bad]" in study.messages[0]
        assert study.faces == 0 and study.volume_mm3 == study.requested_volume_mm3 == 0
        assert study.verified == "Neověřeno."
    payload = encode_result(result)
    assert len(payload) == 10 and payload["model_signature"] == result.model_signature
    copied = decode_result(pickle.loads(pickle.dumps(payload)))
    assert copied.ndt == result.ndt and copied.map_error == result.map_error


# Vstupy vycházejí ze skutečného kvádru a uložených studií. Každá cesta musí
# hlásit chybu receptu dřív, než řeší chybějící mapu/sondu nebo spouští algoritmus.
OPERATIONS = [
    ("confirm_ndt_study", ("s2",)), ("verify_ndt_study", ("s2", "Zkušební záznam")),
    ("ndt_pt_estimate", ("s2",)), ("compute_ndt_pt", ("s2",)), ("start_ndt_pt", ("s2",)),
    ("ndt_mt_estimate", ("s3",)), ("compute_ndt_mt", ("s3",)), ("start_ndt_mt", ("s3",)),
    ("ndt_rt_estimate", ("s4",)), ("compute_ndt_rt", ("s4",)), ("start_ndt_rt", ("s4",)),
    ("compute_ndt_coverage", ()), ("start_ndt_coverage", ()),
    ("ndt_access_estimate", ("s1",)), ("compute_ndt_access", ("s1",)),
    ("start_ndt_access", ("s1",)), ("ndt_plan_estimate", ("s1",)),
    ("compute_ndt_plan", ("s1",)), ("check_ndt_plan", ("s1",)),
    ("start_ndt_plan", ("s1",)), ("start_ndt_plan_check", ("s1",)),
    ("ndt_audit_items", ()), ("compute_ndt_audit", ()), ("start_ndt_audit", ()),
    ("compute_ndt_design", ()), ("ndt_design_estimate", ()), ("start_ndt_design", ()),
    ("apply_ndt_design_variant", (1,)),
]


@pytest.mark.parametrize(("method", "args"), OPERATIONS)
def test_every_ndt_entry_rejects_partial_model_without_mutating_it(tmp_path, method, args):
    session = opened(tmp_path, failed=True)
    before = copy.deepcopy((session.document, session._undo, session._redo, session.path,
                            session.dirty))
    with pytest.raises(DocumentError, match=r"\[bad\].*R50"):
        getattr(session, method)(*args)
    assert (session.document, session._undo, session._redo, session.path, session.dirty) == before
    assert not session.computing


EXPORTS = ["export_thickness_map", "export_ndt_coverage", "export_ndt_pt", "export_ndt_mt",
           "export_ndt_rt", "export_ndt_access", "export_ndt_plan", "export_ndt_audit",
           "export_ndt_design"]


@pytest.mark.parametrize("method", EXPORTS)
def test_no_ndt_output_is_created_or_overwritten_on_partial_model(tmp_path, method):
    session = opened(tmp_path, failed=True)
    path = tmp_path / "sentinel"
    path.write_bytes(b"puvodni vysledek")
    with pytest.raises(DocumentError, match=r"\[bad\]"):
        getattr(session, method)(path)
    assert path.read_bytes() == b"puvodni vysledek"
    assert {p.name for p in tmp_path.iterdir()} == {"model.json", "sentinel"}
    with pytest.raises(DocumentError, match=r"\[bad\]"):
        session.export_ndt_rt_png("P1", path)
    with pytest.raises(DocumentError, match=r"\[bad\]"):
        session.save_ndt_design_variant(1, path)


def test_old_real_maps_stay_hidden_after_failed_rebuild_and_fresh_results_recover(tmp_path):
    session = opened(tmp_path)
    session.show_thickness_map(True)
    assert session.thickness_map is not None
    pt = session.compute_ndt_pt("s2")
    assert session.ndt_pt_map is pt
    old_result = session.result
    runner = SimpleNamespace(submit=lambda *args, **kwargs: 10)
    session._runner = runner
    session.set_parameter("h", "50")
    runner.poll = lambda: SimpleNamespace(job=10, update=None, result=None, error="Worker spadl")
    session.poll()
    assert session.result is old_result and old_result.ok
    assert session.ndt_pt_map is None and session.thickness_map is None
    assert session.ndt_placement is None and session.ndt_target_preview("s1") is None
    assert all(s.state == "broken" for s in session.ndt_studies)
    assert all("předchozímu stavu" in s.messages[0] for s in session.ndt_studies)
    with pytest.raises(DocumentError, match="předchozímu stavu"):
        session.export_ndt_pt(tmp_path / "old.csv")
    session._runner = None
    session.rebuild()
    assert session.ndt_pt_map is None
    with pytest.raises(DocumentError, match="zastaralá"):
        session.compute_ndt_pt("s2")
    session.confirm_ndt_study("s2")
    fresh = session.compute_ndt_pt("s2")
    assert fresh is not pt and session.ndt_pt_map is fresh
    session.export_ndt_pt(tmp_path / "fresh.csv")
    assert not (tmp_path / "old.csv").exists()


@pytest.mark.parametrize("kind", ["coverage", "mt", "rt", "audit", "access", "plan", "design"])
def test_each_real_result_cannot_reappear_after_worker_failure(tmp_path, kind):
    from test_ndt_audit_session import quick_plate
    from test_ndt_mt_session import opened as mt_opened
    from test_ndt_mt_session import quick as mt_quick
    from test_ndt_session import coverage_session

    if kind in ("coverage", "access", "plan"):
        session = coverage_session()
        if kind == "coverage":
            result = session.compute_ndt_coverage(mode="line", length_mm=0, step_mm=20)
            getter = "ndt_coverage"
        elif kind == "access":
            result = session.compute_ndt_access("s1", {"step_mm": 50,
                "target_step_mm": 50, "direction_step_deg": 90, "bounces": (0,)})
            getter = "ndt_access"
        else:
            result = session.compute_ndt_plan("s1", options={"row_step_mm": 40,
                "check_step_mm": 5})
            getter = "ndt_plan_result"
    elif kind == "mt":
        session = mt_quick(mt_opened())
        result = session.compute_ndt_mt("s2")
        getter = "ndt_mt_map"
    elif kind in ("rt", "audit"):
        session = quick_plate()
        if kind == "rt":
            result = session.compute_ndt_rt("s2")
            getter = "ndt_rt_map"
        else:
            result = session.compute_ndt_audit(include=["s2"])
            getter = "ndt_audit"
    else:
        session = ModelSession()
        session.open(EXAMPLES / "ndt" / "navrh_kapsa.json")
        result = session.compute_ndt_design({"study": "s3",
            "parameters": [{"name": "a", "values": [90]}],
            "options": {"verify": False, "rejected": False}})
        getter = "ndt_design"
    assert getattr(session, getter) is result
    before = session.result
    runner = SimpleNamespace(submit=lambda *args, **kwargs: 42)
    session._runner = runner
    parameter, value = ("a", "80") if kind == "design" else ("t", "30")
    session.set_parameter(parameter, value)
    runner.poll = lambda: SimpleNamespace(job=42, update=None, result=None, error="Worker spadl")
    assert session.poll() and not session.computing
    assert session.result is before and before.ok
    assert getattr(session, getter) is None
    assert session.model_problem and session.ndt_plan_drawing("s1") == (None, None)
    assert session.ndt_rt_drawing("s2", "P1") is None


def test_incomplete_confirmation_is_rejected_and_stale_study_does_not_block_geometry(tmp_path):
    session = opened(tmp_path)
    sid = session.add_ndt_study("PT")
    before = session.document.to_dict()
    with pytest.raises(DocumentError, match="neúplná"):
        session.confirm_ndt_study(sid)
    assert session.document.to_dict() == before
    session.set_parameter("h", "50")
    assert session.result.ok and session.ndt_studies[1].state == "stale"
    assert session.export(tmp_path / "good.step").exists()
    with pytest.raises(DocumentError, match="zastaralá"):
        session.compute_ndt_pt("s2")
    audit = session.compute_ndt_audit(include=["s2"])
    entry = audit.entry("s2")
    assert entry.status == "unavailable" and entry.places == []
    assert "zastaralá" in entry.reason
    paths = session.export_ndt_audit(tmp_path / "audit")
    assert any(p.name == "zprava.html" for p in paths)
    html = (tmp_path / "audit" / "zprava.html").read_text(encoding="utf-8")
    assert PT_DISCLAIMER in html
    assert not any(p.name.startswith("studie-s2") for p in paths)


@pytest.mark.parametrize("operation", ["target", "probe", "yoke", "projection", "volume"])
def test_geometry_picks_cannot_anchor_a_study_to_partial_body(tmp_path, operation):
    session = opened(tmp_path, failed=True)
    top = face_at(session.result.part, 0, 0, 40)
    before = session.document.to_dict()
    calls = {
        "target": lambda: session.set_ndt_target("s2", [top.wrapped], (0, 0, 40)),
        "probe": lambda: session.place_ndt_probe("s1", [top.wrapped], (0, 0, 40)),
        "yoke": lambda: session.place_ndt_yoke("s3", (0, 0, 40), 0),
        "projection": lambda: session.ndt_rt_projection_at("s4", (0, 0, 40)),
        "volume": lambda: session.check_ndt_volume_target(volume_target()),
    }
    with pytest.raises(DocumentError, match=r"\[bad\]"):
        calls[operation]()
    assert session.document.to_dict() == before
    assert session.ndt_placement_request is None and session.ndt_yoke is None


def test_late_reply_from_replaced_job_cannot_restore_old_result_or_map(tmp_path):
    session = opened(tmp_path)
    old_result = session.result
    old_map = session.compute_ndt_pt("s2")
    assert session.ndt_pt_map is old_map
    jobs = iter((41, 42))
    runner = SimpleNamespace(submit=lambda *args, **kwargs: next(jobs))
    session._runner = runner
    session.set_parameter("h", "45")
    obsolete = rebuild(session.document)
    session.set_parameter("h", "50")
    actual = rebuild(session.document)
    replies = iter((SimpleNamespace(job=41, update=None, result=obsolete, error=""),
                    SimpleNamespace(job=42, update=None, result=actual, error="")))
    runner.poll = lambda: next(replies)
    assert not session.poll() and session.computing
    assert session.result is old_result and session.ndt_pt_map is None
    assert session.poll() and not session.computing
    assert session.result is actual and session.result.parameters["h"] == 50
    assert session.ndt_pt_map is None


@pytest.mark.parametrize("command", [
    ["paprsek", "--z", "0,0,50", "--smer", "0,0,-1"],
    ["sonda", "--bod", "0,0,40", "--prima", "5"],
    ["pokryti", "--plocha", "0,0,40", "--prima", "5", "--cil", "0,0,0"],
])
def test_direct_cli_ndt_commands_never_use_partial_body(tmp_path, capsys, command):
    session = opened(tmp_path, failed=True)
    args = [command[0], str(session.path), *command[1:]]
    if command[0] == "pokryti":
        args += ["--csv", str(tmp_path / "out.csv")]
    assert main(args) == 2
    out = capsys.readouterr()
    assert "[bad]" in out.err and "R50" in out.err
    assert "celkem v materiálu" not in out.out and "Předpoklady:" not in out.out
    assert not (tmp_path / "out.csv").exists()


@pytest.mark.parametrize("device_study", [False, True])
def test_successful_one_off_cli_uses_overridden_recipe_fingerprint(tmp_path, capsys, device_study):
    session = opened(tmp_path)
    session.set_ndt_device("s1", Probe.straight(5))
    session.save()
    original = session.path.read_bytes()
    assert main(["paprsek", str(session.path), "--set", "h=50", "--z", "0,0,60",
                 "--smer", "0,0,-1"]) == 0
    assert "celkem v materiálu: 50.00 mm" in capsys.readouterr().out
    args = ["pokryti", str(session.path), "--set", "h=50", "--plocha", "0,0,50",
                 "--prima", "5", "--cil", "0,0,0", "--delka", "0", "--krok", "10",
                 "--csv", str(tmp_path / "one-off.csv")]
    if device_study:
        args += ["--studie", "s1"]
    assert main(args) == 0
    out = capsys.readouterr().out
    expected = part_fingerprint(session.document.with_parameters({"h": 50}))
    assert expected in out and "jednorázové zadání" in out and "'study_id': None" in out
    if device_study:
        assert "'device_study_id': 's1'" in out
    assert session.path.read_bytes() == original


def test_actual_spawn_keeps_failed_history_diagnostic_and_recovers(tmp_path):
    with_runner = BackgroundRebuilder()
    try:
        source = tmp_path / "worker.json"
        ndt_document(failed=True).save(source)
        session = ModelSession(with_runner)
        session.open(source)
        assert session.wait(30)
        assert session.result.part.volume == pytest.approx(24000)
        assert all(s.state == "broken" for s in session.ndt_studies)
        with pytest.raises(DocumentError, match="Model není dokončený"):
            session.confirm_ndt_study("s2")
        fixed = session.feature("bad")
        fixed["radius"] = 2
        # Konec historie se záměrně odstraní, aby oprava netestovala jiné sražení.
        session.delete_feature("tail")
        session.update_feature("bad", fixed)
        assert session.wait(30) and session.result.ok
        assert session.ndt_studies[1].state == "stale"
        session.confirm_ndt_study("s2")
        assert session.wait(30) and session.ndt_studies[1].state == "ok"
    finally:
        with_runner.close()
