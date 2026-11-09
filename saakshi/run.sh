#!/usr/bin/env bash
# Saakshi — build the UI and serve everything on http://localhost:8100 (PORT=… to change)
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8100}"
if [ ! -f .env ] && [ ! -f ../.env ]; then
  echo "Missing .env — copy .env.example and add GNANI_API_KEY and GROQ_API_KEY." >&2
  exit 1
fi
echo "› installing backend deps"
(cd backend && uv sync --quiet)
echo "› building web UI"
(cd web && { [ -d node_modules ] || npm install --silent; } && npm run build --silent)
echo "› Saakshi is live on http://localhost:${PORT}"
exec uv run --project backend uvicorn saakshi.server:app --app-dir backend --host 0.0.0.0 --port "${PORT}" --timeout-graceful-shutdown 2
