"""
代码模式前端验证用的「夹具会话」

直接往库里插一条带 HTML 代码块的对话（不走模型调用），
让浏览器端的验证不依赖网络与模型是否稳定写代码。

用法：
    # 单文件夹具（HTML 一个代码块）
    python -m app.scripts.seed_code_fixture create

    # 多文件夹具（HTML + CSS + JS 三个代码块，验证前端合并预览）
    python -m app.scripts.seed_code_fixture create-multi

    # 清理夹具
    python -m app.scripts.seed_code_fixture clean
"""

import asyncio
import json
import sys
import uuid
from decimal import Decimal

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User

FIXTURE_ACCOUNT = "code_mode_fixture"
FIXTURE_PASSWORD = "12345678"
# 用标准 UUID 作为对话 ID：和其他对话一样是 varchar(36)，避免自定义串踩到列长限制
CONVERSATION_ID = "f1c7a9e4-0000-4000-8000-000000000001"
USER_ID = 990001

HTML_CODE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Hello</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #fff;
      font-family: Arial, "Microsoft YaHei", sans-serif;
    }
    h1 {
      color: red;
      font-size: 4rem;
      margin: 0;
    }
  </style>
</head>
<body>
  <h1>Hello</h1>
</body>
</html>
"""

CONTENT = (
    "这是一个最简单的单文件页面：红色大标题 Hello 居中显示。\n\n"
    "```html\n" + HTML_CODE + "```\n\n"
    "直接把代码保存为 index.html 双击即可打开。"
)

CODE_BLOCKS = json.dumps(
    [
        {
            "language": "html",
            "code": HTML_CODE,
            "startIndex": CONTENT.index("```html"),
            "endIndex": CONTENT.rindex("```") + 3,
            "sanitizedHtml": HTML_CODE,
        }
    ],
    ensure_ascii=False,
)


async def create() -> int:
    from app.utils.password import encrypt_password

    async with AsyncSessionLocal() as db:
        # 夹具账号：已存在就更新密码，避免反复创建
        user = (
            await db.execute(select(User).where(User.user_account == FIXTURE_ACCOUNT))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                user_account=FIXTURE_ACCOUNT,
                user_password=encrypt_password(FIXTURE_PASSWORD),
                user_name="代码模式夹具",
                user_role="user",
                is_delete=0,
            )
            db.add(user)
            await db.flush()
        user_id = user.id

        # 清掉旧的夹具对话，保证每次都是干净状态
        await _delete_conversation(db, CONVERSATION_ID)

        db.add(
            Conversation(
                id=CONVERSATION_ID,
                user_id=user_id,
                title="夹具：Hello 单文件页面",
                conversation_type="side_by_side",
                models=["nvidia/nemotron-3-ultra-550b-a55b:free"],
                code_preview_enabled=1,
                total_tokens=123,
                total_cost=Decimal("0"),
                is_delete=0,
            )
        )
        db.add(
            ConversationMessage(
                id=str(uuid.uuid4()),
                conversation_id=CONVERSATION_ID,
                user_id=user_id,
                message_index=0,
                variant_index=None,
                role="user",
                model_name=None,
                content="写一个最简单的HTML页面：红色大标题写着 Hello，居中显示。",
                is_delete=0,
            )
        )
        db.add(
            ConversationMessage(
                id=str(uuid.uuid4()),
                conversation_id=CONVERSATION_ID,
                user_id=user_id,
                message_index=1,
                variant_index=None,
                role="assistant",
                model_name="nvidia/nemotron-3-ultra-550b-a55b:free",
                content=CONTENT,
                response_time_ms=3060,
                input_tokens=24,
                output_tokens=99,
                cost=Decimal("0"),
                reasoning=None,
                code_blocks=CODE_BLOCKS,
                is_delete=0,
            )
        )
        await db.commit()

    print(f"FIXTURE_ACCOUNT={FIXTURE_ACCOUNT}")
    print(f"FIXTURE_PASSWORD={FIXTURE_PASSWORD}")
    print(f"FIXTURE_CONVERSATION_ID={CONVERSATION_ID}")
    print(f"FIXTURE_USER_ID={user_id}")
    return 0


async def clean() -> int:
    async with AsyncSessionLocal() as db:
        await _delete_conversation(db, CONVERSATION_ID)
        await _delete_conversation(db, MULTI_CONVERSATION_ID)
        await db.execute(delete(User).where(User.user_account == FIXTURE_ACCOUNT))
        await db.commit()
    print("已清理夹具会话与夹具账号")
    return 0


# =============================================================================
# 多文件夹具：AI 把 HTML / CSS / JS 拆成三个代码块返回
# 前端 CodePreview 会把 CSS 注入 <head>、JS 注入 </body>，合成一份文档后预览
# =============================================================================

MULTI_CONVERSATION_ID = "f1c7a9e4-0000-4000-8000-000000000002"

MULTI_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>多文件合并测试</title>
</head>
<body>
  <h1 id="title">初始文字</h1>
</body>
</html>
"""

