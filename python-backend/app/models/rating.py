"""
用户评分数据库模型
"""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String

from app.db.session import Base


class Rating(Base):
    """
    用户评分表模型

    用户在 Side-by-Side 对比后，对某一轮消息（messageIndex）给出评价：
    model_better（某个模型更好）/ tie（平局）/ both_bad（都不好）。
    同一用户对同一轮消息只保留一条评分，重复提交走更新逻辑。
    """

    __tablename__ = "rating"

    id = Column(String(36), primary_key=True, comment="评分唯一标识")
    conversation_id = Column("conversationId", String(36), nullable=False, comment="对话ID")
    message_index = Column("messageIndex", Integer, nullable=False, comment="消息序号")
    user_id = Column("userId", BigInteger, nullable=False, comment="用户ID")
    rating_type = Column(
        "ratingType", String(20), nullable=False, comment="评分类型: model_better/tie/both_bad"
    )
    winner_model = Column("winnerModel", String(100), nullable=True, comment="获胜模型")
    loser_model = Column("loserModel", String(100), nullable=True, comment="失败模型")
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
