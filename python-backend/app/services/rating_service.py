"""
用户评分服务层
"""

import logging
import re
import uuid
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import RATING_TYPE_VARIANT_PREFIX, RATING_TYPES
from app.exceptions import BusinessException, ErrorCode
from app.models.rating import Rating

logger = logging.getLogger(__name__)

# Prompt Lab 的变体评分：rating_type 形如 variant_0 / variant_1 ...
_VARIANT_RATING_PATTERN = re.compile(rf"^{RATING_TYPE_VARIANT_PREFIX}(\d+)$")


def _is_valid_rating_type(rating_type: str) -> bool:
    """Side-by-Side 走 RATING_TYPES 白名单，Prompt Lab 的 variant_N 按正则放行"""
    return rating_type in RATING_TYPES or bool(_VARIANT_RATING_PATTERN.match(rating_type))


def _parse_variant_index(rating_type: str) -> Optional[int]:
    """从 variant_N 里解出变体序号，非变体评分返回 None"""
    matched = _VARIANT_RATING_PATTERN.match(rating_type)
    return int(matched.group(1)) if matched else None


class RatingService:
    """评分服务类"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_or_update_rating(
        self,
        conversation_id: str,
        message_index: int,
        user_id: int,
        rating_type: str,
        winner_model: Optional[str] = None,
        loser_model: Optional[str] = None,
        winner_variant_index: Optional[int] = None,
    ) -> bool:
        """
        保存或更新评分（有则更新、无则新增）

        同一用户对同一轮消息只保留一条评分记录，
        重复提交视为修改，避免评分列表出现重复数据。

        Args:
            conversation_id: 对话ID
            message_index: 消息序号
            user_id: 用户ID
            rating_type: 评分类型: model_better/tie/both_bad；Prompt Lab 为 variant_0、variant_1...
            winner_model: 获胜模型
            loser_model: 失败模型
            winner_variant_index: 获胜变体索引（Prompt Lab 专用）

        Returns:
            是否保存成功
        """
        if not conversation_id:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "对话ID不能为空")
        if not _is_valid_rating_type(rating_type):
            raise BusinessException(ErrorCode.PARAMS_ERROR, "评分类型不合法")

        # rating_type 已经带了序号时以它为准，避免前端漏传 winnerVariantIndex
        # 导致「评的是变体 2、库里记的是空」这种不一致数据
        parsed_variant_index = _parse_variant_index(rating_type)
        if parsed_variant_index is not None:
            winner_variant_index = parsed_variant_index

        result = await self.db.execute(
            select(Rating).where(
                and_(
                    Rating.conversation_id == conversation_id,
                    Rating.message_index == message_index,
                    Rating.user_id == user_id,
                    Rating.is_delete == 0,
                )
            )
        )
        existing_rating = result.scalar_one_or_none()

        if existing_rating:
            existing_rating.rating_type = rating_type
            existing_rating.winner_model = winner_model
            existing_rating.loser_model = loser_model
            existing_rating.winner_variant_index = winner_variant_index
        else:
            self.db.add(
                Rating(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    message_index=message_index,
                    user_id=user_id,
                    rating_type=rating_type,
                    winner_variant_index=winner_variant_index,
                    winner_model=winner_model,
                    loser_model=loser_model,
                    is_delete=0,
                )
            )

        await self.db.commit()
        return True

    async def get_rating(
        self, conversation_id: str, message_index: int, user_id: int
    ) -> Optional[Rating]:
        """查询用户对某一轮消息的评分"""
        result = await self.db.execute(
            select(Rating).where(
                and_(
                    Rating.conversation_id == conversation_id,
                    Rating.message_index == message_index,
                    Rating.user_id == user_id,
                    Rating.is_delete == 0,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_ratings(self, conversation_id: str, user_id: int) -> List[Rating]:
        """
        查询某个对话下当前用户的全部评分

        前端「点击历史会话」时需要回填每一轮的评分状态（评分按钮显示成已选中），
        因此按 messageIndex 升序一次性返回。
        """
        result = await self.db.execute(
            select(Rating)
            .where(
                and_(
                    Rating.conversation_id == conversation_id,
                    Rating.user_id == user_id,
                    Rating.is_delete == 0,
                )
            )
            .order_by(Rating.message_index.asc())
        )
        return list(result.scalars().all())
