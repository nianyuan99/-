"""
code_extractor 的轻量自测脚本（不依赖 pytest，直接 python 运行）

用法：
    cd python-backend
    venv\\Scripts\\python.exe -m app.utils.test_code_extractor
"""

import json

from app.utils.code_extractor import extract_code_blocks


def _check(name: str, condition: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' -> ' + detail) if detail else ''}")
    return condition


def main() -> int:
    passed = True

    # 1) 标准 Markdown 代码块
    text = "下面是一个计算器的实现：\n\n```html\n<!DOCTYPE html>\n<html><body><h1>计算器</h1></body></html>\n```\n\n希望对你有帮助。"
    blocks = extract_code_blocks(text)
    passed &= _check("标准 html 代码块被提取", len(blocks) == 1, f"len={len(blocks)}")
    passed &= _check("language 归一化为小写", blocks[0]["language"] == "html")
    passed &= _check("sanitizedHtml 与 code 一致", blocks[0]["sanitizedHtml"] == blocks[0]["code"])
    passed &= _check(
        "startIndex/endIndex 覆盖整个代码块",
        text[blocks[0]["startIndex"] : blocks[0]["endIndex"]].startswith("```html"),
    )
    passed &= _check("endIndex 处是收尾反引号", text[blocks[0]["endIndex"] - 3 : blocks[0]["endIndex"]] == "```")

    # 2) 多个代码块 + 大小写语言标记
    multi = "```HTML\n<div>a</div>\n```\n说明\n```python\nprint(1)\n```"
    blocks = extract_code_blocks(multi)
    passed &= _check("提取到 2 个代码块", len(blocks) == 2, f"len={len(blocks)}")
    passed &= _check("HTML 大写被归一化", blocks[0]["language"] == "html")
    passed &= _check("非 html 不带 sanitizedHtml", "sanitizedHtml" not in blocks[1])

    # 3) 无语言标记的代码块
    blocks = extract_code_blocks("```\nplain text\n```")
    passed &= _check("无语言标记回退为 text", len(blocks) == 1 and blocks[0]["language"] == "text")

    # 4) 兜底：裸 HTML 文档（没有三反引号）
    naked = "这是你要的页面：\n<!DOCTYPE html>\n<html><body><p>hi</p></body></html>\n请查收"
    blocks = extract_code_blocks(naked)
    passed &= _check("裸 HTML 文档被兜底提取", len(blocks) == 1, f"len={len(blocks)}")
    passed &= _check(
        "兜底提取到完整文档",
        bool(blocks) and blocks[0]["code"].startswith("<!DOCTYPE html>") and blocks[0]["code"].endswith("</html>"),
        blocks[0]["code"][:40] if blocks else "",
    )

    # 5) 兜底：HTML 片段
    blocks = extract_code_blocks("直接给你一段：<div class=\"box\">内容</div> 就这样")
    passed &= _check("HTML 片段被兜底提取", len(blocks) == 1, f"len={len(blocks)}")

    # 6) 普通文本不应误判为 HTML
    blocks = extract_code_blocks("这是一段没有任何代码的普通回答，包含 < 和 > 符号。")
    passed &= _check("普通文本不误判为代码块", len(blocks) == 0, f"len={len(blocks)}")

    # 7) 空输入
    passed &= _check("空字符串返回空列表", extract_code_blocks("") == [])
    passed &= _check("全空白返回空列表", extract_code_blocks("   \n\t ") == [])

    # 8) 结果必须能被 json.dumps（要存进 text 列）
    try:
        json.dumps(extract_code_blocks(text), ensure_ascii=False)
        passed &= _check("结果可 JSON 序列化", True)
    except Exception as exc:  # pragma: no cover
        passed &= _check("结果可 JSON 序列化", False, str(exc))

    print("\n" + ("全部通过" if passed else "存在失败用例"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
