"""Nativní část měřiče P8.1; vyžaduje skutečnou obrazovku (nejde o FPS ani offscreen)."""

from __future__ import annotations

import statistics
import time

from benchmark_p8 import (
    history_data,
    inspect_assembly,
    inspect_history,
    make_assembly,
    measure,
    worker_pids,
    write,
)


def gui_case(case, folder, repeats, memory, *, case_started):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from skodacad.gui.app import _screenshot
    from skodacad.gui.assembly_parameter_preview import AssemblyParameterPreviewDialog
    from skodacad.gui.assembly_parameters import AssemblyParametersDialog
    from skodacad.gui.assembly_window import AssemblyWindow
    from skodacad.gui.main_window import MainWindow
    from skodacad.worker import BackgroundRebuilder

    app = QApplication.instance() or QApplication([])
    gaps = []
    previous = time.perf_counter()

    def tick():
        nonlocal previous
        now = time.perf_counter()
        gaps.append((now-previous)*1000)
        previous = now

    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(tick)
    timer.start()

    def pump_until(ready, timeout=150):
        deadline = time.monotonic()+timeout
        while not ready():
            if time.monotonic() >= deadline:
                raise RuntimeError("Nativní okno nebo worker nedokončil měřenou operaci")
            app.processEvents()
            time.sleep(.001)
        app.processEvents()

    def settle():
        count = len(gaps)
        pump_until(lambda: len(gaps) >= count+2, timeout=5)

    phase_gaps = {}

    def observed(name, operation):
        def run():
            nonlocal previous
            previous = time.perf_counter()
            offset = len(gaps)
            result = operation()
            values = gaps[offset:]
            phase_gaps.setdefault(name, []).append({"count": len(values),
                                                    "max_ms": max(values) if values else None})
            return result
        return run

    runner = None
    start = time.perf_counter()
    if case == "gui-history":
        path = write(folder / "history.json", history_data(60))
        runner = BackgroundRebuilder()
        memory.workers = lambda: worker_pids(runner)
        window = MainWindow(runner=runner, user_dir=folder / "profile",
                            examples_dir=folder)
    else:
        path = make_assembly(folder, 800)
        window = AssemblyWindow(user_dir=folder / "profile")
    window.resize(1200, 800)
    window.show()
    pump_until(lambda: window.viewer.ready)
    first_window_s = time.perf_counter()-start
    metrics, details = [], {"first_window_ready_s": first_window_s,
                           "first_window_from_case_entry_s": time.perf_counter()-case_started}
    try:
        if case == "gui-history":
            def open_history():
                if not window.open_model(path):
                    raise RuntimeError("Díl se neotevřel")
                pump_until(lambda: not window.session.computing)
                if window.session.failure:
                    raise RuntimeError(window.session.failure)
                settle()
                return window.session.result

            metrics.append(measure("open-worker-receive-render",
                                   observed("open-worker-receive-render", open_history),
                                   lambda r: inspect_history(r, 60), repeats))
            original = window.session.result
            window.session.set_parameter("t", "11")
            window._refresh_progress()
            if not window.session.computing:
                raise RuntimeError("Nativní zkouška nemá co rušit")
            cancelled_process = runner._active.process
            cancelled = []

            def cancel():
                started = time.perf_counter()
                window.stop_action.trigger()
                cancelled.append(time.perf_counter()-started)

            QTimer.singleShot(50, cancel)
            pump_until(lambda: bool(cancelled))
            if window.session.computing or window.session.document.parameters["t"] != 10:
                raise RuntimeError("Zastavit nevrátilo poslední spočítaný stav")
            if cancelled_process.is_alive():
                raise RuntimeError("Zrušený proces zůstal živý")
            if window.session.result is not original:
                raise RuntimeError("Zastavit nahradilo původní geometrii")
            window.session.set_parameter("t", "12")
            pump_until(lambda: not window.session.computing)
            inspect_history(window.session.result, 60, thickness=12)
            window._rebuild_param_fields()  # změna přes session, mimo měřenou operaci
            details.update(cancel_action_s=cancelled[0], cancel_and_recovery_ok=True)
        else:
            def open_assembly():
                if not window.open_assembly(path):
                    raise RuntimeError("Sestava se neotevřela")
                settle()
                return window.session.result

            metrics.append(measure("open-build-tree-render",
                                   observed("open-build-tree-render", open_assembly),
                                   lambda r: inspect_assembly(r, 800), repeats))

            def select():
                window.select(("c799",))
                settle()
                return window._selection

            def check_selection(value):
                if value != (("c799",),):
                    raise RuntimeError("Velký strom nevybral skutečnou komponentu")
                window.select(("c0",))  # příprava dalšího opakování mimo měřený čas
                return {"selected_id": "c799"}

            metrics.append(measure("select-last-component",
                                   observed("select-last-component", select),
                                   check_selection, repeats))
            failures = []

            def close_preview():
                dialog = QApplication.activeModalWidget()
                if not isinstance(dialog, AssemblyParameterPreviewDialog):
                    failures.append("Náhled se neotevřel")
                    if dialog is not None:
                        dialog.reject()
                    return
                if not dialog.viewer.ready or not dialog._displayed:
                    QTimer.singleShot(20, close_preview)
                    return
                dialog.reject()

            def parameters():
                dialog = QApplication.activeModalWidget()
                if not isinstance(dialog, AssemblyParametersDialog):
                    failures.append("Editor se neotevřel")
                    if dialog is not None:
                        dialog.reject()
                    return
                dialog.table.item(0, 1).setText("21")
                QTimer.singleShot(20, close_preview)
                dialog.preview_button.click()
                if not dialog.isVisible():
                    failures.append("Náhled omylem potvrdil model")
                dialog.reject()

            source, result = window.session.assembly, window.session.result

            def preview():
                QTimer.singleShot(20, parameters)
                window.parameters_button.click()
                settle()
                if failures:
                    raise RuntimeError(str(failures))
                if (window.session.assembly is not source or window.session.result is not result
                        or window.session.can_undo):
                    raise RuntimeError("Prohlížení náhledu změnilo model nebo historii")
                return True

            metrics.append(measure("open-parameter-preview-back",
                                   observed("open-parameter-preview-back", preview),
                                   lambda value: {"model_unchanged": value}, repeats))
        # Mimo časování operací: macOS ještě animuje zavřený modální dialog.
        # Počkáme na kompozitor, aby snímek neobsahoval jeho průsvitný zbytek.
        capture_after = time.monotonic()+.5
        pump_until(lambda: time.monotonic() >= capture_after)
        _screenshot(window, folder / "native-window.png")
        settle()
        ordered = sorted(gaps)
        details["qt_timer_gaps_ms"] = {
            "requested_interval_ms": 5, "count": len(ordered),
            "median": statistics.median(ordered),
            "p95": ordered[min(len(ordered)-1, int(.95*len(ordered)))],
            "max": max(ordered),
            "note": "Zpoždění Qt časovače včetně synchronních operací; "
                    "není to FPS ani latence kliknutí."}
        details["native_view_ready"] = window.viewer.ready
        details["qt_gaps_by_operation"] = phase_gaps  # první položka je zahřívací běh
        return metrics, details
    finally:
        timer.stop()
        window.session.dirty = False
        window.close()
        if runner is not None:
            runner.close()
        app.processEvents()
