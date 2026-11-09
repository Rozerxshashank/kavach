# Kavach + Saakshi as ONE free Render web service (build context: the repo root).
#   Kavach at /, Saakshi at /saakshi/, one process (deploy/render/combined.py).
#   Render's disk is wiped on every restart, so persist.py restores both data folders from a private
#   Hugging Face Dataset on start and backs up what changed every 5 minutes and on shutdown.

FROM node:22-slim AS web
WORKDIR /src
COPY kavach-redteam/web/package.json kavach-redteam/web/package-lock.json kavach/
COPY saakshi/web/package.json saakshi/web/package-lock.json saakshi/
RUN cd kavach && npm ci --no-audit --no-fund && cd ../saakshi && npm ci --no-audit --no-fund
COPY kavach-redteam/web/ kavach/
COPY saakshi/web/ saakshi/
RUN cd kavach && npm run build && cd ../saakshi && npm run build -- --base=/saakshi/

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv PYTHONUNBUFFERED=1
WORKDIR /app/kavach-redteam/backend
# both apps have the same dependencies; Kavach's lock file pins them
COPY kavach-redteam/backend/pyproject.toml kavach-redteam/backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project \
 && uv pip install --python /app/.venv/bin/python --no-cache "huggingface_hub==0.26.5"
COPY kavach-redteam/backend/kavach ./kavach
COPY saakshi/backend/saakshi /app/saakshi/backend/saakshi
COPY --from=web /src/kavach/dist /app/kavach-redteam/web/dist
COPY --from=web /src/saakshi/dist /app/saakshi/web/dist
COPY deploy/render/combined.py deploy/render/persist.py deploy/render/start.sh /app/deploy/

RUN useradd -m -u 10001 app && mkdir -p /data/kavach /data/saakshi && chown -R app /data
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/kavach-redteam/backend:/app/saakshi/backend:/app/deploy \
    KAVACH_ENV=production SAAKSHI_ENV=production \
    KAVACH_DATA_DIR=/data/kavach SAAKSHI_DATA_DIR=/data/saakshi \
    KAVACH_WEB_DIST=/app/kavach-redteam/web/dist SAAKSHI_WEB_DIST=/app/saakshi/web/dist \
    PERSIST_DIRS="kavach:/data/kavach saakshi:/data/saakshi" \
    PORT=10000
USER app
EXPOSE 10000
CMD ["sh", "/app/deploy/start.sh"]
