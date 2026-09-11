import myAxios from '@/request.ts'
import type { BaseResponse } from '@/api/user.ts'
import type { TestResultVO } from '@/api/batchTest.ts'

/**
 * 测试报告相关接口类型定义（与后端 ReportVO 及各 VO 对应）
 */

/** 报告摘要 */
export interface ReportSummaryVO {
  totalCost?: number
  avgResponseTimeMs?: number
  totalTokens?: number
  totalResults?: number
  modelCount?: number
}

/** 单个模型的统计信息 */
export interface ModelStatisticsVO {
  modelName: string
  testCount: number
  avgResponseTimeMs?: number
  avgInputTokens?: number
  avgOutputTokens?: number
  totalTokens?: number
  totalCost?: number
  avgCost?: number
  avgUserRating?: number
  avgAiScore?: number
}

/** 雷达图单个模型的数据系列 */
export interface RadarSeriesVO {
  modelName: string
  values: number[]
}

/** 雷达图数据 */
export interface RadarChartDataVO {
  dimensions: string[]
  series: RadarSeriesVO[]
}

/** 柱状图单组数据 */
export interface BarSeriesVO {
  name: string
  data: number[]
  unit?: string
}

/** 柱状图数据 */
export interface BarChartDataVO {
  categories: string[]
  series: BarSeriesVO[]
}

/** 完整测试报告 */
export interface ReportVO {
  taskId: string
  taskName?: string
  summary: ReportSummaryVO
  modelStatistics: ModelStatisticsVO[]
  radarChart: RadarChartDataVO
  barChart: BarChartDataVO
  testResults: TestResultVO[]
}

/**
 * 生成测试报告
 */
export async function generateReport(params: { taskId: string }) {
  return myAxios.get<BaseResponse<ReportVO>>('/report/generate', { params })
}
