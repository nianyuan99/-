"""
代码模式「提示词实验」接口验证

覆盖 code-mode/prompt-lab/stream：确认变体模式下也能拿到带变体索引的 codeBlocks。

用法（后端已在 9090 运行）：
    python -m app.scripts.verify_code_mode_lab
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
TEST_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
VARIANTS = [
    "写一个最简HTML页面，只有一行红色大字 Hello。只要代码不要解释。",
    "请输出一个HTML文件，页面上居中显示一个绿色标题 World。",
]

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' -> ' + detail) if detail else ''}")
    if not ok:
        failures.append(f"{name}: {detail}")


async def main() -> int:
    async with httpx.AsyncClient(timeout=180.0) as client:
        account = f"codemode_lab_{random.randint(100000, 999999)}"
        reg = await client.post(
            f"{BASE}/user/register",
            json={
                "userAccount": account,
                "userPassword": "12345678",
                "checkPassword": "12345678",
                "userName": "代码模式变体验证",
            },
        )
        check("注册测试账号", reg.json().get("code") == 0, str(reg.json()))
        login = await client.post(
            f"{BASE}/user/login", json={"userAccount": account, "userPassword": "12345678"}
        )
        check("登录测试账号", login.json().get("code") == 0)
        if failures:
            return 1

        conversation_id = None
        chunks: list[dict] = []

        print(f"\nPOST /conversation/code-mode/prompt-lab/stream ({len(VARIANTS)} 个变体) ...")
        async with client.stream(
            "POST",
            f"{BASE}/conversation/code-mode/prompt-lab/stream",
            json={"model": TEST_MODEL, "promptVariants": VARIANTS},
        ) as response:
            check("状态码 200", response.status_code == 200, str(response.status_code))
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = json.loads(line[5:].strip())
                conversation_id = payload.get("conversationId") or conversation_id
                chunks.append(payload)

        check("收到流式事件", len(chunks) > 0, f"{len(chunks)} 个")

        # 按变体索引归组 done 事件
        done_by_variant: dict[int, dict] = {}
        for payload in chunks:
            if payload.get("done") and "fullContent" in payload and not payload.get("hasError"):
                idx = payload.get("variantIndex")
                if idx is not None:
                    done_by_variant[idx] = payload

        check("两个变体都收到 done", set(done_by_variant.keys()) == {0, 1}, str(sorted(done_by_variant.keys())))
        for idx, payload in sorted(done_by_variant.items()):
            blocks = payload.get("codeBlocks") or []
            check(
                f"变体 {idx} 带回 codeBlocks",
                len(blocks) > 0,
                f"{len(blocks)} 个, hasCodeBlocks={payload.get('hasCodeBlocks')}",
            )

        # ---------- 落库与接口回读 ----------
        async with AsyncSessionLocal() as db:
            conv = (
                await db.execute(select(Conversation).where(Conversation.id == conversation_id))
            ).scalar_one_or_none()
            check("对话落库且标记为代码预览", conv is not None and conv.code_preview_enabled == 1)
            check("对话类型是 prompt_lab", conv is not None and conv.conversation_type == "prompt_lab")

            rows = (
                await db.execute(
                    select(ConversationMessage).where(
                        ConversationMessage.conversation_id == conversation_id
                    )
                )
            ).scalars().all()
            assistant = [r for r in rows if r.role == "assistant"]
            user_rows = [r for r in rows if r.role == "user"]
            check("两个变体的 assistant 消息都落库", len(assistant) == 2, f"{len(assistant)} 条")
            check("两个变体的 user 消息都落库", len(user_rows) == 2, f"{len(user_rows)} 条")
            check(
                "assistant 消息带 variantIndex",
                sorted(r.variant_index for r in assistant if r.variant_index is not None) == [0, 1],
            )
            check("assistant 消息带 codeBlocks", all(r.code_blocks for r in assistant))

        resp = await client.get(f"{BASE}/conversation/{conversation_id}/messages")
        data = resp.json().get("data") or []
        with_blocks = [r for r in data if r.get("role") == "assistant" and r.get("codeBlocks")]
        check("消息接口返回 codeBlocks 数组", len(with_blocks) == 2, f"{len(with_blocks)} 条")

        # ---------- 列表筛选 ----------
        resp = await client.post(
            f"{BASE}/conversation/list/page/vo",
            json={"conversationType": "prompt_lab", "codePreviewEnabled": True, "current": 1, "pageSize": 50},
        )
        records = (resp.json().get("data") or {}).get("records") or []
        check(
            "按 prompt_lab + codePreviewEnabled 能筛出该会话",
            any(r.get("id") == conversation_id for r in records),
            f"{len(records)} 条",
        )

        await cleanup(conversation_id)

    print()
    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        print(f"\n共 {len(failures)} 项失败")
        return 1
    print("全部通过：代码模式提示词实验接口 + 变体代码块提取 + 落库 + 筛选")
    return 0


async def cleanup(conversation_id: str) -> None:
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
