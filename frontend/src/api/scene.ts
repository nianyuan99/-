import myAxios from '@/request.ts'
import type { BaseResponse, PageResult } from '@/api/user.ts'

/**
 * 场景管理相关接口类型定义（与后端 SceneVO / ScenePromptVO 对应）
 */

export interface SceneVO {
  id: string
  name: string
  description?: string
  category?: string
  /** 1-预设场景 0-自定义场景 */
  isPreset: number
  isActive: number
  /** 场景下提示词数量 */
  promptCount?: number
  createTime: string
  updateTime: string
}

export interface ScenePromptVO {
  id: string
  sceneId: string
  promptIndex: number
  title: string
  content: string
  difficulty?: string
  tags?: string[]
  expectedOutput?: string
  createTime: string
  updateTime: string
}

export interface SceneDetailVO extends SceneVO {
  prompts: ScenePromptVO[]
}

export interface SceneQueryRequest {
  name?: string
  category?: string
  isPreset?: boolean
  current?: number
  pageSize?: number
}

export interface CreateSceneRequest {
  name: string
  description?: string
  category?: string
}

export interface UpdateSceneRequest {
  id: string
  name?: string
  description?: string
  category?: string
}

export interface AddScenePromptRequest {
  sceneId: string
  title: string
  content: string
  difficulty?: string
  tags?: string[]
  expectedOutput?: string
}

export interface UpdateScenePromptRequest {
  id: string
  title?: string
  content?: string
  difficulty?: string
  tags?: string[]
  expectedOutput?: string
}

/**
 * 创建场景
 */
export async function createScene(params: CreateSceneRequest) {
  return myAxios.post<BaseResponse<string>>('/scene/create', params)
}

/**
 * 更新场景
 */
export async function updateScene(params: UpdateSceneRequest) {
  return myAxios.post<BaseResponse<boolean>>('/scene/update', params)
}

/**
 * 删除场景
 */
export async function deleteScene(id: string) {
  return myAxios.post<BaseResponse<boolean>>('/scene/delete', { id })
}

/**
 * 获取场景详情（含提示词列表）
 */
export async function getScene(id: string) {
  return myAxios.get<BaseResponse<SceneDetailVO>>('/scene/get', { params: { id } })
}

/**
 * 分页查询场景列表
 */
export async function listSceneByPage(params: SceneQueryRequest) {
  return myAxios.post<BaseResponse<PageResult<SceneVO>>>('/scene/list/page', params)
}

/**
 * 查询可用场景（供批量测试选择）
 */
export async function listAvailableScenes() {
  return myAxios.get<BaseResponse<SceneVO[]>>('/scene/list/available')
}

/**
 * 查询场景分类
 */
export async function listSceneCategories() {
  return myAxios.get<BaseResponse<string[]>>('/scene/categories')
}

/**
 * 查询场景下的提示词列表
 */
export async function listScenePrompts(sceneId: string) {
  return myAxios.get<BaseResponse<ScenePromptVO[]>>('/scene/prompts', { params: { sceneId } })
}

/**
 * 添加提示词
 */
export async function addScenePrompt(params: AddScenePromptRequest) {
  return myAxios.post<BaseResponse<string>>('/scene/prompt/add', params)
}

/**
 * 更新提示词
 */
export async function updateScenePrompt(params: UpdateScenePromptRequest) {
  return myAxios.post<BaseResponse<boolean>>('/scene/prompt/update', params)
}

/**
 * 删除提示词
 */
export async function deleteScenePrompt(id: string) {
  return myAxios.post<BaseResponse<boolean>>('/scene/prompt/delete', { id })
}
