# Multi-stage Dockerfile for Icarus Agent API and Worker services
# Stage 1: Build virtual environment with uv
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency manifests and source trees
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/ apps/

# Synchronize production dependencies into /app/.venv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev

# Stage 2: Minimal production runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

# Install ca-certificates and curl for health probes
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged service user
RUN useradd -m -u 1000 icarus && chown -R icarus:icarus /app

# Copy compiled virtual environment and application code
COPY --from=builder --chown=icarus:icarus /app/.venv /app/.venv
COPY --from=builder --chown=icarus:icarus /app /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

USER icarus

EXPOSE 8000

# Default command launches FastAPI server
CMD ["uvicorn", "icarus_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
