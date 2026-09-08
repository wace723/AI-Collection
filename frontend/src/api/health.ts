import client from './client'
import type { HealthInfo } from '../types/api'

/** 后端健康检查：经 /api 前缀走 vite proxy，验证前后端联通 */
export async function getHealth(): Promise<HealthInfo> {
  const res = await client.get('/health')
  return res.data
}
