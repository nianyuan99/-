"""
业务异常定义与全局异常处理
"""

import logging
from enum import Enum

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ErrorCode(Enum):
    """
    错误码枚举
    """

    SUCCESS = (0, "ok")
    PARAMS_ERROR = (40000, "请求参数错误")
    NOT_LOGIN_ERROR = (40100, "未登录")
    NO_AUTH_ERROR = (40101, "无权限")
    NOT_FOUND_ERROR = (40400, "请求数据不存在")
    SYSTEM_ERROR = (50000, "系统内部异常")
    OPERATION_ERROR = (50001, "操作失败")

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


class BusinessException(HTTPException):
    """
    业务异常类

    业务错误不算 HTTP 层面的错误，状态码固定为 200，
    通过响应体中的 code 字段区分成功与失败，与前端约定保持一致。
    """

    def __init__(self, error_code: ErrorCode, detail: str = None):
        self.error_code = error_code
        message = detail if detail else error_code.message
        super().__init__(status_code=status.HTTP_200_OK, detail=message)
        self.code = error_code.code


async def business_exception_handler(request, exc: BusinessException) -> JSONResponse:
    """
    业务异常处理器：把业务异常统一转换为 BaseResponse 格式
    """
    logger.warning("业务异常: code=%s, message=%s, path=%s", exc.code, exc.detail, request.url.path)
    return JSONResponse(
        status_code=200,
        content={
            "code": exc.code,
            "data": None,
            "message": exc.detail,
        },
    )


async def global_exception_handler(request, exc: Exception) -> JSONResponse:
    """
    全局兜底异常处理器
    """
    logger.exception("系统异常: path=%s", request.url.path)
    return JSONResponse(
        status_code=200,
        content={
            "code": 50000,
            "data": None,
            "message": "系统内部异常",
        },
    )
