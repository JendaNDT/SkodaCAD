"""Přepočet na pozadí v pomocném procesu: přenos výsledku, zrušení, pád, ModelSession."""

import math
import time

import pytest

from conftest import box_features, make_doc
from skodacad import Document, DocumentError, rebuild
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder, decode_result, encode_result


def threaded_plate(size="M5"):
    """Deska s vymodelovaným závitem – přepočet trvá několik sekund."""
    return make_doc(box_features(40, 40, 8) + [
        {"id": "d", "type": "hole", "kind": "tapped", "size": size, "plane": "top",
         "positions": [[0, 0]], "through_all": True, "modeled_thread": True}])


@pytest.fixture(scope="module")
def runner():
    rebuilder = BackgroundRebuilder()
    yield rebuilder
    rebuilder.close()


def test_result_survives_transfer_between_processes(examples_dir):
    original = rebuild(Document.load(examples_dir / "kryt.json"))
    copy = decode_result(encode_result(original))
    assert copy.part.volume == pytest.approx(original.part.volume)
    assert copy.part.is_valid and len(copy.part.faces()) == len(original.part.faces())
    assert copy.statuses == original.statuses and copy.parameters == original.parameters
    assert set(copy.parts_before) == set(original.parts_before)
    for key, part in original.parts_before.items():
        assert (part is None) == (copy.parts_before[key] is None)
        if part is not None:
            assert copy.parts_before[key].volume == pytest.approx(part.volume)
    for key, (plane, sketch) in original.sketches.items():
        copied_plane, copied_sketch = copy.sketches[key]
        assert tuple(copied_plane.origin) == pytest.approx(tuple(plane.origin))
        assert tuple(copied_plane.z_dir) == pytest.approx(tuple(plane.z_dir))
        assert copied_sketch.area == pytest.approx(sketch.area)


def test_rebuild_in_worker_matches_direct_rebuild(runner, examples_dir):
    document = Document.load(examples_dir / "prilozka.json")
    job = runner.submit(document.to_dict())
    finished = runner.wait()
    assert finished is not None and finished.job == job and not finished.error
    assert finished.result.part.volume == pytest.approx(rebuild(document).part.volume)
    assert not runner.busy


def test_thickness_map_is_computed_in_worker(runner):
    runner.submit(make_doc(box_features(20, 30, 6)).to_dict(), with_map=True)
    finished = runner.wait()
    assert finished.result.thickness_map.minimum == pytest.approx(6)  # deska 6 mm
    assert finished.result.thickness_map.nominal == pytest.approx(6)
    runner.submit(make_doc(box_features(20, 30, 6)).to_dict())  # bez mapy
    assert runner.wait().result.thickness_map is None


def test_new_change_cancels_running_rebuild(runner):
    runner.submit(threaded_plate("M4").to_dict())
    time.sleep(0.5)
    started = time.monotonic()
    job = runner.submit(make_doc(box_features(20, 30, 40)).to_dict())  # rychlý model
    finished = runner.wait()
    assert finished.job == job  # výsledek patří až k nové změně
    assert finished.result.part.volume == pytest.approx(20 * 30 * 40)
    assert time.monotonic() - started < 10  # nečekalo se na dopočítání závitu


def test_crashed_worker_is_reported_and_replaced(runner):
    runner.submit(threaded_plate("M3").to_dict())
    time.sleep(0.3)
    runner._active.process.kill()  # jako by knihovna jádra shodila proces
    finished = runner.wait(timeout=10)
    assert finished is not None and "spadl" in finished.error
    runner.submit(make_doc(box_features(10, 10, 10)).to_dict())
    assert runner.wait().result.part.volume == pytest.approx(1000)


def test_bad_document_error_comes_back_in_czech(runner):
    runner.submit({"format": "jiny"})
    finished = runner.wait()
    assert "Soubor není model ŠkodaCAD" in finished.error


# --- ModelSession s přepočtem na pozadí --------------------------------------------------


def test_session_keeps_old_result_until_new_one_arrives(runner, examples_dir):
    session = ModelSession(runner)
    session.open(examples_dir / "priruba.json")
    assert session.computing and session.result is None  # starý model se neukazuje
    assert session.wait()
    volume = session.properties.volume_mm3
    session.set_parameter("t", "36")
    assert session.computing and session.properties.volume_mm3 == pytest.approx(volume)
    with pytest.raises(DocumentError, match="ještě přepočítává"):
        session.export(examples_dir / "nikam.step")
    assert session.wait()
    assert session.properties.volume_mm3 > 1.9 * volume  # dvojnásobná tloušťka desky
    assert session.properties.volume_mm3 == pytest.approx(
        rebuild(session.document).part.volume)


