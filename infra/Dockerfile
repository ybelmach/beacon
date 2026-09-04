# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.11.16

# ─── uv binary (copied from official image, no pip needed) ───────────────────
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv-bin

# ─── base: shared Python settings ────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# ─── deps: virtualenv without source code (cached layer for dep changes) ─────
FROM base AS deps

COPY --from=uv-bin /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_FROZEN=1 \
    UV_PYTHON_DOWNLOADS=never

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ─── development: all deps (incl. dev), used in local compose via volume mount
FROM deps AS development

# Include dev deps (pytest, ruff, mypy) so checks can run inside the container
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY beacon/ ./beacon/
COPY scripts/ ./scripts/

EXPOSE 8000
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# ─── builder: prod deps + source, produces the artifact for runtime ───────────
FROM deps AS builder

# README.md is referenced by pyproject's `readme`, so the wheel build needs it.
COPY README.md ./
COPY beacon/ ./beacon/
COPY scripts/ ./scripts/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ─── production: minimal runtime image ───────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS production

ARG APP_VERSION=dev
ARG GIT_SHA=unknown

LABEL org.opencontainers.image.title="beacon" \
      org.opencontainers.image.description="Beacon telemetry backend" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r --gid 10001 appuser \
    && useradd -r --uid 10001 --gid 10001 -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv
COPY --from=builder --chown=appuser:appuser /app/beacon ./beacon
COPY --from=builder --chown=appuser:appuser /app/scripts ./scripts

USER 10001:10001

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${BACKEND_INTERNAL_PORT:-8000}/healthz" || exit 1

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
