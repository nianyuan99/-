"""
用户评分接口层
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from app.schemas.conversation import RatingRequest, RatingVO
from app.schemas.user import BaseResponse
from app.services.rating_service import RatingService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rating", tags=["评分接口"])


@router.post("/add", response_model=BaseResponse[bool], summary="提交或修改评分")
async def add_rating(
    rating_request: RatingRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """用户对某一轮多模型回答进行评分（重复提交视为修改）"""
    login_user = await UserService.get_login_user(db, http_request)
    rating_service = RatingService(db)
    result = await rating_service.save_or_update_rating(
        conversation_id=rating_request.conversation_id,
        message_index=rating_request.message_index,
        user_id=login_user.id,
        rating_type=rating_request.rating_type,
        winner_model=rating_request.winner_model,
        loser_model=rating_request.loser_model,
        winner_variant_index=rating_request.winner_variant_index,
    )
    return BaseResponse(code=0, data=result, message="ok")


@router.get(
    "/{conversation_id}/list",
    response_model=BaseResponse[list[RatingVO]],
    summary="查询某个对话的全部评分",
)
async def list_ratings(
    conversation_id: str,
    http_request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """查询当前用户对某个对话的评分记录（前端加载历史会话时回填评分状态）"""
    login_user = await UserService.get_login_user(db, http_request)
    rating_service = RatingService(db)
    ratings = await rating_service.list_ratings(conversation_id, login_user.id)
    return BaseResponse(
        code=0,
        data=[RatingVO.model_validate(rating) for rating in ratings],
        message="ok",
    )
