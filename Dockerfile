# syntax=docker/dockerfile:1
# One image for every actor; SSO_LAB_ROLE picks idp, app-a or app-b at runtime.

FROM node:24-slim AS frontend
WORKDIR /app
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev
COPY --from=frontend /app/dist ./static

ENV PATH="/app/.venv/bin:$PATH" \
    SSO_LAB_STATIC_DIR=/app/static \
    PORT=8080
RUN useradd --uid 10001 --no-create-home app
USER 10001
CMD ["sh", "-c", "exec uvicorn sso_lab.main:create_app --factory --host 0.0.0.0 --port ${PORT} --no-server-header"]
