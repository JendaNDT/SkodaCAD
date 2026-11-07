"""Spuštění aplikace ŠkodaCAD s oknem.

``skodacad-gui [model.json]``          – otevře okno (bez modelu otevře ukázku příruby)
``skodacad-gui --self-test zprava.txt`` – kontrola sestavené aplikace bez obsluhy
``skodacad-gui --screenshot okno.png``  – snímek okna (pro kontrolu v cloudu)
"""

from __future__ import annotations

import argparse
import faulthandler
import logging
import os
import sys
import tempfile
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from skodacad.session import ModelSession

log = logging.getLogger("skodacad")


def user_dir() -> Path:
    """Složka SkodaCAD v profilu uživatele (log, výchozí místo pro modely)."""
    base = os.environ.get("SKODACAD_HOME")
    path = Path(base) if base else Path.home() / "SkodaCAD"
    path.mkdir(parents=True, exist_ok=True)
    return path


def examples_dir() -> Path | None:
    """Ukázkové modely – v sestavené aplikaci jsou přibalené, při vývoji v repozitáři."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    folder = base / "examples"
    return folder if folder.is_dir() else None


def setup_logging() -> Path:
    log_path = user_dir() / "skodacad.log"
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger("build123d").setLevel(logging.WARNING)  # jinak píše každou operaci
    from skodacad.buildinfo import build_text

    log.info("Start %s, Python %s, %s", build_text(), sys.version.split()[0], sys.platform)
    return log_path


def _install_error_handler(log_path: Path) -> None:
    """Neočekávaná chyba: zapsat do logu a ukázat zprávu místo tichého pádu."""

    def handler(kind, value, tb) -> None:
        log.error("Neočekávaná chyba:\n%s", "".join(traceback.format_exception(kind, value, tb)))
        QMessageBox.critical(
            None, "Neočekávaná chyba",
            f"{kind.__name__}: {value}\n\nPodrobnosti jsou v souboru:\n{log_path}",
        )

    sys.excepthook = handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skodacad-gui", description="ŠkodaCAD – okno aplikace")
    parser.add_argument("model", nargs="?", type=Path, help="model k otevření (.json)")
    parser.add_argument("--self-test", type=Path, metavar="ZPRÁVA",
                        help="zkontroluj aplikaci a výsledek zapiš do souboru")
    parser.add_argument("--screenshot", type=Path, metavar="PNG",
                        help="po otevření ulož snímek okna a skonči")
    args = parser.parse_args(argv)

    log_path = setup_logging()
    if args.self_test:
        return run_self_test(args.self_test)

    from skodacad.worker import BackgroundRebuilder

    runner = BackgroundRebuilder()  # pomocný proces načítá jádro, zatímco se otevírá okno
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("ŠkodaCAD")
    _install_error_handler(log_path)

    from skodacad.gui.main_window import MainWindow

    window = MainWindow(examples_dir=examples_dir(), user_dir=user_dir(), runner=runner)
    window.show()

    def open_initial() -> None:
        if args.model:
            window.open_model(args.model)
        elif examples_dir() and (examples_dir() / "priruba.json").exists():
            window.open_model(examples_dir() / "priruba.json", template=True)

    QTimer.singleShot(0, open_initial)
    if args.screenshot:
        QTimer.singleShot(2500, lambda: _screenshot_when_done(window, args.screenshot))
    try:
        return app.exec()
    finally:
        runner.close()


def _screenshot_when_done(window, path: Path) -> None:
    """Snímek, až doběhne přepočet na pozadí (jinak by na něm byl jen „Přepočítávám…“)."""
    if window.session.computing:
        QTimer.singleShot(200, lambda: _screenshot_when_done(window, path))
        return
    _screenshot(window, path)
    QApplication.instance().quit()


def _screenshot(window, path: Path) -> None:
    window.viewer.fit_all()
    QApplication.processEvents()
    screen = window.screen()
    geometry = window.frameGeometry()
    image = screen.grabWindow(0, geometry.x(), geometry.y(), geometry.width(), geometry.height())
    image.save(str(path))
    log.info("Snímek okna uložen do %s", path)


class _Report(list):
    """Řádky zprávy self-testu – každý se hned zapíše do souboru, aby po pádu procesu
    (pád v knihovně OCCT nebo OpenGL) bylo vidět, kam test došel."""

    def __init__(self, stream) -> None:
        super().__init__()
        self.stream = stream

    def append(self, line: str) -> None:
        super().append(line)
        self.stream.write(line + "\n")
        self.stream.flush()
        log.info("Self-test: %s", line)

    def __iadd__(self, lines):
        for line in lines:
            self.append(line)
        return self


def run_self_test(report_path: Path) -> int:
    """Kontrola sestavené aplikace: jádro, exporty, ukázky a 3D prohlížeč."""
    with open(report_path, "w", encoding="utf-8") as stream:
        faulthandler.enable(stream, all_threads=True)  # pád procesu → kde se to stalo
        try:
            return _run_self_test(_Report(stream))
        finally:
            faulthandler.disable()


def _run_self_test(lines: _Report) -> int:
    ok = True
    try:
        import build123d
        import OCP
        import PySide6

        from skodacad.buildinfo import build_text

        lines += [
            build_text(),  # verze a sestavení (commit z GitHub Actions)
            f"Python {sys.version.split()[0]} ({sys.platform})",
            f"Open CASCADE (OCP) {OCP.__version__}, build123d {build123d.__version__}, "
            f"PySide6 {PySide6.__version__}",
        ]

        folder = examples_dir()
        if folder is None:
            ok = False
            lines.append("✕ Chybí složka s ukázkami")
            models = []
        else:
            models = sorted(folder.glob("*.json"))
        last_model = None
        with tempfile.TemporaryDirectory() as tmp:
            for model in models:
                session = ModelSession()
                result = session.open_template(model)
                if not result.ok:
                    ok = False
                    lines.append(f"✕ {model.name}: {result.first_error.message}")
                    continue
                for fmt in ("step", "stl", "3mf"):
                    session.export(Path(tmp) / f"{model.stem}.{fmt}")
                volume = session.properties.volume_mm3
                lines.append(f"✓ {model.name}: objem {volume:.0f} mm³, export STEP/STL/3MF")
                last_model = model
        references = sorted(folder.glob("ndt/*.json")) if folder is not None else []
        for model in references:  # referenční díly NDT: jen postavit
            result = ModelSession().open_template(model)
            if not result.ok:
                ok = False
                lines.append(f"✕ ndt/{model.name}: {result.first_error.message}")
        if references and ok:
            lines.append(f"✓ Referenční díly NDT: {len(references)} postaveno")
            ok = _self_test_ndt_geometry(folder / "ndt", lines) and ok

        ok = _self_test_window(lines, last_model) and ok
        ok = _self_test_background(models, lines) and ok
        ok = _self_test_step(lines) and ok
    except Exception:  # noqa: BLE001 – zpráva musí vzniknout i při nečekané chybě
        ok = False
        lines.append("✕ Neočekávaná chyba:\n" + traceback.format_exc())

    lines.append("VÝSLEDEK: OK" if ok else "VÝSLEDEK: CHYBA")
    return 0 if ok else 1


def _self_test_step(lines: list[str]) -> bool:
    """Přenos zdroje STEP a otevření modelu i v zabalené aplikaci."""
    from build123d import Align, Box, export_step

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        step = folder / "kvadr.step"
        export_step(Box(40, 30, 20, align=(Align.MIN,) * 3), step)
        session = ModelSession()
        session.new_document()
        session.add_step_import(step.read_bytes(), "kvadr.step")
        if not session.result.ok:
            lines.append(f"✕ Import STEP: {session.result.first_error.message}")
            return False
        path = session.save(folder / "model.json")
        reopened = ModelSession()
        reopened.open(path)
        part = reopened.result.part
        if (not reopened.result.ok or part is None or len(part.solids()) != 1
                or abs(part.volume - 24000) > 1e-5):
            lines.append("✕ Import STEP: po opětovném otevření nesouhlasí těleso nebo objem.")
            return False
        lines.append("✓ Import STEP: jedno těleso, objem 24000 mm³, uložení a otevření")
        return True


def _self_test_window(lines: list[str], model: Path | None) -> bool:
    """Otevře hlavní okno se skutečným 3D prohlížečem a v něm ukázku ``model`` (jako
    uživatel – přes ModelSession). Selhání OpenGL není chyba aplikace."""
    from skodacad.gui.favorite_commands import FavoriteStore
    from skodacad.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(["skodacad-gui"])
    window = MainWindow(examples_dir=examples_dir(), user_dir=user_dir(),
                        favorite_store=FavoriteStore())  # osobní lištu při zkoušce neměníme
    window.resize(900, 600)
    window.show()
    for _ in range(20):
        app.processEvents()
    viewer = window.viewer
    if model is not None:
        window.open_model(model, template=True)
    part = window.session.result.part if window.session.result else None
    app.processEvents()
    ok = True
    if viewer.ready:
        _check_render_size(viewer)
        image = user_dir() / "self-test-3d.png"
        lines.append(f"✓ Okno a 3D prohlížeč: OK (snímek {image}: {viewer.dump(str(image))}, "
                     f"OpenGL: {viewer.graphics_info()}"
                     f"{' – softwarové kreslení' if viewer.software else ''}; "
                     f"{viewer.scale_info()})")
        ok = (_self_test_drawing(viewer, lines) and _self_test_pick(window, part, lines)
              and _self_test_map(window, lines) and _self_test_section(window, lines))
    elif viewer.failed_stage in ("display", "opengl"):
        reason = "chybí obrazovka" if viewer.failed_stage == "display" else "OpenGL nejde spustit"
        lines.append(f"! Okno OK, 3D zobrazení tady nejde ({reason}): {viewer.error}")
    else:
        ok = False
        lines.append(f"✕ 3D prohlížeč: {viewer.failed_stage or 'nespuštěn'}: "
                     f"{viewer.error or 'okno se nezobrazilo'}")
    ok = _self_test_sketcher(window, lines) and ok
    ok = _self_test_assistant(window, lines) and ok
    ok = _self_test_ndt(window, lines) and ok
    ok = _self_test_audit(window, lines) and ok
    ok = _self_test_design(window, lines) and ok
    ok = _self_test_variable_fillet(window, lines) and ok
    ok = _self_test_loft_wall(window, lines) and ok
    ok = _self_test_guided_loft(window, lines) and ok
    ok = _self_test_workspace(window, lines) and ok
    ok = _self_test_cards(window, lines) and ok
    ok = _self_test_main_bar(window, lines) and ok
    ok = _self_test_model_card(window, lines) and ok
    ok = _self_test_inspector(window, lines) and ok
    ok = _self_test_status_pill(window, lines) and ok
    ok = _self_test_tool_cards(window, lines) and ok
    ok = _self_test_ndt_wizard(window, lines) and ok
    ok = _self_test_theme(window, lines) and ok
    ok = _self_test_feature_preview(window, lines) and ok
    ok = _self_test_feature_edit(window, lines) and ok
    ok = _self_test_plate_workflow(window, lines) and ok
    ok = _self_test_native_accessibility(lines) and ok
    ok = _self_test_viewer_lifecycle(window, lines) and ok
    ok = _self_test_command_search(window, lines, check_favorites=True) and ok
    ok = _self_test_tree_filter(window, lines) and ok
    ok = _self_test_param_filter(window, lines) and ok
    ok = _self_test_saved_filter(window, lines) and ok
    ok = _self_test_shortcuts(window, lines, "díl", window.ribbon.command_groups) and ok
    ok = _self_test_assembly(window, lines) and ok
    window.session.dirty = False
    window.close()
    return ok


def _self_test_command_search(window, lines, *, check_favorites=False) -> bool:
    """Native shortcut, keyboard search/cancel and one existing toggle in each window."""
    import copy

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from skodacad.gui.command_search import CommandSearchDialog

    assembly = hasattr(window.session, "assembly")
    title = "sestava" if assembly else "díl"
    action = window.files_action if assembly else window.workspace.collapse_action
    query = "zobrazeni"  # multiple results, accent-insensitive menu path in both windows
    original_checked = action.isChecked()
    favorites = window.favorite_bar
    original_pins = favorites.keys
    errors = []

    def snapshot():
        session = window.session
        model = session.assembly if assembly else session.document
        return (copy.deepcopy(model.to_dict()), session.result, session.dirty,
                list(session._undo), list(session._redo))

    def camera():
        view = window.viewer._view
        return (view.Proj(), view.At(), view.Eye(), view.Scale()) if view else None

    def activate():
        window.raise_()
        window.activateWindow()
        assert QTest.qWaitForWindowActive(window, 2000), "okno není aktivní pro klávesovou zkratku"
        # Let Qt deliver native focus restoration after the preceding modal dialog.
        QTest.qWait(100)

    def search(cancel, *, pin=False, recent=False, restored=""):
        activate()
        visited = []

        def choose():
            dialog = QApplication.activeModalWidget()
            try:
                assert isinstance(dialog, CommandSearchDialog), "hledání se neotevřelo zkratkou"
                visited.append(True)
                assert dialog.query.hasFocus(), "hledání nemá fokus"
                # P7.43: po Zrušit se vrátí označený text, po spuštění je pole prázdné.
                assert dialog.query.text() == restored, (
                    f"hledání ukazuje {dialog.query.text()!r}, očekáváno {restored!r}")
                assert dialog.query.selectedText() == restored, "obnovený text není označený"
                if recent:
                    if restored:
                        QTest.keyClick(dialog.query, Qt.Key.Key_Backspace)
                    assert not dialog.query.text(), f"Backspace nesmazal {dialog.query.text()!r}"
                    assert dialog.current_command().action is action, (
                        f"nahoře je {dialog.current_command().action.text()!r}")
                    assert dialog.results.currentItem().text(1).startswith("Nedávno · ")
                    QTest.keyClick(dialog.query, Qt.Key.Key_Return)
                    return
                QTest.keyClicks(dialog.query, query)
                matches = [dialog.results.topLevelItem(i)
                           for i in range(dialog.results.topLevelItemCount())]
                row = next(i for i, item in enumerate(matches)
                           if item.data(0, Qt.ItemDataRole.UserRole).action is action)
                assert row > 0, "scénář neověřuje pohyb mezi výsledky"
                current = dialog.results.indexOfTopLevelItem(dialog.results.currentItem())
                # Filtering preserves an existing selection; typing need not leave row zero.
                if current == row:
                    QTest.keyClick(dialog.query, Qt.Key.Key_Up)
                    current -= 1
                key = Qt.Key.Key_Down if row > current else Qt.Key.Key_Up
                for _ in range(abs(row-current)):
                    QTest.keyClick(dialog.query, key)
                assert dialog.current_command().action is action, (
                    f"šipky vybraly {dialog.current_command().action.text()!r}, "
                    f"očekáváno {action.text()!r}")
                if pin:
                    assert dialog.pin_button.isEnabled(), "příkaz nejde připnout"
                    QTest.mouseClick(dialog.pin_button, Qt.MouseButton.LeftButton)
                    assert dialog.isVisible() and dialog.results.currentItem().text(0).startswith(
                        "★ "), "připnutí nezůstalo v hledání"
                QTest.keyClick(dialog.query, Qt.Key.Key_Escape if cancel else Qt.Key.Key_Return)
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                if isinstance(dialog, CommandSearchDialog):
                    dialog.reject()

        timer = QTimer(window)
        timer.setSingleShot(True)
        timer.timeout.connect(choose)
        timer.start(150)
        QTest.keyClick(window, Qt.Key.Key_P,
                       Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        # If the shortcut failed there was no nested dialog loop to deliver choose().
        timer.stop()
        timer.deleteLater()
        mode = "Zopakovat" if recent else ("Připnout" if pin else
                                          ("Zrušit" if cancel else "Spustit"))
        assert visited and not errors, "; ".join(errors) or f"{mode}: zkratka neotevřela hledání"

    try:
        if check_favorites:
            assert favorites.store.path is None and not original_pins, "neizolovaná zkušební lišta"
        activate()
        before, view_before = snapshot(), camera()
        search(cancel=True, restored=getattr(window, "_command_search_text", ""))
        assert snapshot() == before and camera() == view_before, "Zrušit změnilo model nebo kameru"
        toggles = []
        action.toggled.connect(toggles.append)
        try:
            search(cancel=False, restored=query)
            assert toggles == [not original_checked], "příkaz se nespustil právě jednou"
            if check_favorites:
                search(cancel=True, pin=True)
                assert toggles == [not original_checked], "připnutí spustilo příkaz"
                QTest.qWait(60)
                button, = favorites.pinned_buttons()
                assert button.isVisible() and button.isChecked() == action.isChecked()
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                assert toggles == [not original_checked, original_checked]
                assert button.isChecked() == action.isChecked()
                search(cancel=False, recent=True, restored=query)
                assert toggles == [not original_checked, original_checked, not original_checked]
        finally:
            action.toggled.disconnect(toggles.append)
        assert snapshot() == before, "pohledový příkaz změnil model nebo historii"
        lines.append(f"✓ Hledání příkazů ({title}): zkratka, bez diakritiky, šipky, Esc beze změn, "
                     "Enter spustí existující příkaz jednou")
        lines.append(f"✓ Text hledání ({title}): po Zrušit se vrátí označený, "
                     "po spuštění příkazu je pole prázdné")
        if check_favorites:
            lines.append(f"✓ Oblíbené příkazy ({title}): připnutí z hledání bez spuštění, "
                         "tlačítko spustí původní příkaz jednou a přebírá jeho stav")
            lines.append(f"✓ Naposledy použité příkazy ({title}): Enter zopakuje poslední "
                         "příkaz bez psaní")
        return True
    except Exception as exc:
        lines.append(f"✕ Hledání příkazů ({title}): {exc}")
        return False
    finally:
        window._command_search_text = ""  # zkouška nemá ovlivnit další hledání
        if check_favorites and favorites.store.path is None:
            favorites.store.replace(favorites.kind, original_pins)
        if action.isChecked() != original_checked:
            action.trigger()


def _self_test_tree_filter(window, lines) -> bool:
    """P7.40: real Ctrl+F, typing, Enter and Esc in the feature tree filter."""
    import copy

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    tree, flt = window.tree, window.tree_filter
    previous = window._selected_id

    def snapshot():
        session = window.session
        return (copy.deepcopy(session.document.to_dict()), session.result, session.dirty,
                list(session._undo), list(session._redo))

    def rows():
        return [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]

    try:
        before, items = snapshot(), rows()
        assert len(items) >= 2, "strom nemá dost prvků pro zkoušku filtru"
        # Id prvku, které odpovídá právě jednomu řádku (nezávisle na otevřeném dílu).
        query = target = None
        for item in reversed(items):
            key = item.data(0, Qt.ItemDataRole.UserRole)
            flt.field.setText(key)
            if len(flt.visible_matches()) == 1:
                query, target = key, item
                break
        flt.clear()
        assert target is not None, "žádné id prvku není jednoznačné"
        tree.setCurrentItem(None)
        window.raise_()
        window.activateWindow()
        assert QTest.qWaitForWindowActive(window, 2000), "okno není aktivní pro zkratku"
        QTest.qWait(100)
        QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        assert flt.field.hasFocus(), "Ctrl+F nedalo fokus do filtru stromu"
        QTest.keyClicks(flt.field, query)
        shown = [item for item in rows() if not item.isHidden()]
        assert shown == [target], f"filtr ukazuje {len(shown)} řádků místo jednoho"
        assert flt.note.isVisible() and f"1 z {len(items)}" in flt.note.text()
        QTest.keyClick(flt.field, Qt.Key.Key_Return)
        assert tree.currentItem() is target and window._selected_id == query
        assert tree.hasFocus(), "Enter nepřesunul fokus do stromu"
        flt.focus()
        QTest.keyClick(flt.field, Qt.Key.Key_Escape)
        assert not flt.field.text() and not flt.note.isVisible()
        assert all(not item.isHidden() for item in rows()), "Esc neobnovil všechny řádky"
        assert rows() == items, "filtr změnil řádky stromu"
        assert snapshot() == before, "filtr změnil model nebo historii"
        lines.append(f"✓ Filtr stromu prvků: Ctrl+F, psaní, Enter vybere „{query}“, "
                     "Esc obnoví všech "
                     f"{len(items)} řádků beze změny modelu")
        return True
    except Exception as exc:
        lines.append(f"✕ Filtr stromu prvků: {exc}")
        return False
    finally:
        flt.clear()
        for item in rows():
            if item.data(0, Qt.ItemDataRole.UserRole) == previous:
                tree.setCurrentItem(item)
                break


def _self_test_shortcuts(window, lines, label: str, groups=()) -> bool:
    """P7.45: skutečná klávesa F1 otevře přehled zkratek; filtr, Esc, beze změny modelu."""
    import copy

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from skodacad.gui.shortcut_overview import conflicts

    session = window.session

    def snapshot():
        recipe = session.document if hasattr(session, "document") else session.assembly
        return (copy.deepcopy(recipe.to_dict()), session.dirty, list(session._undo),
                list(session._redo))

    seen = {}

    def inspect(dialog):
        rows = dialog.rows
        seen.setdefault("places", []).append(dialog.current_place())
        seen["commands"] = sum(row.place not in ("Myš ve 3D", "Ve stromu a filtrech")
                               for row in rows)
        seen["other"] = len(rows) - seen["commands"]
        seen["help"] = any(row.command == "Klávesové zkratky" for row in rows)
        everything = dialog.shown_rows()
        QTest.keyClicks(dialog.filter.field, "ulozit")
        seen["found"] = sorted(command for _keys, command in dialog.shown_rows())
        QTest.keyClick(dialog.filter.field, Qt.Key.Key_Escape)
        seen["restored"] = dialog.shown_rows() == everything == [
            (row.keys, row.command) for row in rows]
        return 0

    try:
        before = snapshot()
        clash = conflicts(window.menuBar(), groups)
        assert not clash, f"zkratky se opakují: {clash}"
        window._exec_dialog = inspect
        window.raise_()
        window.activateWindow()
        assert QTest.qWaitForWindowActive(window, 2000), "okno není aktivní pro F1"
        QTest.qWait(100)
        QTest.keyClick(window, Qt.Key.Key_F1)
        assert seen, "F1 neotevřela přehled zkratek"
        assert seen["help"], "v přehledu chybí vlastní zkratka F1"
        assert seen["commands"] >= 10 and seen["other"] >= 5, f"málo řádků: {seen}"
        assert seen["found"] == ["Uložit", "Uložit jako"], f"filtr našel {seen['found']}"
        assert seen["restored"], "Esc neobnovil všechny řádky přehledu"
        window.controls_action.trigger()  # Nápověda → Ovládání myší…
        assert seen["places"] == [None, "Myš ve 3D"], f"Ovládání myší: {seen['places']}"
        assert snapshot() == before, "přehled zkratek změnil model nebo historii"
        lines.append(f"✓ Přehled zkratek ({label}): F1, {seen['commands']} zkratek příkazů "
                     f"+ {seen['other']} ovládání myší a kláves, filtr „ulozit“ = 2, "
                     "Esc, Ovládání myší otevře skupinu Myš ve 3D, bez kolizí "
                     "a beze změny modelu")
        return True
    except Exception as exc:
        lines.append(f"✕ Přehled zkratek ({label}): {exc}")
        return False
    finally:
        window.__dict__.pop("_exec_dialog", None)


def _self_test_param_filter(window, lines) -> bool:
    """P7.42: real Ctrl+Shift+F, typing, Enter into the first field and Esc."""
    import copy

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    flt, form, fields = window.param_filter, window.params_form, window._param_fields
    section = window.sidebar_sections["parameters"]
    was_expanded = section.expanded

    def snapshot():
        session = window.session
        return (copy.deepcopy(session.document.to_dict()), session.result, session.dirty,
                list(session._undo), list(session._redo), dict(fields))

    def shown():
        return [name for name, field in fields.items() if form.isRowVisible(field)]

    try:
        before = snapshot()
        assert len(fields) >= 2, "díl nemá dost parametrů pro zkoušku filtru"
        query = next((name for name in reversed(fields)
                      if sum(name.casefold() in other.casefold() for other in fields) == 1
                      and not any(name.casefold() in f.text().casefold()
                                  for f in fields.values())), None)
        assert query is not None, "žádný název parametru není jednoznačný"
        section.set_expanded(False)
        window.raise_()
        window.activateWindow()
        assert QTest.qWaitForWindowActive(window, 2000), "okno není aktivní pro zkratku"
        QTest.qWait(100)
        QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.ShiftModifier)
        assert section.expanded, "Ctrl+Shift+F nerozbalilo Parametry dílu"
        assert flt.field.hasFocus(), "Ctrl+Shift+F nedalo fokus do filtru parametrů"
        QTest.keyClicks(flt.field, query)
        assert flt.field.text() == query, "zkratky okna pohltily písmena filtru"
        assert shown() == [query], f"filtr ukazuje {shown()} místo [{query}]"
        QTest.keyClick(flt.field, Qt.Key.Key_Return)
        assert fields[query].hasFocus(), "Enter nepřesunul fokus do pole parametru"
        flt.focus()
        QTest.keyClick(flt.field, Qt.Key.Key_Escape)
        assert not flt.field.text() and shown() == list(fields)
        assert snapshot() == before, "filtr změnil díl, historii nebo pole parametrů"
        lines.append(f"✓ Filtr parametrů: Ctrl+Shift+F rozbalí skupinu, psaní, Enter skočí "
                     f"do „{query}“, Esc obnoví všechny parametry ({len(fields)}) "
                     "beze změny dílu")
        return True
    except Exception as exc:
        lines.append(f"✕ Filtr parametrů: {exc}")
        return False
    finally:
        flt.clear()
        section.set_expanded(was_expanded)


def _self_test_saved_filter(window, lines) -> bool:
    """P7.44: saved measurement filter on the tube example (three saved measurements)."""
    import copy

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    flt, saved = window.saved_filter, window.saved_list

    def shown():
        return [saved.item(r).data(Qt.ItemDataRole.UserRole) for r in range(saved.count())
                if not saved.item(r).isHidden()]

    try:
        assert window.open_model(examples_dir() / "trubka.json", template=True)
        before = (copy.deepcopy(window.session.document.to_dict()), window.session.result,
                  list(window.session._undo))
        assert shown() == ["m1", "m2", "m3"], f"ukázka má měření {shown()}"
        window.raise_()
        window.activateWindow()
        assert QTest.qWaitForWindowActive(window, 2000), "okno není aktivní"
        QTest.qWait(100)
        QTest.keyClick(window, Qt.Key.Key_M,
                       Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        QTest.qWait(50)
        assert flt.field.hasFocus(), "Ctrl+Shift+M nedalo fokus do filtru uložených měření"
        QTest.keyClicks(flt.field, "tloustka")
        assert shown() == ["m1", "m2"], f"filtr ukazuje {shown()}"
        QTest.keyClick(flt.field, Qt.Key.Key_Return)
        assert window._current_saved_id() == "m1", "Enter nevybral první měření"
        flt.focus()
        QTest.keyClick(flt.field, Qt.Key.Key_Escape)
        assert shown() == ["m1", "m2", "m3"], "Esc neobnovil všechna měření"
        after = (copy.deepcopy(window.session.document.to_dict()), window.session.result,
                 list(window.session._undo))
        assert after == before, "filtr změnil díl nebo historii"
        lines.append("✓ Filtr uložených měření: Ctrl+Shift+M, trubka, „tloustka“ = 2 ze 3, "
                     "Enter vybere "
                     "první, Esc obnoví všechna beze změny dílu")
        return True
    except Exception as exc:
        lines.append(f"✕ Filtr uložených měření: {exc}")
        return False
    finally:
        flt.clear()


def _self_test_plate_workflow(window, lines) -> bool:
    """Reference plate through real fields, native mouse picking and session history."""
    import math

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    try:
        window.session.new_document("Ověření desky 80 × 50 × 10")
        for name, value in (("delka", "80"), ("sirka", "50"), ("tloustka", "10")):
            window.session.add_parameter(name, value)
        window._selected_id = None
        window._reload_all()
        window.resize(1400, 850)
        window.workspace.show_panel("editor")
        window.add_feature_actions["sketch"].trigger()

        def enter(field, value):
            field.setFocus()
            field.setText(value)
            QTest.keyClick(field, Qt.Key.Key_Return)

        shapes = window.feature_preview.editor.form.widget("elements")
        enter(shapes._form.widget("width"), "delka")
        enter(shapes._form.widget("height"), "sirka")
        window.feature_preview.accept_button.click()
        window.add_feature_actions["extrude"].trigger()
        enter(window.feature_preview.editor.form.widget("distance"), "tloustka")
        window.feature_preview.accept_button.click()
        assert window.session.result.ok
        assert abs(window.session.properties.volume_mm3 - 40000) < 1e-5
        viewer = window.viewer

        def click(point, toggle=False):
            x, y = viewer._view.Convert(*map(float, point))
            ratio = viewer._pixel_scale()
            modifiers = (Qt.KeyboardModifier.ControlModifier if toggle
                         else Qt.KeyboardModifier.NoModifier)
            QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, modifiers,
                             QPoint(round(x/ratio), round(y/ratio)))
            QApplication.processEvents()

        if viewer.ready:
            viewer.set_standard_view("top")
            viewer.fit_all()
            QApplication.processEvents()
            click((0, 0, 10))
            assert window.selection_actions["sketch"].isEnabled()
            window.workspace.show_panel("measure")
            window.selection_actions["sketch"].trigger()
            assert window.workspace.active == "editor"
            window.feature_preview.accept_button.click()
            assert window.session.document.features[-1]["type"] == "sketch"
            window.undo_action.trigger()  # selection test must leave the plate unchanged

        window.add_feature_actions["hole"].trigger()
        form = window.feature_preview.editor.form
        kind = form.widget("kind")
        kind.setCurrentIndex(kind.findData("clearance"))
        enter(form.widget("diameter"), "6")
        points = form.widget("positions")
        points.setFocus()
        points.setPlainText("-delka/2+10; -sirka/2+10\ndelka/2-10; -sirka/2+10\n"
                            "delka/2-10; sirka/2-10\n-delka/2+10; sirka/2-10")
        count = len(window.session._undo)
        QTest.keyClick(points, Qt.Key.Key_Tab)
        QTest.qWait(300)  # also let the input debounce run when the native window is inactive
        assert not points.hasFocus() and len(window.session._undo) == count
        assert window.feature_preview.accept_button.isEnabled(), (
            window.feature_preview.message.text())
        window.feature_preview.accept_button.click()
        assert len(window.session._undo) == count+1
        assert window.session.result.ok
        assert abs(window.session.properties.volume_mm3 - (40000-360*math.pi)) < 1e-5

        if viewer.ready:
            # Four external vertical corners; cylindrical seams must not be selected.
            for side, y in (("front", -25), ("back", 25)):
                viewer.set_standard_view(side)
                QApplication.processEvents()
                click((-40, y, 5), toggle=(side == "back"))
                click((40, y, 5), toggle=True)
            assert len(viewer.selected_shapes()) == 4
            window.workspace.show_panel("measure")
            window.selection_actions["fillet"].trigger()
            assert window.workspace.active == "editor"
            window.feature_preview.accept_button.click()
        else:
            for side in ("front", "back"):
                window.add_feature("fillet")
                fid = window._selected_id
                feature = window.session.feature(fid)
                feature["edges"] = {"face": side, "parallel": "Z"}
                window.session.update_feature(fid, feature)
                window._reload_all()
        expected = 39840 - 320*math.pi

        def verify(length, volume):
            assert window.session.result.ok and window.session.result.part.is_valid
            props = window.session.properties
            assert props.solids == 1 and abs(props.volume_mm3-volume) < 1e-5
            assert all(abs(a-b) < 1e-5
                       for a, b in zip(props.size_mm, (length, 50, 10), strict=True))

        verify(80, expected)
        enter(window._param_fields["delka"], "100")
        verify(100, expected+10000)
        window.undo_action.trigger()
        verify(80, expected)
        window.redo_action.trigger()
        verify(100, expected+10000)
        window.undo_action.trigger()
        path = user_dir() / "self-test-deska.json"
        assert window._save_to(path) and window.open_model(path)
        verify(80, expected)
        for fmt in ("step", "stl"):
            target = path.with_suffix("."+fmt)
            window.session.export(target)
            assert target.stat().st_size > 0
        if viewer.ready:
            viewer.set_standard_view("iso")
            viewer.fit_all()
            viewer.dump(str(path.with_suffix(".png")))
        lines.append("✓ Modelování desky: 80×50×10, čtyři Ø6 skrz, R2, "
                     "38834,690351 mm³, délka 100/80 a Zpět/Znovu, uložení/otevření, STEP/STL"
                     + (", Qt klik na plochu a čtyři hrany ve 3D" if viewer.ready else ""))
        return True
    except Exception:  # noqa: BLE001 -- include the exact assertion in the package report
        lines.append("✕ Modelování desky:\n" + traceback.format_exc())
        window.cancel_feature_preview()
        return False


def _self_test_feature_preview(window, lines) -> bool:
    """Real command buttons, pending invalid input, cancel and atomic confirmation."""
    import copy
    import math

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    try:
        window.session.new_document("Náhled nového prvku")
        window._selected_id = None
        window._reload_all()
        window.add_feature("sketch")
        window.add_feature("extrude")
        window.resize(1280, 760)
        before, result = copy.deepcopy(window.session.document), window.session.result
        count = len(window.session._undo)
        window.add_feature_actions["hole"].trigger()
        panel = window.feature_preview
        assert panel is not None
        field = panel.editor.form.widget("positions")
        field.setFocus()
        field.setPlainText("1+; 0")
        panel.accept()
        assert not panel.accept_button.isEnabled() and window.session.document == before
        panel.cancel_button.click()
        assert window.feature_preview is None and window.session.result is result
        assert window.session.document == before and len(window.session._undo) == count
        window.add_feature_actions["hole"].trigger()
        panel = window.feature_preview
        kind = panel.editor.form.widget("kind")
        kind.setCurrentIndex(kind.findData("clearance"))
        field = panel.editor.form.widget("diameter")
        field.setFocus()
        field.setText("6")
        QTest.keyClick(field, Qt.Key.Key_Return)
        assert panel.accept_button.isVisibleTo(window) and panel.accept_button.isEnabled()
        assert not window.save_action.isEnabled() and not window.undo_action.isEnabled()
        assert window.session.document == before and window.session.result is result
        QTest.mouseClick(panel.accept_button, Qt.MouseButton.LeftButton)
        assert window.feature_preview is None and len(window.session._undo) == count+1
        assert abs(window.session.properties.volume_mm3-(12000-90*math.pi)) < 1e-5
        window.undo_action.trigger()
        assert window.session.document == before
        window.redo_action.trigger()
        assert abs(window.session.properties.volume_mm3-(12000-90*math.pi)) < 1e-5
        window.session.save(user_dir()/"self-test-nahled-prvku.json")
        lines.append("✓ Náhled nového prvku: izolovaný díl a historie, neplatný rozepsaný "
                     "vstup, Zrušit, Qt klik Potvrdit, jeden krok Zpět/Znovu, "
                     "12000 → 11717,256661 mm³ a uložení")
        return True
    except Exception:  # noqa: BLE001 -- native package report includes the failing assertion
        lines.append("✕ Náhled nového prvku:\n" + traceback.format_exc())
        window.cancel_feature_preview()
        return False


def _self_test_feature_edit(window, lines) -> bool:
    """Native edit command, dependent geometry, cancel, confirm and save/reopen."""
    import copy
    import math

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    try:
        window.session.dirty = False
        assert window.open_model(examples_dir()/"deska_workflow.json", template=True)
        window._selected_id = "extrude1"
        window._reload_all()
        available = window.screen().availableGeometry()
        window.resize(min(1280, available.width()), min(800, available.height()-30))
        window.move(available.topLeft())
        window.workspace.show_panel("editor")
        QApplication.processEvents()
        assert window.feature_editor.form.widget("distance").isReadOnly()
        original, result = copy.deepcopy(window.session.document), window.session.result
        count = len(window.session._undo)
        QTest.mouseClick(window.edit_feature_button, Qt.MouseButton.LeftButton)
        panel = window.feature_preview
        assert panel.preview.editing
        field = panel.editor.form.widget("distance")
        for value in ("12", "15"):
            field.setFocus()
            field.selectAll()
            QTest.keyClicks(field, value)
            QTest.keyClick(field, Qt.Key.Key_Return)
            assert panel.preview.session.result.part.is_valid
            assert abs(panel.preview.session.properties.volume_mm3
                       - (3984-32*math.pi)*float(value)) < 2e-5
            assert window.session.document == original and window.session.result is result
        window.viewer.fit_all()
        QApplication.processEvents()
        assert panel.accept_button.isVisibleTo(window)
        _screenshot(window, user_dir()/"self-test-uprava-prvku.png")
        field.setText("1+")
        panel.accept()
        assert not panel.accept_button.isEnabled()
        QTest.mouseClick(panel.cancel_button, Qt.MouseButton.LeftButton)
        assert window.session.document == original and window.session.result is result
        assert len(window.session._undo) == count and not window.session.dirty
        window.edit_feature_action.trigger()
        panel = window.feature_preview
        field = panel.editor.form.widget("distance")
        field.setText("tloustka+5")
        QTest.keyClick(field, Qt.Key.Key_Return)
        QTest.mouseClick(panel.accept_button, Qt.MouseButton.LeftButton)
        expected = 59760-480*math.pi
        assert window.feature_preview is None and len(window.session._undo) == count+1
        assert abs(window.session.properties.volume_mm3-expected) < 2e-5
        assert all(abs(a-b) < 1e-6 for a, b in
                   zip(window.session.properties.size_mm, (80, 50, 15), strict=True))
        window.undo_action.trigger()
        assert window.session.document == original
        window.redo_action.trigger()
        path = window.session.save(user_dir()/"self-test-uprava-prvku.json")
        assert window.open_model(path) and window.session.result.part.is_valid
        assert abs(window.session.properties.volume_mm3-expected) < 2e-5
        window.start_feature_edit("sketch1")
        panel = window.feature_preview
        panel.editor.form.widget("elements")._form.widget("width").setText("5")
        panel.refresh()
        assert not panel.accept_button.isEnabled()
        assert panel.preview.session.result.first_error.id == "hole1"
        panel.cancel_button.click()
        assert abs(window.session.properties.volume_mm3-expected) < 2e-5
        lines.append("✓ Úprava prvku: Qt vstup a klik, izolovaný náhled, neplatný rozepsaný "
                     "vstup, navazující otvory/R2 a blokace při jejich chybě, Zrušit, "
                     "Potvrdit, jeden krok Zpět/Znovu, 80×50×15 mm / 58252,035526 mm³, "
                     "platné těleso, uložení/otevření a nativní snímek")
        return True
    except Exception:  # noqa: BLE001 -- report the exact assertion in the downloaded package
        lines.append("✕ Úprava prvku:\n" + traceback.format_exc())
        window.cancel_feature_preview()
        return False


def _self_test_native_accessibility(lines) -> bool:
    """Native Cocoa AX must not delete the live Qt interface of a table/list/tree."""
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtGui import QAccessible
    from PySide6.QtWidgets import (
        QListWidget,
        QTableWidget,
        QTableWidgetItem,
        QTreeWidget,
        QTreeWidgetItem,
    )

    from skodacad.gui.macos_accessibility import install, probe

    if not install():
        return True  # This ownership defect is specific to the Cocoa platform plugin.
    try:
        QAccessible.setActive(True)
        for _ in range(4):
            views = [QTreeWidget(), QListWidget(), QTableWidget(3, 2)]
            views[0].setHeaderLabels(["Prvek", "Tělesa"])
            for row in range(3):
                views[0].addTopLevelItem(QTreeWidgetItem([f"Prvek {row}", "1 → 1"]))
                views[1].addItem(f"Tvar {row}")
                for col in range(2):
                    views[2].setItem(row, col, QTableWidgetItem(f"{row}/{col}"))
            views[0].setCurrentItem(views[0].topLevelItem(0))
            views[1].setCurrentRow(0)
            views[2].setCurrentCell(0, 0)
            for view in views:
                view.show()
                QApplication.processEvents()
                for _query in range(3):
                    ident = QAccessible.uniqueId(QAccessible.queryAccessibleInterface(view))
                    assert probe(ident)
                    iface = QAccessible.accessibleInterface(ident)
                    assert iface is not None and iface.isValid()
                view.clear()
                QApplication.processEvents()
                view.close()
                view.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        lines.append("✓ Přístupnost macOS: 12 nativních seznamů/stromů/tabulek, "
                     "výběr a čtení AX, platná identita Qt, obnova a zničení bez pádu")
        return True
    except Exception as exc:  # noqa: BLE001 -- process exit also detects native SIGSEGV
        lines.append(f"✕ Přístupnost macOS: {type(exc).__name__}: {exc}")
        return False


def _self_test_viewer_lifecycle(window, lines) -> bool:
    """Destroy real native surfaces while Qt is alive, including Python reference cycles."""
    import gc

    from PySide6.QtCore import QDeadlineTimer, QEvent
    from PySide6.QtTest import QTest

    from skodacad.gui.viewer import OccViewer

    if not window.viewer.ready:
        lines.append("! Životnost 3D ploch: chybí grafický prohlížeč")
        return True
    try:
        for _ in range(4):
            viewer = OccViewer()
            try:
                viewer.resize(640, 480)
                viewer.show()
                deadline = QDeadlineTimer(5000)
                while not viewer.ready and not viewer.error and not deadline.hasExpired():
                    QTest.qWait(10)
                assert viewer.ready, viewer.error or "Nativní 3D plocha se do 5 s nespustila"
                _check_render_size(viewer)
                viewer.show_part(window.session.result.part, fit=True)
                viewer.resize(720, 520)
                QApplication.processEvents()
                _check_render_size(viewer)
                viewer.fit_all()
                assert viewer.dump(str(user_dir() / "self-test-zivotnost-3d.png"))
            finally:
                viewer.close()
                viewer.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                del viewer
                gc.collect()
                QApplication.processEvents()
        lines.append("✓ Životnost 3D ploch: 4× otevření, změna velikosti, plné rozlišení "
                     "OpenGL před exportem, kreslení, zavření a zničení nativního widgetu")
        return True
    except Exception as exc:  # noqa: BLE001 -- native crashes also fail the process exit code
        lines.append(f"✕ Životnost 3D ploch: {type(exc).__name__}: {exc}")
        return False


def _check_render_size(viewer) -> None:
    """Dump/fit_all nesmí před kontrolou opravit rozlišení nativní plochy."""
    surface = viewer._surface
    ratio = surface.devicePixelRatioF()
    expected = (round(surface.width() * ratio), round(surface.height() * ratio))
    actual = viewer.render_size()
    assert all(abs(a - e) <= 1 for a, e in zip(actual, expected, strict=True)), \
        f"OpenGL {actual}, očekáváno {expected} (Qt {surface.size()}, DPR {ratio})"


def _self_test_workspace(window, lines: list[str]) -> bool:
    """Native layout, real fields, geometry and history in each downloaded package."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from skodacad.gui.window_state import load_state

    try:
        window.session.dirty = False
        assert window.open_model(examples_dir() / "rizeny_prechod.json", template=True)
        window._selected_id = "rizeny"
        window._guide_edit_corner = window._guide_edit_handle = 0
        window._reload_all()
        window.resize(1280, 760)
        window.workspace.reset()
        QApplication.processEvents()
        original = window.session.document.to_dict()
        guides = window.feature_editor.form.widget("guides")
        for corner in range(4):
            guides.corner_picker.setCurrentIndex(corner)
            for handle in range(2):
                guides.handle_buttons.button(handle).click()
                QApplication.processEvents()
                assert guides.pages.currentIndex() == corner*2 + handle
                for axis in (0, 1):
                    field = guides.edits[corner, handle, axis]
                    assert field.isVisibleTo(guides) and field.width() >= 150
        for key in window.workspace.docks:
            window.workspace.show_panel(key)
            QApplication.processEvents()
            assert {k for k, dock in window.workspace.docks.items() if dock.isVisible()} == {key}
        assert window.session.document.to_dict() == original and not window.session.can_undo
        window.workspace.show_panel("editor")
        window.edit_feature_action.trigger()
        panel = window.feature_preview
        guides = panel.editor.form.widget("guides")
        guides.set_selection(0, 0)
        field = guides.edits[0, 0, 0]
        field.setText("4*Bx/3+1")
        field.setFocus()
        QTest.keyClick(field, Qt.Key.Key_Return)
        assert not window.session.can_undo
        panel.accept_button.click()
        assert window.session.result.ok and len(window.session._undo) == 1
        assert abs(window.session.result.part.volume - 78009) < 2e-5
        guides = window.feature_editor.form.widget("guides")
        guides.corner_picker.setCurrentIndex(3)
        guides.handle_buttons.button(1).click()
        window.undo_action.trigger()
        assert abs(window.session.result.part.volume - 77760) < 2e-5
        guides = window.feature_editor.form.widget("guides")
        assert guides.selected_index == 3 and guides.selected_handle == 1
        window.redo_action.trigger()
        assert abs(window.session.result.part.volume - 78009) < 2e-5
        window.session.save(user_dir() / "self-test-prostredi.json")
        window.resize(1024, 720)
        window.workspace.reset()
        QApplication.processEvents()
        assert window.model_dock.isHidden() and window.viewer.width() >= 600
        window.workspace.model_action.trigger()
        assert not window.model_dock.isHidden()
        window.workspace.close_panel()
        window.workspace.actions["editor"].trigger()
        assert window.workspace.active == "editor"
        window.ribbon.set_collapsed(True)
        assert window.ribbon.stack.isHidden()
        window.workspace.save()
        saved = load_state(window.workspace.path)
        assert saved["panel"] == "editor" and saved["ribbon_collapsed"]
        window.ribbon.set_collapsed(False)
        lines.append("✓ Prostředí CAD: pás příkazů, 8 pravých panelů, široká pole všech "
                     "rukojetí, 78009/77760 mm³ a historie, kompaktní okno 1024, obnova panelů "
                     "a oddělené nastavení okna")
        return True
    except Exception as exc:  # noqa: BLE001 -- package test must report a failure
        lines.append(f"✕ Prostředí CAD: {type(exc).__name__}: {exc}")
        return False


