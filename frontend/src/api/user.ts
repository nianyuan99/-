import myAxios from '@/request.ts'

/**
 * 用户接口类型定义（与后端 Pydantic 模型对应）
 */

export interface LoginUserVO {
  id: number
  userAccount: string
  userName?: string
  userAvatar?: string
  userProfile?: string
  userRole: string
  createTime: string
}

export interface UserVO {
  id: number
  userAccount: string
  userName?: string
  userAvatar?: string
  userProfile?: string
  userRole: string
  createTime: string
  updateTime: string
}

export interface UserRegisterRequest {
  userAccount: string
  userPassword: string
  checkPassword: string
}

export interface UserLoginRequest {
  userAccount: string
  userPassword: string
}

export interface UserQueryRequest {
  userAccount?: string
  userName?: string
  current?: number
  pageSize?: number
}

export interface BaseResponse<T> {
  code: number
  data: T
  message: string
}

export interface PageResult<T> {
  records: T[]
  total: number
  current: number
  pageSize: number
}

/**
 * 用户注册
 */
export async function userRegister(params: UserRegisterRequest) {
  return myAxios.post<BaseResponse<number>>('/user/register', params)
}

/**
 * 用户登录
 */
export async function userLogin(params: UserLoginRequest) {
  return myAxios.post<BaseResponse<LoginUserVO>>('/user/login', params)
}

/**
 * 获取当前登录用户
 */
export async function getLoginUser() {
  return myAxios.get<BaseResponse<LoginUserVO>>('/user/get/login')
}

/**
 * 用户注销
 */
export async function userLogout() {
  return myAxios.post<BaseResponse<boolean>>('/user/logout')
}

/**
 * 删除用户（管理员）
 */
export async function deleteUser(id: number) {
  return myAxios.post<BaseResponse<boolean>>('/user/delete', { id })
}

/**
 * 分页查询用户（管理员）
 */
export async function listUserVoByPage(params: UserQueryRequest) {
  return myAxios.post<BaseResponse<PageResult<UserVO>>>('/user/list/page/vo', params)
}
