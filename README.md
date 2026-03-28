# exa-proxy

Exa MCP 智能代理：多 key 管理、自动重试、失败切换。

## 功能特性

- **多 key 管理**：支持添加、删除、启用/禁用多个 Exa API key
- **智能轮询**：自动轮询选择可用的 key
- **自动重试**：遇到 429 或 5xx 错误自动切换下一个 key 重试
- **智能 Fallback**：所有 keys 不可用时自动降级到免费额度（[详细说明](FALLBACK.md)）
- **冷却机制**：失败的 key 自动进入冷却期（默认 60 秒）
- **统计跟踪**：记录每个 key 的请求次数、成功率、错误类型
- **RESTful API**：完整的 key 管理 API，方便集成 Web UI
- **MCP 代理**：透明代理 Exa MCP 协议，无需修改客户端
- **零配置可用**：无需添加 key 即可使用（免费额度）

## 快速开始

### 1. 安装

```bash
cd /run/media/fkxxyz/wsl/home/fkxxyz/pro/exa-proxy
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### 2. 启动服务

```bash
./start.sh
```

或手动启动：

```bash
export EXA_PROXY_HOST="127.0.0.1"
export EXA_PROXY_PORT="8080"
export EXA_PROXY_STORAGE="./data/keys.json"
export EXA_PROXY_UPSTREAM="https://mcp.exa.ai/mcp"

.venv/bin/python -m exa_proxy.main
```

### 3. 添加 API key

```bash
# 添加第一个 key
curl -X POST http://127.0.0.1:8080/api/keys \
  -H "Content-Type: application/json" \
  -d '{"key": "your_exa_api_key_1", "name": "key-1"}'

# 添加第二个 key
curl -X POST http://127.0.0.1:8080/api/keys \
  -H "Content-Type: application/json" \
  -d '{"key": "your_exa_api_key_2", "name": "key-2"}'
```

### 4. 配置 OpenCode

编辑 `~/.config/opencode/opencode.json`：

```json
{
  "mcp": {
    "exa": {
      "type": "remote",
      "url": "http://127.0.0.1:8080/mcp",
      "enabled": true
    }
  }
}
```

重启 OpenCode 后即可使用。

## API 文档

### Key 管理 API

#### 列出所有 keys

```bash
GET /api/keys
```

响应示例：

```json
[
  {
    "id": "uuid-1",
    "name": "key-1",
    "key": "exa_api_key_xxx",
    "enabled": true,
    "created_at": "2026-03-28T10:00:00Z",
    "cooldown_until": null,
    "stats": {
      "total_requests": 100,
      "success_count": 95,
      "error_429_count": 3,
      "error_5xx_count": 2,
      "error_other_count": 0,
      "last_used_at": "2026-03-28T12:00:00Z",
      "last_error_at": "2026-03-28T11:30:00Z"
    }
  }
]
```

#### 添加 key

```bash
POST /api/keys
Content-Type: application/json

{
  "key": "your_exa_api_key",
  "name": "optional_friendly_name"
}
```

#### 获取单个 key

```bash
GET /api/keys/{key_id}
```

#### 更新 key

```bash
PUT /api/keys/{key_id}
Content-Type: application/json

{
  "name": "new_name",
  "enabled": false
}
```

#### 删除 key

```bash
DELETE /api/keys/{key_id}
```

#### 重置 key 状态（清除冷却）

```bash
POST /api/keys/{key_id}/reset
```

#### 获取统计信息

```bash
GET /api/keys/stats
```

响应示例：

```json
{
  "total_keys": 3,
  "enabled_keys": 3,
  "available_keys": 2,
  "in_cooldown": 1,
  "total_requests": 500,
  "total_success": 480,
  "total_429_errors": 15,
  "total_5xx_errors": 5
}
```

### MCP 代理端点

```bash
GET/POST /mcp
```

透明代理 Exa MCP 请求，自动选择可用的 key 并处理重试。

### 健康检查

```bash
GET /health
```

响应示例：

```json
{
  "status": "ok",
  "available_keys": 2,
  "total_keys": 3
}
```

## 重试策略

### Key 选择策略

1. **有可用 key**：轮询选择可用的 key
2. **所有 key 不可用**：自动 fallback 到无 key 模式（使用 Exa 免费额度）
3. **从未添加 key**：直接使用无 key 模式（使用 Exa 免费额度）

### 重试规则

- **429 (Rate Limit)**：
  - 有 key：标记 key 冷却 60 秒，切换下一个 key 重试
  - 无 key：等待 1 秒后重试
- **5xx (Server Error)**：切换下一个 key 重试
- **4xx (Client Error, 除 429)**：不重试，直接返回错误
- **网络错误**：切换下一个 key 重试

最多重试 5 次（可配置）。

### Fallback 机制

当所有 key 都不可用时（禁用或冷却中），代理会自动 fallback 到无 key 模式，使用 Exa 的免费额度。这确保服务始终可用，即使在 key 耗尽的情况下也能继续工作（受免费额度限制）。

## 配置选项

环境变量：

- `EXA_PROXY_HOST`：监听地址（默认：`127.0.0.1`）
- `EXA_PROXY_PORT`：监听端口（默认：`8080`）
- `EXA_PROXY_STORAGE`：key 存储文件路径（默认：`./data/keys.json`）
- `EXA_PROXY_UPSTREAM`：上游 Exa MCP 地址（默认：`https://mcp.exa.ai/mcp`）

## 测试

```bash
# 运行所有测试
.venv/bin/pytest

# 运行 key 管理测试
.venv/bin/pytest tests/test_key_manager.py -v

# 运行旧的路由测试
.venv/bin/pytest tests/test_router.py tests/test_retry_policy.py -v
```

## 架构说明

### 核心组件

1. **KeyManager** (`key_manager.py`)
   - 负责 key 的持久化存储（JSON 文件）
   - 实现轮询选择算法
   - 管理 key 状态（启用/禁用/冷却）
   - 跟踪统计信息

2. **ProxyExecutor** (`executor.py`)
   - 负责执行代理请求
   - 自动选择可用的 key
   - 处理重试逻辑
   - 构造带 `exaApiKey` 参数的 URL

3. **API Router** (`api.py`)
   - 提供 RESTful API 管理 keys
   - 基于 FastAPI

4. **Main App** (`main.py`)
   - 集成 FastAPI 和 MCP 代理
   - 提供 `/mcp` 端点透明代理请求
   - 提供 `/api/keys` 端点管理 keys

### 数据流

```
OpenCode
  ↓ MCP request
Proxy (/mcp)
  ↓ choose available key
ProxyExecutor
  ↓ add exaApiKey to URL
Exa MCP (https://mcp.exa.ai/mcp?exaApiKey=xxx)
  ↓ response or error
ProxyExecutor
  ↓ retry with next key if needed
Proxy
  ↓ MCP response
OpenCode
```

## 未来计划

- [ ] Web UI 管理界面
- [ ] 余额不足检测（需要确定状态码）
- [ ] 更细粒度的重试策略配置
- [ ] Key 使用配额限制
- [ ] 请求日志查询
- [ ] Prometheus metrics 导出

## License

MIT
