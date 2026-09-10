"""
对话接口层

包含 Side-by-Side 多模型并排对比的 SSE 流式接口，以及对话历史查询接口。
"""

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import get_async_redis
from app.db.session import get_async_db
from app.schemas.conversation import (
    ConversationMessageVO,
    ConversationQueryRequest,
    GenerateVariantsRequest,
    PromptLabRequest,
    SideBySideRequest,
)
from app.schemas.user import BaseResponse
from app.services.conversation_service import ConversationService
from app.services.user_service import UserService
from app.utils.rate_limit import RateLimitType, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversation", tags=["对话接口"])


def _get_redis(_http_request: Request):
    """获取异步 Redis 客户端（供限流使用）"""
    return get_async_redis()


async def _stream_with_disconnect_check(
    generator: AsyncGenerator[str, None], http_request: Request
) -> AsyncGenerator[str, None]:
    """
    包装业务生成器，保证客户端断开后立刻释放资源

    Starlette 在客户端断开时确实会主动关闭本生成器（抛 GeneratorExit），
    但它的 disconnect 监听任务会先把 http.disconnect 消息消费掉，
    因此这里再调 is_disconnected() 往往已经拿不到消息。所以做了两层保险：

    1. 每次推送前主动检测一次断开，在「消息尚未被消费」的情况下能更早退出；
    2. finally 中显式 aclose 业务生成器 —— 这一条才是关键，
       它让 ConversationService 的 finally 分支确定性地执行，
       取消所有在途的模型调用（对应前端「停止生成」），真正省下 API 额度。
    """
    try:
        async for event in generator:
            if await http_request.is_disconnected():
                logger.info("客户端已断开，停止推送并取消未完成的模型调用")
                break
            yield event
    finally:
        # 显式关闭，保证业务侧的 async for 立刻收到 GeneratorExit 并执行清理逻辑
        await generator.aclose()


@router.post("/side-by-side/stream", summary="Side-by-Side多模型并排对比(流式)")
async def side_by_side_stream(
    request_data: SideBySideRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Side-by-Side 多模型并排对比（SSE 流式响应）"""
    # 限流检查：AI 调用成本高，按用户维度限制每分钟 5 次
    await check_rate_limit(
        _get_redis(http_request),
        http_request,
        RateLimitType.USER,
        5,
        60,
        message="AI 对话请求过于频繁，请稍后再试",
    )
    # 获取登录用户
    login_user = await UserService.get_login_user(db, http_request)

    conversation_service = ConversationService(db, _get_redis(http_request))

    return StreamingResponse(
        _stream_with_disconnect_check(
            conversation_service.side_by_side_stream(request_data, login_user.id),
            http_request,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 告诉 Nginx 不要缓冲 SSE，否则打字机效果会变成一次性输出
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/prompt-lab/stream", summary="Prompt Lab单模型多提示词对比(流式)")
async def prompt_lab_stream(
    request_data: PromptLabRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Prompt Lab 单模型多提示词对比（SSE 流式响应）"""
    # 限流检查：一次请求会并发调用同一个模型 N 次，成本比 Side-by-Side 更集中
    await check_rate_limit(
        _get_redis(http_request),
        http_request,
        RateLimitType.USER,
        5,
        60,
        message="AI 对话请求过于频繁，请稍后再试",
    )
    login_user = await UserService.get_login_user(db, http_request)

    conversation_service = ConversationService(db, _get_redis(http_request))

    # 参数 / 安全校验必须放在建流之前：
    # prompt_lab_stream 是异步生成器，里面的 BusinessException 要等到响应体开始推送才抛出，
    # 那时 HTTP 头已经发出（200 + text/event-stream），异常没法再转成统一的 BaseResponse，
    # 前端只能拿到一个空流（表现为「连接已中断」），看不到具体原因。
    # 服务内部仍保留同一份校验，手动调用该服务时同样安全。
    conversation_service._validate_prompt_lab_request(request_data)

    return StreamingResponse(
        _stream_with_disconnect_check(
            conversation_service.prompt_lab_stream(request_data, login_user.id),
            http_request,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/prompt-lab/generate-variants",
    response_model=BaseResponse[list[str]],
    summary="变体自动生成",
)
async def generate_prompt_variants(
    request_data: GenerateVariantsRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    变体自动生成：传一个基础提示词，返回 N 个不同风格的变体。
    用于在 Prompt Lab 页面帮用户一键填充变体输入框。
    """
    await check_rate_limit(
        _get_redis(http_request),
        http_request,
        RateLimitType.USER,
        5,
        60,
        message="AI 对话请求过于频繁，请稍后再试",
    )
    login_user = await UserService.get_login_user(db, http_request)
    conversation_service = ConversationService(db, _get_redis(http_request))
    variants = await conversation_service.generate_variants(request_data)
    return BaseResponse(code=0, data=variants, message="ok")


@router.post(
    "/list/page/vo",
    response_model=BaseResponse[dict],
    summary="分页查询我的对话列表",
)
async def list_conversation_vo_by_page(
    query_request: ConversationQueryRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """分页查询当前登录用户的对话列表"""
    login_user = await UserService.get_login_user(db, http_request)
    conversation_service = ConversationService(db, _get_redis(http_request))
    page_result = await conversation_service.list_conversations(
        user_id=login_user.id,
        conversation_type=query_request.conversation_type,
        current=query_request.current,
        page_size=query_request.page_size,
    )
    return BaseResponse(code=0, data=page_result, message="ok")


@router.get(
    "/{conversation_id}/messages",
    response_model=BaseResponse[list[ConversationMessageVO]],
    summary="查询对话的历史消息",
)
async def list_conversation_messages(
    conversation_id: str,
    http_request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """查询某个对话的全部消息（同一轮会有多条不同模型的回复）"""
    login_user = await UserService.get_login_user(db, http_request)
    conversation_service = ConversationService(db, _get_redis(http_request))
    messages = await conversation_service.get_conversation_messages(conversation_id, login_user.id)
    return BaseResponse(code=0, data=messages, message="ok")
