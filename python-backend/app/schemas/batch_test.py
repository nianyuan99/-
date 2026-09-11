"""
批量测试相关的请求和响应模型（Pydantic）
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.constants import (
    BATCH_TEST_DEFAULT_MAX_TOKENS,
    BATCH_TEST_DEFAULT_TEMPERATURE,
    BATCH_TEST_MAX_TOKENS_MAX,
    BATCH_TEST_MAX_TOKENS_MIN,
    BATCH_TEST_TEMPERATURE_MAX,
    BATCH_TEST_TEMPERATURE_MIN,
    MAX_BATCH_TEST_MODELS,
    USER_RATING_MAX,
    USER_RATING_MIN,
)
from pydantic import BaseModel, Field, field_validator

# ============ 请求模型 ============


class CreateBatchTestRequest(BaseModel):
    """创建批量测试任务请求"""

    name: Optional[str] = Field(None, max_length=200, description="任务名称（可选）")
    scene_id: str = Field(..., alias="sceneId", description="场景ID")
    models: List[str] = Field(
        ..., min_length=1, max_length=MAX_BATCH_TEST_MODELS, description="要测试的模型列表"
    )
    temperature: Optional[float] = Field(
        BATCH_TEST_DEFAULT_TEMPERATURE,
        ge=BATCH_TEST_TEMPERATURE_MIN,
        le=BATCH_TEST_TEMPERATURE_MAX,
        description="采样温度（高级参数，可选）",
    )
    max_tokens: Optional[int] = Field(
        BATCH_TEST_DEFAULT_MAX_TOKENS,
        alias="maxTokens",
        ge=BATCH_TEST_MAX_TOKENS_MIN,
        le=BATCH_TEST_MAX_TOKENS_MAX,
        description="单次回答的最大 Token 数（高级参数，可选）",
    )

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class BatchTestTaskQueryRequest(BaseModel):
    """批量测试任务分页查询请求"""

    scene_id: Optional[str] = Field(None, alias="sceneId", description="按场景筛选")
    status: Optional[str] = Field(None, description="按状态筛选")
    current: int = Field(default=1, ge=1, description="当前页码")
    page_size: int = Field(default=10, ge=1, le=100, alias="pageSize", description="每页条数")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class DeleteBatchTestTaskRequest(BaseModel):
    """删除批量测试任务请求"""

    id: str = Field(..., description="任务ID")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class UpdateResultRatingRequest(BaseModel):
    """更新测试结果评分请求"""

    id: str = Field(..., description="结果ID")
    user_rating: int = Field(
        ..., alias="userRating", ge=USER_RATING_MIN, le=USER_RATING_MAX, description="用户评分(1-5)"
    )

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


# ============ 响应模型 ============


class TestTaskVO(BaseModel):
    """批量测试任务视图对象"""

    id: str = Field(..., description="任务ID")
    name: Optional[str] = Field(None, description="任务名称")
    scene_id: str = Field(..., alias="sceneId", description="场景ID")
    scene_name: Optional[str] = Field(None, alias="sceneName", description="场景名称（列表查询时一并返回）")
    models: List[str] = Field(default_factory=list, description="测试的模型列表")
    status: str = Field(..., description="状态: pending/running/completed/failed/cancelled")
    total_subtasks: int = Field(0, alias="totalSubtasks", description="子任务总数")
    completed_subtasks: int = Field(0, alias="completedSubtasks", description="已完成子任务数")
    started_at: Optional[datetime] = Field(None, alias="startedAt", description="开始时间")
    completed_at: Optional[datetime] = Field(None, alias="completedAt", description="完成时间")
    create_time: datetime = Field(..., alias="createTime", description="创建时间")
    update_time: datetime = Field(..., alias="updateTime", description="更新时间")

    model_config = {"populate_by_name": True, "protected_namespaces": (), "from_attributes": True}

    @field_validator("models", mode="before")
    @classmethod
    def _parse_models(cls, value: Any) -> Any:
        """
        兼容 models 列的两种返回形态

        MySQL 的 JSON 列经当前驱动读出来是字符串（不是 list），
        直接交给 Pydantic 会报 「Input should be a valid list」；
        这里统一解析成列表，解析失败时退化为空列表，避免整个列表接口 500。
        """
        if value is None or isinstance(value, (list, tuple)):
            return list(value) if value is not None else []
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8", errors="ignore")
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (ValueError, TypeError):
                return []
            return parsed if isinstance(parsed, list) else []
        return []


class TestResultVO(BaseModel):
    """批量测试结果视图对象"""

    id: str = Field(..., description="结果ID")
    task_id: str = Field(..., alias="taskId", description="任务ID")
    scene_id: str = Field(..., alias="sceneId", description="场景ID")
    prompt_id: str = Field(..., alias="promptId", description="提示词ID")
    prompt_title: Optional[str] = Field(None, alias="promptTitle", description="提示词标题")
    prompt_index: Optional[int] = Field(None, alias="promptIndex", description="提示词序号")
    model_name: str = Field(..., alias="modelName", description="模型名称")
    input_prompt: str = Field(..., alias="inputPrompt", description="输入提示词")
    output_text: str = Field(..., alias="outputText", description="输出内容")
    reasoning: Optional[str] = Field(None, description="思考过程内容")
    response_time_ms: Optional[int] = Field(None, alias="responseTimeMs", description="响应时间(毫秒)")
    input_tokens: Optional[int] = Field(None, alias="inputTokens", description="输入Token数")
    output_tokens: Optional[int] = Field(None, alias="outputTokens", description="输出Token数")
    cost: Optional[float] = Field(None, description="成本(USD)")
    user_rating: Optional[int] = Field(None, alias="userRating", description="用户评分(1-5)")
    ai_score: Optional[Dict[str, Any]] = Field(None, alias="aiScore", description="AI评分详情")
    create_time: datetime = Field(..., alias="createTime", description="创建时间")

    model_config = {"populate_by_name": True, "protected_namespaces": (), "from_attributes": True}


class TaskProgressVO(BaseModel):
    """
    任务进度推送消息

    通过 WebSocket（/topic/task/{taskId}）推送给前端，字段名与前端约定保持一致。
    """

    task_id: str = Field(..., alias="taskId", description="任务ID")
    status: str = Field(..., description="任务状态")
    total_subtasks: int = Field(0, alias="totalSubtasks", description="子任务总数")
    completed_subtasks: int = Field(0, alias="completedSubtasks", description="已完成子任务数")
    percentage: int = Field(0, description="完成百分比（0-100）")
    current_model: Optional[str] = Field(None, alias="currentModel", description="当前测试的模型")
    current_prompt: Optional[str] = Field(None, alias="currentPrompt", description="当前测试的提示词标题")
    model_name: Optional[str] = Field(None, alias="modelName", description="刚完成的模型")
    prompt_title: Optional[str] = Field(None, alias="promptTitle", description="刚完成的提示词标题")
    success: Optional[bool] = Field(None, description="刚完成的子任务是否成功")
    error_message: Optional[str] = Field(None, alias="errorMessage", description="刚完成的子任务错误信息")
    message: Optional[str] = Field(None, description="附加提示信息")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class UserModelUsageVO(BaseModel):
    """用户-模型使用统计视图对象"""

    model_name: str = Field(..., alias="modelName", description="模型名称")
    model_label: Optional[str] = Field(None, alias="modelLabel", description="模型显示名称")
    total_tokens: int = Field(0, alias="totalTokens", description="累计 Token 数")
    total_cost: float = Field(0, alias="totalCost", description="累计花费（美元）")

    model_config = {"populate_by_name": True, "protected_namespaces": (), "from_attributes": True}


class ModelUsageStatVO(BaseModel):
    """模型维度的使用统计（数据统计概览页）"""

    model_name: str = Field(..., alias="modelName", description="模型名称")
    model_label: Optional[str] = Field(None, alias="modelLabel", description="模型显示名称")
    call_count: int = Field(0, alias="callCount", description="被调用次数")
    total_tokens: int = Field(0, alias="totalTokens", description="累计 Token 数")
    total_cost: float = Field(0, alias="totalCost", description="累计花费（美元）")
    avg_response_time_ms: Optional[int] = Field(
        None, alias="avgResponseTimeMs", description="平均响应时间（毫秒）"
    )

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class StatisticsOverviewVO(BaseModel):
    """数据统计概览视图对象"""

    task_count: int = Field(0, alias="taskCount", description="任务总数")
    completed_task_count: int = Field(0, alias="completedTaskCount", description="已完成任务数")
    running_task_count: int = Field(0, alias="runningTaskCount", description="进行中任务数")
    result_count: int = Field(0, alias="resultCount", description="测试结果总数")
    model_count: int = Field(0, alias="modelCount", description="参与过测试的模型数")
    scene_count: int = Field(0, alias="sceneCount", description="可用场景数")
    total_tokens: int = Field(0, alias="totalTokens", description="累计 Token 消耗")
    total_cost: float = Field(0, alias="totalCost", description="累计花费（美元）")
    avg_response_time_ms: Optional[int] = Field(
        None, alias="avgResponseTimeMs", description="平均响应时间（毫秒）"
    )
    model_usage: List[UserModelUsageVO] = Field(
        default_factory=list, alias="modelUsage", description="按模型汇总的使用情况"
    )
    model_stats: List[ModelUsageStatVO] = Field(
        default_factory=list, alias="modelStats", description="模型维度的测试统计"
    )

    model_config = {"populate_by_name": True, "protected_namespaces": ()}
