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
import threading
import time
from dataclasses import dataclass, field
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
        "ndt": list(result.ndt),  # stavy NDT studií – jen texty
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
        ndt=data["ndt"],
    )


# --- pomocný proces -----------------------------------------------------------------------


_STEP_PHASE = None  # nastaveno pouze v procesu přepočtu


def _worker_main(conn: Any, step_phase: Any) -> None:
    """Smyčka pomocného procesu: přijme model, přepočítá ho, pošle výsledek zpět."""
    global _STEP_PHASE  # proces sdělí rodiči, kdy pracuje se STEP
    _STEP_PHASE = step_phase
    from skodacad.document import Document, DocumentError  # jádro se načte hned – pak je
    from skodacad.rebuild import rebuild  # proces připravený

    while True:
        try:
            message = conn.recv()
        except (EOFError, OSError):
            return  # okno skončilo
        if message[0] not in ("rebuild", "coverage", "access", "plan", "pt", "mt", "rt",
                              "audit", "design"):
            return
        kind, job, data, *options = message
        try:
            if kind == "design":
                import datetime

                from skodacad.ndt.design import Design, run
                from skodacad.ndt.study import part_fingerprint

                settings, path, operator = options
                parsed = Design.from_dict(settings)
                doc = Document.from_dict(data)

                def design_progress(index: int, total: int, label: str, inner: Any,
                                    job: int = job) -> None:
                    conn.send(("design_progress", job, (index, total, label, inner)))

                def design_prepared(base: Any, job: int = job) -> None:
                    conn.send(("design_prepared", job, (base.original, base.steps_text)))

                def design_variant(variant: Any, job: int = job) -> None:
                    conn.send(("design_variant", job, variant))

                outcome = run(
                    data, parsed, model=doc.name, path=path, operator=operator,
                    fingerprint=part_fingerprint(doc),
                    created=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    progress=design_progress, on_variant=design_variant,
                    on_prepared=design_prepared)
                reply = ("design", job, outcome)
            elif kind == "access":
                from skodacad.session import ModelSession

                session = ModelSession()
                session.document = Document.from_dict(data)
                session.rebuild()
                study_id, settings, contact = options

                def send(*update: Any, job: int = job) -> None:
                    conn.send((update[0], job, update[1]))

                reply = ("access", job, session.compute_ndt_access(
                    study_id, settings, contact,
                    progress=lambda stage, done, total: send("progress", (stage, done, total)),
                    on_prepared=lambda prepared: send("prepared", prepared),
                    on_variant=lambda index, outcome: send("variant", (index, outcome))))
            elif kind == "plan":
                from skodacad.session import ModelSession

                session = ModelSession()
                session.document = Document.from_dict(data)
                session.rebuild()
                study_id, mode, passes, settings, coverage = options

                def progress(stage: str, done: int, total: int, job: int = job) -> None:
                    conn.send(("progress", job, (stage, done, total)))

                reply = ("plan", job, session._run_plan(study_id, passes, settings, progress)
                         if mode == "build" else session.check_ndt_plan(
                             study_id, settings, coverage=coverage, progress=progress))
            elif kind == "pt":
                from skodacad.session import ModelSession

                session = ModelSession()
                session.document = Document.from_dict(data)
                session.rebuild()

                def counted(done: int, total: int, job: int = job) -> None:
                    conn.send(("progress", job, (done, total)))

                reply = ("pt", job, session.compute_ndt_pt(options[0], progress=counted))
            elif kind == "mt":
                from skodacad.session import ModelSession

                session = ModelSession()
                session.document = Document.from_dict(data)
                session.rebuild()

                def counted_mt(done: int, total: int, job: int = job) -> None:
                    conn.send(("progress", job, (done, total)))

                reply = ("mt", job, session.compute_ndt_mt(options[0], progress=counted_mt))
            elif kind == "rt":
                from skodacad.session import ModelSession

                session = ModelSession()
                session.document = Document.from_dict(data)
                session.rebuild()

                def counted_rt(done: int, total: int, job: int = job) -> None:
                    conn.send(("progress", job, (done, total)))

                reply = ("rt", job, session.compute_ndt_rt(options[0], progress=counted_rt))
            elif kind == "audit":
                from skodacad.session import ModelSession

                session = ModelSession()
                session.document = Document.from_dict(data)
                session.rebuild()
                include, access, operator = options

                def step(index: int, total: int, label: str, inner: Any,
                         job: int = job) -> None:
                    conn.send(("progress", job, (index, total, label, inner)))

                def entry(done: Any, job: int = job, include: list = include) -> None:
                    if done.study_id in include:  # ostatní audit zapíše v okně
                        conn.send(("entry", job, done))

                audit = session.compute_ndt_audit(include, access, operator, progress=step,
                                                  on_entry=entry)
                reply = ("audit", job, len(audit.entries))  # studie už odešly po jedné
            elif kind == "coverage":
                from skodacad.session import ModelSession

                session = ModelSession()
                session.document = Document.from_dict(data)
                session.rebuild()
                session.ndt_placement_request = options[0]
                reply = ("coverage", job, session.compute_ndt_coverage(**options[1]))
            else:
                reply = ("result", job, encode_result(rebuild(Document.from_dict(data),
                                                              with_map=options[0])))
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
    step_phase: Any
    shutdown: threading.Event = field(default_factory=threading.Event)
    limit_error: str = ""

    def guard_step(self) -> None:
        """Dohled pouze během převodu STEP; bez závislosti na dotazování okna."""
        from skodacad.step_task import DEFAULT_TIMEOUT, MAX_RSS, _resident_bytes

        started = None
        while not self.shutdown.wait(0.1):
            if not self.process.is_alive():
                return
            if not self.step_phase.is_set():
                started = None
                continue
            if started is None:
                started = time.monotonic()
            if time.monotonic() - started > DEFAULT_TIMEOUT:
                error = "Převod STEP překročil časový limit."
            else:
                try:
                    memory = _resident_bytes(self.process.pid)
                except Exception:  # noqa: BLE001 -- selhání dohledu zastaví převod
                    memory = None
                if memory is None:
                    error = "Nelze ověřit využití paměti převodu STEP."
                elif memory > MAX_RSS:
                    error = "Převod STEP překročil limit paměti."
                else:
                    continue
            if self.shutdown.is_set() or not self.step_phase.is_set():
                started = None
                continue
            self.limit_error = error
            try:
                if self.process.is_alive():
                    self.process.terminate()
            except OSError:
                pass  # proces mohl právě skončit
            return

    def stop(self) -> None:
        self.shutdown.set()
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
    coverage: Any = None
    access: Any = None  # hotový návrh poloh (etapa 09)
    plan: Any = None  # sestavený nebo ověřený plán dráhy (etapa 10)
    pt: Any = None  # mapa geometrické přístupnosti PT (etapa 11)
    mt: Any = None  # mapa geometrické proveditelnosti a směrového pokrytí MT (etapa 12)
    rt: Any = None  # mapa geometrického promítnutí oblasti RT (etapa 13)
    audit: Any = None  # předběžný NDT audit doběhl (etapa 14; studie chodí v ``update``)
    design: Any = None  # konstrukční návrhy (etapa 15; varianty chodí v ``update``)
    update: tuple[str, Any] | None = None  # průběžná zpráva – výpočet běží dál


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
        phase = self._context.Event()
        process = self._context.Process(target=_worker_main, args=(child, phase), daemon=True,
                                        name="skodacad-prepocet")
        process.start()
        child.close()
        worker = _Worker(process, parent, phase)
        threading.Thread(target=worker.guard_step, daemon=True, name="step-worker-guard").start()
        return worker

    @property
    def busy(self) -> bool:
        return self._active is not None

    def submit(self, document: dict[str, Any], with_map: bool = False) -> int:
        """Spustí přepočet modelu (slovník z ``Document.to_dict``), s ``with_map`` i mapu
        tloušťky stěny. Rozpočítaný starší přepočet se ukončí – jeho výsledek by už neplatil."""
        return self._submit(("rebuild", document, with_map))

    def submit_coverage(self, document: dict[str, Any], placement: Any,
                        options: dict[str, Any]) -> int:
        return self._submit(("coverage", document, placement, options))

    def submit_access(self, document: dict[str, Any], study_id: str, options: dict[str, Any],
                      contact: list[dict[str, Any]] | None) -> int:
        """Návrh poloh sondy; průběh a hotové varianty chodí průběžně (``Finished.update``)."""
        return self._submit(("access", document, study_id, options, contact))

    def submit_plan(self, document: dict[str, Any], study_id: str, mode: str,
                    passes: list[dict[str, Any]] | None, options: dict[str, Any],
                    coverage: bool = True) -> int:
        """Plán dráhy: sestavení (``build``) nebo ověření uloženého (``check``); průběh chodí
        průběžně (``Finished.update``)."""
        return self._submit(("plan", document, study_id, mode, passes, options, coverage))

    def submit_pt(self, document: dict[str, Any], study_id: str) -> int:
        """Mapa PT studie; průběh (hotovo, celkem) chodí průběžně (``Finished.update``)."""
        return self._submit(("pt", document, study_id))

    def submit_mt(self, document: dict[str, Any], study_id: str) -> int:
        """Mapa MT studie; průběh (hotovo, celkem) chodí průběžně (``Finished.update``)."""
        return self._submit(("mt", document, study_id))

    def submit_rt(self, document: dict[str, Any], study_id: str) -> int:
        """Mapa RT studie; průběh (hotovo, celkem) chodí průběžně (``Finished.update``)."""
        return self._submit(("rt", document, study_id))

    def submit_audit(self, document: dict[str, Any], include: list[str], access: list[str],
                     operator: str = "") -> int:
        """Předběžný NDT audit studií ``include``; průběh a každá hotová studie (``entry``)
        chodí průběžně (``Finished.update``)."""
        return self._submit(("audit", document, include, access, operator))

    def submit_design(self, document: dict[str, Any], settings: dict[str, Any],
                      path: str = "", operator: str = "") -> int:
        """Konstrukční návrhy, s průběžným předáváním hotových variant."""
        return self._submit(("design", document, settings, path, operator))

    def _submit(self, message: tuple) -> int:
        self.cancel()
        worker = self._idle.pop(0) if self._idle else self._spawn()
        self._job += 1
        worker.conn.send((message[0], self._job, *message[1:]))
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
        if worker.limit_error:
            reason = worker.limit_error
            worker.stop()
            self._active = None
            if not self._idle:
                self._idle.append(self._spawn())
            return Finished(self._job, error=reason)
        try:
            if worker.conn.poll():
                kind, job, payload = worker.conn.recv()
                if worker.limit_error:
                    reason = worker.limit_error
                    worker.stop()
                    self._active = None
                    if not self._idle:
                        self._idle.append(self._spawn())
                    return Finished(job, error=reason)
                if kind in ("progress", "prepared", "variant", "entry", "design_progress",
                            "design_prepared", "design_variant"):
                    return Finished(job, update=(kind, payload))
                self._active = None
                self._idle.append(worker)
                for extra in self._idle[MAX_IDLE:]:  # víc připravených procesů netřeba
                    extra.stop()
                del self._idle[MAX_IDLE:]
                if kind == "result":
                    return Finished(job, result=decode_result(payload))
                if kind == "coverage":
                    return Finished(job, coverage=payload)
                if kind == "access":
                    return Finished(job, access=payload)
                if kind == "plan":
                    return Finished(job, plan=payload)
                if kind == "pt":
                    return Finished(job, pt=payload)
                if kind == "mt":
                    return Finished(job, mt=payload)
                if kind == "rt":
                    return Finished(job, rt=payload)
                if kind == "audit":
                    return Finished(job, audit=payload)
                if kind == "design":
                    return Finished(job, design=payload)
                return Finished(job, error=payload)
        except (EOFError, OSError):
            pass
        if worker.process.is_alive():
            return None
        reason = worker.limit_error
        worker.stop()  # proces spadl (např. chyba v knihovně jádra)
        self._active = None
        if not self._idle:
            self._idle.append(self._spawn())
        if reason:
            return Finished(self._job, error=reason)
        return Finished(self._job, error=f"Pomocný proces přepočtu spadl (kód "
                                         f"{worker.process.exitcode}). Zkus poslední "
                                         "změnu vrátit tlačítkem Zpět.")

    def wait(self, timeout: float = 120.0) -> Finished | None:
        """Počká na hotový přepočet (pro testy a příkazovou řádku)."""
        end = time.monotonic() + timeout
        while self._active is not None and time.monotonic() < end:
            finished = self.poll()
            if finished is not None and finished.update is None:  # průběh přeskočí
                return finished
            if finished is None:
                time.sleep(0.02)
        return None

    def close(self) -> None:
        """Ukončí všechny pomocné procesy (při zavření okna)."""
        for worker in [*self._idle, *([self._active] if self._active else [])]:
            worker.stop()
        self._idle, self._active = [], None
