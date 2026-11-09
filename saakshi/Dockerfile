# Saakshi: one container, one process. The web UI is built here and served by the API server.
# Data (SQLite + recordings + backups) lives in /data, so mount a persistent volume there.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/saakshi ./saakshi
COPY --from=web /web/dist /app/web/dist

ENV SAAKSHI_ENV=production \
    SAAKSHI_DATA_DIR=/data \
    SAAKSHI_WEB_DIST=/app/web/dist \
    PORT=8100
RUN useradd --uid 10001 --no-create-home saakshi && mkdir -p /data && chown saakshi /data
USER saakshi
VOLUME /data
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"
CMD ["sh", "-c", "exec .venv/bin/uvicorn saakshi.server:app --host 0.0.0.0 --port ${PORT} --timeout-graceful-shutdown 5 --no-server-header"]
