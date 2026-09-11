"""
提示词模板与优化相关 Schema
@author <a href="https://codefather.cn">编程导航学习圈</a>
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class CreatePromptTemplateRequest(BaseModel):
    """
    创建提示词模板请求
    """

    name: str = Field(..., description="模板名称")
    description: Optional[str] = Field(default=None, description="模板描述")
    strategy: str = Field(..., description="策略类型: direct/cot/role_play/few_shot")
    content: str = Field(..., description="模板内容")
    variables: Optional[List[str]] = Field(default=None, description="变量列表")
    category: Optional[str] = Field(default=None, description="分类")
    is_public: Optional[bool] = Field(default=None, description="是否公开到社区", alias="isPublic")

    class Config:
        populate_by_name = True


class UpdatePromptTemplateRequest(BaseModel):
    """
    更新提示词模板请求（字段均可选，只更新传入的字段）
    """

    name: Optional[str] = Field(default=None, description="模板名称")
    description: Optional[str] = Field(default=None, description="模板描述")
    strategy: Optional[str] = Field(default=None, description="策略类型")
    content: Optional[str] = Field(default=None, description="模板内容")
    variables: Optional[List[str]] = Field(default=None, description="变量列表")
    category: Optional[str] = Field(default=None, description="分类")
    is_active: Optional[bool] = Field(default=None, description="是否启用", alias="isActive")
    is_public: Optional[bool] = Field(default=None, description="是否公开到社区", alias="isPublic")

    class Config:
        populate_by_name = True


class PromptTemplateVO(BaseModel):
    """
    提示词模板视图对象
    """

    id: str = Field(..., description="模板ID")
    name: str = Field(..., description="模板名称")
    description: Optional[str] = Field(default=None, description="模板描述")
    strategy: str = Field(..., description="策略类型")
    strategy_name: str = Field(..., description="策略类型显示名称", alias="strategyName")
    content: str = Field(..., description="模板内容")
    variables: List[str] = Field(default_factory=list, description="变量列表")
    category: Optional[str] = Field(default=None, description="分类")
    is_preset: bool = Field(..., description="是否为预设模板", alias="isPreset")
    is_public: bool = Field(default=False, description="是否公开到社区", alias="isPublic")
    usage_count: int = Field(default=0, description="使用次数", alias="usageCount")
    is_active: bool = Field(..., description="是否启用", alias="isActive")
    create_time: Optional[str] = Field(default=None, description="创建时间", alias="createTime")
    # 社区互动数据
    like_count: int = Field(default=0, description="点赞数", alias="likeCount")
    favorite_count: int = Field(default=0, description="收藏数", alias="favoriteCount")
    liked: bool = Field(default=False, description="当前用户是否已点赞")
    favorited: bool = Field(default=False, description="当前用户是否已收藏")
    # 创建者信息（社区里展示「谁分享的」）
    author_id: Optional[int] = Field(default=None, description="创建者ID", alias="authorId")
    author_name: Optional[str] = Field(default=None, description="创建者昵称", alias="authorName")

    class Config:
        populate_by_name = True


class PromptVariableFillRequest(BaseModel):
    """
    模板变量填充请求（功能扩展 1：模板变量自动替换）
    """

    template_id: str = Field(..., description="模板ID", alias="templateId")
    variables: dict[str, str] = Field(default_factory=dict, description="变量名 → 变量值")

    class Config:
        populate_by_name = True


class PromptVariableFillVO(BaseModel):
    """
    模板变量填充结果
    """

    content: str = Field(..., description="填充后的完整提示词")
    unfilled_variables: List[str] = Field(
        default_factory=list,
        description="仍未填值的变量名（调用方应提示用户）",
        alias="unfilledVariables",
    )

    class Config:
        populate_by_name = True


class PromptOptimizationRequest(BaseModel):
    """
    提示词优化请求
    """

    original_prompt: str = Field(..., description="原始提示词", alias="originalPrompt")
    ai_response: Optional[str] = Field(default=None, description="AI回答", alias="aiResponse")
    evaluation_model: Optional[str] = Field(default=None, description="评估模型", alias="evaluationModel")

    class Config:
        populate_by_name = True


class PromptOptimizationVO(BaseModel):
    """
    提示词优化结果视图对象

    quality_score / quality_level 为功能扩展 4「提示词质量评分」。
    """

    issues: List[str] = Field(default_factory=list, description="问题列表")
    optimized_prompt: str = Field(default="", description="优化后的提示词", alias="optimizedPrompt")
    improvements: List[str] = Field(default_factory=list, description="改进点列表")
    quality_score: Optional[int] = Field(
        default=None, description="原始提示词质量评分(0-100)", alias="qualityScore"
    )
    quality_level: Optional[str] = Field(
        default=None, description="质量等级: excellent/good/fair/poor", alias="qualityLevel"
    )

    class Config:
        populate_by_name = True


class PromptOptimizationHistoryVO(BaseModel):
    """
    优化历史记录视图对象（功能扩展 3）
    """

    id: str = Field(..., description="记录ID")
    original_prompt: str = Field(..., description="原始提示词", alias="originalPrompt")
    optimized_prompt: Optional[str] = Field(default=None, description="优化后的提示词", alias="optimizedPrompt")
    issues: List[str] = Field(default_factory=list, description="问题列表")
    improvements: List[str] = Field(default_factory=list, description="改进说明")
    quality_score: Optional[int] = Field(default=None, description="质量评分", alias="qualityScore")
    quality_level: Optional[str] = Field(default=None, description="质量等级", alias="qualityLevel")
    evaluation_model: Optional[str] = Field(default=None, description="评估模型", alias="evaluationModel")
    create_time: Optional[str] = Field(default=None, description="优化时间", alias="createTime")

    class Config:
        populate_by_name = True
