#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

PYTHON_CMD=${PYTHON:-python3.12}

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_CMD was not found. Install Python 3.12.x or set PYTHON=/path/to/python3.12." >&2
  exit 1
fi

"$PYTHON_CMD" - <<'PY'
import sys

if sys.version_info[:2] != (3, 12):
    raise SystemExit(
        f"ERROR: Python 3.12.x is required, got {sys.version.split()[0]}"
    )
PY

if [ ! -x .venv/bin/python ]; then
  "$PYTHON_CMD" -m venv .venv
fi

.venv/bin/python -m pip install -U pip setuptools wheel
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
