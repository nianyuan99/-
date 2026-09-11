"""
场景管理服务层

负责测试场景与其提示词的增删改查。权限规则与教程一致：
- 预设场景（isPreset=1）所有人可见，但任何人都不能修改或删除；
- 自定义场景仅创建者可见、可编辑；
- 提示词同属场景，权限跟随场景。
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import PROMPT_DIFFICULTIES
from app.exceptions import BusinessException, ErrorCode
from app.models.scene import Scene
from app.models.scene_prompt import ScenePrompt
from app.models.test_task import TestTask
from app.schemas.scene import SceneDetailVO, ScenePromptVO, SceneQueryRequest, SceneVO

logger = logging.getLogger(__name__)


class SceneService:
    """场景服务类"""

    # ============ 场景 CRUD ============

    @staticmethod
    async def create_scene(db: AsyncSession, scene_data: dict, user_id: int) -> str:
        """创建自定义场景，返回场景 ID"""
        name = (scene_data.get("name") or "").strip()
        if not name:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "场景名称不能为空")
        if len(name) > 100:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "场景名称过长")

        # 同一用户下场景名称不允许重复，避免列表里出现难以区分的重名场景
        existed = await db.execute(
            select(Scene).where(
                Scene.user_id == user_id,
                Scene.name == name,
                Scene.is_delete == 0,
            )
        )
        if existed.scalar_one_or_none():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "已存在同名场景")

        scene_id = str(uuid.uuid4())
        scene = Scene(
            id=scene_id,
            user_id=user_id,
            name=name,
            description=scene_data.get("description"),
            category=(scene_data.get("category") or None),
            is_preset=0,
            is_active=1,
            is_delete=0,
        )
        db.add(scene)
        await db.commit()
        logger.info("创建场景成功: sceneId=%s, userId=%s", scene_id, user_id)
        return scene_id

    @staticmethod
    async def update_scene(db: AsyncSession, scene_data: dict, user_id: int) -> bool:
        """更新自定义场景（预设场景不可修改）"""
        scene = await SceneService._get_editable_scene(db, scene_data.get("id"), user_id)

        name = scene_data.get("name")
        if name is not None:
            name = str(name).strip()
            if not name:
                raise BusinessException(ErrorCode.PARAMS_ERROR, "场景名称不能为空")
            if len(name) > 100:
                raise BusinessException(ErrorCode.PARAMS_ERROR, "场景名称过长")
            # 改名时同样要保证同一用户下不重名（排除自己）
            existed = await db.execute(
                select(Scene).where(
                    Scene.user_id == user_id,
                    Scene.name == name,
                    Scene.id != scene.id,
                    Scene.is_delete == 0,
                )
            )
            if existed.scalar_one_or_none():
                raise BusinessException(ErrorCode.PARAMS_ERROR, "已存在同名场景")
            scene.name = name

        if "description" in scene_data:
            scene.description = scene_data.get("description")
        if "category" in scene_data:
            scene.category = scene_data.get("category") or None

        await db.commit()
        return True

    @staticmethod
    async def delete_scene(db: AsyncSession, scene_id: str, user_id: int) -> bool:
        """删除自定义场景（逻辑删除，同时逻辑删除其下提示词）"""
        scene = await SceneService._get_editable_scene(db, scene_id, user_id)

        # 已经有测试任务在引用该场景时不允许删除，否则历史任务会指向不存在的场景
        task_count = await db.execute(
            select(func.count())
            .select_from(TestTask)
            .where(TestTask.scene_id == scene.id, TestTask.is_delete == 0)
        )
        if (task_count.scalar() or 0) > 0:
            raise BusinessException(ErrorCode.OPERATION_ERROR, "该场景已有测试任务，无法删除")

        scene.is_delete = 1
        prompts = await db.execute(
            select(ScenePrompt).where(ScenePrompt.scene_id == scene.id, ScenePrompt.is_delete == 0)
        )
        for prompt in prompts.scalars().all():
            prompt.is_delete = 1

        await db.commit()
        logger.info("删除场景成功: sceneId=%s, userId=%s", scene.id, user_id)
        return True

    @staticmethod
    async def get_scene_detail(db: AsyncSession, scene_id: str, user_id: int) -> SceneDetailVO:
        """获取场景详情（含提示词列表）"""
        if not scene_id or not str(scene_id).strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "场景ID不能为空")

        scene = await SceneService._get_visible_scene(db, scene_id.strip(), user_id)
        prompts = await SceneService.list_scene_prompts(db, scene.id, user_id)

        detail = SceneDetailVO.model_validate(scene)
        detail.prompt_count = len(prompts)
        detail.prompts = prompts
        return detail

    @staticmethod
    async def list_scenes_by_page(
        db: AsyncSession, query: SceneQueryRequest, user_id: int
    ) -> Dict[str, Any]:
        """
        分页查询场景列表

        用户能看到所有预设场景以及自己创建的自定义场景，
        等价于 SQL 的 WHERE (userId = ? OR isPreset = 1)。
        """
        conditions = [
            Scene.is_delete == 0,
            or_(Scene.user_id == user_id, Scene.is_preset == 1),
        ]
        if query.name:
            conditions.append(Scene.name.like(f"%{query.name}%"))
        if query.category:
            conditions.append(Scene.category == query.category)
        if query.is_preset is not None:
            conditions.append(Scene.is_preset == (1 if query.is_preset else 0))

        count_result = await db.execute(select(func.count()).select_from(Scene).where(*conditions))
        total = count_result.scalar() or 0

        # 预设场景排前面，其余按创建时间倒序
        query_stmt = (
            select(Scene)
            .where(*conditions)
            .order_by(Scene.is_preset.desc(), Scene.create_time.desc())
            .offset((query.current - 1) * query.page_size)
            .limit(query.page_size)
        )
        scenes = (await db.execute(query_stmt)).scalars().all()

        prompt_counts = await SceneService._count_prompts_by_scene(db, [scene.id for scene in scenes])
        records: List[SceneVO] = []
        for scene in scenes:
            vo = SceneVO.model_validate(scene)
            vo.prompt_count = prompt_counts.get(scene.id, 0)
            records.append(vo)

        return {
            "records": [vo.model_dump(by_alias=True, mode="json") for vo in records],
            "total": total,
            "current": query.current,
            "pageSize": query.page_size,
        }

    @staticmethod
    async def list_categories(db: AsyncSession, user_id: int) -> List[str]:
        """查询当前用户可见的场景分类（供前端筛选下拉框使用）"""
        conditions = [
            Scene.is_delete == 0,
            Scene.category.isnot(None),
            or_(Scene.user_id == user_id, Scene.is_preset == 1),
        ]
        result = await db.execute(select(Scene.category).where(*conditions).distinct())
        return sorted({row[0] for row in result.all() if row[0]})

    # ============ 场景提示词 CRUD ============

    @staticmethod
    async def add_scene_prompt(db: AsyncSession, request_data: dict, user_id: int) -> str:
        """向自定义场景添加提示词，promptIndex 由服务端自动计算"""
        scene_id = (request_data.get("scene_id") or request_data.get("sceneId") or "").strip()
        if not scene_id:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "场景ID不能为空")

        title = (request_data.get("title") or "").strip()
        content = (request_data.get("content") or "").strip()
        if not title:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "提示词标题不能为空")
        if not content:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "提示词内容不能为空")
        if len(title) > 200:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "提示词标题过长")

        difficulty = SceneService._validate_difficulty(request_data.get("difficulty"))

        scene = await SceneService._get_editable_scene(db, scene_id, user_id)

        # 自动计算序号：当前场景下未删除提示词的数量
        count_result = await db.execute(
            select(func.count())
            .select_from(ScenePrompt)
            .where(ScenePrompt.scene_id == scene.id, ScenePrompt.is_delete == 0)
        )
        prompt_index = count_result.scalar() or 0

        prompt_id = str(uuid.uuid4())
        db.add(
            ScenePrompt(
                id=prompt_id,
                scene_id=scene.id,
                user_id=user_id,
                prompt_index=prompt_index,
                title=title,
                content=content,
                difficulty=difficulty,
                tags=request_data.get("tags"),
                expected_output=request_data.get("expected_output") or request_data.get("expectedOutput"),
                is_delete=0,
            )
        )
        await db.commit()
        logger.info("添加提示词成功: sceneId=%s, promptId=%s", scene.id, prompt_id)
        return prompt_id

    @staticmethod
    async def update_scene_prompt(db: AsyncSession, request_data: dict, user_id: int) -> bool:
        """更新提示词（仅自定义场景下的提示词可改）"""
        prompt = await SceneService._get_editable_prompt(db, request_data.get("id"), user_id)

        if "title" in request_data and request_data.get("title") is not None:
            title = str(request_data["title"]).strip()
            if not title:
                raise BusinessException(ErrorCode.PARAMS_ERROR, "提示词标题不能为空")
            if len(title) > 200:
                raise BusinessException(ErrorCode.PARAMS_ERROR, "提示词标题过长")
            prompt.title = title

        if "content" in request_data and request_data.get("content") is not None:
            content = str(request_data["content"]).strip()
            if not content:
                raise BusinessException(ErrorCode.PARAMS_ERROR, "提示词内容不能为空")
            prompt.content = content

        if "difficulty" in request_data:
            prompt.difficulty = SceneService._validate_difficulty(request_data.get("difficulty"))

        if "tags" in request_data:
            prompt.tags = request_data.get("tags")

        if "expected_output" in request_data or "expectedOutput" in request_data:
            prompt.expected_output = request_data.get("expected_output") or request_data.get(
                "expectedOutput"
            )

        await db.commit()
        return True

    @staticmethod
    async def delete_scene_prompt(db: AsyncSession, prompt_id: str, user_id: int) -> bool:
        """删除提示词（逻辑删除），并重排剩余提示词的序号"""
        prompt = await SceneService._get_editable_prompt(db, prompt_id, user_id)
        prompt.is_delete = 1

        # 重排序号，保证 promptIndex 始终连续（批量测试按序号顺序执行）
        remained = await db.execute(
            select(ScenePrompt)
            .where(
                ScenePrompt.scene_id == prompt.scene_id,
                ScenePrompt.is_delete == 0,
                ScenePrompt.id != prompt.id,
            )
            .order_by(ScenePrompt.prompt_index.asc())
        )
        for index, item in enumerate(remained.scalars().all()):
            item.prompt_index = index

        await db.commit()
        return True

    @staticmethod
    async def list_scene_prompts(
        db: AsyncSession, scene_id: str, user_id: int
    ) -> List[ScenePromptVO]:
        """查询场景下的提示词列表（按 promptIndex 升序）"""
        await SceneService._get_visible_scene(db, scene_id, user_id)
        result = await db.execute(
            select(ScenePrompt)
            .where(ScenePrompt.scene_id == scene_id, ScenePrompt.is_delete == 0)
            .order_by(ScenePrompt.prompt_index.asc())
        )
        return [ScenePromptVO.model_validate(prompt) for prompt in result.scalars().all()]

    # ============ 内部方法 ============

    @staticmethod
    async def _get_visible_scene(db: AsyncSession, scene_id: str, user_id: int) -> Scene:
        """查询用户可见的场景（预设场景或自己创建的）"""
        result = await db.execute(
            select(Scene).where(
                Scene.id == scene_id,
                Scene.is_delete == 0,
                or_(Scene.user_id == user_id, Scene.is_preset == 1),
            )
        )
        scene = result.scalar_one_or_none()
        if not scene:
            raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "场景不存在")
        return scene

    @staticmethod
    async def _get_editable_scene(db: AsyncSession, scene_id: Optional[str], user_id: int) -> Scene:
        """查询用户可编辑的场景：必须是自己的自定义场景"""
        if not scene_id or not str(scene_id).strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "场景ID不能为空")

        result = await db.execute(
            select(Scene).where(Scene.id == str(scene_id).strip(), Scene.is_delete == 0)
        )
        scene = result.scalar_one_or_none()
        if not scene:
            raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "场景不存在")
        if scene.is_preset == 1:
            raise BusinessException(ErrorCode.NO_AUTH_ERROR, "预设场景不可修改")
        if scene.user_id != user_id:
            raise BusinessException(ErrorCode.NO_AUTH_ERROR, "无权操作该场景")
        return scene

    @staticmethod
    async def _get_editable_prompt(db: AsyncSession, prompt_id: Optional[str], user_id: int) -> ScenePrompt:
        """查询用户可编辑的提示词：所属场景必须是自己的自定义场景"""
        if not prompt_id or not str(prompt_id).strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "提示词ID不能为空")

        result = await db.execute(
            select(ScenePrompt).where(
                ScenePrompt.id == str(prompt_id).strip(), ScenePrompt.is_delete == 0
            )
        )
        prompt = result.scalar_one_or_none()
        if not prompt:
            raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "提示词不存在")

        scene = await SceneService._get_visible_scene(db, prompt.scene_id, user_id)
        if scene.is_preset == 1:
            raise BusinessException(ErrorCode.NO_AUTH_ERROR, "预设场景的提示词不可修改")
        if scene.user_id != user_id:
            raise BusinessException(ErrorCode.NO_AUTH_ERROR, "无权操作该提示词")
        return prompt

    @staticmethod
    def _validate_difficulty(difficulty: Optional[str]) -> Optional[str]:
        """校验难度取值，空值表示不限难度"""
        if difficulty is None or str(difficulty).strip() == "":
            return None
        value = str(difficulty).strip().lower()
        if value not in PROMPT_DIFFICULTIES:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "难度取值非法")
        return value

    @staticmethod
    async def _count_prompts_by_scene(db: AsyncSession, scene_ids: List[str]) -> Dict[str, int]:
        """批量统计各场景的提示词数量，避免列表查询里逐条 count"""
        if not scene_ids:
            return {}
        result = await db.execute(
            select(ScenePrompt.scene_id, func.count())
            .where(ScenePrompt.scene_id.in_(scene_ids), ScenePrompt.is_delete == 0)
            .group_by(ScenePrompt.scene_id)
        )
        return {row[0]: row[1] for row in result.all()}

    @staticmethod
    async def list_available_scenes(db: AsyncSession, user_id: int) -> List[SceneVO]:
        """查询用户可用于批量测试的场景（启用中的预设场景 + 自己的自定义场景）"""
        result = await db.execute(
            select(Scene)
            .where(
                Scene.is_delete == 0,
                Scene.is_active == 1,
                or_(Scene.user_id == user_id, Scene.is_preset == 1),
            )
            .order_by(Scene.is_preset.desc(), Scene.create_time.desc())
        )
        scenes = result.scalars().all()
        prompt_counts = await SceneService._count_prompts_by_scene(db, [scene.id for scene in scenes])

        scenes_vo: List[SceneVO] = []
        for scene in scenes:
            vo = SceneVO.model_validate(scene)
            vo.prompt_count = prompt_counts.get(scene.id, 0)
            scenes_vo.append(vo)
        return scenes_vo

    @staticmethod
    async def get_scene_prompts_for_test(
        db: AsyncSession, scene_id: str, user_id: int
    ) -> List[ScenePrompt]:
        """
        查询批量测试要用的提示词（返回 ORM 对象，worker 需要 title/content/id）

        没有提示词的场景直接拒绝，避免创建出 0 个子任务的任务。
        """
        scene = await SceneService._get_visible_scene(db, scene_id, user_id)
        if scene.is_active != 1:
            raise BusinessException(ErrorCode.OPERATION_ERROR, "该场景已禁用")

        result = await db.execute(
            select(ScenePrompt)
            .where(ScenePrompt.scene_id == scene.id, ScenePrompt.is_delete == 0)
            .order_by(ScenePrompt.prompt_index.asc())
        )
        prompts = list(result.scalars().all())
        if not prompts:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "该场景下还没有提示词")
        return prompts


