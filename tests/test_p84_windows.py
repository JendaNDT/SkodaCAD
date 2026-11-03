"""Zavřená vlastněná okna sestav se zruší i při zachovaných Python odkazech."""
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QMessageBox
from shiboken6 import isValid

from test_assembly_gui import app as app
from test_assembly_gui import dialogs as dialogs
from test_assembly_gui import main_window as main_window
from test_assembly_gui import project as project


def deferred_deletes():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_repeated_closed_assemblies_release_widgets_and_keep_other_window(main_window, project):
    path = project / "sestavy/krabicka_s_vickem.json"
    survivor = main_window.open_assembly(path)
    original = survivor.session.result
    closed = []
    for _ in range(3):
        window = main_window.open_assembly(path)
        viewer = window.viewer
        closed.append(window)  # odkaz sám nesmí držet zrušené Qt/3D prostředky
        assert window.close()
        deferred_deletes()
        assert not isValid(window) and not isValid(viewer)
        assert main_window.assembly_windows == [survivor]
        assert isValid(survivor) and survivor.isVisible()
        assert survivor.session.result is original
    assert all(not isValid(window) for window in closed)


def test_cancel_close_preserves_dirty_assembly_then_discard_releases_it(
        main_window, project, dialogs):
    path = project / "sestavy/krabicka_s_vickem.json"
    source = path.read_bytes()
    window = main_window.open_assembly(path)
    window.session.rename("vicko", "Upravené víčko")
    recipe, result = window.session.assembly.to_dict(), window.session.result
    assert not window.close()  # výchozí odpověď fixture je Zrušit
    deferred_deletes()
    assert isValid(window) and window.isVisible() and window.session.dirty
    assert window.session.assembly.to_dict() == recipe and window.session.result is result
    assert main_window.assembly_windows == [window]
    dialogs["question"] = QMessageBox.StandardButton.Discard
    assert window.close()
    deferred_deletes()
    assert not isValid(window) and main_window.assembly_windows == []
    assert path.read_bytes() == source


def test_main_close_can_be_cancelled_without_stale_destroyed_windows(main_window, project, dialogs):
    path = project / "sestavy/krabicka_s_vickem.json"
    clean = main_window.open_assembly(path)
    dirty = main_window.open_assembly(path)
    dirty.session.rename("vicko", "Jiné víčko")
    main_window.show()
    assert not main_window.close()
    deferred_deletes()
    assert not isValid(clean)
    assert isValid(dirty) and dirty.isVisible() and main_window.isVisible()
    assert main_window.assembly_windows == [dirty]
    dialogs["question"] = QMessageBox.StandardButton.Discard
    assert main_window.close()
    deferred_deletes()
    assert not isValid(dirty) and main_window.assembly_windows == []


def test_failed_open_releases_new_window_and_registry_is_empty(main_window, tmp_path):
    assert main_window.open_assembly(tmp_path / "chybi.json") is None
    deferred_deletes()
    assert main_window.assembly_windows == []
