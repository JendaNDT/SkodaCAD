"""Nativní pracovní cykly P8.4; žádný reset aplikace či GC mezi cykly."""
from __future__ import annotations

import gc
import importlib.metadata
import json
import math
import multiprocessing
import platform
import sys
import threading
import time
from collections import Counter
from contextlib import nullcontext

from benchmark_p8 import (
    digest,
    history_data,
    inspect_assembly,
    inspect_history,
    make_assembly,
    processor_name,
    worker_pids,
    write,
)

# Kontrola měřiče (ne práce aplikace). P8.5 sem dosadí sondu, která její čas
# vyjme z intervalů Qt (rozhodnutí autora 7. 11. 2026); P8.4 ji měří beze změny.
MEASURER_CHECK = lambda name: nullcontext()  # noqa: E731


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class Driver:
    def __init__(self, app, memory):
        from PySide6.QtCore import QTimer

        self.app, self.memory = app, memory
        self.errors, self.messages = [], []
        self.expected_crash = False
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append(f"{kind.__name__}: {value}")
        self.guard = QTimer()
        self.guard.timeout.connect(self.modal)
        self.guard.start(20)

    def modal(self):
        from PySide6.QtWidgets import QMessageBox

        dialog = self.app.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            text = dialog.text()
            self.messages.append(text)
            if not self.expected_crash or "spadl" not in text:
                self.errors.append(f"Neočekávaný dialog: {text}")
            dialog.accept()  # skutečný dialog se zaznamená, nezůstane bez dozoru viset

    def pump(self, ready, timeout=150):
        from PySide6.QtCore import QEventLoop, QTimer

        loop, timer = QEventLoop(), QTimer()
        deadline, errors = time.monotonic()+timeout, []

        def check():
            try:
                self.memory.check()
                require(not self.errors, str(self.errors))
                require(time.monotonic() < deadline, "Operace nedokončila ochranný čas zkoušky")
                if ready():
                    loop.quit()
            except Exception as exc:  # noqa: BLE001 -- výjimka nesmí utéct z Qt slotu
                errors.append(exc)
                loop.quit()

        timer.timeout.connect(check)
        timer.start(10)
        try:
            loop.exec()  # běžný Qt event loop doručuje i DeferredDelete
        finally:
            timer.stop()
            timer.timeout.disconnect(check)
        if errors:
            raise errors[0]
        require(ready(), "Qt ukončilo čekání před dokončením operace")

    def idle(self):
        until = time.monotonic()+.15
        self.pump(lambda: time.monotonic() >= until, timeout=5)

    def ready(self, window, holes=60, thickness=10):
        self.pump(lambda: not window.session.computing)
        require(not window.session.failure, window.session.failure)
        self.idle()
        return inspect_history(window.session.result, holes, thickness)

    def edit(self, window, value):
        field = window._param_fields["t"]
        field.setText(str(value))
        field.editingFinished.emit()
        window._refresh_progress()
        require(window.session.computing, "Změna nespustila skutečný worker")

    def close(self):
        self.guard.stop()
        self.guard.timeout.disconnect(self.modal)
        sys.excepthook = self.old_hook


def resources(app):
    from skodacad.gui.assembly_parameter_preview import AssemblyParameterPreviewDialog
    from skodacad.gui.assembly_parameters import AssemblyParametersDialog
    from skodacad.gui.assembly_window import AssemblyWindow

    top = app.topLevelWidgets()
    return {"top_levels": len(top), "widgets": len(app.allWidgets()),
            "assembly_windows": sum(isinstance(w, AssemblyWindow) for w in top),
            "parameter_dialogs": sum(isinstance(w, (AssemblyParametersDialog,
                                                     AssemblyParameterPreviewDialog)) for w in top),
            "top_level_classes": dict(Counter(type(w).__name__ for w in top)),
            "python_threads": dict(Counter(t.name for t in threading.enumerate()))}


