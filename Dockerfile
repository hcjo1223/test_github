# Two stages: build the UI, then run the API with the built UI beside it.
# The API serves the UI itself, so one container is the whole service.

FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
# main.py finds the UI at <repo>/frontend/dist, i.e. /srv/frontend/dist here.
COPY --from=ui /ui/dist /srv/frontend/dist

# Everything the app writes (settings, mandates, results, ledgers, caches)
# lives under /data: mount a persistent volume there.
ENV PATH="/srv/backend/.venv/bin:$PATH" \
    AIHF_WEB_HOME=/data \
    AIHF_REQUIRE_AUTH=1 \
    AIHF_COOKIE_SECURE=1
VOLUME ["/data"]

# The platform sets PORT; the owner's password comes from a platform secret
# (AIHF_PASSWORD), never from this file.
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
