import client from './client'
import type {
  APIResponse,
  UserAccount,
  UserCreate,
  UserUpdate,
} from '../types/api'

/** 用户列表（SUPERVISOR/ADMIN） */
export async function listUsers(): Promise<UserAccount[]> {
  const res = await client.get<APIResponse<UserAccount[]>>('/users')
  return res.data.data as UserAccount[]
}

/** 新增用户（ADMIN） */
export async function createUser(payload: UserCreate): Promise<UserAccount> {
  const res = await client.post<APIResponse<UserAccount>>('/users', payload)
  return res.data.data as UserAccount
}

/** 编辑用户（ADMIN）：改角色/停用启用/重置密码 */
export async function updateUser(
  id: number,
  payload: UserUpdate,
): Promise<UserAccount> {
  const res = await client.put<APIResponse<UserAccount>>(`/users/${id}`, payload)
  return res.data.data as UserAccount
}

/** 删除用户（ADMIN） */
export async function deleteUser(id: number): Promise<void> {
  await client.delete(`/users/${id}`)
}
