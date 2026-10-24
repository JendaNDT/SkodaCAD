"""P1.4 E.3: viditelná chyba, obnovení práce a offline diagnostika asistenta."""

import sys
import time
from types import SimpleNamespace

import pytest
from build123d import import_step

from conftest import EXAMPLES, face_at
from skodacad import DocumentError
from skodacad.assistant import ModelTools, build_report
from skodacad.gui.main_window import MainWindow
from skodacad.worker import BackgroundRebuilder
from test_gui import FakeViewer, edit
from test_output_ndt import ndt_document, opened

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtTest import QTest  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def guarded_window(app, tmp_path, monkeypatch):
    errors, messages = [], []
    monkeypatch.setattr(sys, "excepthook", lambda kind, value, tb: errors.append(value))
    for name in ("information", "warning", "critical", "about"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name,
                            lambda *a, **k: messages.append(str(a[2])))
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Discard)
    for name in ("getText", "getItem", "getMultiLineText"):
        monkeypatch.setattr(QtWidgets.QInputDialog, name, lambda *a, **k: ("", False))
    for name in ("getSaveFileName", "getOpenFileName"):
        monkeypatch.setattr(QtWidgets.QFileDialog, name, lambda *a, **k: ("", ""))
    monkeypatch.setattr(QtWidgets.QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    monkeypatch.setattr(MainWindow, "_exec_dialog", lambda *a: 0)
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=EXAMPLES, user_dir=tmp_path)
    w.test_errors, w.test_messages = errors, messages
    yield w
    w.session.dirty = False
    w.close()
    assert errors == []


def open_bad(w, tmp_path, kind="faces"):
    doc = ndt_document(kind=kind)
    doc.parameters["r"] = 50
    doc.features.append({"id": "bad", "type": "fillet", "edges": "all", "radius": "r"})
    source = tmp_path / "bad.json"
    doc.save(source)
    assert w.open_model(source)
    return source


@pytest.mark.parametrize("kind", ["faces", "volume"])
def test_partial_model_has_persistent_warning_and_unavailable_outputs(guarded_window, tmp_path,
                                                                     kind):
    w = guarded_window
    open_bad(w, tmp_path, kind)
    w.ndt_panel.select("s2")
    assert not w.error_label.isHidden() and "[bad]" in w.error_label.text()
    assert "Diagnostický náhled" in w.props_label.text()
    assert "24 000 mm³" in w.props_label.text()
    assert "kontrolovaná oblast: nelze vyhodnotit" in w.ndt_panel.details.text()
    assert "0 ploch" not in w.ndt_panel.details.text()
    assert len(w.export_actions) == 3 and not any(a.isEnabled() for a in w.export_actions)
    assert not w.ndt_panel.confirm_action.isEnabled()
    assert not w.ndt_panel.verify_action.isEnabled()
    assert not w.ndt_panel.pt_action.isEnabled()
    assert not w.audit_panel.run_action.isEnabled()
    assert not w.audit_panel.refresh_action.isEnabled()
    assert w.save_action.isEnabled() and w.save_as_action.isEnabled()
    assert w.ndt_panel.rename_action.isEnabled() and w.ndt_panel.note_action.isEnabled()
    w._refresh_all()
    assert not w.error_label.isHidden() and "[bad]" in w.error_label.text()


def test_export_handlers_refuse_before_opening_file_dialog(guarded_window, tmp_path, monkeypatch):
    w = guarded_window
    open_bad(w, tmp_path)
    w.session.set_section_axis("Z", 20)
    w._refresh_all()
    assert w.session.section is not None and not w.export_section_action.isEnabled()

    def forbidden(*args, **kwargs):
        pytest.fail("Souborový dialog se při chybě modelu nesmí otevřít")

    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", forbidden)
    for fmt in ("step", "stl", "3mf", "glb", "svg"):
        w.export_dialog(fmt)
    w.export_section()
    assert len(w.test_messages) == 6
    assert all("[bad]" in message and "R50" in message for message in w.test_messages)
    assert {p.name for p in tmp_path.iterdir() if p.is_file()} == {"bad.json"}