def _self_test_cards(window, lines: list[str]) -> bool:
    """P7.49: panely jako plovoucí karty nad nativním 3D (skutečné okno balíčku).

    Ověří rozmístění při 1440/1024/960, to, že karta leží nad 3D a klik vedle ní
    dál vybírá plochu, a že „Celý díl“ umístí díl do volného místa mezi kartami."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    viewer, layer = window.viewer, window.card_layer
    try:
        window.session.dirty = False
        assert window.open_model(examples_dir() / "deska.json", template=True)
        original = window.session.document.to_dict()
        sizes = []
        for width in (1440, 1024, 960):
            window.resize(width, 860)
            window.workspace.reset()
            window.workspace.show_panel("editor")
            QApplication.processEvents()
            layer.relayout()
            shown = [c for c in layer.cards if c.isVisible()]
            for card in shown:
                assert viewer.rect().contains(card.geometry()), card.objectName()
                assert card.parentWidget() is viewer
            for a in shown:
                for b in shown:
                    assert a is b or not a.geometry().intersects(b.geometry())
            free = layer.free_rect()
            assert free.width() >= .4 * viewer.width(), (width, free.width())
            sizes.append(f"{width}: 3D {free.width()}/{viewer.width()}")
        window.resize(1440, 860)
        window.workspace.reset()
        window.workspace.show_panel("editor")
        QApplication.processEvents()
        layer.relayout()
        card = window.editor_dock
        inside = card.geometry().center()
        hit = viewer.childAt(inside)
        assert hit is card or card.isAncestorOf(hit), "karta není nad 3D"
        clicked = ""
        if viewer.ready:
            viewer.set_standard_view("iso")
            viewer.fit_all()
            QApplication.processEvents()
            free = layer.free_rect()
            ratio = viewer._pixel_scale()
            part = window.session.result.part
            box = part.bounding_box()
            for x in (box.min.X, box.max.X):
                for y in (box.min.Y, box.max.Y):
                    for z in (box.min.Z, box.max.Z):
                        px, py = viewer._view.Convert(float(x), float(y), float(z))
                        point = QPoint(round(px / ratio), round(py / ratio))
                        assert free.contains(point), f"roh dílu {point} pod kartou"
            top = max(part.faces(), key=lambda f: f.center().Z)
            px, py = viewer._view.Convert(*map(float, top.center()))
            point = QPoint(round(px / ratio), round(py / ratio))
            assert viewer.childAt(point) is viewer._surface, "klik vedle karty nejde do 3D"
            QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.NoModifier, point)
            QApplication.processEvents()
            picked = viewer.selected_shapes()
            assert picked, "klik do 3D vedle karty nic nevybral"
            clicked = f", klik vedle karty vybral {window.session.selection_info(picked).text}"
            viewer.clear_selection()
            image = user_dir() / "self-test-karty.png"
            frame = window.frameGeometry()
            window.screen().grabWindow(0, frame.x(), frame.y(), frame.width(),
                                       frame.height()).save(str(image))
            clicked += f", snímek {image}"
        assert window.session.document.to_dict() == original
        lines.append(f"✓ Karty nad 3D: strom a {len(window.workspace.docks)} pravých panelů nad "
                     f"3D, bez překryvu ({'; '.join(sizes)}), díl mezi kartami{clicked}")
        return True
    except Exception as exc:  # noqa: BLE001 -- package test must report a failure
        lines.append(f"✕ Karty nad 3D: {type(exc).__name__}: {exc}")
        return False


def _self_test_main_bar(window, lines: list[str]) -> bool:
    """P7.50: hlavní lišta 52 px a plovoucí paleta – skutečné kliky myší v balíčku."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from skodacad.gui.main_bar import HEIGHT

    bar, ribbon, card, layer = window.main_bar, window.ribbon, window.palette_card, \
        window.card_layer
    try:
        window.session.dirty = False
        assert window.open_model(examples_dir() / "deska.json", template=True)
        original = window.session.document.to_dict()
        results = []
        for width in (1440, 1024, 960):
            window.resize(width, 860)
            window.workspace.reset()
            window.workspace.show_panel("editor")
            QApplication.processEvents()
            assert bar.height() == HEIGHT, f"lišta {bar.height()} px"
            tabs = ribbon.tabs
            assert bar.rect().contains(tabs.geometry()), "činnosti se do lišty nevešly"
            assert bar.rect().contains(bar.search.geometry().translated(
                bar.search.parentWidget().pos())), "hledání se do lišty nevešlo"
            index = tabs.count() - 1  # Zobrazení
            QTest.mouseClick(tabs, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                             tabs.tabRect(index).center())
            QApplication.processEvents()
            layer.relayout()
            assert ribbon.page == "view" and card.isVisible(), "činnost se nepřepnula"
            free = layer.free_rect()
            geometry = card.geometry()
            assert free.left() <= geometry.left() and geometry.right() <= free.right(), (
                f"paleta {geometry} mimo volné místo {free}")
            for other in layer.cards:
                assert other is card or other.isHidden() or not other.geometry().intersects(
                    geometry), f"paleta překrývá {other.objectName()}"
            results.append(f"{width}: paleta {geometry.width()} px")
        fired = []

        def count(_checked=False):
            fired.append(True)

        window.fit_action.triggered.connect(count)
        button = next(b for b in ribbon.buttons if b.defaultAction() is window.fit_action)
        try:
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            QApplication.processEvents()
        finally:
            window.fit_action.triggered.disconnect(count)
        assert fired == [True], "tlačítko palety nespustilo příkaz právě jednou"
        assert bar.title_label.text() == window.session.document.name
        if sys.platform == "darwin":
            assert window.unifiedTitleAndToolBarOnMac(), "semafor není v hlavní liště"
        ribbon.select_page("model")
        assert window.session.document.to_dict() == original
        lines.append(f"✓ Hlavní lišta a paleta: lišta {HEIGHT} px s činnostmi a hledáním, "
                     f"klik na činnost a na tlačítko palety, paleta mezi kartami "
                     f"({'; '.join(results)})")
        return True
    except Exception as exc:  # noqa: BLE001 -- package test must report a failure
        lines.append(f"✕ Hlavní lišta a paleta: {type(exc).__name__}: {exc}")
        return False


def _self_test_model_card(window, lines: list[str]) -> bool:
    """P7.51: levá karta Prvky | Parametry | Díl – skutečné kliky a zkratky v balíčku."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from skodacad.gui.model_card import ROW_HEIGHT

    tabs, pages = window.model_tabs.tabs, window.model_tabs
    try:
        window.session.dirty = False
        assert window.open_model(examples_dir() / "deska.json", template=True)
        original = window.session.document.to_dict()
        window.resize(1440, 860)
        window.workspace.reset()
        QApplication.processEvents()
        assert pages.current == "features" and window.tree.isVisible()
        rows = window.tree.topLevelItemCount()
        heights = {window.tree.visualItemRect(window.tree.topLevelItem(i)).height()
                   for i in range(rows)}
        assert min(heights) >= ROW_HEIGHT, f"řádky {heights} px"
        assert window.feature_count_label.text().startswith(str(rows))
        for index, widget in ((2, window.name_edit), (1, window.param_filter),
                              (0, window.tree)):
            QTest.mouseClick(tabs, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                             tabs.tabRect(index).center())
            QApplication.processEvents()
            assert widget.isVisible(), f"záložka {tabs.tabText(index)} neukázala obsah"
        window.activateWindow()
        QTest.qWaitForWindowActive(window, 2000)
        pages.select("part")
        QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.ShiftModifier)
        QApplication.processEvents()
        assert pages.current == "parameters", "Ctrl+Shift+F neotevřelo Parametry"
        QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        QApplication.processEvents()
        assert pages.current == "features", "Ctrl+F neotevřelo Prvky"
        QTest.keyClick(window.tree_filter.field, Qt.Key.Key_Escape)
        assert window.session.document.to_dict() == original
        lines.append(f"✓ Levá karta: záložky Prvky/Parametry/Díl klikem i zkratkami, "
                     f"{rows} řádků po {min(heights)} px, „{window.feature_count_label.text()}“")
        return True
    except Exception as exc:  # noqa: BLE001 -- package test must report a failure
        lines.append(f"✕ Levá karta: {type(exc).__name__}: {exc}")
        return False


def _self_test_inspector(window, lines: list[str]) -> bool:
    """P7.52: pravá karta – hlavička, patička, Esc a formulář bez posouvání (1440 × 900)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    try:
        window.session.dirty = False
        assert window.open_model(examples_dir() / "deska.json", template=True)
        original = window.session.document.to_dict()
        history = len(window.session._undo)
        window.resize(1440, 900)
        window.workspace.reset()
        hole = window.session.document.features[2]
        window._selected_id = hole["id"]
        window._reload_all()
        QApplication.processEvents()
        assert window.workspace.heading("editor") == hole["name"], "titulek karty"
        window.edit_feature_action.trigger()
        panel = window.feature_preview
        assert panel is not None, "úprava prvku se neotevřela"
        for _ in range(6):
            QApplication.processEvents()
            window.card_layer.relayout()
        menu = window.workspace.menu_buttons["editor"].text()
        assert menu == "Úprava prvku · náhled", menu
        footer = [panel.esc_hint, panel.refresh_button, panel.cancel_button, panel.accept_button]
        assert all(x.isVisible() for x in footer), "patička není vidět"
        xs = [x.mapTo(panel, x.rect().topLeft()).x() for x in footer]
        assert xs == sorted(xs), "pořadí patičky"
        card = window.editor_dock
        assert window.viewer.rect().contains(card.geometry()), "karta mimo 3D"
        fits = not panel.scroll.overflowing()
        height = card.geometry().height()
        panel.setFocus()
        QTest.keyClick(panel, Qt.Key.Key_Escape)  # Esc zahodí
        QApplication.processEvents()
        assert window.feature_preview is None, "Esc nezavřel náhled"
        assert window.session.document.to_dict() == original
        assert len(window.session._undo) == history
        lines.append(f"✓ Pravá karta: titulek „{hole['name']}“, náhled „{menu}“, patička Esc "
                     f"zahodí · Náhled · Zrušit · Potvrdit, Esc bez změny modelu "
                     f"(karta {height} px)")
        if not fits:
            lines.append(f"! Pravá karta: formulář díry se při 1440 × 900 nevešel, "
                         f"posuvník jako pojistka ({card.preferred_height()} px)")
        return True
    except Exception as exc:  # noqa: BLE001 -- package test must report a failure
        lines.append(f"✕ Pravá karta: {type(exc).__name__}: {exc}")
        if window.feature_preview is not None:
            window.cancel_feature_preview()
        return False


