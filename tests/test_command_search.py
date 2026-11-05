"""Command search: actual QAction callbacks, state, keyboard and document isolation."""

import copy
from contextlib import contextmanager

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from skodacad.gui.command_search import CommandSearchDialog, collect_commands, show_command_search
from test_gui import app, window  # noqa: F401


def labels(dialog):
    return [dialog.results.topLevelItem(i).text(0)
            for i in range(dialog.results.topLevelItemCount())]


@contextmanager
def dialog_response(callback):
    """A failed assertion in a Qt slot must fail the test, never leave a modal wait."""
    errors = []

    def respond():
        dialog = QApplication.activeModalWidget()
        try:
            callback()
        except Exception as exc:
            errors.append(exc)
        finally:
            if isinstance(dialog, CommandSearchDialog) and dialog.isVisible():
                dialog.reject()

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(respond)
    timer.start(0)
    try:
        yield
    finally:
        timer.stop()
    if errors:
        raise errors[0]


@pytest.fixture
def menu_window(app):  # noqa: F811
    owner = QMainWindow()
    menu = owner.menuBar().addMenu("&Soubor")
    save = menu.addAction("&Uložit jako…")
    save.setShortcut("Ctrl+Shift+S")
    menu.addSeparator()
    submenu = menu.addMenu("E&xport")
    export = submenu.addAction("STEP")
    hidden = menu.addAction("Skrytý")
    hidden.setVisible(False)
    owner.menuBar().addMenu("Jiná nabídka").addAction(save)
    owner.command_search_action = menu.addAction("Najít příkaz…")
    yield owner, menu, save, submenu, export
    owner.close()


def test_catalogue_menu_paths_shared_actions_and_ribbon(menu_window):
    owner, menu, save, submenu, export = menu_window
    extra = menu.addAction("Další příkaz")
    menu.removeAction(extra)
    commands = collect_commands(owner.menuBar(), [(("Výkres", "Výstup"), [save, extra])],
                                exclude=(owner.command_search_action,))
    assert [(c.action, c.path) for c in commands] == [
        (save, "Soubor"), (export, "Soubor › Export"), (extra, "Výkres › Výstup")]
    submenu.setEnabled(False)
    assert not commands[1].available
    assert commands[0].available


def test_search_without_accents_multiple_words_and_empty_result(menu_window):
    owner, *_ = menu_window
    dialog = CommandSearchDialog(collect_commands(owner.menuBar()), owner)
    dialog.query.setText("SOUBOR ulozit")
    assert labels(dialog) == ["Uložit jako…"]
    assert dialog.results.topLevelItem(0).text(2)
    dialog.query.setText("soubor export")
    assert labels(dialog) == ["STEP"]
    dialog.query.setText("neexistující")
    assert labels(dialog) == []
    assert not dialog.run_button.isEnabled()
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "Žádný příkaz" in dialog.note.text()
    dialog.reject()


def test_keyboard_selection_and_cancel_never_trigger(menu_window):
    owner, _, save, _, export = menu_window
    calls = []
    save.triggered.connect(lambda: calls.append("save"))
    export.triggered.connect(lambda: calls.append("export"))
    dialog = CommandSearchDialog(collect_commands(owner.menuBar()), owner)
    dialog.show()
    dialog.query.setFocus()
    QTest.keyClick(dialog.query, Qt.Key.Key_Down)
    assert dialog.current_command().action is export
    QTest.keyClick(dialog.query, Qt.Key.Key_Up)
    assert dialog.current_command().action is save
    QTest.keyClick(dialog.query, Qt.Key.Key_Escape)
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert calls == []


