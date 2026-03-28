"""Key 管理 REST API"""

from __future__ import annotations

from typing import Any

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from .key_manager import KeyManager


class AddKeyRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Exa API key")
    name: str | None = Field(None, description="友好名称")


class UpdateKeyRequest(BaseModel):
    name: str | None = Field(None, description="友好名称")
    enabled: bool | None = Field(None, description="是否启用")


class KeyResponse(BaseModel):
    id: str
    name: str
    key: str
    enabled: bool
    created_at: str
    cooldown_until: str | None
    stats: dict[str, Any]


class StatsResponse(BaseModel):
    total_keys: int
    enabled_keys: int
    available_keys: int
    in_cooldown: int
    total_requests: int
    total_success: int
    total_429_errors: int
    total_5xx_errors: int


def create_api_router(
    key_manager: KeyManager,
    auth_dependency: Callable | None = None,
) -> APIRouter:
    """创建 API 路由"""
    dependencies = [Depends(auth_dependency)] if auth_dependency else []
    router = APIRouter(prefix="/api/keys", tags=["keys"], dependencies=dependencies)

    @router.get("", response_model=list[KeyResponse])
    def list_keys() -> list[KeyResponse]:
        """列出所有 keys"""
        keys = key_manager.list_keys()
        return [KeyResponse(**key.to_dict()) for key in keys]

    @router.post("", response_model=KeyResponse, status_code=201)
    def add_key(req: AddKeyRequest) -> KeyResponse:
        """添加新 key"""
        key = key_manager.add_key(key=req.key, name=req.name)
        return KeyResponse(**key.to_dict())

    @router.get("/stats", response_model=StatsResponse)
    def get_stats() -> StatsResponse:
        """获取统计信息"""
        stats = key_manager.get_stats()
        return StatsResponse(**stats)

    @router.get("/{key_id}", response_model=KeyResponse)
    def get_key(key_id: str) -> KeyResponse:
        """获取单个 key"""
        key = key_manager.get_key(key_id)
        if not key:
            raise HTTPException(status_code=404, detail="Key not found")
        return KeyResponse(**key.to_dict())

    @router.put("/{key_id}", response_model=KeyResponse)
    def update_key(key_id: str, req: UpdateKeyRequest) -> KeyResponse:
        """更新 key"""
        key = key_manager.update_key(
            key_id,
            name=req.name,
            enabled=req.enabled,
        )
        if not key:
            raise HTTPException(status_code=404, detail="Key not found")
        return KeyResponse(**key.to_dict())

    @router.delete(
        "/{key_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
    )
    def delete_key(key_id: str) -> Response:
        """删除 key"""
        success = key_manager.delete_key(key_id)
        if not success:
            raise HTTPException(status_code=404, detail="Key not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/{key_id}/reset", response_model=KeyResponse)
    def reset_key(key_id: str) -> KeyResponse:
        """重置 key 状态（清除冷却）"""
        key = key_manager.reset_key(key_id)
        if not key:
            raise HTTPException(status_code=404, detail="Key not found")
        return KeyResponse(**key.to_dict())

    return router
