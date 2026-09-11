import myAxios from '@/request.ts'
import type { BaseResponse } from '@/api/user.ts'

/**
 * 提示词模板与 AI 优化相关接口类型定义（与后端 Pydantic 模型对应）
 */

/** 策略类型：直接提问 / CoT 思维链 / 角色扮演 / Few-shot 示例学习 */
export type PromptStrategy = 'direct' | 'cot' | 'role_play' | 'few_shot'

/** 质量等级：优 / 良 / 中 / 差（功能扩展 4） */
export type PromptQualityLevel = 'excellent' | 'good' | 'fair' | 'poor'

/** 提示词模板 */
export interface PromptTemplateVO {
  id: string
  name: string
  description?: string
  strategy: PromptStrategy | string
  /** 策略显示名（后端补充） */
  strategyName: string
  content: string
  /** 模板里用到的变量名列表，如 ["role", "question"] */
  variables?: string[]
  category?: string
  /** 是否为预设模板（预设模板不可修改、删除） */
  isPreset: boolean
  /** 是否公开到社区（功能扩展 2） */
  isPublic?: boolean
  usageCount?: number
  isActive: boolean
  createTime?: string
  /** 社区互动数据（功能扩展 2） */
  likeCount?: number
  favoriteCount?: number
  /** 当前用户是否已点赞 / 已收藏 */
  liked?: boolean
  favorited?: boolean
  /** 创建者信息（社区里展示「谁分享的」） */
  authorId?: number
  authorName?: string
}

/** 提示词优化结果 */
export interface PromptOptimizationVO {
  issues: string[]
  optimizedPrompt: string
  improvements: string[]
  /** 原始提示词质量评分 0-100（功能扩展 4） */
  qualityScore?: number
  /** 质量等级（功能扩展 4） */
  qualityLevel?: PromptQualityLevel
}

/** 优化历史记录（功能扩展 3） */
export interface PromptOptimizationHistoryVO {
  id: string
  originalPrompt: string
  optimizedPrompt?: string
  issues: string[]
  improvements: string[]
  qualityScore?: number
  qualityLevel?: PromptQualityLevel
  evaluationModel?: string
  createTime?: string
}

/** 模板变量填充结果（功能扩展 1） */
export interface PromptVariableFillVO {
  content: string
  /** 仍未填值的变量名，前端需要提示用户 */
  unfilledVariables: string[]
}

/** 创建模板请求 */
export interface CreatePromptTemplateRequest {
  name: string
  description?: string
  strategy: string
  content: string
  variables?: string[]
  category?: string
  isPublic?: boolean
}

/**
 * 获取模板列表（预设模板 + 自己的自定义模板 + 他人公开的模板）
 */
export async function listTemplates(params?: { strategy?: string }) {
  return myAxios.get<BaseResponse<PromptTemplateVO[]>>('/prompt/template/list', { params })
}

/**
 * 获取社区公开模板（功能扩展 2）
 */
export async function listCommunityTemplates(params?: { strategy?: string; sortBy?: string }) {
  return myAxios.get<BaseResponse<PromptTemplateVO[]>>('/prompt/template/community', { params })
}

/**
 * 获取当前用户收藏的模板（功能扩展 2）
 */
export async function listFavoriteTemplates() {
  return myAxios.get<BaseResponse<PromptTemplateVO[]>>('/prompt/template/favorites')
}

/**
 * 创建自定义模板
 */
export async function createTemplate(data: CreatePromptTemplateRequest) {
  return myAxios.post<BaseResponse<string>>('/prompt/template/add', data)
}

/**
 * 增加模板使用次数
 */
export async function incrementUsage(templateId: string) {
  return myAxios.post<BaseResponse<boolean>>('/prompt/template/use', null, {
    params: { templateId },
  })
}

/**
 * 填充模板变量（功能扩展 1）
 */
export async function fillTemplateVariables(data: {
  templateId: string
  variables: Record<string, string>
}) {
  return myAxios.post<BaseResponse<PromptVariableFillVO>>('/prompt/template/fill', data)
}

/**
 * 点赞 / 取消点赞模板（功能扩展 2）
 */
export async function toggleTemplateLike(templateId: string) {
  return myAxios.post<BaseResponse<boolean>>('/prompt/template/like', null, {
    params: { templateId },
  })
}

/**
 * 收藏 / 取消收藏模板（功能扩展 2）
 */
export async function toggleTemplateFavorite(templateId: string) {
  return myAxios.post<BaseResponse<boolean>>('/prompt/template/favorite', null, {
    params: { templateId },
  })
}

/**
 * 分析并优化提示词（同时会落一条优化历史）
 */
export async function optimizePrompt(data: {
  originalPrompt: string
  aiResponse?: string
  evaluationModel?: string
}) {
  return myAxios.post<BaseResponse<PromptOptimizationVO>>('/prompt/optimization/analyze', data)
}

/**
 * 获取优化历史（功能扩展 3）
 */
export async function listOptimizationHistory(params?: { limit?: number }) {
  return myAxios.get<BaseResponse<PromptOptimizationHistoryVO[]>>(
    '/prompt/optimization/history',
    { params },
  )
}

/**
 * 删除一条优化历史（功能扩展 3）
 */
export async function deleteOptimizationHistory(historyId: string) {
  return myAxios.post<BaseResponse<boolean>>('/prompt/optimization/history/delete', null, {
    params: { historyId },
  })
}

/** 质量等级 → 展示文案（功能扩展 4） */
export const QUALITY_LEVEL_TEXT: Record<string, string> = {
  excellent: '优秀',
  good: '良好',
  fair: '一般',
  poor: '待改进',
}

/** 质量等级 → ant-design 主题色（功能扩展 4） */
export const QUALITY_LEVEL_COLOR: Record<string, string> = {
  excellent: 'green',
  good: 'blue',
  fair: 'orange',
  poor: 'red',
}
