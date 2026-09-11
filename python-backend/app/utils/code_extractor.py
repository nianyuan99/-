"""
代码提取工具

从 AI 返回的 Markdown 内容里识别并提取代码块，供前端 Monaco Editor 高亮展示、
以及 iframe 沙箱预览使用。

对应 Java 版的 CodeExtractor 工具类：Java 用静态方法 + CodeBlock 类（Lombok @Data），
Python 这里换成模块级函数 + @dataclass，代码量更少、调用也更直接。

安全性说明：
    本模块**不做** HTML 清洗，_sanitize_html 原样返回代码。
    安全性完全由前端 <iframe sandbox="allow-scripts"> 保证 —— 后端清洗会误删
    按钮点击事件、定时器、CSS 动画等正常功能，实测得不偿失（见教程第二节）。
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Markdown 代码块：```html\n ... \n```
# [\s\S]*? 等价于「开了 re.DOTALL 的 .*?」，但不需要额外标志位，且是惰性匹配
CODE_BLOCK_PATTERN = re.compile(r"```(\w*)\n([\s\S]*?)```", re.MULTILINE)

# 判定「文本里像不像 HTML」：命中任一标签就认为是 HTML 内容
HTML_TAG_PATTERN = re.compile(
    r"<!DOCTYPE\s+html|<html|<head|<body|<div|<span|<p|<h[1-6]|<script|<style",
    re.IGNORECASE,
)

# 完整的 HTML 文档（从 <!DOCTYPE html> 一直到 </html>）
HTML_DOC_PATTERN = re.compile(r"(<!DOCTYPE\s+html[\s\S]*?</html>)", re.IGNORECASE | re.DOTALL)

# HTML 片段：一对开闭标签及其中的内容
HTML_FRAGMENT_PATTERN = re.compile(r"(<[^>]+>[\s\S]*?</[^>]+>)", re.IGNORECASE | re.DOTALL)


@dataclass
class CodeBlock:
    """代码块 DTO"""

    language: str
    code: str
    start_index: int = 0
    end_index: int = 0
    sanitized_html: Optional[str] = None


def extract_code_blocks(text: str) -> List[Dict[str, Any]]:
    """
    从文本中提取所有代码块

    返回值直接给出 dict（key 用驼峰命名）而不是 CodeBlock 对象，
    因为这份数据最终要 json.dumps 存库、并原样透传给前端，少一层转换。

    Args:
        text: 包含 Markdown 代码块的文本

    Returns:
        代码块列表，每个元素形如
        {"language": "html", "code": "...", "startIndex": 0, "endIndex": 123, "sanitizedHtml": "..."}
    """
    result: List[Dict[str, Any]] = []

    if not text or not text.strip():
        return result

    try:
        for match in CODE_BLOCK_PATTERN.finditer(text):
            # 没写语言标记的代码块（``` 后面直接换行）统一按 text 处理
            language = match.group(1) or "text"
            code = match.group(2)

            block: Dict[str, Any] = {
                "language": language.lower(),
                "code": code,
                "startIndex": match.start(),
                "endIndex": match.end(),
            }

            if language.lower() == "html":
                block["sanitizedHtml"] = _sanitize_html(code)

            result.append(block)
            logger.debug("提取到代码块: language=%s, length=%d", language, len(code))

        # 兜底：没有 Markdown 代码块，但文本里出现了 HTML 标签
        # （AI 有时会忘记用三个反引号包裹，直接在正文里贴 HTML）
        if not result and HTML_TAG_PATTERN.search(text):
            logger.info("未找到Markdown代码块，但检测到HTML标签，尝试提取HTML代码")
            html_code = _extract_html_from_text(text)
            if html_code and html_code.strip():
                result.append(
                    {
                        "language": "html",
                        "code": html_code,
                        "startIndex": 0,
                        "endIndex": len(text),
                        "sanitizedHtml": _sanitize_html(html_code),
                    }
                )

        logger.info("共提取到 %d 个代码块", len(result))

    except Exception:
        # 提取失败不应该影响主流程（内容照常落库和展示），只记日志
        logger.error("提取代码块失败", exc_info=True)

    return result


def _extract_html_from_text(text: str) -> Optional[str]:
    """
    从纯文本中提取 HTML 代码

    优先整篇 HTML 文档，其次一对开闭标签的片段，最后兜底返回整段文本。
    """
    if not text or not text.strip():
        return None

    # 1) 完整的 HTML 文档
    html_doc_match = HTML_DOC_PATTERN.search(text)
    if html_doc_match:
        return html_doc_match.group(1)

    # 2) HTML 片段：从第一个 "<" 截到最后一个 ">"
    if HTML_FRAGMENT_PATTERN.search(text):
        first_tag = text.find("<")
        last_tag = text.rfind(">")
        if first_tag >= 0 and last_tag > first_tag:
            return text[first_tag : last_tag + 1]

    # 3) 兜底：整段文本都当 HTML
    if HTML_TAG_PATTERN.search(text):
        return text

    return None


def _sanitize_html(html: str) -> str:
    """
    HTML 代码预览处理

    注意：此方法直接返回原始 HTML 代码，不进行清理。
    安全性由前端 iframe 的 sandbox 属性（只开 allow-scripts）保证。
    """
    if not html or not html.strip():
        return ""

    try:
        logger.debug("HTML预览处理: 长度=%d", len(html))
        return html
    except Exception:
        logger.error("HTML处理失败", exc_info=True)
        return ""
