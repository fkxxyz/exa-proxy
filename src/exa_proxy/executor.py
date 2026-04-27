"""智能代理执行器：多 key 轮询、自动重试、失败切换"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from .key_manager import KeyManager

logger = logging.getLogger(__name__)


class ExecutionAbortedError(Exception):
    """执行在继续重试前被上层主动中止。"""


class ProxyExecutor:
    """代理执行器：负责选择 key、构造请求、处理重试"""

    def __init__(
        self,
        key_manager: KeyManager,
        upstream_base_url: str,
        max_retries: int = 8,
        retry_wait_seconds: float = 1.0,
    ):
        self.key_manager = key_manager
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.max_retries = max_retries
        self.retry_wait_seconds = retry_wait_seconds

    def _get_retry_delay(self, retry_index: int) -> float:
        """返回指数退避延迟，最大 32 秒。"""
        return min(self.retry_wait_seconds * (2**retry_index), 32.0)

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        """判断状态码是否值得重试。"""
        return status_code == 429 or 500 <= status_code < 600

    async def _sleep_before_retry(self, retry_index: int, reason: str) -> None:
        delay = self._get_retry_delay(retry_index)
        logger.warning(f"{reason}, waiting {delay}s before retry...")
        await asyncio.sleep(delay)

    @staticmethod
    def _response_tuple(response: httpx.Response) -> tuple[int, dict[str, str], bytes]:
        return response.status_code, dict(response.headers), response.content

    async def _abort_if_needed(
        self,
        should_abort: Callable[[], Awaitable[bool]] | None,
        reason: str,
    ) -> None:
        if should_abort is None:
            return
        if await should_abort():
            logger.info(f"Aborting proxy execution: {reason}")
            raise ExecutionAbortedError(reason)

    def _build_url_with_key(self, path: str, api_key: str) -> str:
        """构造带 exaApiKey 参数的 URL"""
        base = f"{self.upstream_base_url}{path}"
        parsed = urlparse(base)
        query_params = parse_qs(parsed.query)
        query_params["exaApiKey"] = [api_key]
        new_query = urlencode(query_params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def _build_url_without_key(self, path: str) -> str:
        """构造不带 key 的 URL（使用免费额度）"""
        return f"{self.upstream_base_url}{path}"

    @staticmethod
    def _is_mcp_rate_limit_error(content: bytes) -> bool:
        """检测 MCP 响应体是否为限流错误。

        Exa MCP 在限流时返回 HTTP 200 + JSON body，其中 isError: true
        且文本包含 "rate limit" 相关关键词。
        """
        if not content:
            return False
        try:
            content_str = content.decode("utf-8")
        except UnicodeDecodeError:
            return False
        if '"isError": true' not in content_str and '"isError":true' not in content_str:
            return False
        if (
            "rate limit" not in content_str.lower()
            and "free mcp" not in content_str.lower()
        ):
            return False
        return True

    async def execute(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        should_abort: Callable[[], Awaitable[bool]] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        """
        执行代理请求，自动选择 key 并处理重试

        策略：
        1. 优先使用可用 key，失败时切换其他 key
        2. 所有 key 冷却时，fallback 到无 key 模式（免费额度）
        3. 仅对 429/5xx/网络异常执行指数退避重试
        4. 退避最大 32 秒，到达最大值后最多再尝试 3 次
        5. 超过重试预算后返回最后一次响应或抛出最后一次异常

        返回：(status_code, response_headers, response_body)
        """
        has_any_keys = len(self.key_manager.list_keys()) > 0
        last_exception: Exception | None = None

        for retry_index in range(self.max_retries + 1):
            await self._abort_if_needed(
                should_abort,
                "client disconnected before retry attempt",
            )

            # 选择可用的 key
            api_key_obj = self.key_manager.choose_key()

            # 如果没有可用 key，fallback 到无 key 模式
            if not api_key_obj:
                if has_any_keys:
                    logger.warning(
                        "All keys in cooldown, falling back to no-key mode (free tier)"
                    )
                else:
                    logger.debug("No keys configured, using no-key mode (free tier)")

                url = self._build_url_without_key(path)

                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.request(
                            method=method,
                            url=url,
                            headers=headers,
                            content=body,
                        )

                    status = response.status_code

                    # 检测响应体中是否包含限流错误（Exa MCP 返回 HTTP 200 + 错误消息）
                    if self._is_mcp_rate_limit_error(response.content):
                        if retry_index >= self.max_retries:
                            logger.error(
                                "Free tier rate limited (detected in response body), retry budget exhausted"
                            )
                            return self._response_tuple(response)
                        await self._abort_if_needed(
                            should_abort,
                            "client disconnected before no-key backoff",
                        )
                        await self._sleep_before_retry(
                            retry_index,
                            "Free tier rate limited (detected in response body)",
                        )
                        continue

                    # 成功
                    if 200 <= status < 300:
                        logger.info(
                            f"Request succeeded with no-key mode (status={status})"
                        )
                        return (
                            status,
                            dict(response.headers),
                            response.content,
                        )

                    # 429 / 5xx：有限指数退避重试
                    if self._is_retryable_status(status):
                        if retry_index >= self.max_retries:
                            logger.error(
                                f"No-key mode retry budget exhausted with status {status}"
                            )
                            return self._response_tuple(response)
                        await self._abort_if_needed(
                            should_abort,
                            "client disconnected before no-key backoff",
                        )
                        await self._sleep_before_retry(
                            retry_index,
                            f"No-key mode failed with retryable status {status}",
                        )
                        continue

                    # 其他错误：直接返回，不重试
                    logger.error(
                        f"No-key mode failed with non-retryable status {status}, not retrying"
                    )
                    return self._response_tuple(response)

                except Exception as e:
                    last_exception = e
                    if retry_index >= self.max_retries:
                        logger.error(f"No-key mode request failed after retries: {e}")
                        raise
                    await self._abort_if_needed(
                        should_abort,
                        "client disconnected before no-key retry after exception",
                    )
                    await self._sleep_before_retry(
                        retry_index,
                        f"No-key mode request failed: {e}",
                    )
                    continue

            # 有可用 key，使用 key 发送请求
            url = self._build_url_with_key(path, api_key_obj.key)

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        content=body,
                    )

                status = response.status_code
                content = response.content

                # 检测响应体中是否包含限流错误（Exa MCP 返回 HTTP 200 + 错误消息）
                if self._is_mcp_rate_limit_error(content):
                    logger.warning(
                        f"Key {api_key_obj.name} rate limited (detected in response body), "
                        f"marking cooldown and retrying..."
                    )
                    self.key_manager.mark_key_failure(
                        api_key_obj.id,
                        status_code=429,
                    )
                    if retry_index >= self.max_retries:
                        logger.error(
                            f"Retry budget exhausted after key {api_key_obj.name} rate limit"
                        )
                        return (
                            status,
                            dict(response.headers),
                            content,
                        )
                    continue

                # 成功
                if 200 <= status < 300:
                    self.key_manager.mark_key_success(api_key_obj.id)
                    logger.info(
                        f"Request succeeded with key {api_key_obj.name} (status={status})"
                    )
                    return (
                        status,
                        dict(response.headers),
                        content,
                    )

                # 429 或 5xx：标记失败，切换 key 重试
                if status == 429 or 500 <= status < 600:
                    logger.warning(
                        f"Key {api_key_obj.name} failed with status {status}, "
                        f"marking cooldown and retrying..."
                    )
                    self.key_manager.mark_key_failure(
                        api_key_obj.id,
                        status_code=status,
                    )
                    if retry_index >= self.max_retries:
                        logger.error(
                            f"Retry budget exhausted with key {api_key_obj.name} status {status}"
                        )
                        return (
                            status,
                            dict(response.headers),
                            response.content,
                        )
                    continue

                # 4xx（除 429）：客户端错误，不重试
                if 400 <= status < 500:
                    logger.error(
                        f"Client error {status} with key {api_key_obj.name}, not retrying"
                    )
                    self.key_manager.mark_key_failure(
                        api_key_obj.id,
                        status_code=status,
                    )
                    return (
                        status,
                        dict(response.headers),
                        response.content,
                    )

                # 其他状态码：记录并重试
                logger.warning(
                    f"Unexpected status {status} with key {api_key_obj.name}, retrying..."
                )
                self.key_manager.mark_key_failure(api_key_obj.id, status_code=status)
                if retry_index >= self.max_retries:
                    return (
                        status,
                        dict(response.headers),
                        response.content,
                    )

            except Exception as e:
                last_exception = e
                logger.error(
                    f"Request failed with key {api_key_obj.name}: {e}, retrying..."
                )
                self.key_manager.mark_key_failure(api_key_obj.id)
                continue

        if last_exception:
            raise last_exception

        raise RuntimeError("Proxy execution failed without a response")
