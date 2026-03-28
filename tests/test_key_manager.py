"""测试 key 管理功能"""

import pytest
from pathlib import Path
import tempfile
import json

from exa_proxy.key_manager import KeyManager, ApiKey


@pytest.fixture
def temp_storage():
    """临时存储文件"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


def test_add_and_list_keys(temp_storage):
    """测试添加和列出 keys"""
    manager = KeyManager(temp_storage)

    key1 = manager.add_key("test_key_1", "Key 1")
    key2 = manager.add_key("test_key_2", "Key 2")

    keys = manager.list_keys()
    assert len(keys) == 2
    assert key1.name == "Key 1"
    assert key2.name == "Key 2"


def test_key_persistence(temp_storage):
    """测试 key 持久化"""
    manager1 = KeyManager(temp_storage)
    manager1.add_key("persistent_key", "Persistent")

    # 重新加载
    manager2 = KeyManager(temp_storage)
    keys = manager2.list_keys()
    assert len(keys) == 1
    assert keys[0].key == "persistent_key"


def test_choose_key_round_robin(temp_storage):
    """测试轮询选择"""
    manager = KeyManager(temp_storage)
    key1 = manager.add_key("key1", "K1")
    key2 = manager.add_key("key2", "K2")

    chosen1 = manager.choose_key()
    chosen2 = manager.choose_key()
    chosen3 = manager.choose_key()

    assert chosen1.id == key1.id
    assert chosen2.id == key2.id
    assert chosen3.id == key1.id  # 回到第一个


def test_key_cooldown(temp_storage):
    """测试冷却机制"""
    manager = KeyManager(temp_storage)
    key1 = manager.add_key("key1", "K1")
    key2 = manager.add_key("key2", "K2")

    # 标记 key1 失败（429）
    manager.mark_key_failure(key1.id, status_code=429, cooldown_seconds=60)

    # 应该跳过 key1，选择 key2
    chosen = manager.choose_key()
    assert chosen.id == key2.id

    # 再次选择，仍然是 key2（key1 在冷却中）
    chosen = manager.choose_key()
    assert chosen.id == key2.id


def test_key_success_tracking(temp_storage):
    """测试成功统计"""
    manager = KeyManager(temp_storage)
    key = manager.add_key("test_key", "Test")

    manager.mark_key_success(key.id)
    manager.mark_key_success(key.id)

    updated_key = manager.get_key(key.id)
    assert updated_key.stats.total_requests == 2
    assert updated_key.stats.success_count == 2


def test_key_failure_tracking(temp_storage):
    """测试失败统计"""
    manager = KeyManager(temp_storage)
    key = manager.add_key("test_key", "Test")

    manager.mark_key_failure(key.id, status_code=429)
    manager.mark_key_failure(key.id, status_code=500)

    updated_key = manager.get_key(key.id)
    assert updated_key.stats.total_requests == 2
    assert updated_key.stats.error_429_count == 1
    assert updated_key.stats.error_5xx_count == 1


def test_update_key(temp_storage):
    """测试更新 key"""
    manager = KeyManager(temp_storage)
    key = manager.add_key("test_key", "Original")

    manager.update_key(key.id, name="Updated", enabled=False)

    updated = manager.get_key(key.id)
    assert updated.name == "Updated"
    assert updated.enabled is False


def test_delete_key(temp_storage):
    """测试删除 key"""
    manager = KeyManager(temp_storage)
    key = manager.add_key("test_key", "Test")

    success = manager.delete_key(key.id)
    assert success is True

    assert manager.get_key(key.id) is None


def test_reset_key(temp_storage):
    """测试重置 key"""
    manager = KeyManager(temp_storage)
    key = manager.add_key("test_key", "Test")

    # 标记失败并冷却
    manager.mark_key_failure(key.id, status_code=429)

    # 重置
    manager.reset_key(key.id)

    updated = manager.get_key(key.id)
    assert updated.cooldown_until is None


def test_get_stats(temp_storage):
    """测试统计信息"""
    manager = KeyManager(temp_storage)
    key1 = manager.add_key("key1", "K1")
    key2 = manager.add_key("key2", "K2")

    manager.mark_key_success(key1.id)
    manager.mark_key_failure(key2.id, status_code=429)

    stats = manager.get_stats()
    assert stats["total_keys"] == 2
    assert stats["enabled_keys"] == 2
    assert stats["total_requests"] == 2
    assert stats["total_success"] == 1
    assert stats["total_429_errors"] == 1
