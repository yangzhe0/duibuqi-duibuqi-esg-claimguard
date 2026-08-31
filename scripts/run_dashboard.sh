#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)
WEB_DIR="$PROJECT_DIR/dashboard_web"
CONDA_BIN="${ESG_CONDA_BIN:-/opt/miniconda3/bin/conda}"
MINERU_PREFIX="$($CONDA_BIN run -n mineru python -c 'import sys; print(sys.prefix)')"
PAPERAGENT_PREFIX="$($CONDA_BIN run -n paperagent python -c 'import sys; print(sys.prefix)')"
export ESG_MINERU_BIN="${ESG_MINERU_BIN:-$MINERU_PREFIX/bin/mineru}"
DASHBOARD_PYTHON="${ESG_DASHBOARD_PYTHON_BIN:-$PAPERAGENT_PREFIX/bin/python}"

if [[ ! -x "$ESG_MINERU_BIN" ]]; then
  echo "MinerU executable not found: $ESG_MINERU_BIN" >&2
  exit 1
fi

if [[ ! -x "$DASHBOARD_PYTHON" ]]; then
  echo "Dashboard Python not found: $DASHBOARD_PYTHON" >&2
  exit 1
fi

if [[ "${ESG_PIPELINE_PROFILE:-claimguard}" == "legacy" ]] && ! curl -fsS "${ESG_OLLAMA_HEALTH_URL:-http://127.0.0.1:11434/api/tags}" >/dev/null 2>&1; then
  echo "Warning: Ollama is unavailable; dashboard browsing works, but uploaded tasks will fail during Qwen3 extraction." >&2
fi

NEEDS_BUILD=0
if [[ ! -f "$WEB_DIR/dist/index.html" ]]; then
  NEEDS_BUILD=1
elif [[ "$WEB_DIR/package.json" -nt "$WEB_DIR/dist/index.html" ]] || [[ "$WEB_DIR/package-lock.json" -nt "$WEB_DIR/dist/index.html" ]]; then
  NEEDS_BUILD=1
elif find "$WEB_DIR/src" -type f -newer "$WEB_DIR/dist/index.html" -print -quit | grep -q .; then
  NEEDS_BUILD=1
fi

if [[ "$NEEDS_BUILD" -eq 1 ]]; then
  echo "Building ESG dashboard frontend..."
  npm --prefix "$WEB_DIR" install
  npm --prefix "$WEB_DIR" run build
fi

cd "$PROJECT_DIR"
exec "$DASHBOARD_PYTHON" -m dashboard_api.server "$@"
