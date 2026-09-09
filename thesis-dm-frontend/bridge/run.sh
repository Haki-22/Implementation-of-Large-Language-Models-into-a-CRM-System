#!/usr/bin/env bash
# Launch the thesis demo bridge on http://127.0.0.1:8765/dm/.
#
# Browser -> FastAPI (this folder) -> the use-case functions -> substrate.db.
# UC-03 chat turns spawn the MCP server through the selected Claude, Codex or agy CLI; each session writes
# its own MCP config and audit log under the UC-03 runtime folder.
# Stop with Ctrl-C. Override the port with THESIS_DM_BRIDGE_PORT=9000 ./run.sh.

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${THESIS_DM_BRIDGE_PORT:-8765}"

if [ -n "${UC03_PYTHON:-}" ]; then
  PY="$UC03_PYTHON"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PY="$VIRTUAL_ENV/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi

if ! command -v claude >/dev/null 2>&1 && ! command -v codex >/dev/null 2>&1 && ! command -v agy >/dev/null 2>&1; then
  echo "WARNING: no claude, codex or agy CLI on PATH; UC-03 needs one of these MCP hosts." >&2
fi

# The manifest pin is verified when a UC-03 server starts (fail closed on a changed tool).
export UC03_MANIFEST_STRICT="${UC03_MANIFEST_STRICT:-1}"

echo "Starting thesis DM bridge on http://127.0.0.1:${PORT}"
echo "  page:        http://127.0.0.1:${PORT}/dm/"
echo "  python:      $PY"
echo

# Try to auto-open the browser; ignore failure (headless / SSH).
( sleep 1 && xdg-open "http://127.0.0.1:${PORT}/dm/" >/dev/null 2>&1 ) &

exec "$PY" -m uvicorn app:app \
  --app-dir "$DIR" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --log-level info
