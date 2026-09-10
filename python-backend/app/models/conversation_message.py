"""
对话消息数据库模型
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, Integer, String, Text

from app.db.session import Base


class ConversationMessage(Base):
    """
    对话消息表模型

    多模型对比模式下，同一轮对话会存在多条 message_index 相同的记录，
    通过 model_name 区分是哪个模型的回复。
    """

    __tablename__ = "conversation_message"

    id = Column(String(36), primary_key=True, comment="消息唯一标识")
    conversation_id = Column("conversationId", String(36), nullable=False, comment="对话ID")
    user_id = Column("userId", BigInteger, nullable=False, comment="用户ID")
    message_index = Column("messageIndex", Integer, nullable=False, comment="消息序号(从0开始)")
    role = Column(String(20), nullable=False, comment="角色: user/assistant")
    model_name = Column("modelName", String(100), nullable=True, comment="模型名称(assistant消息)")
    content = Column(Text, nullable=False, comment="消息内容")
    response_time_ms = Column("responseTimeMs", Integer, nullable=True, comment="响应时间(毫秒)")
    input_tokens = Column("inputTokens", Integer, nullable=True, comment="输入Token数")
    output_tokens = Column("outputTokens", Integer, nullable=True, comment="输出Token数")
    cost = Column(DECIMAL(10, 6), nullable=True, comment="成本(USD)")
    reasoning = Column(Text, nullable=True, comment="思考过程（thinking模式）")
    code_blocks = Column("codeBlocks", Text, nullable=True, comment="代码块列表（JSON格式）")
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

    # 便于业务代码复用的空值兜底
    @property
    def safe_cost(self) -> Decimal:
        """成本为空时返回 0，避免统计时出现 None"""
        return self.cost if self.cost is not None else Decimal("0")
