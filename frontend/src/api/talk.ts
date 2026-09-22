import client from './client'
import type {
  APIResponse,
  GenerateTalk,
  TalkRecommend,
} from '../types/api'

/** 推荐基础话术（GET /api/talk/recommend?task_id=） */
export async function getRecommendTalks(taskId: number): Promise<TalkRecommend> {
  const res = await client.get<APIResponse<TalkRecommend>>('/talk/recommend', {
    params: { task_id: taskId },
  })
  return res.data.data as TalkRecommend
}

/** AI 生成话术（POST /api/talk/generate?task_id=，失败降级模板）
 *
 * LLM 真实调用约 40s（glm-5.2），单独设 120s 超时（默认 10s 会误超时报错）。
 */
export async function generateTalk(taskId: number): Promise<GenerateTalk> {
  const res = await client.post<APIResponse<GenerateTalk>>(
    '/talk/generate',
    null,
    { params: { task_id: taskId }, timeout: 120000 },
  )
  return res.data.data as GenerateTalk
}

/** 话术反馈 useful/useless */
export async function sendFeedback(
  conversationId: number,
  feedback: 'useful' | 'useless',
): Promise<{ conversation_id: number; feedback: string }> {
  const res = await client.post<
    APIResponse<{ conversation_id: number; feedback: string }>
  >('/talk/feedback', { conversation_id: conversationId, feedback })
  return res.data.data as { conversation_id: number; feedback: string }
}