def _self_test_status_pill(window, lines: list[str]) -> bool:
    """P7.53: stavová pilulka a přepínač pohledů – skutečné kliky a kamera OCCT."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    viewer, layer, pill = window.viewer, window.card_layer, window.status_pill
    try:
        window.session.dirty = False
        assert window.open_model(examples_dir() / "deska.json", template=True)
        window.resize(1440, 900)
        window.workspace.reset()
        window.workspace.show_panel("editor")
        QApplication.processEvents()
        layer.relayout()
        assert window.statusBar().isHidden(), "stavový řádek je vidět (R5)"
        assert pill.state.text() == "✓ Spočítáno", pill.state.text()
        view = viewer.rect()
        cards = (window.pill_card, window.view_card)
        for card in cards:
            assert card.isVisible() and view.contains(card.geometry()), card.objectName()
            assert card.geometry().bottom() == view.bottom() - 14, card.objectName()
        assert not window.pill_card.geometry().intersects(window.view_card.geometry())
        details = ""
        if viewer.ready:
            buttons = window.view_switcher.buttons
            QTest.mouseClick(buttons["top"], Qt.MouseButton.LeftButton)
            QApplication.processEvents()
            direction = viewer._view.Proj()
            assert abs(direction[2] - 1) < 1e-6, f"Shora: směr kamery {direction}"
            assert window.view_switcher.active == "top"
            QTest.mouseClick(buttons["iso"], Qt.MouseButton.LeftButton)
            QTest.mouseClick(buttons["fit"], Qt.MouseButton.LeftButton)
            QApplication.processEvents()
            ratio = viewer._pixel_scale()
            limit = min(window.pill_card.geometry().top(), window.view_card.geometry().top())
            box = window.session.result.part.bounding_box()
            lowest = max(viewer._view.Convert(float(x), float(y), float(z))[1] / ratio
                         for x in (box.min.X, box.max.X) for y in (box.min.Y, box.max.Y)
                         for z in (box.min.Z, box.max.Z))
            assert lowest < limit, f"díl sahá pod pilulku ({lowest:.0f} ≥ {limit})"
            assert viewer.childAt(QPoint(view.center().x(), limit - 20)) is viewer._surface
            details = f", Shora = kamera +Z, díl nad pilulkou ({lowest:.0f} < {limit} px)"
        lines.append(f"✓ Pilulka a pohledy: „{pill.state.text()} | {pill.message}“, stavový "
                     f"řádek skrytý, přepínač Izo/Zepředu/Shora/Celý díl{details}")
        return True
    except Exception as exc:  # noqa: BLE001 -- package test must report a failure
        lines.append(f"✕ Pilulka a pohledy: {type(exc).__name__}: {exc}")
        return False


def _card_fits(card) -> int:
    """Šířka obsahu karty; obsah širší než karta by byl vpravo oříznutý (P7.54)."""
    scroll = card.widget()
    content = scroll.widget() if hasattr(scroll, "widget") and callable(scroll.widget) \
        else scroll
    assert content.width() <= scroll.viewport().width(), (
        f"{card.objectName()}: obsah {content.width()} px je širší než karta "
        f"{scroll.viewport().width()} px")
    return content.width()


def _self_test_tool_cards(window, lines: list[str]) -> bool:
    """P7.54: karty Měření, Řez a Mapa tloušťky a náhled prvku (rámy 3a–3c) – skutečná
    tlačítka a klávesa Esc, šířka obsahu se skutečným písmem systému."""
    from build123d import Vector
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from skodacad.gui.model_card import PREVIEW_ROLE

    pill, layer = window.status_pill, window.card_layer
    try:
        window.session.dirty = False
        assert window.open_model(examples_dir() / "deska.json", template=True)
        window.resize(1440, 900)
        window.workspace.reset()
        QApplication.processEvents()  # okno self-testu počítá synchronně
        part = window.session.result.part
        holes = [min(part.faces(), key=lambda f, x=x: f.distance_to(Vector(x, 0, 10)))
                 for x in (-16.6, 23.4)]  # stěny závitů M8 v ose X ±20 mm
        window.workspace.show_panel("measure")
        window._selection_changed([h.wrapped for h in holes])
        QApplication.processEvents()
        layer.relayout()
        first = window.measure_list.item(0).text()
        assert first == "Rozteč os: 40.00 mm", first
        assert pill.focus == ("measure", "Rozteč os 40.00 mm"), pill.focus
        window.measure_sections["drawing"].set_expanded(True)  # nejširší obsah karty
        QApplication.processEvents()
        layer.relayout()
        QApplication.processEvents()
        widths = [_card_fits(window.measure_dock)]
        window.measure_sections["drawing"].set_expanded(False)
        QTest.mouseClick(window.measure_buttons["save"], Qt.MouseButton.LeftButton)
        QApplication.processEvents()  # okno self-testu počítá synchronně
        assert window.saved_list.count() == 1, "Uložit nepřidalo měření"
        QTest.mouseClick(window.measure_buttons["delete"], Qt.MouseButton.LeftButton)
        QApplication.processEvents()  # okno self-testu počítá synchronně
        assert window.saved_list.count() == 0, "Smazat neodebralo měření"
        window._selection_changed([])

        window.workspace.show_panel("section")
        QTest.mouseClick(window.section_toggle, Qt.MouseButton.LeftButton)
        QApplication.processEvents()  # okno self-testu počítá synchronně
        assert window.session.section is not None, "zaškrtávátko řez nezapnulo"
        QApplication.processEvents()
        layer.relayout()
        QApplication.processEvents()
        widths.append(_card_fits(window.section_dock))
        area = window.section_area.text()
        assert pill.focus == ("section", "Řez · Y = 0 mm"), pill.focus
        QTest.mouseClick(window.section_toggle, Qt.MouseButton.LeftButton)
        QApplication.processEvents()  # okno self-testu počítá synchronně
        assert window.session.section is None and pill.focus is None

        window.workspace.show_panel("map")
        QApplication.processEvents()
        layer.relayout()
        QApplication.processEvents()
        widths.append(_card_fits(window.map_dock))

        part = window.session.result.part  # uložení měření díl přepočítalo
        before = (window.session.document.to_dict(), len(window.session._undo))
        top = min(part.faces(), key=lambda f: f.distance_to(Vector(0, 30, 15)))
        window.start_feature_preview("chamfer", shapes=[e.wrapped for e in top.edges()])
        rows = [window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())]
        assert rows and rows[-1].data(0, PREVIEW_ROLE), "strom nemá řádek náhledu"
        assert pill.focus and pill.focus[0] == "preview", pill.focus
        assert not window.ribbon.isEnabled(), "paleta je během náhledu aktivní"
        focus = pill.state.text()
        panel = window.feature_preview
        for _ in range(4):  # karta náhledu se ukáže a rozmístí jako u uživatele
            QApplication.processEvents()
            layer.relayout()
        panel.setFocus()
        QTest.keyClick(panel, Qt.Key.Key_Escape)  # Esc zahodí
        QApplication.processEvents()
        assert window.feature_preview is None, "Esc nezrušil náhled"
        assert not any(window.tree.topLevelItem(i).data(0, PREVIEW_ROLE)
                       for i in range(window.tree.topLevelItemCount()))
        assert window.ribbon.isEnabled() and pill.focus is None
        after = (window.session.document.to_dict(), len(window.session._undo))
        assert after == before, "zrušený náhled změnil model nebo historii"
        window.workspace.show_panel("editor")
        lines.append(f"✓ Karty nástrojů: měření „{first}“ v pilulce, Uložit/Smazat, řez "
                     f"{area} (zaškrtávátko, pilulka), náhled „{focus}“ s řádkem ve stromu "
                     f"a Esc; obsah karet {'/'.join(map(str, widths))} px se vejde")
        return True
    except Exception as exc:  # noqa: BLE001 -- package test must report a failure
        lines.append(f"✕ Karty nástrojů: {type(exc).__name__}: {exc}")
        if window.feature_preview is not None:
            window.cancel_feature_preview()
        return False


def _self_test_ndt_wizard(window, lines: list[str]) -> bool:
    """P7.55: NDT průvodce UT a skupina „NDT studie“ – skutečné kliky, přibalené vymezení
    UT, šířka obsahu karty se skutečným písmem."""
    from build123d import Vector
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from skodacad.gui.ndt_wizard import scope_text
    from skodacad.ndt import UT_DISCLAIMER

    panel, layer = window.ndt_panel, window.card_layer
    try:
        window.session.dirty = False
        assert window.open_model(examples_dir() / "ndt" / "deska.json", template=True)
        window.resize(1440, 900)
        window.workspace.reset()
        QApplication.processEvents()
        assert UT_DISCLAIMER in scope_text("UT"), "chybí přibalené vymezení UT (docs/ndt)"
        window.ribbon.select_page("ndt")
        studies = window.ndt_study_list
        QApplication.processEvents()
        layer.relayout()
        assert studies.isVisible() and studies.count() == 2, "skupina NDT studie v levé kartě"
        rect = studies.visualItemRect(studies.item(0))
        QTest.mouseClick(studies.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        QApplication.processEvents()
        assert panel.current_id() == "s1" and window.workspace.active == "ndt"
        wizard = panel.ut_wizard
        assert [step.kind for step in wizard.steps] == ["done", "done", "active", "future"]
        assert panel.warning.text() == UT_DISCLAIMER and panel.warning.isVisible()
        badge = window.workspace.badges["ndt"].text()
        part = window.session.result.part
        top = min(part.faces(), key=lambda f: f.distance_to(Vector(40, 0, 20)))
        window._selection_changed([top.wrapped])
        window.viewer.picked_point = (40.0, 0.0, 20.0)
        QApplication.processEvents()
        panel.place_action.trigger()
        QApplication.processEvents()
        assert window.session.ndt_placement.state == "ok", "sonda nedosedla"
        assert wizard.active == 2 and wizard.next.isEnabled()
        QTest.mouseClick(wizard.next, Qt.MouseButton.LeftButton)  # Další: pokrytí
        QApplication.processEvents()
        assert wizard.active == 3, "Další neotevřelo krok pokrytí"
        panel.coverage_step.setValue(25)
        panel.coverage_convergence.setChecked(False)
        panel.coverage_action.trigger()
        QApplication.processEvents()
        layer.relayout()
        QApplication.processEvents()
        covered = window.session.ndt_coverage.percent("covered")
        assert window.status_pill.focus == ("measure", f"● Pokryto {covered:.2f} %")
        assert panel.coverage_bar.bar.isVisible(), "pruh pokrytí není vidět"
        width = _card_fits(window.ndt_dock)
        window.session.clear_ndt_coverage()
        panel.remove_probe()
        # P7.56: PT a MT (kapsa) a RT (otvor) – stejné čtyři kroky, šířka karty
        assert window.open_model(examples_dir() / "ndt" / "kapsa.json", template=True)
        QApplication.processEvents()
        others = []
        for study, box in (("s2", panel.pt_box), ("s3", panel.mt_box)):
            panel.select(study)
            for _ in range(3):
                QApplication.processEvents()
                layer.relayout()
            kinds = [step.kind for step in box.steps]
            assert box.isVisible() and kinds == ["done", "done", "active", "future"], kinds
            others.append(_card_fits(window.ndt_dock))
        assert window.open_model(examples_dir() / "ndt" / "otvor.json", template=True)
        QApplication.processEvents()
        panel.select("s2")
        panel.rt_box.compute_action.trigger()
        for _ in range(3):
            QApplication.processEvents()
            layer.relayout()
        assert panel.rt_box.active == 3 and panel.rt_box.bar.bar.isVisible(), "RT mapa"
        others.append(_card_fits(window.ndt_dock))
        panel.rt_box.clear()  # Skrýt mapu
        window.ribbon.select_page("model")
        window.workspace.show_panel("editor")
        lines.append(f"✓ NDT průvodce: skupina studií v levé kartě (klik), {badge}, kroky "
                     f"hotovo/hotovo/aktivní/budoucí, přiložení, skutečné „Další: pokrytí“, "
                     f"pokryto {covered:.2f} % v pilulce i pruhu, vymezení UT přibalené, "
                     f"obsah karty {width} px se vejde; PT/MT/RT čtyři kroky, výpočet RT "
                     f"přejde na mapu s pruhem, karty {'/'.join(map(str, others))} px")
        return True
    except Exception as exc:  # noqa: BLE001 -- package test must report a failure
        lines.append(f"✕ NDT průvodce: {type(exc).__name__}: {exc}")
        return False


def _self_test_theme(window, lines: list[str]) -> bool:
    """P7.48: ikony Duo (QtSvg v balíčku), paleta z návrhu a tmavé pozadí 3D."""
    from PySide6.QtGui import QColor, QImage, QPalette

    from skodacad.gui import ui_theme
    from skodacad.gui.cad_icons import icon
    from skodacad.gui.duo_icons import DUO

    app = QApplication.instance()
    before = app.property("skodacadAppearance") or "system"
    try:
        for color in ("#0a64d8", "#4a9eff"):
            for name in DUO:
                image = icon(name, color).pixmap(24, 24).toImage()
                assert any(image.pixelColor(x, y).alpha() > 200 for x in range(24)
                           for y in range(24)), f"ikona {name} je prázdná"
        from skodacad.gui.viewer import BACKGROUNDS, _middle

        # Základní ovladač Windows bez grafické karty (GDI Generic, OpenGL 1.1 – sestavovací
        # počítač GitHubu) vrací ve snímku černé pozadí, i když OCCT drží barvy návrhu;
        # tam se pixely pozadí jen vypíšou („!“), jinde je self-test kontroluje přísně.
        basic = "GDI Generic" in window.viewer.graphics_info()
        backgrounds, seen = [], []
        for key, dark in (("dark", True), ("light", False)):
            window.workspace.appearance_actions[key].trigger()
            QApplication.processEvents()
            palette = app.palette()
            assert palette.color(QPalette.ColorRole.Window) == ui_theme.card_color(dark)
            assert palette.color(QPalette.ColorRole.Link).name() == ui_theme.tokens(dark)["accent"]
            assert window.viewer.dark_background is dark
            if window.viewer.ready:
                # Barvy, jak je drží OCCT, platí na každém ovladači.
                wanted = (*BACKGROUNDS[dark], _middle(*BACKGROUNDS[dark]))
                held = window.viewer.background_colors()
                assert held == wanted, f"pozadí 3D v OCCT {held}, návrh {wanted}"
                path = user_dir() / f"self-test-vzhled-{key}.png"
                assert window.viewer.dump(str(path))
                shot = QImage(str(path))
                w, h = shot.width(), shot.height()
                grid = [shot.pixelColor(x * (w - 1) // 15, y * (h - 1) // 15)
                        for x in range(16) for y in range(16)]
                corner = shot.pixelColor(w - 3, 3)  # pozadí vpravo nahoře
                points = [corner, shot.pixelColor(w - 3, h - 3), shot.pixelColor(w // 2, 3),
                          shot.pixelColor(w // 2, h // 2)]
                black = sum(c.rgb() & 0xFFFFFF == 0 for c in grid)
                seen.append(f"{key} {'/'.join(c.name(QColor.NameFormat.HexArgb) for c in points)}"
                            f" černých {black}/256 formát {shot.format().name} {w}×{h}")
                backgrounds.append(corner.lightness())
        info = f"{'; '.join(seen)}; OpenGL: {window.viewer.graphics_info()}"
        checked = len(backgrounds) == 2 and not basic
        if checked:
            assert backgrounds[0] < 110 < backgrounds[1], f"pozadí 3D {backgrounds} ({info})"
        font = app.font().family()
        shown = backgrounds if checked else ("bez 3D" if not seen else "barvy OCCT")
        lines.append(f"✓ Vzhled a ikony: 41 ikon Duo ve světlém i tmavém vzhledu, paleta "
                     f"z návrhu, pozadí 3D tmavé/světlé {shown}, písmo {font}")
        if seen and not checked:
            lines.append(f"! Vzhled a ikony: pozadí 3D na snímku neověřeno – základní ovladač "
                         f"bez grafické karty, ověřeny barvy nastavené v OCCT ({info})")
        return True
    except Exception as exc:  # noqa: BLE001 -- package test must report a failure
        lines.append(f"✕ Vzhled a ikony: {type(exc).__name__}: {exc}")
        return False
    finally:
        window.workspace.set_appearance(before)
        QApplication.processEvents()


def _self_test_variable_fillet(window, lines: list[str]) -> bool:
    """Stejná ukázka v zabalené aplikaci: směry, historie a skutečné značky ve 3D."""
    import math

    from skodacad.document import Document

    model = examples_dir() / "promenne_zaobleni.json"
    window.session.dirty = False
    try:
        if not window.open_model(model, template=True):
            raise ValueError("ukázku nejde otevřít")
        expected = 24000 - (1 - math.pi / 4) * 20 / 3 * (4 + 12 + 36)
        assert window.session.result.ok
        assert abs(window.session.result.part.volume - expected) < 2e-6
        feature = window.session.feature("zaobleni")
        feature["reverse"] = True
        window.session.update_feature("zaobleni", feature)
        assert window.session.feature_direction("zaobleni")[0][0].Z == 20
        window.session.undo()
        assert window.session.feature_direction("zaobleni")[0][0].Z == 0
        window.session.redo()
        path = user_dir() / "self-test-promenne-zaobleni.json"
        window.session.document.save(path)
        assert Document.load(path).to_dict()["version"] == 32
        window._selected_id = "zaobleni"
        window._reload_all()
        QApplication.processEvents()
        if window.viewer.ready:
            window.viewer.dump(str(user_dir() / "self-test-promenne-zaobleni.png"))
        lines.append("✓ Proměnné zaoblení: lineární R2 → R6, objem 23925,604697 mm³, "
                     "obrácení, Zpět/Znovu, uložení v32 a značky R1/R2")
        window.session.dirty = False
        return True
    except Exception as exc:  # noqa: BLE001 – uvést přesný důvod ve zprávě balíčku
        lines.append(f"✕ Proměnné zaoblení: {type(exc).__name__}: {exc}")
        window.session.dirty = False
        return False


def _self_test_guided_loft(window, lines: list[str]) -> bool:
    """Nová funkce, rukojeti, přesné čáry v prohlížeči, historie a zápis v34."""
    from skodacad.document import Document

    window.session.dirty = False
    try:
        assert window.open_model(examples_dir() / "rizeny_prechod.json", template=True)
        window._selected_id = "rizeny"
        window._reload_all()
        assert window.session.result.ok
        assert abs(window.session.result.part.volume - 77760) < 2e-5
        editor = window.feature_editor.form.widget("guides")
        editor.buttons.button(2).click()
        assert window.session.guided_loft_display("rizeny", 2)["selected"] == 2
        if window.viewer.ready:
            assert window.viewer._guide_objects
            QApplication.processEvents()
            window.viewer.dump(str(user_dir() / "self-test-rizeny-prechod.png"))
        window.edit_feature_action.trigger()
        panel = window.feature_preview
        edit = panel.editor.form.widget("guides").edits[0, 0, 0]
        edit.setText("12")
        edit.editingFinished.emit()
        panel.accept_button.click()
        assert window.session.result.ok
        assert abs(window.session.guided_loft_display("rizeny")["guides"][0]["curve"][20][0]
                   - 24) < 1e-6
        window.undo_action.trigger()
        assert abs(window.session.result.part.volume - 77760) < 2e-5
        window.redo_action.trigger()
        path = user_dir() / "self-test-rizeny-prechod.json"
        window.session.save(path)
        saved = Document.load(path)
        assert saved.to_dict()["version"] == 34
        assert saved.features[-1]["guides"][0]["controls"][0][0] == 12
        assert window.open_model(path)
        assert window.session.result.ok
        window.session.export(user_dir() / "self-test-rizeny-prechod.step")
        _self_test_guide_drag(window, lines)
        lines.append("✓ Řízený přechod: 77760 mm³, čtyři vodítka a řídicí polygon ve 3D, "
                     "úprava rukojeti, Zpět/Znovu, uložení/otevření v34 a STEP")
        return True
    except Exception as exc:  # noqa: BLE001 -- výsledek self-testu místo pádu aplikace
        lines.append(f"✗ Řízený přechod: {exc}")
        return False


def _self_test_guide_drag(window, lines: list[str]) -> None:
    """Skutečné Qt události přes nativní plochu a OCCT projekci, nikoli jen signál."""
    import copy

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    window._selected_id = "rizeny"
    window._guide_edit_corner = 0
    window._guide_edit_handle = 0
    window._reload_all()
    window.workspace.show_panel("editor")
    viewer = window.viewer
    if not viewer.ready:
        lines.append("! Tažení ve 3D: chybí grafický prohlížeč; session ověřují testy.")
        return
    window.resize(1400, 850)
    QApplication.processEvents()
    viewer.fit_all()
    QApplication.processEvents()

    def position():
        data = viewer._guides_data
        pole = data["guides"][data["selected"]]["poles"][1]
        x, y = viewer._view.Convert(*map(float, pole))
        ratio = viewer._pixel_scale()
        return QPoint(round(x/ratio), round(y/ratio))

    before = copy.deepcopy(window.session.document)
    result, undo = window.session.result, len(window.session._undo)
    start = position()
    QTest.mousePress(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
    assert viewer._guide_drag is not None, "Rukojeť se nepodařilo uchopit."
    end = start + QPoint(-24, 0)
    QTest.mouseMove(viewer._surface, end)
    assert window.session.document == before and window.session.result is result
    assert len(window.session._undo) == undo
    QTest.mouseRelease(viewer._surface, Qt.MouseButton.LeftButton, pos=end)
    assert viewer._guide_drag is None and window.session.result.ok
    assert window.session.document != before and len(window.session._undo) == undo+1
    moved = copy.deepcopy(window.session.document)
    window.undo_action.trigger()
    assert window.session.document == before
    window.redo_action.trigger()
    assert window.session.document == moved
    start = position()
    QTest.mousePress(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
    assert viewer._guide_drag is not None
    QTest.mouseMove(viewer._surface, start + QPoint(12, 0))
    QTest.keyClick(viewer._surface, Qt.Key.Key_Escape)
    QTest.mouseRelease(viewer._surface, Qt.MouseButton.LeftButton, pos=start + QPoint(12, 0))
    assert viewer._guide_drag is None and window.session.document == moved
    assert len(window.session._undo) == undo+1
    window.session.save(user_dir() / "self-test-tazeni-rukojeti.json")
    viewer.dump(str(user_dir() / "self-test-tazeni-rukojeti.png"))
    lines.append("✓ Tažení rukojeti ve 3D: Qt události, OCCT projekce XY, náhled bez změny "
                 "modelu, jeden krok Zpět/Znovu a zrušení Esc")

    before = copy.deepcopy(window.session.document)
    result, undo = window.session.result, len(window.session._undo)
    control = window.feature_editor.form.widget("guides").drag_step
    control.setValue(1.)
    assert window.session.document == before and window.session.result is result
    assert len(window.session._undo) == undo and viewer._guide_drag_step == 1.
    pole = viewer._guides_data["guides"][viewer._guides_data["selected"]]["poles"][1]
    start = position()
    QTest.mousePress(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
    assert viewer._guide_drag is not None
    end = start + QPoint(-24, 0)
    QTest.mouseMove(viewer._surface, end)
    delta = list(viewer._guide_drag["delta"])
    assert any(delta) and all(v == round(v) for v in delta)
    assert window.session.document == before and window.session.result is result
    QTest.mouseRelease(viewer._surface, Qt.MouseButton.LeftButton, pos=end)
    assert window.session.result.ok and len(window.session._undo) == undo+1
    actual = viewer._guides_data["guides"][viewer._guides_data["selected"]]["poles"][1]
    assert abs(actual[0]-pole[0]-delta[0]) < 1e-8
    assert abs(actual[1]-pole[1]-delta[1]) < 1e-8 and actual[2] == pole[2]
    moved = copy.deepcopy(window.session.document)
    window.undo_action.trigger()
    assert window.session.document == before
    assert window.feature_editor.form.widget("guides").drag_step.value() == 1.
    window.redo_action.trigger()
    assert window.session.document == moved
    result, undo = window.session.result, len(window.session._undo)
    control = window.feature_editor.form.widget("guides").drag_step
    control.setValue(.1)
    assert viewer._guide_drag_step == .1
    control.setValue(0.)
    assert "Volně" in control.text() and viewer._guide_drag_step == 0.
    assert window.session.document == moved and window.session.result is result
    assert len(window.session._undo) == undo
    window.session.save(user_dir() / "self-test-krok-tazeni.json")
    lines.append("✓ Krok tažení: ovládání 1 mm / 0,1 mm / Volně, stejné přichycení náhledu "
                 "a výsledku, pevné Z, jeden krok Zpět/Znovu, volba beze změny receptu")

    for direction, view in (("X", "front"), ("Y", "right")):
        before = copy.deepcopy(window.session.document)
        result, undo = window.session.result, len(window.session._undo)
        editor = window.feature_editor.form.widget("guides")
        editor.drag_step.setValue(1.)
        editor.drag_direction.setCurrentIndex(editor.drag_direction.findData(direction))
        assert window.session.document == before and window.session.result is result
        viewer.set_standard_view(view)
        QApplication.processEvents()
        pole = viewer._guides_data["guides"][viewer._guides_data["selected"]]["poles"][1]
        start = position()
        QTest.mousePress(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
        assert viewer._guide_drag is not None, f"Osa {direction} není uchopitelná v {view}."
        end = start + QPoint(24, 0)
        QTest.mouseMove(viewer._surface, end)
        delta = list(viewer._guide_drag["delta"])
        active, inactive = (0, 1) if direction == "X" else (1, 0)
        assert delta[inactive] == 0 and abs(delta[active]) >= 1
        assert delta[active] == round(delta[active])
        assert window.session.document == before and window.session.result is result
        QTest.mouseRelease(viewer._surface, Qt.MouseButton.LeftButton, pos=end)
        assert window.session.result.ok and len(window.session._undo) == undo+1
        actual = viewer._guides_data["guides"][viewer._guides_data["selected"]]["poles"][1]
        assert abs(actual[active]-pole[active]-delta[active]) < 1e-8
        assert actual[inactive] == pole[inactive] and actual[2] == pole[2]
        assert window.session.document.features[-1]["guides"][0]["controls"][0][inactive] == \
            before.features[-1]["guides"][0]["controls"][0][inactive]
        moved = copy.deepcopy(window.session.document)
        window.undo_action.trigger()
        assert window.session.document == before
        window.redo_action.trigger()
        assert window.session.document == moved
        editor = window.feature_editor.form.widget("guides")
        assert editor.drag_direction.currentData() == direction and editor.drag_step.value() == 1.
    before = copy.deepcopy(window.session.document)
    editor.drag_direction.setCurrentIndex(editor.drag_direction.findData("XY"))
    assert viewer._guide_drag_direction == "XY" and window.session.document == before
    viewer.set_standard_view("iso")
    window.session.save(user_dir() / "self-test-smer-tazeni.json")
    viewer.dump(str(user_dir() / "self-test-smer-tazeni.png"))
    lines.append("✓ Směr tažení: pouze X zepředu / pouze Y zprava / XY, krok 1 mm, "
                 "pevné Z a druhá souřadnice, jeden krok Zpět/Znovu, volba beze změny receptu")


def _self_test_loft_wall(window, lines: list[str]) -> bool:
    """Výslovné režimy přes skutečný formulář, historie a zápis v33 v balíčku."""
    import math

    from skodacad.document import Document

    window.session.dirty = False
    try:
        assert window.open_model(examples_dir() / "loft_stena.json", template=True)
        window._selected_id = "prechod"
        window._reload_all()
        form = window.feature_editor.form
        combo = form.widget("wall_mode")
        assert combo.count() == 2 and combo.currentData() == "normal"
        wall_panel = window.feature_editor.wall_panel
        wall_panel.button.click()
        report = window.session.loft_wall_report("prechod")
        assert report is not None and report.counts["nominal"] == 25
        wall_panel.table.setCurrentCell(0, 0)
        assert window.session.loft_wall_measurement("prechod", 0)
        lines.append("✓ CAD přehled stěny: 25 normálových měření 3 mm, tabulka a značka ve 3D")
        shift = 3 * math.sqrt(1 + 1 / 9)
        normal_volume = math.pi * 60 * (60 * shift - shift**2)
        assert window.session.result.ok
        assert abs(window.session.result.part.volume - normal_volume) < 2e-5
        QApplication.processEvents()
        if window.viewer.ready:
            window.viewer.dump(str(user_dir() / "self-test-stena-loftu.png"))
        combo.setCurrentIndex(combo.findData("sections"))
        assert abs(window.session.result.part.volume - math.pi * 10260) < 2e-5
        assert window.session.loft_wall_report("prechod") is None
        wall_panel.button.click()
        report = window.session.loft_wall_report("prechod")
        assert report is not None and report.counts["below"] == 25
        assert all(abs(t - 3 / math.sqrt(1 + 1 / 9)) < 2e-5 for t in report.lengths)
        window.undo_action.trigger()
        assert window.session.feature("prechod")["wall_mode"] == "normal"
        window.redo_action.trigger()
        assert window.session.feature("prechod")["wall_mode"] == "sections"
        path = user_dir() / "self-test-stena-loftu.json"
        window.session.document.save(path)
        saved = Document.load(path)
        assert saved.to_dict()["version"] == 33
        assert saved.features[-1]["wall_mode"] == "sections"
        window.session.dirty = False
        assert window.open_model(examples_dir() / "vysypka.json", template=True)
        assert window.session.result.ok and "wall_mode" not in window.session.feature("vysypka")
        assert abs(window.session.result.part.volume - 908807.4817089331) < 2e-5
        lines.append("✓ Stěna přechodu: kolmo / v rovinách skic, formulář, Zpět/Znovu, "
                     "zápis v33 a zachovaná geometrie staré výsypky")
        return True
    except Exception as exc:  # noqa: BLE001 – důvod uvést ve zprávě balíčku
        lines.append(f"✕ Stěna přechodu: {type(exc).__name__}: {exc}")
        return False
    finally:
        window.session.dirty = False


def _self_test_assembly(window, lines: list[str]) -> bool:
    """Zabalená aplikace: ukázková sestava v okně sestavy se skutečným 3D prohlížečem
    (díly se počítají synchronně – pomocné procesy prověřuje samostatná část)."""
    folder = examples_dir()
    sample = folder / "sestavy" / "krabicka_s_vickem.json" if folder is not None else None
    if sample is None or not sample.is_file():
        lines.append("✕ Sestava: chybí ukázka sestavy (examples/sestavy)")
        return False
    app = QApplication.instance()
    assembly = window.open_assembly(sample, template=True)
    if assembly is None:
        lines.append("✕ Sestava: ukázku nejde otevřít")
        return False
    for _ in range(10):
        app.processEvents()
    result = assembly.session.result
    ok = (result is not None and result.complete and len(result.instances) == 6
          and abs(result.volume_mm3 - 31309.287) < 0.01)
    drawn = ""
    if ok and assembly.viewer.ready:
        _check_render_size(assembly.viewer)
        image = user_dir() / "self-test-sestava.png"
        drawn = f", 3D snímek {image}: {assembly.viewer.dump(str(image))}"
    if ok:
        lines.append(f"✓ Sestava: {result.volume_mm3:.0f} mm³, 6 komponent, víčko z = 26…32"
                     f"{drawn}")
        ok = _self_test_assembly_layout(assembly, lines) and ok
        ok = _self_test_command_search(assembly, lines, check_favorites=True) and ok
        ok = _self_test_assembly_tree_filter(assembly, lines) and ok
        ok = _self_test_shortcuts(assembly, lines, "sestava") and ok
        ok = _self_test_assembly_views(assembly, lines) and ok
        ok = _self_test_assembly_isolation(assembly, lines) and ok
        ok = _self_test_assembly_visibility(assembly, lines) and ok
        ok = _self_test_assembly_transparency(assembly, lines) and ok
        ok = _self_test_assembly_transparency_levels(assembly, lines) and ok
        ok = _self_test_assembly_multi_selection(assembly, lines) and ok
        ok = _self_test_assembly_motion_panel(assembly, lines) and ok
        ok = _self_test_assembly_batch_move(assembly, lines) and ok
        ok = _self_test_assembly_selection_drag(assembly, lines) and ok
        ok = _self_test_assembly_batch_move(assembly, lines, single=True) and ok
        ok = _self_test_assembly_selection_drag(assembly, lines, single=True) and ok
        ok = _self_test_assembly_batch_rotation(assembly, lines) and ok
        ok = _self_test_assembly_rotation_handles(assembly, lines) and ok
        ok = _self_test_assembly_rotation_handles(assembly, lines, custom=True) and ok
        ok = _self_test_rotation_center_pick(assembly, lines) and ok
        ok = _self_test_cylinder_rotation_axis(assembly, lines) and ok
        ok = _self_test_cylinder_rotation_axis(assembly, lines, kind="line") and ok
        ok = _self_test_cylinder_rotation_axis(assembly, lines, kind="plane") and ok
        ok = _self_test_cylinder_rotation_axis(assembly, lines, kind="vertices") and ok
        for custom in (False, True):
            ok = _self_test_assembly_rotation_handles(
                assembly, lines, custom=custom, single=True) and ok
        for kind in ("cylinder", "line", "plane", "vertices"):
            ok = _self_test_cylinder_rotation_axis(
                assembly, lines, kind=kind, single=True) and ok
    else:
        lines.append(f"✕ Sestava: {'; '.join(result.problems) if result else 'bez výsledku'}")
    assembly.session.dirty = False
    assembly.close()
    ok = _self_test_constraints(window, lines, folder) and ok
    return _self_test_checks(window, lines, folder) and ok


def _self_test_assembly_tree_filter(window, lines) -> bool:
    """P7.41: real Ctrl+F/typing/Enter/Esc/Ctrl+A in the component tree filter."""
    import copy
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    tree, flt = window.tree, window.tree_filter
    previous = window._selection

    def snapshot():
        session = window.session
        return (copy.deepcopy(session.assembly.to_dict()), session.result, session.dirty,
                list(session._undo), list(session._redo), dict(window._visibility),
                window._isolated, len(window.visible_instances()))

    def components():
        found = []

        def walk(item):
            if isinstance(json.loads(item.data(0, Qt.ItemDataRole.UserRole)), list):
                found.append(item)
            for index in range(item.childCount()):
                walk(item.child(index))

        for index in range(tree.topLevelItemCount()):
            walk(tree.topLevelItem(index))
        return found

    def shown(item):  # řádek i všichni jeho rodiče jsou vidět
        while item is not None:
            if item.isHidden():
                return False
            item = item.parent()
        return True

    try:
        before, rows = snapshot(), components()
        assert len(rows) >= 2, "sestava nemá dost komponent pro zkoušku filtru"
        query = target = None
        window.select(None)
        for item in reversed(rows):  # id komponenty, které odpovídá právě jednomu řádku
            path = json.loads(item.data(0, Qt.ItemDataRole.UserRole))
            flt.field.setText(path[-1])
            if [m for m in flt.visible_matches() if m in rows] == [item]:
                query, target = path, item
                break
        flt.clear()
        assert target is not None, "žádné id komponenty není jednoznačné"
        window.raise_()
        window.activateWindow()
        assert QTest.qWaitForWindowActive(window, 2000), "okno sestavy není aktivní"
        QTest.qWait(100)
        QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        assert flt.field.hasFocus(), "Ctrl+F nedalo fokus do filtru komponent"
        QTest.keyClicks(flt.field, query[-1])
        assert flt.field.text() == query[-1], "zkratky okna pohltily písmena filtru"
        assert [m for m in flt.visible_matches() if m in rows] == [target] and shown(target)
        assert sum(map(shown, components())) < len(rows), "filtr nic neskryl"
        QTest.keyClick(flt.field, Qt.Key.Key_Return)
        assert window._selection == (tuple(query),) and tree.hasFocus()
        flt.field.setText("zzz-nenalezeno")  # nic neodpovídá, vybraný řádek zůstane vidět
        assert flt.visible_matches() == [] and shown(target)
        window.select(None)
        assert not any(map(shown, components())), "nevybrané neodpovídající řádky jsou vidět"
        flt.clear()
        tree.setFocus()
        QTest.keyClick(tree, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        assert len(window._selection) == len(rows), "Ctrl+A bez filtru nevybralo vše"
        flt.field.setText(query[-1])
        tree.setFocus()
        QTest.keyClick(tree, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        assert window._selection == (tuple(query),), "Ctrl+A s filtrem vybralo i skryté"
        flt.focus()
        QTest.keyClick(flt.field, Qt.Key.Key_Escape)
        assert not flt.field.text() and all(map(shown, components()))
        window.select_many(previous)
        assert snapshot() == before, "filtr změnil sestavu, historii, viditelnost nebo 3D"
        lines.append(f"✓ Filtr stromu komponent: Ctrl+F, psaní, Enter vybere „{query[-1]}“, "
                     "vybraný řádek zůstane vidět, Ctrl+A jen nalezené, Esc obnoví "
                     f"{len(rows)} komponent beze změny sestavy")
        return True
    except Exception as exc:
        lines.append(f"✕ Filtr stromu komponent: {exc}")
        return False
    finally:
        flt.clear()
        window.select_many(previous)


def _self_test_assembly_layout(assembly, lines) -> bool:
    """Prostor pro 3D, čitelná pole a Enter v novém rozložení, bez ztráty historie."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    try:
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(100)  # native window activation/layout is asynchronous, notably on Windows
        before = assembly.session.assembly.to_dict()
        widths = []
        actual_widths = []
        for width in (1200, 1024):
            assembly.resize(width, 720)
            assembly.reset_layout()
            QTest.qWait(100)
            actual_width = assembly.width()  # native Windows can cap windows to its desktop
            minimum = actual_width - 580  # 250 + 300 for panels, at most 30 for separators
            assert actual_width >= 960, f"skutečné okno {actual_width} < 960"
            fields = [e.width() for e in [*assembly.position_edits, *assembly.rotation_edits]]
            assert assembly.viewer.width() >= minimum, (
                f"3D {assembly.viewer.width()} < {minimum}; požadované okno {width}, "
                f"skutečné {assembly.width()}, panely "
                f"{assembly.tree_dock.width()}/{assembly.component_dock.width()}")
            assert assembly.tree.columnWidth(0) >= 140, (
                f"sloupec názvu {assembly.tree.columnWidth(0)}")
            assert all(w >= 90 for w in fields), f"šířky polí {fields}"
            assert assembly.checks_dock.isHidden(), "kontroly zůstaly viditelné po resetu"
            if assembly.viewer.ready:
                _check_render_size(assembly.viewer)
            widths.append(assembly.viewer.width())
            actual_widths.append(actual_width)
        assembly.select(("vicko",))

        def lid_x():
            return next(i.part.bounding_box().min.X for i in assembly.session.result.instances
                        if i.ids == ("vicko",))

        original = lid_x()
        field = assembly.position_edits[0]
        field.setFocus()
        QTest.qWait(100)
        field.setText("1,5")
        QTest.keyClick(field, Qt.Key.Key_Return)
        QApplication.processEvents()
        moved = lid_x()
        assert abs(moved - original - 1.5) < 1e-7, (
            f"Enter: X {original} → {moved}, pole {field.text()!r}, "
            f"fokus {field.hasFocus()}, historie {assembly.session.can_undo}")
        assembly.undo_action.trigger()
        assert assembly.session.assembly.to_dict() == before, "Zpět neobnovilo původní sestavu"
        assembly.checks_dock.toggleViewAction().trigger()
        assert not assembly.checks_dock.isHidden(), "přepínač kontrol panel neotevřel"
        assembly.reset_layout_action.trigger()
        assert assembly.checks_dock.isHidden(), "akce resetu kontroly neskryla"
        lines.append(f"✓ Panely sestavy: 3D šířka {widths[0]}/{widths[1]} při skutečném okně "
                     f"{actual_widths[0]}/{actual_widths[1]} (požadavek 1200/1024), "
                     "panely a mezery ≤580, šest polí ≥90, Enter posun 1,5 mm a Zpět, "
                     "skrytí/obnova kontrol bez změny sestavy")
        return True
    except Exception:  # noqa: BLE001 -- srozumitelná evidence self-testu balíčku
        lines.append("✕ Panely sestavy:\n" + traceback.format_exc())
        return False


