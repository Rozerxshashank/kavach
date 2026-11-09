#!/usr/bin/env bash
# Kavach — one command to build the UI and serve everything on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ] && [ ! -f ../.env ]; then
  echo "Missing .env — copy .env.example and add GNANI_API_KEY and GROQ_API_KEY." >&2
  exit 1
fi

echo "› installing backend deps"
(cd backend && uv sync --quiet)

echo "› building web UI"
(cd web && { [ -d node_modules ] || npm install --silent; } && npm run build --silent)

echo "› Kavach is live on http://localhost:8000"
exec uv run --project backend uvicorn kavach.server:app --app-dir backend --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 2