def preview_and_close(driver, main, path, folder, capture):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from skodacad.gui.app import _screenshot
    from skodacad.gui.assembly_parameter_preview import AssemblyParameterPreviewDialog
    from skodacad.gui.assembly_parameters import AssemblyParametersDialog

    window = main.open_assembly(path)
    require(window is not None, "Sestava se neotevřela")
    driver.pump(lambda: window.viewer.ready and not window.computing)
    with MEASURER_CHECK("assembly-800-copies"):
        inspect_assembly(window.session.result, 800)
    window.select(("c799",))
    window.set_component_transparency(("c799",), 35)
    window.isolate_selected()
    require(len(window.visible_instances()) == 1, "Izolace nezachovala výběr")
    window.show_all()
    window.reset_transparency()
    original = window.session.assembly.to_dict()
    result = window.session.result
    failures, seen = [], []
    deadline = time.monotonic()+30

    def reject_preview():
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, AssemblyParameterPreviewDialog):
            failures.append("Nativní náhled se neotevřel")
            if dialog is not None:
                dialog.reject()
            return
        if not dialog.viewer.ready or not dialog._displayed:
            if time.monotonic() < deadline:
                QTimer.singleShot(20, reject_preview)
                return
            failures.append("Nativní 3D náhled není připravený")
        else:
            seen.append(True)
        dialog.reject()

    def editor():
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, AssemblyParametersDialog):
            failures.append("Editor parametrů se neotevřel")
            if dialog is not None:
                dialog.reject()
            return
        dialog.table.item(0, 1).setText("21")
        QTimer.singleShot(20, reject_preview)
        dialog.preview_button.click()
        dialog.reject()

    QTimer.singleShot(20, editor)
    window.parameters_button.click()
    driver.idle()
    require(not failures and seen == [True], str(failures))
    require(window.session.assembly.to_dict() == original and window.session.result is result
            and not window.session.can_undo, "Zrušený náhled změnil model/výsledek/historii")
    if capture:
        _screenshot(window, folder / f"assembly-{capture}.png")
    ready = window.viewer.ready
    closing_workers = worker_pids(main._assembly_runner)
    require(window.close(), "Čistá sestava se nezavřela")
    # Žádné deleteLater, reset ani gc.collect: běžné uzavření produktu je předmětem měření.
    return {"instances": 800, "volume_mm3": 800000, "selection": "c799",
            "native_view_ready": ready, "preview_native_ready": True,
            "cancel_model_unchanged": True, "assembly_worker_pids": closing_workers}


def step_roundtrip(driver, session, folder):
    from skodacad.step_task import StepTask
    from skodacad.worker import _shape_from

    path = session.export(folder / "current.step")
    limited = StepTask(path, max_rss=1)  # skutečné RSS, nikoli náhrada čtečky nebo vyčerpání stroje
    try:
        driver.pump(lambda: limited._done.is_set())
        outcome = limited.poll()
        require(outcome is not None and "limit paměti" in outcome.error,
                "STEP neodmítl záměrně nedostatečný rozpočet")
        driver.pump(lambda: limited._stopped.is_set(), timeout=10)
        require(not limited._process.is_alive(), "STEP proces po limitu zůstal živý")
    finally:
        limited.cancel()
    task = StepTask(path)
    try:
        driver.pump(lambda: task._done.is_set())
        outcome = task.poll()
        require(outcome is not None and not outcome.error, str(outcome))
        expected = 248*20*12-60*math.pi*3
        require(outcome.facts.solids == 1 and math.isclose(
            outcome.facts.volume_mm3, expected, abs_tol=1e-5), "STEP má jiný analytický objem")
        restored = _shape_from(("Part", outcome.shape_bytes))
        require(restored.is_valid and len(restored.solids()) == 1
                and math.isclose(restored.volume, expected, abs_tol=1e-5),
                "Přenesená STEP geometrie je jiná")
        driver.pump(lambda: task._stopped.is_set(), timeout=10)
        require(not task._process.is_alive(), "Hotový STEP proces zůstal živý")
        return {"limited_process_dead": True, "recovery_process_dead": True,
                "limit_bytes": 1, "payload_bytes": len(outcome.shape_bytes),
                "step_bytes": path.stat().st_size, "solids": 1,
                "volume_mm3": round(restored.volume, 6)}
    finally:
        task.cancel()