def _self_test_assembly_motion_panel(assembly, lines) -> bool:
    """Nativní záložky a sbalování zachovají vstupy, model, kameru a historii."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    viewer, session = assembly.viewer, assembly.session
    assembly.select(("nozicka_1",))
    fields = [assembly.name_edit, *assembly.position_edits, *assembly.move_edits,
              assembly.batch_rotation_angle, *assembly.rotation_center_edits]
    original = [field.text() for field in fields]
    before, result = session.assembly.to_dict(), session.result
    history = (len(session._undo), len(session._redo), session.dirty)
    try:
        assembly.raise_()
        assembly.activateWindow()
        assembly.placement_section.set_expanded(False)
        assembly.appearance_section.set_expanded(False)
        assembly.component_scroll.ensureWidgetVisible(assembly.move_box)
        QTest.qWait(30)
        direction, scale = viewer._view.Proj(), viewer._view.Scale()
        for index, field in enumerate(fields):
            field.setText(f"{index}+h")
        pending = [field.text() for field in fields]
        old = {"token": assembly._move_token(), "delta": [5, 0, 0]}
        bar = assembly.movement_tabs.tabBar()
        for index in (1, 0, 1, 0):
            QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(index).center())
            QTest.qWait(30)
            assert assembly.movement_tabs.currentIndex() == index
            assert assembly.move_box.isVisible() == (index == 0)
            assert assembly.batch_rotation_box.isVisible() == (index == 1)
        for section in (assembly.placement_section, assembly.appearance_section):
            for expanded in (True, False):
                assembly.component_scroll.ensureWidgetVisible(section.button)
                QTest.mouseClick(section.button, Qt.MouseButton.LeftButton)
                QTest.qWait(30)
                assert section.expanded == expanded
        viewer.selection_moved.emit(old)
        assert [field.text() for field in fields] == pending
        assert session.assembly.to_dict() == before and session.result is result
        assert (len(session._undo), len(session._redo), session.dirty) == history
        assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
        lines.append("✓ Panel pohybu sestavy: skutečné kliky Posun/Otočení a sbalení sekcí, "
                     "rozepsaná pole/model/historie/kamera zachovány, starý tah odmítnut")
        return True
    except Exception:  # noqa: BLE001 -- diagnostika sestaveného balíčku
        lines.append("✕ Panel pohybu sestavy:\n" + traceback.format_exc())
        return False
    finally:
        for field, text in zip(fields, original, strict=True):
            field.setText(text)
        assembly.placement_section.set_expanded(False)
        assembly.appearance_section.set_expanded(False)
        assembly.component_scroll.ensureWidgetVisible(assembly.move_box)


def _self_test_assembly_views(assembly, lines) -> bool:
    """Skutečná tlačítka, klávesy a směr kamery; F musí vměstnat vrcholy všech kopií."""
    import math

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    viewer = assembly.viewer
    if not viewer.ready:
        lines.append("! Pohledy sestavy: chybí grafický prohlížeč")
        return True
    try:
        before = assembly.session.assembly.to_dict()
        history = (len(assembly.session._undo), len(assembly.session._redo))
        selected, dirty = assembly._selected, assembly.session.dirty
        expected = {"top": (0., 0., 1.), "front": (0., -1., 0.),
                    "iso": (1/math.sqrt(3), -1/math.sqrt(3), 1/math.sqrt(3))}

        def check_direction(key):
            actual = viewer._view.Proj()
            assert all(abs(a-b) < 1e-7 for a, b in zip(actual, expected[key], strict=True)), \
                f"{key}: směr {actual}, očekáváno {expected[key]}"

        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(100)
        toolbar_widths = []
        for width in (1024, 960):
            assembly.resize(width, 720)
            QTest.qWait(100)
            for action in (*[assembly.view_actions[k] for k in ("top", "front", "iso")],
                           assembly.fit_action, assembly.isolate_action, assembly.visibility_action,
                           assembly.restore_visibility_action):
                button = assembly.toolbar.widgetForAction(action)
                assert button.isVisible(), (
                    f"lišta: {action.text()} skryté při {assembly.width()}, "
                    f"potřeba {assembly.toolbar.sizeHint().width()}")
                assert assembly.toolbar.rect().contains(button.geometry()), action.text()
            toolbar_widths.append(assembly.width())
        for key in ("top", "front", "iso"):
            button = assembly.toolbar.widgetForAction(assembly.view_actions[key])
            assert button.isVisible(), f"tlačítko {key} je skryté"
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            QApplication.processEvents()
            check_direction(key)
        viewer._surface.setFocus()
        QTest.qWait(50)
        for code, key in ((Qt.Key.Key_7, "top"), (Qt.Key.Key_1, "front"),
                          (Qt.Key.Key_0, "iso")):
            QTest.keyClick(viewer._surface, code)
            QApplication.processEvents()
            check_direction(key)
        zoomed = viewer._view.Scale() * 6
        viewer._view.SetScale(zoomed)
        viewer._view.Redraw()
        QTest.keyClick(viewer._surface, Qt.Key.Key_F)
        QApplication.processEvents()
        assert viewer._view.Scale() < zoomed, "F nezmenšilo zvětšený pohled"
        check_direction("iso")
        width, height = viewer._view.Window().Size()
        for instance in assembly.session.result.instances:
            for vertex in instance.part.vertices():
                point = vertex.center()
                x, y = viewer._view.Convert(float(point.X), float(point.Y), float(point.Z))
                assert 0 <= x < width and 0 <= y < height, \
                    f"vrchol {instance.ids} mimo celý pohled: {x}/{y} v {width}/{height}"
        assert assembly.session.assembly.to_dict() == before, "pohled změnil recept"
        assert history == (len(assembly.session._undo), len(assembly.session._redo))
        assert selected == assembly._selected and dirty == assembly.session.dirty
        lines.append(f"✓ Pohledy sestavy: lišta {toolbar_widths[0]}/{toolbar_widths[1]}, "
                     "tlačítka i klávesy 7/1/0, správné směry kamery, "
                     "F vměstná vrcholy všech kopií, recept/historie/výběr beze změny")
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika staženého balíčku
        lines.append("✕ Pohledy sestavy:\n" + traceback.format_exc())
        return False


def _self_test_assembly_isolation(assembly, lines) -> bool:
    """Nativní AIS obsahuje jen izolovaný díl; návrat obnoví celou geometrii."""
    from build123d import Compound
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    if not assembly.viewer.ready:
        lines.append("! Izolace sestavy: chybí grafický prohlížeč")
        return True
    try:
        session, viewer = assembly.session, assembly.viewer
        before = session.assembly.to_dict()
        history = (len(session._undo), len(session._redo), session.dirty)
        total = session.result.volume_mm3
        lid = next(i for i in session.result.instances if i.ids == ("vicko",))
        assembly.select(lid.ids)
        assembly.position_edits[0].setText("rozepsaný výraz")
        assembly.view_actions["top"].trigger()
        direction = viewer._view.Proj()
        button = assembly.toolbar.widgetForAction(assembly.isolate_action)
        assert button.isVisible() and button.isEnabled()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert assembly._isolated == (lid.ids,) and assembly._selected == lid.ids
        assert len(assembly.visible_instances()) == 1
        drawn = Compound(viewer._ais.Shape())
        assert len(drawn.solids()) == 1 and abs(drawn.volume - lid.volume_mm3) < 1e-5
        for actual, expected in ((drawn.bounding_box().min, lid.part.bounding_box().min),
                                 (drawn.bounding_box().max, lid.part.bounding_box().max)):
            assert all(abs(a-b) < 1e-6 for a, b in zip(actual, expected, strict=True))
        assert viewer._view.Proj() == direction
        assert assembly.position_edits[0].text() == "rozepsaný výraz"
        assert not assembly._picks and not assembly.constraint_action.isEnabled()
        assert "izolace (1/6)" in assembly.windowTitle()
        assert "Součty níže platí pro celou sestavu" in assembly.summary.text()
        viewer._surface.setFocus()
        QTest.keyClick(viewer._surface, Qt.Key.Key_F)
        width, height = viewer._view.Window().Size()
        for vertex in lid.part.vertices():
            p = vertex.center()
            x, y = viewer._view.Convert(float(p.X), float(p.Y), float(p.Z))
            assert 0 <= x < width and 0 <= y < height
        button = assembly.toolbar.widgetForAction(assembly.restore_visibility_action)
        assert button.isVisible() and button.isEnabled()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        drawn = Compound(viewer._ais.Shape())
        assert assembly._isolated is None and len(drawn.solids()) == 6
        assert abs(drawn.volume - total) < 1e-5 and viewer._view.Proj() == direction
        assert assembly._selected == lid.ids
        assert assembly.position_edits[0].text() == "rozepsaný výraz"
        assert session.assembly.to_dict() == before
        assert history == (len(session._undo), len(session._redo), session.dirty)
        lines.append("✓ Izolace sestavy: nativní tlačítka, AIS 1/6 → 6/6 těles, "
                     "objem/obálka, kamera a F, recept/historie/rozepsané pole beze změny")
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika balíčku
        lines.append("✕ Izolace sestavy:\n" + traceback.format_exc())
        return False
    finally:
        assembly.show_all()


def _self_test_assembly_visibility(assembly, lines) -> bool:
    """Skutečný checkbox/H/tlačítko a AIS; ruční skrývání zůstává po ukončení izolace."""
    import json

    from build123d import Compound
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    viewer, session = assembly.viewer, assembly.session
    if not viewer.ready:
        lines.append("! Viditelnost sestavy: chybí grafický prohlížeč")
        return True
    try:
        assembly.show_all()
        before = session.assembly.to_dict()
        history = (len(session._undo), len(session._redo), session.dirty)
        total = session.result.volume_mm3
        lid = next(i for i in session.result.instances if i.ids == ("vicko",))
        foot = next(i for i in session.result.instances if i.ids == ("nozicka_1",))

        def row(item):
            if json.loads(item.data(0, Qt.ItemDataRole.UserRole)) == ["vicko"]:
                return item
            for n in range(item.childCount()):
                found = row(item.child(n))
                if found is not None:
                    return found
            return None

        item = next(found for n in range(assembly.tree.topLevelItemCount())
                    if (found := row(assembly.tree.topLevelItem(n))) is not None)
        assembly.tree.setCurrentItem(item)
        assembly.position_edits[0].setText("rozepsaná poloha")
        direction, scale = viewer._view.Proj(), viewer._view.Scale()
        assembly.tree.setFocus()
        QTest.keyClick(assembly.tree, Qt.Key.Key_Space)
        QApplication.processEvents()
        drawn = Compound(viewer._ais.Shape())
        assert item.checkState(0) == Qt.CheckState.Unchecked
        assert len(drawn.solids()) == 5 and abs(drawn.volume-(total-lid.volume_mm3)) < 1e-5
        assert assembly._selected == lid.ids
        assert assembly.position_edits[0].text() == "rozepsaná poloha"
        assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
        QTest.keyClick(assembly.tree, Qt.Key.Key_Space)
        QApplication.processEvents()
        assert item.checkState(0) == Qt.CheckState.Checked
        assert len(Compound(viewer._ais.Shape()).solids()) == 6
        button = assembly.toolbar.widgetForAction(assembly.visibility_action)
        assert button.isVisible() and assembly.toolbar.rect().contains(button.geometry())
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert len(Compound(viewer._ais.Shape()).solids()) == 5
        viewer._surface.setFocus()
        QTest.qWait(50)
        QTest.keyClick(viewer._surface, Qt.Key.Key_H)
        assert len(Compound(viewer._ais.Shape()).solids()) == 6
        assert assembly.position_edits[0].text() == "rozepsaná poloha"
        assembly.set_component_visible(foot.ids, False)
        assembly.isolate_action.trigger()
        assert len(Compound(viewer._ais.Shape()).solids()) == 1
        assembly.end_isolation_action.trigger()
        drawn = Compound(viewer._ais.Shape())
        assert assembly._isolated is None and len(drawn.solids()) == 5
        assert abs(drawn.volume-(total-foot.volume_mm3)) < 1e-5
        for instance in session.result.instances:
            assembly.set_component_visible(instance.ids, False)
        assert not assembly.visible_instances() and viewer._ais is None
        QTest.keyClick(viewer._surface, Qt.Key.Key_F)  # prázdný pohled není chyba
        button = assembly.toolbar.widgetForAction(assembly.restore_visibility_action)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        drawn = Compound(viewer._ais.Shape())
        assert len(drawn.solids()) == 6 and abs(drawn.volume-total) < 1e-5
        assert not assembly._visibility and assembly._isolated is None
        assert assembly._selected == lid.ids
        assert assembly.position_edits[0].text() == "rozepsaná poloha"
        assert session.assembly.to_dict() == before
        assert history == (len(session._undo), len(session._redo), session.dirty)
        lines.append("✓ Viditelnost sestavy: checkbox/H/tlačítka, AIS 6→5→6, "
                     "izolace 5→1→5, prázdný pohled 0→6, objem, kamera, "
                     "recept/historie/rozepsané pole beze změny")
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika balíčku
        lines.append("✕ Viditelnost sestavy:\n" + traceback.format_exc())
        return False
    finally:
        assembly.show_all()


def _self_test_assembly_transparency(assembly, lines) -> bool:
    """Nativní materiál i obraz, T/checkbox a skutečný výběr plochy před i po přepnutí."""
    from build123d import Compound
    from OCP.Prs3d import Prs3d_TypeOfHighlight_LocalSelected
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QAccessible, QAccessibleActionInterface, QImage
    from PySide6.QtTest import QTest

    viewer, session = assembly.viewer, assembly.session
    if not viewer.ready:
        lines.append("! Průhlednost sestavy: chybí grafický prohlížeč")
        return True
    try:
        assembly.show_all()
        assembly.reset_transparency()
        before = session.assembly.to_dict()
        history = (len(session._undo), len(session._redo), session.dirty)
        body = next(i for i in session.result.instances if i.ids == ("krabicka",))
        lid = next(i for i in session.result.instances if i.ids == ("vicko",))
        assembly.view_actions["front"].trigger()
        assembly.fit_action.trigger()
        QApplication.processEvents()
        front = min(body.part.faces(), key=lambda f: f.center().Y)
        point = front.center()
        x, y = viewer._view.Convert(float(point.X), float(point.Y), float(point.Z))
        ratio = viewer._pixels(QPoint(100, 100))[0] / 100
        pos = QPoint(round(x / ratio), round(y / ratio))
        QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, pos=pos)
        QApplication.processEvents()
        assert viewer.selected_shapes() and assembly._picks, "klik nevybral plochu"
        assert assembly._selected == body.ids, "klik nevybral krabičku"
        picked = list(viewer.selected_shapes())
        picks = list(assembly._picks)
        assembly.position_edits[0].setText("rozepsaná poloha")
        direction, scale, ais = viewer._view.Proj(), viewer._view.Scale(), viewer._ais

        def alpha(instance):
            aspects = viewer._ais.CustomAspectsMap()
            drawer = (aspects.Find(instance.part.wrapped)
                      if aspects.IsBound(instance.part.wrapped) else viewer._ais.Attributes())
            # Prs3d_Drawer.Transparency() je jiná vlastnost; render používá materiál.
            return drawer.ShadingAspect().Aspect().FrontMaterial().Transparency()

        viewer._surface.setFocus()
        QTest.qWait(50)
        QTest.keyClick(viewer._surface, Qt.Key.Key_T)
        QApplication.processEvents()
        assert assembly.transparency_box.checkState() == Qt.CheckState.Checked
        assert assembly.transparency_action.isChecked()
        assert viewer._ais is ais and abs(alpha(body)-.7) < 1e-6 and alpha(lid) == 0
        style = viewer._context.HighlightStyle(Prs3d_TypeOfHighlight_LocalSelected)
        assert style.DisplayMode() == 0
        assert len(viewer.selected_shapes()) == len(picked)
        assert all(a.IsSame(b) for a, b in zip(viewer.selected_shapes(), picked, strict=True))
        assert assembly._picks == picks, "přepnutí zahodilo plochy pro vazbu"
        assert assembly.position_edits[0].text() == "rozepsaná poloha"
        assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
        drawn = Compound(ais.Shape())
        assert len(drawn.solids()) == 6 and abs(drawn.volume-session.result.volume_mm3) < 1e-5
        # Průhledná plocha se dál dá vybrat skutečným klikem.
        viewer.clear_selection()
        QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, pos=pos)
        assert viewer.selected_shapes() and assembly._selected == body.ids
        viewer.clear_selection()  # výplň vybrané plochy nesmí překrýt porovnání materiálu
        assembly.select(body.ids)  # prázdný výběr nově zruší i výběr komponenty
        viewer._context.ClearDetected(False)
        assembly.position_edits[0].setText("rozepsaná poloha")
        box = assembly.transparency_box
        assembly.component_scroll.ensureWidgetVisible(box)
        QTest.mouseClick(box, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert alpha(body) == 0 and not box.isChecked()
        opaque = user_dir() / "self-test-sestava-plna.png"
        transparent = user_dir() / "self-test-sestava-pruhledna.png"
        assert viewer.dump(str(opaque))
        QTest.mouseClick(box, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert abs(alpha(body)-.7) < 1e-6 and box.isChecked()
        assert viewer.dump(str(transparent))
        image_a, image_b = QImage(str(opaque)), QImage(str(transparent))
        assert not image_a.isNull() and image_a.size() == image_b.size()
        assert image_a != image_b, "změna materiálu se neprojevila v obrazu"
        assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
        accessible = QAccessible.queryAccessibleInterface(box).actionInterface()
        toggle = QAccessibleActionInterface.toggleAction()
        assert accessible is not None and toggle in accessible.actionNames()
        accessible.doAction(toggle)
        QApplication.processEvents()
        assert alpha(body) == 0 and not box.isChecked(), "AX přepnul jen checkbox, ne 3D"
        accessible.doAction(toggle)
        QApplication.processEvents()
        assert abs(alpha(body)-.7) < 1e-6 and box.isChecked()
        assembly.visibility_action.trigger()
        assert len(Compound(viewer._ais.Shape()).solids()) == 5
        assert not viewer._transparent_parts and assembly._is_transparent(body.ids)
        assembly.show_all()
        assert abs(alpha(body)-.7) < 1e-6
        assembly.isolate_action.trigger()
        assert len(Compound(viewer._ais.Shape()).solids()) == 1 and abs(alpha(body)-.7) < 1e-6
        assembly.reset_transparency_action.trigger()
        assert alpha(body) == 0 and assembly._isolated == (body.ids,)
        assert assembly.position_edits[0].text() == "rozepsaná poloha"
        assert session.assembly.to_dict() == before
        assert history == (len(session._undo), len(session._redo), session.dirty)
        lines.append("✓ Průhlednost sestavy: checkbox/AX/T, AIS 70→0→70 %, obraz změněn, "
                     "skrytí/izolace, výběr/kamera/objem/recept/historie/rozepsané pole beze změny")
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika staženého balíčku
        lines.append("✕ Průhlednost sestavy:\n" + traceback.format_exc())
        return False
    finally:
        assembly.reset_transparency()
        assembly.show_all()


def _self_test_assembly_transparency_levels(assembly, lines) -> bool:
    """Číselné pole, nativní AX hodnota, oba konce rozsahu a samostatné materiály."""
    from build123d import Compound
    from PySide6.QtCore import QEvent, QPoint, Qt
    from PySide6.QtGui import QAccessible
    from PySide6.QtTest import QTest

    viewer, session = assembly.viewer, assembly.session
    if not viewer.ready:
        lines.append("! Míra průhlednosti sestavy: chybí grafický prohlížeč")
        return True
    try:
        assembly.show_all()
        assembly.reset_transparency()
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(50)
        before = session.assembly.to_dict()
        history = (len(session._undo), len(session._redo), session.dirty)
        body = next(i for i in session.result.instances if i.ids == ("krabicka",))
        foot = next(i for i in session.result.instances if i.ids == ("nozicka_1",))
        front = min(body.part.faces(), key=lambda f: f.center().Y).center()
        x, y = viewer._view.Convert(float(front.X), float(front.Y), float(front.Z))
        ratio = viewer._pixels(QPoint(100, 100))[0] / 100
        pos = QPoint(round(x/ratio), round(y/ratio))
        QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, pos=pos)
        assert assembly._selected == body.ids and viewer.selected_shapes()
        picked, picks = list(viewer.selected_shapes()), list(assembly._picks)
        assembly.position_edits[0].setText("rozepsaná poloha")
        ais, result = viewer._ais, session.result
        direction, scale = viewer._view.Proj(), viewer._view.Scale()
        field = assembly.transparency_percent
        assembly.component_scroll.ensureWidgetVisible(field)

        def enter(value):
            field.setFocus()
            field.selectAll()
            QTest.keyClicks(field, str(value))
            QTest.keyClick(field, Qt.Key.Key_Return)
            QApplication.processEvents()

        def alpha(instance):
            aspects = viewer._ais.CustomAspectsMap()
            drawer = (aspects.Find(instance.part.wrapped)
                      if aspects.IsBound(instance.part.wrapped) else viewer._ais.Attributes())
            return drawer.ShadingAspect().Aspect().FrontMaterial().Transparency()

        enter(35)
        assert abs(alpha(body)-.35) < 1e-6 and alpha(foot) == 0
        assert viewer._ais is ais and session.result is result
        assert all(a.IsSame(b) for a, b in zip(viewer.selected_shapes(), picked, strict=True))
        assert assembly._picks == picks and assembly.position_edits[0].text() == "rozepsaná poloha"
        QApplication.sendEvent(assembly, QEvent(QEvent.Type.ActivationChange))
        assert session.result is result, "návrat do okna zahodil identitu zobrazené geometrie"
        enter(0)
        assert alpha(body) == 0 and not assembly.transparency_box.isChecked()
        viewer._surface.setFocus()
        QTest.keyClick(viewer._surface, Qt.Key.Key_T)
        assert field.value() == 35 and abs(alpha(body)-.35) < 1e-6
        enter(100)
        assert alpha(body) == 1 and assembly.transparency_box.isChecked()
        QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, pos=pos)
        assert viewer.selected_shapes() and assembly._selected == body.ids
        enter(0)
        viewer._surface.setFocus()
        QTest.keyClick(viewer._surface, Qt.Key.Key_T)
        assert field.value() == 100 and alpha(body) == 1
        assembly.select(foot.ids)
        enter(85)
        assert abs(alpha(foot)-.85) < 1e-6 and alpha(body) == 1
        accessible = QAccessible.queryAccessibleInterface(field).valueInterface()
        assert accessible is not None
        accessible.setCurrentValue(55)
        QApplication.processEvents()
        assert field.value() == 55 and abs(alpha(foot)-.55) < 1e-6 and alpha(body) == 1
        assert viewer._ais is ais and viewer._view.Proj() == direction
        assert abs(viewer._view.Scale()-scale) < 1e-9
        assembly.set_component_visible(body.ids, False)
        assembly.show_all()
        assert alpha(body) == 1 and abs(alpha(foot)-.55) < 1e-6
        drawn = Compound(viewer._ais.Shape())
        assert len(drawn.solids()) == 6 and abs(drawn.volume-session.result.volume_mm3) < 1e-5
        assert session.assembly.to_dict() == before
        assert history == (len(session._undo), len(session._redo), session.dirty)
        lines.append("✓ Míra průhlednosti sestavy: Qt/AX 35/85/55/0/100 %, T obnoví míru, "
                     "samostatné materiály, návrat do okna, kamera/výběr/objem/recept/historie "
                     "a rozepsané pole beze změny")
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika balíčku
        lines.append("✕ Míra průhlednosti sestavy:\n" + traceback.format_exc())
        return False
    finally:
        assembly.reset_transparency()
        assembly.show_all()


def _self_test_assembly_multi_selection(assembly, lines) -> bool:
    """Nativní strom i OCCT: rozsah, přidání/ubrání ploch a společné příkazy."""
    from build123d import Compound
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    viewer, session = assembly.viewer, assembly.session
    if not viewer.ready:
        lines.append("! Hromadný výběr sestavy: chybí grafický prohlížeč")
        return True
    try:
        assembly.show_all()
        assembly.reset_transparency()
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(50)
        before = session.assembly.to_dict()
        history = (len(session._undo), len(session._redo), session.dirty)
        result = session.result
        body = next(i for i in result.instances if i.ids == ("krabicka",))
        lid = next(i for i in result.instances if i.ids == ("vicko",))
        expected = (body.ids, lid.ids)
        from skodacad.gui.assembly_window import AssemblyWindow

        deferred = AssemblyWindow()
        try:
            assert deferred.open_assembly(session.path, template=True)
            deferred.select_many(expected)
            assert not deferred.viewer.ready
            deferred.show()
            QTest.qWait(150)
            assert deferred.viewer.ready and deferred._selection == expected
            assert deferred.viewer._highlight is not None
            assert len(Compound(deferred.viewer._ais.Shape()).solids()) == 6
        finally:
            deferred.session.dirty = False
            deferred.close()
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(50)

        def row_click(index, modifiers=Qt.KeyboardModifier.NoModifier):
            item = assembly.tree.topLevelItem(index)
            assembly.tree.scrollToItem(item)
            rect = assembly.tree.visualItemRect(item)
            QTest.mouseClick(assembly.tree.viewport(), Qt.MouseButton.LeftButton,
                            modifiers, QPoint(rect.left()+100, rect.center().y()))

        row_click(0)
        row_click(1, Qt.KeyboardModifier.ControlModifier)
        assert assembly._selection == expected and len(assembly.tree.selectedItems()) == 2
        assert not assembly.apply_button.isEnabled() and not assembly.remove_action.isEnabled()
        assert "Vybrané komponenty: 2" in assembly.form_note.text()
        assembly.component_scroll.ensureWidgetVisible(assembly.transparency_percent)
        field = assembly.transparency_percent
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, "60")
        QTest.keyClick(field, Qt.Key.Key_Return)
        assert [assembly._transparency_value(ids) for ids in expected] == [60, 60]
        for instance in (body, lid):
            drawer = viewer._ais.CustomAspectsMap().Find(instance.part.wrapped)
            assert abs(drawer.ShadingAspect().Aspect().FrontMaterial().Transparency()-.6) < 1e-6
        direction, scale = viewer._view.Proj(), viewer._view.Scale()
        assembly.tree.setFocus()
        QTest.keyClick(assembly.tree, Qt.Key.Key_H)
        assert len(Compound(viewer._ais.Shape()).solids()) == 4
        assert assembly._selection == expected and len(assembly.tree.selectedItems()) == 2
        QTest.keyClick(assembly.tree, Qt.Key.Key_H)
        assert len(Compound(viewer._ais.Shape()).solids()) == 6
        assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
        QTest.keyClick(assembly.tree, Qt.Key.Key_I)
        drawn = Compound(viewer._ais.Shape())
        assert assembly._isolated == expected and len(drawn.solids()) == 2
        assert abs(drawn.volume-body.part.volume-lid.part.volume) < 1e-5
        assembly.show_all()
        row_click(0)
        row_click(2, Qt.KeyboardModifier.ShiftModifier)
        assert len(assembly._selection) == 3
        QTest.keyClick(assembly.tree, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        assert len(assembly._selection) == 6
        QTest.keyClick(assembly.tree, Qt.Key.Key_Escape)
        assert not assembly._selection and not assembly.tree.selectedItems()

        assembly.reset_transparency()
        assembly.view_actions["front"].trigger()

        def surface_click(instance, modifiers=Qt.KeyboardModifier.NoModifier):
            front = min(instance.part.faces(), key=lambda f: f.center().Y).center()
            x, y = viewer._view.Convert(float(front.X), float(front.Y), float(front.Z))
            ratio = viewer._pixels(QPoint(100, 100))[0] / 100
            QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, modifiers,
                            QPoint(round(x/ratio), round(y/ratio)))

        surface_click(body)
        surface_click(lid, Qt.KeyboardModifier.ControlModifier)
        assert assembly._selection == expected and len(viewer.selected_shapes()) == 2
        assert len(assembly._picks) == 2 and assembly.constraint_action.isEnabled()
        picked = list(assembly._picks)
        viewer._surface.setFocus()
        QTest.keyClick(viewer._surface, Qt.Key.Key_T)
        assert assembly._picks == picked and len(viewer.selected_shapes()) == 2
        surface_click(lid, Qt.KeyboardModifier.ControlModifier)
        assert assembly._selected == body.ids and len(viewer.selected_shapes()) == 1
        QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
        assert not assembly._selection and not assembly._picks
        assert session.result is result and session.assembly.to_dict() == before
        assert history == (len(session._undo), len(session._redo), session.dirty)
        assert abs(Compound(viewer._ais.Shape()).volume-result.volume_mm3) < 1e-5
        lines.append("✓ Hromadný výběr sestavy: první paint zachová výběr, "
                     "strom Ctrl/⌘/Shift/A/Esc, 3D přidat/ubrat, "
                     "H 6→4→6, I 2/6, společná míra 60 %, plochy pro vazby, kamera, "
                     "objem/recept/historie beze změny")
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika balíčku
        lines.append("✕ Hromadný výběr sestavy:\n" + traceback.format_exc())
        return False
    finally:
        assembly.reset_transparency()
        assembly.show_all()


def _self_test_assembly_batch_move(assembly, lines, *, single=False) -> bool:
    """Skutečný Enter/tlačítka, dva parametrické díly, jeden krok Zpět/Znovu."""
    import numpy as np
    from build123d import Compound
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    viewer, session = assembly.viewer, assembly.session
    label = "Posun jednoho dílu" if single else "Hromadný posun sestavy"
    if not viewer.ready:
        lines.append(f"! {label}: chybí grafický prohlížeč")
        return True
    steps = len(session._undo)
    try:
        assembly.show_all()
        assembly.reset_transparency()
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(50)
        assembly.select_many((("krabicka",), ("vicko",)))
        assembly.component_scroll.ensureWidgetVisible(assembly.move_box)
        assert assembly.move_box.isVisible() and not assembly.move_button.isEnabled()
        assert "Pevné komponenty: Krabička" in assembly.move_note.text()
        ids = (("nozicka_1",),) if single else (("nozicka_1",), ("nozicka_2",))
        assembly.select_many(ids)
        assert assembly.move_button.isEnabled()
        before = session.assembly.to_dict()
        old = {i.ids: np.array(tuple(i.part.center())) for i in session.result.instances}
        rotations = {c.id: list(c.rotation) for c in session.assembly.components}
        expressions = {cid: list(session.assembly.component(cid).position) for cid, in ids}
        assert all(isinstance(v, str) for pos in expressions.values() for v in pos)
        assembly.set_component_transparency(ids[0], 35)
        if not single:
            assembly.set_component_transparency(ids[1], 85)
        assembly.set_component_visible(("vicko",), False)
        assembly.isolate_selected()
        for field, value in zip(assembly.move_edits, ("2,5", "-1", "-4"), strict=True):
            assembly.component_scroll.ensureWidgetVisible(field)
            field.setFocus()
            field.selectAll()
            QTest.keyClicks(field, value)
        assembly.visibility_action.trigger()
        assert not assembly.visible_instances()
        assembly.visibility_action.trigger()
        assert [f.text() for f in assembly.move_edits] == ["2,5", "-1", "-4"]
        direction, scale = viewer._view.Proj(), viewer._view.Scale()
        field = assembly.move_edits[2]
        assembly.component_scroll.ensureWidgetVisible(field)
        field.setFocus()
        QTest.keyClick(field, Qt.Key.Key_Return)
        assert len(session._undo) == steps+1 and not session.can_redo
        assert assembly._selection == ids and assembly._isolated == ids
        assert assembly._visibility == {("vicko",): False}
        assert [f.text() for f in assembly.move_edits] == ["0", "0", "0"]
        assert not assembly._picks
        assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
        for instance in session.result.instances:
            expected = old[instance.ids] + (np.array([2.5, -1, -4]) if instance.ids in ids else 0)
            assert np.allclose(tuple(instance.part.center()), expected, atol=1e-6, rtol=0)
        assert {c.id: c.rotation for c in session.assembly.components} == rotations
        assert all(isinstance(v, str) for cid, in ids
                   for v in session.assembly.component(cid).position)
        drawn = Compound(viewer._ais.Shape())
        assert len(drawn.solids()) == len(ids) and session.result.complete
        assert len(session.result.instances) == 6 and abs(session.result.volume_mm3-31309.287) < .01
        after = session.assembly.to_dict()
        assembly.undo_action.trigger()
        assert session.assembly.to_dict() == before and len(session._undo) == steps
        assembly.redo_action.trigger()
        assert session.assembly.to_dict() == after and len(session._undo) == steps+1
        assert assembly._selection == ids
        lines.append(f"✓ {label}: nativní Enter, posun [2,5; −1; −4] mm, "
                     "pevná komponenta blokována, výrazy poloh zachovány, H a izolace, "
                     "kamera/otočení/ostatní díly/objem beze změny, jeden krok Zpět/Znovu")
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika balíčku
        lines.append(f"✕ {label}:\n" + traceback.format_exc())
        return False
    finally:
        while len(session._undo) > steps:
            session.undo()
        assembly._refresh()
        assembly.reset_transparency()
        assembly.show_all()


def _self_test_assembly_selection_drag(assembly, lines, *, single=False) -> bool:
    """Nativní myš přes OCCT projekci: náhled XYZ, materiály, Esc a historie."""
    import numpy as np
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    viewer, session = assembly.viewer, assembly.session
    label = "Tažení jednoho dílu" if single else "Tažení výběru sestavy"
    if not viewer.ready:
        lines.append(f"! {label}: chybí grafický prohlížeč")
        return True
    steps = len(session._undo)
    ids = (("nozicka_1",),) if single else (("nozicka_1",), ("nozicka_2",))
    try:
        assembly.show_all()
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(50)
        assembly.select_many(ids)
        assembly.move_step.setValue(.5)
        assembly.set_component_transparency(ids[0], 35)
        if not single:
            assembly.set_component_transparency(ids[1], 85)
        assembly.move_edits[0].setText("2,5")
        viewer.set_standard_view("iso")
        QApplication.processEvents()
        viewer.fit_all()

        def positions(axis):
            tip = next(t for a, t in viewer._move_tips if a == axis)
            end = list(tip)
            end[axis] += 8.
            ratio = viewer._pixel_scale()
            return tuple(QPoint(*(round(v/ratio) for v in viewer._view.Convert(*point)))
                         for point in (tip, tuple(end)))

        for axis in range(3):
            original = session.assembly.to_dict()
            old_result = session.result
            old = {i.ids: np.array(tuple(i.part.center())) for i in old_result.instances}
            direction, scale = viewer._view.Proj(), viewer._view.Scale()
            start, end = positions(axis)
            surface_size = viewer._surface.size()
            QTest.mousePress(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
            QTest.qWait(30)  # skutečná myš dá Qt čas na layout/fokus, nejen synchronní signály
            assert viewer._selection_drag is not None, f"Nelze uchopit osu {'XYZ'[axis]}"
            assert viewer._surface.size() == surface_size, "Zpráva nesmí změnit velikost 3D plochy"
            QTest.mouseMove(viewer._surface, end)
            QTest.qWait(30)
            drag = viewer._selection_drag
            assert drag is not None and any(drag["delta"])
            delta = np.array(drag["delta"])
            assert abs(delta[axis]-8.) <= .5 and np.count_nonzero(delta) == 1
            assert session.assembly.to_dict() == original and session.result is old_result
            assert len(session._undo) == steps
            translation = drag["preview"].LocalTransformation().TranslationPart()
            assert np.allclose((translation.X(), translation.Y(), translation.Z()), delta)
            assert all(viewer._ais.CustomAspects(s).IsHidden() for s in drag["data"]["shapes"])
            assert np.allclose([
                drag["preview"].CustomAspects(s).ShadingAspect().Aspect().FrontMaterial()
                .Transparency() for s in drag["data"]["shapes"]],
                [.35] if single else [.35, .85], atol=1e-6)
            QTest.mouseRelease(viewer._surface, Qt.MouseButton.LeftButton, pos=end)
            assert viewer._selection_drag is None and len(session._undo) == steps+1
            assert assembly._selection == ids and assembly.move_edits[0].text() == "2,5"
            assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
            for instance in session.result.instances:
                expected = old[instance.ids] + (delta if instance.ids in ids else 0)
                assert np.allclose(tuple(instance.part.center()), expected, atol=1e-6, rtol=0)
                assert instance.part.is_valid
            moved = session.assembly.to_dict()
            assembly.undo_action.trigger()
            assert session.assembly.to_dict() == original and len(session._undo) == steps
            assembly.redo_action.trigger()
            assert session.assembly.to_dict() == moved and len(session._undo) == steps+1
            assembly.undo_action.trigger()

        # Zrušený tah zachová také existující větev Znovu a rozepsaný číselný posun.
        before, result = session.assembly.to_dict(), session.result
        assert session.can_redo
        for cancel in ("escape", "step", "focus"):
            start, end = positions(0)
            QTest.mousePress(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
            QTest.qWait(30)
            QTest.mouseMove(viewer._surface, end)
            QTest.qWait(30)
            assert viewer._selection_drag is not None
            if cancel == "escape":
                QTest.keyClick(viewer._surface, Qt.Key.Key_Escape)
            elif cancel == "step":
                assembly.move_step.setValue(1.)
            else:
                assembly.move_edits[0].setFocus()
                QApplication.processEvents()
            QTest.mouseRelease(viewer._surface, Qt.MouseButton.LeftButton, pos=end)
            assert viewer._selection_drag is None and session.assembly.to_dict() == before
            assert session.result is result and len(session._undo) == steps and session.can_redo
            assert assembly.move_edits[0].text() == "2,5"
        assembly.select_many((("krabicka",), ("vicko",)))
        assert not viewer._move_tips and not assembly.move_handles.isEnabled()
        parts = "jeden díl, 35 %" if single else "oba díly, 35/85 %"
        lines.append(f"✓ {label}: nativní myš XYZ, {parts}, "
                     "náhled bez změny modelu, stejný posun, jeden krok Zpět/Znovu, "
                     "Esc/krok/fokus zachovají historii i rozepsaná pole, pevný díl blokován")
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika balíčku
        lines.append(f"✕ {label}:\n" + traceback.format_exc())
        return False
    finally:
        viewer.cancel_selection_drag()
        while len(session._undo) > steps:
            session.undo()
        assembly.move_step.setValue(1.)
        assembly._refresh()
        assembly.reset_transparency()
        assembly.show_all()


def _self_test_assembly_batch_rotation(assembly, lines) -> bool:
    """Nativní osa/Enter; jeden tuhý pohyb včetně skrytého dílu, žádné modelování v GUI."""
    import math

    import numpy as np
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    viewer, session = assembly.viewer, assembly.session
    if not viewer.ready:
        lines.append("! Společné otočení sestavy: chybí grafický prohlížeč")
        return True
    steps = len(session._undo)
    ids = (("nozicka_1",), ("nozicka_2",))
    try:
        assembly.show_all()
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(100)
        assembly.select_many((("krabicka",), ("vicko",)))
        assert not assembly.batch_rotation_button.isEnabled()
        assert "Pevné komponenty" in assembly.batch_rotation_note.text()
        assembly.select_many(ids)
        assembly.move_edits[0].setText("2,5")
        assembly.set_component_transparency(ids[0], 35)
        assembly.set_component_transparency(ids[1], 85)
        assembly.isolate_selected()
        assembly.set_component_visible(ids[1], False)
        assert len(assembly.visible_instances()) == 1
        for axis in range(3):
            original = session.assembly.to_dict()
            old = {i.ids: np.array(tuple(i.part.center())) for i in session.result.instances}
            # Nožičky mají stejné objemy; střed zahrnuje také skrytou druhou nožičku.
            center = (old[ids[0]]+old[ids[1]])/2
            direction, scale = viewer._view.Proj(), viewer._view.Scale()
            combo = assembly.batch_rotation_axis
            assembly.component_scroll.ensureWidgetVisible(combo)
            combo.setFocus()
            QTest.keyClick(combo, Qt.Key.Key_Home)
            for _ in range(axis):
                QTest.keyClick(combo, Qt.Key.Key_Down)
            assert combo.currentText() == "XYZ"[axis]
            field = assembly.batch_rotation_angle
            assembly.component_scroll.ensureWidgetVisible(field)
            field.setFocus()
            field.selectAll()
            QTest.keyClicks(field, "37,5")
            QTest.keyClick(field, Qt.Key.Key_Return)
            QTest.qWait(30)
            assert len(session._undo) == steps+1 and assembly._selection == ids
            assert assembly._isolated == ids and len(assembly.visible_instances()) == 1
            assert assembly.move_edits[0].text() == "2,5" and field.text() == "37,5"
            assert [assembly._transparency_value(path) for path in ids] == [35, 85]
            assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
            e = np.eye(3)[axis]
            x, y, z = e
            cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
            t = math.radians(37.5)
            q = np.eye(3)*math.cos(t)+(1-math.cos(t))*np.outer(e, e)+math.sin(t)*cross
            for i in session.result.instances:
                expected = center+q @ (old[i.ids]-center) if i.ids in ids else old[i.ids]
                assert np.allclose(tuple(i.part.center()), expected, atol=1e-6, rtol=0)
                assert i.part.is_valid
            assert np.allclose(session.rotation_center([p[0] for p in ids]), center, atol=1e-7)
            assert session.result.complete and abs(session.result.volume_mm3-31309.287) < .01
            assert all(isinstance(v, str) for cid, in ids
                       for v in session.assembly.component(cid).position)
            moved = session.assembly.to_dict()
            assembly.undo_action.trigger()
            assert session.assembly.to_dict() == original and len(session._undo) == steps
            assembly.redo_action.trigger()
            assert session.assembly.to_dict() == moved and len(session._undo) == steps+1
            assembly.undo_action.trigger()

        before, result, redo = session.assembly.to_dict(), session.result, list(session._redo)
        assembly.batch_rotation_angle.setText("360")
        assembly.batch_rotation_button.click()
        QTest.qWait(30)
        assert session.assembly.to_dict() == before and session.result is result
        assert len(session._undo) == steps and session._redo == redo
        lines.append("✓ Společné otočení sestavy: nativní osa/Enter 37,5° XYZ, "
                     "tuhý pohyb obou dílů včetně skrytého, neměnný společný střed, "
                     "pevný díl blokován, 35/85 %, kamera/okolní díly/parametry/objem zachovány, "
                     "jeden krok Zpět/Znovu, 360° bez historie")
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika balíčku
        lines.append("✕ Společné otočení sestavy:\n" + traceback.format_exc())
        return False
    finally:
        while len(session._undo) > steps:
            session.undo()
        assembly.batch_rotation_axis.setCurrentText("Z")
        assembly.batch_rotation_angle.setText("90")
        assembly._refresh()
        assembly.reset_transparency()
        assembly.show_all()


def _self_test_assembly_rotation_handles(assembly, lines, custom=False, *, single=False) -> bool:
    """Skutečné tažení prstenců, AIS náhled, přerušení a jedno přijetí po puštění."""
    import math

    import numpy as np
    from OCP.gp import gp_Pnt
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    viewer, session = assembly.viewer, assembly.session
    label = "Vlastní střed otáčení" if custom else "Rotační rukojeti"
    if not viewer.ready:
        lines.append(f"! {label}: chybí grafický prohlížeč")
        return True
    if single:
        label += " jednoho dílu"
    steps = len(session._undo)
    ids = (("nozicka_1",),) if single else (("nozicka_1",), ("nozicka_2",))
    try:
        assembly.show_all()
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(100)
        assembly.select_many(ids)
        assembly.rotation_center_mode.setCurrentIndex(2 if custom else 0)
        if custom:
            for field, text in zip(assembly.rotation_center_edits, ("5", "-10", "2,5"),
                                   strict=True):
                field.setText(text)
        assembly.move_edits[0].setText("2,5")
        assembly.batch_rotation_angle.setText("37,5")
        assembly.set_component_transparency(ids[0], 35)
        if not single:
            assembly.set_component_transparency(ids[1], 85)
        assembly.isolate_selected()
        viewer.set_standard_view("iso")
        assembly.component_scroll.ensureWidgetVisible(assembly.rotation_handles)
        QTest.mouseClick(assembly.rotation_handles, Qt.MouseButton.LeftButton)
        QTest.qWait(30)
        assert assembly.rotation_handles.isChecked() and not assembly.move_handles.isChecked()
        assembly.rotation_step.setValue(15.)

        def position(axis, degrees):
            center = viewer._move_data["anchor"]
            radius = viewer._view.Convert(round(90*viewer._pixel_scale()))
            p = list(center)
            p[(axis+1) % 3] += radius*math.cos(math.radians(degrees))
            p[(axis+2) % 3] += radius*math.sin(math.radians(degrees))
            return QPoint(*(round(v/viewer._pixel_scale())
                            for v in viewer._view.Convert(*map(float, p))))

        for axis in range(3):
            if axis == 1 and not single:
                assembly.set_component_visible(ids[1], False)  # kamera stále vměstnává obě
            before, result = session.assembly.to_dict(), session.result
            old = {i.ids: np.array(tuple(i.part.center())) for i in result.instances}
            center = (np.array([5, -10, 2.5]) if custom else
                      old[ids[0]] if single else (old[ids[0]]+old[ids[1]])/2)
            assert np.allclose(viewer._move_data["anchor"], center, atol=1e-8, rtol=0)
            assert [a for a, _tip in viewer._move_tips] == [0, 1, 2]
            start, end = position(axis, 45), position(axis, 77)
            direction, scale = viewer._view.Proj(), viewer._view.Scale()
            QTest.mousePress(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
            QTest.qWait(30)
            assert viewer._selection_drag is not None, f"Nelze uchopit prstenec {'XYZ'[axis]}"
            assert viewer._selection_drag["axis"] == axis
            QTest.mouseMove(viewer._surface, end)
            QTest.qWait(30)
            drag = viewer._selection_drag
            assert drag is not None and drag["angle"] == 30
            assert session.assembly.to_dict() == before and session.result is result
            assert len(session._undo) == steps
            c = gp_Pnt(*center).Transformed(drag["preview"].LocalTransformation())
            assert np.allclose((c.X(), c.Y(), c.Z()), center, atol=1e-8, rtol=0)
            assert all(viewer._ais.CustomAspects(s).IsHidden() for s in drag["data"]["shapes"])
            QTest.mouseRelease(viewer._surface, Qt.MouseButton.LeftButton, pos=end)
            QTest.qWait(30)
            assert viewer._selection_drag is None and len(session._undo) == steps+1
            assert assembly._selection == ids and assembly._isolated == ids
            assert assembly.move_edits[0].text() == "2,5"
            assert assembly.batch_rotation_angle.text() == "37,5"
            assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
            x, y, z = e = np.eye(3)[axis]
            cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
            t = math.radians(30)
            q = np.eye(3)*math.cos(t)+(1-math.cos(t))*np.outer(e, e)+math.sin(t)*cross
            for i in session.result.instances:
                expected = center+q @ (old[i.ids]-center) if i.ids in ids else old[i.ids]
                assert np.allclose(tuple(i.part.center()), expected, atol=1e-6, rtol=0)
                assert i.part.is_valid
            assert session.result.complete and abs(session.result.volume_mm3-31309.287) < .01
            assert [assembly._transparency_value(path) for path in ids] == (
                [35] if single else [35, 85])
            moved = session.assembly.to_dict()
            assembly.undo_action.trigger()
            assert session.assembly.to_dict() == before and len(session._undo) == steps
            assembly.redo_action.trigger()
            assert session.assembly.to_dict() == moved and len(session._undo) == steps+1
            assembly.undo_action.trigger()

        before, result, redo = session.assembly.to_dict(), session.result, list(session._redo)
        causes = ("escape", "step", "mode", "focus", "resize")
        for cause in (*causes, *(("center", "center_mode", "invalid_center") if custom else ())):
            start, end = position(2, 45), position(2, 77)
            QTest.mousePress(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
            QTest.qWait(30)
            QTest.mouseMove(viewer._surface, end)
            QTest.qWait(30)
            assert viewer._selection_drag is not None
            if cause == "escape":
                QTest.keyClick(viewer._surface, Qt.Key.Key_Escape)
            elif cause == "step":
                assembly.rotation_step.setValue(5.)
            elif cause == "mode":
                assembly.move_handles.setChecked(True)
            elif cause == "focus":
                assembly.component_scroll.ensureWidgetVisible(assembly.batch_rotation_angle)
                assembly.batch_rotation_angle.setFocus()
            elif cause in ("center", "invalid_center"):
                assembly.rotation_center_edits[0].setText("6" if cause == "center" else "")
                if cause == "invalid_center":
                    assert not assembly.batch_rotation_button.isEnabled()
                    assert viewer._move_data is None
            elif cause == "center_mode":
                assembly.rotation_center_mode.setCurrentIndex(1)
            else:
                assembly.resize(assembly.width()+1, assembly.height()+1)
            QTest.qWait(30)
            QTest.mouseRelease(viewer._surface, Qt.MouseButton.LeftButton, pos=end)
            assert viewer._selection_drag is None and session.assembly.to_dict() == before
            assert session.result is result and len(session._undo) == steps
            assert session._redo == redo
            if custom:
                assembly.rotation_center_mode.setCurrentIndex(2)
                assembly.rotation_center_edits[0].setText("5")
            assembly.rotation_handles.setChecked(True)

        assembly.rotation_step.setValue(15.)
        start = position(2, 45)
        QTest.mousePress(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
        QTest.qWait(30)
        for k in range(1, 12):
            QTest.mouseMove(viewer._surface, position(2, 45+30*k))
            QTest.qWait(5)
        QTest.mouseRelease(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
        assert viewer._selection_drag is None and session.assembly.to_dict() == before
        assert len(session._undo) == steps and session._redo == redo
        if custom:
            assembly.rotation_center_copy.click()
            expected = session.rotation_center([p[0] for p in ids])
            assert viewer._move_data["anchor"] == expected
            assert session.assembly.to_dict() == before and session._redo == redo
            assembly.rotation_center_mode.setCurrentIndex(1)
            assert viewer._move_data["anchor"] == (0, 0, 0)
            assembly.batch_rotation_axis.setCurrentText("Z")
            assembly.batch_rotation_angle.setText("90")
            old = {i.ids: tuple(i.part.center()) for i in session.result.instances}
            assembly.component_scroll.ensureWidgetVisible(assembly.batch_rotation_angle)
            assembly.batch_rotation_angle.setFocus()
            QTest.qWait(30)
            QTest.keyClick(assembly.batch_rotation_angle, Qt.Key.Key_Return)
            QTest.qWait(30)
            assert len(session._undo) == steps+1
            for i in session.result.instances:
                x, y, z = old[i.ids]
                expected = (-y, x, z) if i.ids in ids else (x, y, z)
                assert np.allclose(tuple(i.part.center()), expected, atol=1e-6, rtol=0)
            assembly.undo_action.trigger()
            assert session.assembly.to_dict() == before
        parts = "jeden díl, 35 %" if single else "oba díly včetně skrytého, 35/85 %"
        lines.append(f"✓ {label}: skutečné tažení XYZ, náhled bez změny modelu, "
                     f"přichycení 15° → pohyb 30°, {parts}, pevný střed, "
                     "kamera/okolí/objem/pole zachovány, jeden krok Zpět/Znovu, "
                     "Esc/krok/režim/fokus/resize a 360° bez historie"
                     + (", změna bodu/volby/chybný bod ruší tah, převzetí těžiště, "
                        "počátek sestavy a číselné otočení Enterem" if custom else ""))
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika balíčku
        lines.append(f"✕ {label}:\n" + traceback.format_exc())
        return False
    finally:
        viewer.cancel_selection_drag()
        while len(session._undo) > steps:
            session.undo()
        assembly.rotation_handles.setChecked(False)
        assembly.move_handles.setChecked(True)
        assembly.rotation_step.setValue(15.)
        assembly.rotation_center_mode.setCurrentIndex(0)
        assembly._refresh()
        assembly.reset_transparency()
        assembly.show_all()


def _self_test_rotation_center_pick(assembly, lines) -> bool:
    """Skutečný klik na kružnici, vrchol a plochu jiného dílu; běžný výběr zůstává."""
    import math

    import numpy as np
    from OCP.collections import List_int
    from PySide6.QtCore import QPoint, QSignalBlocker, Qt
    from PySide6.QtTest import QTest

    viewer, session = assembly.viewer, assembly.session
    if not viewer.ready:
        lines.append("! Výběr středu ve 3D: chybí grafický prohlížeč")
        return True
    steps = len(session._undo)
    ids = (("nozicka_1",), ("nozicka_2",))
    try:
        assembly.show_all()
        assembly.select_many(ids)
        for path in (("krabicka",), ("vicko",)):
            assembly.set_component_visible(path, False)
        assembly.set_component_transparency(ids[0], 35)
        assembly.set_component_transparency(ids[1], 85)
        assembly.rotation_handles.setChecked(True)
        assembly.move_edits[0].setText("2,5")
        assembly.batch_rotation_angle.setText("37,5")
        viewer.set_standard_view("top")
        QTest.qWait(100)

        def screen(point):
            return QPoint(*(round(v/viewer._pixel_scale())
                            for v in viewer._view.Convert(*map(float, point))))

        # Technická příprava existujícího AIS výběru bez změny komponent v controlleru.
        with QSignalBlocker(viewer):
            viewer._select_at(*viewer._pixels(screen((-32, -17, 0))))
        selected = viewer.selected_shapes()
        assert selected, "Příprava běžného výběru plochy selhala"
        assembly._picks = [(shape, viewer.picked_point) for shape in selected]
        assembly._refresh_pick_note()
        picked_before, picks_before = viewer.picked_point, list(assembly._picks)
        modes = List_int()
        viewer._context.ActivatedModes(viewer._ais, modes)
        modes_before = list(modes)
        before, result = session.assembly.to_dict(), session.result
        redo = list(session._redo)
        for kind, target, expected in (("circle", (34.5, 17+math.sqrt(18.75), 0), (32, 17, 0)),
                                       ("vertex", (37, 17, 0), (37, 17, 0)),
                                       ("face", (32, 17, 0), None)):
            assembly.rotation_pick_kind.setCurrentIndex(assembly.rotation_pick_kind.findData(kind))
            assembly.component_scroll.ensureWidgetVisible(assembly.rotation_pick_button)
            QTest.qWait(30)
            QTest.mouseClick(assembly.rotation_pick_button, Qt.MouseButton.LeftButton)
            QTest.qWait(30)
            assert viewer._center_pick is not None and not viewer._move_objects
            pos = screen(target)
            ray = viewer._view.ConvertWithProj(*viewer._pixels(pos))
            if expected is None:  # nezávislý průsečík zaokrouhleného pixelu s rovinou z=0
                t = -ray[2]/ray[5]
                expected = tuple(ray[i]+t*ray[i+3] for i in range(3))
            direction, scale = viewer._view.Proj(), viewer._view.Scale()
            QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, pos=pos)
            QTest.qWait(30)
            assert viewer._center_pick is None, f"Klik {kind} nepřevzal bod"
            actual = [float(f.text()) for f in assembly.rotation_center_edits]
            assert np.allclose(actual, expected, atol=1e-7, rtol=0), (kind, actual, expected)
            assert assembly.rotation_center_mode.currentIndex() == 2
            assert assembly._selection == ids and assembly._picks == picks_before
            assert session.assembly.to_dict() == before and session.result is result
            assert len(session._undo) == steps and session._redo == redo
            assert viewer.picked_point == picked_before
            assert len(viewer.selected_shapes()) == len(selected)
            assert all(any(s.IsSame(old) for old in selected) for s in viewer.selected_shapes())
            restored = List_int()
            viewer._context.ActivatedModes(viewer._ais, restored)
            assert sorted(restored) == sorted(modes_before)
            assert viewer._view.Proj() == direction and math.isclose(viewer._view.Scale(), scale)
            assert [assembly._transparency_value(p) for p in ids] == [35, 85]
            assert assembly.move_edits[0].text() == "2,5"
            assert assembly.batch_rotation_angle.text() == "37,5"

        saved = [f.text() for f in assembly.rotation_center_edits]
        for cause in ("escape", "stop", "kind", "miss"):
            assembly.component_scroll.ensureWidgetVisible(assembly.rotation_pick_button)
            QTest.mouseClick(assembly.rotation_pick_button, Qt.MouseButton.LeftButton)
            QTest.qWait(30)
            assert viewer._center_pick is not None
            if cause == "stop":
                QTest.mouseClick(assembly.rotation_pick_button, Qt.MouseButton.LeftButton)
            elif cause == "kind":
                assembly.rotation_pick_kind.setCurrentIndex(0)
            else:
                if cause == "miss":
                    QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, pos=QPoint(8, 8))
                    QTest.qWait(30)
                    assert viewer._center_pick is not None
                QTest.keyClick(viewer._surface, Qt.Key.Key_Escape)
            QTest.qWait(30)
            assert viewer._center_pick is None and assembly._selection == ids
            assert [f.text() for f in assembly.rotation_center_edits] == saved
            assert session.assembly.to_dict() == before and session._redo == redo

        # Převzatý bod následně používá skutečné číselné otočení, jednou Zpět/Znovu.
        pivot = np.array([float(f.text()) for f in assembly.rotation_center_edits])
        old = {i.ids: np.array(tuple(i.part.center())) for i in result.instances}
        assembly.batch_rotation_axis.setCurrentText("Z")
        assembly.batch_rotation_angle.setText("90")
        assembly.component_scroll.ensureWidgetVisible(assembly.batch_rotation_angle)
        assembly.batch_rotation_angle.setFocus()
        QTest.keyClick(assembly.batch_rotation_angle, Qt.Key.Key_Return)
        QTest.qWait(30)
        assert len(session._undo) == steps+1 and session.result.complete
        for i in session.result.instances:
            x, y, z = old[i.ids]-pivot
            expected = pivot+np.array([-y, x, z]) if i.ids in ids else old[i.ids]
            assert np.allclose(tuple(i.part.center()), expected, atol=1e-6, rtol=0)
            assert i.part.is_valid
        changed = session.assembly.to_dict()
        assembly.undo_action.trigger()
        assert session.assembly.to_dict() == before and len(session._undo) == steps
        assembly.redo_action.trigger()
        assert session.assembly.to_dict() == changed and len(session._undo) == steps+1
        assembly.undo_action.trigger()
        lines.append("✓ Výběr středu ve 3D: skutečný klik na střed kružnice, vrchol a přesný "
                     "bod plochy jiného dílu; výběr komponent/ploch/vazeb, kamera, materiály "
                     "35/85 %, pole a historie zachovány; Esc/tlačítko/změna druhu, prázdný "
                     "klik čeká; převzatý bod řídí otočení s jedním Zpět/Znovu")
        return True
    except Exception:  # noqa: BLE001 -- diagnostika staženého balíčku
        lines.append("✕ Výběr středu ve 3D:\n" + traceback.format_exc())
        return False
    finally:
        viewer.cancel_rotation_center_pick()
        while len(session._undo) > steps:
            session.undo()
        assembly.rotation_center_mode.setCurrentIndex(0)
        assembly.rotation_pick_kind.setCurrentIndex(0)
        assembly.rotation_handles.setChecked(False)
        assembly.move_handles.setChecked(True)
        assembly._refresh()
        assembly.reset_transparency()
        assembly.show_all()


def _self_test_cylinder_rotation_axis(assembly, lines, *, kind="cylinder", single=False) -> bool:
    """Skutečný klik na šikmou referenci, přesná osa, číselné otočení i tažení."""
    import math

    import numpy as np
    from OCP.collections import List_int
    from PySide6.QtCore import QPoint, QSignalBlocker, Qt
    from PySide6.QtTest import QTest

    from skodacad.gui.rotation_drag import plane_frame
    from skodacad.gui.viewer import _rotation_pick_point

    viewer, session = assembly.viewer, assembly.session
    line = kind == "line"
    plane = kind == "plane"
    vertices = kind == "vertices"
    label = {"line": "Osa hrany", "plane": "Kolmice k ploše",
             "vertices": "Osa dvou vrcholů"}.get(kind, "Osa válce")
    if single:
        label += " jednoho dílu"
    if not viewer.ready:
        lines.append(f"! {label}: chybí grafický prohlížeč")
        return True
    initial_steps = len(session._undo)
    ids = (("nozicka_1",),) if single else (("nozicka_1",), ("nozicka_2",))
    try:
        # Reference se připraví přes session, nikdy se nepřepíše soubor ukázkového dílu.
        session.set_placement("nozicka_3", rotation=[30, 40, 50])
        assembly._refresh()
        steps = len(session._undo)
        assembly.show_all()
        assembly.select_many(ids)
        for path in (("krabicka",), ("vicko",)):
            assembly.set_component_visible(path, False)
        assembly.set_component_transparency(ids[0], 35)
        if not single:
            assembly.set_component_transparency(ids[1], 85)
        assembly.rotation_handles.setChecked(True)
        viewer.set_standard_view("back" if line or vertices else "iso")
        QTest.qWait(100)
        matrix, origin = session._pose("nozicka_3")
        normal = matrix @ np.array([0., 0., 1.])
        # Přímý šev pláště je o poloměr mimo osu válce, nejde převzít střed válce.
        pivot = origin+matrix @ np.array([5. if line else 0., 0., 1.5])

        def screen(point):
            return QPoint(*(round(v/viewer._pixel_scale())
                            for v in viewer._view.Convert(*map(float, point))))

        target = origin+matrix @ np.array([2., 0., 3.]) if plane else None
        if vertices:
            pivot = origin+matrix @ np.array([5., 0., 3.])
            other_matrix, other_origin = session._pose("nozicka_4")
            target = other_origin+other_matrix @ np.array([5., 0., 3.])
            normal = (target-pivot)/np.linalg.norm(target-pivot)
        if plane:
            # Nezávislý průsečík skutečného pixelového paprsku s rovinou čela.
            ray = np.array(viewer._view.ConvertWithProj(*viewer._pixels(screen(target))))
            on_plane = origin+matrix @ np.array([0., 0., 3.])
            pivot = ray[:3]+ray[3:]*np.dot(normal, on_plane-ray[:3])/np.dot(normal, ray[3:])

        with QSignalBlocker(viewer):
            viewer._select_at(*viewer._pixels(screen((-32, -12, -1.5) if line or vertices
                                                    else (-32, -17, 0))))
        selected = viewer.selected_shapes()
        assert selected, "Příprava výběru plochy selhala"
        assembly._picks = [(shape, viewer.picked_point) for shape in selected]
        picks_before, picked_before = list(assembly._picks), viewer.picked_point
        modes = List_int()
        viewer._context.ActivatedModes(viewer._ais, modes)
        modes_before = sorted(modes)
        assembly.move_edits[0].setText("2,5")
        assembly.batch_rotation_angle.setText("37,5")
        assembly.batch_rotation_axis.setCurrentIndex(
            {"line": 4, "plane": 5, "vertices": 6}.get(kind, 3))
        assert not assembly.batch_rotation_button.isEnabled()
        before, result, redo = session.assembly.to_dict(), session.result, list(session._redo)
        assembly.component_scroll.ensureWidgetVisible(assembly.rotation_axis_pick_button)
        QTest.mouseClick(assembly.rotation_axis_pick_button, Qt.MouseButton.LeftButton)
        QTest.qWait(30)
        assert viewer._center_pick is not None and not viewer._move_objects
        # Kružnice pro osu hrany / rovinné čelo pro válec jsou nevhodné.
        bad_target = origin+matrix @ np.array([3., 4., 3.]) if line else (-32, -17, 0)
        if plane:
            bad_target = (-32+5/math.sqrt(2), -17-5/math.sqrt(2), -1.5)
        QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton,
                         pos=screen(bad_target))
        QTest.qWait(30)
        assert viewer._center_pick is not None and assembly._picked_rotation_axis() is None
        if line:
            assert viewer._context.HasDetectedShape()
            assert _rotation_pick_point(viewer._context.DetectedShape(), "circle") is not None
        if plane:
            from skodacad.gui.viewer import _rotation_pick_cylinder
            assert viewer._context.HasDetectedShape()
            assert _rotation_pick_cylinder(viewer._context.DetectedShape()) is not None
        radial = np.array(viewer._view.Proj())
        radial -= normal*np.dot(radial, normal)
        radial /= np.linalg.norm(radial)
        camera, scale = viewer._view.Proj(), viewer._view.Scale()
        if vertices:
            QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, pos=screen(pivot))
            QTest.qWait(30)
            assert viewer._center_pick is not None and "first" in viewer._center_pick
            assert viewer._center_pick.get("marker") is not None
            assert assembly._picked_rotation_axis() is None
            assert session.assembly.to_dict() == before and len(session._undo) == steps
            QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, pos=screen(pivot))
            QTest.qWait(30)
            assert viewer._center_pick is not None and assembly._picked_rotation_axis() is None
        QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton,
                         pos=screen(target if plane or vertices else pivot if line
                                    else pivot+5*radial))
        QTest.qWait(30)
        assert viewer._center_pick is None, f"Klik nepřevzal referenci: {label}"
        point, direction = assembly._picked_rotation_axis()
        assert np.allclose(point, pivot, atol=1e-8, rtol=0), (point, pivot)
        # Parametrizace pláště může mít opačné znaménko než lokální Z dílu.
        assert abs(abs(np.dot(direction, normal))-1) < 1e-10
        assert np.linalg.norm(np.cross(direction, normal)) < 1e-10, (direction, normal)
        if plane or vertices:
            assert np.dot(direction, normal) > 1-1e-10  # ven z materiálu, nikoli proti normále
        normal = np.array(direction)
        assert assembly._selection == ids and assembly._picks == picks_before
        assert session.assembly.to_dict() == before and session.result is result
        assert len(session._undo) == steps and session._redo == redo
        assert viewer.picked_point == picked_before
        assert len(viewer.selected_shapes()) == len(selected)
        assert all(any(s.IsSame(old) for old in selected) for s in viewer.selected_shapes())
        restored = List_int()
        viewer._context.ActivatedModes(viewer._ais, restored)
        assert sorted(restored) == modes_before
        assert viewer._view.Proj() == camera and abs(viewer._view.Scale()-scale) < 1e-9
        original_point, original_direction = point, np.array(direction)
        for sign in (-1, 1, -1):
            token = assembly._rotation_token()
            assembly.component_scroll.ensureWidgetVisible(assembly.rotation_axis_reverse_button)
            QTest.mouseClick(assembly.rotation_axis_reverse_button, Qt.MouseButton.LeftButton)
            QTest.qWait(30)
            point, direction = assembly._picked_rotation_axis()
            assert point == original_point
            assert np.array_equal(direction, sign*original_direction)
            assert assembly._rotation_token() != token
            assert viewer._move_data["axis_direction"] == direction
            assert assembly._selection == ids and assembly._picks == picks_before
            assert session.assembly.to_dict() == before and session.result is result
            assert len(session._undo) == steps and session._redo == redo
            assert viewer.picked_point == picked_before
            assert all(any(s.IsSame(old) for old in selected) for s in viewer.selected_shapes())
            assert len(viewer.selected_shapes()) == len(selected)
            assert viewer._view.Proj() == camera and abs(viewer._view.Scale()-scale) < 1e-9
        normal = np.array(direction)
        if line or vertices:
            viewer.set_standard_view("iso")  # prstenec v zadním pohledu téměř zaniká
            QTest.qWait(30)
        assert [a for a, _ in viewer._move_tips] == [3]
        assert assembly.move_edits[0].text() == "2,5"
        assert assembly.batch_rotation_angle.text() == "37,5"
        old = {i.ids: np.array(tuple(i.part.center())) for i in result.instances}

        def expected_rotation(angle):
            x, y, z = normal
            cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
            t = math.radians(angle)
            return np.eye(3)*math.cos(t)+(1-math.cos(t))*np.outer(normal, normal)+math.sin(t)*cross

        def check_motion(angle):
            q = expected_rotation(angle)
            for i in session.result.instances:
                expected = pivot+q @ (old[i.ids]-pivot) if i.ids in ids else old[i.ids]
                assert np.allclose(tuple(i.part.center()), expected, atol=1e-6, rtol=0)
                assert i.part.is_valid
            assert session.result.complete and len(session._undo) == steps+1
            assert assembly._selection == ids
            assert [assembly._transparency_value(p) for p in ids] == ([35] if single else [35, 85])
            moved = session.assembly.to_dict()
            assembly.undo_action.trigger()
            assert session.assembly.to_dict() == before and len(session._undo) == steps
            assembly.redo_action.trigger()
            assert session.assembly.to_dict() == moved and len(session._undo) == steps+1
            assembly.undo_action.trigger()

        assembly.batch_rotation_angle.setText("90")
        assembly.component_scroll.ensureWidgetVisible(assembly.batch_rotation_angle)
        assembly.batch_rotation_angle.setFocus()
        QTest.keyClick(assembly.batch_rotation_angle, Qt.Key.Key_Return)
        QTest.qWait(30)
        check_motion(90)
        _n, u, v = map(np.array, plane_frame(tuple(normal)))

        def ring_position(angle):
            radius = viewer._view.Convert(round(90*viewer._pixel_scale()))
            return screen(pivot+radius*(u*math.cos(math.radians(angle))
                                        + v*math.sin(math.radians(angle))))

        start, end = ring_position(45), ring_position(77)
        QTest.mousePress(viewer._surface, Qt.MouseButton.LeftButton, pos=start)
        QTest.qWait(30)
        assert viewer._selection_drag is not None and viewer._selection_drag["axis"] == 3
        QTest.mouseMove(viewer._surface, end)
        QTest.qWait(30)
        assert viewer._selection_drag["angle"] == 30
        assert session.assembly.to_dict() == before and len(session._undo) == steps
        preview = viewer._selection_drag["preview"].LocalTransformation()
        matrix = np.array([[preview.Value(row, col) for col in range(1, 5)]
                           for row in range(1, 4)])
        q = expected_rotation(30)
        assert np.allclose(matrix, np.column_stack((q, pivot-q @ pivot)), atol=1e-9, rtol=0)
        QTest.mouseRelease(viewer._surface, Qt.MouseButton.LeftButton, pos=end)
        QTest.qWait(30)
        check_motion(30)
        if vertices:
            viewer.set_standard_view("back")
            QTest.qWait(30)
        for cause in ("escape", "button", "axis"):
            assembly.component_scroll.ensureWidgetVisible(assembly.rotation_axis_pick_button)
            QTest.mouseClick(assembly.rotation_axis_pick_button, Qt.MouseButton.LeftButton)
            QTest.qWait(30)
            assert viewer._center_pick is not None
            if vertices:
                # I rozpracovaný pár musí zmizet bez nahrazení předchozí osy.
                QTest.mouseClick(viewer._surface, Qt.MouseButton.LeftButton, pos=screen(pivot))
                QTest.qWait(30)
                assert "first" in viewer._center_pick
            if cause == "escape":
                QTest.keyClick(viewer._surface, Qt.Key.Key_Escape)
            elif cause == "button":
                QTest.mouseClick(assembly.rotation_axis_pick_button, Qt.MouseButton.LeftButton)
            else:
                assembly.batch_rotation_axis.setCurrentText("Z")
            QTest.qWait(30)
            assert viewer._center_pick is None and assembly._selection == ids
            assert getattr(assembly, f"_rotation_{kind}") == (point, direction)
            assert session.assembly.to_dict() == before and len(session._undo) == steps
        reference = {"line": "přímou hranu", "plane": "rovinnou plochu",
                     "vertices": "dvojici vrcholů různých dílů"}.get(
            kind, "válcovou plochu")
        refused = {"line": "kružnice odmítnuta", "plane": "válec odmítnut",
                   "vertices": "první vrchol bez změny, stejný druhý odmítnut"}.get(
            kind, "rovina odmítnuta")
        reverse_label = {"line": "hrana", "plane": "plocha", "vertices": "dva vrcholy"}.get(
            kind, "válec")
        lines.append(f"✓ Obrácení směru osy ({reverse_label}): "
                     "tři skutečné kliky, druhý vrátí původní směr; bod, výběr a historie "
                     "beze změny; Enter 90° i tažení 30° kolem obrácené osy, jeden Zpět/Znovu")
        transparency = "35 %" if single else "35/85 %"
        lines.append(f"✓ {label}: skutečný výběr reference ({reference}); "
                     f"přesný bod i směr, {refused}, výběr/plochy/vazby/kamera/pole "
                     "a historie zachovány; Enter 90° i tažení 30° kolem stejné osy, "
                     f"{transparency}, jeden krok Zpět/Znovu; Esc/tlačítko/změna osy ruší výběr")
        return True
    except Exception:  # noqa: BLE001 -- diagnostika staženého balíčku
        lines.append(f"✕ {label}:\n" + traceback.format_exc())
        return False
    finally:
        viewer.cancel_rotation_center_pick()
        viewer.cancel_selection_drag()
        while len(session._undo) > initial_steps:
            session.undo()
        assembly.batch_rotation_axis.setCurrentText("Z")
        setattr(assembly, f"_rotation_{kind}", None)
        assembly.rotation_handles.setChecked(False)
        assembly._refresh()
        assembly.reset_transparency()
        assembly.show_all()


def _self_test_assembly_parameters(assembly, lines) -> bool:
    """Skutečný modální editor: zadání, vazba, Zpět/Znovu a odmítnuté smazání."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialogButtonBox, QLineEdit

    from skodacad.gui.assembly_parameters import AssemblyParametersDialog

    session, viewer = assembly.session, assembly.viewer
    failures = []
    before = session.assembly.to_dict()

    def edit(dialog, row, column, text):
        dialog.table.setFocus()
        dialog.table.setCurrentCell(row, column)
        dialog.table.editItem(dialog.table.item(row, column))
        field = next(e for e in dialog.table.findChildren(QLineEdit) if e.isVisible())
        field.selectAll()
        QTest.keyClicks(field, text)
        QTest.keyClick(field, Qt.Key.Key_Return)
        QTest.qWait(20)  # delegát buňky se zavírá odloženě

    def interact(remove=False):
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, AssemblyParametersDialog), "editor se neotevřel"
            if remove:
                dialog.table.setCurrentCell(0, 0)
                QTest.mouseClick(dialog.delete_button, Qt.MouseButton.LeftButton)
                QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
                assert dialog.isVisible() and "mezera" in dialog.message.text()
                assert session.assembly.to_dict() == before
                QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel),
                                 Qt.MouseButton.LeftButton)
                return
            assert dialog.usage_table.rowCount() == 1
            assert dialog.usage_table.item(0, 0).text() == "Vazba „Víčko na okraji“ (v1)"
            edit(dialog, 0, 1, "12,5")
            assert dialog.table.item(0, 2).text() == "12,5"
            QTest.mouseClick(dialog.add_button, Qt.MouseButton.LeftButton)
            field = next(e for e in dialog.table.findChildren(QLineEdit) if e.isVisible())
            field.selectAll()
            QTest.keyClicks(field, "polovina")
            QTest.keyClick(field, Qt.Key.Key_Return)
            QTest.qWait(20)
            edit(dialog, 1, 1, "6,25")
            assert dialog.table.item(1, 2).text() == "6,25"
            assert "nepoužívá" in dialog.usage_title.text()
            edit(dialog, 0, 1, "polovina * 2")
            cell = dialog.table.visualItemRect(dialog.table.item(1, 0))
            QTest.mouseClick(dialog.table.viewport(), Qt.MouseButton.LeftButton, pos=cell.center())
            QTest.qWait(20)
            rows = [tuple(dialog.usage_table.item(r, c).text() for c in range(4))
                    for r in range(dialog.usage_table.rowCount())]
            assert ("Parametr „mezera“", "Hodnota", "polovina * 2", "Přímo") in rows
            assert ("Vazba „Víčko na okraji“ (v1)", "Vzdálenost [mm]",
                    "mezera", "Přes mezera") in rows
            assert session.assembly.to_dict() == before, "zadání předčasně změnilo sestavu"
            QTest.qWait(50)
            dialog.grab().save(str(user_dir() / "self-test-parametry-sestavy.png"))
            QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
            assert not dialog.isVisible(), dialog.message.text()
        except Exception:  # noqa: BLE001 -- výjimka z časovače nesmí zůstat mimo self-test
            failures.append(traceback.format_exc())
            if dialog is not None:
                dialog.reject()

    try:
        assembly.raise_()
        assembly.activateWindow()
        assembly._refresh()
        QTest.qWait(100)
        direction, scale = viewer._view.Proj(), viewer._view.Scale()
        history = len(session._undo)
        bounds = next(i.part.bounding_box() for i in session.result.instances
                      if i.ids == ("vicko",))
        z_before = bounds.max.Z
        QTimer.singleShot(100, interact)
        QTest.mouseClick(assembly.parameters_button, Qt.MouseButton.LeftButton)
        assert not failures, "\n".join(failures)
        assert session.assembly.parameters == {"mezera": "polovina * 2", "polovina": 6.25}
        lid = next(i.part for i in session.result.instances if i.ids == ("vicko",))
        assert lid.is_valid and abs(lid.bounding_box().max.Z-z_before-12.5) < 1e-7
        assert session.result.complete and all(c.state == "ok" for c in session.result.constraints)
        assert len(session._undo) == history + 1
        assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
        assembly.undo_action.trigger()
        assert session.assembly.to_dict() == before and len(session._undo) == history
        assembly.redo_action.trigger()
        assert session.result.parameters["mezera"] == 12.5
        assembly.undo_action.trigger()
        result = session.result
        history = (len(session._undo), len(session._redo), session.dirty)
        QTimer.singleShot(100, lambda: interact(remove=True))
        assembly.parameters_action.trigger()
        assert not failures, "\n".join(failures)
        assert session.assembly.to_dict() == before and session.result is result
        assert (len(session._undo), len(session._redo), session.dirty) == history
        lines.append("✓ Parametry sestavy: skutečný editor, Enter v buňce, desetinná čárka, "
                     "závislý výraz, víčko +12,5 mm a 7 splněných vazeb; jeden krok Zpět/Znovu, "
                     "kamera zachována, smazání používaného parametru odmítnuto, Zrušit beze změn")
        lines.append("✓ Použití parametrů sestavy: skutečný výběr řádku, přímý odkaz do parametru "
                     "mezera a nepřímý do vzdálenostní vazby přes mezera, živá změna pracovní "
                     "závislosti, nepoužitá hodnota; prohlížení bez změny modelu a historie")
        return True
    except Exception:  # noqa: BLE001 -- diagnostika sestavené aplikace
        lines.append("✕ Parametry sestavy:\n" + traceback.format_exc())
        return False


