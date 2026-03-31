# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
WORKDIR /app

# Create virtualenv for clean dependency isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Step 1: Install dependencies ONLY (changes rarely)
# This layer is cached unless pyproject.toml dependencies change
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
        fastapi fastmcp httpx pydantic pydantic-settings uvicorn validators

# Step 2: Copy source code (changes frequently)
# This does NOT invalidate the dependency cache above
COPY src ./src

# Step 3: Install the package itself (no deps, already installed)
RUN pip install --no-deps .

# Runtime image
FROM python:3.12-slim
WORKDIR /app

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EXA_PROXY_HOST=0.0.0.0 \
    EXA_PROXY_PORT=8080 \
    EXA_PROXY_STORAGE=/data/keys.json \
    EXA_PROXY_UPSTREAM=https://mcp.exa.ai/mcp

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application files
COPY README.md ./

# Data volume (container runs as root to match host file permissions)
VOLUME ["/data"]

EXPOSE 8080

CMD ["python", "-m", "exa_proxy.main"]
