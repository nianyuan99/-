"""
报告接口层

`/report/generate` 按任务 ID 生成多维度对比报告：摘要 + 各模型统计 + 雷达图/柱状图 + 详细结果。
"""

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from app.exceptions import BusinessException, ErrorCode
from app.schemas.report import ReportVO
from app.schemas.user import BaseResponse
from app.services.report_service import ReportService
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["报告接口"])


@router.get("/generate", response_model=BaseResponse[ReportVO], summary="生成测试报告")
async def generate_report(
    request: Request,
    taskId: str = Query(..., description="任务ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    根据任务ID生成多维度对比报告
    """
    if not taskId or not taskId.strip():
        raise BusinessException(ErrorCode.PARAMS_ERROR, "任务ID不能为空")

    user = await UserService.get_login_user(db, request)
    report = await ReportService.generate_report(db, taskId.strip(), user.id)
    return BaseResponse(code=0, data=report, message="ok")
