"""
提示词安全校验

教程的 `_validate_prompt_lab_request()` 会对每个提示词变体调用 `validate_prompt(v)`，
但没有给出实现（Java 版对应 PromptSecurityUtils）。这里补一份轻量的本地黑名单，
把风险最明确的几类输入拦在调用模型之前：提示词注入 / 套取系统提示词 / 危险物品制作 / 恶意代码。

设计取向是「够用就好」：这是第一道防线，不是完整的内容安全方案（真正的审核要靠模型侧）。
因此规则刻意写得窄 —— 涉及动作的必须同时出现「动作词 + 目标词」，避免误伤正常的编程提问
（例如「写一个扫雷游戏，格子下面是炸弹」这类不该被拦）。
"""

import re
from typing import List, Pattern, Tuple

from app.exceptions import BusinessException, ErrorCode

# 单个提示词变体的长度上限（字符），防止把超长文本直接塞给模型
MAX_PROMPT_LENGTH = 8000

# (分类, 正则)：命中任意一条即拒绝
_BLOCKED_RULES: List[Tuple[str, Pattern[str]]] = [
    (
        "提示词注入",
        re.compile(
            r"(ignore|disregard|forget)\s+(all\s+)?(the\s+)?(previous|above|prior|preceding)\s+"
            r"(instructions?|prompts?|rules?)"
            r"|忽略(以上|之前|前面|上面|以前)(的)?(所有)?(指令|指示|要求|规则|设定)",
            re.IGNORECASE,
        ),
    ),
    (
        "套取系统提示词",
        re.compile(
            r"(reveal|repeat|print|show|leak)\s+(me\s+)?(your\s+)?(system\s+)?"
            r"(prompt|instructions?|initial\s+settings)"
            r"|(重复|输出|打印|泄露|告诉我)(你的)?(系统)?(提示词|系统指令|初始设定)",
            re.IGNORECASE,
        ),
    ),
    (
        "危险物品制作",
        re.compile(
            r"(how\s+to\s+)?(make|build|synthesize|manufacture|construct)\s+(a\s+|an\s+)?"
            r"(bomb|explosive|napalm|nerve\s+agent|meth|methamphetamine|pipe\s+bomb)"
            r"|(制作|制造|合成|自制|怎么做|如何做|教程).{0,8}"
            r"(炸弹|爆炸物|燃烧瓶|冰毒|毒品|神经毒剂|枪支)",
            re.IGNORECASE,
        ),
    ),
    (
        "恶意代码",
        re.compile(
            r"(write|create|build|develop|generate|code)\s+(a\s+|an\s+)?"
            r"(ransomware|keylogger|rootkit|botnet|credential\s+stealer|backdoor)"
            r"|(写|编写|实现|开发|生成|帮我做).{0,8}"
            r"(勒索软件|勒索病毒|木马|键盘记录器|后门程序|僵尸网络|窃取密码)",
            re.IGNORECASE,
        ),
    ),
]


def validate_prompt(prompt: str) -> None:
    """
    校验单条提示词，不通过直接抛业务异常

    Args:
        prompt: 待校验的提示词文本

    Raises:
        BusinessException: 内容为空、超长或命中安全黑名单
    """
    if prompt is None or not prompt.strip():
        raise BusinessException(ErrorCode.PARAMS_ERROR, "提示词不能为空")

    if len(prompt) > MAX_PROMPT_LENGTH:
        raise BusinessException(
            ErrorCode.PARAMS_ERROR, f"单个提示词长度不能超过 {MAX_PROMPT_LENGTH} 个字符"
        )

    for category, pattern in _BLOCKED_RULES:
        matched = pattern.search(prompt)
        if matched:
            raise BusinessException(
                ErrorCode.PARAMS_ERROR,
                f"提示词包含不被允许的内容（{category}），请修改后重试",
            )
