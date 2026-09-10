"""
模型信息数据库模型
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, Integer, String, Text

from app.db.session import Base


class Model(Base):
    """
    模型信息表模型

    存放从 OpenRouter 同步过来的模型列表（ID 使用 OpenRouter 格式，如 openai/gpt-4o），
    价格字段统一换算为「每百万 tokens 的美元价格」。
    """

    __tablename__ = "model"

    id = Column(String(100), primary_key=True, comment="模型ID（OpenRouter格式，如：openai/gpt-4o）")
    name = Column(String(200), nullable=False, comment="模型显示名称")
    description = Column(Text, nullable=True, comment="模型描述")
    provider = Column(String(100), nullable=True, comment="提供商（如：OpenAI, Anthropic）")
    context_length = Column("contextLength", Integer, nullable=True, comment="上下文长度（tokens）")
    input_price = Column(
        "inputPrice", DECIMAL(10, 6), nullable=True, comment="输入价格（每百万tokens，美元）"
    )
    output_price = Column(
        "outputPrice", DECIMAL(10, 6), nullable=True, comment="输出价格（每百万tokens，美元）"
    )
    recommended = Column(Integer, nullable=False, default=0, comment="是否推荐（1-推荐 0-不推荐）")
    is_china = Column("isChina", Integer, nullable=False, default=0, comment="是否国内模型（1-国内 0-国外）")
    tags = Column(String(500), nullable=True, comment="标签（JSON数组字符串）")
    raw_data = Column("rawData", Text, nullable=True, comment="OpenRouter原始数据（JSON）")
    total_tokens = Column("totalTokens", BigInteger, nullable=False, default=0, comment="累计使用Token数")
    total_cost = Column(
        "totalCost", DECIMAL(12, 6), nullable=False, default=Decimal("0"), comment="累计花费（美元）"
    )
    create_time = Column("createTime", DateTime, nullable=False, default=datetime.now, comment="创建时间")
    update_time = Column(
        "updateTime",
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment="更新时间",
    )
    is_delete = Column("isDelete", Integer, nullable=False, default=0, comment="逻辑删除")
