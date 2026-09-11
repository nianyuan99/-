"""
批量测试接口层

包含批量测试任务的创建 / 查询 / 删除 / 取消、测试结果查询与评分，
以及数据统计概览接口。
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import get_async_redis
from app.db.session import get_async_db
from app.schemas.batch_test import (
    BatchTestTaskQueryRequest,
    CreateBatchTestRequest,
    DeleteBatchTestTaskRequest,
    StatisticsOverviewVO,
    TestResultVO,
    TestTaskVO,
    UpdateResultRatingRequest,
)
from app.schemas.user import BaseResponse
from app.services.batch_test_service import BatchTestService
from app.services.user_service import UserService
from app.utils.rate_limit import RateLimitType, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch-test", tags=["批量测试接口"])


def _get_redis(_http_request: Request):
    """获取异步 Redis 客户端（供限流使用）"""
    return get_async_redis()


# ============ 任务 ============


@router.post("/create", response_model=BaseResponse[str], summary="创建批量测试任务")
async def create_batch_test_task(
    request_body: CreateBatchTestRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    创建批量测试任务

    限流：每用户 60 秒内最多创建 3 次。一个任务会触发「模型数 × 提示词数」次模型调用，
    不加限制很容易把 API 额度打满。
    """
    await check_rate_limit(
        _get_redis(request),
        request,
        RateLimitType.USER,
        3,
        60,
        message="批量测试创建过于频繁，请稍后再试",
    )
    user = await UserService.get_login_user(db, request)
    req_data = request_body.model_dump(exclude_none=True)
    task_id = await BatchTestService.create_batch_test_task(db, req_data, user.id)
    return BaseResponse(code=0, data=task_id, message="ok")


@router.get("/task/get", response_model=BaseResponse[TestTaskVO], summary="获取任务详情")
async def get_batch_test_task(
    request: Request,
    id: str = Query(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """获取任务详情（任务进度也可通过前端轮询该接口获取，WebSocket 用于实时推送）"""
    user = await UserService.get_login_user(db, request)
    task = await BatchTestService.get_task(db, id, user.id)
    return BaseResponse(code=0, data=task, message="ok")


@router.post("/task/list/page", response_model=BaseResponse[dict], summary="分页查询任务列表")
async def list_batch_test_task_by_page(
    query_request: BatchTestTaskQueryRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """分页查询当前用户的批量测试任务"""
    user = await UserService.get_login_user(db, request)
    page_result = await BatchTestService.list_tasks_by_page(db, query_request, user.id)
    return BaseResponse(code=0, data=page_result, message="ok")


@router.post("/task/delete", response_model=BaseResponse[bool], summary="删除任务")
async def delete_batch_test_task(
    request_body: DeleteBatchTestTaskRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """删除任务（逻辑删除，同时逻辑删除其测试结果）"""
    user = await UserService.get_login_user(db, request)
    result = await BatchTestService.delete_task(db, request_body.id, user.id)
    return BaseResponse(code=0, data=result, message="ok")


@router.post("/task/cancel", response_model=BaseResponse[bool], summary="取消任务")
async def cancel_batch_test_task(
    request_body: DeleteBatchTestTaskRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    取消任务

    Worker 在执行每个子任务前检查任务状态，发现已取消即跳过，
    因此在途请求会跑完，但不会再有新的模型调用被发起。
    """
    user = await UserService.get_login_user(db, request)
    result = await BatchTestService.cancel_task(db, request_body.id, user.id)
    return BaseResponse(code=0, data=result, message="ok")


# ============ 结果 ============


@router.get("/result/list", response_model=BaseResponse[List[TestResultVO]], summary="获取任务的测试结果")
async def list_batch_test_result(
    request: Request,
    taskId: str = Query(..., description="任务ID"),
    modelName: Optional[str] = Query(None, description="按模型筛选（可选）"),
    db: AsyncSession = Depends(get_async_db),
):
    """查询任务的测试结果，可按模型筛选"""
    user = await UserService.get_login_user(db, request)
    results = await BatchTestService.list_task_results(db, taskId, user.id, modelName)
    return BaseResponse(code=0, data=results, message="ok")


@router.post("/result/rating", response_model=BaseResponse[bool], summary="更新测试结果评分")
async def update_batch_test_result_rating(
    request_body: UpdateResultRatingRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """更新测试结果的用户评分（1-5 分）"""
    user = await UserService.get_login_user(db, request)
    result = await BatchTestService.update_result_rating(
        db, request_body.id, request_body.user_rating, user.id
    )
    return BaseResponse(code=0, data=result, message="ok")


# ============ 数据统计 ============


@router.get("/statistics/overview", response_model=BaseResponse[StatisticsOverviewVO], summary="数据统计概览")
async def get_statistics_overview(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """当前用户的数据统计概览：任务数、结果数、Token 与成本，以及按模型维度的明细"""
    user = await UserService.get_login_user(db, request)
    overview = await BatchTestService.get_statistics_overview(db, user.id)
    return BaseResponse(code=0, data=overview, message="ok")
