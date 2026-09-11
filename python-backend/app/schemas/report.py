"""
测试报告相关的响应模型（Pydantic）

数据分三层：先看摘要了解大概，再看每个模型的统计信息，最后看图表做直观对比。
统计计算全部在后端完成，前端拿到数据直接渲染。

字段别名（alias）统一用 camelCase，与前端 TS 类型对齐；
`populate_by_name=True` 允许内部用 Python 名构造，`serialize_by_alias=True`
保证对外序列化输出 camelCase。
"""

from typing import List, Optional

from app.schemas.batch_test import TestResultVO
from pydantic import BaseModel, ConfigDict, Field


class ReportSummaryVO(BaseModel):
    """
    报告摘要
    """

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    total_cost: Optional[float] = Field(
        None, description="总成本(USD)", alias="totalCost"
    )
    avg_response_time_ms: Optional[float] = Field(
        None, description="平均响应时间(毫秒)", alias="avgResponseTimeMs"
    )
    total_tokens: Optional[int] = Field(None, description="总Token消耗", alias="totalTokens")
    total_results: Optional[int] = Field(None, description="测试结果总数", alias="totalResults")
    model_count: Optional[int] = Field(
        None, description="参与测试的模型数量", alias="modelCount"
    )


class ModelStatisticsVO(BaseModel):
    """
    模型统计信息
    """

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    model_name: str = Field(..., description="模型名称", alias="modelName")
    test_count: int = Field(..., description="测试次数", alias="testCount")
    avg_response_time_ms: Optional[float] = Field(
        None, description="平均响应时间(毫秒)", alias="avgResponseTimeMs"
    )
    avg_input_tokens: Optional[float] = Field(
        None, description="平均输入Token数", alias="avgInputTokens"
    )
    avg_output_tokens: Optional[float] = Field(
        None, description="平均输出Token数", alias="avgOutputTokens"
    )
    total_tokens: Optional[int] = Field(None, description="总Token数", alias="totalTokens")
    total_cost: Optional[float] = Field(None, description="总成本(USD)", alias="totalCost")
    avg_cost: Optional[float] = Field(None, description="平均成本(USD)", alias="avgCost")
    avg_user_rating: Optional[float] = Field(
        None, description="平均用户评分(1-5)", alias="avgUserRating"
    )
    avg_ai_score: Optional[float] = Field(
        None, description="平均AI评分(0-100，各评委 totalScore 的平均)", alias="avgAiScore"
    )


class RadarSeriesVO(BaseModel):
    """
    雷达图单个模型的数据系列
    """

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    model_name: str = Field(..., description="模型名称", alias="modelName")
    values: List[float] = Field(
        default_factory=list, description="各维度标准化后的分数(0-100)，顺序与 dimensions 一致"
    )


class RadarChartDataVO(BaseModel):
    """
    雷达图数据

    所有维度的分数都标准化到 0-100，这样不同量纲的数据才能放在一张图里对比。
    """

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    dimensions: List[str] = Field(default_factory=list, description="维度名称")
    series: List[RadarSeriesVO] = Field(default_factory=list, description="各模型的数据系列")


class BarSeriesVO(BaseModel):
    """
    柱状图单组数据
    """

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    name: str = Field(..., description="系列名称")
    data: List[float] = Field(default_factory=list, description="各模型的值，顺序与 categories 一致")
    unit: Optional[str] = Field(None, description="单位")


class BarChartDataVO(BaseModel):
    """
    柱状图数据

    三个指标：平均响应时间(ms)、总 Token 消耗、总成本(USD)。
    """

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    categories: List[str] = Field(default_factory=list, description="类目（模型名称）")
    series: List[BarSeriesVO] = Field(default_factory=list, description="各指标的数据系列")


class ReportVO(BaseModel):
    """
    测试报告
    """

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        protected_namespaces=(),
    )

    task_id: str = Field(..., description="任务ID", alias="taskId")
    task_name: Optional[str] = Field(None, description="任务名称", alias="taskName")
    summary: ReportSummaryVO = Field(..., description="报告摘要")
    model_statistics: List[ModelStatisticsVO] = Field(
        ..., description="各模型统计", alias="modelStatistics"
    )
    radar_chart: RadarChartDataVO = Field(..., description="雷达图数据", alias="radarChart")
    bar_chart: BarChartDataVO = Field(..., description="柱状图数据", alias="barChart")
    test_results: List[TestResultVO] = Field(
        ..., description="详细测试结果列表", alias="testResults"
    )
