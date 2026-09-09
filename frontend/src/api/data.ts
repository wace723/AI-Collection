import client from './client'
import type { APIResponse, OrderList, UploadSummary } from '../types/api'

/** 上传 CSV 文件解析入库（仅 ADMIN） */
export async function uploadCsv(file: File): Promise<UploadSummary> {
  const form = new FormData()
  form.append('file', file)
  const res = await client.post<APIResponse<UploadSummary>>('/data/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data.data as UploadSummary
}

/** 订单分页列表 */
export async function listOrders(page = 1, limit = 50): Promise<OrderList> {
  const res = await client.get<APIResponse<OrderList>>('/data/orders', {
    params: { page, limit },
  })
  return res.data.data as OrderList
}