def test_parameter_repair_undo_redo_and_explicit_study_confirmation(guarded_window, tmp_path):
    w = guarded_window
    open_bad(w, tmp_path)
    edit(w, "r", "2")
    assert w.session.result.ok and not w.session.model_problem
    assert w.error_label.isHidden() and all(a.isEnabled() for a in w.export_actions)
    assert "Diagnostický" not in w.props_label.text()
    w.ndt_panel.select("s2")
    assert w.ndt_panel.current().state == "stale"
    assert w.ndt_panel.confirm_action.isEnabled() and not w.ndt_panel.verify_action.isEnabled()
    w.undo_action.trigger()
    assert "[bad]" in w.error_label.text() and not w.error_label.isHidden()
    assert not any(a.isEnabled() for a in w.export_actions)
    w.redo_action.trigger()
    assert not w.session.model_problem and all(a.isEnabled() for a in w.export_actions)
    w.ndt_panel.select("s2")
    w.ndt_panel.confirm_action.trigger()
    assert w.ndt_panel.current().state == "ok" and w.ndt_panel.current().verified == "Neověřeno."
    assert w.ndt_panel.pt_action.isEnabled()
    assert "verified" not in w.session.ndt_study("s2")
    assert w.test_messages == []


def test_bad_recipe_can_be_saved_as_copy_reopened_and_repaired(guarded_window, tmp_path,
                                                             monkeypatch):
    w = guarded_window
    source = open_bad(w, tmp_path)
    original = source.read_bytes()
    destination = tmp_path / "copy.json"
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(destination), ""))
    w.save_as_action.trigger()
    assert destination.is_file() and source.read_bytes() == original
    assert w.open_model(destination) and "[bad]" in w.error_label.text()
    edit(w, "r", "2")
    assert w.session.result.ok and not w.session.model_problem
    assert source.read_bytes() == original


def test_failed_worker_shows_stale_warning_even_with_previous_ok_result(guarded_window, tmp_path):
    w = guarded_window
    source = tmp_path / "valid.json"
    ndt_document().save(source)
    assert w.open_model(source)
    old = w.session.result
    w.session._runner = SimpleNamespace(submit=lambda *a, **k: 7)
    edit(w, "h", "45")
    w.session._runner.poll = lambda: SimpleNamespace(job=7, update=None, result=None,
                                                    error="řízená chyba přenosu")
    w.session.poll()
    w._refresh_all()
    assert w.session.result is old and old.ok
    assert not w.error_label.isHidden() and "předchozímu stavu" in w.error_label.text()
    assert "Diagnostický" in w.props_label.text()
    assert not any(a.isEnabled() for a in w.export_actions)
    w.ndt_panel.select("s2")
    assert "nelze vyhodnotit" in w.ndt_panel.details.text()
    w.session._runner = None
    w.session.rebuild()
    w._refresh_all()
    assert not w.session.model_problem and w.error_label.isHidden()
    assert all(a.isEnabled() for a in w.export_actions)


def test_real_background_rebuild_recovers_window_actions(guarded_window, tmp_path):
    w = guarded_window
    runner = BackgroundRebuilder()

    def settle():
        end = time.monotonic() + 30
        while w.session.computing and time.monotonic() < end:
            w.session.poll()
            QTest.qWait(20)
        assert not w.session.computing
        w._refresh_all()

    try:
        w.session._runner = runner
        open_bad(w, tmp_path)
        settle()
        assert "[bad]" in w.error_label.text() and not any(
            a.isEnabled() for a in w.export_actions)
        edit(w, "r", "2")
        assert not any(a.isEnabled() for a in w.export_actions)
        settle()
        assert w.session.result.ok and w.error_label.isHidden()
        assert all(a.isEnabled() for a in w.export_actions)
    finally:
        w.session.cancel()
        w.session._runner = None
        runner.close()


