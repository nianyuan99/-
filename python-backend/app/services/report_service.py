"""
报告服务：生成测试报告

整体流程：查询数据 → 验证权限 → 计算摘要 → 计算模型统计 → 生成图表数据 → 组装返回。

图表数据全部在后端算好、标准化到 0-100，前端拿到直接渲染，不需要再额外计算。
"""

import json
import logging
from collections import defaultdict
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BusinessException, ErrorCode
from app.models.test_result import TestResult
from app.models.test_task import TestTask
from app.schemas.batch_test import TestResultVO
from app.schemas.report import (
    BarChartDataVO,
    BarSeriesVO,
    ModelStatisticsVO,
    RadarChartDataVO,
    RadarSeriesVO,
    ReportSummaryVO,
    ReportVO,
)

logger = logging.getLogger(__name__)

# 雷达图的 5 个维度
RADAR_DIMENSIONS = ["准确性", "完整性", "速度", "成本效率", "用户满意度"]

# 标准化相关常量（相当于 Java 的 private static final）
SCORE_MAX = 100.0
# 速度用反比例标准化：10000 / 响应时间(ms)，100ms 得 100 分、1000ms 得 10 分
SPEED_NORMALIZE_DIVISOR = 10000.0
# 成本效率：1.0 / (平均成本 * 100 + 0.01) * 100，成本越低分数越高，+0.01 防止除零
COST_EFFICIENCY_FACTOR = 100.0
COST_EFFICIENCY_OFFSET = 0.01
# 完整性以平均输出 Token 数为基准，2000 视为满分（与批测默认 maxTokens 对齐）
COMPLETENESS_MAX = 2000.0


