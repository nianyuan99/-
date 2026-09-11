"""
SockJS / STOMP 协议实现

为什么要手写：前端用的是 `sockjs-client` + `@stomp/stompjs`，
SockJS 的握手路径带有随机前缀（/ws/{server}/{session}/websocket），
STOMP 又是一套自己的文本帧协议。Python 后端没有 Java 版现成的
spring-websocket 支持，所以这里按协议实现最小可用子集，
好处是前端代码与 Java 版完全一致，后端可以无缝切换。

只实现前端实际会用到的东西：
- SockJS：/info 握手信息 + websocket 传输（sockjs-client 优先走 WebSocket）
- STOMP：CONNECT / SUBSCRIBE / UNSUBSCRIBE / DISCONNECT 与 MESSAGE 帧
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Dict, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# STOMP 帧以 NULL 结尾
NULL = "\x00"
# SockJS 在 WebSocket 帧之外还会发一个 'o'（open）帧，STOMP 消息本身用数组包裹
SOCKJS_OPEN_FRAME = "o"
# SockJS 服务端下发「一批消息」的帧类型前缀：格式为 a["msg1","msg2"]
# 少了这个前缀，sockjs-client 会把 JSON 数组的 '[' 当成帧类型，
# 后面的 JSON.parse 必然失败（调试日志里的 "bad json"），消息被静默丢弃。
SOCKJS_MESSAGE_FRAME = "a"

# SockJS 协议要求的握手信息
SOCKJS_SERVER_VERSION = "0.3.3"

# 单条 WebSocket 消息的最大长度（SockJS 帧里是 JSON 数组，留足余量）
MAX_FRAME_LENGTH = 256 * 1024


def build_sockjs_info(websocket: bool = True) -> Dict[str, Any]:
    """构造 SockJS /info 响应"""
    return {
        "websocket": websocket,
        "cookie_needed": True,
        "origins": ["*:*"],
        "entropy": 1234567,
    }


class StompSession:
    """
    单个 WebSocket 连接上的 STOMP 会话

    一个连接可以订阅多个目的地，因此内部维护 subId -> destination 的映射，
    广播时按 subId 回填到 MESSAGE 帧的 subscription 头里，前端才能对上号。

    sockjs_framing 决定出站帧的封装方式（踩过的坑）：
    SockJS 规定服务端发出的每一帧都必须是 JSON 数组包起来的字符串，
    直接发裸 STOMP 帧会被 sockjs-client 判为 "bad json" 并丢弃
    （表现：浏览器永远收不到 CONNECTED / MESSAGE，而裸 WebSocket 客户端却一切正常）。
    """

    def __init__(self, websocket: WebSocket, session_id: str, sockjs_framing: bool = True):
        self.websocket = websocket
        self.session_id = session_id
        self.sockjs_framing = sockjs_framing
        self.subscriptions: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    async def send_sockjs_open(self) -> None:
        """发送 SockJS 的 open 帧，告诉客户端可以开始发 STOMP 帧了"""
        await self._send_raw(SOCKJS_OPEN_FRAME)

    async def send_stomp_frame(self, frame: str) -> None:
        """
        发送一帧 STOMP

        SockJS 传输下必须封装成 `a["<stomp 帧>"]`：
        'a' 是「服务端消息数组」的帧类型前缀，数组里每项是一条消息。
        """
        payload = (
            SOCKJS_MESSAGE_FRAME + json.dumps([frame]) if self.sockjs_framing else frame
        )
        await self._send_raw(payload)

    async def send_stomp_message(self, destination: str, body: str, sub_id: str) -> None:
        """发送 STOMP MESSAGE 帧"""
        headers = [
            "MESSAGE",
            f"destination:{destination}",
            f"subscription:{sub_id}",
            "message-id:" + f"{self.session_id}-{sub_id}",
            "content-type:application/json;charset=UTF-8",
            f"content-length:{len(body.encode('utf-8'))}",
        ]
        frame = "\n".join(headers) + "\n\n" + body + NULL
        await self.send_stomp_frame(frame)

    async def close(self) -> None:
        """关闭连接（幂等，重复调用不会报错）"""
        self._closed = True
        try:
            await self.websocket.close()
        except Exception:
            # 客户端已经先断开时 close 会抛异常，这里忽略即可
            pass

    async def _send_raw(self, text: str) -> None:
        if self._closed:
            return
        async with self._lock:
            try:
                await self.websocket.send_text(text)
            except Exception as e:
                self._closed = True
                logger.debug("WebSocket 发送失败，标记连接已关闭: sessionId=%s, error=%s", self.session_id, e)


class ConnectionManager:
    """
    WebSocket 连接管理器

    维护 task_id -> {连接key -> StompSession} 的嵌套字典，
    广播时只推给订阅了该任务的连接，避免把所有进度消息发给所有人。
    """

    def __init__(self):
        self.active_connections: Dict[str, Dict[str, StompSession]] = defaultdict(dict)

    def subscribe(self, session: StompSession, sub_id: str, destination: str) -> str:
        """
        订阅某个目的地

        任务进度用 /topic/task/{taskId} 的形式，这里从中解析出 taskId；
        其他目的地（如 /user/queue/xxx）按原样作为 key 使用。
        """
        task_id = parse_task_id_from_destination(destination)
        session.subscriptions[sub_id] = destination
        key = self._connection_key(session, sub_id)
        self.active_connections[task_id][key] = session
        logger.info("WebSocket 订阅成功: taskId=%s, sessionId=%s", task_id, session.session_id)
        return task_id

    def unsubscribe(self, session: StompSession, sub_id: Optional[str], destination: Optional[str]) -> None:
        """
        取消订阅：subId 与 destination 至少传一个

        前端取消订阅时一般只带 id，但协议上 destination 也可能出现，
        所以两者都作为兜底条件，按「会话 + 订阅」精确定位要删的连接键。
        """
        if sub_id:
            session.subscriptions.pop(sub_id, None)
        elif destination and destination in session.subscriptions.values():
            for key, value in list(session.subscriptions.items()):
                if value == destination:
                    sub_id = key
                    session.subscriptions.pop(key, None)
                    break

        if not sub_id:
            logger.debug("收到无法定位的 UNSUBSCRIBE: sessionId=%s", session.session_id)
            return

        connection_key = self._connection_key(session, sub_id)
        for connections in self.active_connections.values():
            connections.pop(connection_key, None)
        logger.info("WebSocket 取消订阅: sessionId=%s, subId=%s", session.session_id, sub_id)

    def disconnect(self, session: StompSession) -> None:
        """连接断开：清理该连接的所有订阅"""
        for task_id, connections in list(self.active_connections.items()):
            for key, conn in list(connections.items()):
                if conn is session:
                    del connections[key]
            if not connections:
                self.active_connections.pop(task_id, None)

    async def broadcast_to_task(self, task_id: str, message: Dict[str, Any]) -> None:
        """向订阅了该任务的所有连接广播进度"""
        key = str(task_id)
        connections = self.active_connections.get(key)
        if not connections:
            return

        body = json.dumps(message, ensure_ascii=False, default=str)
        destination = f"/topic/task/{key}"
        # 复制一份再遍历：发送过程中可能有连接断开并修改字典
        for conn_key, session in list(connections.items()):
            sub_id = conn_key.split("|", 1)[1] if "|" in conn_key else conn_key
            if session.closed:
                self._remove(conn_key)
                continue
            try:
                await session.send_stomp_message(destination, body, sub_id)
            except Exception as e:
                logger.debug("进度广播失败: taskId=%s, error=%s", task_id, e)

    def has_subscribers(self, task_id: str) -> bool:
        """该任务当前是否有活跃订阅（无订阅时可跳过推送）"""
        key = str(task_id)
        return bool(self.active_connections.get(key))

    def _remove(self, connection_key: str) -> None:
        for connections in self.active_connections.values():
            if connection_key in connections:
                del connections[connection_key]

    @staticmethod
    def _connection_key(session: StompSession, sub_id: str) -> str:
        """连接键：同一连接订阅多次会有多个 key，用 '|' 分隔会话与订阅"""
        return f"{session.session_id}|{sub_id}"


def parse_task_id_from_destination(destination: str) -> str:
    """
    从 STOMP 目的地解析任务 ID

    /topic/task/{taskId} → {taskId}；不是任务主题时原样返回，
    保证用户队列之类的其他目的地也能正常订阅。
    """
    prefix = "/topic/task/"
    if destination.startswith(prefix):
        return destination[len(prefix) :]
    return destination


def parse_stomp_frames(raw_text: str) -> list:
    """
    解析收到的 STOMP 帧

    SockJS 传输过来的可能是：
    - 'o'：open 帧，忽略
    - 'h'：heartbeat 帧，忽略
    - 'c[...]'：关闭帧，需要断开连接
    - '["CONNECT\\n...\\u0000"]'：JSON 数组包裹的 STOMP 帧
    - 裸 STOMP 帧（非 SockJS 客户端直接连原生 WebSocket 时）
    """
    if raw_text == SOCKJS_OPEN_FRAME or raw_text == "h":
        return []

    if raw_text.startswith("c"):
        return [{"command": "DISCONNECT", "headers": {}, "body": ""}]

    frames: list = []
    payloads = []
    if raw_text.startswith("["):
        try:
            parsed = json.loads(raw_text)
            payloads = [item for item in parsed if isinstance(item, str)]
        except (ValueError, TypeError):
            logger.warning("解析 SockJS 帧失败: %s", raw_text[:200])
            return []
    else:
        payloads = [raw_text]

    for payload in payloads:
        for frame_text in payload.split(NULL):
            frame = _parse_single_frame(frame_text)
            if frame:
                frames.append(frame)
    return frames


def _parse_single_frame(frame_text: str) -> Optional[Dict[str, Any]]:
    """解析单个 STOMP 帧文本"""
    text = frame_text.strip("\n")
    if not text.strip():
        return None

    if "\n\n" in text:
        header_part, body = text.split("\n\n", 1)
    else:
        header_part, body = text, ""

    lines = [line for line in header_part.split("\n") if line.strip()]
    if not lines:
        return None

    command = lines[0].strip()
    headers: Dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip()] = value.strip()

    return {"command": command, "headers": headers, "body": body}


# 全局唯一的连接管理器
manager = ConnectionManager()
