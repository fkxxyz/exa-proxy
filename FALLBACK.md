# Fallback 机制说明

## 概述

Exa Proxy 实现了智能的 fallback 机制，确保服务在任何情况下都能保持可用。

## 三种工作模式

### 1. 有 Key 模式（推荐）

**场景**：已添加至少一个可用的 API key

**行为**：
- 轮询选择可用的 key
- 遇到 429 或 5xx 错误时自动切换下一个 key
- 失败的 key 进入 60 秒冷却期

**优势**：
- 更高的请求配额
- 更稳定的服务质量
- 多 key 负载均衡

**示例**：
```bash
# 添加 keys
./cli.py add "exa_key_1" --name "主 Key"
./cli.py add "exa_key_2" --name "备用 Key"

# 查看状态
./cli.py health
# 输出: Available keys: 2/2
```

### 2. Fallback 模式（自动降级）

**场景**：已添加 keys，但所有 keys 都不可用（禁用或冷却中）

**行为**：
- 自动切换到无 key 模式
- 使用 Exa 免费额度
- 日志记录 fallback 事件
- 继续尝试恢复使用 keys

**触发条件**：
- 所有 keys 都被禁用
- 所有 keys 都在冷却期
- 所有 keys 都遇到持续错误

**日志示例**：
```
[WARNING] All keys unavailable, falling back to no-key mode (free tier)
[INFO] Request succeeded with no-key mode (status=200)
```

**示例场景**：
```bash
# 所有 keys 都遇到 429
# Key 1: 冷却中（还剩 45 秒）
# Key 2: 冷却中（还剩 30 秒）
# → 自动 fallback 到免费额度

# 60 秒后，keys 恢复可用
# → 自动切换回使用 keys
```

### 3. 无 Key 模式（免费额度）

**场景**：从未添加任何 API key

**行为**：
- 直接使用 Exa 免费额度
- 不尝试使用 keys
- 受免费额度限制

**限制**：
- 更低的请求配额
- 可能遇到更频繁的 429 错误

**日志示例**：
```
[INFO] No keys configured, using no-key mode (free tier)
[INFO] Request succeeded with no-key mode (status=200)
```

**适用场景**：
- 测试和开发
- 低频使用
- 临时使用

## 工作流程图

```
请求到达
  ↓
有可用 key？
  ├─ 是 → 使用 key 发送请求
  │        ↓
  │      成功？
  │        ├─ 是 → 返回结果
  │        └─ 否 → 429/5xx？
  │                 ├─ 是 → 标记冷却，切换下一个 key
  │                 └─ 否 → 返回错误
  │
  └─ 否 → 有任何 keys（但都不可用）？
           ├─ 是 → Fallback 到无 key 模式
           │        ↓
           │      发送无 key 请求
           │        ↓
           │      成功？
           │        ├─ 是 → 返回结果
           │        └─ 否 → 等待 1 秒，重试
           │
           └─ 否 → 直接使用无 key 模式
                    ↓
                  发送无 key 请求
                    ↓
                  返回结果
```

## 配置建议

### 生产环境

```bash
# 添加多个 keys 以提高可用性
./cli.py add "exa_key_1" --name "主 Key"
./cli.py add "exa_key_2" --name "备用 Key 1"
./cli.py add "exa_key_3" --name "备用 Key 2"

# 定期监控
./cli.py stats
```

**优势**：
- 高可用性
- 自动故障转移
- 即使所有 keys 失败也能 fallback

### 开发/测试环境

```bash
# 选项 1：不添加 key，使用免费额度
# 无需配置，直接使用

# 选项 2：添加一个开发 key
./cli.py add "exa_dev_key" --name "开发 Key"
```

## 监控和告警

### 检测 Fallback 事件

查看日志：
```bash
tail -f /tmp/exa-proxy-v2.log | grep -i fallback
```

输出示例：
```
[2026-03-28 14:10:23] [WARNING] All keys unavailable, falling back to no-key mode (free tier)
```

### 健康检查

```bash

./cli.py health
```

输出解读：
- `Available keys: 0/0` - 无 key 模式
- `Available keys: 0/3` - Fallback 模式（3 个 keys 都不可用）
- `Available keys: 2/3` - 正常模式（2 个 keys 可用）

### 告警规则建议

1. **Critical**: `available_keys == 0 && total_keys > 0`
   - 所有 keys 不可用，正在使用 fallback

2. **Warning**: `available_keys < total_keys / 2`
   - 超过一半的 keys 不可用

3. **Info**: `total_keys == 0`
   - 无 key 模式（预期行为）

## 常见问题

### Q: Fallback 模式会影响性能吗？

A: 不会。Fallback 只是切换到不带 key 的请求，网络延迟相同。但免费额度的配额更低，可能更容易遇到 429 错误。

### Q: Fallback 后会自动恢复使用 keys 吗？

A: 会。每次请求都会先尝试选择可用的 key，如果 key 冷却期结束，会自动恢复使用。

### Q: 可以禁用 Fallback 吗？

A: 当前版本不支持禁用。Fallback 是为了确保服务可用性的安全机制。

### Q: Fallback 模式下的请求会被统计吗？

A: 不会。只有使用 key 的请求才会被记录到 key 的统计信息中。

### Q: 如何知道当前是否在使用 Fallback？

A: 查看日志或健康检查：
```bash
./cli.py health
# 如果 available_keys: 0/N (N > 0)，说明在使用 fallback
```

## 最佳实践

1. **添加多个 keys**：至少 2-3 个，提高可用性
2. **监控健康状态**：定期检查 `available_keys`
3. **设置告警**：当进入 fallback 模式时收到通知
4. **查看日志**：了解 fallback 触发的原因
5. **及时处理**：如果频繁 fallback，考虑添加更多 keys 或升级配额

## 示例：完整的使用流程

```bash
# 1. 启动服务（无 key）
./start.sh
# → 使用无 key 模式

# 2. 添加第一个 key
./cli.py add "exa_key_1" --name "主 Key"
# → 自动切换到有 key 模式

# 3. 主 key 遇到 429
# → 自动 fallback 到无 key 模式
# → 日志: "All keys unavailable, falling back to no-key mode"

# 4. 60 秒后，主 key 冷却结束
# → 自动恢复使用主 key
# → 日志: "Request succeeded with key 主 Key"

# 5. 添加备用 key
./cli.py add "exa_key_2" --name "备用 Key"
# → 现在有 2 个 keys 轮询

# 6. 主 key 再次遇到 429
# → 切换到备用 key（不需要 fallback）
# → 日志: "Key 主 Key failed with status 429, marking cooldown and retrying..."
# → 日志: "Request succeeded with key 备用 Key"
```

## 总结

Fallback 机制确保 Exa Proxy 在任何情况下都能保持可用：

- ✅ 有 keys 时优先使用 keys
- ✅ Keys 不可用时自动降级到免费额度
- ✅ Keys 恢复后自动切换回来
- ✅ 从未添加 keys 也能正常工作

这种设计让服务既灵活又可靠，适合各种使用场景。
