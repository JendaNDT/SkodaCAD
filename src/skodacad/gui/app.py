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
    window.session.dirty = False
    window.close()
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
