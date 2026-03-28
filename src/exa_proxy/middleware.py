from __future__ import annotations

from fastmcp.server.middleware import Middleware, MiddlewareContext


class ProxyLoggingMiddleware(Middleware):
    def __init__(self, include_payloads: bool = True):
        self.include_payloads = include_payloads

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool_name = context.message.name
        arguments = context.message.arguments

        if self.include_payloads:
            print(f"[exa-proxy] call tool={tool_name} args={arguments}")
        else:
            print(f"[exa-proxy] call tool={tool_name}")

        result = await call_next(context)
        print(f"[exa-proxy] result tool={tool_name}")
        return result
