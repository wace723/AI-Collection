import client from './client'
import { getMe } from './auth'
import type {
  APIResponse,
  AssignmentRunOut,
  BatchRunOut,
  BatchStatusOut,
  Task,
  TaskDetail,
  TaskList,
  TaskListParams,
  TaskResultInput,
} from '../types/api'

/** 获取当前登录用户（用于工作台判断角色/显示） */
export { getMe }

/** 任务分页列表（COLLECTOR 后端强制只看自己） */
export async function listTasks(params: TaskListParams = {}): Promise<TaskList> {
  const res = await client.get<APIResponse<TaskList>>('/tasks', {
    params: {
      status: params.status,
      assignee: params.assignee,
      page: params.page ?? 1,
      size: params.size ?? 20,
    },
  })
  return res.data.data as TaskList
}

/** 任务详情（含订单摘要 + 特征摘要） */
export async function getTask(taskId: number): Promise<TaskDetail> {
  const res = await client.get<APIResponse<TaskDetail>>(`/tasks/${taskId}`)
  return res.data.data as TaskDetail
}

/** 回填处理结果：IN_PROGRESS → DONE/PROMISE 改期 */
export async function submitTaskResult(
  taskId: number,
  payload: TaskResultInput,
): Promise<Task> {
  const res = await client.post<APIResponse<Task>>(
    `/tasks/${taskId}/result`,
    payload,
  )
  return res.data.data as Task
}

/** 手动触发跑批（ADMIN） */
export async function runBatch(recalc = true): Promise<BatchRunOut> {
  const res = await client.post<APIResponse<BatchRunOut>>(
    '/tasks/batch/run',
    null,
    { params: { recalc } },
  )
  return res.data.data as BatchRunOut
}

/** 手动触发分配（ADMIN） */
export async function runAssign(): Promise<AssignmentRunOut> {
  const res = await client.post<APIResponse<AssignmentRunOut>>('/tasks/assign/run')
  return res.data.data as AssignmentRunOut
}

/** 批次状态聚合 */
export async function getBatchStatus(
  batchId: string,
): Promise<BatchStatusOut> {
  const res = await client.get<APIResponse<BatchStatusOut>>(
    `/tasks/batch/status/${batchId}`,
  )
  return res.data.data as BatchStatusOut
}

/** 主管手动改派任务（SUPERVISOR/ADMIN） */
export async function reassignTask(
  taskId: number,
  assigneeId: number,
): Promise<Task> {
  const res = await client.post<APIResponse<Task>>(
    `/tasks/${taskId}/reassign`,
    null,
    { params: { assignee_id: assigneeId } },
  )
  return res.data.data as Task
}
