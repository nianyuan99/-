"""
场景管理接口层

提供测试场景与其提示词的 RESTful 接口。
权限：预设场景所有人可见但不可改；自定义场景仅创建者可见可改。
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from app.schemas.scene import (
    AddScenePromptRequest,
    CreateSceneRequest,
    DeleteScenePromptRequest,
    DeleteSceneRequest,
    SceneDetailVO,
    ScenePromptVO,
    SceneQueryRequest,
    SceneVO,
    UpdateScenePromptRequest,
    UpdateSceneRequest,
)
from app.schemas.user import BaseResponse
from app.services.scene_service import SceneService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scene", tags=["场景管理接口"])


@router.post("/create", response_model=BaseResponse[str], summary="创建场景")
async def create_scene(
    request_body: CreateSceneRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """创建自定义场景（预设场景不可通过接口创建）"""
    user = await UserService.get_login_user(db, request)
    scene_data = request_body.model_dump(exclude_none=True)
    scene_id = await SceneService.create_scene(db, scene_data, user.id)
    return BaseResponse(code=0, data=scene_id, message="ok")


@router.post("/update", response_model=BaseResponse[bool], summary="更新场景")
async def update_scene(
    request_body: UpdateSceneRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """更新场景信息（仅自定义场景）"""
    user = await UserService.get_login_user(db, request)
    scene_data = request_body.model_dump(exclude_none=True)
    result = await SceneService.update_scene(db, scene_data, user.id)
    return BaseResponse(code=0, data=result, message="ok")


@router.post("/delete", response_model=BaseResponse[bool], summary="删除场景")
async def delete_scene(
    request_body: DeleteSceneRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """删除场景（逻辑删除，已有测试任务的场景不允许删除）"""
    user = await UserService.get_login_user(db, request)
    result = await SceneService.delete_scene(db, request_body.id, user.id)
    return BaseResponse(code=0, data=result, message="ok")


@router.get("/get", response_model=BaseResponse[SceneDetailVO], summary="获取场景详情")
async def get_scene(
    request: Request,
    id: str = Query(..., description="场景ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """获取场景详情（含提示词列表）"""
    user = await UserService.get_login_user(db, request)
    detail = await SceneService.get_scene_detail(db, id, user.id)
    return BaseResponse(code=0, data=detail, message="ok")


@router.post("/list/page", response_model=BaseResponse[dict], summary="分页查询场景列表")
async def list_scene_by_page(
    query_request: SceneQueryRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """分页查询场景列表（预设场景 + 自己创建的自定义场景）"""
    user = await UserService.get_login_user(db, request)
    page_result = await SceneService.list_scenes_by_page(db, query_request, user.id)
    return BaseResponse(code=0, data=page_result, message="ok")


@router.get("/list/available", response_model=BaseResponse[List[SceneVO]], summary="查询可用场景（供批量测试选择）")
async def list_available_scenes(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """查询启用中的场景列表，供批量测试页面选择场景"""
    user = await UserService.get_login_user(db, request)
    scenes = await SceneService.list_available_scenes(db, user.id)
    return BaseResponse(code=0, data=scenes, message="ok")


@router.get("/categories", response_model=BaseResponse[List[str]], summary="查询场景分类")
async def list_scene_categories(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """查询当前用户可见的场景分类（供筛选下拉框使用）"""
    user = await UserService.get_login_user(db, request)
    categories = await SceneService.list_categories(db, user.id)
    return BaseResponse(code=0, data=categories, message="ok")


@router.get("/prompts", response_model=BaseResponse[List[ScenePromptVO]], summary="获取场景的提示词列表")
async def list_scene_prompts(
    request: Request,
    sceneId: str = Query(..., description="场景ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """查询场景下的提示词列表（按序号升序）"""
    user = await UserService.get_login_user(db, request)
    prompts = await SceneService.list_scene_prompts(db, sceneId, user.id)
    return BaseResponse(code=0, data=prompts, message="ok")


@router.post("/prompt/add", response_model=BaseResponse[str], summary="添加提示词")
async def add_scene_prompt(
    request_body: AddScenePromptRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """向自定义场景添加提示词（序号由服务端自动计算）"""
    user = await UserService.get_login_user(db, request)
    prompt_data = request_body.model_dump(exclude_none=True)
    prompt_id = await SceneService.add_scene_prompt(db, prompt_data, user.id)
    return BaseResponse(code=0, data=prompt_id, message="ok")


@router.post("/prompt/update", response_model=BaseResponse[bool], summary="更新提示词")
async def update_scene_prompt(
    request_body: UpdateScenePromptRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """更新提示词（预设场景的提示词不可修改）"""
    user = await UserService.get_login_user(db, request)
    prompt_data = request_body.model_dump(exclude_none=True)
    result = await SceneService.update_scene_prompt(db, prompt_data, user.id)
    return BaseResponse(code=0, data=result, message="ok")


@router.post("/prompt/delete", response_model=BaseResponse[bool], summary="删除提示词")
async def delete_scene_prompt(
    request_body: DeleteScenePromptRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """删除提示词（逻辑删除并重排剩余提示词序号）"""
    user = await UserService.get_login_user(db, request)
    result = await SceneService.delete_scene_prompt(db, request_body.id, user.id)
    return BaseResponse(code=0, data=result, message="ok")
