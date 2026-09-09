import client from './client'
import { setToken, clearToken } from '../utils/auth'
import type { LoginData, User } from '../types/api'

/** 登录：成功后存 token，返回用户与 token */
export async function login(username: string, password: string): Promise<LoginData> {
  const res = await client.post('/auth/login', { username, password })
  const data = res.data.data as LoginData
  setToken(data.access_token)
  return data
}

/** 获取当前登录用户 */
export async function getMe(): Promise<User> {
  const res = await client.get('/auth/me')
  return res.data.data as User
}

/** 登出：清除本地 token */
export function logout(): void {
  clearToken()
}
