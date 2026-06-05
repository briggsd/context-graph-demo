# mcp-server — thin wrapper around Dockerfile.backend with a different CMD
# Build context must be set to the repo root in Railway dashboard.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY backend/pyproject.toml ./
RUN uv sync --no-dev --no-install-project
RUN uv run python -m spacy download en_core_web_sm
COPY backend/ .
CMD ["uv", "run", "python", "mcp_server.py"]
