"""Favorite commands exercise real search, Qt actions and a throwaway profile."""

import copy
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from skodacad.gui.assembly_window import AssemblyWindow
from skodacad.gui.favorite_commands import MAX_FAVORITES, FavoriteEditor, FavoriteStore
from skodacad.gui.main_window import MainWindow
from test_command_search import dialog_response
from test_gui import FakeViewer, app  # noqa: F401


def buttons(window):
    pins = window.favorite_bar._pins
    return [pins.itemAt(i).widget() for i in range(pins.count())]


def pin_from_search(window, query, action, *, pinned=False):
    def choose():
        dialog = QApplication.activeModalWidget()
        dialog.query.setText(query)
        for i in range(dialog.results.topLevelItemCount()):
            item = dialog.results.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole).action is action:
                dialog.results.setCurrentItem(item)
                break
        assert dialog.current_command().action is action
        assert dialog.pin_button.isEnabled()
        QTest.mouseClick(dialog.pin_button, Qt.MouseButton.LeftButton)
        assert dialog.isVisible(), "připnutí nesmí zavřít hledání ani spustit příkaz"
        assert dialog.results.currentItem().text(0).startswith("★ ") is (not pinned)
        QTest.keyClick(dialog.query, Qt.Key.Key_Escape)

    with dialog_response(choose):
        window.command_search_action.trigger()


@pytest.mark.parametrize("kind", ["part", "assembly"])
def test_pin_search_then_use_real_toggle_and_reopen(app, tmp_path, kind):  # noqa: F811
    def create():
        cls = MainWindow if kind == "part" else AssemblyWindow
        return cls(viewer_factory=FakeViewer, user_dir=tmp_path)

    window = create()
    window.show()
    assert window.favorite_bar.isHidden()
    if kind == "part":
        assert window.new_model()
        action = window.workspace.collapse_action
        document, query = window.session.document, "sbalit pas"
    else:
        assert window.new_assembly(tmp_path / "sestava.json")
        action = window.files_action
        document, query = window.session.assembly, "soubory ve stromu"
    before = copy.deepcopy(document.to_dict())
    history = (list(window.session._undo), list(window.session._redo), window.session.dirty)
    result = window.session.result
    calls = []
    action.toggled.connect(calls.append)
    checked = action.isChecked()
    pin_from_search(window, query, action)
    assert calls == [] and action.isChecked() == checked
    assert not window.favorite_bar.isHidden()
    button, = buttons(window)
    assert button.command.action is action
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert calls == [not checked] and button.isChecked() == action.isChecked()
    current = window.session.document if kind == "part" else window.session.assembly
    assert current.to_dict() == before and window.session.result is result
    assert (window.session._undo, window.session._redo, window.session.dirty) == history
    window.session.dirty = False
    keys = window.favorite_bar.keys
    window.close()

    again = create()
    again.show()
    assert again.favorite_bar.keys == keys
    button, = buttons(again)
    pin_from_search(again, query if kind == "assembly" else "pas nastroju",
                    button.command.action, pinned=True)
    assert again.favorite_bar.isHidden() and buttons(again) == []
    again.close()


def test_favorites_reuse_availability_including_parent_and_current_label(app, tmp_path):  # noqa: F811
    window = MainWindow(viewer_factory=FakeViewer, user_dir=tmp_path)
    window.show()
    action = window.edit_feature_action
    assert not action.isEnabled()
    pin_from_search(window, "upravit prvek", action)
    button, = buttons(window)
    calls = []
    action.triggered.connect(lambda: calls.append(True))
    assert not button.isEnabled()
    action.setEnabled(True)
    assert button.isEnabled()
    parent = button.command.parents[-1]
    parent.setEnabled(False)
    assert not button.isEnabled()
    button.click()
    assert calls == []
    parent.setEnabled(True)
    action.setText("Jiný název")
    assert button.accessibleName() == "Jiný název"
    assert button.isEnabled()
    window.close()


def test_reorder_cancel_remove_and_sync_open_assemblies(app, tmp_path):  # noqa: F811
    owner = MainWindow(viewer_factory=FakeViewer, user_dir=tmp_path)
    a, b = [AssemblyWindow(viewer_factory=FakeViewer, favorite_store=owner.favorite_store)
            for _ in range(2)]
    pin_from_search(a, "soubory ve stromu", a.files_action)
    pin_from_search(a, "cela sestava", a.fit_action)
    assert [button.command.action for button in buttons(b)] == [b.files_action, b.fit_action]
    assert owner.favorite_bar.keys == ()

    dialog = FavoriteEditor(a.favorite_bar)
    dialog.down.click()
    dialog.reject()
    assert [button.command.action for button in buttons(a)] == [a.files_action, a.fit_action]

    dialog = FavoriteEditor(a.favorite_bar)
    dialog.down.click()
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    assert [button.command.action for button in buttons(b)] == [b.fit_action, b.files_action]

    dialog = FavoriteEditor(a.favorite_bar)
    dialog.remove.click()
    dialog.accept()
    assert [button.command.action for button in buttons(b)] == [b.files_action]
    assert FavoriteStore(tmp_path / "oblibene-prikazy.json").get("assembly") == a.favorite_bar.keys
    for window in (a, b, owner):
        window.close()


def test_profile_validation_limit_and_write_failure(app, tmp_path):  # noqa: F811
    path = tmp_path / "oblibene-prikazy.json"
    path.write_text("neúplný JSON", encoding="utf-8")
    assert FavoriteStore(path).get("part") == ()
    path.write_text(json.dumps({"version": 1, "part": [7, "x", "x", *map(str, range(9))],
                                "assembly": ["sestava"]}), encoding="utf-8")
    store = FavoriteStore(path)
    assert store.get("part") == ("x", "0", "1", "2", "3", "4")
    assert store.get("assembly") == ("sestava",)
    assert len(store.get("part")) == MAX_FAVORITES

    window = MainWindow(viewer_factory=FakeViewer, user_dir=tmp_path / "novy")
    window.favorite_store.path = path / "not-a-directory.json"
    window.show()

    def choose():
        dialog = QApplication.activeModalWidget()
        dialog.query.setText("ulozit jako")
        assert dialog.pin_button.isEnabled()
        dialog.pin_button.click()
        assert "nepodařilo uložit" in dialog.note.text()
        assert window.favorite_bar.keys == ()

    with dialog_response(choose):
        window.command_search_action.trigger()
    assert FavoriteStore(path).get("assembly") == ("sestava",)
    window.close()
