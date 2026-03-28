from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Any

from .config import UpstreamConfig
from .router import AttemptContext, UpstreamRouter


@dataclass
class UpstreamCallError(Exception):
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class RetryableProxyExecutor:
    def __init__(
        self,
        upstreams: list[UpstreamConfig],
        invoke: Callable[[UpstreamConfig, dict[str, Any]], Awaitable[Any]],
    ):
        self.upstreams = upstreams
        self.invoke = invoke
        self.router = UpstreamRouter(upstreams)

    async def execute(self, tool_name: str, arguments: dict[str, Any]):
        enabled_upstreams = [
            upstream for upstream in self.upstreams if upstream.enabled
        ]
        if not enabled_upstreams:
            raise ValueError("No enabled upstreams configured")

        context = AttemptContext(tool_name=tool_name, arguments=arguments)
        last_error: Exception | None = None

        for _ in range(len(enabled_upstreams)):
            upstream = self.router.choose(context)
            rewritten_arguments = self.router.rewrite_arguments(upstream, arguments)

            try:
                return await self.invoke(upstream, rewritten_arguments)
            except UpstreamCallError as exc:
                last_error = exc
                if not exc.retryable:
                    raise
                self.router.mark_failure(upstream)

        if last_error:
            raise last_error

        raise RuntimeError("Proxy execution failed without explicit error")
