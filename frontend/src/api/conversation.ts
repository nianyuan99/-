import myAxios from '@/request.ts'
import type { BaseResponse, PageResult } from '@/api/user.ts'

/**
 * 对话与评分相关接口类型定义（与后端 Pydantic 模型对应）
 */

/** 从回答里提取出的一个代码块 */
export interface CodeBlockVO {
  language: string
  code: string
  /** 在原文中的起止位置（HTML 代码块才有实际意义） */
  startIndex?: number
  endIndex?: number
  /** 后端做预览处理后的 HTML（目前原样返回，安全由 iframe sandbox 负责） */
  sanitizedHtml?: string
}

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
  /** 代码模式：done 事件里直接带回解析好的代码块 */
  codeBlocks?: CodeBlockVO[]
  hasCodeBlocks?: boolean
}

export interface ConversationVO {
  id: string
  title?: string
  conversationType: string
  models: string[]
  /** 是否启用代码预览（1-启用 0-不启用） */
  codePreviewEnabled?: number
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
  /** 从回答里提取的代码块（代码模式；没有代码块时为 undefined） */
  codeBlocks?: CodeBlockVO[]
  createTime: string
}

export interface ConversationQueryRequest {
  conversationType?: string
  /** 按是否启用代码预览筛选：代码模式页传 true，普通对比页传 false 以排除代码会话 */
  codePreviewEnabled?: boolean
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
 * 代码模式请求：多模型并排生成可运行代码
 *
 * 流式接口统一走 createPostSSE，这里的类型只用于约束请求体字段。
 */
export interface CodeModeRequest {
  models: string[]
  prompt: string
  imageUrls?: string[]
  conversationId?: string
  stream?: boolean
  webSearchEnabled?: boolean
}

/** 代码模式提示词实验请求：同模型 + 多提示词变体 + 代码生成 */
export interface CodeModePromptLabRequest {
  model: string
  promptVariants: string[]
  variantImageUrls?: string[][]
  conversationId?: string
  stream?: boolean
  webSearchEnabled?: boolean
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
