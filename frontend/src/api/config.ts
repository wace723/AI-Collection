import client from './client'
import type {
  AIConfig,
  AIConfigUpdate,
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

/** 当前 AI 话术配置（api_key 脱敏，主管/管理员可查） */
export async function getAIConfig(): Promise<AIConfig> {
  const res = await client.get<APIResponse<AIConfig>>('/config/ai')
  return res.data.data as AIConfig
}

/** 更新 AI 话术配置（主管/管理员；api_key 空则保留旧值） */
export async function updateAIConfig(
  payload: AIConfigUpdate,
): Promise<AIConfig> {
  const res = await client.put<APIResponse<AIConfig>>('/config/ai', payload)
  return res.data.data as AIConfig
}
