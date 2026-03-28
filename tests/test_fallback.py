"""测试 fallback 机制"""

import pytest
from pathlib import Path
import tempfile

from exa_proxy.key_manager import KeyManager
from exa_proxy.executor import ProxyExecutor


@pytest.fixture
def temp_storage():
    """临时存储文件"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


def test_no_key_url_building(temp_storage):
    """测试无 key 的 URL 构造"""
    manager = KeyManager(temp_storage)
    executor = ProxyExecutor(manager, "https://mcp.exa.ai/mcp")

    # 测试不带 key 的 URL
    url = executor._build_url_without_key("/test")
    assert url == "https://mcp.exa.ai/mcp/test"
    assert "exaApiKey" not in url


def test_with_key_url_building(temp_storage):
    """测试带 key 的 URL 构造"""
    manager = KeyManager(temp_storage)
    executor = ProxyExecutor(manager, "https://mcp.exa.ai/mcp")

    # 测试带 key 的 URL
    url = executor._build_url_with_key("/test", "test_key_123")
    assert "https://mcp.exa.ai/mcp/test" in url
    assert "exaApiKey=test_key_123" in url


def test_has_any_keys_logic(temp_storage):
    """测试 has_any_keys 逻辑"""
    manager = KeyManager(temp_storage)

    # 初始没有 keys
    assert len(manager.list_keys()) == 0

    # 添加一个 key
    manager.add_key("test_key", "Test")
    assert len(manager.list_keys()) == 1

    # 禁用 key
    key = manager.list_keys()[0]
    manager.update_key(key.id, enabled=False)

    # 仍然有 keys（虽然不可用）
    assert len(manager.list_keys()) == 1

    # 但 choose_key 返回 None
    assert manager.choose_key() is None
