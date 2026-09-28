import client from './client'
import type {
  APIResponse,
  CoverageMatrix,
  GenerateTalk,
  Placeholder,
  TalkRecommend,
  TalkTemplateInput,
  TalkTemplateManage,
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
 * LLM 调用（关闭 thinking 后约 2-5s），单独设 30s 超时（默认 10s 偏紧）。
 */
export async function generateTalk(taskId: number): Promise<GenerateTalk> {
  const res = await client.post<APIResponse<GenerateTalk>>(
    '/talk/generate',
    null,
    { params: { task_id: taskId }, timeout: 30000 },
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

// ── talk-003 话术模板管理 + 覆盖度 + 占位符 ────────────────────────

/** 话术模板列表（ADMIN，按档/轮/类型筛选） */
export async function listTemplates(params?: {
  risk_tier?: string
  scene?: string
  template_type?: string
}): Promise<TalkTemplateManage[]> {
  const res = await client.get<APIResponse<TalkTemplateManage[]>>(
    '/talk/templates',
    { params },
  )
  return res.data.data as TalkTemplateManage[]
}

/** 创建话术模板（ADMIN，占位符校验 400） */
export async function createTemplate(
  payload: TalkTemplateInput,
): Promise<TalkTemplateManage> {
  const res = await client.post<APIResponse<TalkTemplateManage>>(
    '/talk/templates',
    payload,
  )
  return res.data.data as TalkTemplateManage
}

/** 更新话术模板（ADMIN） */
export async function updateTemplate(
  id: number,
  payload: TalkTemplateInput,
): Promise<TalkTemplateManage> {
  const res = await client.put<APIResponse<TalkTemplateManage>>(
    `/talk/templates/${id}`,
    payload,
  )
  return res.data.data as TalkTemplateManage
}

/** 软删除话术模板（ADMIN，is_active=false） */
export async function deleteTemplate(
  id: number,
): Promise<TalkTemplateManage> {
  const res = await client.delete<APIResponse<TalkTemplateManage>>(
    `/talk/templates/${id}`,
  )
  return res.data.data as TalkTemplateManage
}

/** 可用占位符列表（供模板编辑器「插入变量」按钮） */
export async function getPlaceholders(): Promise<Placeholder[]> {
  const res = await client.get<APIResponse<Placeholder[]>>(
    '/talk/templates/placeholders',
  )
  return res.data.data as Placeholder[]
}

/** 话术覆盖度矩阵（ADMIN，按当前 active risk_config 展开） */
export async function getCoverage(): Promise<CoverageMatrix> {
  const res = await client.get<APIResponse<CoverageMatrix>>('/talk/coverage')
  return res.data.data as CoverageMatrix
}
