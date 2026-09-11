import myAxios from '@/request.ts'
import type { BaseResponse, PageResult } from '@/api/user.ts'

/**
 * 批量测试相关接口类型定义（与后端 TestTaskVO / TestResultVO 对应）
 */

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface TestTaskVO {
  id: string
  name?: string
  sceneId: string
  sceneName?: string
  models: string[]
  status: TaskStatus
  totalSubtasks: number
  completedSubtasks: number
  startedAt?: string
  completedAt?: string
  createTime: string
  updateTime: string
}

export interface TestResultVO {
  id: string
  taskId: string
  sceneId: string
  promptId: string
  promptTitle?: string
  promptIndex?: number
  modelName: string
  inputPrompt: string
  outputText: string
  reasoning?: string
  responseTimeMs?: number
  inputTokens?: number
  outputTokens?: number
  cost?: number
  userRating?: number
  aiScore?: Record<string, unknown>
  createTime: string
}

export interface CreateBatchTestRequest {
  name?: string
  sceneId: string
  models: string[]
  temperature?: number
  maxTokens?: number
}

export interface BatchTestTaskQueryRequest {
  sceneId?: string
  status?: TaskStatus
  current?: number
  pageSize?: number
}

/** WebSocket 推送的任务进度消息（与后端 TaskProgressVO 对应） */
export interface TaskProgressMessage {
  taskId: string
  status: TaskStatus
  totalSubtasks: number
  completedSubtasks: number
  percentage: number
  currentModel?: string
  currentPrompt?: string
  modelName?: string
  promptTitle?: string
  success?: boolean
  errorMessage?: string
  message?: string
}

export interface UserModelUsageVO {
  modelName: string
  modelLabel?: string
  totalTokens: number
  totalCost: number
}

export interface ModelUsageStatVO {
  modelName: string
  modelLabel?: string
  callCount: number
  totalTokens: number
  totalCost: number
  avgResponseTimeMs?: number
}

export interface StatisticsOverviewVO {
  taskCount: number
  completedTaskCount: number
  runningTaskCount: number
  resultCount: number
  modelCount: number
  sceneCount: number
  totalTokens: number
  totalCost: number
  avgResponseTimeMs?: number
  modelUsage: UserModelUsageVO[]
  modelStats: ModelUsageStatVO[]
}

/**
 * 创建批量测试任务
 */
export async function createBatchTestTask(params: CreateBatchTestRequest) {
  return myAxios.post<BaseResponse<string>>('/batch-test/create', params)
}

/**
 * 获取任务详情
 */
export async function getBatchTestTask(id: string) {
  return myAxios.get<BaseResponse<TestTaskVO>>('/batch-test/task/get', { params: { id } })
}

/**
 * 分页查询任务列表
 */
export async function listBatchTestTaskByPage(params: BatchTestTaskQueryRequest) {
  return myAxios.post<BaseResponse<PageResult<TestTaskVO>>>('/batch-test/task/list/page', params)
}

/**
 * 删除任务
 */
export async function deleteBatchTestTask(id: string) {
  return myAxios.post<BaseResponse<boolean>>('/batch-test/task/delete', { id })
}

/**
 * 取消任务
 */
export async function cancelBatchTestTask(id: string) {
  return myAxios.post<BaseResponse<boolean>>('/batch-test/task/cancel', { id })
}

/**
 * 获取任务的测试结果（可按模型筛选）
 */
export async function listBatchTestResult(taskId: string, modelName?: string) {
  return myAxios.get<BaseResponse<TestResultVO[]>>('/batch-test/result/list', {
    params: { taskId, modelName },
  })
}

/**
 * 更新测试结果评分（1-5 分）
 */
export async function updateBatchTestResultRating(id: string, userRating: number) {
  return myAxios.post<BaseResponse<boolean>>('/batch-test/result/rating', { id, userRating })
}

/**
 * 数据统计概览
 */
export async function getStatisticsOverview() {
  return myAxios.get<BaseResponse<StatisticsOverviewVO>>('/batch-test/statistics/overview')
}
