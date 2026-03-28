from __future__ import annotations

from typing import Any

import httpx

from .config import UpstreamConfig
from .proxy_logic import UpstreamCallError


class UpstreamHttpInvoker:
    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    async def invoke(
        self, upstream: UpstreamConfig, payload: dict[str, Any]
    ) -> dict[str, Any]:
        headers = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
        }
        if upstream.authorization:
            headers["authorization"] = upstream.authorization

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(upstream.url, json=payload, headers=headers)

        if response.status_code in {401, 403, 408, 409, 425, 429, 500, 502, 503, 504}:
            raise UpstreamCallError(
                f"Upstream request failed with status {response.status_code}",
                retryable=True,
            )
        if response.is_error:
            raise UpstreamCallError(
                f"Upstream request failed with status {response.status_code}",
                retryable=False,
            )

        try:
            return response.json()
        except Exception as exc:  # pragma: no cover
            raise UpstreamCallError(
                f"Invalid upstream JSON response: {exc}", retryable=False
            ) from exc
