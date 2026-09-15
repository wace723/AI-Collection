import client from './client'
import type { APIResponse, StaffPerformance } from '../types/api'

/** 员工绩效统计（SUPERVISOR/ADMIN） */
export async function getStaffPerformance(): Promise<StaffPerformance[]> {
  const res = await client.get<APIResponse<StaffPerformance[]>>(
    '/supervisor/staff-performance',
  )
  return res.data.data as StaffPerformance[]
}
