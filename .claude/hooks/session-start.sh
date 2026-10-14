#!/bin/bash
# Připraví prostředí ŠkodaCAD v cloudové session Claude Code:
# systémové knihovny pro Qt (okno a jeho snímky přes Xvfb) a virtuální
# prostředí .venv s build123d (Open CASCADE), PySide6, pytest a ruff.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

QT_LIBS="libegl1 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0
libxcb-xinerama0 libxcb-randr0 libxcb-render-util0 libxcb-image0 libgl1-mesa-dri xvfb"
# shellcheck disable=SC2086
if ! dpkg -s $QT_LIBS >/dev/null 2>&1; then
  SUDO=""
  if [ "$(id -u)" != "0" ]; then SUDO="sudo -n"; fi
  # Bez knihoven půjde jádro i testy jádra; testy okna se pak jen přeskočí.
  # shellcheck disable=SC2086
  { $SUDO apt-get update -qq && $SUDO apt-get install -y -qq $QT_LIBS; } >/dev/null 2>&1 \
    || echo "Upozornění: systémové knihovny pro Qt se nepodařilo nainstalovat." >&2
fi

if command -v uv >/dev/null 2>&1; then
  [ -x .venv/bin/python ] || uv venv .venv --quiet
  uv pip install --python .venv/bin/python --quiet -e ".[dev,gui]"
else
  [ -x .venv/bin/python ] || python3 -m venv .venv
  .venv/bin/python -m pip install --quiet -e ".[dev,gui]"
fi

# Příkazy skodacad, skodacad-gui, pytest a ruff budou v session dostupné bez cesty.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
