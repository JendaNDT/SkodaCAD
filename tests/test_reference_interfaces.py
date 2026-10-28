"""P1.3 C.3: actual process/Qt actions, interface errors and saved history."""

import math
import pickle
import time

import pytest

from conftest import edge_at, face_at
from reference_documents import edge_document, face_document, projection_document, radius_document
from skodacad import rebuild
from skodacad.assistant import build_report
from skodacad.cli import main
from skodacad.session import ModelSession
from skodacad.worker import BackgroundRebuilder, decode_result, encode_result

FACTORIES = {"edge": edge_document, "face": face_document, "radius": radius_document,
             "projection": projection_document}


def check(result, kind, repaired):
    assert result.part.is_valid
    assert len(result.part.solids()) == (2 if kind == "face" else 1)
    if kind == "edge":
        volume = 24000 - ((9 - math.pi * 9 / 4) * 40 if repaired else 0)
        assert result.part.is_inside((-9.9, -14.9, 20))
        assert result.part.is_inside((9.9, -14.9, 20)) != repaired
    elif kind == "projection":
        volume = 24000 + (2 * math.pi if repaired else 0)
        assert result.part.is_inside((0, 0, 41)) == repaired
    elif kind == "face":
        volume = 8000
        assert result.part.is_inside((-60, 0, 5)) and result.part.is_inside((20, 0, 5))
    else:
        volume = 360 * math.pi
        assert result.part.is_inside((5.9, 0, 5)) and not result.part.is_inside((6.1, 0, 5))
    assert result.part.volume == pytest.approx(volume, rel=1e-10)
    if kind in ("edge", "projection"):
        assert result.ok == repaired
        if not repaired:
            assert result.first_error.id == "bad" and result.statuses[-1].status == "skipped"
            assert "není jednoznačný" in result.first_error.message
            assert result.parts_before["bad"].volume == pytest.approx(24000)
        else:
            assert all(s.status == "ok" for s in result.statuses)
    else:
        assert result.ok  # chyba měření/oblasti není novou chybou objemové geometrie
        assert result.ndt[0].state == ("ok" if repaired else "broken")
        assert result.ndt[0].faces == int(repaired) and result.ndt[0].verified == "Neověřeno."
        if repaired:
            value = 400 if kind == "face" else 12
            assert result.measurements[0].value.value == pytest.approx(value)
        else:
            assert result.measurements[0].value is None and result.measurements[0].error


@pytest.fixture(scope="module")
def runner():
    worker = BackgroundRebuilder()
    yield worker
    worker.close()


@pytest.mark.parametrize("kind", FACTORIES)
@pytest.mark.parametrize("repaired", [False, True])
def test_reference_states_use_bin_tools_protocol_with_model_signature(kind, repaired):
    result = rebuild(FACTORIES[kind](repaired))
    payload = encode_result(result)
    assert set(payload) == {"part", "parameters", "statuses", "parts_before", "sketches",
                            "measurements", "thickness_map", "map_error", "ndt",
                            "model_signature"}
    restored = decode_result(pickle.loads(pickle.dumps(payload)))
    assert restored.model_signature == result.model_signature
    assert restored.statuses == result.statuses
    assert restored.measurements == result.measurements and restored.ndt == result.ndt
    check(restored, kind, repaired)


@pytest.mark.parametrize("kind", FACTORIES)
def test_real_spawn_preserves_bad_good_bad_reference_results(runner, kind):
    for repaired in (False, True, False):
        doc = FACTORIES[kind](repaired)
        before = doc.to_dict()
        direct = rebuild(doc)
        job = runner.submit(before)
        completed = runner.wait(timeout=60)
        assert completed is not None and completed.job == job and not completed.error
        assert completed.result.statuses == direct.statuses
        assert completed.result.measurements == direct.measurements
        assert completed.result.ndt == direct.ndt
        check(completed.result, kind, repaired)
        assert doc.to_dict() == before


