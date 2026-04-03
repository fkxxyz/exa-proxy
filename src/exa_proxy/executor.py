"""智能代理执行器：多 key 轮询、自动重试、失败切换"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from .key_manager import KeyManager

logger = logging.getLogger(__name__)


class ProxyExecutor:
    """代理执行器：负责选择 key、构造请求、处理重试"""

    def __init__(
        self,
        key_manager: KeyManager,
        upstream_base_url: str,
        max_retries: int = 5,
        retry_wait_seconds: float = 1.0,
    ):
        self.key_manager = key_manager
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.max_retries = max_retries
        self.retry_wait_seconds = retry_wait_seconds

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
    ) -> tuple[int, dict[str, str], bytes]:
        """
        执行代理请求，自动选择 key 并处理重试

        策略：
        1. 优先使用可用 key，失败时切换其他 key
        2. 所有 key 冷却时，fallback 到无 key 模式（免费额度）
        3. 无 key 也冷却时，等待后重新尝试（优先尝试 key）
        4. 无限重试直到成功，确保所有请求都能完成

        返回：(status_code, response_headers, response_body)
        """
        has_any_keys = len(self.key_manager.list_keys()) > 0

        while True:  # 无限重试直到成功
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
                        logger.warning(
                            "Free tier rate limited (detected in response body), "
                            f"waiting {self.retry_wait_seconds}s before retry..."
                        )
                        await asyncio.sleep(self.retry_wait_seconds)
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

                    # 429：免费额度耗尽，等待后重试（优先尝试 key）
                    if status == 429:
                        logger.warning(
                            f"Free tier rate limited (429), waiting {self.retry_wait_seconds}s before retry..."
                        )
                        await asyncio.sleep(self.retry_wait_seconds)
                        continue

                    # 其他错误，等待后重试
                    logger.warning(
                        f"No-key mode failed with status {status}, retrying..."
                    )
                    await asyncio.sleep(self.retry_wait_seconds)
                    continue

                except Exception as e:
                    logger.warning(f"No-key mode request failed: {e}, retrying...")
                    await asyncio.sleep(self.retry_wait_seconds)
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

            except Exception as e:
                logger.error(
                    f"Request failed with key {api_key_obj.name}: {e}, retrying..."
                )
                self.key_manager.mark_key_failure(api_key_obj.id)
                continue