@pytest.mark.parametrize("method", ["UT", "MT", "RT"])
def test_stale_study_working_preview_is_labelled(guarded_window, method):
    w = guarded_window
    source = EXAMPLES / "ndt" / ("otvor.json" if method == "RT" else "deska.json")
    assert w.open_model(source, template=True)
    s = w.session
    sid = "s1" if method == "UT" else "s2"
    s.set_info(material="hliník")
    assert next(r.state for r in s.ndt_studies if r.id == sid) == "stale"
    assert "zastaralá" in s.ndt_preview_note(sid)
    if method == "UT":
        s.place_ndt_probe(sid, [face_at(s.result.part, 0, 0, 20).wrapped], (0, 0, 20))
    elif method == "MT":
        s.place_ndt_yoke(sid, (0, 0, 20), 0)
        assert "Pracovní náhled" in s.ndt_yoke_drawing()[4]
    else:
        assert "Pracovní náhled" in s.ndt_rt_drawing(sid, "P1")[4]
    w._refresh_all()
    w.ndt_panel.select(sid)
    if method == "UT":
        assert "Pracovní náhled" in w.ndt_panel.placement_label.text()
        assert "Pracovní náhled" in w.viewer.probe[3]
    elif method == "MT":
        assert "Pracovní náhled" in w.ndt_panel.mt_yoke.text()
    assert "verified" not in s.ndt_study(sid)


def test_ai_reports_partial_image_and_repairs_offline(tmp_path):
    s = opened(tmp_path, failed=True)
    tools = ModelTools(s, look=lambda view: b"test-png")
    assert not any("export" in item["name"] or "ndt" in item["name"]
                   for item in tools.definitions)
    output = tools.run("view_part", {"view": "current"})
    assert output.content[0]["type"] == "image"
    assert "Diagnostický náhled" in output.content[1]["text"]
    report = build_report(s)
    assert "Diagnostický náhled" in report and "[bad]" in report
    assert "24000.0 mm³" in report and "NĚKTERÉ PRVKY MAJÍ CHYBU" in report
    s.begin_group()
    assert not tools.run("delete_feature", {"id": "tail"}).is_error
    result = tools.run("update_feature", {"id": "bad", "changes": {"radius": 2}})
    s.end_group()
    assert not result.is_error and not s.model_problem
    assert "Diagnostický" not in tools.run("view_part", {}).content[1]["text"]
    assert s.undo() and "[bad]" in s.model_problem
    assert s.redo() and not s.model_problem


def test_ai_labels_stale_body_after_failed_worker(tmp_path):
    s = opened(tmp_path)
    s._runner = SimpleNamespace(submit=lambda *a, **k: 7)
    s.set_parameter("h", "45")
    tools = ModelTools(s, look=lambda view: b"test-png")
    assert "Diagnostický náhled" in tools.report()
    assert tools.report().count("neplatná vazba") == 4
    s._runner.poll = lambda: SimpleNamespace(job=7, update=None, result=None, error="přenos selhal")
    s.poll()
    assert "předchozímu stavu" in tools.run("view_part", {}).content[1]["text"]
    assert "přenos selhal" in tools.report() and "předchozímu stavu" in tools.report()


@pytest.mark.parametrize("failed", [False, True])
def test_timeout_and_stop_restore_the_actual_last_recipe(tmp_path, failed):
    s = opened(tmp_path, failed=failed)
    previous = s.document
    s._runner = SimpleNamespace(submit=lambda *a, **k: 7, cancel=lambda: None)
    s.set_parameter("h", "45")
    assert not s.wait(timeout=0) and s.computing
    with pytest.raises(DocumentError, match="přepočítává"):
        s.export(tmp_path / "during.step")
    assert s.cancel() and not s.computing and s.document == previous and s.can_redo
    if failed:
        with pytest.raises(DocumentError, match=r"\[bad\]"):
            s.export(tmp_path / "stopped.step")
    else:
        part = import_step(s.export(tmp_path / "stopped.step"))
        assert part.is_valid and part.volume == pytest.approx(24000)
    s.redo()
    assert s.computing and s.document.parameters["h"] == 45
    assert not (tmp_path / "during.step").exists()


