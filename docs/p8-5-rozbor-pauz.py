"""Diagnostika P8.5: kde vznikají dlouhé pauzy obsluhy Qt (jen rozbor, ne měření rozpočtu).

xvfb-run -a python docs/p8-5-rozbor-pauz.py <repo> <vystup.json> <zahrivaci> <cykly>
Stejná zátěž P8.4/P8.5 (soak_p8_gui), navíc hlídací vlákno, které při pauze delší než
0,3 s každých 100 ms zapíše zásobník hlavního vlákna. Každá pauza nese krok cyklu.
"""
import json
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

state = {"phase": "initial", "cycle": None, "last_tick": None}
gaps = []
main_id = threading.get_ident()
samples = []
lock = threading.Lock()


def phase_print(*args, **kwargs):
    text = " ".join(str(a) for a in args)
    if text.startswith("P84_PHASE "):
        _, cycle, phase = text.split(" ", 2)
        # pauzy po tomto bodě patří následujícímu kroku
        state["phase"], state["cycle"] = f"po {phase}", cycle
    print(*args, **kwargs)




def frames():
    frame = sys._current_frames().get(main_id)
    stack = traceback.extract_stack(frame)
    keep = [f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in stack
            if "skodacad" in f.filename or "soak_p8" in f.filename]
    return keep[-6:] or [f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in stack[-4:]]


def watchdog():
    while not state.get("done"):
        time.sleep(.1)
        last = state["last_tick"]
        if last is not None and time.perf_counter()-last > .3:
            with lock:
                samples.append(tuple(frames()))


def main(repo):
    sys.path.insert(0, str(repo / "tests"))
    sys.path.insert(0, str(repo / "src"))
    import soak_p8
    import soak_p8_gui
    soak_p8_gui.print = phase_print
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication([])  # noqa: F841 -- Qt aplikace musí žít po celý běh
    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)

    def tick():
        now = time.perf_counter()
        last = state["last_tick"]
        state["last_tick"] = now
        if last is None:
            return
        gap = now-last
        with lock:
            stack = list(samples)
            samples.clear()
        if gap > .3:
            counts = {}
            for s in stack:
                counts[s] = counts.get(s, 0)+1
            top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
            gaps.append({"gap_s": round(gap, 3), "phase": state["phase"], "cycle": state["cycle"],
                         "stacks": [{"n": n, "frames": list(s)} for s, n in top]})

    timer.timeout.connect(tick)
    QTimer.singleShot(0, lambda: (state.__setitem__("last_tick", time.perf_counter()),
                                  timer.start(50)))
    threading.Thread(target=watchdog, daemon=True).start()
    folder = Path(tempfile.mkdtemp(prefix="gapdiag-"))
    t0 = time.perf_counter()
    try:
        soak_p8.child(folder, cycles, warmups, 3072*1024**2)
    finally:
        state["done"] = True
        timer.stop()
        out.write_text(json.dumps({"wall_s": time.perf_counter()-t0, "gaps": gaps},
                                  ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    out, warmups, cycles = Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    main(Path(sys.argv[1]))
