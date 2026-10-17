# syntax=docker/dockerfile:1
# Image of the SaaS (erplora.com). The web service runs the default CMD; saas-migrate
# (`python manage.py migrate --noinput`) and saas-cron (one command per schedule) run the same
# image with another command. Contract: aws README, «Contrato app ↔ infra» → «Imagen».
#   docker buildx build --platform linux/arm64 --provenance=false -t erplora/saas:<tag> .
#   bash docker/image.test.sh erplora/saas:<tag>
# packages/live and packages/ui are git submodules: the build context needs them checked out.
# Nothing secret goes in: the build runs with DEBUG=1 and no database.

ARG PYTHON_IMAGE=python:3.14-slim
ARG NODE_IMAGE=node:24-slim

FROM ghcr.io/astral-sh/uv:0.11 AS uv

# 1. The SPA bundle (frontend/dist). Plain JS and CSS, so it is built on the builder's own
#    platform, without emulation.
FROM --platform=$BUILDPLATFORM ${NODE_IMAGE} AS web
ARG PNPM_VERSION=10.34.7
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable pnpm && corepack prepare "pnpm@${PNPM_VERSION}" --activate
WORKDIR /src
# Dependencies first, so code changes reuse this layer. @erplora/ui is the packages/ui submodule,
# a member of this repo's pnpm workspace.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY patches/ patches/
COPY packages/ui/package.json packages/ui/package.json
RUN pnpm install --frozen-lockfile
# The code, packages/ui included (the tsconfig.*.json extend ./packages/ui).
COPY . .
# Type checking and tests are the CI's test job (`pnpm typecheck`, `pnpm test`): the image only
# bundles (`pnpm build` = `vue-tsc --build && vite build`).
RUN pnpm exec vite build

# 2. Python environment, compiled catalogues and STATIC_ROOT.
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"
WORKDIR /app/project
# Dependencies first, so code changes reuse this layer. erplora-live is the packages/live submodule
# (`[tool.uv.sources]` of pyproject.toml), installed as a wheel (--no-editable), with its
# catalogues compiled first so the wheel carries the .mo files.
COPY pyproject.toml uv.lock ./
COPY packages/live packages/live
RUN find packages/live -name '*.po' -exec sh -c 'msgfmt --check -o "${1%.po}.mo" "$1"' _ {} \; \
    && uv sync --frozen --no-dev --no-editable
COPY . .
COPY --from=web /src/frontend/dist frontend/dist
# packages/ is already installed in the virtualenv. The .mo files of the context are dropped:
# compilemessages skips a .mo that looks newer than its .po, stale or not. DEBUG=1 lets the
# settings load without production secrets (none is needed to compile or collect).
RUN rm -rf packages \
    && find . -name '*.mo' -delete \
    && DEBUG=1 python manage.py compilemessages \
    && DEBUG=1 python manage.py collectstatic --noinput

# 3. Runtime: read-only code owned by root, run as uid 10001; only /tmp needs to be writable.
FROM ${PYTHON_IMAGE}
# TLS verify-full against Aurora (DB_SSLROOTCERT).
ADD --chmod=644 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /etc/ssl/certs/rds-global-bundle.pem
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --no-create-home app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/project /app/project
WORKDIR /app/project
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings
USER 10001:10001
EXPOSE 8000
# The ALB idle timeout is 120 s; Twisted keeps idle connections far longer, so the ALB always
# closes first (no 502s). --proxy-headers trusts the ALB's X-Forwarded-* headers.
CMD ["daphne", "--bind", "0.0.0.0", "--port", "8000", "--proxy-headers", "config.asgi:application"]