def test_error_in_saved_measurement_does_not_block_valid_geometry_export(tmp_path):
    s = opened(tmp_path)
    s.document.measurements = [{"id": "m1", "kind": "diameter", "a": {
        "face": {"at": [0, 0, 900], "normal": [0, 0, 1], "type": "plane"}}}]
    s.rebuild()
    assert s.result.measurements[0].error and not s.model_problem
    part = import_step(s.export(tmp_path / "valid.step"))
    assert part.is_valid and part.volume == pytest.approx(24000)


@pytest.mark.parametrize("kind", ["audit", "design"])
def test_gui_cannot_export_old_report_or_pdf_after_worker_failure(guarded_window, tmp_path,
                                                                monkeypatch, kind):
    import importlib

    w = guarded_window
    if kind == "audit":
        source = tmp_path / "valid.json"
        ndt_document().save(source)
        assert w.open_model(source)
        assert w.session.compute_ndt_audit(include=["s2"])
        panel, parameter = w.audit_panel, "h"
    else:
        assert w.open_model(EXAMPLES / "ndt" / "navrh_kapsa.json", template=True)
        assert w.session.compute_ndt_design({"study": "s3", "parameters": [
            {"name": "a", "values": [90]}], "options": {"verify": False, "rejected": False}})
        panel, parameter = w.design_panel, "a"
    w._refresh_all()
    assert panel.export_action.isEnabled()
    w.session._runner = SimpleNamespace(submit=lambda *a, **k: 8)
    w.session.set_parameter(parameter, "45")
    w.session._runner.poll = lambda: SimpleNamespace(job=8, update=None, result=None,
                                                    error="řízená chyba přenosu")
    w.session.poll()
    w._refresh_all()
    assert not panel.export_action.isEnabled()

    def forbidden(*a, **k):
        pytest.fail("Stará zpráva nesmí otevřít výstupní dialog ani zapisovat PDF")

    monkeypatch.setattr(QtWidgets.QFileDialog, "getExistingDirectory", forbidden)
    module = importlib.import_module(f"skodacad.gui.{kind}_panel")
    monkeypatch.setattr(module, "write_pdf", forbidden)
    panel.export()
    assert w.test_messages == []


def test_stopped_audit_preserves_one_real_result_and_marks_the_remaining_study(tmp_path):
    from skodacad.ndt import PT_DISCLAIMER
    from skodacad.ndt.audit import STOPPED

    s = opened(tmp_path)
    s.set_ndt_method("s3", "PT")
    s.set_ndt_pt_settings("s3", s.ndt_pt_settings("s2"))
    complete = s.compute_ndt_audit(include=["s2", "s3"])
    first = complete.entry("s2")
    assert first.status == "done" and first.result is not None
    replies = iter([SimpleNamespace(job=9, update=("entry", first)), None])
    s._runner = SimpleNamespace(submit_audit=lambda *a, **k: 9,
                               poll=lambda: next(replies, None), cancel=lambda: None)
    s.start_ndt_audit(include=["s2", "s3"])
    assert s.poll() and s.audit_pending and s.cancel()
    stopped = s.ndt_audit
    assert not stopped.complete and stopped.entry("s2").result is first.result
    pending = stopped.entry("s3")
    assert pending.status == "skipped" and pending.reason == STOPPED and pending.result is None
    folder = tmp_path / "stopped-audit"
    paths = s.export_ndt_audit(folder)
    assert {p.name for p in paths} == {"zprava.html", "mista.csv", "studie-s2-pt.csv"}
    html = (folder / "zprava.html").read_text(encoding="utf-8")
    assert PT_DISCLAIMER in html and STOPPED in html
