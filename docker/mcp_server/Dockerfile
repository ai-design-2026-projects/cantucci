FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY mcp_server/ ./mcp_server/

ENV CINEPAL_MCP_BACKEND_URL=http://backend:8000

ENTRYPOINT ["python", "-m", "mcp_server.server"]
