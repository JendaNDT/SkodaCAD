"""Údaj o sestavení aplikace – kterým sestavením vznikl výstup (etapa 14, dohledatelnost).

Verze balíčku je pořád ``0.1.0``, proto se k ní přidává sestavení: GitHub Actions před
PyInstallerem zapíše commit a datum do ``skodacad/_build.py``; při vývoji ze zdrojů se vezme
``git describe``, jinak „vývojová verze“.
"""

from __future__ import annotations

import platform
import subprocess
from functools import lru_cache
from pathlib import Path

from skodacad import __version__

DEVELOPMENT = "vývojová verze"


def _git_describe() -> str:
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        return ""
    try:
        done = subprocess.run(["git", "-C", str(root), "describe", "--always", "--dirty"],
                              capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


@lru_cache(maxsize=1)
def build_info() -> dict[str, str]:
    """Verze, sestavení a knihovny jako slovník textů (zpráva auditu, O aplikaci)."""
    try:
        from skodacad import _build  # type: ignore[attr-defined]  # jen v sestavené aplikaci

        commit, date, kind = str(_build.COMMIT), str(_build.DATE), "sestavení"
    except ImportError:
        commit, date, kind = _git_describe(), "", DEVELOPMENT
    info = {"version": __version__, "kind": kind, "commit": commit, "date": date,
            "python": platform.python_version()}
    try:
        import build123d
        import OCP

        info["occt"] = str(getattr(OCP, "__version__", "?"))
        info["build123d"] = str(getattr(build123d, "__version__", "?"))
    except ImportError:  # pragma: no cover – jádro bez OCCT nejde
        pass
    return info


def build_text() -> str:
    """Jedna věta, např. „ŠkodaCAD 0.1.0, sestavení 1a2b3c4 (2026-10-20)“."""
    info = build_info()
    if info["kind"] == DEVELOPMENT:
        detail = f"{DEVELOPMENT} (git {info['commit']})" if info["commit"] else DEVELOPMENT
    else:
        detail = f"sestavení {info['commit'][:12]}" + (f" ({info['date']})" if info["date"]
                                                      else "")
    return f"ŠkodaCAD {info['version']}, {detail}"


def libraries_text() -> str:
    info = build_info()
    return (f"Python {info['python']}, Open CASCADE (OCP) {info.get('occt', '?')}, "
            f"build123d {info.get('build123d', '?')}")
