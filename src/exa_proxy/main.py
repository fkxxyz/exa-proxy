"""主入口：FastAPI + 自定义 MCP 代理 + Key 管理 API"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn

from .api import create_api_router
from .executor import ProxyExecutor
from .key_manager import KeyManager

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)
security = HTTPBasic()


def create_admin_auth():
    username = os.getenv("EXA_PROXY_ADMIN_USERNAME", "admin")
    password = os.getenv("EXA_PROXY_ADMIN_PASSWORD", "admin")

    def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
        valid_username = secrets.compare_digest(credentials.username, username)
        valid_password = secrets.compare_digest(credentials.password, password)

        if not (valid_username and valid_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )

        return credentials.username

    return require_admin


def render_admin_page(stats: dict, keys: list[dict]) -> str:
    rows = "".join(
        (
            "<tr>"
            f"<td>{key['name']}</td>"
            f"<td>{key['id']}</td>"
            f"<td>{'yes' if key['enabled'] else 'no'}</td>"
            f"<td>{key['stats']['total_requests']}</td>"
            f"<td>{key['stats']['success_count']}</td>"
            f"<td>{key['stats']['error_429_count']}</td>"
            f"<td>{key['cooldown_until'] or '-'}</td>"
            "</tr>"
        )
        for key in keys
    )
    if not rows:
        rows = '<tr><td colspan="7">No keys configured</td></tr>'

    return f"""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <title>Exa Proxy Admin</title>
    <style>
      body {{ font-family: sans-serif; max-width: 1000px; margin: 40px auto; padding: 0 16px; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
      th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
      th {{ background: #f5f5f5; }}
      .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
      .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; background: #fafafa; }}
      code {{ background: #f2f2f2; padding: 2px 6px; border-radius: 4px; }}
    </style>
  </head>
  <body>
    <h1>Exa Proxy Admin</h1>
    <p>Protected by HTTP Basic Auth. MCP endpoint remains public at <code>/mcp</code>.</p>
    <div class=\"grid\">
      <div class=\"card\"><strong>Total keys</strong><div>{stats["total_keys"]}</div></div>
      <div class=\"card\"><strong>Enabled keys</strong><div>{stats["enabled_keys"]}</div></div>
      <div class=\"card\"><strong>Available keys</strong><div>{stats["available_keys"]}</div></div>
      <div class=\"card\"><strong>Total requests</strong><div>{stats["total_requests"]}</div></div>
    </div>
    <h2>Keys</h2>
    <table>
      <thead>
        <tr>
          <th>Name</th><th>ID</th><th>Enabled</th><th>Requests</th><th>Success</th><th>429</th><th>Cooldown</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </body>
</html>
"""


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    # 配置
    storage_path = Path(os.getenv("EXA_PROXY_STORAGE", "./data/keys.json"))
    upstream_url = os.getenv("EXA_PROXY_UPSTREAM", "https://mcp.exa.ai/mcp")
    host = os.getenv("EXA_PROXY_HOST", "127.0.0.1")
    port = int(os.getenv("EXA_PROXY_PORT", "8080"))

    # 初始化 key manager
    key_manager = KeyManager(storage_path)
    logger.info(f"Loaded {len(key_manager.list_keys())} keys from {storage_path}")

    # 初始化代理执行器
    executor = ProxyExecutor(key_manager, upstream_url)

    # 创建 FastAPI app
    app = FastAPI(title="Exa Proxy", version="0.2.0")

    admin_auth = create_admin_auth()

    # 挂载 key 管理 API
    api_router = create_api_router(key_manager, auth_dependency=admin_auth)
    app.include_router(api_router)

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page(_: str = Depends(admin_auth)) -> HTMLResponse:
        """简易管理页面"""
        html = render_admin_page(
            key_manager.get_stats(),
            [key.to_dict() for key in key_manager.list_keys()],
        )
        return HTMLResponse(content=html)

    @app.get("/health")
    def health_check():
        """健康检查"""
        stats = key_manager.get_stats()
        return {
            "status": "ok",
            "available_keys": stats["available_keys"],
            "total_keys": stats["total_keys"],
        }

    @app.api_route("/mcp", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy_mcp(request: Request) -> Response:
        """MCP 代理端点：智能选择 key 并转发请求"""
        method = request.method
        path = ""  # 空路径，因为 upstream_base_url 已经包含 /mcp
        headers = dict(request.headers)
        body = await request.body()

        # 移除 Host header 避免冲突
        headers.pop("host", None)

        try:
            status, resp_headers, resp_body = await executor.execute(
                method=method,
                path=path,
                headers=headers,
                body=body if body else None,
            )

            # 处理 SSE 响应
            content_type = resp_headers.get("content-type", "")
            if "text/event-stream" in content_type:

                async def stream_generator():
                    yield resp_body

                return StreamingResponse(
                    stream_generator(),
                    status_code=status,
                    headers=resp_headers,
                    media_type="text/event-stream",
                )

            # 普通响应
            return Response(
                content=resp_body,
                status_code=status,
                headers=resp_headers,
            )

        except Exception as e:
            logger.error(f"Proxy error: {e}")
            return Response(
                content=str(e),
                status_code=503,
            )

    return app


def main():
    """启动服务器"""
    host = os.getenv("EXA_PROXY_HOST", "127.0.0.1")
    port = int(os.getenv("EXA_PROXY_PORT", "8080"))

    app = create_app()
    logger.info(f"Starting Exa Proxy on {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
