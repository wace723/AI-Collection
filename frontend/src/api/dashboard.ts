import client from './client'
import type {
  APIResponse,
  DailyDashboard,
  MonthlyDashboard,
  WeeklyDashboard,
} from '../types/api'

/** 日大盘（新增任务/各档/回款/回款率/风险分布/账龄分布） */
export async function getDailyDashboard(): Promise<DailyDashboard> {
  const res = await client.get<APIResponse<DailyDashboard>>('/dashboard/daily')
  return res.data.data as DailyDashboard
}

/** 周大盘（7 日趋势 + 催收员绩效排名） */
export async function getWeeklyDashboard(): Promise<WeeklyDashboard> {
  const res = await client.get<APIResponse<WeeklyDashboard>>('/dashboard/weekly')
  return res.data.data as WeeklyDashboard
}

/** 月大盘（月度欠费率/回款率/各档催收效果） */
export async function getMonthlyDashboard(): Promise<MonthlyDashboard> {
  const res = await client.get<APIResponse<MonthlyDashboard>>(
    '/dashboard/monthly',
  )
  return res.data.data as MonthlyDashboard
}
