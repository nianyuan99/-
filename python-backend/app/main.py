"""
FastAPI主应用
"""

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import batch_test, conversation, health, model, rating, scene, test, user
from app.core.config import get_settings
from app.core.logging_config import LoggingConfig
from app.core.scheduler import setup_scheduler, shutdown_scheduler
from app.exceptions import BusinessException, business_exception_handler, global_exception_handler
from app.middleware.session_middleware import RedisSessionMiddleware
from app.services.progress_service import clear_main_loop, set_main_loop
from app.ws import router as ws_router

settings = get_settings()

LoggingConfig.setup_logging(log_level="DEBUG" if settings.APP_DEBUG else "INFO")

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="AI大模型评测平台 - Python后端",
    version="0.0.1",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册自定义 Redis Session 中间件（放在 CORS 之后注册，Session 在最外层）
app.add_middleware(RedisSessionMiddleware)

# 注册业务异常处理器，统一转换为 BaseResponse 格式
app.add_exception_handler(BusinessException, business_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.include_router(health.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(test.router, prefix="/api")
app.include_router(conversation.router, prefix="/api")
app.include_router(rating.router, prefix="/api")
app.include_router(model.router, prefix="/api")
app.include_router(scene.router, prefix="/api")
app.include_router(batch_test.router, prefix="/api")

# WebSocket 不挂在 /api 下：前端 sockjs-client 连接的是 /ws，
# 再加一层 /api 前缀会和 Java 版的路径约定不一致
app.include_router(ws_router.router)


@app.get("/")
async def root():
    """根路径"""
    logger.info("访问根路径")
    return {
        "message": "Welcome to AI Evaluation Platform",
        "docs": "/api/docs",
        "version": "0.0.1"
    }


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("=" * 50)
    logger.info("AI 大模型评测平台启动")
    logger.info("应用名称: %s", settings.APP_NAME)
    logger.info("环境: %s", settings.APP_ENV)
    logger.info("端口: %d", settings.APP_PORT)
    logger.info("调试模式: %s", settings.APP_DEBUG)
    logger.info("=" * 50)

    # 记录主事件循环，供线程池中的 worker 跨线程调度 WebSocket 广播
    set_main_loop(asyncio.get_running_loop())

    # 启动定时任务调度器（每天凌晨 2 点同步 OpenRouter 模型列表）
    setup_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    clear_main_loop()
    shutdown_scheduler()
    logger.info("AI 大模型评测平台关闭")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.APP_PORT,
        reload=settings.APP_DEBUG
    )
