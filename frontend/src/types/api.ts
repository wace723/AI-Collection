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

/** 任务状态 */
export type TaskStatus =
  | 'PENDING_ASSIGN'
  | 'PENDING'
  | 'IN_PROGRESS'
  | 'DONE'
  | 'CANCELLED'

/** 处理结果枚举 */
export type TaskResultType =
  | 'PAID'
  | 'PROMISE'
  | 'DISPUTE'
  | 'LOST_CONTACT'
  | 'OTHER'

/** 催收任务（列表/详情基础字段） */
export interface Task {
  id: number
  order_id: number
  service_fee_order_no: string
  risk_tier: RiskTier
  scene: Scene
  day_offset: number
  due_date: string
  status: TaskStatus
  assignee_id: number | null
  assigned_at: string | null
  result: TaskResultType | null
  result_note: string | null
  next_followup_date: string | null
  batch_id: string
}

/** 任务分页列表 */
export interface TaskList {
  items: Task[]
  total: number
  page: number
  limit: number
}

/** 任务列表查询参数 */
export interface TaskListParams {
  status?: TaskStatus
  assignee?: number
  page?: number
  size?: number
}

/** 回填结果入参 */
export interface TaskResultInput {
  result: TaskResultType
  note?: string
  next_followup_date?: string
  talk_used?: string
}

/** 任务详情内嵌的订单摘要 */
export interface OrderBrief {
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
}

/** 任务详情内嵌的用户特征摘要 */
export interface FeatureBrief {
  history_fee_order_count: number | null
  last_pay_duration_days: number | null
  avg_pay_duration_days: number | null
  fwsc_history_pay_amount: number | null
  signup_count: number | null
  bidding_count: number | null
  win_count: number | null
  win_rate: number | null
  active_90d: number | null
  is_member_at_win: boolean | null
  register_fund: number | null
  supplier_categories: string | null
}

/** 任务详情（含订单摘要 + 特征摘要） */
export interface TaskDetail extends Task {
  order: OrderBrief | null
  feature: FeatureBrief | null
}

/** 跑批摘要 */
export interface BatchRunOut {
  batch_id: string
  today: string
  scanned: number
  generated: number
  idempotent_skipped: number
  by_tier: Record<string, number>
}

/** 分配摘要 */
export interface AssignmentRunOut {
  assigned: number
  skipped: number
  by_assignee: Record<number, number>
  assignee_names: Record<number, string>
}

/** 批次状态聚合 */
export interface BatchStatusOut {
  batch_id: string
  total: number
  by_status: Record<string, number>
  by_tier: Record<string, number>
}
