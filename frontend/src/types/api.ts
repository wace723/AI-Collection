/** 统一 API 响应类型 */
export interface APIResponse<T = unknown> {
  success: boolean
  data: T | null
  error: string | null
}

export interface HealthInfo {
  status: string
  app: string
  version: string
}

/** 用户角色 */
export type Role = 'COLLECTOR' | 'SUPERVISOR' | 'ADMIN'

/** 用户信息 */
export interface User {
  id: number
  username: string
  display_name: string
  role: Role
  is_active: boolean
}

/** 登录返回数据 */
export interface LoginData {
  access_token: string
  token_type: string
  user: User
}
