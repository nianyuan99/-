"""
WebSocket（SockJS + STOMP）路由

前端通过 `sockjs-client` 连接 `${baseUrl}/ws`，sockjs-client 会先请求
`/ws/info` 拿握手信息，然后建立 `/ws/{server}/{session}/websocket` 连接，
在连接上跑 STOMP 协议订阅 `/topic/task/{taskId}` 接收批量测试进度。

订阅鉴权：SockJS 握手会带上浏览器 Cookie，这里直接复用 Redis Session
读取登录态，确认该任务的归属用户后才会推送，避免任务进度被他人订阅。
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.constants import USER_LOGIN_STATE
from app.db.session import AsyncSessionLocal
from app.middleware.session_middleware import session_backend
from app.models.test_task import TestTask
from app.services.progress_service import send_current_progress
from app.ws.stomp_handler import (
    StompSession,
    build_sockjs_info,
    manager,
    parse_stomp_frames,
    parse_task_id_from_destination,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])

# STOMP 心跳间隔（秒）
HEARTBEAT_INTERVAL = 10


@router.get("/info", summary="SockJS 握手信息")
async def sockjs_info():
    """sockjs-client 建立连接前会先请求这个地址"""
    return JSONResponse(build_sockjs_info())


@router.get("/{server_id}/{session_id}/info", summary="SockJS 传输握手信息")
async def sockjs_transport_info(server_id: str, session_id: str):
    """
    SockJS 为每个具体传输请求的握手信息

    这是踩过的坑：sockjs-client 在挑选传输时会先请求
    `${url}/{server-id}/{session-id}/info`（例如 /ws/123/abc/info）来确认该传输是否被服务端支持。
    如果这里 404，即使真正的 /websocket 端点存在，客户端也会认为服务端不支持 WebSocket 传输，
    从而降级到 XHR（本实现未提供），最终表现为连接直接关闭、STOMP 握手无法完成。
    """
    return JSONResponse(build_sockjs_info())


@router.websocket("/{server_id}/{session_id}/websocket")
async def sockjs_websocket(websocket: WebSocket, server_id: str, session_id: str):
    """SockJS WebSocket 传输端点"""
    # Sec-WebSocket-Protocol 协商：stompjs 经由 SockJS 时不会带这个头，
    # 但浏览器原生 WebSocket 直连（例如自己写的客户端）会带 'stomp'/'v12.stomp'，
    # 服务端不回显子协议时浏览器会判定协商失败并直接断开连接。
    requested = websocket.headers.get("sec-websocket-protocol")
    subprotocol = None
    if requested:
        protocols = [p.strip() for p in requested.split(",") if p.strip()]
        for candidate in ("v12.stomp", "v11.stomp", "v10.stomp", "stomp"):
            if candidate in protocols:
                subprotocol = candidate
                break

    await websocket.accept(subprotocol=subprotocol)

    # SockJS 规定连接建立后先发一个 'o' 帧
    session = StompSession(websocket, f"{server_id}_{session_id}")
    await session.send_sockjs_open()

    # 从握手 Cookie 中读取登录态（SockJS 会带上同源 Cookie）
    user_id = await _resolve_login_user_id(websocket)
    if user_id is None:
        # 未登录：先完成 STOMP 握手再报错，前端能拿到明确原因而不是看到连接莫名断开
        await _reject_unauthenticated(session)
        return

    heartbeat_task = asyncio.create_task(_heartbeat_loop(session))

    try:
        while True:
            raw_text = await websocket.receive_text()
            for frame in parse_stomp_frames(raw_text):
                command = frame.get("command")
                if command == "CONNECT":
                    await _handle_connect(session)
                elif command == "SUBSCRIBE":
                    await _handle_subscribe(session, frame, user_id)
                elif command == "UNSUBSCRIBE":
                    manager.unsubscribe(
                        session,
                        frame["headers"].get("id"),
                        frame["headers"].get("destination"),
                    )
                elif command == "DISCONNECT":
                    await session.close()
                    return
                elif command in ("SEND", "ACK", "NACK"):
                    # 批量测试的进度推送是单向的，客户端不需要发送业务消息
                    logger.debug("忽略客户端 STOMP 命令: %s", command)
                elif command:
                    logger.debug("未支持的 STOMP 命令: %s", command)
    except WebSocketDisconnect:
        logger.info("WebSocket 连接已断开: sessionId=%s", session.session_id)
    except Exception as e:
        logger.warning("WebSocket 会话异常: sessionId=%s, error=%s", session.session_id, e)
    finally:
        heartbeat_task.cancel()
        manager.disconnect(session)
        await session.close()


async def _handle_connect(session: StompSession) -> None:
    """响应 STOMP CONNECT，回 CONNECTED 帧"""
    frame = "CONNECTED\nversion:1.2\nheart-beat:0,0\nserver:ai-eval-python\n\n" + "\x00"
    await session.send_stomp_frame(frame)


async def _handle_subscribe(session: StompSession, frame: Dict[str, Any], user_id: int) -> None:
    """处理 STOMP SUBSCRIBE：校验任务归属后建立订阅并补推当前进度"""
    headers = frame.get("headers", {})
    sub_id = headers.get("id")
    destination = headers.get("destination")
    if not sub_id or not destination:
        await _send_error(session, "SUBSCRIBE 缺少 id 或 destination")
        return

    task_id = parse_task_id_from_destination(destination)

    # 只有 /topic/task/{taskId} 这类任务主题需要做归属校验，其他目的地直接放行
    if destination.startswith("/topic/task/"):
        owned = await _check_task_owner(task_id, user_id)
        if not owned:
            await _send_error(session, "任务不存在或无权查看")
            return

    manager.subscribe(session, sub_id, destination)

    if destination.startswith("/topic/task/"):
        # 任务可能在建立连接前就已经开始甚至完成，这里立即补推一次快照
        asyncio.create_task(send_current_progress(task_id))


async def _reject_unauthenticated(session: StompSession) -> None:
    """未登录连接的兜底：回一条 CONNECTED + ERROR，让前端日志里能看到原因"""
    await _handle_connect(session)
    await _send_error(session, "未登录，无法订阅任务进度")
    await asyncio.sleep(0.2)
    await session.close()


async def _send_error(session: StompSession, message: str) -> None:
    """发送 STOMP ERROR 帧"""
    frame = f"ERROR\nmessage:{message}\ncontent-length:0\n\n\x00"
    await session.send_stomp_frame(frame)
    logger.info("已向客户端返回 STOMP 错误: sessionId=%s, message=%s", session.session_id, message)


async def _heartbeat_loop(session: StompSession) -> None:
    """定期发送 SockJS 心跳帧，保持连接不被中间层判定为空闲断开"""
    try:
        while not session.closed:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            await session.send_stomp_frame("h")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.debug("心跳发送结束: sessionId=%s, error=%s", session.session_id, e)


async def _resolve_login_user_id(websocket: WebSocket) -> Optional[int]:
    """从 WebSocket 握手的 Cookie 中解析登录用户 ID，未登录返回 None"""
    session_id = websocket.cookies.get("session_id")
    if not session_id:
        return None
    try:
        if not await session_backend.exists(session_id):
            return None
        session_data = await session_backend.get(session_id)
    except Exception as e:
        logger.warning("读取 WebSocket 登录态失败: %s", e)
        return None

    user_info = (session_data or {}).get(USER_LOGIN_STATE)
    if not user_info or not user_info.get("id"):
        return None
    return user_info["id"]


async def _check_task_owner(task_id: str, user_id: int) -> bool:
    """校验任务是否属于该用户"""
    from sqlalchemy import select

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(TestTask).where(TestTask.id == task_id, TestTask.is_delete == 0)
            )
            task = result.scalar_one_or_none()
    except Exception as e:
        logger.warning("校验任务归属失败: taskId=%s, error=%s", task_id, e)
        return False

    if not task:
        return False
    return task.user_id == user_id
