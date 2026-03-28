#!/bin/bash
# Exa Proxy 启动脚本

cd "$(dirname "$0")"

# 默认配置
export EXA_PROXY_HOST="${EXA_PROXY_HOST:-127.0.0.1}"
export EXA_PROXY_PORT="${EXA_PROXY_PORT:-8080}"
export EXA_PROXY_STORAGE="${EXA_PROXY_STORAGE:-./data/keys.json}"
export EXA_PROXY_UPSTREAM="${EXA_PROXY_UPSTREAM:-https://mcp.exa.ai/mcp}"

echo "Starting Exa Proxy..."
echo "  Host: $EXA_PROXY_HOST"
echo "  Port: $EXA_PROXY_PORT"
echo "  Storage: $EXA_PROXY_STORAGE"
echo "  Upstream: $EXA_PROXY_UPSTREAM"
echo ""

exec .venv/bin/python -m exa_proxy.main
