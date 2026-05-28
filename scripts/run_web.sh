#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

PYTHON_CMD=${PYTHON:-python3.12}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-8000}
LINK_HOST=$HOST

case "$LINK_HOST" in
  0.0.0.0|::)
    LINK_HOST=localhost
    ;;
esac

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_CMD was not found. Install Python 3.12+ or set PYTHON=/path/to/python3." >&2
  exit 1
fi

"$PYTHON_CMD" - <<'PY'
import sys

if sys.version_info < (3, 12):
    raise SystemExit(
        f"ERROR: Python 3.12 or later is required, got {sys.version.split()[0]}"
    )
PY

if [ ! -x .venv/bin/python ]; then
  "$PYTHON_CMD" -m venv .venv
fi

.venv/bin/python -m pip install -U pip setuptools wheel
.venv/bin/python -m pip install -r requirements-web.txt

echo
echo "CC4M Web UI is starting:"
echo "  http://$LINK_HOST:$PORT/"
echo "  http://$LINK_HOST:$PORT/visualize/"
echo

.venv/bin/python main.py web-ui --host "$HOST" --port "$PORT" --visualize-only
