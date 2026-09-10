"""
对话与评分相关的请求和响应模型（Pydantic）

字段别名说明：前端（JS）习惯驼峰命名，Python 习惯下划线命名。
通过 Field(alias=...) 让两边各用各的风格，model_dump_json(by_alias=True)
序列化后即为前端可直接消费的驼峰格式。
"""

from datetime import datetime
from typing import List, Optional

from app.constants import MAX_PROMPT_VARIANTS_COUNT, MIN_PROMPT_VARIANTS_COUNT
from pydantic import BaseModel, Field


# ============ 请求模型 ============


class SideBySideRequest(BaseModel):
    """Side-by-Side 多模型并排对比请求"""

    conversation_id: Optional[str] = Field(None, alias="conversationId", description="对话ID，为空则新建对话")
    models: List[str] = Field(..., description="模型列表（1-8个）")
    prompt: str = Field(..., description="提示词")
    image_urls: Optional[List[str]] = Field(None, alias="imageUrls", description="图片URL列表")
    web_search_enabled: Optional[bool] = Field(False, alias="webSearchEnabled", description="是否联网搜索")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class GenerateVariantsRequest(BaseModel):
    """变体自动生成请求：传一个基础提示词，让大模型生成 N 个不同风格的变体"""

    base_prompt: str = Field(
        ..., min_length=1, max_length=2000, alias="basePrompt", description="基础提示词"
    )
    count: int = Field(
        default=3,
        ge=MIN_PROMPT_VARIANTS_COUNT,
        le=MAX_PROMPT_VARIANTS_COUNT,
        description=f"要生成的变体数量（{MIN_PROMPT_VARIANTS_COUNT}-{MAX_PROMPT_VARIANTS_COUNT}）",
    )
    model: Optional[str] = Field(
        None,
        description="生成用的模型；为空时用服务端默认免费模型。Prompt Lab 当前选中的模型可选传入",
    )

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class PromptLabRequest(BaseModel):
    """Prompt Lab 单模型多提示词对比请求"""

    conversation_id: Optional[str] = Field(
        None, alias="conversationId", description="对话ID，为空则新建对话"
    )
    model: str = Field(..., description="模型名称（只有一个，对比的是提示词而不是模型）")
    prompt_variants: List[str] = Field(
        ..., alias="promptVariants", description="提示词变体列表（2-5 个）"
    )
    variant_image_urls: Optional[List[List[str]]] = Field(
        None, alias="variantImageUrls", description="每个变体对应的图片URL列表"
    )
    web_search_enabled: Optional[bool] = Field(
        False, alias="webSearchEnabled", description="是否联网搜索"
    )

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class RatingRequest(BaseModel):
    """用户评分请求"""

    conversation_id: str = Field(..., alias="conversationId", description="对话ID")
    message_index: int = Field(..., alias="messageIndex", ge=0, description="消息序号")
    rating_type: str = Field(
        ...,
        alias="ratingType",
        description="评分类型: model_better/tie/both_bad；Prompt Lab 为 variant_0、variant_1...",
    )
    winner_model: Optional[str] = Field(None, alias="winnerModel", description="获胜模型")
    loser_model: Optional[str] = Field(None, alias="loserModel", description="失败模型")
    winner_variant_index: Optional[int] = Field(
        None, alias="winnerVariantIndex", ge=0, description="获胜变体索引（Prompt Lab 专用）"
    )

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class ConversationQueryRequest(BaseModel):
    """对话分页查询请求"""

    conversation_type: Optional[str] = Field(
        None, alias="conversationType", description="对话类型: side_by_side/prompt_lab/battle"
    )
    current: int = Field(default=1, ge=1, description="当前页码")
    page_size: int = Field(default=10, ge=1, le=100, alias="pageSize", description="每页条数")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


# ============ 响应模型 ============


