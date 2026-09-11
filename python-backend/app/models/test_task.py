"""
批量测试任务数据库模型
"""

import json
from datetime import datetime
from typing import List

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, String

from app.db.session import Base


class TestTask(Base):
    """
    批量测试任务表模型

    子任务总数 = 模型数 × 提示词数，前端通过 completedSubtasks / totalSubtasks 显示进度百分比。
    状态流转：pending → running → completed / failed / cancelled。
    """

    __tablename__ = "test_task"

    id = Column(String(36), primary_key=True, comment="任务唯一标识")
    user_id = Column("userId", BigInteger, nullable=False, comment="用户ID")
    name = Column(String(200), nullable=True, comment="任务名称")
    scene_id = Column("sceneId", String(36), nullable=False, comment="场景ID")
    models = Column(JSON, nullable=False, comment="测试的模型列表")
    status = Column(
        String(20), nullable=False, comment="状态: pending/running/completed/failed/cancelled"
    )
    total_subtasks = Column("totalSubtasks", Integer, nullable=False, default=0, comment="子任务总数")
    completed_subtasks = Column(
        "completedSubtasks", Integer, nullable=False, default=0, comment="已完成子任务数"
    )
    started_at = Column("startedAt", DateTime, nullable=True, comment="开始时间")
    completed_at = Column("completedAt", DateTime, nullable=True, comment="完成时间")
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

    @property
    def model_list(self) -> List[str]:
        """
        把 models 列还原成 Python 列表

        注意：MySQL 的 JSON 列经当前驱动读出来是字符串（如 '["a","b"]'），
        不是 list，所以不能直接当数组用。统一在这里解析，避免每个调用点各写一遍。
        """
        raw = self.models
        if raw is None:
            return []
        if isinstance(raw, (list, tuple)):
            return [str(item) for item in raw]
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="ignore")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                return []
            return [str(item) for item in parsed] if isinstance(parsed, list) else []
        return []
