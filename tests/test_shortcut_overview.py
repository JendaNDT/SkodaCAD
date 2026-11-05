"""P7.45: přehled klávesových zkratek (F1) – čte se z příkazů okna, nic nemění."""

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAction, QKeySequence  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from skodacad.gui.command_search import collect_commands, plain_label  # noqa: E402
from skodacad.gui.main_window import MainWindow  # noqa: E402
from skodacad.gui.shortcut_overview import (  # noqa: E402
    LOCAL_ACTIONS,
    ShortcutDialog,
    collect_shortcuts,
    conflicts,
    local_keys,
)
from test_assembly_gui import dialogs, main_window, project  # noqa: E402, F401
from test_gui import FakeViewer, app  # noqa: E402, F401


@pytest.fixture
def window(app, examples_dir, tmp_path):  # noqa: F811
    model = tmp_path / "priruba.json"
    shutil.copy(examples_dir / "priruba.json", model)
    w = MainWindow(viewer_factory=FakeViewer, examples_dir=examples_dir, user_dir=tmp_path)
    assert w.open_model(model)
    w.resize(1400, 900)
    w.show()
    w.activateWindow()
    assert QTest.qWaitForWindowActive(w)
    yield w
    w.session.dirty = False
    w.close()


@pytest.fixture
def assembly(main_window, project):  # noqa: F811
    window = main_window.open_assembly(project / "sestavy" / "krabicka_s_vazbami.json")
    assert window is not None
    window.resize(1400, 900)
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)
    return window


def native(text):
    return QKeySequence(text).toString(QKeySequence.SequenceFormat.NativeText)


def open_overview(w, monkeypatch):
    """Stiskne skutečnou akci F1 a vrátí otevřený dialog (místo čekání na zavření)."""
    seen = []

    def record(dialog):
        seen.append(dialog)
        rows = [(r.place, r.keys, r.command) for r in dialog.rows]
        seen.append(rows)
        seen.append(dialog.shown_rows())
        dialog.filter.field.setText("ulozit")
        seen.append(dialog.shown_rows())
        seen.append(dialog.filter.note.text())
        QTest.keyClick(dialog.filter.field, Qt.Key.Key_Escape)
        seen.append(dialog.shown_rows())
        return 0

    monkeypatch.setattr(w, "_exec_dialog", record)
    w.shortcuts_action.trigger()
    assert len(seen) == 6, "akce F1 neotevřela přehled"
    return seen


def help_menu(w):
    menus = {plain_label(a.text()): a.menu() for a in w.menuBar().actions() if a.menu()}
    return menus["Nápověda"]


def unlisted(w, groups=()):
    listed = {id(c.action) for c in collect_commands(w.menuBar(), groups, include_hidden=True)}
    return sorted(a.text() for a in w.findChildren(QAction)
                  if not a.shortcut().isEmpty() and id(a) not in listed
                  and a.text() not in LOCAL_ACTIONS)


def test_part_overview_lists_menu_shortcuts_and_mouse_without_changes(window, monkeypatch):
    w = window
    before = (w.session.document.to_dict(), list(w.session._undo), w.session.dirty)
    assert w.shortcuts_action.shortcut().toString() == "F1"
    assert w.shortcuts_action in help_menu(w).actions()
    _dialog, rows, shown, filtered, note, cleared = open_overview(w, monkeypatch)
    assert ("Soubor", native("Ctrl+S"), "Uložit") in rows
    assert ("Soubor", native("Ctrl+Shift+S"), "Uložit jako") in rows
    assert ("Úpravy", native("Ctrl+F"), "Filtrovat strom prvků") in rows
    assert ("Zobrazení", native("F9"), "Strom modelu") in rows
    assert ("Nápověda", native("F1"), "Klávesové zkratky") in rows
    places = [row[0] for row in rows]
    assert places.index("Soubor") < places.index("Zobrazení") < places.index("Myš ve 3D")
    assert ("Myš ve 3D", local_keys("Alt+kolečko"), "Natočení přiložené NDT sondy o 15°") in rows
    assert any(row[0] == "Ve stromu a filtrech" and "panelu AI" in row[1] for row in rows)
    assert len(shown) == len(rows)  # bez filtru vše, nadpisy skupin se nepočítají
    assert {command for _keys, command in filtered} == {"Uložit", "Uložit jako"}
    assert note == f"Filtr: 2 z {len(rows)} zkratek. Esc filtr zruší."
    assert cleared == shown
    assert (w.session.document.to_dict(), list(w.session._undo), w.session.dirty) == before


