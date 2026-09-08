import client from './client'
import type { HealthInfo } from '../types/api'

/** 后端健康检查（infra-001 用于验证前后端联通） */
export async function getHealth(): Promise<HealthInfo> {
  // 注意：/health 挂在根，不带 /api 前缀，用相对路径直接请求
  const res = await client.get('/health', { baseURL: '' })
  return res.data
}
