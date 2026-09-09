import client from './client'
import type {
  APIResponse,
  RiskConfig,
  RiskConfigUpdate,
} from '../types/api'

/** 当前生效风险档配置（登录可见） */
export async function getRiskConfig(): Promise<RiskConfig> {
  const res = await client.get<APIResponse<RiskConfig>>('/config/risk/current')
  return res.data.data as RiskConfig
}

/** 更新风险档配置，生成新版本（仅 ADMIN） */
export async function updateRiskConfig(
  payload: RiskConfigUpdate,
): Promise<RiskConfig> {
  const res = await client.put<APIResponse<RiskConfig>>(
    '/config/risk',
    payload,
  )
  return res.data.data as RiskConfig
}

/** 配置历史（仅 ADMIN） */
export async function getRiskHistory(): Promise<RiskConfig[]> {
  const res = await client.get<APIResponse<RiskConfig[]>>('/config/risk/history')
  return res.data.data as RiskConfig[]
}

/** 回滚到指定历史版本（仅 ADMIN，方案 B 复制为新版本） */
export async function rollbackRisk(version: number): Promise<RiskConfig> {
  const res = await client.post<APIResponse<RiskConfig>>(
    `/config/risk/rollback/${version}`,
  )
  return res.data.data as RiskConfig
}