def _self_test_assembly_parameter_rename(assembly, lines) -> bool:
    """Nativní přejmenování v pracovní tabulce a jedna společná transakce všech odkazů."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialogButtonBox, QLineEdit

    from skodacad.gui.assembly_parameters import AssemblyParametersDialog

    session, viewer = assembly.session, assembly.viewer
    mark = len(session._undo)
    original = session.assembly.to_dict()
    failures = []

    def physical():
        return [(i.ids, i.part.is_valid, round(i.part.volume, 7),
                 sorted(tuple(round(v, 7) for v in p) for p in i.part.vertices()))
                for i in session.result.instances]

    def finish_name(dialog, name):
        field = next(e for e in dialog.table.findChildren(QLineEdit) if e.isVisible())
        field.selectAll()
        QTest.keyClicks(field, name)
        QTest.keyClick(field, Qt.Key.Key_Return)
        QTest.qWait(20)

    def interact(cancel=False):
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, AssemblyParametersDialog), "editor se neotevřel"
            if not cancel:
                QTest.mouseClick(dialog.add_button, Qt.MouseButton.LeftButton)
                finish_name(dialog, "polovina")
                dialog.table.setCurrentCell(1, 1)
                dialog.table.editItem(dialog.table.item(1, 1))
                finish_name(dialog, "mezera/2")
            dialog.table.setCurrentCell(0, 0)
            QTest.mouseClick(dialog.rename_button, Qt.MouseButton.LeftButton)
            if not cancel:
                finish_name(dialog, "polovina")
                assert "už existuje" in dialog.message.text()
                assert dialog.table.item(0, 0).text() == "mezera"
                QTest.mouseClick(dialog.rename_button, Qt.MouseButton.LeftButton)
            finish_name(dialog, "zrusena" if cancel else "vule_vicka")
            assert session.assembly.to_dict() == before, "přejmenování předčasně změnilo model"
            if cancel:
                QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel),
                                 Qt.MouseButton.LeftButton)
                return
            assert dialog.parameters() == {"vule_vicka": 0, "polovina": "vule_vicka/2"}
            rows = [tuple(dialog.usage_table.item(r, c).text() for c in range(4))
                    for r in range(dialog.usage_table.rowCount())]
            assert any(r[1] == "Posun X [mm]" and r[2] == "vule_vicka-32" for r in rows)
            assert any(r[1] == "Otočení Z [°]" and r[2] == "vule_vicka" for r in rows)
            assert any(r[1] == "Vzdálenost [mm]" and r[2] == "vule_vicka" for r in rows)
            QTest.qWait(30)
            dialog.grab().save(str(user_dir() / "self-test-prejmenovani-parametru.png"))
            QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
            assert not dialog.isVisible(), dialog.message.text()
        except Exception:  # noqa: BLE001 -- zachytit chybu z události modálního okna
            failures.append(traceback.format_exc())
            if dialog is not None:
                dialog.reject()

    try:
        # Výrazy dávají stejné souřadnice jako původní nožička a ověří také polohu/otočení.
        session.set_placement("nozicka_1", position=["mezera-32", -17, -3],
                              rotation=[0, 0, "mezera"])
        assembly._refresh()
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(100)
        before, shape = session.assembly.to_dict(), physical()
        sources = {s.file: s.file.read_bytes() for s in session.result.statuses}
        history = len(session._undo)
        direction, scale = viewer._view.Proj(), viewer._view.Scale()
        QTimer.singleShot(100, interact)
        QTest.mouseClick(assembly.parameters_button, Qt.MouseButton.LeftButton)
        assert not failures, "\n".join(failures)
        assert session.assembly.parameters == {"vule_vicka": 0, "polovina": "vule_vicka/2"}
        assert session.assembly.constraints[0].value == "vule_vicka"
        foot = session.assembly.component("nozicka_1")
        assert foot.position[0] == "vule_vicka-32" and foot.rotation[2] == "vule_vicka"
        assert physical() == shape and all(item[1] for item in shape)
        assert session.result.complete and all(c.state == "ok" for c in session.result.constraints)
        assert len(session._undo) == history + 1
        assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
        assembly.undo_action.trigger()
        assert session.assembly.to_dict() == before and len(session._undo) == history
        assembly.redo_action.trigger()
        assert session.assembly.constraints[0].value == "vule_vicka" and physical() == shape
        assembly.undo_action.trigger()
        result = session.result
        history = (len(session._undo), len(session._redo), session.dirty)
        QTimer.singleShot(100, lambda: interact(cancel=True))
        assembly.parameters_action.trigger()
        assert not failures, "\n".join(failures)
        assert session.assembly.to_dict() == before and session.result is result
        assert (len(session._undo), len(session._redo), session.dirty) == history
        assert all(path.read_bytes() == content for path, content in sources.items())
        lines.append("✓ Přejmenování parametru sestavy: skutečné tlačítko a Enter, mezera → "
                     "vule_vicka v parametru/poloze/otočení/vazbě i přehledu použití; geometrie "
                     "a kamera zachovány, 7 vazeb splněno, jeden Zpět/Znovu, kolize názvu "
                     "odmítnuta, Zrušit i zdrojové soubory beze změn")
        return True
    except Exception:  # noqa: BLE001 -- diagnostika sestavené aplikace
        lines.append("✕ Přejmenování parametru sestavy:\n" + traceback.format_exc())
        return False
    finally:
        while len(session._undo) > mark:
            session.undo()
        assert session.assembly.to_dict() == original


def _self_test_assembly_parameter_navigation(assembly, lines) -> bool:
    """Skutečné kliknutí v modálním editoru: výběr ve stromu i nativním 3D, bez přepočtu."""
    import json

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialogButtonBox, QLineEdit

    from skodacad.assembly_parameter_usage import UsageTarget
    from skodacad.gui.assembly_parameters import AssemblyParametersDialog

    session, viewer = assembly.session, assembly.viewer
    mark = len(session._undo)
    original = session.assembly.to_dict()
    failures = []

    def finish_cell(dialog, text):
        field = next(e for e in dialog.table.findChildren(QLineEdit) if e.isVisible())
        field.selectAll()
        QTest.keyClicks(field, text)
        QTest.keyClick(field, Qt.Key.Key_Return)
        QTest.qWait(20)

    def click(dialog, kind, id_):
        row = dialog._usage_targets.index(UsageTarget(kind, id_))
        item = dialog.usage_table.item(row, 0)
        dialog.usage_table.scrollToItem(item)
        QTest.mouseClick(dialog.usage_table.viewport(), Qt.MouseButton.LeftButton,
                         pos=dialog.usage_table.visualItemRect(item).center())
        QTest.qWait(30)

    def interact():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, AssemblyParametersDialog), "editor se neotevřel"
            QTest.mouseClick(dialog.add_button, Qt.MouseButton.LeftButton)
            finish_cell(dialog, "polovina")
            dialog.table.setCurrentCell(1, 1)
            dialog.table.editItem(dialog.table.item(1, 1))
            finish_cell(dialog, "mezera/2")
            dialog.table.setCurrentCell(0, 0)
            QTest.mouseClick(dialog.rename_button, Qt.MouseButton.LeftButton)
            finish_cell(dialog, "vule")
            dialog.table.setCurrentCell(0, 1)
            dialog.table.editItem(dialog.table.item(0, 1))
            finish_cell(dialog, "12,5")
            renames = list(dialog._renames)
            assert ("mezera", "vule") in renames
            click(dialog, "component", "nozicka_1")
            assert assembly._selection == (("nozicka_1",),) and assembly._constraint is None
            assert json.loads(assembly.tree.currentItem().data(0, Qt.ItemDataRole.UserRole)) == [
                "nozicka_1"]
            assert viewer._highlight is not None, "díl se ve 3D nezvýraznil"
            viewer.selection_moved.emit(old_move)
            assert session.assembly.to_dict() == before, "přijal se starý tah"
            assembly.tree.collapseAll()
            click(dialog, "constraint", "v1")
            assert assembly._constraint == "v1" and not assembly._selection
            assert json.loads(assembly.tree.currentItem().data(0, Qt.ItemDataRole.UserRole)) == {
                "constraint": "v1"}
            assert assembly.tree.currentItem().parent().isExpanded()
            assert viewer._highlight is not None and len(session.constraint_faces("v1")) == 2
            assert dialog.parameters() == {"vule": 12.5, "polovina": "vule/2"}
            assert dialog._renames == renames and dialog.isVisible()
            assert "Vybráno:" in dialog.usage_navigation.text()
            dialog.grab().save(str(user_dir() / "self-test-vyber-z-pouziti-parametru.png"))
            click(dialog, "parameter", "polovina")
            assert dialog.table.currentRow() == 1 and assembly._constraint == "v1"
            assert session.assembly is source and session.result is result
            assert session.assembly.to_dict() == before
            assert (len(session._undo), len(session._redo), session.dirty) == history
            assert viewer._view.Proj() == direction and abs(viewer._view.Scale()-scale) < 1e-9
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel),
                             Qt.MouseButton.LeftButton)
        except Exception:  # noqa: BLE001 -- chyby z událostí modálního dialogu do protokolu
            failures.append(traceback.format_exc())
            if dialog is not None:
                dialog.reject()

    try:
        session.set_placement("nozicka_1", position=["mezera-32", -17, -3],
                              rotation=[0, 0, "mezera"])
        assembly._refresh()
        assembly.select(("nozicka_1",))
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(100)
        source, result = session.assembly, session.result
        before = source.to_dict()
        history = (len(session._undo), len(session._redo), session.dirty)
        sources = {s.file: s.file.read_bytes() for s in result.statuses}
        direction, scale = viewer._view.Proj(), viewer._view.Scale()
        old_move = {"token": assembly._move_token(), "delta": [5, 0, 0]}
        QTimer.singleShot(100, interact)
        QTest.mouseClick(assembly.parameters_button, Qt.MouseButton.LeftButton)
        assert not failures, "\n".join(failures)
        assert session.assembly is source and session.result is result
        assert session.assembly.to_dict() == before and assembly._constraint == "v1"
        assert (len(session._undo), len(session._redo), session.dirty) == history
        assert len(result.constraints) == 7 and all(c.state == "ok" for c in result.constraints)
        assert all(path.read_bytes() == content for path, content in sources.items())
        lines.append("✓ Výběr z použití parametru sestavy: skutečné kliknutí na díl, vazbu "
                     "a navazující parametr; strom i nativní 3D zvýraznění, rozbalení vazeb, "
                     "pracovní přejmenování a 12,5 zachovány; starý tah odmítnut, kamera, "
                     "model, výsledek, historie a zdroje beze změn, 7 vazeb splněno, "
                     "Zrušit ponechá pouze výběr")
        return True
    except Exception:  # noqa: BLE001 -- diagnostika sestavené aplikace
        lines.append("✕ Výběr z použití parametru sestavy:\n" + traceback.format_exc())
        return False
    finally:
        while len(session._undo) > mark:
            session.undo()
        assert session.assembly.to_dict() == original


def _self_test_assembly_parameter_preview(assembly, lines) -> bool:
    """Dvě skutečná modální okna: porovnání 3D, návrat, potvrzení a zastaralý návrh."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialogButtonBox, QLineEdit

    from skodacad.gui.assembly_parameter_preview import AssemblyParameterPreviewDialog
    from skodacad.gui.assembly_parameters import AssemblyParametersDialog

    session, viewer = assembly.session, assembly.viewer
    mark = len(session._undo)
    original = session.assembly.to_dict()
    failures = []

    def edit(dialog, row, column, text):
        dialog.table.setCurrentCell(row, column)
        dialog.table.editItem(dialog.table.item(row, column))
        field = next(e for e in dialog.table.findChildren(QLineEdit) if e.isVisible())
        field.selectAll()
        QTest.keyClicks(field, text)
        QTest.keyClick(field, Qt.Key.Key_Return)
        QTest.qWait(20)

    def lid(result):
        return next(i.part for i in result.instances if i.ids == ("vicko",))

    def inspect_preview(mode):
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, AssemblyParameterPreviewDialog), "náhled se neotevřel"
            QTest.qWait(150)
            assert dialog.viewer.ready and dialog.viewer._ais is not None
            assert dialog.viewer is not viewer and dialog.viewer._highlight is not None
            assert dialog.changed_ids == {"vicko"} and "7/7" in dialog.summary.text()
            assert abs(lid(dialog.preview.result).bounding_box().max.Z
                       - lid(result).bounding_box().max.Z - 12.5) < 1e-6
            assert session.assembly is source and session.result is result
            assert session.assembly.to_dict() == before
            assert (len(session._undo), len(session._redo), session.dirty) == history
            direction, scale = dialog.viewer._view.Proj(), dialog.viewer._view.Scale()
            QTest.mouseClick(dialog.original_box, Qt.MouseButton.LeftButton)
            assert dialog.original_box.isChecked() and "Původní" in dialog.heading.text()
            QTest.mouseClick(dialog.original_box, Qt.MouseButton.LeftButton)
            assert not dialog.original_box.isChecked()
            assert dialog.viewer._view.Proj() == direction
            assert abs(dialog.viewer._view.Scale() - scale) < 1e-9
            if mode == "apply":
                _screenshot(dialog, user_dir() / "self-test-nahled-parametru-sestavy.png")
                QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
                assert not dialog.isVisible(), dialog.message.text()
            elif mode == "stale":
                session.set_info(name="Novější sestava")
                new_source, new_result = session.assembly, session.result
                QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
                assert "od náhledu změnil" in dialog.message.text()
                assert not dialog.apply_button.isEnabled()
                assert session.assembly is new_source and session.result is new_result
                QTest.mouseClick(dialog.back_button, Qt.MouseButton.LeftButton)
            else:
                QTest.mouseClick(dialog.back_button, Qt.MouseButton.LeftButton)
        except Exception:  # noqa: BLE001 -- chyby nativních událostí do zprávy
            failures.append(traceback.format_exc())
            if dialog is not None:
                dialog.reject()

    def inspect_parameters(mode):
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, AssemblyParametersDialog), "editor se neotevřel"
            QTest.mouseClick(dialog.add_button, Qt.MouseButton.LeftButton)
            field = next(e for e in dialog.table.findChildren(QLineEdit) if e.isVisible())
            field.selectAll()
            QTest.keyClicks(field, "polovina")
            QTest.keyClick(field, Qt.Key.Key_Return)
            QTest.qWait(20)
            edit(dialog, 1, 1, "6,25")
            edit(dialog, 0, 1, "polovina*2")
            edit(dialog, 0, 0, "vule")
            QTimer.singleShot(100, lambda: inspect_preview(mode))
            QTest.mouseClick(dialog.preview_button, Qt.MouseButton.LeftButton)
            assert not failures, "\n".join(failures)
            if mode != "apply":
                assert dialog.isVisible()
                assert dialog.parameters() == {"vule": "polovina*2", "polovina": 6.25}
                if mode == "back":
                    edit(dialog, 0, 1, "missing+1")
                    assert not dialog.preview_button.isEnabled()
                    assert "neznámý" in dialog.message.text()
                QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel),
                                 Qt.MouseButton.LeftButton)
        except Exception:  # noqa: BLE001 -- chyby nativních událostí do zprávy
            failures.append(traceback.format_exc())
            if dialog is not None:
                dialog.reject()

    try:
        assembly._refresh()
        assembly.raise_()
        assembly.activateWindow()
        QTest.qWait(100)
        base_direction, base_scale = viewer._view.Proj(), viewer._view.Scale()
        sources = {s.file: s.file.read_bytes() for s in session.result.statuses}
        for mode in ("back", "apply", "stale"):
            source, result = session.assembly, session.result
            before = source.to_dict()
            history = (len(session._undo), len(session._redo), session.dirty)
            QTimer.singleShot(100, lambda mode=mode: inspect_parameters(mode))
            QTest.mouseClick(assembly.parameters_button, Qt.MouseButton.LeftButton)
            assert not failures, "\n".join(failures)
            assert viewer._view.Proj() == base_direction
            assert abs(viewer._view.Scale() - base_scale) < 1e-9
            if mode == "apply":
                assert session.assembly.parameters == {"vule": "polovina*2", "polovina": 6.25}
                assert len(session._undo) == history[0] + 1
                assert abs(lid(session.result).bounding_box().max.Z
                           - lid(result).bounding_box().max.Z - 12.5) < 1e-6
                assert session.result.complete and len(session.result.constraints) == 7
                assembly.undo_action.trigger()
                assert session.assembly.to_dict() == before
                assembly.redo_action.trigger()
                assert session.assembly.constraints[0].value == "vule"
                assembly.undo_action.trigger()
            elif mode == "back":
                assert session.assembly is source and session.result is result
                assert session.assembly.to_dict() == before
                assert (len(session._undo), len(session._redo), session.dirty) == history
            else:
                assert session.assembly.name == "Novější sestava"
                assert session.assembly.parameters == before["parameters"]
        assert all(path.read_bytes() == data for path, data in sources.items())
        lines.append("✓ Náhled parametrů sestavy: skutečná tlačítka a 3D okno, "
                     "desetinná čárka, závislý výraz a přejmenování, víčko +12,5 mm "
                     "a 7 splněných vazeb; přepínání původní/náhled, návrat i Zrušit "
                     "bez změny modelu/výsledku/historie/zdrojů a hlavní kamery; "
                     "Použít jedním Zpět/Znovu, chybný výraz a zastaralý náhled odmítnuty")
        return True
    except Exception:  # noqa: BLE001 -- diagnostika sestavené aplikace
        lines.append("✕ Náhled parametrů sestavy:\n" + traceback.format_exc())
        return False
    finally:
        while len(session._undo) > mark:
            session.undo()
        assert session.assembly.to_dict() == original


