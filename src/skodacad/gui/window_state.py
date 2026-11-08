"""Small, bounded, atomic UI preferences. These never belong to a CAD document."""

import json
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QRect

PANELS = ("editor", "measure", "map", "section", "ndt", "audit", "design", "assistant")
# Činnosti hlavní lišty (P7.50); „file“ z verze 1 už není (Soubor je jen nabídka).
ACTIVITIES = ("model", "sketch", "drawing", "assembly", "ndt", "view")
MAX_BYTES = 16_384
VERSION = 2
SIDEBAR_TABS = ("features", "parameters", "part")
LEFT_SECTIONS = ("info", "parameters", "properties")
# Sbalitelné sekce pravé karty, které rozbaluje jen uživatel (P7.58). Sekce, které okno
# samo otvírá podle stavu (např. „Studie a jejich správa“), se neukládají.
INSPECTOR_SECTIONS = ("measure.saved", "measure.drawing", "ndt.beam", "ndt.ut_details",
                      "ndt.access", "ndt.plan", "ndt.pt_details", "ndt.mt_details",
                      "ndt.mt_yoke", "ndt.rt_details", "ndt.rt_preview")
# Verze 1 → 2: stejné hodnoty pod novým jménem; šířky karet (model_width, editor_width)
# jsou od P7.49 pevné podle návrhu a zahazují se.
V1_NAMES = {"page": "activity", "ribbon_collapsed": "palette_collapsed",
            "model_visible": "left_visible", "sidebar_tab": "left_tab",
            "sections": "left_sections"}


def _flags(value, keys):
    if not isinstance(value, dict):
        return None
    return {k: value[k] for k in keys if type(value.get(k)) is bool}


def clean_state(value):
    """Ověřené nastavení okna ve tvaru verze 2; verze 1 se převede, neznámé a chybné
    hodnoty se zahodí (nastavení okna nikdy nebrání otevření)."""
    result = {}
    if not isinstance(value, dict) or type(value.get("version")) is not int:
        return result
    if value["version"] == 1:
        value = {V1_NAMES.get(k, k): v for k, v in value.items() if k not in V1_NAMES.values()}
    elif value["version"] != VERSION:
        return result
    for key in ("left_visible", "palette_collapsed", "maximized"):
        if type(value.get(key)) is bool:
            result[key] = value[key]
    if "panel" in value and value["panel"] in (*PANELS, None):
        result["panel"] = value.get("panel")
    if value.get("activity") in ACTIVITIES:
        result["activity"] = value["activity"]
    if value.get("appearance") in ("system", "light", "dark"):
        result["appearance"] = value["appearance"]
    if value.get("left_tab") in SIDEBAR_TABS:  # záložka levé karty (P7.51)
        result["left_tab"] = value["left_tab"]
    for key, names in (("left_sections", LEFT_SECTIONS), ("inspector", INSPECTOR_SECTIONS)):
        flags = _flags(value.get(key), names)
        if flags is not None:
            result[key] = flags
    rect = value.get("geometry")
    if (isinstance(rect, list) and len(rect) == 4 and all(type(n) is int for n in rect)
            and all(abs(n) <= 32_768 for n in rect[:2])
            and 400 <= rect[2] <= 16_384 and 300 <= rect[3] <= 16_384):
        result["geometry"] = rect
    return result


def load_state(path: Path | None):
    if path is None:
        return {}
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return {}
        return clean_state(json.loads(raw))
    except (OSError, ValueError, UnicodeError, RecursionError):
        return {}


def save_state(path: Path | None, state):
    if path is None:
        return
    temporary = None
    try:
        data = json.dumps({"version": VERSION, **clean_state({"version": VERSION, **state})},
                          ensure_ascii=False).encode("utf-8")
        if len(data) > MAX_BYTES:
            raise ValueError("Nastavení okna je příliš velké.")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".okno-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fit_geometry(rect, screens):
    """Keep the entire frame inside a currently available screen, including negative origins."""
    candidates = [QRect(screen) for screen in screens if screen.width() > 0 and screen.height() > 0]
    if not candidates:
        return QRect(rect)
    screen = max(candidates, key=lambda s: max(0, s.intersected(rect).width())
                 * max(0, s.intersected(rect).height()))
    width, height = min(rect.width(), screen.width()), min(rect.height(), screen.height())
    x = min(max(rect.x(), screen.left()), screen.right() - width + 1)
    y = min(max(rect.y(), screen.top()), screen.bottom() - height + 1)
    return QRect(x, y, width, height)
