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
    from skodacad.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(["skodacad-gui"])
    window = MainWindow(examples_dir=examples_dir(), user_dir=user_dir())
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
    ok = _self_test_feature_preview(window, lines) and ok
    ok = _self_test_feature_edit(window, lines) and ok
    ok = _self_test_plate_workflow(window, lines) and ok
    ok = _self_test_native_accessibility(lines) and ok
    ok = _self_test_viewer_lifecycle(window, lines) and ok
    ok = _self_test_assembly(window, lines) and ok
    window.session.dirty = False
    window.close()
    return ok


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

    from PySide6.QtCore import QEvent

    from skodacad.gui.viewer import OccViewer

    if not window.viewer.ready:
        lines.append("! Životnost 3D ploch: chybí grafický prohlížeč")
        return True
    try:
        for _ in range(4):
            viewer = OccViewer()
            viewer.resize(640, 480)
            viewer.show()
            QApplication.processEvents()
            assert viewer.ready, viewer.error
            _check_render_size(viewer)
            viewer.show_part(window.session.result.part, fit=True)
            viewer.resize(720, 520)
            QApplication.processEvents()
            _check_render_size(viewer)
            viewer.fit_all()
            assert viewer.dump(str(user_dir() / "self-test-zivotnost-3d.png"))
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
        ok = _self_test_assembly_views(assembly, lines) and ok
        ok = _self_test_assembly_isolation(assembly, lines) and ok
        ok = _self_test_assembly_visibility(assembly, lines) and ok
        ok = _self_test_assembly_transparency(assembly, lines) and ok
    else:
        lines.append(f"✕ Sestava: {'; '.join(result.problems) if result else 'bez výsledku'}")
    assembly.session.dirty = False
    assembly.close()
    ok = _self_test_constraints(window, lines, folder) and ok
    return _self_test_checks(window, lines, folder) and ok


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
        assert assembly._isolated == lid.ids and assembly._selected == lid.ids
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
    from PySide6.QtGui import QImage
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
        assembly.visibility_action.trigger()
        assert len(Compound(viewer._ais.Shape()).solids()) == 5
        assert not viewer._transparent_parts and assembly._is_transparent(body.ids)
        assembly.show_all()
        assert abs(alpha(body)-.7) < 1e-6
        assembly.isolate_action.trigger()
        assert len(Compound(viewer._ais.Shape()).solids()) == 1 and abs(alpha(body)-.7) < 1e-6
        assembly.reset_transparency_action.trigger()
        assert alpha(body) == 0 and assembly._isolated == body.ids
        assert assembly.position_edits[0].text() == "rozepsaná poloha"
        assert session.assembly.to_dict() == before
        assert history == (len(session._undo), len(session._redo), session.dirty)
        lines.append("✓ Průhlednost sestavy: checkbox/T, AIS 70→0→70 %, obraz změněn, "
                     "skrytí/izolace, výběr/kamera/objem/recept/historie/rozepsané pole beze změny")
        return True
    except Exception:  # noqa: BLE001 -- úplná diagnostika staženého balíčku
        lines.append("✕ Průhlednost sestavy:\n" + traceback.format_exc())
        return False
    finally:
        assembly.reset_transparency()
        assembly.show_all()


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
