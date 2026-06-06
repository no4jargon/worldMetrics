#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/backend/.venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
  echo "Missing backend virtualenv interpreter at $VENV_PYTHON" >&2
  echo "Create it first with: cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

export PYTHONPATH="$ROOT_DIR/backend"
exec "$VENV_PYTHON" -m app.main personal-tracker "$@"