def test_cancel_returns_to_last_computed_state_and_redo_retries(runner):
    session = ModelSession(runner)
    session.new_document()
    session.add_feature("sketch")
    session.add_feature("extrude")
    assert session.wait()
    before = session.document
    session.add_feature("hole", values={"size": "M5", "through_all": True,
                                        "modeled_thread": True})
    assert session.computing
    assert session.cancel()
    assert not session.computing and session.document == before
    assert session.properties.volume_mm3 == pytest.approx(40 * 30 * 10)
    assert session.can_redo and session.can_undo
    session.redo()  # zrušenou změnu jde zkusit znovu
    assert [f["type"] for f in session.document.features] == ["sketch", "extrude", "hole"]
    assert session.wait()
    assert session.properties.volume_mm3 < 40 * 30 * 10 - math.pi * 2.1**2 * 10  # díra + závit
    assert session.properties.volume_mm3 == pytest.approx(
        rebuild(session.document).part.volume)
    session.undo()
    assert session.wait() and session.document == before


def test_selection_waits_for_computed_model(runner):
    session = ModelSession(runner)
    session.new_document()
    session.add_feature("sketch")
    session.add_feature("extrude")
    with pytest.raises(DocumentError, match="ještě přepočítává"):
        session.add_from_selection("fillet", [])
    assert session.wait()
    assert session.failure == ""


# --- okno s přepočtem na pozadí ------------------------------------------------------------


@pytest.fixture
def window(runner, examples_dir, tmp_path, monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qt = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QMessageBox

    from skodacad.gui.main_window import MainWindow
    from test_gui import FakeViewer

    qt.QApplication.instance() or qt.QApplication([])
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path,
                   runner=runner)
    yield w
    w.session.cancel()
    w.session.dirty = False
    w._runner = None  # sdílené procesy zavře až fixture „runner“
    w.close()


def settle(w, timeout=60.0):
    """Nechá běžet okno (časovač převezme výsledek), dokud se model přepočítává."""
    from PySide6.QtTest import QTest

    end = time.monotonic() + timeout
    while w.session.computing and time.monotonic() < end:
        QTest.qWait(50)
    assert not w.session.computing, "přepočet na pozadí nedoběhl"


def tree_texts(w):
    return [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]


def test_window_shows_progress_and_then_result(window, examples_dir):
    from PySide6.QtTest import QTest

    window.open_model(examples_dir / "deska.json", template=True)
    assert window.session.computing
    assert len(tree_texts(window)) == len(window.session.document.features)  # strom hned
    QTest.qWait(400)  # delší než PENDING_DELAY → okno ukáže „Přepočítávám…“
    if window.session.computing:
        assert window.progress_label.isVisibleTo(window)
        assert window.progress_label.text().startswith("⏳ Přepočítávám")
        assert window.stop_action.isEnabled()
        assert all(text.startswith("⏳") for text in tree_texts(window))
        assert not any(a.isEnabled() for a in window.selection_actions.values())
    settle(window)
    assert all(text.startswith("✓") for text in tree_texts(window))
    assert not window.progress_label.isVisibleTo(window)
    assert not window.stop_action.isEnabled()
    assert window.session.properties.volume_mm3 == pytest.approx(
        rebuild(window.session.document).part.volume)
    assert window.viewer.parts[-1][0] is window.session.result.part


def test_stop_button_returns_to_computed_model(window):
    from PySide6.QtTest import QTest

    window.new_model()
    window.add_feature("sketch")
    window.add_feature("extrude")
    settle(window)
    computed = window.session.document
    window.add_feature("hole")  # díra je vybraná ve stromu i ve formuláři
    settle(window)
    form = window.feature_editor.form
    size = form.widget("size")
    size.setCurrentIndex(size.findData("M5"))
    form.widget("modeled_thread").setChecked(True)  # vymodelovaný závit = pomalý přepočet
    assert window.session.computing
    assert window.tree.currentItem().text(0).endswith("(vymodelovaný)")  # výběr zůstal
    QTest.qWait(400)
    window.stop_action.trigger()
    assert not window.session.computing
    assert not window.session.document.features[-1].get("modeled_thread")
    assert window.redo_action.isEnabled()
    assert "Přepočet zastaven" in window.statusBar().currentMessage()
    assert len(window.session.document.features) == len(computed.features) + 1


def test_feature_added_while_computing_is_in_tree_and_editor(window):
    window.new_model()
    window.add_feature("sketch")
    window.add_feature("extrude")
    assert window.session.computing
    assert [window.tree.topLevelItem(i).data(0, 256) for i in range(2)] == ["sketch1",
                                                                           "extrude1"]
    assert window.feature_editor.feature_id == "extrude1"
    settle(window)
    assert window.session.properties.volume_mm3 == pytest.approx(40 * 30 * 10)


