import client from './client'
import type { APIResponse, TalkRecommend } from '../types/api'

/** 推荐基础话术（GET /api/talk/recommend?task_id=） */
export async function getRecommendTalks(taskId: number): Promise<TalkRecommend> {
  const res = await client.get<APIResponse<TalkRecommend>>('/talk/recommend', {
    params: { task_id: taskId },
  })
  return res.data.data as TalkRecommend
}
