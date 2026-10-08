# syntax=docker/dockerfile:1

# ---- build: resolve and install dependencies into a virtualenv ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Dependencies first, so this layer is reused until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- runtime: slim image with just the virtualenv, running as an unprivileged user ----
FROM python:3.12-slim-bookworm AS runtime
RUN useradd --system --create-home --uid 1000 app \
    && mkdir /data \
    && chown app:app /data
WORKDIR /app
COPY --from=build --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    LIVESTOCKS_HOST=0.0.0.0 \
    LIVESTOCKS_DB_PATH=/data/livestocks.db \
    NICEGUI_STORAGE_PATH=/data/.nicegui

USER app
VOLUME /data
EXPOSE 8080

# The slim image has no curl, so probe with Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=4)"

CMD ["livestocks"]