def test_new_command_preview_has_own_worker_and_recovers_from_failure(window):
    from PySide6.QtTest import QTest

    window.new_model()
    window.add_feature("sketch")
    window.add_feature("extrude")
    settle(window)
    before, result = window.session.document.to_dict(), window.session.result
    count = len(window.session._undo)
    window.add_feature_actions["hole"].trigger()
    panel = window.feature_preview
    assert panel is not None and panel.preview.session.computing
    assert window._feature_preview_runner is not window._runner
    assert not panel.accept_button.isEnabled() and not window.session.computing
    window._feature_preview_runner._active.process.kill()

    def finish_preview():
        end = time.monotonic()+45
        while panel.preview.session.computing and time.monotonic() < end:
            QTest.qWait(20)
        assert not panel.preview.session.computing

    finish_preview()
    assert panel.preview.session.failure and not panel.accept_button.isEnabled()
    assert window.session.result is result and window.session.document.to_dict() == before
    panel.refresh_button.click()
    finish_preview()
    assert panel.accept_button.isEnabled()
    assert window.session.document.to_dict() == before
    panel.accept_button.click()
    assert window.feature_preview is None and not window.session.computing
    assert window.session.properties.volume_mm3 == pytest.approx(12000-250*math.pi/4)
    assert len(window.session._undo) == count+1


def test_window_audit_in_background_with_progress_and_stop(window, examples_dir):
    """Předběžný NDT audit z panelu na pozadí (etapa 14): průběh, místa, Zastavit."""
    import dataclasses

    from PySide6.QtTest import QTest

    window.open_model(examples_dir / "ndt" / "otvor.json", template=True)
    settle(window)
    session, panel = window.session, window.audit_panel
    session.set_ndt_rt_settings("s2", dataclasses.replace(session.ndt_rt_settings("s2"),
                                                          step_mm=10, image_step_mm=20))
    settle(window)
    window.show_audit()
    panel.run_action.trigger()
    assert session.audit_pending and panel.stop_action.isEnabled()
    end = time.monotonic() + 60
    while session.audit_pending and not session.ndt_audit_progress \
            and time.monotonic() < end:
        QTest.qWait(20)
    assert session.ndt_audit_progress.startswith("studie ")
    settle(window)
    assert not session.audit_pending and panel.places.rowCount() == 2
    assert panel.progress.text() == "" and panel.export_action.isEnabled()
    panel.run_action.trigger()
    panel.stop_action.trigger()
    assert not session.computing and "Audit byl zastaven" in panel.overview.text()
    assert panel.places.rowCount() == 0  # RT studie nedoběhla – „neprovedeno“


@pytest.mark.parametrize("kind", ["pattern", "mirror"])
def test_late_transaction_failure_repair_and_history_in_background_window(window, tmp_path,
                                                                       monkeypatch, kind):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFileDialog

    from test_gui import set_text
    from transaction_cases import late_failure_document

    source = tmp_path / "source.json"
    destination = tmp_path / "copy.json"
    late_failure_document(kind).save(source)
    original = source.read_bytes()
    window.open_model(source, template=True)
    settle(window)
    assert window.session.result.first_error.id == "bad"
    assert window.session.result.statuses[-1].status == "skipped"
    assert window.session.properties.volume_mm3 == pytest.approx(80000 - 40 * math.pi)
    assert set(window.session.result.sketches) == {"s", "s0", "s1"}
    assert "Počet těles: 1" in window.props_label.text()
    item = next(window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())
                if window.tree.topLevelItem(i).data(0, Qt.UserRole) == "bad")
    window.tree.setCurrentItem(item)
    key, value = ("spacing", "-20") if kind == "pattern" else ("offset", "0")
    set_text(window.feature_editor.form.widget(key), value)
    settle(window)
    assert window.session.result.ok and all(t.startswith("✓") for t in tree_texts(window))
    assert window.session.properties.volume_mm3 == pytest.approx(80000 - 80 * math.pi)
    window.undo_action.trigger()
    settle(window)
    assert window.session.result.first_error.id == "bad"
    assert window.session.properties.volume_mm3 == pytest.approx(80000 - 40 * math.pi)
    window.redo_action.trigger()
    settle(window)
    assert window.session.result.ok
    assert window.session.properties.volume_mm3 == pytest.approx(80000 - 80 * math.pi)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_k: (str(destination), ""))
    window.save_as_action.trigger()
    assert destination.is_file()
    window.open_model(destination)
    settle(window)
    assert window.session.result.ok and window.session.properties.solids == 1
    assert window.session.properties.volume_mm3 == pytest.approx(80000 - 80 * math.pi)
    assert source.read_bytes() == original
