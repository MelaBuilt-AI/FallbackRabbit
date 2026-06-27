# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy source
COPY fallbackrabbit/ ./fallbackrabbit/
COPY README.md LICENSE ./

# Build wheel
RUN uv run python -m build --wheel

# ──────────────────────────────────────────────
# Runtime stage
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy built wheel and install
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl

# Create data directory
RUN mkdir -p /app/data

# Expose API port
EXPOSE 8000

# Environment defaults
ENV FALLBACKRABBIT_HOST=0.0.0.0
ENV FALLBACKRABBIT_PORT=8000
ENV FALLBACKRABBIT_STORAGE_URL=sqlite:////app/data/chains.db

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the server
CMD ["fallbackrabbit", "serve", "--host", "0.0.0.0", "--port", "8000"]