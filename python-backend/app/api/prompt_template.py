"""
提示词模板接口层
"""

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from app.schemas.prompt import (
    CreatePromptTemplateRequest,
    PromptTemplateVO,
    PromptVariableFillRequest,
    UpdatePromptTemplateRequest,
)
from app.schemas.user import BaseResponse
from app.services.prompt_template_service import PromptTemplateService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompt/template", tags=["提示词模板接口"])


@router.get("/list", response_model=BaseResponse[list], summary="获取模板列表")
async def list_templates(
    request: Request,
    strategy: str | None = Query(default=None, description="策略类型"),
    db: AsyncSession = Depends(get_async_db),
):
    """获取模板列表（预设模板 + 自己的自定义模板 + 他人公开的模板）"""
    user = await UserService.get_login_user(db, request)
    templates: list[PromptTemplateVO] = await PromptTemplateService.list_templates(
        db, user.id, strategy
    )
    return BaseResponse(
        code=0, data=[t.model_dump(by_alias=True) for t in templates], message="ok"
    )


@router.get("/community", response_model=BaseResponse[list], summary="获取社区公开模板")
async def list_community_templates(
    request: Request,
    strategy: str | None = Query(default=None, description="策略类型"),
    sortBy: str = Query(default="latest", description="排序: latest/hot"),
    db: AsyncSession = Depends(get_async_db),
):
    """功能扩展 2：浏览社区里其他用户公开分享的模板"""
    user = await UserService.get_login_user(db, request)
    templates: list[PromptTemplateVO] = (
        await PromptTemplateService.list_community_templates(
            db, user.id, strategy, sortBy
        )
    )
    return BaseResponse(
        code=0, data=[t.model_dump(by_alias=True) for t in templates], message="ok"
    )


@router.get("/favorites", response_model=BaseResponse[list], summary="获取收藏的模板")
async def list_favorite_templates(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """功能扩展 2：当前用户收藏的模板列表"""
    user = await UserService.get_login_user(db, request)
    templates: list[PromptTemplateVO] = (
        await PromptTemplateService.list_favorite_templates(db, user.id)
    )
    return BaseResponse(
        code=0, data=[t.model_dump(by_alias=True) for t in templates], message="ok"
    )


@router.get("/get", response_model=BaseResponse[dict], summary="获取模板详情")
async def get_template(
    request: Request,
    templateId: str = Query(..., description="模板ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """按 ID 获取单个模板详情（含点赞/收藏状态）"""
    user = await UserService.get_login_user(db, request)
    template = await PromptTemplateService.get_template_vo(db, templateId, user.id)
    return BaseResponse(code=0, data=template.model_dump(by_alias=True), message="ok")


@router.post("/add", response_model=BaseResponse[str], summary="创建模板")
async def create_template(
    request_body: CreatePromptTemplateRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """创建自定义模板（可选公开到社区）"""
    user = await UserService.get_login_user(db, request)
    template_id = await PromptTemplateService.create_template(
        db=db,
        name=request_body.name,
        strategy=request_body.strategy,
        content=request_body.content,
        user_id=user.id,
        description=request_body.description,
        variables=request_body.variables,
        category=request_body.category,
        is_public=request_body.is_public,
    )
    return BaseResponse(code=0, data=template_id, message="ok")


@router.post("/update", response_model=BaseResponse[bool], summary="更新模板")
async def update_template(
    request_body: UpdatePromptTemplateRequest,
    request: Request,
    templateId: str = Query(..., description="模板ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """更新自定义模板（预设模板不可修改）"""
    user = await UserService.get_login_user(db, request)
    result = await PromptTemplateService.update_template(
        db=db,
        template_id=templateId,
        user_id=user.id,
        name=request_body.name,
        description=request_body.description,
        strategy=request_body.strategy,
        content=request_body.content,
        variables=request_body.variables,
        category=request_body.category,
        is_active=request_body.is_active,
        is_public=request_body.is_public,
    )
    return BaseResponse(code=0, data=result, message="ok")


@router.post("/delete", response_model=BaseResponse[bool], summary="删除模板")
async def delete_template(
    request: Request,
    templateId: str = Query(..., description="模板ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """删除自定义模板（逻辑删除，预设模板不可删除）"""
    user = await UserService.get_login_user(db, request)
    result = await PromptTemplateService.delete_template(
        db=db, template_id=templateId, user_id=user.id
    )
    return BaseResponse(code=0, data=result, message="ok")


@router.post("/use", response_model=BaseResponse[bool], summary="增加模板使用次数")
async def increment_usage_count(
    request: Request,
    templateId: str = Query(..., description="模板ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """记录一次模板使用（模板不存在时返回 false，不报错）"""
    await UserService.get_login_user(db, request)
    result = await PromptTemplateService.increment_usage_count(db, templateId)
    return BaseResponse(code=0, data=result, message="ok")


@router.post("/fill", response_model=BaseResponse[dict], summary="填充模板变量")
async def fill_template_variables(
    request_body: PromptVariableFillRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    功能扩展 1：模板变量自动替换

    把用户填的变量值替换进模板占位符，返回填充后的完整提示词。
    未填值的变量会在 unfilledVariables 里返回，由前端提示用户。
    """
    await UserService.get_login_user(db, request)
    content, unfilled = await PromptTemplateService.fill_template(
        db, request_body.template_id, request_body.variables
    )
    return BaseResponse(
        code=0,
        data={"content": content, "unfilledVariables": unfilled},
        message="ok",
    )


@router.post("/like", response_model=BaseResponse[bool], summary="点赞/取消点赞模板")
async def toggle_like(
    request: Request,
    templateId: str = Query(..., description="模板ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """功能扩展 2：点赞或取消点赞，返回操作后是否已点赞"""
    user = await UserService.get_login_user(db, request)
    result = await PromptTemplateService.toggle_like(db, templateId, user.id)
    return BaseResponse(code=0, data=result, message="ok")


@router.post("/favorite", response_model=BaseResponse[bool], summary="收藏/取消收藏模板")
async def toggle_favorite(
    request: Request,
    templateId: str = Query(..., description="模板ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """功能扩展 2：收藏或取消收藏，返回操作后是否已收藏"""
    user = await UserService.get_login_user(db, request)
    result = await PromptTemplateService.toggle_favorite(db, templateId, user.id)
    return BaseResponse(code=0, data=result, message="ok")
