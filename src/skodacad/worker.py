"""Přepočet modelu na pozadí v pomocném procesu – okno přitom zůstane živé.

Proč proces, a ne vlákno: jádro Open CASCADE při výpočtu drží zámek Pythonu (GIL), takže
by okno stálo i s výpočtem ve vedlejším vlákně (změřeno: pauzy až 2 s). Pomocný proces
počítá úplně samostatně, jde kdykoli ukončit (tlačítko Zastavit, nová změna modelu)
a jeho pád neshodí okno.

Okno drží jeden proces, který počítá, a jeden záložní, který je už připravený (má
načtené jádro, což trvá pár sekund). Nová změna modelu rozpočítaný přepočet ukončí
a hned pokračuje v záložním procesu.

Výsledek (díl, díly před prvky, skici) se přenáší v binárním formátu jádra OCCT
(BinTools) – pickle tvary build123d neumí (drží historii booleovských operací).
"""

from __future__ import annotations

import io
import multiprocessing
import time
from dataclasses import dataclass
from typing import Any

from skodacad.rebuild import BuildResult

MAX_IDLE = 2  # kolik připravených procesů nejvýš držet (počítající + záložní)


# --- přenos výsledku mezi procesy --------------------------------------------------------


def _shape_bytes(shape: Any) -> tuple[str, bytes] | None:
    if shape is None:
        return None
    from OCP.BinTools import BinTools

    stream = io.BytesIO()
    BinTools.Write_s(shape.wrapped, stream)
    return type(shape).__name__, stream.getvalue()


def _shape_from(data: tuple[str, bytes] | None) -> Any:
    if data is None:
        return None
    from build123d import Compound, Part, Sketch, Solid
    from build123d.topology.shape_core import downcast
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape

    kind, raw = data
    shape = TopoDS_Shape()
    BinTools.Read_s(shape, io.BytesIO(raw))
    classes = {"Part": Part, "Compound": Compound, "Solid": Solid, "Sketch": Sketch}
    return classes.get(kind, Part)(downcast(shape))


def encode_result(result: BuildResult) -> dict[str, Any]:
    """Výsledek přepočtu → slovník s čísly, texty a bajty (přenese se rourou)."""
    return {
        "part": _shape_bytes(result.part),
        "parameters": dict(result.parameters),
        "statuses": list(result.statuses),
        "parts_before": {key: _shape_bytes(part) for key, part in result.parts_before.items()},
        "sketches": {key: (tuple(plane.origin), tuple(plane.x_dir), tuple(plane.z_dir),
                           _shape_bytes(sketch))
                     for key, (plane, sketch) in result.sketches.items()},
        "measurements": list(result.measurements),  # jen čísla a texty
        "thickness_map": result.thickness_map,  # seznamy čísel
        "map_error": result.map_error,
    }


def decode_result(data: dict[str, Any]) -> BuildResult:
    from build123d import Plane

    return BuildResult(
        part=_shape_from(data["part"]),
        parameters=data["parameters"],
        statuses=data["statuses"],
        parts_before={key: _shape_from(raw) for key, raw in data["parts_before"].items()},
        sketches={key: (Plane(origin, x_dir, z_dir), _shape_from(raw))
                  for key, (origin, x_dir, z_dir, raw) in data["sketches"].items()},
        measurements=data["measurements"],
        thickness_map=data["thickness_map"],
        map_error=data["map_error"],
    )


# --- pomocný proces -----------------------------------------------------------------------


def _worker_main(conn: Any) -> None:
    """Smyčka pomocného procesu: přijme model, přepočítá ho, pošle výsledek zpět."""
    from skodacad.document import Document, DocumentError  # jádro se načte hned – pak je
    from skodacad.rebuild import rebuild  # proces připravený

    while True:
        try:
            message = conn.recv()
        except (EOFError, OSError):
            return  # okno skončilo
        if message[0] != "rebuild":
            return
        _, job, data, with_map = message
        try:
            reply = ("result", job, encode_result(rebuild(Document.from_dict(data),
                                                          with_map=with_map)))
        except DocumentError as exc:
            reply = ("error", job, str(exc))
        except Exception as exc:  # noqa: BLE001 – chybu pošleme oknu, proces běží dál
            reply = ("error", job, f"Neočekávaná chyba přepočtu ({type(exc).__name__}: {exc}).")
        try:
            conn.send(reply)
        except (EOFError, OSError):
            return