def _cycles(folder, cycles, warmups, memory):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from qt_cleanup import dispose_new_widgets, top_levels
    from skodacad.gui.app import _screenshot
    from skodacad.gui.main_window import MainWindow
    from skodacad.worker import MAX_IDLE, BackgroundRebuilder

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)  # měřič musí zaznamenat i stav po běžném closeEvent
    previous = top_levels()
    driver = Driver(app, memory)
    runner = BackgroundRebuilder()
    main = MainWindow(runner=runner, user_dir=folder / "profile", examples_dir=folder)
    main.resize(1200, 800)
    main.show()
    history = write(folder / "history.json", history_data(60))
    assembly = make_assembly(folder / "assembly", 800)
    inputs = {str(p.relative_to(folder)): digest(p) for p in
              (history, assembly, assembly.parent / "box.json")}
    start = time.perf_counter()
    event_count = 0
    stream = (folder / "events.jsonl").open("x", encoding="utf-8")

    def record(phase, facts, cycle=None):
        nonlocal event_count
        driver.idle()
        row = {"phase": phase, "at_s": time.perf_counter()-start,
               "memory": memory.sample(), "resources": resources(app), "facts": facts}
        require(row["memory"]["total_rss_bytes"] is not None,
                "V ustáleném bodě chybí RSS některého živého procesu")
        if cycle is not None:
            row.update(cycle=cycle, warmup=cycle < warmups)
        memory.check()
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
        stream.flush()
        event_count += 1
        print(f"P84_PHASE {cycle} {phase}", flush=True)
        return row

    try:
        driver.pump(lambda: main.viewer.ready)
        record("initial", {"native_view_ready": main.viewer.ready})
        for cycle in range(warmups+cycles):
            require(main.open_model(history), "Historie se neotevřela")
            record("open", driver.ready(main), cycle)
            yield
            driver.edit(main, 11)
            driver.ready(main, thickness=11)
            main.undo_action.trigger()
            driver.ready(main)
            main.redo_action.trigger()
            record("edit-undo-redo", driver.ready(main, thickness=11), cycle)
            yield
            saved = main.session.save(folder / "saved.json")
            require(main.open_model(saved), "Uložený díl se neotevřel")
            record("save-reopen", driver.ready(main, thickness=11), cycle)
            yield
            original = main.session.result
            driver.edit(main, 12)
            cancelled = runner._active.process
            QTimer.singleShot(50, main.stop_action.trigger)
            driver.pump(lambda: not main.session.computing)
            require(not cancelled.is_alive() and main.session.result is original
                    and main.session.document.parameters["t"] == 11,
                    "Zastavit neukončilo proces nebo nevrátilo poslední výsledek")
            main.redo_action.trigger()
            record("cancel-recover", {**driver.ready(main, thickness=12),
                                     "cancelled_process_dead": True}, cycle)
            yield
            del cancelled, original
            original = main.session.result
            driver.expected_crash = True
            offset = len(driver.messages)
            driver.edit(main, 13)
            crashed = runner._active.process
            QTimer.singleShot(50, crashed.kill)
            driver.pump(lambda: not main.session.computing)
            require(not crashed.is_alive() and "spadl" in main.session.failure
                    and main.session.result is original and len(driver.messages) == offset+1,
                    "Pád procesu nezachoval poslední geometrii nebo chybu neukázal")
            driver.expected_crash = False
            main.undo_action.trigger()
            record("crash-recover", {**driver.ready(main, thickness=12),
                                    "crashed_process_dead": True, "error_shown": True}, cycle)
            yield
            del crashed, original
            record("step-limit-recover", step_roundtrip(driver, main.session, folder), cycle)
            yield
            require(main.save(), "Obnovený díl se neuložil")
            capture = "first" if cycle == 0 else "last" if cycle == warmups+cycles-1 else ""
            facts = preview_and_close(driver, main, assembly, folder, capture)
            yield  # vrátit se do hlavní Qt smyčky, která vlastní naplánované DeferredDelete
            alive = {p.pid for p in multiprocessing.active_children() if p.is_alive()}
            require(main._assembly_runner is None
                    and set(facts["assembly_worker_pids"]).isdisjoint(alive),
                    "Po poslední sestavě zůstal její pomocný pool")
            require(main._runner is runner, "Zavření sestavy změnilo pool hlavního dílu")
            facts["assembly_pool_closed"] = True
            record("assembly-preview-close", facts, cycle)
            yield
            if capture:
                _screenshot(main, folder / f"history-{capture}.png")
            owned = set(worker_pids(runner))
            row = record("cycle-end", {**inspect_history(main.session.result, 60, 12),
                                       "owned_worker_pids": sorted(owned)}, cycle)
            actual = {int(pid) for pid in row["memory"]["rss_bytes"]
                      if int(pid) != row["memory"]["parent_pid"]}
            require(actual == owned and len(owned) <= MAX_IDLE,
                    "Po cyklu zůstal cizí nebo nadbytečný pomocný proces")
            require(row["resources"]["parameter_dialogs"] == 0,
                    "Po zavření zůstal editor nebo náhled parametrů")
            require(row["resources"]["assembly_windows"] == 0,
                    "Po běžném zavření zůstalo živé okno sestavy")
            yield
        record("before-diagnostic-gc", {})
        collected = gc.collect()  # oddělená diagnostika; primární cykly už byly změřeny
        record("after-diagnostic-gc", {"collected": collected})
        require(main.close(), "Aplikace se po uložených cyklech nezavřela")
        driver.pump(lambda: not multiprocessing.active_children(), timeout=10)
        record("normal-close", {"owned_workers_dead": True})
        require(all(digest(folder / name) == value for name, value in inputs.items()),
                "Zkouška změnila původní vstupy")
        return {"cycles_completed": cycles, "warmups_completed": warmups,
                "events": event_count, "inputs_sha256": inputs,
                "native_view_ready": main.viewer.ready, "owned_workers_dead": True,
                "environment": {"system": platform.platform(), "python": platform.python_version(),
                    "cpu": processor_name(),
                    "packages": {d.metadata["Name"]: d.version
                        for d in importlib.metadata.distributions()
                        if any(k in d.metadata["Name"].lower() for k in
                               ("build123d", "ocp", "pyside6", "numpy"))}}}
    finally:
        # Nouzový úklid měřiče až PO primárních/diagnostických bodech; není důkazem úspěchu.
        stream.close()
        main.session.dirty = False
        main.close()
        runner.close()
        driver.close()
        dispose_new_widgets(previous)


def run(folder, cycles, warmups, memory):
    """Běžná hlavní Qt smyčka; mezi uživatelskými operacemi jí vždy vrátíme řízení."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    sequence = _cycles(folder, cycles, warmups, memory)
    results, errors = [], []

    def advance():
        try:
            next(sequence)
            QTimer.singleShot(50, advance)
        except StopIteration as done:
            results.append(done.value)
            app.quit()
        except BaseException as exc:  # výjimka se znovu vyvolá mimo Qt callback
            errors.append(exc)
            app.quit()

    QTimer.singleShot(0, advance)
    try:
        app.exec()
    finally:
        sequence.close()
    if errors:
        raise errors[0]
    require(len(results) == 1, "Hlavní Qt smyčka skončila před dokončením cyklů")
    return results[0]