def _self_test_constraints(window, lines: list[str], folder) -> bool:
    """Zabalená aplikace: vazby P5.3 – řešič (numpy) v balíčku, ukázka plně určená."""
    sample = folder / "sestavy" / "krabicka_s_vazbami.json"
    if not sample.is_file():
        lines.append("✕ Vazby: chybí ukázka krabicka_s_vazbami.json")
        return False
    assembly = window.open_assembly(sample, template=True)
    if assembly is None:
        lines.append("✕ Vazby: ukázku nejde otevřít")
        return False
    session = assembly.session
    result = session.result
    try:
        session.set_parameters({"mezera": 15})  # víčko se nadzvedne o 15 mm
        lifted = session.assembly.component("vicko").position
        session.undo()
        back = session.assembly.component("vicko").position
    except Exception as exc:  # noqa: BLE001 – self-test hlásí, nepadá
        lines.append(f"✕ Vazby: {exc}")
        ok = False
    else:
        freedom = result.status("vicko").freedom_text if result is not None else ""
        ok = (result is not None and result.complete and len(result.constraints) == 7
              and freedom == "plně určená" and lifted == [0, 0, 47] and back == [0, 0, 32])
        if ok:
            lines.append("✓ Vazby: 7 splněných, víčko plně určené, mezera 15 → z = 47 a Zpět")
        else:
            problems = "; ".join(result.problems) if result is not None else "bez výsledku"
            lines.append(f"✕ Vazby: {freedom}, víčko {lifted}; {problems}")
    if ok:
        ok = _self_test_assembly_parameters(assembly, lines) and ok
        ok = _self_test_assembly_parameter_rename(assembly, lines) and ok
        ok = _self_test_assembly_parameter_navigation(assembly, lines) and ok
        ok = _self_test_assembly_parameter_preview(assembly, lines) and ok
    session.dirty = False
    assembly.close()
    return ok


