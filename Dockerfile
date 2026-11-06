# syntax=docker/dockerfile:1.7
# Образ API и воркера Normocontrol AI: `docker build -t normocontrol/api .`
# --build-arg WITH_LIBREOFFICE=false — образ меньше (~400 МБ), но без точных номеров страниц.

ARG PYTHON_IMAGE=python:3.12.14-slim-trixie

FROM ghcr.io/astral-sh/uv:0.12.23 AS uv

# ---------------------------------------------------------------- зависимости и пакет
FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra pdf
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --extra pdf

# ---------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime
ARG WITH_LIBREOFFICE=true
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini fonts-liberation fonts-dejavu-core \
    && if [ "$WITH_LIBREOFFICE" = "true" ]; then \
         apt-get install -y --no-install-recommends libreoffice-writer-nogui; \
       fi \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app profiles ./profiles
COPY --chown=app:app config.yaml ./config.yaml
RUN mkdir -p /app/data && chown app:app /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/app \
    NC_ENV=prod \
    NC_LOG__JSON_FORMAT=true \
    NC_API__HOST=0.0.0.0 \
    NC_API__PORT=8000

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]
ENTRYPOINT ["tini", "--", "normocontrol"]
CMD ["serve"]
