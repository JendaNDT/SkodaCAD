"""Oddělená diagnostika skutečného ukončení pytest; timeout vždy znamená chybu."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def child(folder, arguments):
    import atexit
    import faulthandler
    import gc
    import multiprocessing.process
    import threading

    # Otevřený soubor ponecháme živý po celou dobu normálního ukončování Pythonu.
    global _trace_file
    _trace_file = (folder / "tracebacks.log").open("w", encoding="utf-8")
    faulthandler.enable(file=_trace_file, all_threads=True)
    faulthandler.dump_traceback_later(120, repeat=True, file=_trace_file)
    stages = folder / "stages.jsonl"

    def stage(name, **extra):
        row = {"stage": name, "monotonic": time.monotonic(), "pid": os.getpid(), **extra}
        with stages.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False)+"\n")
        print("EXIT_DIAG " + json.dumps(row, ensure_ascii=False), flush=True)

    def snapshot(name):
        stage(name, threads=[{"name": t.name, "ident": t.ident, "daemon": t.daemon}
                             for t in threading.enumerate()],
              children=[{"pid": p.pid, "name": p.name, "daemon": p.daemon}
                        for p in list(multiprocessing.process._children)])

    stage("BOOT", python=sys.version, executable=sys.executable, arguments=arguments)
    atexit.register(snapshot, "ATEXIT_EARLY_REGISTERED")
    import pytest

    armed = False

    def collection(phase, info):
        if armed:
            stage("GC_"+phase.upper(), **info)

    gc.callbacks.append(collection)

    class Diagnostics:
        @pytest.hookimpl(hookwrapper=True, tryfirst=True)
        def pytest_sessionfinish(self, session, exitstatus):
            nonlocal armed
            armed = True
            snapshot("SESSIONFINISH_ENTER")
            faulthandler.dump_traceback_later(15, repeat=True, file=_trace_file)
            yield
            snapshot("SESSIONFINISH_LEAVE")

        @pytest.hookimpl(hookwrapper=True, tryfirst=True)
        def pytest_unconfigure(self, config):
            snapshot("UNCONFIGURE_ENTER")
            yield
            snapshot("UNCONFIGURE_LEAVE")

    code = pytest.main(arguments, plugins=[Diagnostics()])
    snapshot("PYTEST_RETURN")
    stage("PYTEST_EXIT_CODE", code=int(code))
    atexit.register(snapshot, "ATEXIT_LATE_REGISTERED")
    return int(code)  # běžný sys.exit, žádné nucené úspěšné ukončení


def windows_dump(pid, path):
    """Snímek našeho vlastního procesu před ukončením při diagnostickém timeoutu."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        return {"error": ctypes.get_last_error(), "phase": "OpenProcess"}
    try:
        dump = ctypes.WinDLL("dbghelp", use_last_error=True).MiniDumpWriteDump
        dump.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.HANDLE,
                         wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        dump.restype = wintypes.BOOL
        with path.open("wb") as stream:
            ok = dump(handle, pid, msvcrt.get_osfhandle(stream.fileno()),
                      0x1000 | 0x20, None, None, None)
        return {"ok": bool(ok), "error": 0 if ok else ctypes.get_last_error()}
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=2040)
    parser.add_argument("--exit-grace", type=float, default=90)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.pytest_args
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if not arguments or args.timeout <= 0 or args.exit_grace <= 0:
        parser.error("Zadej argumenty pytest a kladné časové limity")
    folder = args.output.resolve()
    if args.child:
        return child(folder, arguments)
    if folder.exists():
        parser.error("Diagnostická evidence již existuje")
    folder.mkdir(parents=True)
    command = [sys.executable, str(Path(__file__).resolve()), "--child", "--output",
               str(folder), "--", *arguments]
    started, shutdown_started = time.monotonic(), None
    reason = None
    with (folder / "process.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONFAULTHANDLER": "1"},
            start_new_session=os.name != "nt")
        while process.poll() is None:
            now = time.monotonic()
            stagefile = folder / "stages.jsonl"
            if stagefile.exists() and shutdown_started is None:
                lines = stagefile.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:  # právě zapisovaný poslední řádek
                        continue
                    if row.get("stage") == "SESSIONFINISH_ENTER":
                        shutdown_started = now
                        break
            if shutdown_started is not None and now-shutdown_started > args.exit_grace:
                reason = "shutdown_timeout"
            elif now-started > args.timeout:
                reason = "overall_timeout"
            if reason:
                write_json(folder / "timeout.json", {"reason": reason, "pid": process.pid,
                    "elapsed_s": now-started, "shutdown_observed_s":
                    None if shutdown_started is None else now-shutdown_started})
                if os.name == "nt":
                    try:
                        write_json(folder / "dump-result.json",
                                   windows_dump(process.pid, folder / "hung-process.dmp"))
                    except Exception as exc:  # diagnostika nesmí znemožnit timeout
                        write_json(folder / "dump-result.json", {"error": repr(exc)})
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   check=False, stdout=log, stderr=subprocess.STDOUT)
                else:
                    import signal

                    os.killpg(process.pid, signal.SIGKILL)
                break
            time.sleep(.5)
        code = process.wait(timeout=15)
    write_json(folder / "supervisor.json", {"child_exit": code, "reason": reason,
               "elapsed_s": time.monotonic()-started, "normal_exit": reason is None})
    print((folder / "process.log").read_text(encoding="utf-8"), flush=True)
    if (folder / "tracebacks.log").exists():
        print((folder / "tracebacks.log").read_text(encoding="utf-8"), flush=True)
    return 124 if reason else code


if __name__ == "__main__":
    raise SystemExit(main())
