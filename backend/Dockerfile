FROM ghcr.io/astral-sh/uv:python3.11-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=.

WORKDIR /backend

# Copy only dependency files first for better caching
COPY ./pyproject.toml ./uv.lock* ./

# Install deps (creates/uses .venv)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

# Copy application code
COPY . /backend

EXPOSE 8000
