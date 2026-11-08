"""P7.64: kontrola responzivity okna – stejné rámy návrhu 1a v několika velikostech okna.

Spuštění z kořene repozitáře (obrazovka Xvfb větší než největší zkoušené okno):

    xvfb-run -a -s "-screen 0 1920x1200x24" python docs/p7-64-responzivita.py VÝSTUP

Volitelně ``QT_SCALE_FACTOR=1.25`` (Windows 125 %) – velikosti jsou pak logické body.
Pro každou velikost a rám uloží snímek ``VÝSTUP/<velikost>/<rám>.png`` a do
``VÝSTUP/zprava.json`` zapíše měření: obdélníky karet, překryvy, oříznutí (karta nižší
než obsah), obsah širší než karta, posuvník, šířku volného místa pro 3D, šířku lišty.
Skript jen ovládá okno – model ani soubory v ``examples/`` nemění.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

SIZES = ((960, 600), (1024, 700), (1280, 800), (1440, 900), (1920, 1080))
FRAMES = ("2a-model", "2c-ndt-pruvodce", "2d-skicar", "3a-nahled-prvku", "3b-mereni",
          "3c-rez", "3d-ndt-pokryti")


def main():
    from build123d import Vertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QScrollArea, QStackedWidget

    from skodacad.gui.app import examples_dir
    from skodacad.gui.floating import ContentScroll
    from skodacad.gui.main_window import MainWindow
    from skodacad.worker import BackgroundRebuilder

    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    home = Path(tempfile.mkdtemp(prefix="skodacad-p764-"))  # vlastní okno.json
    runner = BackgroundRebuilder()
    app = QApplication(sys.argv[:1])
    w = MainWindow(examples_dir=examples_dir(), user_dir=home, runner=runner)
    w.show()
    report: dict[str, dict] = {}
    failures = []
    state = {"size": None}

    def wait(ms=400):
        end = time.time() + ms / 1000
        while time.time() < end:
            app.processEvents()

    def settle():
        wait(300)
        while w.session.computing:
            wait(200)
        wait(300)

    def content_width(card):
        holder = card.widget()
        if isinstance(holder, QScrollArea):
            content = holder.widget()
            return (max(content.width(), content.minimumSizeHint().width()),
                    holder.viewport().width())
        page = holder.currentWidget() if isinstance(holder, QStackedWidget) else holder
        return max(page.width(), page.minimumSizeHint().width()), holder.width()

    def measure():
        layer = w.card_layer
        view = w.viewer.rect()
        cards = [c for c in layer.cards if not c.isHidden() and c.isVisible()]
        data = {"cards": {}, "overlaps": [], "problems": []}
        for card in cards:
            g = card.geometry()
            wanted, room = content_width(card)
            scrolls = card.findChildren(ContentScroll)
            entry = {"side": card.side, "rect": [g.x(), g.y(), g.width(), g.height()],
                     "content": wanted, "room": room,
                     "scroll": any(s.overflowing() for s in scrolls),
                     "wanted_height": card.preferred_height()}
            data["cards"][card.objectName()] = entry
            name = card.objectName()
            if not view.contains(g):
                data["problems"].append(f"{name}: mimo 3D pohled {entry['rect']}")
            if wanted > room + 1:
                data["problems"].append(f"{name}: obsah {wanted} px širší než karta {room} px")
            if card.side in ("top", "bottom", "corner") and entry["wanted_height"] > g.height():
                data["problems"].append(f"{name}: oříznutá výška {g.height()} < "
                                        f"{entry['wanted_height']}")
            if card.side == "top":
                content = card.widget()
                hint = max(content.sizeHint().width(), content.minimumWidth()) + 2
                if hint > g.width():
                    data["problems"].append(f"{name}: paleta zúžená {g.width()} < {hint} px")
            if card.side in ("bottom", "corner"):
                content = card.widget()
                hint = max(content.sizeHint().width(), content.minimumWidth()) + 2
                if hint > g.width():
                    data["problems"].append(f"{name}: zúžená {g.width()} < {hint} px")
            if entry["scroll"]:
                data["problems"].append(f"{name}: posuvník (obsah {entry['wanted_height']} px, "
                                        f"karta {g.height()} px)")
        for i, a in enumerate(cards):
            for b in cards[i + 1:]:
                if a.geometry().intersects(b.geometry()):
                    data["overlaps"].append([a.objectName(), b.objectName()])
                    data["problems"].append(f"překryv {a.objectName()} × {b.objectName()}")
        free = layer.free_rect()
        data["free_width"] = free.width()
        data["view"] = [view.width(), view.height()]
        bar = w.main_bar
        data["bar"] = [bar.width(), bar.sizeHint().width(), bar.minimumSizeHint().width()]
        if bar.tabs.width() < bar.tabs.sizeHint().width() - 1:
            data["problems"].append(f"lišta: záložky činností se nevejdou ({bar.tabs.width()} < "
                                    f"{bar.tabs.sizeHint().width()} px, šipky)")
        if bar.minimumSizeHint().width() > bar.width():
            data["problems"].append(f"lišta: potřebuje {bar.minimumSizeHint().width()} px, "
                                    f"má {bar.width()} px")
        if free.width() < 200:
            data["problems"].append(f"3D: volná šířka jen {free.width()} px")
        return data

    def grab(frame):
        wait(600)
        w.card_layer.relayout()
        wait(200)
        size = state["size"]
        folder = out / f"{size[0]}x{size[1]}"
        folder.mkdir(exist_ok=True)
        g = w.frameGeometry()
        w.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height()).save(
            str(folder / f"{frame}.png"))
        report.setdefault(f"{size[0]}x{size[1]}", {})[frame] = measure()
        problems = report[f"{size[0]}x{size[1]}"][frame]["problems"]
        print("✓" if not problems else "!", size, frame, "; ".join(problems), flush=True)

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

    def model():
        open_plate()
        w._selected_id = "upinani"
        w._reload_all()
        w.workspace.show_panel("editor")
        grab("2a-model")

    def sketch(done):
        def inside():
            mode = w._sketch_mode
            dialog = mode.dialog
            wait(400)
            dialog.set_tool("line")
            for x, y in ((0, 0), (80, 8), (80, -12), (0, -20), (0, 0)):
                dialog.click(x, y)
            dialog.finish_drawing()
            dialog.set_tool("select")
            dialog.canvas.fit()
            grab("2d-skicar")
            mode.palette.cancel.click()
            QTimer.singleShot(0, done)

        open_plate()
        QTimer.singleShot(100, inside)
        w.profile_sketch_action.trigger()

    def tools():
        open_plate()
        part = w.session.result.part
        top = max(part.faces(), key=lambda f: (round(f.center().Z, 6), f.area))
        w.start_feature_preview("chamfer", shapes=[e.wrapped for e in top.outer_wire().edges()])
        wait(2000)
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
        w.ndt_panel.coverage_step.setValue(25)
        w.ndt_panel.coverage_convergence.setChecked(False)
        w.ndt_panel.coverage_action.trigger()
        settle()
        w.ndt_panel.refresh()
        grab("3d-ndt-pokryti")
        w.session.clear_ndt_coverage()
        w.ndt_panel.remove_probe()
        w.ribbon.select_page("model")

    sizes = list(SIZES)

    def next_size():
        if not sizes:
            finish()
            return
        size = sizes.pop(0)
        state["size"] = size
        w.resize(*size)
        wait(500)
        try:
            model()
            tools()
            ndt()
        except Exception as exc:  # noqa: BLE001 – skript má vypsat, co se nepovedlo
            failures.append(f"{size}: {type(exc).__name__}: {exc}")
            print("✕", size, type(exc).__name__, exc, flush=True)
        try:
            sketch(next_size)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{size} skicář: {type(exc).__name__}: {exc}")
            QTimer.singleShot(0, next_size)

    def finish():
        (out / "zprava.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
        w.session.dirty = False
        app.quit()

    QTimer.singleShot(500, next_size)
    app.exec()
    runner.close()
    if failures:
        raise SystemExit("Nepovedlo se: " + "; ".join(failures))


if __name__ == "__main__":
    main()