def test_disabled_parent_live_state_and_destroyed_action(menu_window):
    owner, _, _, submenu, export = menu_window
    calls = []
    export.triggered.connect(lambda: calls.append(True))
    dialog = CommandSearchDialog(collect_commands(owner.menuBar()), owner)
    dialog.query.setText("STEP")
    submenu.setEnabled(False)
    assert labels(dialog) == ["STEP [nedostupné]"]
    assert not dialog.run_button.isEnabled()
    dialog.accept()
    assert dialog.selected_command is None and not calls
    submenu.setEnabled(True)
    assert dialog.run_button.isEnabled()
    export.setVisible(False)
    assert labels(dialog) == []
    export.setVisible(True)
    dialog.reject()
    # An external command can disappear while the search owns no part of its lifetime.
    temporary = QAction("Dočasný")
    dialog = CommandSearchDialog(collect_commands(owner.menuBar(), [(("Další",), [temporary])]),
                                 owner)
    dialog.query.setText("docasny")
    from shiboken6 import delete
    delete(temporary)
    dialog.accept()  # stale result is rechecked, removed, and never invoked
    assert labels(dialog) == []
    dialog.reject()


def test_selected_command_runs_once_after_search_closes(menu_window):
    owner, _, save, *_ = menu_window
    calls = []
    save.triggered.connect(lambda: calls.append(QApplication.activeModalWidget()))

    def choose():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, CommandSearchDialog)
        dialog.query.setText("ulozit")
        QTest.keyClick(dialog.query, Qt.Key.Key_Return)

    with dialog_response(choose):
        show_command_search(owner)
    assert calls == [None]


def test_recheck_state_after_dialog_closes(menu_window):
    owner, _, save, *_ = menu_window
    calls = []
    save.triggered.connect(lambda: calls.append(True))

    def choose():
        dialog = QApplication.activeModalWidget()
        dialog.query.setText("ulozit")
        dialog.finished.connect(lambda _: save.setEnabled(False))
        dialog.accept()

    with dialog_response(choose):
        show_command_search(owner)
    assert calls == []


def test_checkable_action_toggles_exactly_once(menu_window):
    owner, _, save, *_ = menu_window
    save.setCheckable(True)
    calls = []
    save.toggled.connect(calls.append)

    def choose():
        dialog = QApplication.activeModalWidget()
        dialog.query.setText("ulozit")
        assert dialog.note.text().startswith("Vypnuto.")
        dialog.accept()

    with dialog_response(choose):
        show_command_search(owner)
    assert calls == [True]


def test_part_search_cancel_preserves_document_and_ribbon_commands(window):  # noqa: F811
    session = window.session
    before = copy.deepcopy(session.document.to_dict())
    result = session.result
    undo, redo, dirty = list(session._undo), list(session._redo), session.dirty
    selected = window._selected_id
    commands = collect_commands(window.menuBar(), window.ribbon.command_groups,
                                exclude=(window.command_search_action,))
    assert sum(c.action is window.save_action for c in commands) == 1
    assert any(c.action is window.drawing_preview_action for c in commands)
    assert all(c.action is not window.command_search_action for c in commands)

    def cancel():
        dialog = QApplication.activeModalWidget()
        dialog.query.setText("vybrané hrany")
        assert labels(dialog)
        assert not dialog.run_button.isEnabled()  # no picked edge
        QTest.keyClick(dialog.query, Qt.Key.Key_Escape)

    with dialog_response(cancel):
        window.command_search_action.trigger()
    assert session.document.to_dict() == before
    assert session.result is result
    assert (session._undo, session._redo, session.dirty) == (undo, redo, dirty)
    assert window._selected_id == selected


def test_assembly_search_uses_current_window(app, tmp_path):  # noqa: F811
    from skodacad.gui.assembly_window import AssemblyWindow
    from test_gui import FakeViewer

    owner = AssemblyWindow(viewer_factory=FakeViewer, user_dir=tmp_path)
    commands = collect_commands(owner.menuBar(), exclude=(owner.command_search_action,))
    assert any(c.action is owner.parameters_action for c in commands)
    assert sum(c.action is owner.bill_action for c in commands) == 1
    assert all("NDT" not in c.path for c in commands)
    before = (owner.session.assembly, owner.session.result, owner.session.dirty)

    def cancel():
        dialog = QApplication.activeModalWidget()
        dialog.query.setText("parametry")
        assert labels(dialog) == ["Parametry sestavy… [nedostupné]"]
        dialog.reject()

    with dialog_response(cancel):
        owner.command_search_action.trigger()
    assert (owner.session.assembly, owner.session.result, owner.session.dirty) == before
    owner.close()
