"""Spuštění aplikace ŠkodaCAD s oknem.

``skodacad-gui [model.json]``          – otevře okno (bez modelu otevře ukázku příruby)
``skodacad-gui --self-test zprava.txt`` – kontrola sestavené aplikace bez obsluhy
``skodacad-gui --screenshot okno.png``  – snímek okna (pro kontrolu v cloudu)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from skodacad import __version__
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
    log.info("Start ŠkodaCAD %s, Python %s, %s", __version__, sys.version.split()[0],
             sys.platform)
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

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("ŠkodaCAD")
    _install_error_handler(log_path)

    from skodacad.gui.main_window import MainWindow

    window = MainWindow(examples_dir=examples_dir(), user_dir=user_dir())
    window.show()

    def open_initial() -> None:
        if args.model:
            window.open_model(args.model)
        elif examples_dir() and (examples_dir() / "priruba.json").exists():
            window.open_model(examples_dir() / "priruba.json", template=True)

    QTimer.singleShot(0, open_initial)
    if args.screenshot:
        QTimer.singleShot(2500, lambda: (_screenshot(window, args.screenshot), app.quit()))
    return app.exec()


def _screenshot(window, path: Path) -> None:
    window.viewer.fit_all()
    QApplication.processEvents()
    screen = window.screen()
    geometry = window.frameGeometry()
    image = screen.grabWindow(0, geometry.x(), geometry.y(), geometry.width(), geometry.height())
    image.save(str(path))
    log.info("Snímek okna uložen do %s", path)


def run_self_test(report_path: Path) -> int:
    """Kontrola sestavené aplikace: jádro, exporty, ukázky a 3D prohlížeč."""
    lines: list[str] = []
    ok = True
    try:
        import build123d
        import OCP
        import PySide6

        lines += [
            f"ŠkodaCAD {__version__}",
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
        last_part = None
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
                last_part = result.part

        ok = _self_test_window(lines, last_part) and ok
    except Exception:  # noqa: BLE001 – zpráva musí vzniknout i při nečekané chybě
        ok = False
        lines.append("✕ Neočekávaná chyba:\n" + traceback.format_exc())

    lines.append("VÝSLEDEK: OK" if ok else "VÝSLEDEK: CHYBA")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("Self-test: %s", "OK" if ok else "CHYBA")
    return 0 if ok else 1


def _self_test_window(lines: list[str], part) -> bool:
    """Otevře hlavní okno se skutečným 3D prohlížečem. Selhání OpenGL není chyba aplikace."""
    from skodacad.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(["skodacad-gui"])
    window = MainWindow(examples_dir=examples_dir(), user_dir=user_dir())
    window.resize(900, 600)
    window.show()
    for _ in range(20):
        app.processEvents()
    viewer = window.viewer
    viewer.show_part(part, fit=True)
    app.processEvents()
    ok = True
    if viewer.ready:
        image = user_dir() / "self-test-3d.png"
        lines.append(f"✓ Okno a 3D prohlížeč: OK (snímek {image}: {viewer.dump(str(image))})")
        ok = _self_test_pick(window, part, lines)
    elif viewer.failed_stage in ("display", "opengl"):
        reason = "chybí obrazovka" if viewer.failed_stage == "display" else "OpenGL nejde spustit"
        lines.append(f"! Okno OK, 3D zobrazení tady nejde ({reason}): {viewer.error}")
    else:
        ok = False
        lines.append(f"✕ 3D prohlížeč: {viewer.failed_stage or 'nespuštěn'}: "
                     f"{viewer.error or 'okno se nezobrazilo'}")
    ok = _self_test_sketcher(window, lines) and ok
    window.session.dirty = False
    window.close()
    return ok


def _self_test_sketcher(window, lines: list[str]) -> bool:
    """Skicář: výchozí obrys (obdélník s kótami) musí řešič plně určit."""
    from skodacad.gui.sketcher import SketcherDialog
    from skodacad.schema import new_shape

    try:
        dialog = SketcherDialog(new_shape("profile"), window.session.solve_profile, window)
        solution = dialog.solution
        dialog.deleteLater()
    except Exception as exc:  # noqa: BLE001 – zpráva do self-testu místo pádu
        lines.append(f"✕ Skicář: {type(exc).__name__}: {exc}")
        return False
    if solution is None or not solution.ok or solution.dof != 0:
        detail = solution.message if solution is not None else "nic se nespočítalo"
        lines.append(f"✕ Skicář: obrys se nevyřešil ({detail})")
        return False
    lines.append("✓ Skicář a řešič vazeb (SolveSpace): OK")
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
    return True


if __name__ == "__main__":
    raise SystemExit(main())
