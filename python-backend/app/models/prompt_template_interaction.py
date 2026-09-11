"""
模板点赞与收藏数据库模型

两个动作分开两张表（而不是一张表带 type 字段），因为它们的唯一约束维度不同：
点赞是「一个用户对一个模板只能点一次」，收藏同理，语义上都是 (userId, templateId) 唯一。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String

from app.db.session import Base


class PromptTemplateLike(Base):
    """
    模板点赞表
    """

    __tablename__ = "prompt_template_like"

    id = Column(String(36), primary_key=True, comment="点赞唯一标识")
    template_id = Column("templateId", String(36), nullable=False, comment="模板ID")
    user_id = Column("userId", BigInteger, nullable=False, comment="用户ID")
    create_time = Column("createTime", DateTime, nullable=False, default=datetime.now, comment="创建时间")
    is_delete = Column("isDelete", Integer, nullable=False, default=0, comment="逻辑删除")


class PromptTemplateFavorite(Base):
    """
    模板收藏表
    """

    __tablename__ = "prompt_template_favorite"

    id = Column(String(36), primary_key=True, comment="收藏唯一标识")
    template_id = Column("templateId", String(36), nullable=False, comment="模板ID")
    user_id = Column("userId", BigInteger, nullable=False, comment="用户ID")
    create_time = Column("createTime", DateTime, nullable=False, default=datetime.now, comment="创建时间")
    is_delete = Column("isDelete", Integer, nullable=False, default=0, comment="逻辑删除")
