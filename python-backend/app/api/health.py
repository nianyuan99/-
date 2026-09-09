"""
健康检查接口
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.redis import get_redis
from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["Health"])
logger = logging.getLogger(__name__)


@router.get("")
async def health_check():
    """健康检查接口"""
    logger.info("健康检查")
    return {
        "status": "ok",
        "message": "AI Evaluation Platform is running"
    }


@router.get("/db")
async def db_health_check(db: Session = Depends(get_db)):
    """数据库健康检查"""
    try:
        db.execute(text("SELECT 1"))
        logger.info("数据库连接正常")
        return {
            "status": "ok",
            "message": "Database connection is healthy"
        }
    except Exception as e:
        logger.error("数据库连接失败: %s", str(e))
        return {
            "status": "error",
            "message": f"Database connection failed: {str(e)}"
        }


@router.get("/redis")
async def redis_health_check():
    """Redis健康检查"""
    try:
        redis = get_redis()
        redis.ping()
        logger.info("Redis连接正常")
        return {
            "status": "ok",
            "message": "Redis connection is healthy"
        }
    except Exception as e:
        logger.error("Redis连接失败: %s", str(e))
        return {
            "status": "error",
            "message": f"Redis connection failed: {str(e)}"
        }
