"""Orientační zátěž limitu velikosti: malý kvádr doplněný mezerami do 16 MiB.

Spouštět jako skript. Nejde o velký geometricky složitý STEP ani pevnou mez paměti.
"""
import time
from pathlib import Path

from skodacad.step_probe import MAX_STEP_BYTES
from skodacad.step_task import StepTask, _resident_bytes

SOURCE = Path(__file__).parent / "fixtures" / "step" / "01-jedno-teleso.step"


def main():
    data = SOURCE.read_bytes()
    data += b" " * (MAX_STEP_BYTES - len(data))
    started = time.monotonic()
    task = StepTask(data)
    highest = 0
    try:
        while (result := task.poll()) is None:
            rss = _resident_bytes(task._process.pid)
            highest = max(highest, rss or 0)
            time.sleep(0.1)
        if result.error:
            raise RuntimeError(result.error)
        print(f"STEP {len(data)} B, time {time.monotonic() - started:.2f} s, "
              f"peak sampled resident memory {highest / 1024**2:.1f} MiB, "
              f"volume {result.facts.volume_mm3:.3f} mm^3.")
    finally:
        task.cancel()


if __name__ == "__main__":
    main()
