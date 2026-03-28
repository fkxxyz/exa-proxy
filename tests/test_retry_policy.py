import pytest

from exa_proxy.config import UpstreamConfig
from exa_proxy.proxy_logic import RetryableProxyExecutor, UpstreamCallError


@pytest.mark.asyncio
async def test_executor_retries_with_next_upstream_after_rate_limit_error():
    upstreams = [
        UpstreamConfig(
            name="exa-a", url="https://mcp.exa.ai/mcp", authorization="Bearer a"
        ),
        UpstreamConfig(
            name="exa-b", url="https://mcp.exa.ai/mcp", authorization="Bearer b"
        ),
    ]

    calls = []

    async def invoke(upstream, payload):
        calls.append(upstream.name)
        if upstream.name == "exa-a":
            raise UpstreamCallError("rate limit", retryable=True)
        return {"ok": True, "upstream": upstream.name, "payload": payload}

    executor = RetryableProxyExecutor(upstreams=upstreams, invoke=invoke)
    result = await executor.execute(tool_name="exa_search", arguments={"query": "mcp"})

    assert calls == ["exa-a", "exa-b"]
    assert result["ok"] is True
    assert result["upstream"] == "exa-b"