def test_part_shortcuts_are_unique_and_all_listed(window):
    w = window
    assert conflicts(w.menuBar(), w.ribbon.command_groups) == {}
    assert unlisted(w, w.ribbon.command_groups) == []


def test_overview_follows_changed_shortcut(window):
    w = window
    w.save_action.setShortcut(QKeySequence("Ctrl+Alt+S"))
    rows = collect_shortcuts(w.menuBar(), w.ribbon.command_groups)
    assert [r.keys for r in rows if r.command == "Uložit"] == [native("Ctrl+Alt+S")]
    w.save_action.setShortcut(QKeySequence())
    rows = collect_shortcuts(w.menuBar(), w.ribbon.command_groups)
    assert all(r.command != "Uložit" for r in rows)  # bez zkratky v přehledu není


def test_assembly_overview_has_own_commands_and_tree_keys(assembly, monkeypatch):
    w = assembly
    before = (w.session.assembly.to_dict(), list(w.session._undo), w.session.dirty)
    assert w.shortcuts_action.shortcut().toString() == "F1"
    assert w.shortcuts_action in help_menu(w).actions()
    _dialog, rows, shown, filtered, note, cleared = open_overview(w, monkeypatch)
    assert ("Úpravy", native("Ctrl+L"), "Přidat vazbu") in rows
    assert ("Zobrazení", native("I"), "Izolovat vybrané") in rows
    assert ("Zobrazení", native("F8"), "Kontrola sestavy") in rows or any(
        row[1] == native("F8") for row in rows)
    assert ("Ve stromu a filtrech", local_keys("Ctrl/⌘+A ve stromu"),
            "Vybrat všechny komponenty (s filtrem jen nalezené)") in rows
    assert all("NDT" not in row[2] for row in rows)  # sestava nemá NDT sondu
    assert all(row[1] != "Pravý klik" for row in rows)  # sestava nemá místní nabídku ve 3D
    assert {command for _keys, command in filtered} == {"Uložit", "Uložit jako"}
    assert note.startswith("Filtr: 2 z ")
    assert cleared == shown
    assert (w.session.assembly.to_dict(), list(w.session._undo), w.session.dirty) == before


def test_assembly_shortcuts_are_unique_and_all_listed(assembly):
    assert conflicts(assembly.menuBar()) == {}
    assert unlisted(assembly) == []


def test_local_keys_per_platform():
    assert local_keys("Ctrl/⌘+klik", "darwin") == "⌘+klik"
    assert local_keys("Ctrl/⌘+klik", "win32") == "Ctrl+klik"
    assert local_keys("Alt+kolečko", "darwin") == "⌥+kolečko"
    assert local_keys("Alt+kolečko", "linux") == "Alt+kolečko"


def test_dialog_enter_jumps_to_first_match(app):  # noqa: F811
    from skodacad.gui.shortcut_overview import Shortcut

    dialog = ShortcutDialog([Shortcut("Ctrl+S", "Uložit", "Soubor"),
                             Shortcut("F", "Celý díl", "Zobrazení")])
    try:
        dialog.filter.field.setText("cely")
        assert dialog.shown_rows() == [("F", "Celý díl")]
        assert dialog.tree.topLevelItem(0).isHidden()  # skupina bez nalezených zmizí
        QTest.keyClick(dialog.filter.field, Qt.Key.Key_Return)
        assert dialog.tree.currentItem().text(1) == "Celý díl"
    finally:
        dialog.deleteLater()


def test_packaged_shortcuts_driver_part(window):
    from skodacad.gui.app import _self_test_shortcuts

    lines = []
    assert _self_test_shortcuts(window, lines, "díl", window.ribbon.command_groups), lines
    assert lines[-1].startswith("✓ Přehled zkratek (díl): F1")
    assert "_exec_dialog" not in window.__dict__  # ovladač vrátil původní dialogy


def test_packaged_shortcuts_driver_assembly(assembly):
    from skodacad.gui.app import _self_test_shortcuts

    lines = []
    assert _self_test_shortcuts(assembly, lines, "sestava"), lines
    assert lines[-1].startswith("✓ Přehled zkratek (sestava): F1")
    assert "_exec_dialog" not in assembly.__dict__
