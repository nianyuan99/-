"""
代码模式 HTTP 端到端验证脚本

不同于 verify_code_mode.py（直接调 service 层），本脚本走真实的 HTTP 接口，
验证「浏览器实际会拿到什么」：
1. 注册/登录拿到会话 Cookie
2. POST /conversation/code-mode/stream 能收到带 codeBlocks 的 done 事件
3. GET /conversation/{id}/messages 返回的 codeBlocks 是数组（不是 JSON 字符串）
4. POST /conversation/list/page/vo 的 codePreviewEnabled 筛选生效
5. 数据库里的 codeBlocks / codePreviewEnabled 落库正确
6. 清理测试数据

用法（后端已在 9090 端口运行时）：
    python -m app.scripts.verify_code_mode_http
"""

import asyncio
import json
import random
import sys

import httpx
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage

BASE = "http://127.0.0.1:9090/api"
# 默认用 nemotron：实测 nex-n2.5-mini 偶尔会「聊起来」而不写代码，
# 这里需要一个稳定产出 HTML 的模型来验证代码块提取链路。
TEST_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
TEST_PROMPT = "写一个最简单的HTML页面，红色标题写着 Hello，只要 HTML 不要说明文字。"

failures: list[str] = []

# 当前使用的测试账号（--seed-only 时要打印出来，供浏览器测试登录复用）
probe_account = ""


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' -> ' + detail) if detail else ''}")
    if not ok:
        failures.append(f"{name}: {detail}")


async def login(client: httpx.AsyncClient) -> bool:
    """注册或登录测试账号，成功后 Cookie 会写进 client"""
    global probe_account
    suffix = random.randint(100000, 999999)
    account = f"codemode_probe_{suffix}"
    probe_account = account
    payload = {
        "userAccount": account,
        "userPassword": "12345678",
        "checkPassword": "12345678",
        "userName": "代码模式验证",
    }
    resp = await client.post(f"{BASE}/user/register", json=payload)
    body = resp.json()
    if body.get("code") != 0:
        check("注册测试账号", False, str(body))
        return False

    resp = await client.post(
        f"{BASE}/user/login",
        json={"userAccount": account, "userPassword": "12345678"},
    )
    body = resp.json()
    if body.get("code") != 0:
        check("登录测试账号", False, str(body))
        return False

    check("注册并登录测试账号", True, account)
    return True


async def main() -> int:
    # 支持 --seed-only：只造一条代码会话并打印 conversationId（供浏览器测试复用，避免依赖模型连通性）
    seed_only = "--seed-only" in sys.argv

    async with httpx.AsyncClient(timeout=180.0) as client:
        if not await login(client):
            return 1

        # ---------- 1. 代码模式流式接口 ----------
        conversation_id = None
        done_chunk = None
        error_chunk = None
        chunk_count = 0

        print(f"\nPOST /conversation/code-mode/stream (model={TEST_MODEL}) ...")
        async with client.stream(
            "POST",
            f"{BASE}/conversation/code-mode/stream",
            json={"models": [TEST_MODEL], "prompt": TEST_PROMPT},
        ) as response:
            check("SSE 响应状态码 200", response.status_code == 200, str(response.status_code))
            check(
                "Content-Type 是 text/event-stream",
                "text/event-stream" in response.headers.get("content-type", ""),
                response.headers.get("content-type", ""),
            )
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                chunk_count += 1
                payload = json.loads(line[5:].strip())
                conversation_id = payload.get("conversationId") or conversation_id
                if payload.get("hasError"):
                    error_chunk = payload
                # done 事件一定带 fullContent 字段（内容可能为空）
                if payload.get("done") and "fullContent" in payload:
                    done_chunk = payload

        if seed_only:
            print(f"\nSEED_CONVERSATION_ID={conversation_id}")
            print(f"SEED_ACCOUNT={probe_account}")
            print("SEED_PASSWORD=12345678")
            return 0

        check("收到 SSE 事件", chunk_count > 0, f"{chunk_count} 个")
        check("流中无错误", error_chunk is None, str(error_chunk.get("error") if error_chunk else ""))
        check("收到 done 事件", done_chunk is not None)
        if not done_chunk:
            return await finish(conversation_id, None)

        blocks = done_chunk.get("codeBlocks") or []
        check("done 事件 hasCodeBlocks=true", done_chunk.get("hasCodeBlocks") is True)
        check("done 事件带回 codeBlocks", len(blocks) > 0, f"{len(blocks)} 个")
        if blocks:
            first = blocks[0]
            check("代码块语言为 html", first.get("language") == "html", str(first.get("language")))
            check("代码块带 sanitizedHtml", "sanitizedHtml" in first)
            check("代码内容像 HTML", "<" in (first.get("code") or ""))

        # ---------- 2. 消息查询接口：codeBlocks 必须是数组 ----------
        resp = await client.get(f"{BASE}/conversation/{conversation_id}/messages")
        body = resp.json()
        check("查询历史消息接口成功", body.get("code") == 0, str(body.get("message")))
        rows = body.get("data") or []
        assistant = [r for r in rows if r.get("role") == "assistant"]
        check("历史消息里有 assistant 回复", len(assistant) > 0, f"{len(assistant)} 条")
        if assistant:
            stored = assistant[0].get("codeBlocks")
            check(
                "历史消息 codeBlocks 反序列化为数组",
                isinstance(stored, list) and len(stored) > 0,
                f"type={type(stored).__name__}",
            )

        return await finish(conversation_id, client)


