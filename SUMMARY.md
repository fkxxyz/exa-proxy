# Exa Proxy 项目总结

## 项目概述

Exa Proxy 是一个智能 MCP 代理服务，为 Exa API 提供多 key 管理、自动重试、失败切换功能。

## 已实现功能

### 核心功能

1. **多 Key 管理**
   - JSON 文件持久化存储
   - 支持添加、删除、启用/禁用 keys
   - 每个 key 独立的统计信息

2. **智能选择**
   - 轮询算法选择可用 key
   - 自动跳过禁用和冷却中的 keys
   - 线程安全的并发访问

3. **自动重试与 Fallback**
   - 429 (Rate Limit) → 冷却 60 秒，切换下一个 key
   - 5xx (Server Error) → 切换下一个 key
   - 4xx (Client Error, 除 429) → 不重试
   - 网络错误 → 切换下一个 key
   - **所有 key 不可用 → 自动 fallback 到无 key 模式（使用 Exa 免费额度）**
   - **从未添加 key → 直接使用无 key 模式（使用 Exa 免费额度）**
   - 默认最多重试 8 次（共 9 次尝试），指数退避封顶 32 秒

4. **统计跟踪**
   - 总请求数、成功数
   - 429 错误数、5xx 错误数
   - 最后使用时间、最后错误时间

5. **RESTful API**
   - `GET /api/keys` - 列出所有 keys
   - `POST /api/keys` - 添加 key
   - `GET /api/keys/{id}` - 获取单个 key
   - `PUT /api/keys/{id}` - 更新 key
   - `DELETE /api/keys/{id}` - 删除 key
   - `POST /api/keys/{id}/reset` - 重置 key 状态
   - `GET /api/keys/stats` - 统计信息
   - `GET /health` - 健康检查

6. **MCP 代理**
   - 透明代理 `/mcp` 端点
   - 自动添加 `exaApiKey` URL 参数
   - 支持 SSE (Server-Sent Events) 响应

7. **CLI 工具**
   - `./cli.py list` - 列出 keys
   - `./cli.py add <key> --name <name>` - 添加 key
   - `./cli.py stats` - 统计信息
   - `./cli.py health` - 健康检查

## 项目结构

```
exa-proxy/
├── src/exa_proxy/
│   ├── __init__.py
│   ├── main.py           # FastAPI 应用入口
│   ├── key_manager.py    # Key 管理核心逻辑
│   ├── executor.py       # 代理执行器（重试逻辑）
│   ├── api.py            # RESTful API 路由
│   ├── config.py         # 配置模型（旧）
│   ├── router.py         # 上游路由器（旧）
│   ├── proxy_logic.py    # 代理逻辑（旧）
│   ├── http_proxy.py     # HTTP 代理（旧）
│   └── middleware.py     # 中间件（旧）
├── tests/
│   ├── test_key_manager.py    # Key 管理测试 ✅
│   ├── test_router.py         # 路由测试（旧）
│   ├── test_retry_policy.py   # 重试测试（旧）
│   └── test_main.py           # 主程序测试（旧）
├── data/
│   └── keys.json         # Key 存储文件
├── pyproject.toml        # 项目配置
├── README.md             # 项目文档
├── USAGE.md              # 使用示例
├── start.sh              # 启动脚本
└── cli.py                # CLI 管理工具
```

## 技术栈

- **Python 3.11+**
- **FastAPI** - Web 框架
- **Uvicorn** - ASGI 服务器
- **httpx** - HTTP 客户端
- **Pydantic** - 数据验证
- **pytest** - 测试框架

## 配置

环境变量：

- `EXA_PROXY_HOST` - 监听地址（默认：127.0.0.1）
- `EXA_PROXY_PORT` - 监听端口（默认：8080）
- EXA_PROXY_STORAGE` - Key 存储路径（默认：./data/keys.json）
- `EXA_PROXY_UPSTREAM` - 上游 URL（默认：https://mcp.exa.ai/mcp）

## 测试状态

- ✅ Key 管理测试（10/10 通过）
- ⚠️ 旧的路由/重试测试（基于旧架构，需要更新）

## 当前运行状态

- 服务运行中：`http://127.0.0.1:8080`
- PID 文件：`/tmp/exa-proxy.pid`
- 日志文件：`/tmp/exa-proxy-v2.log`
- 已添加 2 个测试 keys

## OpenCode 集成

已配置 OpenCode 使用本地代理：

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

## 架构变更

### 旧架构（v0.1）

- 基于 FastMCP `create_proxy()`
- 静态配置多个上游
- 中间件日志记录
- 未实现真正的 key 轮询

### 新架构（v0.2）

- 基于 FastAPI
- 动态 key 管理（JSON 存储）
- 智能选择和重试
- RESTful API 管理
- 真正的多 key 轮询和失败切换

## 未来计划

- [ ] Web UI 管理界面
- [ ] 余额不足检测
- [ ] 更细粒度的重试策略配置
- [ ] Key 使用配额限制
- [ ] 请求日志查询 API
- [ ] Prometheus metrics 导出
- [ ] Docker 容器化
- [ ] 更新旧的测试用例

## 快速命令

```bash
# 启动服务
./start.sh

# 查看日志
tail -f /tmp/exa-proxy-v2.log

# 添加 key
./cli.py add "your_exa_key" --name "My Key"

# 列出 keys
./cli.py list

# 查看统计
./cli.py stats

# 健康检查
./cli.py health

# 停止服务
kill $(cat /tmp/exa-proxy.pid)

# 运行测试
.venv/bin/pytest tests/test_key_manager.py -v
```

## 关键文件

- `src/exa_proxy/key_manager.py` - 核心 key 管理逻辑
- `src/exa_proxy/executor.py` - 代理执行和重试逻辑
- `src/exa_proxy/api.py` - RESTful API 定义
- `src/exa_proxy/main.py` - FastAPI 应用入口
- `data/keys.json` - Key 持久化存储

## 注意事项

1. **Key 安全**：keys.json 包含敏感信息，不要提交到 git
2. **并发安全**：KeyManager 使用线程锁保证并发安全
3. **冷却机制**：失败的 key 会自动冷却 60 秒
4. **重试限制**：默认最多重试 8 次（共 9 次尝试），指数退避封顶 32 秒，避免无限循环
5. **4xx 错误**：除 429 外的 4xx 错误不会重试（客户端错误）

## 已知限制

1. 单进程运行（未来可考虑多进程/分布式）
2. JSON 文件存储（未来可考虑数据库）
3. 内存中的冷却状态（重启后丢失）
4. 无请求日志持久化
5. 无 Web UI

## 贡献者

- 初始开发：八叶草 (2026-03-28)