def _self_test_checks(window, lines: list[str], folder) -> bool:
    """Zabalená aplikace: kontroly P5.4 – průnik jádrem, kusovník a export STEP (XCAF)."""
    sample = folder / "sestavy" / "deska_se_sroubem.json"
    if not sample.is_file():
        lines.append("✕ Kontrola sestavy: chybí ukázka deska_se_sroubem.json")
        return False
    assembly = window.open_assembly(sample, template=True)
    if assembly is None:
        lines.append("✕ Kontrola sestavy: ukázku nejde otevřít")
        return False
    session = assembly.session
    step = user_dir() / "self-test-sestava.step"
    try:
        assembly.run_check()  # bez pomocného procesu (jako ostatní části self-testu)
        outcome = session.last_check()
        rows = session.bill()
        session.export_step(step)
        written = step.read_text(errors="replace")
    except Exception as exc:  # noqa: BLE001 – self-test hlásí, nepadá
        lines.append(f"✕ Kontrola sestavy: {exc}")
        ok = False
    else:
        kinds = [finding.kind for finding in outcome.findings] if outcome else []
        volume = outcome.findings[0].volume if kinds else 0
        ok = (kinds == ["accepted"] and abs(volume - 12.959) < 0.001 and len(rows) == 2
              and written.startswith("ISO-10303-21") and "'sroub_1'" in written)
        if ok:
            lines.append(f"✓ Kontrola sestavy: přijatá kolize 12,959 mm³, kusovník 2 řádky, "
                         f"STEP {step} ({step.stat().st_size} B)")
        else:
            lines.append(f"✕ Kontrola sestavy: nálezy {kinds}, objem {volume}, kusovník "
                         f"{len(rows)} řádků, STEP {written[:20]!r}")
    session.dirty = False
    assembly.close()
    return ok


