import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Card,
  Table,
  Button,
  Modal,
  Input,
  Tag,
  Tooltip,
  message,
  Empty,
  Divider,
} from 'antd'
import { ReloadOutlined, EditOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  getCoverage,
  listTemplates,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  getPlaceholders,
} from '../../api/talk'
import type {
  CoverageCell,
  CoverageMatrix,
  Placeholder,
  TalkTemplateInput,
  TalkTemplateManage,
} from '../../types/api'

const { TextArea } = Input

const TIER_COLOR: Record<string, string> = {
  HIGH: 'red',
  MEDIUM: 'orange',
  LOW: 'green',
}

const TIER_LABEL: Record<string, string> = {
  HIGH: '高风险',
  MEDIUM: '中风险',
  LOW: '低风险',
}

/** 一个格子的编辑状态：固定模板 + AI 提示词两条（可能各自已存在或新建） */
interface CellEditState {
  cell: CoverageCell
  // 该格现有的 FIXED / AI_PROMPT 模板（null=未配，需新建）
  fixedExisting: TalkTemplateManage | null
  aiExisting: TalkTemplateManage | null
  fixedContent: string
  aiSystemPrompt: string
  aiUserPrompt: string
}

/** 话术配置后台：覆盖度矩阵 + 居中弹窗编辑（talk-003） */
export default function TalkConfigPanel() {
  const [coverage, setCoverage] = useState<CoverageMatrix | null>(null)
  const [templates, setTemplates] = useState<TalkTemplateManage[]>([])
  const [placeholders, setPlaceholders] = useState<Placeholder[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editState, setEditState] = useState<CellEditState | null>(null)
  const [saving, setSaving] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [cov, tpls, phs] = await Promise.all([
        getCoverage().catch(() => null),
        listTemplates().catch(() => [] as TalkTemplateManage[]),
        getPlaceholders().catch(() => [] as Placeholder[]),
      ])
      if (cov) setCoverage(cov)
      setTemplates(tpls)
      setPlaceholders(phs)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  /** 打开编辑弹窗：同时加载该格的 FIXED + AI_PROMPT 现有模板 */
  const openEditor = (cell: CoverageCell) => {
    const fixedExisting =
      templates.find(
        (t) =>
          t.risk_tier === cell.risk_tier &&
          t.scene === cell.scene &&
          t.template_type === 'FIXED',
      ) || null
    const aiExisting =
      templates.find(
        (t) =>
          t.risk_tier === cell.risk_tier &&
          t.scene === cell.scene &&
          t.template_type === 'AI_PROMPT',
      ) || null
    setEditState({
      cell,
      fixedExisting,
      aiExisting,
      fixedContent: fixedExisting?.content || '',
      aiSystemPrompt: aiExisting?.system_prompt || '',
      aiUserPrompt: aiExisting?.user_prompt || '',
    })
    setModalOpen(true)
  }

  /** 保存：FIXED 和 AI_PROMPT 各自处理（有则更新，无则新建，空则保留不建） */
  const onSave = async () => {
    if (!editState) return
    setSaving(true)
    try {
      const { cell, fixedExisting, aiExisting, fixedContent, aiSystemPrompt, aiUserPrompt } =
        editState
      const base: Omit<TalkTemplateInput, 'template_type' | 'content' | 'system_prompt' | 'user_prompt'> = {
        name: `${cell.risk_tier}×${cell.scene}`,
        risk_tier: cell.risk_tier,
        scene: cell.scene,
        is_active: true,
      }

      // 固定模板：有内容则保存（新建或更新），无内容且有现存则不删（保留）
      if (fixedContent.trim()) {
        const payload: TalkTemplateInput = {
          ...base,
          template_type: 'FIXED',
          content: fixedContent,
        }
        if (fixedExisting) {
          await updateTemplate(fixedExisting.id, payload)
        } else {
          await createTemplate(payload)
        }
      }

      // AI 提示词：system+user 都有内容才保存
      if (aiSystemPrompt.trim() && aiUserPrompt.trim()) {
        const payload: TalkTemplateInput = {
          ...base,
          template_type: 'AI_PROMPT',
          system_prompt: aiSystemPrompt,
          user_prompt: aiUserPrompt,
        }
        if (aiExisting) {
          await updateTemplate(aiExisting.id, payload)
        } else {
          await createTemplate(payload)
        }
      }

      message.success('话术配置已保存')
      setModalOpen(false)
      loadData()
    } catch {
      /* 校验/接口错误由全局拦截器处理 */
    } finally {
      setSaving(false)
    }
  }

  /** 删除该格两类模板 */
  const onDeleteCell = async () => {
    if (!editState) return
    const { fixedExisting, aiExisting } = editState
    if (fixedExisting) await deleteTemplate(fixedExisting.id)
    if (aiExisting) await deleteTemplate(aiExisting.id)
    message.success('该格话术已删除')
    setModalOpen(false)
    loadData()
  }

  const columns: ColumnsType<CoverageCell> = [
    {
      title: '风险档',
      dataIndex: 'risk_tier',
      render: (tier: string) => (
        <Tag color={TIER_COLOR[tier]}>{TIER_LABEL[tier] || tier}</Tag>
      ),
    },
    {
      title: '轮次',
      dataIndex: 'scene',
      render: (scene: string) => `第 ${scene.replace('ROUND_', '')} 轮`,
    },
    {
      title: '催收时点',
      dataIndex: 'day_offset',
      render: (d: number) => `中标后第 ${d} 天`,
    },
    {
      title: '固定模板',
      dataIndex: 'fixed_configured',
      render: (v: boolean) =>
        v ? <Tag color="green">已配</Tag> : <Tag color="default">未配</Tag>,
    },
    {
      title: 'AI提示词',
      dataIndex: 'ai_prompt_configured',
      render: (v: boolean) =>
        v ? <Tag color="blue">已配</Tag> : <Tag color="default">未配</Tag>,
    },
    {
      title: '操作',
      render: (_: unknown, record: CoverageCell) => (
        <Button
          size="small"
          icon={<EditOutlined />}
          onClick={() => openEditor(record)}
        >
          编辑
        </Button>
      ),
    },
  ]

  const cells = coverage?.cells || []
  const hasCoverage = cells.length > 0

  return (
    <Card
      title="话术配置（按风险档 × 轮次）"
      size="small"
      extra={
        <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>
          刷新
        </Button>
      }
    >
      <p style={{ color: '#888', marginBottom: 12 }}>
        按当前生效风险档配置的触达轮次展开。红色高亮格为缺口（固定模板未配），点击「编辑」配置该格的话术与 AI 提示词。
      </p>

      {!hasCoverage ? (
        <Empty description="尚无生效风险档配置，请先在「风险档配置」Tab 配置催收时点" />
      ) : (
        <Table<CoverageCell>
          rowKey={(r) => `${r.risk_tier}-${r.scene}`}
          columns={columns}
          dataSource={cells}
          loading={loading}
          pagination={false}
          size="small"
          rowClassName={(r) => (!r.fixed_configured ? 'talk-missing-row' : '')}
        />
      )}

      <Modal
        title={
          editState
            ? `话术配置 — ${TIER_LABEL[editState.cell.risk_tier]} 第 ${editState.cell.scene.replace('ROUND_', '')} 轮`
            : '话术配置'
        }
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        width={720}
        destroyOnClose
        footer={[
          editState && (editState.fixedExisting || editState.aiExisting) ? (
            <Button key="delete" danger onClick={onDeleteCell} loading={saving}>
              删除该格话术
            </Button>
          ) : null,
          <Button key="cancel" onClick={() => setModalOpen(false)}>
            取消
          </Button>,
          <Button key="save" type="primary" onClick={onSave} loading={saving}>
            保存
          </Button>,
        ]}
      >
        {editState && (
          <>
            <Divider orientation="left" plain>
              固定模板话术
            </Divider>
            <PlaceholderTextArea
              label="话术正文（催收员工作台直接展示）"
              value={editState.fixedContent}
              onChange={(v) =>
                setEditState({ ...editState, fixedContent: v })
              }
              placeholders={placeholders}
              placeholder="如：{供应商名称}您好，订单{订单号}（标的：{标的名称}）已逾期，请尽快缴费。"
            />

            <Divider orientation="left" plain>
              AI 提示词（喂 LLM 生成话术，可选）
            </Divider>
            <PlaceholderTextArea
              label="System 提示词（追加在合规基线后）"
              value={editState.aiSystemPrompt}
              onChange={(v) =>
                setEditState({ ...editState, aiSystemPrompt: v })
              }
              placeholders={placeholders}
              placeholder="如：语气正式但紧迫，强调逾期对投标资格的影响。"
            />
            <div style={{ height: 12 }} />
            <PlaceholderTextArea
              label="User 提示词"
              value={editState.aiUserPrompt}
              onChange={(v) =>
                setEditState({ ...editState, aiUserPrompt: v })
              }
              placeholders={placeholders}
              placeholder="如：请为供应商{供应商名称}生成催收话术，订单{订单号}..."
            />
          </>
        )}
      </Modal>

      <style>{`
        .talk-missing-row td { background: #fff1f0 !important; }
      `}</style>
    </Card>
  )
}

