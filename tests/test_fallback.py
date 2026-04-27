"""测试 fallback 机制"""

import asyncio
from pathlib import Path
import tempfile

import httpx
import pytest

from exa_proxy.key_manager import KeyManager
from exa_proxy.executor import ExecutionAbortedError, ProxyExecutor


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


class _FakeResponse:
    def __init__(
        self, status_code: int, content: bytes = b"", headers: dict | None = None
    ):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "application/json"}


@pytest.mark.asyncio
async def test_no_key_mode_does_not_retry_non_retryable_4xx(monkeypatch, temp_storage):
    manager = KeyManager(temp_storage)
    executor = ProxyExecutor(manager, "https://mcp.exa.ai/mcp")

    attempts = 0
    sleep_calls = []

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            nonlocal attempts
            attempts += 1
            return _FakeResponse(405, b'{"error":"method not allowed"}')

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=30.0: _FakeAsyncClient())
    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    status, _, body = await executor.execute(
        method="GET", path="", headers={}, body=None
    )

    assert status == 405
    assert body == b'{"error":"method not allowed"}'
    assert attempts == 1
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_no_key_mode_uses_exponential_backoff_with_cap_and_three_extra_attempts(
    monkeypatch, temp_storage
):
    manager = KeyManager(temp_storage)
    executor = ProxyExecutor(manager, "https://mcp.exa.ai/mcp")

    attempts = 0
    sleep_calls = []

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            nonlocal attempts
            attempts += 1
            return _FakeResponse(429, b'{"error":"rate limited"}')

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=30.0: _FakeAsyncClient())
    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    status, _, body = await executor.execute(
        method="POST", path="", headers={}, body=b"{}"
    )

    assert status == 429
    assert body == b'{"error":"rate limited"}'
    assert attempts == 9
    assert sleep_calls == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 32.0, 32.0]


@pytest.mark.asyncio
async def test_all_keys_cooldown_then_no_key_fallback_returns_after_bounded_retries(
    monkeypatch, temp_storage
):
    manager = KeyManager(temp_storage)
    key = manager.add_key("test_key", "Test")
    manager.mark_key_failure(key.id, status_code=429, cooldown_seconds=300)
    executor = ProxyExecutor(manager, "https://mcp.exa.ai/mcp")

    attempts = 0
    sleep_calls = []

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            nonlocal attempts
            attempts += 1
            return _FakeResponse(503, b'{"error":"upstream unavailable"}')

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=30.0: _FakeAsyncClient())
    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    status, _, body = await executor.execute(
        method="POST", path="", headers={}, body=b"{}"
    )

    assert status == 503
    assert body == b'{"error":"upstream unavailable"}'
    assert attempts == 9
    assert sleep_calls == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 32.0, 32.0]


@pytest.mark.asyncio
async def test_execute_aborts_before_first_attempt_when_abort_requested(
    monkeypatch, temp_storage
):
    manager = KeyManager(temp_storage)
    executor = ProxyExecutor(manager, "https://mcp.exa.ai/mcp")

    attempts = 0

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            nonlocal attempts
            attempts += 1
            return _FakeResponse(200, b'{"ok":true}')

    async def _should_abort():
        return True

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=30.0: _FakeAsyncClient())

    with pytest.raises(ExecutionAbortedError):
        await executor.execute(
            method="POST",
            path="",
            headers={},
            body=b"{}",
            should_abort=_should_abort,
        )

    assert attempts == 0


@pytest.mark.asyncio
async def test_execute_aborts_before_backoff_sleep_when_abort_requested(
    monkeypatch, temp_storage
):
    manager = KeyManager(temp_storage)
    executor = ProxyExecutor(manager, "https://mcp.exa.ai/mcp")

    attempts = 0
    sleep_calls = []
    abort_checks = 0

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, content=None):
            nonlocal attempts
            attempts += 1
            return _FakeResponse(429, b'{"error":"rate limited"}')

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    async def _should_abort():
        nonlocal abort_checks
        abort_checks += 1
        return abort_checks >= 2

    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=30.0: _FakeAsyncClient())
    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    with pytest.raises(ExecutionAbortedError):
        await executor.execute(
            method="POST",
            path="",
            headers={},
            body=b"{}",
            should_abort=_should_abort,
        )

    assert attempts == 1
    assert sleep_calls == []
