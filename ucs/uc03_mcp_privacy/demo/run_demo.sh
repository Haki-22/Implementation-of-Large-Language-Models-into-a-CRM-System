#!/usr/bin/env bash
# UC-03 demo smoke: drive the MCP server through the strict profile on a scratch
# copy of the CRM database and check every guarantee the README states.
#
#   ./ucs/uc03_mcp_privacy/demo/run_demo.sh                 # strict, scratch copy
#   ./ucs/uc03_mcp_privacy/demo/run_demo.sh --security open
#
# Exit code 0 = every check passed; the report explains any failure.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." &>/dev/null && pwd)"
if [[ -n "${UC03_PYTHON:-}" ]]; then PY="$UC03_PYTHON";
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then PY="$VIRTUAL_ENV/bin/python";
else PY="$(command -v python3 || command -v python)"; fi
cd "$PROJECT_ROOT"
exec "$PY" -m ucs.uc03_mcp_privacy.demo.smoke "$@"
