# Exa Proxy 快速参考

## 启动和停止

```bash
# 启动
./start.sh

# 停止
kill $(cat /tmp/exa-proxy.pid)

# 查看日志
tail -f /tmp/exa-proxy-v2.log

# 查看状态
./cli.py health
```

## Key 管理

```bash
# 列出所有 keys
./cli.py list

# 添加 key
./cli.py add "your_exa_key" --name "My Key"

# 查看统计
./cli.py stats

# 删除所有 keys（回到免费模式）
for id in $(./cli.py list | tail -n +3 | awk '{print $1}'); do
  curl -s -X DELETE http://127.0.0.1:8080/api/keys/$id
done
```

## API 端点

```bash
# 健康检查
curl http://127.0.0.1:8080/health

# 列出 keys
curl http://127.0.0.1:8080/api/keys

# 添加 key
curl -X POST http://127.0.0.1:8080/api/keys \
  -H "Content-Type: application/json" \
  -d '{"key": "your_key", "name": "My Key"}'

# 统计信息
curl http://127.0.0.1:8080/api/keys/stats

# 禁用 key
curl -X PUT http://127.0.0.1:8080/api/keys/{key_id} \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# 重置 key（清除冷却）
curl -X POST http://127.0.0.1:8080/api/keys/{key_id}/reset

# 删除 key
curl -X DELETE http://127.0.0.1:8080/api/keys/{key_id}
```

## OpenCode 配置

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

重启 OpenCode：

```bash
systemctl --user restart opencode-serve.service
```

## 工作模式

| 模式 | 条件 | 行为 |
|------|------|------|
| **有 Key 模式** | 至少一个 key 可用 | 轮询使用 keys，失败时切换 |
| **Fallback 模式** | 有 keys 但都不可用 | 自动降级到免费额度 |
| **无 Key 模式** | 从未添加 key | 直接使用免费额度 |

## 重试策略

| 错误类型 | 行为 |
|----------|------|
| 429 (Rate Limit) | 冷却 60 秒，切换下一个 key |
| 5xx (Server Error) | 切换下一个 key |
| 4xx (Client Error) | 不重试，直接返回 |
| 网络错误 | 切换下一个 key |
| 所有 keys 不可用 | Fallback 到免费额度 |

## 监控

```bash
# 实时日志
tail -f /tmp/exa-proxy-v2.log

# 查看 fallback 事件
tail -f /tmp/exa-proxy-v2.log | grep -i fallback

# 查看错误
tail -f /tmp/exa-proxy-v2.log | grep -i error

# 健康检查
watch -n 5 './cli.py health'

# 统计信息
watch -n 10 './cli.py stats'
```

## 测试

```bash
# 运行所有测试
.venv/bin/pytest

# 运行特定测试
.venv/bin/pytest tests/test_key_manager.py -v
.venv/bin/pytest tests/test_fallback.py -v

# 测试覆盖率
.venv/bin/pytest --cov=exa_proxy
```

## 环境变量

```bash
export EXA_PROXY_HOST="127.0.0.1"      # 监听地址
export EXA_PROXY_PORT="8080"           # 监听端口
export EXA_PROXY_STORAGE="./data/keys.json"  # Key 存储路径
export EXA_PROXY_UPSTREAM="https://mcp.exa.ai/mcp"  # 上游地址
```

## 常见任务

### 添加多个 keys

```bash
./cli.py add "exa_key_1" --name "主 Key"
./cli.py add "exa_key_2" --name "备用 Key 1"
./cli.py add "exa_key_3" --name "备用 Key 2"
```

### 查看哪些 keys 在冷却

```bash
curl -s http://127.0.0.1:8080/api/keys | \
  jq '.[] | select(.cooldown_until != null) | {name, cooldown_until}'
```

### 查看错误率最高的 key

```bash
curl -s http://127.0.0.1:8080/api/keys | \
  jq -r '.[] | "\(.stats.error_429_count + .stats.error_5xx_count)\t\(.name)"' | \
  sort -rn | head -5
```

### 备份和恢复

```bash
# 备份
cp data/keys.json data/keys.backup.json

# 恢复
cp data/keys.backup.json data/keys.json
# 重启服务
kill $(cat /tmp/exa-proxy.pid) && ./start.sh
```

## 故障排查

### 服务无法启动

```bash
# 检查端口占用
lsof -i:8080

# 查看日志
tail -50 /tmp/exa-proxy-v2.log

# 检查配置
cat data/keys.json | jq
```

### 所有请求都失败

```bash
# 检查健康状态
./cli.py health

# 查看 keys 状态
./cli.py list

# 查看日志
tail -f /tmp/exa-proxy-v2.log
```

### Key却

```bash
# 查看统计
./cli.py stats

# 可能原因：
# 1. Key 配额不足 → 添加更多 keys
# 2. 请求频率过高 → 降低请求频率
# 3. Key 无效 → 检查 key 是否正确
```

## 文档

- [README.md](README.md) - 完整文档
- [USAGE.md](USAGE.md) - 使用示例
- [FALLBACK.md](FALLBACK.md) - Fallback 机制详解
- [SUMMARY.md](SUMMARY.md) - 项目总结

## 获取帮助

```bash
# CLI 帮助
./cli.py --help

# 查看 API 文档
curl http://127.0.0.1:8080/docs  # (如果启用了 FastAPI docs)
```