def _self_test_design(window, lines: _Report) -> bool:
    """Zabalená aplikace: etapa 15B, dvě varianty, náhled a PDF bez změny souboru."""
    from skodacad.gui.audit_panel import write_pdf
    from skodacad.ndt.design import TITLE, Design

    folder = examples_dir()
    model = folder / "ndt" / "navrh_kapsa.json" if folder is not None else None
    if model is None or not model.is_file():
        lines.append("✕ Konstrukční návrh: chybí referenční díl č. 10")
        return False
    lines.stream.write("  … Konstrukční návrh (15B)\n")
    lines.stream.flush()
    window.session.dirty = False
    window.open_model(model, template=True)
    session, panel = window.session, window.design_panel
    original = session.document.to_dict()
    settings = Design.from_dict({
        "study": "s3", "parameters": [{"name": "a", "values": [40, 90]}],
        "conditions": [{"measurement": "m1", "min": 15, "reason": "stěna"}],
        "options": {"verify": False, "rejected": False}})
    try:
        outcome = session.compute_ndt_design(settings)
        panel.refresh()
        if len(outcome.variants) != 2 or panel.table.rowCount() != 2:
            lines.append("✕ Konstrukční návrh: očekávány 2 varianty")
            return False
        panel.table.selectRow(1)
        if session.document.to_dict() != original:
            lines.append("✕ Konstrukční návrh: náhled změnil původní model")
            return False
        with tempfile.TemporaryDirectory() as temporary:
            paths = session.export_ndt_design(temporary)
            paths.append(write_pdf(outcome.html(), Path(temporary) / "navrh.pdf", title=TITLE))
            ok = ((Path(temporary) / "navrh.pdf").read_bytes().startswith(b"%PDF")
                  and {p.name for p in paths} ==
                  {"navrh.html", "varianty.csv", "navrh.pdf"})
        panel.hide_preview()
        lines.append(("✓ " if ok else "✕ ") +
                     "Konstrukční návrh (15B): 2 varianty, náhled bez změny modelu, "
                     "HTML/CSV/PDF")
        return ok
    except Exception as exc:  # noqa: BLE001 – self-test má chybu vysvětlit
        lines.append(f"✕ Konstrukční návrh (15B): {type(exc).__name__}: {exc}")
        return False
    finally:
        panel.hide_preview()
        session.dirty = False


def _self_test_ndt_geometry(folder: Path, lines: list[str]) -> bool:
    """NDT geometrické jádro bez okna (kontrolu dělá jádro – okno nemodeluje)."""
    from skodacad.ndt import mt, pt, rt
    from skodacad.ndt.geometry import self_check

    ok, text = self_check(folder)
    lines.append(("✓ " if ok else "✕ ") + text)
    pt_ok, pt_text = pt.self_check(folder)
    lines.append(("✓ " if pt_ok else "✕ ") + pt_text)
    mt_ok, mt_text = mt.self_check(folder)
    lines.append(("✓ " if mt_ok else "✕ ") + mt_text)
    rt_ok, rt_text = rt.self_check(folder)
    lines.append(("✓ " if rt_ok else "✕ ") + rt_text)
    return ok and pt_ok and mt_ok and rt_ok


def _self_test_audit(window, lines: _Report) -> bool:
    """Předběžný NDT audit v okně (etapa 14): deska s otvorem, RT studie s hrubou sítí –
    dvě místa u okrajů, klik na místo, složka se zprávou HTML a PDF (Qt PDF v balíčku)."""
    import dataclasses
    import tempfile

    lines.stream.write("  … NDT audit\n")
    lines.stream.flush()
    folder = examples_dir()
    model = folder / "ndt" / "otvor.json" if folder is not None else None
    if model is None or not model.exists():
        lines.append("✕ NDT audit: chybí referenční díl ndt/otvor.json")
        return False
    window.session.dirty = False
    window.open_model(model, template=True)
    session, panel = window.session, window.audit_panel
    session.set_ndt_rt_settings("s2", dataclasses.replace(session.ndt_rt_settings("s2"),
                                                          step_mm=10, image_step_mm=20))
    window.show_audit()
    panel.run_action.trigger()
    audit = session.ndt_audit
    places = audit.places() if audit is not None else []
    if len(places) != 2 or panel.places.rowCount() != 2:
        lines.append(f"✕ NDT audit: čekána 2 místa RT, je {len(places)}")
        return False
    panel.places.selectRow(0)
    QApplication.processEvents()
    with tempfile.TemporaryDirectory() as temporary:
        paths = panel._export(temporary)
        pdf = (Path(temporary) / "zprava.pdf").read_bytes()
        page = (Path(temporary) / "zprava.html").read_text(encoding="utf-8")
        images = page.count('alt="Mapa ve 3D –')  # obrázek z 3D okna (bez OpenGL žádný)
    names = sorted(p.name for p in paths)
    if "zprava.html" not in names or not pdf.startswith(b"%PDF") or b"/Image" not in pdf:
        lines.append(f"✕ NDT audit: zpráva {names}, PDF {pdf[:8]!r}")
        return False
    session.dirty = False
    lines.append(f"✓ NDT audit (14): 2 místa RT u okrajů, zpráva {', '.join(names)} "
                 f"(PDF {len(pdf)} B), obrázky map z 3D: {images}")
    return True


def _self_test_ndt(window, lines: _Report) -> bool:
    """NDT studie v okně: referenční deska – platná, po změně tloušťky zastaralá, Zpět platná
    (a zvýraznění kontrolované oblasti ve 3D)."""
    lines.stream.write("  … NDT studie\n")
    lines.stream.flush()
    folder = examples_dir()
    model = folder / "ndt" / "deska.json" if folder is not None else None
    if model is None or not model.exists():
        lines.append("✕ NDT studie: chybí referenční díl ndt/deska.json")
        return False
    window.session.dirty = False
    window.open_model(model, template=True)
    panel, session = window.ndt_panel, window.session
    panel.studies.setCurrentRow(0)  # → zvýraznění kontrolované oblasti ve 3D
    QApplication.processEvents()
    states = [[r.state for r in session.ndt_studies]]
    field = window._param_fields["t"]
    field.setText("30")
    field.editingFinished.emit()
    states.append([r.state for r in session.ndt_studies])
    window.undo_action.trigger()
    QApplication.processEvents()
    states.append([r.state for r in session.ndt_studies])
    count = len(states[0])  # deska má studii UT i MT (etapa 12) – všechny stejně
    if not count or states != [["ok"] * count, ["stale"] * count, ["ok"] * count]:
        lines.append(f"✕ NDT studie: stavy {' → '.join(map(str, states))} (čekáno platná → "
                     "zastaralá → platná)")
        return False
    item = panel.studies.item(0).text() if panel.studies.count() else "?"
    lines.append(f"✓ NDT studie: OK ({item}; po změně tloušťky zastaralá, Zpět platná)")
    lines.stream.write("  … NDT sonda\n")
    lines.stream.flush()
    top = max(session.result.part.faces(), key=lambda face: face.center().Z)  # horní plocha
    placed = session.place_ndt_probe(session.ndt_studies[0].id, [top.wrapped], (0, 0, 20), 90)
    beam = session.ndt_beam
    shifted = session.shift_ndt_probe(5.0)
    scan = session.scan_ndt_line(10.0, 2.0)
    window._refresh_all()  # sonda i paprsek se nakreslí ve 3D (průhledné tělo, čára, popisek)
    QApplication.processEvents()
    if not placed.ok or not shifted.ok or not scan.free_ranges or beam is None or not beam.ok:
        lines.append(f"✕ NDT sonda: {placed.text}")
        return False
    image = user_dir() / "self-test-sonda.png"
    shown = window.viewer.dump(str(image)) if window.viewer.ready else False
    lines.append(f"✓ NDT sonda: OK ({placed.short}, {beam.short}, {scan.summary}, "
                 f"snímek {image}: {shown})")
    from skodacad.ndt.devices import Probe

    bottom = min(session.result.part.faces(), key=lambda face: face.center().Z)
    session.set_ndt_target("s1", [bottom.wrapped], (0, 0, 0))
    session.set_ndt_device("s1", Probe.straight(10))
    top = max(session.result.part.faces(), key=lambda face: face.center().Z)
    session.place_ndt_probe("s1", [top.wrapped], (0, 0, 20))
    coverage = session.compute_ndt_coverage(mode="line", step_mm=10, length_mm=10)
    window._refresh_all()
    QApplication.processEvents()
    image = user_dir() / "self-test-pokryti.png"
    shown = window.viewer.dump(str(image)) if window.viewer.ready else False
    if not coverage.triangles or coverage.percent("covered") <= 0 or not shown:
        lines.append("✕ Mapa geometrického pokrytí UT: výpočet nebo kreslení selhalo")
        return False
    lines.append(f"✓ Mapa geometrického pokrytí UT: {coverage.percent('covered'):.2f} %, "
                 f"snímek {image}: {shown}")
    session.clear_ndt_placement()
    window._refresh_all()
    volume_model = folder / "ndt" / "cilove_objemy" / "tupy_svar_objem.json"
    session.dirty = False
    window.open_model(volume_model, template=True)
    panel.select("s1")
    window._refresh_all()
    QApplication.processEvents()
    volume = session.ndt_target_volume("s1")
    if (abs(volume.volume_mm3 - 14613.84387633061) > 1e-4
            or panel.coverage_action.isEnabled() or "mm³" not in panel.details.text()):
        lines.append("✕ NDT cílový objem: geometrie, načtení nebo stav ovládání nesouhlasí")
        return False
    lines.append(f"✓ NDT cílový objem (07A): {volume.volume_mm3:.6f} mm³; "
                 "načtení v okně a oddělení od pokrytí OK")
    preview = session.ndt_target_preview("s1")
    drawn = bool(getattr(window.viewer, "_target_objects", None)) if window.viewer.ready \
        else True
    image = user_dir() / "self-test-cil.png"
    shown = window.viewer.dump(str(image)) if window.viewer.ready else False
    if preview is None or abs(preview[0].volume - volume.volume_mm3) > 1e-4 or not drawn:
        lines.append("✕ NDT náhled cílového objemu (07C): těleso se nespočítalo nebo "
                     "nenakreslilo")
        return False
    lines.append(f"✓ NDT náhled cílového objemu (07C): průhledný svar ve 3D, snímek {image}: "
                 f"{shown}")
    from skodacad.ndt.volume_coverage import VolumeCoverageMap

    lines.stream.write("  … NDT objemové pokrytí (07B)\n")
    lines.stream.flush()
    # Malá oblast uvnitř desky prověří zabalený modul, váhy i skutečné osové zásahy.
    session.dirty = False
    window.open_model(folder / "ndt" / "deska.json", template=True)
    session.set_ndt_volume_target("s1", {"kind": "volume", "frame": {
        "origin": [-5, -5, 5], "axis": [0, 1, 0], "across": [1, 0, 0]},
        "length_mm": 10, "profile_mm": [[0, 0], [10, 0], [10, 10], [0, 10]]})
    session.set_ndt_device("s1", Probe.straight(10))
    top = max(session.result.part.faces(), key=lambda face: face.center().Z)
    session.place_ndt_probe("s1", [top.wrapped], (0, 0, 20))
    panel.select("s1")
    window._refresh_all()
    enabled = panel.coverage_action.isEnabled()  # 07C: objem jde spočítat z panelu
    covered = session.compute_ndt_coverage(step_mm=25, target_step_mm=5, bounces=0,
                                           convergence=True)
    if (not isinstance(covered, VolumeCoverageMap) or not enabled
            or abs(covered.total_volume - 1000) > 1e-6
            or abs(covered.volume("covered") - 1000) > 1e-6
            or "convergence" not in covered.assumptions):
        lines.append("✕ NDT objemové pokrytí: objem, osové zásahy, citlivost nebo panel "
                     "nesouhlasí")
        return False
    lines.append(f"✓ NDT objemové pokrytí (07B, panel 07C): {covered.volume('covered'):.6f} / "
                 f"{covered.total_volume:.6f} mm³, {covered.percent('covered'):.2f} %; "
                 "citlivost na krok ověřena")
    from skodacad.ndt.volume_drawing import mesh_areas

    lines.stream.write("  … NDT objemová kresba a průřez (07C)\n")
    lines.stream.flush()
    # Krychle 10 mm celá pokrytá: povrch 600 mm², v průřezu uprostřed zbude 10 × 5 × 10 mm.
    whole = mesh_areas(session.visible_ndt_coverage())
    window._refresh_all()
    panel.cross_section()
    QApplication.processEvents()
    half = mesh_areas(session.visible_ndt_coverage())
    drawn = bool(getattr(window.viewer, "_coverage_objects", None)) if window.viewer.ready \
        else True
    image = user_dir() / "self-test-objem.png"
    shown = window.viewer.dump(str(image)) if window.viewer.ready else False
    session.clear_section()
    window._refresh_all()
    if (len(whole) != 1 or abs(sum(whole.values()) - 600) > 1e-6 or len(half) != 1
            or abs(sum(half.values()) - 400) > 1e-6 or not drawn):
        lines.append(f"✕ NDT objemová kresba: plochy {whole} / v průřezu {half} (čekáno 600 "
                     "a 400 mm² zeleně)")
        return False
    lines.append(f"✓ NDT objemová kresba (07C): povrch 600 mm², průřez svarem 400 mm² "
                 f"zeleně, snímek {image}: {shown}")
    lines += covered.summary()  # i protokol balíčkové zkoušky nese celé vymezení UT
    session.dirty = False
    window.open_model(volume_model, template=True)
    return True


def _self_test_assistant(window, lines: _Report) -> bool:
    """AI asistent bez sítě: skutečná knihovna anthropic s přehranými odpověďmi, pomocné
    vlákno, krok s modelem v hlavním vlákně, obrázek dílu pro AI a celá odpověď jedním Zpět."""
    import time

    import anthropic

    from skodacad.assistant import offline_client

    lines.stream.write("  … AI asistent (bez sítě)\n")
    lines.stream.flush()
    session = window.session
    if session.document is None:
        session.new_document()
    original = session.document.name
    requests: list[dict] = []
    turns = [
        ([{"type": "tool_use", "id": "t1", "name": "set_part_info",
           "input": {"name": "Self-test AI"}}], "tool_use"),
        ([{"type": "tool_use", "id": "t2", "name": "view_part", "input": {"view": "current"}}],
         "tool_use"),
        ([{"type": "text", "text": "Hotovo."}], "end_turn"),
    ]
    panel = window.assistant_panel
    panel.client_factory = lambda settings: offline_client(turns, requests)
    panel.prompt.setPlainText("přejmenuj díl")
    panel.send()
    end = time.monotonic() + 60
    while panel.busy and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)
    if panel.busy or len(requests) != 3:
        lines.append(f"✕ AI asistent: nedoběhl ({panel.history_text()[-300:]})")
        return False
    renamed = session.document.name == "Self-test AI"
    image = requests[2]["body"]["messages"][-1]["content"][0]
    picture = (f"obrázek dílu {len(image['content'][0]['source']['data'])} znaků"
               if not image.get("is_error") else "bez obrázku (3D tady nejde)")
    window.undo_action.trigger()
    undone = session.document.name == original
    panel.new_conversation()
    if not (renamed and undone):
        lines.append(f"✕ AI asistent: přejmenování {renamed}, Zpět {undone}")
        return False
    lines.append(f"✓ AI asistent (bez sítě): OK (anthropic {anthropic.__version__}, krok "
                 f"s modelem, {picture}, Zpět)")
    return True


def _self_test_background(models: list[Path], lines: list[str]) -> bool:
    """Přepočet na pozadí: pomocný proces se musí spustit (ve Windows je to znovu spuštěný
    SkodaCAD.exe) a vrátit stejný díl jako přepočet v okně."""
    from skodacad.document import Document
    from skodacad.rebuild import rebuild
    from skodacad.worker import BackgroundRebuilder

    if not models:
        return True
    document = Document.load(models[0])
    runner = BackgroundRebuilder()
    try:
        started = time.monotonic()
        runner.submit(document.to_dict())
        finished = runner.wait(timeout=180)
    finally:
        runner.close()
    if finished is None or finished.error:
        detail = finished.error if finished else "nedoběhl do 3 minut"
        lines.append(f"✕ Přepočet na pozadí (pomocný proces): {detail}")
        return False
    expected = rebuild(document).part.volume
    if abs(finished.result.part.volume - expected) > 1e-6 * expected:
        lines.append(f"✕ Přepočet na pozadí: objem {finished.result.part.volume:.0f} mm³, "
                     f"čekáno {expected:.0f} mm³")
        return False
    lines.append(f"✓ Přepočet na pozadí (pomocný proces): OK ({models[0].name}, "
                 f"{time.monotonic() - started:.1f} s i se startem procesu)")
    return True


def _self_test_sketcher(window, lines: list[str]) -> bool:
    """Skicář: výchozí obrys (obdélník s kótami) musí řešič plně určit a kružnice uvnitř
    se musí dotknout spodní hrany (tečnost přes skrytý bod dotyku)."""
    from skodacad.gui.sketcher import SketcherDialog
    from skodacad.schema import new_shape

    try:
        dialog = SketcherDialog(new_shape("profile"), window.session.solve_profile, window)
        solution = dialog.solution
        dialog.set_tool("circle")
        dialog.click(20, 12)
        dialog.click(24, 12)
        dialog.select(["s1", "k1"])
        dialog.apply_constraint("tangent")
        circle = dialog.profile["segments"].get("k1")
        touching = (dialog.solution.ok and circle is not None and
                    abs(dialog.profile["points"][circle["center"]][1] - circle["radius"]) < 1e-6)
        dialog.deleteLater()
    except Exception as exc:  # noqa: BLE001 – zpráva do self-testu místo pádu
        lines.append(f"✕ Skicář: {type(exc).__name__}: {exc}")
        return False
    if solution is None or not solution.ok or solution.dof != 0:
        detail = solution.message if solution is not None else "nic se nespočítalo"
        lines.append(f"✕ Skicář: obrys se nevyřešil ({detail})")
        return False
    if not touching:
        lines.append("✕ Skicář: kružnice se nedotkla hrany (tečnost ke kružnici)")
        return False
    lines.append("✓ Skicář a řešič vazeb (SolveSpace): OK (i kružnice a tečnost)")
    return True


def _self_test_drawing(viewer, lines: _Report) -> bool:
    """Každý druh kreslení měření zvlášť: zpráva se zapisuje průběžně, takže když ovladač
    OpenGL spadne, poslední řádek ukáže, na čem."""
    done = []
    for variant in ("line", "point", "ball", "label", "arial", "map", "map_top", "accent",
                    "probe", "target", "points", "plan"):
        lines.stream.write(f"  … kreslení „{variant}“\n")
        lines.stream.flush()
        viewer.probe_drawing(variant)
        done.append(variant)
    lines.append(f"✓ Kreslení značek měření: OK ({', '.join(done)})")
    return True


def _self_test_map(window, lines: _Report) -> bool:
    """Mapa tloušťky stěny celé ukázky: výpočet i nakreslení desítek tisíc barevných bodů."""
    lines.stream.write("  … mapa tloušťky\n")
    lines.stream.flush()
    window.thickness_map_action.trigger()
    QApplication.processEvents()
    found = window.session.thickness_map
    if found is None:
        error = window.session.result.map_error if window.session.result else "?"
        lines.append(f"✕ Mapa tloušťky: nespočítala se ({error})")
        return False
    image = user_dir() / "self-test-mapa.png"
    lines.append(f"✓ Mapa tloušťky: OK (nejtenčí {found.minimum:.2f} mm, {len(found.values)} "
                 f"bodů za {found.seconds:.1f} s, snímek {image}: "
                 f"{window.viewer.dump(str(image))})")
    window.thickness_map_action.trigger()  # vypnout
    return True


def _self_test_section(window, lines: _Report) -> bool:
    """Řez ukázky (přesný řez jádrem, barevné plochy řezu) – i s mapou tloušťky v řezu."""
    lines.stream.write("  … řez modelem\n")
    lines.stream.flush()
    window.section_action.trigger()
    QApplication.processEvents()
    section = window.session.section
    if section is None:
        lines.append(f"✕ Řez modelem: {window.session.section_error or 'nezapnul se'}")
        return False
    window.thickness_map_action.trigger()  # mapa jen na zbylé polovině
    QApplication.processEvents()
    image = user_dir() / "self-test-rez.png"
    lines.append(f"✓ Řez modelem: OK (plocha řezu {section.area:.0f} mm², i s mapou, snímek "
                 f"{image}: {window.viewer.dump(str(image))})")
    window.thickness_map_action.trigger()
    window.section_action.trigger()
    return True


def _self_test_pick(window, part, lines: list[str]) -> bool:
    """Klik doprostřed nejdelší hrany dílu musí něco vybrat (hranu nebo plochu u ní)."""
    viewer = window.viewer
    edge = max(part.edges(), key=lambda e: e.length)
    middle = edge.position_at(0.5)
    x, y = viewer._view.Convert(float(middle.X), float(middle.Y), float(middle.Z))
    viewer._select_at(x, y)
    QApplication.processEvents()
    picked = viewer.selected_shapes()
    if not picked:
        lines.append(f"✕ Výběr kliknutím: na hraně dílu (pixel {x}, {y}) se nic nevybralo")
        return False
    lines.append(f"✓ Výběr kliknutím: OK ({window.session.selection_info(picked).text})")
    # Výběr se hned změří (panel Měření) a čára s popiskem se nakreslí do 3D.
    if window.measure_list.count() == 0:
        lines.append("✕ Měření: na vybrané hraně/ploše se nic nezměřilo")
        return False
    image = user_dir() / "self-test-mereni.png"
    lines.append(f"✓ Měření: OK ({window.measure_list.item(0).text()}, čára ve 3D: "
                 f"{bool(viewer._measure_objects)}, snímek {image}: {viewer.dump(str(image))})")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
