FROM python:3.11-slim AS deps

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra dataset

FROM python:3.11-slim

# libgomp1: required at runtime by numpy/hdbscan OpenMP routines.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

COPY --from=deps /app/.venv /app/.venv

COPY backend/ ./backend/
COPY configs/ ./configs/
COPY db/ ./db/
COPY demo/ ./demo/
COPY dataset/ ./dataset/
COPY core/ ./core/

ENV HF_HOME=/opt/models/hf

RUN CONFIG_PATH=configs/dev.yaml python -c "\
from core.text_encoder import preload_model; \
from core.image_encoder import preload_clip_model; \
preload_model(); preload_clip_model()"

COPY docker/backend/entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