class ReportService:
    """
    报告服务：生成测试报告
    """

    @staticmethod
    async def generate_report(db: AsyncSession, task_id: str, user_id: int) -> ReportVO:
        """根据任务ID生成多维度对比报告"""
        if not task_id or not str(task_id).strip():
            raise BusinessException(ErrorCode.PARAMS_ERROR, "任务ID不能为空")

        task_result = await db.execute(
            select(TestTask).where(TestTask.id == task_id.strip(), TestTask.is_delete == 0)
        )
        task = task_result.scalar_one_or_none()
        if not task:
            raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "任务不存在")
        if task.user_id != user_id:
            raise BusinessException(ErrorCode.NO_AUTH_ERROR, "无权限查看该任务报告")

        results_result = await db.execute(
            select(TestResult)
            .where(TestResult.task_id == task_id.strip(), TestResult.is_delete == 0)
            .order_by(TestResult.create_time.asc())
        )
        test_results: List[TestResult] = list(results_result.scalars().all())

        if not test_results:
            raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "该任务暂无测试结果")

        summary = ReportService._calculate_summary(test_results)
        model_statistics = ReportService._calculate_model_statistics(test_results)
        radar_chart = ReportService._generate_radar_chart(test_results, model_statistics)
        bar_chart = ReportService._generate_bar_chart(model_statistics)
        test_result_vo_list = [ReportService._to_test_result_vo(r) for r in test_results]

        return ReportVO(
            task_id=task.id,
            task_name=task.name,
            summary=summary,
            model_statistics=model_statistics,
            radar_chart=radar_chart,
            bar_chart=bar_chart,
            test_results=test_result_vo_list,
        )

    # ============ 摘要与统计 ============

    @staticmethod
    def _calculate_summary(test_results: List[TestResult]) -> ReportSummaryVO:
        """计算报告摘要"""
        total_cost_float = sum(
            float(r.cost) for r in test_results if r.cost is not None
        ) or None

        response_times = [
            r.response_time_ms for r in test_results if r.response_time_ms is not None
        ]
        avg_response_ms = sum(response_times) / len(response_times) if response_times else None

        total_tokens = sum(
            (r.input_tokens or 0) + (r.output_tokens or 0)
            for r in test_results
            if (r.input_tokens is not None or r.output_tokens is not None)
        )

        model_names = {r.model_name for r in test_results}
        return ReportSummaryVO(
            total_cost=total_cost_float,
            avg_response_time_ms=avg_response_ms,
            total_tokens=total_tokens,
            total_results=len(test_results),
            model_count=len(model_names),
        )

    @staticmethod
    def _calculate_model_statistics(test_results: List[TestResult]) -> List[ModelStatisticsVO]:
        """按模型分组计算统计信息"""
        grouped: dict[str, List[TestResult]] = defaultdict(list)
        for r in test_results:
            grouped[r.model_name].append(r)

        statistics_list: List[ModelStatisticsVO] = []
        for model_name, model_results in grouped.items():
            count = len(model_results)
            response_times = [
                r.response_time_ms for r in model_results if r.response_time_ms is not None
            ]
            avg_response_ms = sum(response_times) / len(response_times) if response_times else None

            input_token_values = [
                r.input_tokens for r in model_results if r.input_tokens is not None
            ]
            avg_input_tokens = (
                sum(input_token_values) / len(input_token_values)
                if input_token_values
                else None
            )

            output_token_values = [
                r.output_tokens for r in model_results if r.output_tokens is not None
            ]
            avg_output_tokens = (
                sum(output_token_values) / len(output_token_values)
                if output_token_values
                else None
            )

            total_tokens = sum(
                (r.input_tokens or 0) + (r.output_tokens or 0)
                for r in model_results
                if (r.input_tokens is not None or r.output_tokens is not None)
            )

            costs = [float(r.cost) for r in model_results if r.cost is not None]
            total_cost = sum(costs) if costs else None
            avg_cost = (total_cost / count) if total_cost is not None and count > 0 else None

            user_ratings = [
                r.user_rating for r in model_results if r.user_rating is not None
            ]
            avg_user_rating = (
                sum(user_ratings) / len(user_ratings) if user_ratings else None
            )

            ai_scores: List[float] = []
            for r in model_results:
                total_score = ReportService._extract_ai_total_score(r.ai_score)
                if total_score is not None:
                    ai_scores.append(total_score)
            avg_ai_score = sum(ai_scores) / len(ai_scores) if ai_scores else None

            statistics_list.append(
                ModelStatisticsVO(
                    model_name=model_name,
                    test_count=count,
                    avg_response_time_ms=avg_response_ms,
                    avg_input_tokens=avg_input_tokens,
                    avg_output_tokens=avg_output_tokens,
                    total_tokens=total_tokens,
                    total_cost=total_cost,
                    avg_cost=avg_cost,
                    avg_user_rating=avg_user_rating,
                    avg_ai_score=avg_ai_score,
                )
            )
        return statistics_list

    @staticmethod
    def _extract_ai_total_score(raw: Any) -> Optional[float]:
        """
        从 test_result.aiScore 里取出该条结果的 AI 总分（0-100）

        口径说明：aiScore 顶层只有 averageRating（1-10 的综合评级）和 consistency，
        没有总分字段，所以这里取各评委 `totalScore` 的平均值。totalScore 是评委按五个
        维度打出的 0-100 总分，用它才能让「模型统计表的 AI 评分」「雷达图的准确性」
        「详细结果里的 AI 总分」三处保持同一口径（教程也写明平均 AI 评分是 0-100 分）。

        解析失败或没有可用总分时返回 None，由调用方跳过该条，不影响整个报告。
        """
        if not raw or not str(raw).strip():
            return None
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="ignore")
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("解析AI评分失败: %s, %s", raw, e)
            return None
        if not isinstance(obj, dict):
            return None

        judges = obj.get("judges")
        if not isinstance(judges, list):
            return None
        totals = [
            float(judge["totalScore"])
            for judge in judges
            if isinstance(judge, dict)
            and isinstance(judge.get("totalScore"), (int, float))
        ]
        if not totals:
            return None
        average = sum(totals) / len(totals)
        return average if average > 0 else None

    # ============ 图表数据 ============

    @staticmethod
    def _generate_radar_chart(
        test_results: List[TestResult],
        model_statistics: List[ModelStatisticsVO],
    ) -> RadarChartDataVO:
        """生成雷达图数据"""
        series_list: List[RadarSeriesVO] = []
        for stat in model_statistics:
            # avg_ai_score 是各评委 totalScore 的平均（0-100 口径），
            # 所以这里按 0-100 归一化即可，不用再做量纲换算
            accuracy = stat.avg_ai_score if stat.avg_ai_score is not None else 0.0
            accuracy_norm = ReportService._normalize_score(accuracy, 0.0, 100.0)

            completeness = ReportService._calculate_completeness(test_results, stat.model_name)
            completeness_norm = ReportService._normalize_score(
                completeness, 0.0, COMPLETENESS_MAX
            )

            speed = 0.0
            if stat.avg_response_time_ms is not None and stat.avg_response_time_ms > 0:
                speed = min(SCORE_MAX, SPEED_NORMALIZE_DIVISOR / stat.avg_response_time_ms)

            cost_eff = 0.0
            if stat.avg_cost is not None and stat.avg_cost > 0:
                cost_eff = min(
                    SCORE_MAX,
                    (1.0 / (stat.avg_cost * COST_EFFICIENCY_FACTOR + COST_EFFICIENCY_OFFSET))
                    * 100.0,
                )

            user_sat = 0.0
            if stat.avg_user_rating is not None:
                user_sat = ReportService._normalize_score(stat.avg_user_rating, 1.0, 5.0)

            series_list.append(
                RadarSeriesVO(
                    model_name=stat.model_name,
                    values=[accuracy_norm, completeness_norm, speed, cost_eff, user_sat],
                )
            )
        return RadarChartDataVO(dimensions=RADAR_DIMENSIONS, series=series_list)

    @staticmethod
    def _calculate_completeness(test_results: List[TestResult], model_name: str) -> float:
        """
        计算模型回答的完整性原始值（0 - COMPLETENESS_MAX）

        教程只写了「完整性（基于输出长度和 Token 数）」，未给出具体算式，
        这里取该模型所有测试结果的平均输出 Token 数：输出越长视为覆盖越全面。
        """
        output_tokens = [
            r.output_tokens
            for r in test_results
            if r.model_name == model_name and r.output_tokens is not None
        ]
        if not output_tokens:
            return 0.0
        return sum(output_tokens) / len(output_tokens)

    @staticmethod
    def _normalize_score(value: float, min_val: float, max_val: float) -> float:
        """将分数标准化到 0-100"""
        if max_val == min_val:
            return 0.0
        normalized = ((value - min_val) / (max_val - min_val)) * 100.0
        return max(0.0, min(SCORE_MAX, normalized))

    @staticmethod
    def _generate_bar_chart(model_statistics: List[ModelStatisticsVO]) -> BarChartDataVO:
        """生成柱状图数据"""
        categories = [s.model_name for s in model_statistics]
        response_times = [
            s.avg_response_time_ms if s.avg_response_time_ms is not None else 0.0
            for s in model_statistics
        ]
        total_tokens = [
            float(s.total_tokens) if s.total_tokens is not None else 0.0
            for s in model_statistics
        ]
        total_costs = [
            s.total_cost if s.total_cost is not None else 0.0 for s in model_statistics
        ]
        return BarChartDataVO(
            categories=categories,
            series=[
                BarSeriesVO(name="平均响应时间", data=response_times, unit="ms"),
                BarSeriesVO(name="总Token消耗", data=total_tokens, unit="tokens"),
                BarSeriesVO(name="总成本", data=total_costs, unit="USD"),
            ],
        )

    # ============ 组装 ============

    @staticmethod
    def _to_test_result_vo(test_result: TestResult) -> TestResultVO:
        """把测试结果 ORM 对象转成对外视图对象（aiScore 由校验器解析成对象）"""
        return TestResultVO.model_validate(test_result)
