"""Small, bounded, atomic UI preferences. These never belong to a CAD document."""

import json
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QRect

PANELS = ("editor", "measure", "map", "section", "ndt", "audit", "design", "assistant")
PAGES = ("file", "model", "sketch", "drawing", "assembly", "ndt", "view")
MAX_BYTES = 16_384


def clean_state(value):
    result = {}
    if (not isinstance(value, dict) or type(value.get("version")) is not int
            or value["version"] != 1):
        return result
    for key in ("model_visible", "ribbon_collapsed", "maximized"):
        if type(value.get(key)) is bool:
            result[key] = value[key]
    for key in ("model_width", "editor_width"):
        number = value.get(key)
        if type(number) is int and 180 <= number <= 1200:
            result[key] = number
    if "panel" in value and value["panel"] in (*PANELS, None):
        result["panel"] = value.get("panel")
    if value.get("page") in PAGES:
        result["page"] = value["page"]
    if value.get("appearance") in ("system", "light", "dark"):
        result["appearance"] = value["appearance"]
    sections = value.get("sections")
    if isinstance(sections, dict):
        result["sections"] = {k: sections[k] for k in ("info", "parameters", "properties")
                              if type(sections.get(k)) is bool}
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
        data = json.dumps({"version": 1, **clean_state({"version": 1, **state})},
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
