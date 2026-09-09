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

/** CSV 上传结果统计 */
export interface UploadSummary {
  inserted: number
  skipped: number
  errors: string[]
}

/** 订单列表项 */
export interface Order {
  id: number
  supplier_no: string
  supplier_name: string
  biz_no: string
  service_fee_order_no: string
  tender_type_desc: string | null
  purchase_type_desc: string | null
  win_bid_date: string | null
  register_area: string | null
  pay_status: string | null
  pay_time: string | null
  risk_prob: number | null
  risk_tier: string | null
  risk_calc_time: string | null
}

/** 订单分页列表 */
export interface OrderList {
  items: Order[]
  total: number
  page: number
  limit: number
}

/** 风险重算结果统计 */
export interface RecalcRiskSummary {
  recalculated: number
  skipped: number
  tiers: Record<string, number>
}

/** 风险档枚举 */
export type RiskTier = 'HIGH' | 'MEDIUM' | 'LOW'

/** 催收场景枚举 */
export type Scene = 'FIRST' | 'SECOND' | 'THIRD' | 'DISPUTE' | 'PROMISE'

/** 催收时点配置 */
export interface CollectionSchedule {
  risk_tier: RiskTier
  day_offset: number
  scene: Scene
  seq: number
  is_active: boolean
}

/** 风险档配置（含关联催收时点） */
export interface RiskConfig {
  id: number
  version: number
  high_threshold: number
  medium_threshold: number
  is_active: boolean
  created_by: number | null
  created_at: string
  updated_at: string
  schedules: CollectionSchedule[]
}

/** 风险档配置更新输入 */
export interface RiskConfigUpdate {
  high_threshold: number
  medium_threshold: number
  schedules: CollectionSchedule[]
}
