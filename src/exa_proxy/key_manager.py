"""API Key 管理模块：持久化存储、智能选择、状态跟踪"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass
class KeyStats:
    """Key 使用统计"""

    total_requests: int = 0
    success_count: int = 0
    error_429_count: int = 0
    error_5xx_count: int = 0
    error_other_count: int = 0
    last_used_at: str | None = None
    last_error_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "error_429_count": self.error_429_count,
            "error_5xx_count": self.error_5xx_count,
            "error_other_count": self.error_other_count,
            "last_used_at": self.last_used_at,
            "last_error_at": self.last_error_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KeyStats:
        return cls(**data)


@dataclass
class ApiKey:
    """API Key 实体"""

    id: str
    key: str
    name: str
    enabled: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    cooldown_until: str | None = None
    stats: KeyStats = field(default_factory=KeyStats)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "cooldown_until": self.cooldown_until,
            "stats": self.stats.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApiKey:
        stats_data = data.pop("stats", {})
        return cls(**data, stats=KeyStats.from_dict(stats_data))

    def is_available(self) -> bool:
        """检查 key 是否可用（启用且未在冷却中）"""
        if not self.enabled:
            return False
        if self.cooldown_until:
            cooldown_time = datetime.fromisoformat(self.cooldown_until)
            if cooldown_time > datetime.now(timezone.utc):
                return False
        return True

    def mark_cooldown(self, seconds: int = 60) -> None:
        """标记 key 进入冷却期"""
        until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        self.cooldown_until = until.isoformat()

    def clear_cooldown(self) -> None:
        """清除冷却状态"""
        self.cooldown_until = None

    def record_request(self, success: bool, status_code: int | None = None) -> None:
        """记录请求结果"""
        now = datetime.now(timezone.utc).isoformat()
        self.stats.total_requests += 1
        self.stats.last_used_at = now

        if success:
            self.stats.success_count += 1
        else:
            self.stats.last_error_at = now
            if status_code == 429:
                self.stats.error_429_count += 1
            elif status_code and 500 <= status_code < 600:
                self.stats.error_5xx_count += 1
            else:
                self.stats.error_other_count += 1


class KeyManager:
    """API Key 管理器：负责存储、选择、状态管理"""

    def __init__(self, storage_path: Path | str):
        self.storage_path = Path(storage_path)
        self._keys: dict[str, ApiKey] = {}
        self._cursor = 0
        self._lock = Lock()
        self._load()

    def _load(self) -> None:
        """从文件加载 keys"""
        if not self.storage_path.exists():
            return

        # 检查文件是否为空
        if self.storage_path.stat().st_size == 0:
            return

        with open(self.storage_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data.get("keys", []):
                key = ApiKey.from_dict(item)
                self._keys[key.id] = key

    def _save(self) -> None:
        """保存 keys 到文件"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"keys": [key.to_dict() for key in self._keys.values()]}
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add_key(self, key: str, name: str | None = None) -> ApiKey:
        """添加新 key"""
        with self._lock:
            key_id = str(uuid.uuid4())
            api_key = ApiKey(
                id=key_id,
                key=key,
                name=name or f"key-{key_id[:8]}",
            )
            self._keys[key_id] = api_key
            self._save()
            return api_key

    def get_key(self, key_id: str) -> ApiKey | None:
        """获取指定 key"""
        return self._keys.get(key_id)

    def list_keys(self) -> list[ApiKey]:
        """列出所有 keys"""
        return list(self._keys.values())

    def update_key(
        self,
        key_id: str,
        *,
        name: str | None = None,
        enabled: bool | None = None,
    ) -> ApiKey | None:
        """更新 key 属性"""
        with self._lock:
            key = self._keys.get(key_id)
            if not key:
                return None

            if name is not None:
                key.name = name
            if enabled is not None:
                key.enabled = enabled

            self._save()
            return key

    def delete_key(self, key_id: str) -> bool:
        """删除 key"""
        with self._lock:
            if key_id not in self._keys:
                return False
            del self._keys[key_id]
            self._save()
            return True

    def reset_key(self, key_id: str) -> ApiKey | None:
        """重置 key 状态（清除冷却）"""
        with self._lock:
            key = self._keys.get(key_id)
            if not key:
                return None
            key.clear_cooldown()
            self._save()
            return key

    def choose_key(self) -> ApiKey | None:
        """智能选择可用的 key（轮询 + 跳过不可用）"""
        with self._lock:
            if not self._keys:
                return None

            keys_list = list(self._keys.values())
            total = len(keys_list)

            for _ in range(total):
                key = keys_list[self._cursor]
                self._cursor = (self._cursor + 1) % total

                if key.is_available():
                    return key

            return None

    def mark_key_failure(
        self,
        key_id: str,
        status_code: int | None = None,
        cooldown_seconds: int = 60,
    ) -> None:
        """标记 key 失败并记录统计"""
        with self._lock:
            key = self._keys.get(key_id)
            if not key:
                return

            key.record_request(success=False, status_code=status_code)

            # 429 或 5xx 触发冷却
            if status_code == 429 or (status_code and 500 <= status_code < 600):
                key.mark_cooldown(cooldown_seconds)

            self._save()

    def mark_key_success(self, key_id: str) -> None:
        """标记 key 成功"""
        with self._lock:
            key = self._keys.get(key_id)
            if not key:
                return
            key.record_request(success=True)
            self._save()

    def get_stats(self) -> dict[str, Any]:
        """获取整体统计信息"""
        keys = list(self._keys.values())
        available = sum(1 for k in keys if k.is_available())
        enabled = sum(1 for k in keys if k.enabled)
        in_cooldown = sum(1 for k in keys if k.enabled and not k.is_available())

        total_requests = sum(k.stats.total_requests for k in keys)
        total_success = sum(k.stats.success_count for k in keys)
        total_429 = sum(k.stats.error_429_count for k in keys)
        total_5xx = sum(k.stats.error_5xx_count for k in keys)

        return {
            "total_keys": len(keys),
            "enabled_keys": enabled,
            "available_keys": available,
            "in_cooldown": in_cooldown,
            "total_requests": total_requests,
            "total_success": total_success,
            "total_429_errors": total_429,
            "total_5xx_errors": total_5xx,
        }
