# Exa Proxy 使用示例

## 场景 1：基本使用

### 1. 启动服务

```bash
cd /run/media/fkxxyz/wsl/home/fkxxyz/pro/exa-proxy
./start.sh
```

### 2. 添加 API keys

```bash
# 添加第一个 key
curl -X POST http://127.0.0.1:8080/api/keys \
  -H "Content-Type: application/json" \
  -d '{"key": "your_real_exa_key_1", "name": "主 Key"}'

# 添加备用 key
curl -X POST http://127.0.0.1:8080/api/keys \
  -H "Content-Type: application/json" \
  -d '{"key": "your_real_exa_key_2", "name": "备用 Key"}'
```

### 3. 查看所有 keys

```bash
curl http://127.0.0.1:8080/api/keys | jq
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

### 5. 重启 OpenCode

```bash
systemctl --user restart opencode-serve.service
```

现在 OpenCode 使用 Exa 工具时会自动通过代理，并在遇到 429 错误时自动切换 key。

## 场景 2：监控和管理

### 查看统计信息

```bash
curl http://127.0.0.1:8080/api/keys/stats | jq
```

输出示例：

```json
{
  "total_keys": 3,
  "enabled_keys": 3,
  "available_keys": 2,
  "in_cooldown": 1,
  "total_requests": 150,
  "total_success": 140,
  "total_429_errors": 8,
  "total_5xx_errors": 2
}
```

### 查看单个 key 详情

```bash
KEY_ID="fcc83c8b-5251-487a-9332-530005087d1d"
curl http://127.0.0.1:8080/api/keys/$KEY_ID | jq
```

### 禁用某个 key

```bash
KEY_ID="fcc83c8b-5251-487a-9332-530005087d1d"
curl -X PUT http://127.0.0.1:8080/api/keys/$KEY_ID \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### 重新启用 key

```bash
KEY_ID="fcc83c8b-5251-487a-9332-530005087d1d"
curl -X PUT http://127.0.0.1:8080/api/keys/$KEY_ID \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### 手动清除 key 冷却状态

```bash
KEY_ID="fcc83c8b-5251-487a-9332-530005087d1d"
curl -X POST http://127.0.0.1:8080/api/keys/$KEY_ID/reset
```

### 删除 key

```bash
KEY_ID="fcc83c8b-5251-487a-9332-530005087d1d"
curl -X DELETE http://127.0.0.1:8080/api/keys/$KEY_ID
```

## 场景 3：监控日志

### 实时查看代理日志

```bash
tail -f /tmp/exa-proxy-v2.log
```

日志会显示：

- 每次请求使用的 key
- 请求成功/失败状态
- 自动重试和切换 key 的过程

示例日志：

```
[2026-03-28 13:53:45] [exa_proxy.executor] INFO: Request succeeded with key 主 Key (status=200)
[2026-03-28 13:54:10] [exa_proxy.executor] WARNING: Key 主 Key failed with status 429, marking cooldown and retrying...
[2026-03-28 13:54:10] [exa_proxy.executor] INFO: Request succeeded with key 备用 Key (status=200)
```

## 场景 4：批量管理

### 批量添加 keys

```bash
#!/bin/bash
KEYS=(
  "exa_key_1:主 Key"
  "exa_key_2:备用 Key 1"
  "exa_key_3:备用 Key 2"
)

for entry in "${KEYS[@]}"; do
  IFS=':' read -r key name <<< "$entry"
  curl -X POST http://127.0.0.1:8080/api/keys \
    -H "Content-Type: application/json" \
    -d "{\"key\": \"$key\", \"name\": \"$name\"}"
  echo ""
done
```

### 导出所有 keys（备份）

```bash
curl http://127.0.0.1:8080/api/keys > keys_backup.json
```

### 查看哪些 keys 在冷却中

```bash
curl http://127.0.0.1:8080/api/keys | jq '.[] | select(.cooldown_until != null) | {name, cooldown_until}'
```

### 查看错误率最高的 key

```bash
curl http://127.0.0.1:8080/api/keys | jq -r '.[] | "\(.stats.error_429_count + .stats.error_5xx_co)\t\(.name)"' | sort -rn
```

## 场景 5：健康检查和告警

### 简单健康检查脚本

```bash
#!/bin/bash
# check_exa_proxy.sh

RESPONSE=$(curl -s http://127.0.0.1:8080/health)
AVAILABLE=$(echo $RESPONSE | jq -r '.available_keys')
TOTAL=$(echo $RESPONSE | jq -r '.total_keys')

if [ "$AVAILABLE" -eq 0 ]; then
  echo "CRITICAL: No available keys!"
  exit 2
elif [ "$AVAILABLE" -lt 2 ]; then
  echo "WARNING: Only $AVAILABLE/$TOTAL keys available"
  exit 1
else
  echo "OK: $AVAILABLE/$TOTAL keys available"
  exit 0
fi
```

### 定时检查（crontab）

```bash
# 每 5 分钟检查一次
*/5 * * * o/check_exa_proxy.sh
```

## 场景 6：开发和调试

### 测试代理是否工作

```bash
# 使用 httpie 或 curl 直接测试 MCP 端点
curl -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

### 查看 key 存储文件

```bash
cat /run/media/fkxxyz/wsl/home/fkxxyz/pro/exa-proxy/data/keys.json | jq
```

### 手动编）

```bash
# 停止服务
kill $(cat /tmp/exa-proxy.pid)

# 编辑文件
vim /run/media/fkxxyz/wsl/home/fkxxyz/pro/exa-proxy/data/keys.json

# 重启服务
cd /run/media/fkxxyz/wsl/home/fkxxyz/pro/exa-proxy && ./start.sh
```

## 常见问题

### Q: 如何知道当前使用的是哪个 key？

A: 查看日志 `/tmp/exa-proxy-v2.log`，每次请求都会记录使用的 key 名称。

### Q: 所有 key 都 429 了怎么办？

A: 代理会等待 1 秒后重新评估，如果有 key 冷却期结束会自动使用。你也可以手动重置 key：

```bash
curl -X POST http://127.0.0.1:8080/api/keys/{key_id}/reset
```

### Q: 如何临时禁用某个 key？

A: 使用 PUT 请求更新 `enabled` 字段为 `false`。

### Q: 代理会影响性能吗？

A: 几乎没有影响，代理只是转发请求并添加 `exaApiKey` 参数。网络延迟主要来自上游 Exa 服务。

### Q: 可以在生产环境使用吗？

A: 可以，但建议：
- 使用 systemd 或 supervisor 管理进程
- 配置日志轮转
- 定期备份 keys.json
- 监控健康检查端点

## 进阶：systemd 服务配置

创建 `/etc/systemd/user/exa-proxy.service`：

```ini
[Unit]
Description=Exa MCP Proxy
After=network.target

[Service]
Type=simple
WorkingDirectory=/run/media/fkxxyz/wsl/home/fkxxyz/pro/exa-proxy
ExecStart=/run/media/fkxxyz/wsl/home/fkxxyz/pro/exa-proxy/start.sh
Restart=always
RestartSec=10
Environment="EXA_PROXY_HOST=127.0.0.1"
Environment="EXA_PROXY_PORT=8080"
Environment="EXA_PROXY_STORAGE=/run/media/fkxxyz/wsl/home/fkxxyz/pro/exa-proxy/data/keys.json"

[Install]
WantedBy=default.target
```

启用服务：

```bash
systemctl --user daemon-reload
systemctl --user enable exa-proxy.service
systemctl --user start exa-proxy.service
systemctl --user status exa-proxy.service
```