class StreamChunkVO(BaseModel):
    """SSE 流式响应数据块"""

    conversation_id: Optional[str] = Field(None, alias="conversationId", description="对话ID")
    model_name: Optional[str] = Field(None, alias="modelName", description="模型名称")
    variant_index: Optional[int] = Field(None, alias="variantIndex", description="变体索引")
    message_index: Optional[int] = Field(None, alias="messageIndex", description="本轮消息序号，评分时使用")
    content: Optional[str] = Field(None, description="内容片段")
    full_content: Optional[str] = Field(None, alias="fullContent", description="完整内容")
    input_tokens: Optional[int] = Field(None, alias="inputTokens", description="输入Token数")
    output_tokens: Optional[int] = Field(None, alias="outputTokens", description="输出Token数")
    elapsed_ms: Optional[int] = Field(None, alias="elapsedMs", description="已耗时（毫秒）")
    response_time_ms: Optional[int] = Field(None, alias="responseTimeMs", description="响应时间（毫秒）")
    cost: Optional[float] = Field(None, description="成本（USD）")
    done: Optional[bool] = Field(None, description="是否完成")
    error: Optional[str] = Field(None, description="错误信息")
    has_error: Optional[bool] = Field(None, alias="hasError", description="是否发生错误")
    reasoning: Optional[str] = Field(None, description="思考过程")
    has_reasoning: Optional[bool] = Field(None, alias="hasReasoning", description="是否有思考过程")
    thinking_time: Optional[int] = Field(None, alias="thinkingTime", description="思考时间（秒）")

    model_config = {"protected_namespaces": (), "populate_by_name": True}


class ConversationMessageVO(BaseModel):
    """对话消息视图对象"""

    id: str = Field(..., description="消息ID")
    conversation_id: str = Field(..., alias="conversationId", description="对话ID")
    message_index: int = Field(..., alias="messageIndex", description="消息序号")
    variant_index: Optional[int] = Field(
        None, alias="variantIndex", description="变体索引（Prompt Lab 专用）"
    )
    role: str = Field(..., description="角色: user/assistant")
    model_name: Optional[str] = Field(None, alias="modelName", description="模型名称")
    content: str = Field(..., description="消息内容")
    response_time_ms: Optional[int] = Field(None, alias="responseTimeMs", description="响应时间（毫秒）")
    input_tokens: Optional[int] = Field(None, alias="inputTokens", description="输入Token数")
    output_tokens: Optional[int] = Field(None, alias="outputTokens", description="输出Token数")
    cost: Optional[float] = Field(None, description="成本（USD）")
    reasoning: Optional[str] = Field(None, description="思考过程")
    create_time: datetime = Field(..., alias="createTime", description="创建时间")

    model_config = {"populate_by_name": True, "protected_namespaces": (), "from_attributes": True}


class RatingVO(BaseModel):
    """评分视图对象"""

    id: str = Field(..., description="评分ID")
    conversation_id: str = Field(..., alias="conversationId", description="对话ID")
    message_index: int = Field(..., alias="messageIndex", description="消息序号")
    rating_type: str = Field(
        ...,
        alias="ratingType",
        description="评分类型: model_better/tie/both_bad；Prompt Lab 为 variant_0、variant_1...",
    )
    winner_variant_index: Optional[int] = Field(
        None, alias="winnerVariantIndex", description="获胜变体索引（Prompt Lab 专用）"
    )
    winner_model: Optional[str] = Field(None, alias="winnerModel", description="获胜模型")
    loser_model: Optional[str] = Field(None, alias="loserModel", description="失败模型")

    model_config = {"populate_by_name": True, "protected_namespaces": (), "from_attributes": True}


class ConversationVO(BaseModel):
    """对话视图对象"""

    id: str = Field(..., description="对话ID")
    title: Optional[str] = Field(None, description="对话标题")
    conversation_type: str = Field(..., alias="conversationType", description="对话类型")
    models: List[str] = Field(default_factory=list, description="参与的模型列表")
    total_tokens: Optional[int] = Field(None, alias="totalTokens", description="总Token消耗")
    total_cost: Optional[float] = Field(None, alias="totalCost", description="总成本（USD）")
    create_time: datetime = Field(..., alias="createTime", description="创建时间")
    update_time: datetime = Field(..., alias="updateTime", description="更新时间")

    model_config = {"populate_by_name": True, "protected_namespaces": (), "from_attributes": True}


class ModelVO(BaseModel):
    """模型信息视图对象"""

    id: str = Field(..., description="模型ID")
    name: str = Field(..., description="模型显示名称")
    description: Optional[str] = Field(None, description="模型描述")
    provider: Optional[str] = Field(None, description="提供商")
    context_length: Optional[int] = Field(None, alias="contextLength", description="上下文长度")
    input_price: Optional[float] = Field(None, alias="inputPrice", description="输入价格（每百万tokens）")
    output_price: Optional[float] = Field(None, alias="outputPrice", description="输出价格（每百万tokens）")
    recommended: int = Field(default=0, description="是否推荐")
    is_china: int = Field(default=0, alias="isChina", description="是否国内模型")
    created: Optional[int] = Field(
        None, description="模型发布时间（Unix 秒，取自 OpenRouter 原始数据的 created 字段）"
    )
    tags: Optional[str] = Field(None, description="标签")

    model_config = {"populate_by_name": True, "protected_namespaces": (), "from_attributes": True}
