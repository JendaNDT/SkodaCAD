"""Qt 6.11.3 Cocoa ownership fix; remove when the pinned Qt includes QTBUG-149612.

Implements the native element teardown semantics of upstream Qt commit
8148c48deb8e4345bacb797cb75c011df6f797fa. Accessibility stays enabled.
"""
import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QApplication

_library = None


def install() -> bool:
    global _library
    if sys.platform != 'darwin' or QApplication.platformName() != 'cocoa':
        return False
    if qVersion() != '6.11.3':
        raise RuntimeError('Oprava přístupnosti macOS vyžaduje ověřené Qt 6.11.3.')
    if _library is not None:
        return True
    if getattr(sys, 'frozen', False):
        path = Path(__file__).with_name('_cocoa_accessibility.dylib')
    else:
        path = (Path(__file__).resolve().parents[3]
                / 'out/platform-support/_cocoa_accessibility.dylib')
    if not path.is_file():
        raise RuntimeError('Chybí součást pro macOS. Sestav aplikaci nebo spusť '
                           'python packaging/build_macos_accessibility.py.')
    library = ctypes.CDLL(str(path))
    library.skodacad_install_ax_fix.argtypes = []
    library.skodacad_install_ax_fix.restype = ctypes.c_int
    result = library.skodacad_install_ax_fix()
    if result not in (1, 2):
        raise RuntimeError(f'Opravu přístupnosti macOS nelze bezpečně použít ({result}).')
    _library = library  # callbacks are native, and the library remains loaded until process exit
    return True


def probe(table_id: int) -> bool:
    if _library is None:
        raise RuntimeError('Nativní oprava není načtená.')
    _library.skodacad_probe_ax_table.argtypes = [ctypes.c_uint32]
    _library.skodacad_probe_ax_table.restype = ctypes.c_int
    return _library.skodacad_probe_ax_table(table_id) == 1
