"""
场景提示词数据库模型
"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, String, Text

from app.db.session import Base


class ScenePrompt(Base):
    """
    场景提示词表模型

    promptIndex 保证提示词的执行顺序，批量测试时按序号从小到大依次处理。
    预设场景的提示词 userId 统一为 0（系统内置），自定义提示词记录真实用户 ID。
    """

    __tablename__ = "scene_prompt"

    id = Column(String(36), primary_key=True, comment="提示词唯一标识")
    scene_id = Column("sceneId", String(36), nullable=False, comment="场景ID")
    user_id = Column("userId", BigInteger, nullable=False, comment="用户ID")
    prompt_index = Column("promptIndex", Integer, nullable=False, comment="提示词序号")
    title = Column(String(200), nullable=False, comment="提示词标题")
    content = Column(Text, nullable=False, comment="提示词内容")
    difficulty = Column(String(20), nullable=True, comment="难度: easy/medium/hard")
    tags = Column(JSON, nullable=True, comment="标签数组")
    expected_output = Column("expectedOutput", Text, nullable=True, comment="期望输出(可选)")
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
