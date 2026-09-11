"""
提示词优化历史数据库模型

每次调用 AI 优化接口都存一条，供用户回顾历史建议、对比不同优化方案。
issues / improvements 以 JSON 数组文本落库（对应库表 json 类型）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from app.db.session import Base


class PromptOptimizationHistory(Base):
    """
    提示词优化历史表
    """

    __tablename__ = "prompt_optimization_history"

    id = Column(String(36), primary_key=True, comment="记录唯一标识")
    user_id = Column("userId", BigInteger, nullable=False, comment="用户ID")
    original_prompt = Column("originalPrompt", Text, nullable=False, comment="原始提示词")
    optimized_prompt = Column("optimizedPrompt", Text, nullable=True, comment="优化后的提示词")
    issues = Column("issues", Text, nullable=True, comment="发现的问题(JSON数组)")
    improvements = Column("improvements", Text, nullable=True, comment="改进说明(JSON数组)")
    quality_score = Column(
        "qualityScore", Integer, nullable=True, comment="原始提示词质量评分(0-100)"
    )
    evaluation_model = Column("evaluationModel", String(100), nullable=True, comment="评估模型")
    create_time = Column("createTime", DateTime, nullable=False, default=datetime.now, comment="创建时间")
    is_delete = Column("isDelete", Integer, nullable=False, default=0, comment="逻辑删除")
