import myAxios from '@/request.ts'
import type { BaseResponse, PageResult } from '@/api/user.ts'

/**
 * 对话与评分相关接口类型定义（与后端 Pydantic 模型对应）
 */

/** SSE 流式响应数据块 */
export interface StreamChunkVO {
  conversationId?: string
  modelName?: string
  variantIndex?: number
  /** 本轮消息序号，评分时回传 */
  messageIndex?: number
  content?: string
  fullContent?: string
  inputTokens?: number
  outputTokens?: number
  elapsedMs?: number
  responseTimeMs?: number
  cost?: number
  done?: boolean
  error?: string
  hasError?: boolean
  reasoning?: string
  hasReasoning?: boolean
  thinkingTime?: number
}

export interface ConversationVO {
  id: string
  title?: string
  conversationType: string
  models: string[]
  totalTokens?: number
  totalCost?: number
  createTime: string
  updateTime: string
}

export interface ConversationMessageVO {
  id: string
  conversationId: string
  messageIndex: number
  role: string
  modelName?: string
  content: string
  responseTimeMs?: number
  inputTokens?: number
  outputTokens?: number
  cost?: number
  reasoning?: string
  createTime: string
}

export interface ConversationQueryRequest {
  conversationType?: string
  current?: number
  pageSize?: number
}

export interface RatingRequest {
  conversationId: string
  messageIndex: number
  ratingType: 'model_better' | 'tie' | 'both_bad'
  winnerModel?: string
  loserModel?: string
}

/** 评分记录（用于加载历史会话时回填评分状态） */
export interface RatingVO {
  id: string
  conversationId: string
  messageIndex: number
  ratingType: 'model_better' | 'tie' | 'both_bad'
  winnerModel?: string
  loserModel?: string
}

/**
 * 分页查询我的对话列表
 */
export async function listConversationVoByPage(params: ConversationQueryRequest) {
  return myAxios.post<BaseResponse<PageResult<ConversationVO>>>('/conversation/list/page/vo', params)
}

/**
 * 查询某个对话的历史消息
 */
export async function listConversationMessages(conversationId: string) {
  return myAxios.get<BaseResponse<ConversationMessageVO[]>>(
    `/conversation/${conversationId}/messages`,
  )
}

/**
 * 查询某个对话的全部评分（加载历史会话时回填评分状态）
 */
export async function listRatings(conversationId: string) {
  return myAxios.get<BaseResponse<RatingVO[]>>(`/rating/${conversationId}/list`)
}

/**
 * 提交或修改评分
 */
export async function addRating(params: RatingRequest) {
  return myAxios.post<BaseResponse<boolean>>('/rating/add', params)
}

export type { BaseResponse, PageResult }
