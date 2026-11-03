"""Životnost oken patří testu; close() samotné QWidget nezruší."""
from __future__ import annotations

import sys


def application():
    widgets = sys.modules.get("PySide6.QtWidgets")
    return widgets.QApplication.instance() if widgets is not None else None


def top_levels():
    app = application()
    return tuple(app.topLevelWidgets()) if app is not None else ()


def dispose_new_widgets(previous):
    """Zavře a doručí DeferredDelete novým oknům, dokud běží Qt i Python."""
    app = application()
    if app is None:
        return
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid

    owned = [w for w in app.topLevelWidgets() if not any(w is old for old in previous)]
    # Potvrzení neuložených dat už test ověřil; po jeho skončení nesmí čekat dialog.
    for widget in owned:
        session = getattr(widget, "session", None)
        if session is not None and hasattr(session, "dirty"):
            session.dirty = False
    for widget in owned:
        if isValid(widget):
            widget.close()  # běžný closeEvent ukončí vlastní timery/workery
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    if any(isValid(widget) for widget in owned):
        raise AssertionError("Testovací okno zůstalo živé po DeferredDelete")
