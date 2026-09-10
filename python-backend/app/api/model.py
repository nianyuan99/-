"""
模型接口层
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.user import require_admin
from app.db.session import get_async_db
from app.schemas.conversation import ModelVO
from app.schemas.user import BaseResponse
from app.services.model_service import ModelService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model", tags=["模型接口"])


@router.get("/list", response_model=BaseResponse[List[ModelVO]], summary="查询模型列表")
async def list_models(
    keyword: Optional[str] = Query(None, description="按模型ID/名称模糊搜索"),
    is_china: Optional[int] = Query(None, alias="isChina", description="是否只看国内模型"),
    recommended: Optional[int] = Query(None, description="是否只看推荐模型"),
    limit: int = Query(500, ge=1, le=1000, description="最多返回条数"),
    db: AsyncSession = Depends(get_async_db),
):
    """查询模型列表（供前端模型选择器使用，国内模型优先返回）"""
    model_service = ModelService(db)
    models = await model_service.list_models(
        keyword=keyword, is_china=is_china, recommended=recommended, limit=limit
    )
    return BaseResponse(code=0, data=models, message="ok")


@router.post(
    "/sync",
    response_model=BaseResponse[int],
    summary="从OpenRouter同步模型列表（管理员）",
    dependencies=[Depends(require_admin)],
)
async def sync_models(db: AsyncSession = Depends(get_async_db)):
    """从 OpenRouter 同步模型列表（权限校验由 require_admin 依赖统一完成）"""
    model_service = ModelService(db)
    synced_count = await model_service.sync_models_from_openrouter()
    return BaseResponse(code=0, data=synced_count, message="ok")
