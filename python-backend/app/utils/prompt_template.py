"""
提示词模板工具（功能扩展 1：模板变量自动替换）

`fill_template_variables` 照教程给出的实现，保持签名与行为一致。
"""

import re
from typing import Dict, List

# 匹配 {变量名} 占位符；变量名限定为字母/数字/下划线，避免误吃 JSON 之类的大括号
PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def fill_template_variables(template_content: str, variables: Dict[str, str]) -> str:
    """
    填充模板变量

    对应教程「功能扩展 1」给出的实现：逐个把 {key} 替换成用户填的值。
    未提供值的变量保持占位符原样，由调用方用 `extract_template_variables` 检出并提示。
    """
    result = template_content
    for key, value in variables.items():
        placeholder = "{" + key + "}"
        result = result.replace(placeholder, value if value is not None else "")
    return result


def extract_template_variables(template_content: str) -> List[str]:
    """
    提取模板里的变量名（按首次出现顺序去重）

    模板入库时若没存 variables，用这个兜底从 content 里解析。
    """
    if not template_content:
        return []
    seen: List[str] = []
    for match in PLACEHOLDER_PATTERN.finditer(template_content):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def find_unfilled_variables(template_content: str, filled_content: str) -> List[str]:
    """
    找出填充后仍然残留的变量名
    """
    return extract_template_variables(filled_content)
