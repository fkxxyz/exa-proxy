from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import UpstreamConfig


@dataclass
class AttemptContext:
    tool_name: str | None
    arguments: dict


class UpstreamRouter:
    def __init__(self, upstreams: list[UpstreamConfig]):
        self._upstreams = upstreams
        self._cursor = 0
        self._cooldowns: dict[str, datetime] = {}

    def choose(self, context: AttemptContext) -> UpstreamConfig:
        if not self._upstreams:
            raise ValueError("No upstreams configured")

        now = datetime.now(timezone.utc)
        total = len(self._upstreams)

        for _ in range(total):
            upstream = self._upstreams[self._cursor]
            self._cursor = (self._cursor + 1) % total
            cooldown_until = self._cooldowns.get(upstream.name)

            if not upstream.enabled:
                continue
            if cooldown_until and cooldown_until > now:
                continue

            return upstream

        raise RuntimeError("No healthy upstream available")

    def mark_failure(self, upstream: UpstreamConfig) -> None:
        self._cooldowns[upstream.name] = datetime.now(timezone.utc) + timedelta(
            seconds=upstream.cooldown_seconds
        )

    def rewrite_arguments(self, upstream: UpstreamConfig, arguments: dict) -> dict:
        rewritten = dict(arguments)
        proxy_meta = dict(rewritten.get("_proxy", {}))
        proxy_meta["upstream"] = upstream.name
        rewritten["_proxy"] = proxy_meta
        return rewritten
