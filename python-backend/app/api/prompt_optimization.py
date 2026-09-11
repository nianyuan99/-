"""
提示词优化接口层
"""

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import get_async_redis
from app.db.session import get_async_db
from app.schemas.prompt import PromptOptimizationRequest
from app.schemas.user import BaseResponse
from app.services.prompt_optimization_service import (
    PromptOptimizationService,
    delete_optimization_history,
    list_optimization_history,
)
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompt/optimization", tags=["提示词优化接口"])

_optimization_service: PromptOptimizationService | None = None


def get_optimization_service() -> PromptOptimizationService:
    """进程内单例：内部持有 AsyncOpenAI 客户端，不需要每次请求都创建"""
    global _optimization_service
    if _optimization_service is None:
        _optimization_service = PromptOptimizationService()
    return _optimization_service


def _get_redis(_http_request: Request):
    """获取异步 Redis 客户端"""
    return get_async_redis()


@router.post("/analyze", response_model=BaseResponse[dict], summary="分析并优化提示词")
async def optimize_prompt(
    request_body: PromptOptimizationRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    从 5 个维度分析提示词，返回问题清单、优化后的提示词、改进说明与质量评分

    每次调用都会自动保存一条优化历史（功能扩展 3）。
    """
    user = await UserService.get_login_user(db, request)
    service = get_optimization_service()
    result = await service.optimize_prompt(
        original_prompt=request_body.original_prompt,
        ai_response=request_body.ai_response,
        evaluation_model=request_body.evaluation_model,
        user_id=user.id,
        db=db,
        redis_client=_get_redis(request),
    )
    return BaseResponse(code=0, data=result.model_dump(by_alias=True), message="ok")


@router.get("/history", response_model=BaseResponse[list], summary="获取优化历史")
async def get_optimization_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="返回条数"),
    db: AsyncSession = Depends(get_async_db),
):
    """功能扩展 3：回顾之前的优化建议，按时间倒序"""
    user = await UserService.get_login_user(db, request)
    records = await list_optimization_history(db, user.id, limit)
    return BaseResponse(
        code=0, data=[r.model_dump(by_alias=True) for r in records], message="ok"
    )


@router.post("/history/delete", response_model=BaseResponse[bool], summary="删除优化历史")
async def remove_optimization_history(
    request: Request,
    historyId: str = Query(..., description="记录ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """删除一条优化历史（逻辑删除，仅限本人）"""
    user = await UserService.get_login_user(db, request)
    result = await delete_optimization_history(db, historyId, user.id)
    return BaseResponse(code=0, data=result, message="ok")
