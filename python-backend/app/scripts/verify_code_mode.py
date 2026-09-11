"""
代码模式后端集成自测脚本

用真实的模型调用跑一遍 code_mode_stream，验证：
1. 系统提示词注入生效（模型按 HTML 单文件格式输出）
2. 流式 done 事件里带回 codeBlocks
3. codeBlocks 正确落库（conversation_message.codeBlocks）

用法（在 python-backend 目录下）：
    venv\\Scripts\\python.exe -m app.scripts.verify_code_mode
"""

import asyncio
import json
import sys

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.schemas.conversation import CodeModeRequest
from app.services.conversation_service import ConversationService

# 用免费模型跑，避免付费模型 402
TEST_MODEL = "nex-agi/nex-n2.5-mini:free"
TEST_PROMPT = "帮我写一个最简单的HTML页面，页面上有一个红色标题写着 Hello，不需要任何交互。"
TEST_USER_ID = 1  # 仅用于写库归属，脚本跑完会清理


async def main() -> int:
    async with AsyncSessionLocal() as db:
        service = ConversationService(db)
        request = CodeModeRequest(models=[TEST_MODEL], prompt=TEST_PROMPT)

        conversation_id = None
        done_chunk = None
        chunk_count = 0
        error_chunk = None

        print(f"开始调用 model={TEST_MODEL} ...")
        async for event in service.code_mode_stream(request, TEST_USER_ID):
            if not event.startswith("data: "):
                continue
            payload = json.loads(event[6:].strip())
            chunk_count += 1
            conversation_id = payload.get("conversationId") or conversation_id
            if payload.get("hasError"):
                error_chunk = payload
                print("!! 模型返回错误:", payload.get("error"))
            if payload.get("done") and payload.get("fullContent") is not None:
                done_chunk = payload

        print(f"\n收到 {chunk_count} 个 SSE 事件, conversationId={conversation_id}")

        failures = []
        if error_chunk:
            failures.append(f"流中出现错误: {error_chunk.get('error')}")
        if not done_chunk:
            failures.append("没有收到 done 事件")
            print("\n".join(f"FAIL: {f}" for f in failures))
            await _cleanup(conversation_id)
            return 1

        content = done_chunk.get("fullContent") or ""
        code_blocks = done_chunk.get("codeBlocks") or []
        has_code_blocks = done_chunk.get("hasCodeBlocks")

        print(f"回答长度: {len(content)}")
        print(f"hasCodeBlocks: {has_code_blocks}")
        print(f"codeBlocks 数量: {len(code_blocks)}")
        for i, block in enumerate(code_blocks):
            print(
                f"  [{i}] language={block.get('language')} "
                f"code_len={len(block.get('code') or '')} "
                f"has_sanitizedHtml={'sanitizedHtml' in block}"
            )

        if not code_blocks:
            failures.append("done 事件里没有 codeBlocks")
        else:
            first = code_blocks[0]
            if first.get("language") != "html":
                failures.append(f"第一个代码块语言不是 html: {first.get('language')}")
            if "<" not in (first.get("code") or ""):
                failures.append("代码内容看起来不是 HTML")
            if "sanitizedHtml" not in first:
                failures.append("html 代码块缺少 sanitizedHtml 字段")

        # ---- 校验落库 ----
        async with AsyncSessionLocal() as db:
            conv = (
                await db.execute(select(Conversation).where(Conversation.id == conversation_id))
            ).scalar_one_or_none()
            if conv is None:
                failures.append("对话没有落库")
            else:
                print(f"\n库中对话: codePreviewEnabled={conv.code_preview_enabled} type={conv.conversation_type}")
                if conv.code_preview_enabled != 1:
                    failures.append(f"codePreviewEnabled 应为 1，实际 {conv.code_preview_enabled}")

            rows = (
                await db.execute(
                    select(ConversationMessage).where(
                        ConversationMessage.conversation_id == conversation_id
                    )
                )
            ).scalars().all()
            assistant = [r for r in rows if r.role == "assistant"]
            print(f"库中消息数: {len(rows)} (assistant={len(assistant)})")
            if not assistant:
                failures.append("assistant 消息没有落库")
            else:
                stored = assistant[0].code_blocks
                print(f"库中 codeBlocks 字段: {'<空>' if not stored else str(len(stored)) + ' 字节'}")
                if not stored:
                    failures.append("codeBlocks 没有落库")
                else:
                    parsed = json.loads(stored)
                    if not isinstance(parsed, list) or not parsed:
                        failures.append("库中 codeBlocks 不是非空列表")

        print()
        if failures:
            for f in failures:
                print(f"FAIL: {f}")
        else:
            print("全部通过：系统提示词生效 + 代码块提取 + done 事件回传 + 落库")

        await _cleanup(conversation_id)
        return 1 if failures else 0


async def _cleanup(conversation_id):
    """清理测试数据，避免污染真实库"""
    if not conversation_id:
        return
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
