FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml ./
RUN uv sync --no-dev

COPY main.py ./

EXPOSE 9091

# Shell form so ${PORT:-9091} expands correctly on Railway and locally
CMD uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-9091}
