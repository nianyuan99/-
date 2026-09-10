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
  /** 变体索引（Prompt Lab 专用；Side-by-Side 消息为 null） */
  variantIndex?: number
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

/**
 * 评分类型
 *
 * Side-by-Side 用 model_better / tie / both_bad；
 * Prompt Lab 对变体评分，用 variant_0、variant_1 ...
 */
export type RatingType = 'model_better' | 'tie' | 'both_bad' | `variant_${number}`

export interface RatingRequest {
  conversationId: string
  messageIndex: number
  ratingType: RatingType
  winnerModel?: string
  loserModel?: string
  /** 获胜变体索引（Prompt Lab 专用） */
  winnerVariantIndex?: number
}

/** 评分记录（用于加载历史会话时回填评分状态） */
export interface RatingVO {
  id: string
  conversationId: string
  messageIndex: number
  ratingType: RatingType
  winnerModel?: string
  loserModel?: string
  /** 获胜变体索引（Prompt Lab 专用） */
  winnerVariantIndex?: number
}

/** Prompt Lab 单模型多提示词对比请求 */
export interface PromptLabRequest {
  conversationId?: string
  model: string
  promptVariants: string[]
  variantImageUrls?: string[][]
  webSearchEnabled?: boolean
}

/** 变体自动生成请求 */
export interface GenerateVariantsRequest {
  basePrompt: string
  count: number
  model?: string
}

/**
 * 变体自动生成：传一个基础提示词，返回 N 个不同风格的变体
 */
export async function generateVariants(params: GenerateVariantsRequest) {
  return myAxios.post<BaseResponse<string[]>>(
    '/conversation/prompt-lab/generate-variants',
    params,
  )
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
