import client from './client'
import type { APIResponse, OrderList, UploadSummary } from '../types/api'

// 导入 CSV 单独设 120s 超时：数据量大时导入+自动跑批可能耗时数十秒
// （默认 client 10s 超时会导致大文件导入误超时、结果 Modal 不弹）
const UPLOAD_TIMEOUT = 120000

/** 导入待支付订单 CSV（全量/增量共用，仅 ADMIN） */
export async function uploadPendingCsv(file: File): Promise<UploadSummary> {
  const form = new FormData()
  form.append('file', file)
  const res = await client.post<APIResponse<UploadSummary>>(
    '/data/upload-pending',
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: UPLOAD_TIMEOUT,
    },
  )
  return res.data.data as UploadSummary
}

/** 导入已支付订单 CSV（回写支付状态，仅 ADMIN） */
export async function uploadPaidCsv(file: File): Promise<UploadSummary> {
  const form = new FormData()
  form.append('file', file)
  const res = await client.post<APIResponse<UploadSummary>>(
    '/data/upload-paid',
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: UPLOAD_TIMEOUT,
    },
  )
  return res.data.data as UploadSummary
}

/** 订单分页列表 */
export async function listOrders(page = 1, limit = 50): Promise<OrderList> {
  const res = await client.get<APIResponse<OrderList>>('/data/orders', {
    params: { page, limit },
  })
  return res.data.data as OrderList
}
