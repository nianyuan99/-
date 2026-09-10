"""
OpenRouter配置
"""

from typing import Optional

from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from app.core.config import get_settings

settings = get_settings()

# OpenRouter 要求的附加请求头，用于标识调用来源
OPENROUTER_EXTRA_HEADERS = {
    "HTTP-Referer": "https://codefather.cn",
    "X-Title": "AI Evaluation Platform",
}

# 全局复用的异步客户端实例（AsyncOpenAI 内部维护连接池，无需每次重建）
_async_openai_client: Optional[AsyncOpenAI] = None


def get_openrouter_client(model_name: str = "deepseek/deepseek-chat") -> ChatOpenAI:
    """
    获取OpenRouter客户端（LangChain 封装）

    Args:
        model_name: 模型名称，默认使用DeepSeek

    Returns:
        ChatOpenAI客户端实例
    """
    return ChatOpenAI(
        model=model_name,
        openai_api_key=settings.OPENROUTER_API_KEY,
        openai_api_base=settings.OPENROUTER_BASE_URL,
        temperature=0.7,
        max_tokens=2000,
        streaming=True,
        model_kwargs={"extra_headers": OPENROUTER_EXTRA_HEADERS},
    )


def get_async_openai_client() -> AsyncOpenAI:
    """
    获取异步 OpenAI 官方客户端（直连 OpenRouter）

    相比 LangChain 封装，官方 SDK 能直接读取 delta.reasoning，
    无需编写 HTTP 拦截器转换字段，多模型并发流式对比场景下更合适。

    Returns:
        AsyncOpenAI 客户端实例（进程内单例）
    """
    global _async_openai_client
    if _async_openai_client is None:
        _async_openai_client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
        )
    return _async_openai_client


SUPPORTED_MODELS = [
    "deepseek/deepseek-chat",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3-opus",
    "google/gemini-pro-1.5",
    "meta-llama/llama-3.1-70b-instruct",
    "qwen/qwen-2.5-72b-instruct",
]
