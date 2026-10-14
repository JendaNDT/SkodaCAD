#!/bin/bash
# Připraví Python prostředí ŠkodaCAD v cloudové session Claude Code:
# virtuální prostředí .venv s build123d (Open CASCADE), pytest a ruff.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

if command -v uv >/dev/null 2>&1; then
  [ -x .venv/bin/python ] || uv venv .venv --quiet
  uv pip install --python .venv/bin/python --quiet -e ".[dev]"
else
  [ -x .venv/bin/python ] || python3 -m venv .venv
  .venv/bin/python -m pip install --quiet -e ".[dev]"
fi

# Příkazy skodacad, pytest a ruff budou v session dostupné bez cesty.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