def repair(session, kind):
    if kind in ("edge", "projection"):
        feature = session.feature("bad")
        if kind == "edge":
            feature["edges"] = {"between": ["front", "right"]}
        else:
            refs = feature["elements"][0]["references"]
            refs[next(iter(refs))]["edge"] = {"between": ["top", "front"]}
        session.update_feature("bad", feature)
        return
    # Jedna existující skupina historie (stejná cesta jako offline úprava nástroji AI).
    session.begin_group()
    try:
        point = (-60, 0, 10) if kind == "face" else (6, 0, 5)
        face = face_at(session.result.part, *point)
        session.set_ndt_target("s1", [face.wrapped], point)
        assert session.ndt_studies[0].state == "stale"
        session.confirm_ndt_study("s1")
        session.remove_measurement("m1")
        face = face_at(session.result.part, *point)
        session.add_measurement([face.wrapped], "area" if kind == "face" else "diameter", point)
    finally:
        session.end_group()


@pytest.mark.parametrize("kind", FACTORIES)
def test_cli_offline_report_history_and_saved_copy_keep_the_same_reference_state(kind, tmp_path,
                                                                              capsys):
    source, copy = tmp_path / "source.json", tmp_path / "copy.json"
    FACTORIES[kind]().save(source)
    original = source.read_bytes()
    session = ModelSession()
    session.open(source)
    check(session.result, kind, False)
    report = build_report(session)  # bez API klienta nebo síťového volání
    code = main(["build", str(source), "--format", "step", "-o", str(tmp_path / "out")])
    assert code == (1 if kind in ("edge", "projection") else 0)  # beze změny R01/P1.4
    cli = capsys.readouterr().out
    error = (session.result.first_error.message if session.result.first_error
             else session.result.measurements[0].error)
    assert error in cli and error in report
    if session.result.ndt:
        assert session.result.ndt[0].label in cli and session.result.ndt[0].label in report
    repair(session, kind)
    check(session.result, kind, True)
    session.undo()
    check(session.result, kind, False)
    session.redo()
    check(session.result, kind, True)
    session.save(copy)
    reopened = ModelSession()
    reopened.open(copy)
    check(reopened.result, kind, True)
    assert source.read_bytes() == original


@pytest.fixture
def window(runner, tmp_path, examples_dir, monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qt = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from skodacad.gui.main_window import MainWindow
    from test_gui import FakeViewer

    app = qt.QApplication.instance() or qt.QApplication([])
    warnings = []
    monkeypatch.setattr(qt.QMessageBox, "warning", lambda *a, **_k: warnings.append(a[2]))
    w = MainWindow(viewer_factory=FakeViewer, runner=runner, user_dir=tmp_path,
                   examples_dir=examples_dir)
    yield w
    w.session.cancel()
    w.session.dirty = False
    w._runner = None
    w.close()
    app.processEvents()
    assert not warnings, warnings


def settle(window):
    from PySide6.QtTest import QTest

    end = time.monotonic() + 60
    while window.session.computing and time.monotonic() < end:
        QTest.qWait(50)
    assert not window.session.computing


def test_qt_window_repairs_actual_worker_geometry_by_replacing_the_picked_edge(window, tmp_path,
                                                                           monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFileDialog

    source, copy = tmp_path / "source.json", tmp_path / "copy.json"
    edge_document().save(source)
    original = source.read_bytes()
    assert window.open_model(source, template=True)
    settle(window)
    check(window.session.result, "edge", False)
    item = next(window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())
                if window.tree.topLevelItem(i).data(0, Qt.UserRole) == "bad")
    window.tree.setCurrentItem(item)
    assert "nejbližší k bodu" in window.feature_editor.form.widget("edges").text()
    edge = edge_at(window.session.result.part, 10, -15, 20)
    window.viewer.click([edge])
    assert window.replace_in_feature_action.isEnabled()
    window.replace_in_feature_action.trigger()
    settle(window)
    check(window.session.result, "edge", True)
    assert all(window.tree.topLevelItem(i).text(0).startswith("✓")
               for i in range(window.tree.topLevelItemCount()))
    assert "Počet těles: 1" in window.props_label.text()
    window.undo_action.trigger()
    settle(window)
    check(window.session.result, "edge", False)
    window.redo_action.trigger()
    settle(window)
    check(window.session.result, "edge", True)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_k: (str(copy), ""))
    window.save_as_action.trigger()
    assert copy.exists() and window.open_model(copy)
    settle(window)
    check(window.session.result, "edge", True)
    assert source.read_bytes() == original
