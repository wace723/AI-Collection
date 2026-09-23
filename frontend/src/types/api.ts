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

/** 跑批结果摘要（待支付导入后自动跑批返回） */
export interface BatchResultOut {
  generated: number
  deleted: number
  skipped: number
  by_tier: Record<string, number>
}

/** CSV 上传结果统计 */
export interface UploadSummary {
  inserted: number
  skipped: number
  updated: number
  errors: string[]
  batch_result?: BatchResultOut | null
}

/** 订单列表项 */
export interface Order {
  id: number
  supplier_no: string
  supplier_name: string
  biz_no: string
  service_fee_order_no: string
  subject_name: string | null
  tender_type_desc: string | null
  purchase_type_desc: string | null
  bid_category: string | null
  contract_type: string | null
  subject_estimate_amount: number | null
  engineering_bureau: string | null
  subsidiary: string | null
  win_bid_date: string | null
  order_generated_date: string | null
  register_area: string | null
  register_province: string | null
  pay_status: string | null
  pay_time: string | null
  actual_pay_duration_days: number | null
  risk_prob: number | null
  risk_tier: string | null
  risk_import_time: string | null
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

/** 处理结果枚举（data-003 两分类） */
export type TaskResultType = 'UNREACHED' | 'REACHED'

/** 订单催收状态（data-003 状态机） */
export type CollectionState = 'NO_NEED' | 'PENDING_COLLECTION' | 'COLLECTED' | 'FINALIZED'

/** 催收任务（列表/详情基础字段） */
export interface Task {
  id: number
  order_id: number
  service_fee_order_no: string
  supplier_name: string
  subject_name: string | null
  subject_estimate_amount: number | null
  win_bid_date: string | null
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
  collection_state: CollectionState
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
  collection_state?: CollectionState
  page?: number
  size?: number
}

/** 回填结果入参（data-003 两分类，移除 next_followup_date） */
export interface TaskResultInput {
  result: TaskResultType
  note?: string
  talk_used?: string
}

/** 任务详情内嵌的订单摘要（含标的/品类/支付等完整字段） */
export interface OrderBrief {
  id: number
  supplier_no: string
  supplier_name: string
  biz_no: string
  service_fee_order_no: string
  subject_name: string | null
  tender_type_desc: string | null
  purchase_type_desc: string | null
  bid_category: string | null
  contract_type: string | null
  subject_estimate_amount: number | null
  engineering_bureau: string | null
  subsidiary: string | null
  win_bid_date: string | null
  order_generated_date: string | null
  register_area: string | null
  register_province: string | null
  pay_status: string | null
  pay_time: string | null
  actual_pay_duration_days: number | null
  risk_prob: number | null
  risk_tier: string | null
  risk_import_time: string | null
}

/** 任务详情内嵌的用户特征摘要（完整画像字段，分类展示用） */
export interface FeatureBrief {
  // A 类 · 缴费历史
  history_fee_order_count: number | null
  last_pay_duration_days: number | null
  avg_pay_duration_days: number | null
  // B 类 · 活跃度与支付
  fwsc_history_pay_amount: number | null
  signup_count: number | null
  bidding_count: number | null
  win_count: number | null
  win_rate: number | null
  active_90d: number | null
  first_win_interval_days: number | null
  is_member_at_win: boolean | null
  member_purchase_count_before_win: number | null
  // C 类 · 资质与标签
  register_fund: number | null
  register_interval_days: number | null
  in_date_interval_days: number | null
  entry_interval_days: number | null
  supplier_categories: string | null
  ads_win_rate: number | null
  high_quality_cnt: number | null
  cooperate_org_num: number | null
  total_perform_project_num: number | null
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

/** 推荐话术项（content 已渲染） */
export interface TalkTemplateItem {
  template_id: number
  name: string
  risk_tier: string
  age_bucket: string
  scene: string
  user_feature_tag: string | null
  content: string
  score: number
}

/** 话术推荐响应 */
export interface TalkRecommend {
  task_id: number
  age_bucket: string
  user_tag: string | null
  templates: TalkTemplateItem[]
}

/** AI 话术配置（api_key 脱敏） */
export interface AIConfig {
  provider: string
  api_key_masked: string | null
  base_url: string | null
  model: string | null
  enabled: boolean
  from_db: boolean
  updated_at: string | null
  updated_by: number | null
}

/** AI 配置更新入参（api_key 空则保留旧值） */
export interface AIConfigUpdate {
  provider: 'mock' | 'openai_compatible'
  api_key?: string
  base_url?: string
  model?: string
  enabled: boolean
}

/** AI 话术生成响应 */
export interface GenerateTalk {
  enabled: boolean
  content: string | null
  conversation_id: number | null
  provider: string
  fallback: boolean
  fallback_reason: string | null
}

// ── 数据大盘（dash-001） ─────────────────────────────────────────

/** 周大盘趋势单日点 */
export interface DailyTrendPoint {
  date: string
  new_tasks: number
  completed: number
  completion_rate: number
  paid: number
  processed: number
  paid_rate: number
}

/** 催收员绩效 */
export interface CollectorPerformance {
  collector_id: number
  username: string
  display_name: string
  paid_count: number
}

/** 日大盘 */
export interface DailyDashboard {
  date: string
  new_tasks: number
  new_tasks_by_tier: Record<string, number>
  paid_count: number
  processed_count: number
  paid_rate: number
  unpaid_total: number
  risk_distribution: Record<string, number>
  age_distribution: Record<string, number>
}

/** 周大盘 */
export interface WeeklyDashboard {
  week_start: string
  week_end: string
  trend: DailyTrendPoint[]
  collector_ranking: CollectorPerformance[]
}

/** 单风险档催收效果 */
export interface TierEffect {
  risk_tier: string
  processed: number
  paid: number
  paid_rate: number
}

/** 月大盘 */
export interface MonthlyDashboard {
  month_start: string
  month_end: string
  unpaid_rate: number
  paid_count: number
  processed_count: number
  paid_rate: number
  tier_effects: TierEffect[]
}

// ── 用户管理（supervisor 增强） ──────────────────────────────────

/** 用户（含 id/角色/状态，与 auth User 同结构） */
export interface UserAccount {
  id: number
  username: string
  display_name: string
  role: Role
  is_active: boolean
}

/** 新增用户入参 */
export interface UserCreate {
  username: string
  password: string
  display_name: string
  role: Role
}

/** 编辑用户入参（全可选，reset_password 重置为 admin123） */
export interface UserUpdate {
  role?: Role
  is_active?: boolean
  reset_password?: boolean
}

// ── 员工绩效（supervisor 增强） ──────────────────────────────────

/** 催收员绩效 */
export interface StaffPerformance {
  id: number
  username: string
  display_name: string
  role: string
  is_active: boolean
  pending_count: number
  in_progress_count: number
  done_count: number
  paid_count: number
  paid_rate: number
  today_reached: number
  today_unreached: number
  today_pending: number
}
