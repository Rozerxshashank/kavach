#!/bin/sh
# Public addresses come from Render (RENDER_EXTERNAL_URL) unless set; the two apps talk over loopback.
set -e
BASE="${PUBLIC_URL:-$RENDER_EXTERNAL_URL}"
BASE="${BASE%/}"
export KAVACH_PUBLIC_URL="${KAVACH_PUBLIC_URL:-$BASE}"
export SAAKSHI_PUBLIC_URL="${SAAKSHI_PUBLIC_URL:-$BASE/saakshi}"
export KAVACH_SAAKSHI_URL="http://127.0.0.1:${PORT}/saakshi"
export KAVACH_SHIELD_URL="http://127.0.0.1:${PORT}"
exec python /app/deploy/persist.py uvicorn combined:app --host 0.0.0.0 --port "$PORT" \
  --timeout-graceful-shutdown 8 --no-server-header
