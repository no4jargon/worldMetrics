#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

rm -f "$ROOT_DIR/backend/data/worldmetrics.sqlite3"
rm -f "$ROOT_DIR/web/data/overview.json"
rm -f "$ROOT_DIR/web/data/series.json"
rm -f "$ROOT_DIR/web/data/release-monitor.json"
rm -f "$ROOT_DIR/web/data/refresh-metadata.json"
rm -f "$ROOT_DIR/web/data/refresh-status.json"

cat <<MSG
Local dev database and dashboard snapshots removed.

Next website open will auto-repopulate if the frontend is running with default auto-refresh enabled.
Manual repopulation command:
  cd "$ROOT_DIR/backend" && source .venv/bin/activate && python -m app.main refresh-dev --reset-db --months 60
MSG
