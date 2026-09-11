"""
场景与场景提示词相关的请求和响应模型（Pydantic）

字段别名说明：前端（JS）习惯驼峰命名，Python 习惯下划线命名。
通过 Field(alias=...) 让两边各用各的风格，model_dump(by_alias=True) 后即为前端可消费的驼峰格式。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

# ============ 请求模型 ============


class CreateSceneRequest(BaseModel):
    """创建场景请求"""

    name: str = Field(..., min_length=1, max_length=100, description="场景名称")
    description: Optional[str] = Field(None, description="场景描述")
    category: Optional[str] = Field(None, max_length=50, description="分类:编程/数学/文案等")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class UpdateSceneRequest(BaseModel):
    """更新场景请求"""

    id: str = Field(..., description="场景ID")
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="场景名称")
    description: Optional[str] = Field(None, description="场景描述")
    category: Optional[str] = Field(None, max_length=50, description="分类")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class DeleteSceneRequest(BaseModel):
    """删除场景请求"""

    id: str = Field(..., description="场景ID")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class SceneQueryRequest(BaseModel):
    """场景分页查询请求"""

    name: Optional[str] = Field(None, max_length=100, description="按场景名称模糊搜索")
    category: Optional[str] = Field(None, max_length=50, description="按分类筛选")
    is_preset: Optional[bool] = Field(
        None, alias="isPreset", description="按类型筛选：true-预设场景 false-自定义场景"
    )
    current: int = Field(default=1, ge=1, description="当前页码")
    page_size: int = Field(default=10, ge=1, le=100, alias="pageSize", description="每页条数")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class AddScenePromptRequest(BaseModel):
    """添加场景提示词请求"""

    scene_id: str = Field(..., alias="sceneId", description="场景ID")
    title: str = Field(..., min_length=1, max_length=200, description="提示词标题")
    content: str = Field(..., min_length=1, description="提示词内容")
    difficulty: Optional[str] = Field(None, description="难度: easy/medium/hard")
    tags: Optional[List[str]] = Field(None, description="标签数组")
    expected_output: Optional[str] = Field(None, alias="expectedOutput", description="期望输出(可选)")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class UpdateScenePromptRequest(BaseModel):
    """更新场景提示词请求"""

    id: str = Field(..., description="提示词ID")
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="提示词标题")
    content: Optional[str] = Field(None, min_length=1, description="提示词内容")
    difficulty: Optional[str] = Field(None, description="难度: easy/medium/hard")
    tags: Optional[List[str]] = Field(None, description="标签数组")
    expected_output: Optional[str] = Field(None, alias="expectedOutput", description="期望输出(可选)")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class DeleteScenePromptRequest(BaseModel):
    """删除场景提示词请求"""

    id: str = Field(..., description="提示词ID")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


# ============ 响应模型 ============


class ScenePromptsRequest(BaseModel):
    """查询场景提示词列表请求（GET 场景详情时也用同一个查询参数）"""

    scene_id: str = Field(..., alias="sceneId", description="场景ID")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class ScenePromptVO(BaseModel):
    """场景提示词视图对象"""

    id: str = Field(..., description="提示词ID")
    scene_id: str = Field(..., alias="sceneId", description="场景ID")
    prompt_index: int = Field(..., alias="promptIndex", description="提示词序号")
    title: str = Field(..., description="提示词标题")
    content: str = Field(..., description="提示词内容")
    difficulty: Optional[str] = Field(None, description="难度: easy/medium/hard")
    tags: Optional[List[str]] = Field(None, description="标签数组")
    expected_output: Optional[str] = Field(None, alias="expectedOutput", description="期望输出")
    create_time: datetime = Field(..., alias="createTime", description="创建时间")
    update_time: datetime = Field(..., alias="updateTime", description="更新时间")

    model_config = {"populate_by_name": True, "protected_namespaces": (), "from_attributes": True}


class SceneVO(BaseModel):
    """场景视图对象"""

    id: str = Field(..., description="场景ID")
    name: str = Field(..., description="场景名称")
    description: Optional[str] = Field(None, description="场景描述")
    category: Optional[str] = Field(None, description="分类")
    is_preset: int = Field(default=0, alias="isPreset", description="是否为预设场景（1-预设 0-自定义）")
    is_active: int = Field(default=1, alias="isActive", description="是否启用")
    prompt_count: Optional[int] = Field(
        None, alias="promptCount", description="场景下提示词数量（列表查询时一并返回）"
    )
    create_time: datetime = Field(..., alias="createTime", description="创建时间")
    update_time: datetime = Field(..., alias="updateTime", description="更新时间")

    model_config = {"populate_by_name": True, "protected_namespaces": (), "from_attributes": True}


class SceneDetailVO(SceneVO):
    """场景详情视图对象：在场景信息基础上带上提示词列表"""

    prompts: List[ScenePromptVO] = Field(default_factory=list, description="场景下的提示词列表")

    model_config = {"populate_by_name": True, "protected_namespaces": (), "from_attributes": True}
