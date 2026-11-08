"""P7.58: srovnání osmi rámů návrhu 1a s aplikací (Linux Xvfb, 1440 × 900).

Spuštění z kořene repozitáře:

    xvfb-run -a -s "-screen 0 1440x900x24" python docs/p7-58-srovnani-ramu.py docs/p7-58-srovnani

Pro každý rám nafotí okno ve stejném stavu jako referenční obrazovka v
``docs/p7-48-navrh-okna/obrazovky/`` a uloží ``<rám>-srovnani.png`` (vlevo návrh,
vpravo aplikace, každý v polovině velikosti).
Skript jen ovládá okno jako uživatel – model ani soubory v ``examples/`` nemění.
"""

import sys
import tempfile
import time
from pathlib import Path

FRAMES = ("2a-model-svetly", "2b-model-tmavy", "2c-ndt-pruvodce", "2d-skicar",
          "3a-nahled-prvku", "3b-mereni", "3c-rez", "3d-ndt-pokryti")
REFERENCES = Path(__file__).resolve().parent / "p7-48-navrh-okna" / "obrazovky"


def side_by_side(reference, actual, target):
    """Vlevo návrh, vpravo aplikace, obojí zmenšené na 720 × 450 px s popiskem."""
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    width, height, label = 720, 450, 28
    image = QImage(width * 2 + 12, height + label, QImage.Format.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    font = QFont()
    font.setPixelSize(15)
    font.setBold(True)
    painter.setFont(font)
    for index, (path, title) in enumerate(((reference, "Návrh 1a"), (actual, "ŠkodaCAD"))):
        left = index * (width + 12)
        source = QImage(str(path)).scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
        painter.drawImage(left, label, source)
        painter.setPen(QColor("#1d1d1f"))
        painter.drawText(QRect(left, 0, width, label), Qt.AlignmentFlag.AlignCenter, title)
    painter.end()
    image.save(str(target))


def main():
    from build123d import Vertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from skodacad.gui.app import examples_dir
    from skodacad.gui.main_window import MainWindow
    from skodacad.worker import BackgroundRebuilder

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    home = Path(tempfile.mkdtemp(prefix="skodacad-p758-"))  # vlastní okno.json, ne autorovo
    runner = BackgroundRebuilder()
    app = QApplication(sys.argv[:1])
    w = MainWindow(examples_dir=examples_dir(), user_dir=home, runner=runner)
    w.resize(1440, 900)
    w.show()
    failures = []

    def wait(ms=400):
        end = time.time() + ms / 1000
        while time.time() < end:
            app.processEvents()

    def settle():
        wait(400)
        while w.session.computing:
            wait(200)
        wait(400)

    def grab(frame):
        wait(700)
        g = w.frameGeometry()
        path = home / f"{frame}.png"  # samotný snímek jen dočasně
        w.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height()).save(str(path))
        side_by_side(REFERENCES / f"{frame}.png", path, out / f"{frame}-srovnani.png")
        print("✓", frame, flush=True)

    def face_at(x, y, z):
        part = w.session.result.part
        return min(part.faces(), key=lambda f: BRepExtrema_DistShapeShape(
            f.wrapped, Vertex(x, y, z).wrapped).Value())

    def open_plate():
        w.session.dirty = False
        w.open_model(examples_dir() / "deska.json", template=True)
        settle()
        w.workspace.reset()
        w.viewer.fit_all()

    def model(frame, appearance):
        w.workspace.set_appearance(appearance)
        open_plate()
        w._selected_id = "upinani"
        w._reload_all()
        w.workspace.show_panel("editor")
        grab(frame)

    def sketch():
        def inside():
            mode = w._sketch_mode
            dialog = mode.dialog
            wait(500)
            dialog.set_tool("line")
            for x, y in ((0, 0), (80, 8), (80, -12), (0, -20), (0, 0)):
                dialog.click(x, y)
            dialog.finish_drawing()
            dialog.set_tool("circle")
            dialog.click(80, -2)
            dialog.click(86, -2)
            dialog.set_tool("select")
            segments = dialog.profile["segments"]
            line = next(n for n, s in segments.items() if s["type"] == "line")
            circle = next(n for n, s in segments.items() if s["type"] == "circle")
            dialog.select([line, circle])
            dialog.canvas.fit()
            grab("2d-skicar")
            mode.palette.cancel.click()

        open_plate()
        QTimer.singleShot(100, inside)
        w.profile_sketch_action.trigger()

    def tools():
        open_plate()
        part = w.session.result.part
        top = max(part.faces(), key=lambda f: (round(f.center().Z, 6), f.area))
        # Obvod horní plochy jako v rámu 3a (bez hran děr).
        w.start_feature_preview("chamfer", shapes=[e.wrapped for e in top.outer_wire().edges()])
        wait(2500)
        grab("3a-nahled-prvku")
        w.cancel_feature_preview()
        settle()
        holes = [face_at(sx * 20 + 3.4, 0, 10) for sx in (-1, 1)]
        w.workspace.show_panel("measure")
        w._selection_changed([h.wrapped for h in holes])
        grab("3b-mereni")
        w._selection_changed([])
        w.workspace.show_panel("section")
        w.section_action.trigger()
        settle()
        grab("3c-rez")
        w.section_action.trigger()
        settle()

    def ndt():
        w.session.dirty = False
        w.open_model(examples_dir() / "ndt" / "deska.json", template=True)
        settle()
        w.workspace.reset()
        w.ribbon.select_page("ndt")
        w.workspace.show_panel("ndt")
        w.ndt_panel.select("s1")
        settle()
        w.viewer.fit_all()
        w._selection_changed([face_at(40, 0, 20).wrapped])
        w.viewer.picked_point = (40.0, 0.0, 20.0)
        w.ndt_panel.place_probe()
        settle()
        grab("2c-ndt-pruvodce")
        w.ndt_panel.ut_wizard.go_next()
        w.ndt_panel.coverage_step.setValue(10)
        w.ndt_panel.coverage_action.trigger()
        settle()
        w.ndt_panel.refresh()
        grab("3d-ndt-pokryti")

    def run():
        try:
            model("2a-model-svetly", "light")
            model("2b-model-tmavy", "dark")
            w.workspace.set_appearance("light")
            sketch()
            tools()
            ndt()
        except Exception as exc:  # noqa: BLE001 – skript má vypsat, co se nepovedlo
            failures.append(exc)
            print("✕", type(exc).__name__, exc, flush=True)
        w.session.dirty = False
        app.quit()

    QTimer.singleShot(500, run)
    app.exec()
    runner.close()
    missing = [f for f in FRAMES if not (out / f"{f}-srovnani.png").exists()]
    if failures or missing:
        raise SystemExit(f"Nepovedlo se: {missing or failures}")


if __name__ == "__main__":
    main()
