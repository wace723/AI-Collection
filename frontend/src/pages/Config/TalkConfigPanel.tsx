import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Card,
  Table,
  Button,
  Drawer,
  Form,
  Input,
  Select,
  Space,
  Tag,
  Tooltip,
  message,
  Empty,
} from 'antd'
import { ReloadOutlined, PlusOutlined, EditOutlined } from '@ant-design/icons'
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
  RiskTier,
  TalkTemplateInput,
  TalkTemplateManage,
} from '../../types/api'

const { TextArea } = Input

const RISK_TIER_OPTIONS: { label: string; value: RiskTier }[] = [
  { label: '高风险', value: 'HIGH' },
  { label: '中风险', value: 'MEDIUM' },
  { label: '低风险', value: 'LOW' },
]

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

/** 话术配置后台：覆盖度矩阵 + 模板编辑抽屉（talk-003） */
export default function TalkConfigPanel() {
  const [coverage, setCoverage] = useState<CoverageMatrix | null>(null)
  const [templates, setTemplates] = useState<TalkTemplateManage[]>([])
  const [placeholders, setPlaceholders] = useState<Placeholder[]>([])
  const [loading, setLoading] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<TalkTemplateManage | null>(null)
  const [form] = Form.useForm<TalkTemplateInput>()

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

  /** 打开模板编辑抽屉（新建或编辑指定格子） */
  const openEditor = (cell?: CoverageCell) => {
    // 查该格现有模板（FIXED 优先显示）
    let existing: TalkTemplateManage | null = null
    if (cell) {
      existing =
        templates.find(
          (t) =>
            t.risk_tier === cell.risk_tier &&
            t.scene === cell.scene &&
            t.template_type === 'FIXED',
        ) || null
    }
    setEditing(existing)
    form.setFieldsValue({
      name: existing?.name || (cell ? `${cell.risk_tier}×${cell.scene}` : ''),
      risk_tier: cell?.risk_tier || ('HIGH' as RiskTier),
      scene: cell?.scene || 'ROUND_1',
      template_type: existing?.template_type || 'FIXED',
      content: existing?.content || '',
      system_prompt: existing?.system_prompt || '',
      user_prompt: existing?.user_prompt || '',
      is_active: existing?.is_active ?? true,
    })
    setDrawerOpen(true)
  }

  const onSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editing) {
        await updateTemplate(editing.id, values)
        message.success('话术模板已更新')
      } else {
        await createTemplate(values)
        message.success('话术模板已创建')
      }
      setDrawerOpen(false)
      loadData()
    } catch {
      /* 校验/接口错误由 antd + 全局拦截器处理 */
    }
  }

  const onDelete = async () => {
    if (!editing) return
    await deleteTemplate(editing.id)
    message.success('话术模板已删除')
    setDrawerOpen(false)
    loadData()
  }

  /** 矩阵表格列：风险档 / 轮次 / day_offset / FIXED / AI_PROMPT 状态 + 操作 */
  const columns: ColumnsType<CoverageCell> = [
    {
      title: '风险档',
      dataIndex: 'risk_tier',
      render: (tier: string) => <Tag color={TIER_COLOR[tier]}>{TIER_LABEL[tier] || tier}</Tag>,
    },
    {
      title: '轮次',
      dataIndex: 'scene',
      render: (scene: string) => `第${scene.replace('ROUND_', '')}轮（${scene}）`,
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
        <Button size="small" icon={<EditOutlined />} onClick={() => openEditor(record)}>
          {record.fixed_configured || record.ai_prompt_configured ? '编辑' : '配置'}
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
        按当前生效风险档配置的触达轮次展开。红色高亮格为缺口（固定模板/AI提示词未配），点击「配置」补充话术。
      </p>

      {!hasCoverage ? (
        <Empty description="尚无生效风险档配置，请先在上方「风险档配置」面板配置催收时点" />
      ) : (
        <Table<CoverageCell>
          rowKey={(r) => `${r.risk_tier}-${r.scene}`}
          columns={columns}
          dataSource={cells}
          loading={loading}
          pagination={false}
          size="small"
          rowClassName={(r) =>
            !r.fixed_configured || !r.ai_prompt_configured ? 'talk-missing-row' : ''
          }
        />
      )}

      <div style={{ marginTop: 12 }}>
        <Button type="dashed" icon={<PlusOutlined />} onClick={() => openEditor()}>
          新建话术模板
        </Button>
      </div>

      <Drawer
        title={editing ? '编辑话术模板' : '新建话术模板'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={640}
        extra={
          <Space>
            {editing && (
              <Button danger onClick={onDelete}>
                删除
              </Button>
            )}
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" onClick={onSubmit}>
              保存
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="模板名称"
            rules={[{ required: true, message: '请输入模板名称' }]}
          >
            <Input placeholder="如 HIGH×ROUND_2×FIXED" />
          </Form.Item>
          <Space style={{ display: 'flex' }} size="middle">
            <Form.Item
              name="risk_tier"
              label="风险档"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <Select options={RISK_TIER_OPTIONS} />
            </Form.Item>
            <Form.Item
              name="scene"
              label="轮次"
              rules={[{ required: true, message: '如 ROUND_1' }]}
              style={{ flex: 1 }}
            >
              <Input placeholder="ROUND_1" />
            </Form.Item>
            <Form.Item
              name="template_type"
              label="类型"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <Select
                options={[
                  { label: '固定模板（直接展示）', value: 'FIXED' },
                  { label: 'AI提示词（喂LLM生成）', value: 'AI_PROMPT' },
                ]}
              />
            </Form.Item>
          </Space>

          <Form.Item shouldUpdate noStyle>
            {({ getFieldValue }) =>
              getFieldValue('template_type') === 'FIXED' ? (
                <PlaceholderTextArea
                  name="content"
                  label="话术正文"
                  required
                  placeholders={placeholders}
                  placeholder="如：{供应商名称}您好，订单{订单号}（标的：{标的名称}）已逾期，请尽快缴费。"
                />
              ) : (
                <>
                  <PlaceholderTextArea
                    name="system_prompt"
                    label="System 提示词（追加在合规基线后）"
                    required
                    placeholders={placeholders}
                    placeholder="如：语气正式但紧迫，强调逾期对投标资格的影响。"
                  />
                  <PlaceholderTextArea
                    name="user_prompt"
                    label="User 提示词"
                    required
                    placeholders={placeholders}
                    placeholder="如：请为供应商{供应商名称}生成催收话术，订单{订单号}..."
                  />
                </>
              )
            }
          </Form.Item>

          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Select
              options={[
                { label: '启用', value: true },
                { label: '停用', value: false },
              ]}
            />
          </Form.Item>
        </Form>
      </Drawer>

      <style>{`
        .talk-missing-row td { background: #fff1f0 !important; }
      `}</style>
    </Card>
  )
}

/** 带「插入变量」下拉的 TextArea：点击变量插入到光标位置。 */
function PlaceholderTextArea({
  name,
  label,
  required,
  placeholders,
  placeholder,
}: {
  name: string
  label: string
  required?: boolean
  placeholders: Placeholder[]
  placeholder?: string
}) {
  const ref = useRef<{ focus: () => void; textarea?: HTMLTextAreaElement } | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  // 插入占位符到 TextArea 光标位置
  const insertPlaceholder = (key: string) => {
    const ta = inputRef.current
    if (!ta) return
    const start = ta.selectionStart ?? ta.value.length
    const end = ta.selectionEnd ?? ta.value.length
    const insert = `{${key}}`
    const newVal = ta.value.slice(0, start) + insert + ta.value.slice(end)
    // 用 Form 的 setFieldsValue 不可行（拿不到 form 实例），改用原生修改 + 触发 input 事件
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      'value',
    )?.set
    nativeInputValueSetter?.call(ta, newVal)
    ta.dispatchEvent(new Event('input', { bubbles: true }))
    setTimeout(() => {
      ta.focus()
      ta.setSelectionRange(start + insert.length, start + insert.length)
    }, 0)
  }

  return (
    <Form.Item
      name={name}
      label={label}
      rules={required ? [{ required: true, message: `请输入${label}` }] : undefined}
    >
      <div>
        <Space style={{ marginBottom: 4 }}>
          <span style={{ fontSize: 12, color: '#888' }}>插入变量：</span>
          {placeholders.slice(0, 6).map((p) => (
            <Tooltip key={p.key} title={p.description}>
              <Tag
                style={{ cursor: 'pointer' }}
                onClick={() => insertPlaceholder(p.key)}
              >
                {p.key}
              </Tag>
            </Tooltip>
          ))}
          <Select
            size="small"
            placeholder="更多变量…"
            style={{ width: 160 }}
            showSearch
            optionFilterProp="label"
            options={placeholders.map((p) => ({
              label: `${p.key}（${p.description}）`,
              value: p.key,
            }))}
            onChange={(key: string) => insertPlaceholder(key)}
            value={undefined}
          />
        </Space>
        <TextArea
          ref={ref as never}
          rows={5}
          placeholder={placeholder}
          onChange={(e) => {
            // 保持 inputRef 同步，供插入用
            inputRef.current = e.target as HTMLTextAreaElement
          }}
          onFocus={(e) => {
            inputRef.current = e.target as HTMLTextAreaElement
          }}
        />
      </div>
    </Form.Item>
  )
}