/**
 * 带「插入变量」的 TextArea：所有变量直接平铺展示，点击插入到光标位置。
 * 受控组件（value + onChange），不依赖 Form 实例。
 */
function PlaceholderTextArea({
  label,
  value,
  onChange,
  placeholders,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholders: Placeholder[]
  placeholder?: string
}) {
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  const insertPlaceholder = (key: string) => {
    const ta = inputRef.current
    if (!ta) return
    const start = ta.selectionStart ?? value.length
    const end = ta.selectionEnd ?? value.length
    const insert = `{${key}}`
    onChange(value.slice(0, start) + insert + value.slice(end))
    setTimeout(() => {
      ta.focus()
      ta.setSelectionRange(start + insert.length, start + insert.length)
    }, 0)
  }

  return (
    <div>
      <div style={{ fontSize: 13, color: '#555', marginBottom: 4 }}>{label}</div>
      {/* 所有变量直接平铺展示（flex wrap），点击插入 */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 4,
          marginBottom: 6,
          padding: 8,
          background: '#fafafa',
          borderRadius: 4,
        }}
      >
        {placeholders.map((p) => (
          <Tooltip key={p.key} title={p.description}>
            <Tag
              style={{ cursor: 'pointer', margin: 0 }}
              color="blue"
              onClick={() => insertPlaceholder(p.key)}
            >
              {p.key}
            </Tag>
          </Tooltip>
        ))}
      </div>
      <TextArea
        ref={inputRef as never}
        rows={4}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onFocus={(e) => {
          inputRef.current = e.target as HTMLTextAreaElement
        }}
      />
    </div>
  )
}
