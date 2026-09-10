import myAxios from '@/request.ts'
import type { BaseResponse, PageResult } from '@/api/user.ts'

/**
 * 模型相关接口类型定义（与后端 ModelVO 对应）
 */
export interface ModelVO {
  id: string
  name: string
  description?: string
  provider?: string
  contextLength?: number
  inputPrice?: number
  outputPrice?: number
  recommended: number
  isChina: number
  /** 模型发布时间（Unix 秒，取自 OpenRouter）—— 下拉里按它由新到旧排 */
  created?: number
  tags?: string
}

/**
 * 查询模型列表（国内模型优先返回）
 */
export async function listModels() {
  return myAxios.get<BaseResponse<ModelVO[]>>('/model/list')
}

/**
 * 从 OpenRouter 同步模型列表（管理员）
 */
export async function syncModels() {
  return myAxios.post<BaseResponse<number>>('/model/sync')
}

export type { BaseResponse, PageResult }
