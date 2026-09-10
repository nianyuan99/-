"""
模型管理服务层

负责从 OpenRouter 同步模型列表（价格、上下文长度、是否国内模型等），
并提供前端模型选择器所需的查询能力。
"""

import json
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    CHINA_MODEL_PROVIDERS,
    EXCLUDED_MODEL_SUFFIXES,
    RECOMMENDED_MODEL_IDS,
)
from app.core.config import get_settings
from app.models.model import Model
from app.schemas.conversation import ModelVO

logger = logging.getLogger(__name__)

settings = get_settings()

# 策展列表转成 set，同步时逐条判断是否推荐，避免 O(n²) 查找
RECOMMENDED_MODEL_ID_SET = frozenset(RECOMMENDED_MODEL_IDS)

# 价格换算：OpenRouter 返回的是「每 token 价格」，库表存的是「每百万 tokens 价格」
PRICE_UNIT = Decimal("1000000")

# 价格字段精度，与数据库 DECIMAL(10, 6) 对齐
PRICE_PRECISION = Decimal("0.000001")

# DECIMAL(10, 6) 能表示的最大值，超出后写库会直接报错
PRICE_MAX = Decimal("9999.999999")

# 只保留前 N 个字符的原始数据，避免 rawData 字段过大
RAW_DATA_MAX_LENGTH = 20000


