"""
AI 评分相关的数据结构（Pydantic）

一条测试结果会经过「多个 AI 评委」交叉打分：
- EvaluationResult：单个评委一次调用的原始解析结果（内部使用）
- JudgeScore：单个评委的评分（对外序列化进 test_result.aiScore）
- AIScoreResult：多评委汇总结果（各评委明细 + 平均评级 + 一致性）
"""

import json
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field


class EvaluationResult(BaseModel):
    """
    单次 AI 评分结果（单评委）
    """

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    scores: Dict[str, int] = Field(default_factory=dict, description="各维度分数")
    total_score: int = Field(..., alias="total_score", description="总分(100分制)")
    rating: int = Field(..., description="评级(1-10)")
    comment: str = Field("", description="简短评价")


class JudgeScore(BaseModel):
    """
    评委评分结果（多评委时每个评委一条）
    """

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    model: str = Field(..., description="评委模型名称")
    scores: Dict[str, int] = Field(default_factory=dict, description="各维度分数")
    total_score: int = Field(..., alias="totalScore", description="总分")
    rating: int = Field(..., description="评级(1-10)")
    comment: str = Field("", description="评委评语")


class AIScoreResult(BaseModel):
    """
    AI 评分结果（多评委汇总）
    """

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    judges: List[JudgeScore] = Field(default_factory=list, description="各评委评分列表")
    average_rating: float = Field(..., alias="averageRating", description="平均评级")
    consistency: float = Field(0.0, description="一致性(标准差)")


def ai_score_result_to_json(ai_score_result: AIScoreResult) -> str:
    """
    将 AIScoreResult 序列化为 JSON 字符串，用于写入 test_result.aiScore
    """
    return json.dumps(ai_score_result.model_dump(by_alias=True), ensure_ascii=False)
