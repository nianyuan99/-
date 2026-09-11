"""
提示词模板管理服务
@author <a href="https://codefather.cn">编程导航学习圈</a>
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BusinessException, ErrorCode
from app.models.prompt_template import PromptTemplate
from app.models.prompt_template_interaction import (
    PromptTemplateFavorite,
    PromptTemplateLike,
)
from app.models.user import User
from app.schemas.prompt import PromptTemplateVO
from app.utils.prompt_template import PLACEHOLDER_PATTERN

logger = logging.getLogger(__name__)

STRATEGY_NAME_MAP = {
    "direct": "直接提问",
    "cot": "CoT (思维链)",
    "role_play": "角色扮演",
    "few_shot": "Few-shot (示例学习)",
}

QUALITY_LEVEL_MAP = [
    (90, "excellent"),
    (75, "good"),
    (60, "fair"),
]


def calculate_quality_level(score: Optional[int]) -> Optional[str]:
    """
    把 0-100 的质量评分映射成等级（功能扩展 4）

    前端按等级上色：excellent 绿 / good 蓝 / fair 橙 / poor 红。
    """
    if score is None:
        return None
    for threshold, level in QUALITY_LEVEL_MAP:
        if score >= threshold:
            return level
    return "poor"


def _parse_variables(raw: Optional[str]) -> List[str]:
    """解析 variables 列（JSON 数组文本），失败时退化为空列表"""
    if not raw or not str(raw).strip():
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("解析模板变量失败: %s", e)
        return []


def _dump_variables(variables: Optional[List[str]]) -> Optional[str]:
    """序列化变量列表；为空时返回 None"""
    return json.dumps(variables, ensure_ascii=False) if variables else None


def _to_vo(
    template: PromptTemplate,
    like_count: int = 0,
    favorite_count: int = 0,
    liked: bool = False,
    favorited: bool = False,
    author_name: Optional[str] = None,
) -> PromptTemplateVO:
    """
    实体转 VO

    变量列缺失时从 content 里现解析一遍，保证预设模板（SQL 里手写的 variables）
    与用户手输 content 两种情况都能正确渲染表单。
    """
    variables = _parse_variables(template.variables)
    if not variables and template.content:
        variables = [m.group(1) for m in PLACEHOLDER_PATTERN.finditer(template.content)]
        # 去重且保序
        seen: List[str] = []
        for name in variables:
            if name not in seen:
                seen.append(name)
        variables = seen

    return PromptTemplateVO(
        id=template.id,
        name=template.name,
        description=template.description,
        strategy=template.strategy,
        strategyName=STRATEGY_NAME_MAP.get(template.strategy, template.strategy),
        content=template.content,
        variables=variables,
        category=template.category,
        isPreset=(template.is_preset == 1),
        isPublic=(template.is_public == 1),
        usageCount=template.usage_count or 0,
        isActive=(template.is_active == 1),
        createTime=template.create_time.isoformat() if template.create_time else None,
        likeCount=like_count,
        favoriteCount=favorite_count,
        liked=liked,
        favorited=favorited,
        authorId=template.user_id,
        authorName=author_name,
    )


async def _load_interaction_counts(
    db: AsyncSession, template_ids: List[str], user_id: int
) -> Tuple[Dict[str, int], Dict[str, int], Set[str], Set[str]]:
    """
    批量查点赞/收藏数与当前用户的互动状态

    列表接口一次性批量查（而不是逐条查询），避免 N+1。
    """
    if not template_ids:
        return {}, {}, set(), set()

    like_rows = await db.execute(
        select(PromptTemplateLike.template_id, func.count(PromptTemplateLike.id))
        .where(
            PromptTemplateLike.template_id.in_(template_ids),
            PromptTemplateLike.is_delete == 0,
        )
        .group_by(PromptTemplateLike.template_id)
    )
    like_count_map = {row[0]: row[1] for row in like_rows.fetchall()}

    favorite_rows = await db.execute(
        select(
            PromptTemplateFavorite.template_id, func.count(PromptTemplateFavorite.id)
        )
        .where(
            PromptTemplateFavorite.template_id.in_(template_ids),
            PromptTemplateFavorite.is_delete == 0,
        )
        .group_by(PromptTemplateFavorite.template_id)
    )
    favorite_count_map = {row[0]: row[1] for row in favorite_rows.fetchall()}

    my_likes = await db.execute(
        select(PromptTemplateLike.template_id).where(
            PromptTemplateLike.template_id.in_(template_ids),
            PromptTemplateLike.user_id == user_id,
            PromptTemplateLike.is_delete == 0,
        )
    )
    liked_set = {row[0] for row in my_likes.fetchall()}

    my_favorites = await db.execute(
        select(PromptTemplateFavorite.template_id).where(
            PromptTemplateFavorite.template_id.in_(template_ids),
            PromptTemplateFavorite.user_id == user_id,
            PromptTemplateFavorite.is_delete == 0,
        )
    )
    favorited_set = {row[0] for row in my_favorites.fetchall()}

    return like_count_map, favorite_count_map, liked_set, favorited_set


async def _load_author_names(
    db: AsyncSession, templates: List[PromptTemplate]
) -> Dict[int, str]:
    """批量查模板创建者昵称（只查自定义模板的，预设模板没有作者）"""
    author_ids = {
        t.user_id for t in templates if t.user_id is not None and t.is_preset != 1
    }
    if not author_ids:
        return {}

    rows = await db.execute(
        select(User.id, User.user_name, User.user_account).where(
            User.id.in_(author_ids), User.is_delete == 0
        )
    )
    names: Dict[int, str] = {}
    for uid, user_name, user_account in rows.fetchall():
        names[uid] = user_name or user_account or f"用户{uid}"
    return names


async def _build_vos(
    db: AsyncSession, templates: List[PromptTemplate], user_id: int
) -> List[PromptTemplateVO]:
    """把一批模板实体组装成带互动数据的 VO"""
    ids = [t.id for t in templates]
    like_count_map, favorite_count_map, liked_set, favorited_set = (
        await _load_interaction_counts(db, ids, user_id)
    )
    author_names = await _load_author_names(db, templates)

    return [
        _to_vo(
            t,
            like_count=like_count_map.get(t.id, 0),
            favorite_count=favorite_count_map.get(t.id, 0),
            liked=t.id in liked_set,
            favorited=t.id in favorited_set,
            author_name=author_names.get(t.user_id) if t.user_id is not None else None,
        )
        for t in templates
    ]


class PromptTemplateService:

    @staticmethod
    async def list_templates(
        db: AsyncSession,
        user_id: int,
        strategy: Optional[str] = None,
    ) -> List[PromptTemplateVO]:
        """模板库列表：预设模板 + 当前用户的自定义模板 + 别人公开的模板"""
        conditions = [
            PromptTemplate.is_delete == 0,
            PromptTemplate.is_active == 1,
            or_(
                PromptTemplate.is_preset == 1,
                PromptTemplate.user_id == user_id,
                PromptTemplate.is_public == 1,
            ),
        ]
        if strategy and strategy.strip():
            conditions.append(PromptTemplate.strategy == strategy.strip())

        result = await db.execute(
            select(PromptTemplate)
            .where(and_(*conditions))
            .order_by(
                PromptTemplate.is_preset.desc(),
                PromptTemplate.usage_count.desc(),
                PromptTemplate.create_time.desc(),
            )
        )
        templates = list(result.scalars().all())
        return await _build_vos(db, templates, user_id)

    @staticmethod
    async def list_community_templates(
        db: AsyncSession,
        user_id: int,
        strategy: Optional[str] = None,
        sort_by: str = "latest",
    ) -> List[PromptTemplateVO]:
        """
        社区模板列表（功能扩展 2）：只看 isPublic=1 的自定义模板

        sort_by: latest（最新）/ hot（点赞最多）
        """
        conditions = [
            PromptTemplate.is_delete == 0,
            PromptTemplate.is_active == 1,
            PromptTemplate.is_public == 1,
            PromptTemplate.is_preset == 0,
        ]
        if strategy and strategy.strip():
            conditions.append(PromptTemplate.strategy == strategy.strip())

        stmt = select(PromptTemplate).where(and_(*conditions))
        if sort_by == "hot":
            stmt = stmt.order_by(
                PromptTemplate.usage_count.desc(), PromptTemplate.create_time.desc()
            )
        else:
            stmt = stmt.order_by(PromptTemplate.create_time.desc())

        result = await db.execute(stmt)
        templates = list(result.scalars().all())
        vos = await _build_vos(db, templates, user_id)

        # 点赞排序需要先拿到 counts，这里在内存里按点赞数二次排序（社区模板量级很小）
        if sort_by == "hot":
            vos.sort(key=lambda v: v.like_count, reverse=True)
        return vos

    @staticmethod
    async def list_favorite_templates(
        db: AsyncSession, user_id: int
    ) -> List[PromptTemplateVO]:
        """当前用户收藏的模板列表（功能扩展 2）"""
        fav_rows = await db.execute(
            select(PromptTemplateFavorite.template_id).where(
                PromptTemplateFavorite.user_id == user_id,
                PromptTemplateFavorite.is_delete == 0,
            )
        )
        fav_ids = [row[0] for row in fav_rows.fetchall()]
        if not fav_ids:
            return []

        result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.id.in_(fav_ids),
                PromptTemplate.is_delete == 0,
                PromptTemplate.is_active == 1,
            )
        )
        templates = list(result.scalars().all())
        vos = await _build_vos(db, templates, user_id)
        # 收藏列表按收藏时间倒序更自然
        order = {tid: idx for idx, tid in enumerate(fav_ids)}
        vos.sort(key=lambda v: order.get(v.id, 0))
        return vos

    @staticmethod
    async def get_template(db: AsyncSession, template_id: str) -> PromptTemplate:
        """按 ID 取模板实体，不存在则抛业务异常"""
        if not template_id or not template_id.strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "模板ID不能为空")
        result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.id == template_id.strip(),
                PromptTemplate.is_delete == 0,
            )
        )
        template = result.scalar_one_or_none()
        if not template:
            raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "模板不存在")
        return template

    @staticmethod
    async def get_template_vo(
        db: AsyncSession, template_id: str, user_id: int
    ) -> PromptTemplateVO:
        """按 ID 取模板 VO（含互动数据）"""
        template = await PromptTemplateService.get_template(db, template_id)
        vos = await _build_vos(db, [template], user_id)
        return vos[0]

    @staticmethod
    async def create_template(
        db: AsyncSession,
        name: str,
        strategy: str,
        content: str,
        user_id: int,
        description: Optional[str] = None,
        variables: Optional[List[str]] = None,
        category: Optional[str] = None,
        is_public: Optional[bool] = None,
    ) -> str:
        if not name or not name.strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "模板名称不能为空")
        if not strategy or not strategy.strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "策略类型不能为空")
        if not content or not content.strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "模板内容不能为空")

        template_id = str(uuid.uuid4())

        template = PromptTemplate(
            id=template_id,
            user_id=user_id,
            name=name.strip(),
            description=description.strip() if description and description.strip() else None,
            strategy=strategy.strip(),
            content=content.strip(),
            variables=_dump_variables(variables),
            category=category.strip() if category and category.strip() else None,
            is_preset=0,
            is_public=1 if is_public else 0,
            usage_count=0,
            is_active=1,
            is_delete=0,
        )
        db.add(template)
        await db.commit()
        return template_id

    @staticmethod
    async def update_template(
        db: AsyncSession,
        template_id: str,
        user_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        strategy: Optional[str] = None,
        content: Optional[str] = None,
        variables: Optional[List[str]] = None,
        category: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_public: Optional[bool] = None,
    ) -> bool:
        existing = await PromptTemplateService.get_template(db, template_id)
        if existing.is_preset == 1:
            raise BusinessException(ErrorCode.NO_AUTH_ERROR, "预设模板不能修改")
        if existing.user_id != user_id:
            raise BusinessException(ErrorCode.NO_AUTH_ERROR, "无权限操作")

        if name is not None:
            existing.name = name.strip()
        if description is not None:
            existing.description = (description.strip() or None)
        if strategy is not None:
            existing.strategy = strategy.strip()
        if content is not None:
            existing.content = content.strip()
        if variables is not None:
            existing.variables = _dump_variables(variables)
        if category is not None:
            existing.category = category.strip() if category.strip() else None
        if is_active is not None:
            existing.is_active = 1 if is_active else 0
        if is_public is not None:
            existing.is_public = 1 if is_public else 0
        existing.update_time = datetime.now()
        await db.commit()
        return True

    @staticmethod
    async def delete_template(
        db: AsyncSession,
        template_id: str,
        user_id: int,
    ) -> bool:
        template = await PromptTemplateService.get_template(db, template_id)
        if template.is_preset == 1:
            raise BusinessException(ErrorCode.NO_AUTH_ERROR, "预设模板不能删除")
        if template.user_id != user_id:
            raise BusinessException(ErrorCode.NO_AUTH_ERROR, "无权限操作")

        template.is_delete = 1
        await db.commit()
        return True

    @staticmethod
    async def increment_usage_count(db: AsyncSession, template_id: str) -> bool:
        if not template_id or not template_id.strip():
            return False

        result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.id == template_id.strip(),
                PromptTemplate.is_delete == 0,
            )
        )
        template = result.scalar_one_or_none()
        if not template:
            return False

        template.usage_count = (template.usage_count or 0) + 1
        template.update_time = datetime.now()
        await db.commit()
        return True

    # ==================== 功能扩展 1：模板变量自动替换 ====================

    @staticmethod
    async def fill_template(
        db: AsyncSession, template_id: str, variables: Dict[str, str]
    ) -> Tuple[str, List[str]]:
        """
        把用户填的变量值填进模板，返回 (填充后内容, 仍未填值的变量名)

        变量为空串时视为「没填」，保持占位符原样并计入未填列表，由前端提示。
        """
        from app.utils.prompt_template import fill_template_variables

        template = await PromptTemplateService.get_template(db, template_id)

        expected = _parse_variables(template.variables)
        if not expected:
            expected = [m.group(1) for m in PLACEHOLDER_PATTERN.finditer(template.content)]

        # 只接受模板里真实存在的变量，忽略前端传来的多余键
        usable = {
            key: value
            for key, value in (variables or {}).items()
            if key in expected and value is not None and str(value).strip() != ""
        }

        filled = fill_template_variables(template.content, usable)
        unfilled = [name for name in expected if name not in usable]
        return filled, unfilled

    # ==================== 功能扩展 2：点赞 / 收藏 ====================

    @staticmethod
    async def toggle_like(db: AsyncSession, template_id: str, user_id: int) -> bool:
        """
        点赞 / 取消点赞，返回操作后是否处于已点赞状态
        """
        await PromptTemplateService.get_template(db, template_id)

        result = await db.execute(
            select(PromptTemplateLike).where(
                PromptTemplateLike.template_id == template_id,
                PromptTemplateLike.user_id == user_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # 已点过 → 取反（逻辑删除字段来回翻转，保留唯一一行）
            existing.is_delete = 0 if existing.is_delete == 1 else 1
            await db.commit()
            return existing.is_delete == 0

        db.add(
            PromptTemplateLike(
                id=str(uuid.uuid4()),
                template_id=template_id,
                user_id=user_id,
                is_delete=0,
            )
        )
        await db.commit()
        return True

    @staticmethod
    async def toggle_favorite(db: AsyncSession, template_id: str, user_id: int) -> bool:
        """
        收藏 / 取消收藏，返回操作后是否处于已收藏状态
        """
        await PromptTemplateService.get_template(db, template_id)

        result = await db.execute(
            select(PromptTemplateFavorite).where(
                PromptTemplateFavorite.template_id == template_id,
                PromptTemplateFavorite.user_id == user_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.is_delete = 0 if existing.is_delete == 1 else 1
            await db.commit()
            return existing.is_delete == 0

        db.add(
            PromptTemplateFavorite(
                id=str(uuid.uuid4()),
                template_id=template_id,
                user_id=user_id,
                is_delete=0,
            )
        )
        await db.commit()
        return True