class ModelService:
    """模型服务类"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ 对外方法 ============

    async def sync_models_from_openrouter(self) -> int:
        """
        从 OpenRouter 同步模型列表

        逻辑：拉取 /models → 解析价格（每 token 换算为每百万 tokens）→
        判断是否国内模型 → 已存在则更新，不存在则插入。

        Returns:
            同步的模型数量
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.OPENROUTER_BASE_URL}/models",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://codefather.cn",
                    "X-Title": "AI Evaluation Platform",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        models_data: List[Dict[str, Any]] = data.get("data", [])
        if not models_data:
            logger.warning("OpenRouter 返回的模型列表为空")
            return 0

        # 一次性查出已有模型，避免循环里逐条查询数据库
        result = await self.db.execute(select(Model))
        existing_map: Dict[str, Model] = {model.id: model for model in result.scalars().all()}

        # 同步的目标是「镜像上游」：该存在的模型 is_delete 归 0，被排除的变体归 1。
        # 这样既能拦住新出现的批处理变体，也能自动清理之前已经写进库里的脏数据。
        excluded_count = 0
        for existing_model in existing_map.values():
            if existing_model.is_delete == 0 and self.is_excluded_model(existing_model.id):
                existing_model.is_delete = 1
                excluded_count += 1

        synced_count = 0
        synced_ids = set()
        for model_data in models_data:
            model_id = model_data.get("id")
            if not model_id or self.is_excluded_model(model_id):
                continue

            input_price, output_price = self._parse_pricing(model_data.get("pricing", {}) or {})
            is_china = self._is_china_model(model_id)
            recommended = 1 if model_id in RECOMMENDED_MODEL_ID_SET else 0
            raw_data = json.dumps(model_data, ensure_ascii=False)[:RAW_DATA_MAX_LENGTH]
            synced_ids.add(model_id)

            existing_model = existing_map.get(model_id)
            if existing_model:
                existing_model.name = model_data.get("name", model_id)
                existing_model.description = model_data.get("description")
                existing_model.provider = self._extract_provider(model_id)
                existing_model.context_length = model_data.get("context_length")
                existing_model.input_price = input_price
                existing_model.output_price = output_price
                existing_model.is_china = is_china
                existing_model.recommended = recommended
                existing_model.raw_data = raw_data
                # 曾经因为进入排除名单被逻辑删除、如今上游又提供时，恢复可见
                existing_model.is_delete = 0
            else:
                self.db.add(
                    Model(
                        id=model_id,
                        name=model_data.get("name", model_id),
                        description=model_data.get("description"),
                        provider=self._extract_provider(model_id),
                        context_length=model_data.get("context_length"),
                        input_price=input_price,
                        output_price=output_price,
                        recommended=recommended,
                        is_china=is_china,
                        raw_data=raw_data,
                        total_tokens=0,
                        total_cost=Decimal("0"),
                        is_delete=0,
                    )
                )

            synced_count += 1

        await self.db.commit()
        self._warn_missing_recommended_models(synced_ids)
        logger.info(
            "模型同步完成，共同步 %s 个模型，排除 %s 个批次/扩展变体",
            synced_count,
            excluded_count,
        )
        return synced_count

    async def list_models(
        self,
        keyword: Optional[str] = None,
        is_china: Optional[int] = None,
        recommended: Optional[int] = None,
        limit: int = 500,
    ) -> List[ModelVO]:
        """
        查询模型列表（供前端模型选择器使用）

        排序规则：国内模型优先 → 推荐模型优先 → 最近更新优先，
        这样国内用户打开选择器时优先看到访问速度更快的模型。

        Args:
            keyword: 按模型 ID / 名称模糊搜索
            is_china: 是否只看国内模型（1-是 0-否 None-不限）
            recommended: 是否只看推荐模型（1-是 0-否 None-不限）
            limit: 最多返回条数

        Returns:
            模型视图对象列表
        """
        query = select(Model).where(Model.is_delete == 0)

        if keyword:
            like_pattern = f"%{keyword}%"
            query = query.where(or_(Model.id.like(like_pattern), Model.name.like(like_pattern)))
        if is_china is not None:
            query = query.where(Model.is_china == is_china)
        if recommended is not None:
            query = query.where(Model.recommended == recommended)

        query = query.order_by(
            Model.is_china.desc(),
            Model.recommended.desc(),
            Model.update_time.desc(),
        ).limit(limit)

        result = await self.db.execute(query)
        return [self._to_vo(model) for model in result.scalars().all()]

    async def get_model(self, model_id: str) -> Optional[Model]:
        """按模型 ID 查询模型（用于成本计算时取价格）"""
        result = await self.db.execute(
            select(Model).where(Model.id == model_id, Model.is_delete == 0)
        )
        return result.scalar_one_or_none()

    async def count_models(self) -> int:
        """统计已同步的模型数量"""
        result = await self.db.execute(
            select(func.count()).select_from(Model).where(Model.is_delete == 0)
        )
        return result.scalar() or 0

    # ============ 内部方法 ============

    @classmethod
    def _to_vo(cls, model: Model) -> ModelVO:
        """ORM → VO，顺带把 rawData 里的发布时间提到顶层（前端要按它排序）"""
        vo = ModelVO.model_validate(model)
        vo.created = cls._extract_created(model.raw_data)
        return vo

    @staticmethod
    def _extract_created(raw_data: Optional[str]) -> Optional[int]:
        """
        从 OpenRouter 原始数据里取「模型发布时间」

        库里没有单独的发布时间列，只能从 rawData 的 `created` 字段读
        （OpenRouter 给的是 Unix 秒）。解析不出来就返回 None，
        前端对这种模型退化为保持原有顺序。
        """
        if not raw_data:
            return None
        try:
            created = json.loads(raw_data).get("created")
        except (TypeError, ValueError):
            return None
        return created if isinstance(created, int) else None

    @staticmethod
    def _to_per_million(raw_price: Any) -> Optional[Decimal]:
        """
        把「每 token 价格」换算为「每百万 tokens 价格」

        需要处理两种异常值：
        1. OpenRouter 对动态定价模型（openrouter/auto 等）返回 -1 作为哨兵值，
           换算后为 -1000000，直接写库会溢出 DECIMAL(10, 6)，这类价格视为未知；
        2. 极少数模型价格超过 DECIMAL(10, 6) 上限，做截断并告警。
        """
        try:
            value = Decimal(str(raw_price)) * PRICE_UNIT
        except (ArithmeticError, ValueError):
            return None

        if value < 0:
            return None

        if value > PRICE_MAX:
            logger.warning("模型价格 %s 超出 DECIMAL(10, 6) 上限，已按上限截断", value)
            value = PRICE_MAX

        return value.quantize(PRICE_PRECISION, rounding=ROUND_HALF_UP)

    @classmethod
    def _parse_pricing(cls, pricing: Dict[str, Any]) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """
        解析模型价格

        OpenRouter 返回的价格是 per-token 的字符串（例如 0.0000025），
        直接转 float 再运算会有精度问题，这里统一走 Decimal。
        """
        input_price: Optional[Decimal] = None
        output_price: Optional[Decimal] = None

        try:
            if pricing.get("prompt") is not None:
                input_price = cls._to_per_million(pricing["prompt"])
            if pricing.get("completion") is not None:
                output_price = cls._to_per_million(pricing["completion"])
        except (ArithmeticError, ValueError) as e:
            logger.warning("解析模型价格失败: pricing=%s, error=%s", pricing, str(e))

        return input_price, output_price

    @staticmethod
    def _extract_provider(model_id: str) -> str:
        """
        从模型 ID 中提取提供商

        例如 "deepseek/deepseek-chat" → "deepseek"
        """
        if "/" not in model_id:
            return model_id
        return model_id.split("/", 1)[0]

    @staticmethod
    def _is_china_model(model_id: str) -> int:
        """
        判断是否为国内模型

        直接按提供商关键字匹配，命中即返回 1，便于前端优先展示访问更快的国内模型。
        """
        model_id_lower = model_id.lower()
        for provider in CHINA_MODEL_PROVIDERS:
            if provider in model_id_lower:
                return 1
        return 0

    @staticmethod
    def is_excluded_model(model_id: str) -> bool:
        """
        判断是否为本平台不接入的特殊变体（批处理 / 扩展上下文）

        例如 z-ai/glm-5.3:batch 是 OpenRouter 的批处理接口，
        需要异步提交且最长 24 小时才返回，用在实时流式对比里必然失败；
        这类模型对本站是纯噪声，同步阶段就直接过滤掉，不让它进入模型表。
        """
        suffix = model_id.rsplit(":", 1)[-1].lower() if ":" in model_id else ""
        return suffix in EXCLUDED_MODEL_SUFFIXES

    @staticmethod
    def _warn_missing_recommended_models(synced_ids: set) -> None:
        """
        提示策展列表里本次没有同步到的模型

        RECOMMENDED_MODEL_IDS 是人工维护的精确 ID，上游下线或改名后这些条目会失效，
        同步时把未命中的打出来，方便及时发现并更新策展列表。
        """
        missing = sorted(RECOMMENDED_MODEL_ID_SET - synced_ids)
        if missing:
            logger.warning(
                "以下策展推荐模型本次未同步到（可能已下线或改名），请更新 constants.RECOMMENDED_MODEL_IDS: %s",
                missing,
            )
