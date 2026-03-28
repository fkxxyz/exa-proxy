FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EXA_PROXY_HOST=0.0.0.0 \
    EXA_PROXY_PORT=8080 \
    EXA_PROXY_STORAGE=/data/keys.json \
    EXA_PROXY_UPSTREAM=https://mcp.exa.ai/mcp

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

VOLUME ["/data"]

EXPOSE 8080

CMD ["python", "-m", "exa_proxy.main"]