async def finish(conversation_id, client) -> int:
    # ---------- 3. 列表筛选 ----------
    if client is not None:
        resp = await client.post(
            f"{BASE}/conversation/list/page/vo",
            json={"codePreviewEnabled": True, "current": 1, "pageSize": 50},
        )
        body = resp.json()
        records = (body.get("data") or {}).get("records") or []
        check(
            "codePreviewEnabled=true 能筛出代码会话",
            any(r.get("id") == conversation_id for r in records),
            f"{len(records)} 条",
        )
        check(
            "筛出的会话 codePreviewEnabled 都是 1",
            all(r.get("codePreviewEnabled") == 1 for r in records),
        )

        resp = await client.post(
            f"{BASE}/conversation/list/page/vo",
            json={"codePreviewEnabled": False, "current": 1, "pageSize": 50},
        )
        records_false = (resp.json().get("data") or {}).get("records") or []
        check(
            "codePreviewEnabled=false 不包含代码会话",
            all(r.get("id") != conversation_id for r in records_false),
            f"{len(records_false)} 条",
        )
        check(
            "非代码会话 codePreviewEnabled 都是 0",
            all(r.get("codePreviewEnabled") == 0 for r in records_false),
        )

    # ---------- 4. 落库校验 ----------
    if conversation_id:
        async with AsyncSessionLocal() as db:
            conv = (
                await db.execute(select(Conversation).where(Conversation.id == conversation_id))
            ).scalar_one_or_none()
            check("对话已落库", conv is not None)
            if conv:
                check("库中 codePreviewEnabled=1", conv.code_preview_enabled == 1, str(conv.code_preview_enabled))

            rows = (
                await db.execute(
                    select(ConversationMessage).where(
                        ConversationMessage.conversation_id == conversation_id
                    )
                )
            ).scalars().all()
            assistant_rows = [r for r in rows if r.role == "assistant"]
            check("assistant 消息已落库", len(assistant_rows) > 0)
            if assistant_rows:
                check(
                    "库中 codeBlocks 非空",
                    bool(assistant_rows[0].code_blocks),
                    f"{len(assistant_rows[0].code_blocks or '')} 字节",
                )

        await cleanup(conversation_id)

    print()
    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        print(f"\n共 {len(failures)} 项失败")
        return 1
    print("全部通过：HTTP 接口 + 代码块提取 + 落库 + 列表筛选")
    return 0


async def cleanup(conversation_id: str) -> None:
    """清理测试产生的对话与消息（保留测试账号，避免影响用户表）"""
    async with AsyncSessionLocal() as db:
        conv = (
            await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        ).scalar_one_or_none()
        if conv:
            await db.delete(conv)
        rows = (
            await db.execute(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == conversation_id
                )
            )
        ).scalars().all()
        for row in rows:
            await db.delete(row)
        await db.commit()
    print(f"已清理测试对话 {conversation_id}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