MULTI_CSS = """#title {
  color: rgb(0, 128, 0);
  font-size: 3rem;
  text-align: center;
}
"""

# 这段 JS 负责把标题改掉：如果前端没把 JS 注入进去，iframe 里就只会看到「初始文字」
MULTI_JS = """document.getElementById('title').textContent = 'MERGED_OK';
"""

MULTI_CONTENT = (
    "分成三个文件写更清晰：\n\n"
    "```html\n" + MULTI_HTML + "```\n\n"
    "```css\n" + MULTI_CSS + "```\n\n"
    "```javascript\n" + MULTI_JS + "```\n"
)

MULTI_CODE_BLOCKS = json.dumps(
    [
        {"language": "html", "code": MULTI_HTML, "sanitizedHtml": MULTI_HTML},
        {"language": "css", "code": MULTI_CSS},
        {"language": "javascript", "code": MULTI_JS},
    ],
    ensure_ascii=False,
)


async def create_multi() -> int:
    from app.utils.password import encrypt_password

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.user_account == FIXTURE_ACCOUNT))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                user_account=FIXTURE_ACCOUNT,
                user_password=encrypt_password(FIXTURE_PASSWORD),
                user_name="代码模式夹具",
                user_role="user",
                is_delete=0,
            )
            db.add(user)
            await db.flush()
        user_id = user.id

        await _delete_conversation(db, MULTI_CONVERSATION_ID)

        db.add(
            Conversation(
                id=MULTI_CONVERSATION_ID,
                user_id=user_id,
                title="夹具：HTML+CSS+JS 多文件合并",
                conversation_type="side_by_side",
                models=["nvidia/nemotron-3-ultra-550b-a55b:free"],
                code_preview_enabled=1,
                total_tokens=200,
                total_cost=Decimal("0"),
                is_delete=0,
            )
        )
        db.add(
            ConversationMessage(
                id=str(uuid.uuid4()),
                conversation_id=MULTI_CONVERSATION_ID,
                user_id=user_id,
                message_index=0,
                variant_index=None,
                role="user",
                model_name=None,
                content="用 HTML + CSS + JS 三个文件写一个标题页。",
                is_delete=0,
            )
        )
        db.add(
            ConversationMessage(
                id=str(uuid.uuid4()),
                conversation_id=MULTI_CONVERSATION_ID,
                user_id=user_id,
                message_index=1,
                variant_index=None,
                role="assistant",
                model_name="nvidia/nemotron-3-ultra-550b-a55b:free",
                content=MULTI_CONTENT,
                response_time_ms=4200,
                input_tokens=30,
                output_tokens=120,
                cost=Decimal("0"),
                reasoning=None,
                code_blocks=MULTI_CODE_BLOCKS,
                is_delete=0,
            )
        )
        await db.commit()

    print(f"FIXTURE_ACCOUNT={FIXTURE_ACCOUNT}")
    print(f"FIXTURE_PASSWORD={FIXTURE_PASSWORD}")
    print(f"FIXTURE_CONVERSATION_ID={MULTI_CONVERSATION_ID}")
    return 0


async def _delete_conversation(db, conversation_id: str) -> None:
    await db.execute(delete(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id))
    await db.execute(delete(Conversation).where(Conversation.id == conversation_id))


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "create"
    if action == "clean":
        raise SystemExit(asyncio.run(clean()))
    if action == "create-multi":
        raise SystemExit(asyncio.run(create_multi()))
    raise SystemExit(asyncio.run(create()))