@dataclass
class _Worker:
    process: Any
    conn: Any

    def stop(self) -> None:
        try:
            self.conn.close()
        except OSError:
            pass
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=5)


@dataclass
class Finished:
    """Hotový přepočet: ``result`` (BuildResult), nebo česká chyba v ``error``."""

    job: int
    result: BuildResult | None = None
    error: str = ""


class BackgroundRebuilder:
    """Přepočty v pomocných procesech. Bez Qt – okno se jen ptá metodou ``poll``."""

    def __init__(self) -> None:
        self._context = multiprocessing.get_context("spawn")  # Windows umí jen spawn
        self._idle: list[_Worker] = []
        self._active: _Worker | None = None
        self._job = 0
        self.started = 0.0  # kdy začal běžící přepočet (time.monotonic)
        self._idle.append(self._spawn())  # jádro se načítá, zatímco se otevírá okno

    def _spawn(self) -> _Worker:
        parent, child = self._context.Pipe()
        process = self._context.Process(target=_worker_main, args=(child,), daemon=True,
                                        name="skodacad-prepocet")
        process.start()
        child.close()
        return _Worker(process, parent)

    @property
    def busy(self) -> bool:
        return self._active is not None

    def submit(self, document: dict[str, Any], with_map: bool = False) -> int:
        """Spustí přepočet modelu (slovník z ``Document.to_dict``), s ``with_map`` i mapu
        tloušťky stěny. Rozpočítaný starší přepočet se ukončí – jeho výsledek by už neplatil."""
        self.cancel()
        worker = self._idle.pop(0) if self._idle else self._spawn()
        self._job += 1
        worker.conn.send(("rebuild", self._job, document, with_map))
        self._active = worker
        self.started = time.monotonic()
        if not self._idle:
            self._idle.append(self._spawn())  # záloha pro další změnu
        return self._job

    def cancel(self) -> None:
        """Ukončí běžící přepočet (proces se zahodí, záložní je připravený)."""
        if self._active is not None:
            self._active.stop()
            self._active = None
            if not self._idle:
                self._idle.append(self._spawn())

    def poll(self) -> Finished | None:
        """Hotový přepočet, nebo None (ještě běží / nic neběží). Nikdy nečeká."""
        worker = self._active
        if worker is None:
            return None
        try:
            if worker.conn.poll():
                kind, job, payload = worker.conn.recv()
                self._active = None
                self._idle.append(worker)
                for extra in self._idle[MAX_IDLE:]:  # víc připravených procesů netřeba
                    extra.stop()
                del self._idle[MAX_IDLE:]
                if kind == "result":
                    return Finished(job, result=decode_result(payload))
                return Finished(job, error=payload)
        except (EOFError, OSError):
            pass
        if worker.process.is_alive():
            return None
        worker.stop()  # proces spadl (např. chyba v knihovně jádra)
        self._active = None
        if not self._idle:
            self._idle.append(self._spawn())
        return Finished(self._job, error=f"Pomocný proces přepočtu spadl (kód "
                                         f"{worker.process.exitcode}). Zkus poslední "
                                         "změnu vrátit tlačítkem Zpět.")

    def wait(self, timeout: float = 120.0) -> Finished | None:
        """Počká na hotový přepočet (pro testy a příkazovou řádku)."""
        end = time.monotonic() + timeout
        while self._active is not None and time.monotonic() < end:
            finished = self.poll()
            if finished is not None:
                return finished
            time.sleep(0.02)
        return None

    def close(self) -> None:
        """Ukončí všechny pomocné procesy (při zavření okna)."""
        for worker in [*self._idle, *([self._active] if self._active else [])]:
            worker.stop()
        self._idle, self._active = [], None
